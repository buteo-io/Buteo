# TrackMy System Architecture

This document details the system design, component boundaries, data flow pipelines, and database relations for the TrackMy platform.

---

## 1. System Topology & Component Overview

TrackMy is a modular open-core platform separated into three principal services (`apps/api`, `apps/ingest`, `apps/web`) and a shared domain package (`packages/core/tracker_core`).

```mermaid
graph TD
    %% Clients
    subgraph Clients [Clients & Devices]
        device_tcp[Teltonika GPS Tracker<br/>TCP:5027]
        device_http[OsmAnd / OwnTracks Client<br/>HTTP:8766]
        browser[Web Browser / Mobile View<br/>HTTPS]
    end

    %% Edge Router
    subgraph Edge [Edge Router]
        traefik[Traefik Reverse Proxy<br/>Ports 80/443/5027/8766]
    end

    %% Internal Services
    subgraph CoreServices [Core Application Services]
        frontend[web-frontend<br/>Nginx / Ports 80]
        api[api-server<br/>FastAPI / Port 8765]
        ingest[ingest-server<br/>Python AsyncIO / Ports 5027, 8766]
    end

    %% Shared Library
    subgraph DomainPackage [Shared Core Package]
        core_lib[packages/core/tracker_core<br/>Models, Database engine, Analytics, Migrations]
    end

    %% Database
    subgraph Storage [Persistence]
        identity_db[(Central Identity DB<br/>SQLite / PostgreSQL)]
        tenant_dbs[(Tenant Isolated DBs<br/>tenant_*.db / tracker_tenant_*)]
    end

    %% Routing Flow
    device_tcp -->|GPRS TCP Handshake & AVL stream| traefik
    device_http -->|HTTP GET/POST location| traefik
    browser -->|Web Traffic| traefik

    traefik -->|Proxy to :5027| ingest
    traefik -->|Proxy to :8766| ingest
    traefik -->|Proxy to /| frontend
    traefik -->|Proxy to /api/* & /share/*| api

    %% Database Connection
    api -->|Authenticates & resolves route| identity_db
    api -->|Binds dynamic session| tenant_dbs
    ingest -->|Looks up IMEI route| identity_db
    ingest -->|Persists coordinate| tenant_dbs

    %% Package dependency representation
    api -.->|imports| core_lib
    ingest -.->|imports| core_lib
```

---

## 2. Shared Core Package (`packages/core/tracker_core`)

The monorepo centers around `tracker_core` to prevent duplication of logic across independent deployment units (API and Ingest).

- **`store/`**: SQLAlchemy ORM declarations (`models.py`) and transactional connection engines (`db.py`). 
- **`internal/appctx/`**: Pydantic-Settings declaration (`config.py`) parsing and validating environment configuration.
- **`analytics.py`**: Pure utility library for geographic and trip calculations (Haversine distances, path smoothing, spatial aggregation, trip isolation, export builders).
- **`overnight_service.py`**: Business-domain orchestrator for incremental overnight spot detection and merging logic.
- **`queries.py`**: Centralized, performance-optimized database queries with window constraints and safety caps.
- **`alembic/`**: Active database schema and step-by-step SQL migration paths.

---

## 3. Data Pipelines & Flows

### A. Location Ingest Data Flow

TrackMy supports high-frequency TCP stream tracking alongside intermittent HTTP pushing. Regardless of source protocol, data undergoes consistent filtering and parsing prior to persistence.

```mermaid
sequenceDiagram
    autonumber
    actor Dev as GPS Device / Client
    participant Ingest as Ingest Server
    participant IdentityDB as Central Identity DB
    participant TenantDB as Tenant Isolated DB
    participant Core as Core Analytics Engine

    alt HTTP Protocol (OsmAnd / Traccar / OwnTracks)
        Dev->>Ingest: HTTP GET/POST location payload
    else TCP Protocol (Teltonika Codec 8/8E)
        Dev->>Ingest: TCP Handshake (IMEI)
        Ingest-->>Dev: Accept Handshake
        Dev->>Ingest: Binary AVL packet stream
    end

    Note over Ingest: Resolve Client Identity & Credentials (IMEI / ID)
    Ingest->>IdentityDB: Query gps_devices (lookup tenant_id)
    IdentityDB-->>Ingest: Return tenant_id
    
    alt Device Unknown / Unmapped
        Ingest-->>Dev: Reject / Disconnect / HTTP 401
    else Device Mapped to Tenant
        Ingest->>TenantDB: Query Device Registry (verify active status in tenant DB)
        TenantDB-->>Ingest: Device Registered & Active?
        
        alt Device Revoked or Unknown
            Ingest-->>Dev: Reject / Disconnect / HTTP 401 or 410
        else Device Validated
            Note over Ingest: Extract coords, timestamp, speed, altitude, satellite stats
            Note over Ingest: Apply Ingest outlier filtering (spike defense)
            Ingest->>TenantDB: Insert Position record
            Ingest-->>Dev: Confirm Write (HTTP 200 / Codec ACK)
        end
    end
```

