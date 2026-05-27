# STRUCTURE.md — Codebase Structure

```
Buteo/
├── apps/
│   ├── api/                        # REST API service
│   │   ├── api/
│   │   │   ├── main.py             # create_app(), lifespan, CORS, middleware, router wiring
│   │   │   ├── deps.py             # FastAPI dependencies: current_user, get_db, ownership
│   │   │   ├── ownership.py        # own_device / own_place / own_trip helpers (404 guards)
│   │   │   ├── schemas.py          # Shared Pydantic schemas (PositionOut, UTCModel)
│   │   │   ├── limiter.py          # slowapi Limiter singleton
│   │   │   ├── media_utils.py      # File upload validation helpers
│   │   │   ├── routers/
│   │   │   │   ├── auth.py         # POST /auth/login, /logout, GET /me
│   │   │   │   ├── trips.py        # CRUD + stats + positions + export (GPX/CSV)
│   │   │   │   ├── places.py       # CRUD + media
│   │   │   │   ├── overnight_spots.py  # detect, CRUD, media
│   │   │   │   ├── analytics.py    # /devices/{id}/trips, /overnights, /mileage, /summary
│   │   │   │   ├── share_links.py  # CRUD + rotate + revoke
│   │   │   │   ├── public_share.py # Unauthenticated /share/:token endpoints
│   │   │   │   ├── devices.py      # Device listing / revocation
│   │   │   │   ├── entities.py     # Entity CRUD
│   │   │   │   ├── positions.py    # Raw position queries
│   │   │   │   └── media.py        # Media serve endpoint
│   │   │   ├── plugins/
│   │   │   │   ├── loader.py       # Dynamic plugin discovery + mounting
│   │   │   │   └── dummy/          # Reference plugin skeleton
│   │   │   └── tests/              # pytest integration tests (~19 files)
│   │   └── requirements.txt
│   │
│   ├── ingest/                     # Location ingest service
│   │   └── ingest/
│   │       ├── osmand/
│   │       │   ├── api.py          # FastAPI app: /traccar_client, /owntracks
│   │       │   └── helpers.py      # _ingest_one, IMEI → tenant routing, position write
│   │       └── codec8/             # Teltonika binary protocol parser + TCP server
│   │
│   └── web/                        # React SPA
│       └── src/
│           ├── App.tsx             # Top-level state orchestrator (~977 lines)
│           ├── api.ts              # Typed fetch wrapper + all API calls
│           ├── auth.tsx            # AuthProvider, useAuth hook
│           ├── main.tsx            # ReactDOM root, route split (app vs /share/:token), PWA SW
│           ├── i18n.ts             # i18next init
│           ├── components/         # Map, Sidebar, Modal, EntityModal, PlaceTypeIcon, etc.
│           ├── contexts/           # DateRangeContext, EntityContext, MapStateContext
│           ├── hooks/              # useLivePoll, useTheme, useEntityForm
│           ├── modals/             # DetailsModal, GalleryModal, OvernightSpotModal, PlaceModal, TripModal, EntityDetailsModal
│           ├── panels/             # DevicesPanel, ExportPanel, PlacesPanel, SettingsPanel, SharePanel, TripsPanel
│           ├── pages/              # Login, PublicShare
│           ├── plugins/            # Frontend plugin registry + dummy
│           ├── utils/              # time.ts, ...
│           └── locales/            # Translation JSON files
│
├── packages/
│   └── core/tracker_core/          # Shared Python package
│       ├── store/
│       │   ├── models.py           # All ORM models (User→Entity→Device→Position→Trip→OvernightSpot→Place→ShareLink)
│       │   ├── identity_db.py      # Identity engine, Tenant, GPSDevice models, init_identity_db
│       │   ├── core_db.py          # Tenant engine base, init_core_db
│       │   ├── tenant_db_manager.py # TenantDatabaseManager singleton
│       │   ├── security.py         # JWT make/parse/verify, bcrypt, share token hash
│       │   └── ids.py              # PrefixUUID type, gen_public_id, gen_tenant_id
│       ├── analytics.py            # Haversine, stop/trip/overnight detection, GPX/CSV export
│       ├── overnight_service.py    # detect_and_persist_overnights, _merge_consecutive_overnights
│       ├── queries.py              # positions_in_window_capped (200k cap)
│       ├── alembic/                # Core DB migrations
│       ├── cli/
│       │   ├── manage.py           # Admin CLI (create-user, create-entity, etc.)
│       │   └── seed_demo.py        # Demo data seeder (uses OSRM for realistic routes)
│       └── internal/appctx/
│           └── config.py           # AppConfig (pydantic-settings)
│
├── deployments/docker/             # Dockerfiles for api, ingest, web
├── docs/                           # architecture.md, deployment.md, env vars docs
├── scripts/                        # backup_db.py, mock_tracker.py
├── docker-compose.yml
└── .env.example
```

## Key File Sizes / Complexity Signals
| File | Lines | Notes |
|---|---|---|
| `App.tsx` | ~977 | Largest file; owns all frontend state |
| `styles.css` | 54 KB | Likely Tailwind build output |
| `store/models.py` | 528 | All ORM models |
| `share_links.py` | 437 | Complex privacy filter logic |
| `public_share.py` | 435 | Unauthenticated share endpoint |
| `seed_demo.py` | 20 KB | Demo data generator |
| `manage.py` | 16 KB | CLI |
| `pyproject.toml` | 165 | Ruff config |