### B. Map Visualization and Share API Flow

```mermaid
sequenceDiagram
    autonumber
    actor Web as User / Public Guest
    participant API as API Server
    participant DB as Database
    participant Core as Core Analytics

    Web->>API: Request Trip Positions (e.g. GET /trips/{id}/positions)
    API->>DB: Fetch associated raw Position records in window
    DB-->>API: Return records
    API->>Core: Process positions (Haversine mileage, simplify path if requested)
    Core-->>API: Return computed geospatial track & bounds
    
    alt Shared Link Access
        Note over API: Apply Share Link Rules (Blur Radius, Delay Cutoff, Places inclusion)
        API->>Core: Apply blur corridor & date-bound filtering
    end
    
    API-->>Web: Serve standardized GeoJSON or JSON response
```

---

## 4. Database Schema (Entity Relationship Diagram)

TrackMy handles multiple trackers across different real-world entities (e.g., vehicles, individuals, pets). Below is the logical data model schema.

```mermaid
erDiagram
    User ||--o{ Device : "manages"
    User ||--o{ Place : "defines"
    User ||--o{ Tag : "owns"
    User ||--o{ ShareLink : "configures"
    User ||--o{ OvernightSpot : "owns"

    Entity ||--o{ Device : "binds to"
    Device ||--o{ Position : "records"
    Device ||--o{ Trip : "groups positions into"
    
    Trip ||--o{ OvernightSpot : "contains"
    
    Place ||--o{ PlaceMedia : "attaches"
    OvernightSpot ||--o{ OvernightSpotMedia : "attaches"
    
    %% Junction tables
    Place }|--|{ Trip : "place_trips (M:M)"
    ShareLink }|--|{ Place : "share_link_places (M:M)"
    ShareLink }|--|{ OvernightSpot : "share_link_overnight_spots (M:M)"

    User {
        int id PK
        uuid public_id UK
        string email UNIQUE
        string password_hash
        int token_version
        datetime created_at
    }

    Entity {
        int id PK
        uuid public_id UK
        string name
        string entity_type "vehicle | pet | person | tracker"
        datetime created_at
    }

    Device {
        int id PK
        uuid public_id UK
        string imei UNIQUE
        string name
        int user_id FK
        int entity_id FK
        datetime last_seen_at
        datetime revoked_at
    }

    Position {
        int id PK
        int device_id FK
        datetime time_id
        double lat
        double lon
        double speed
        double altitude
        int satellites
    }

    Trip {
        int id PK
        uuid public_id UK
        int device_id FK
        string name
        datetime started_at
        datetime ended_at "NULL if ongoing"
        datetime overnights_last_checked_position_time
    }

    Place {
        int id PK
        uuid public_id UK
        int user_id FK
        double lat
        double lon
        string name
        string notes
        int place_type_id FK
    }

    PlaceMedia {
        int id PK
        uuid public_id UK
        int place_id FK
        int user_id FK
        string filename_stored
        string media_type
        datetime created_at
    }

    Tag {
        int id PK
        int user_id FK
        string name
    }

    ShareLink {
        int id PK
        uuid public_id UK
        int user_id FK
        int trip_id FK
        string token "SHA-256 hashed"
        int delay_hours
        double blur_meters
        datetime expires_at
    }

    OvernightSpot {
        int id PK
        uuid public_id UK
        int user_id FK
        int trip_id FK
        double lat
        double lon
        int nights_count
        datetime last_stay_at
    }
```
