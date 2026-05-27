# Self-Hosting Quickstart Guide

This guide gets you from a fresh, blank Linux VPS to a fully functional, production-ready TrackMy GPS logging system in under 15 minutes.

---

## Step 1: Provision a Server & Setup DNS

1. Rent a small Virtual Private Server (VPS) from any provider (Hetzner, DigitalOcean, Linode, Scaleway, etc.). 
   - **Recommended Specs**: 1 vCPU, 1 GB RAM, 20 GB SSD.
   - **Operating System**: Ubuntu 22.04 LTS or 24.04 LTS.
2. Log in to your DNS provider and configure two `A` (or `AAAA`) records pointing to your VPS public IPv4/IPv6 address:
   - `track.yourdomain.com` (Frontend dashboard)
   - `api.track.yourdomain.com` (Backend API router)

---

## Step 2: Install Docker and Compose

On your clean VPS, run the official Docker installation script:

```bash
# Update packages and install curl
sudo apt-get update && sudo apt-get install -y curl

# Install Docker engine
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add your user to the docker group so you don't need sudo
sudo usermod -aG docker $USER
```
*Note: Log out and log back in to apply group privileges, or run `newgrp docker`.*

---

## Step 3: Establish Folder Structure and Configuration

Create a dedicated application directory:
```bash
sudo mkdir -p /opt/trackmy
sudo chown -R $USER:$USER /opt/trackmy
cd /opt/trackmy
```

### 1. Create a `.env` File
Create a `.env` file (`nano .env`) and populate it with your domain names and secrets:

```ini
# Generate a secret: run `openssl rand -hex 32` on your local terminal
JWT_SECRET=f3a8b4c731e9c2f6d0a7a3b4c5e6f1a2a3b4c5e6f7a8b9c0d1e2f3a4b5c6d7e8

# Domain names
DOMAIN=track.yourdomain.com
API_DOMAIN=api.track.yourdomain.com

# Persist to local data directory
DATA_DIR=/opt/trackmy/data

# Secure production cookies
AUTH_COOKIE_SECURE=true
DEV_INSECURE_COOKIES=false

# CORS Configuration
CORS_ORIGINS=https://track.yourdomain.com
```

### 2. Create the `docker-compose.yml` File
Create a `docker-compose.yml` file (`nano docker-compose.yml`) containing the production topology. Here is the standard production configuration utilizing Traefik for automatic Let's Encrypt TLS:

```yaml
version: '3.8'

networks:
  traefik:
    external: true

services:
  # Traefik Reverse Proxy & TLS Provisioner
  traefik:
    image: traefik:v2.10
    container_name: traefik
    restart: always
    command:
      - "--providers.docker=true"
      - "--providers.docker.exposedbydefault=false"
      - "--entrypoints.web.address=:80"
      - "--entrypoints.websecure.address=:443"
      - "--entrypoints.web.http.redirections.entrypoint.to=websecure"
      - "--entrypoints.web.http.redirections.entrypoint.scheme=https"
      - "--certificatesresolvers.letsencrypt.acme.tlschallenge=true"
      - "--certificatesresolvers.letsencrypt.acme.email=your-email@yourdomain.com"
      - "--certificatesresolvers.letsencrypt.acme.storage=/letsencrypt/acme.json"
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - "/var/run/docker.sock:/var/run/docker.sock:ro"
      - "./letsencrypt:/letsencrypt"
    networks:
      - traefik

  # Web UI (React SPA served by Nginx)
  frontend:
    image: ghcr.io/mrtnz/trackmy-web:latest  # Or build locally if self-compiling
    container_name: trackmy-frontend
    restart: always
    environment:
      - API_UPSTREAM=api:8765
    networks:
      - traefik
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.frontend.rule=Host(`${DOMAIN}`)"
      - "traefik.http.routers.frontend.entrypoints=websecure"
      - "traefik.http.routers.frontend.tls=true"
      - "traefik.http.routers.frontend.tls.certresolver=letsencrypt"

  # Core API Server
  api:
    image: ghcr.io/mrtnz/trackmy-api:latest  # Or build locally
    container_name: trackmy-api
    restart: always
    env_file: .env
    environment:
      - DATA_DIR=/data
    volumes:
      - "./data:/data"
    networks:
      - traefik
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.api.rule=Host(`${API_DOMAIN}`)"
      - "traefik.http.routers.api.entrypoints=websecure"
      - "traefik.http.routers.api.tls=true"
      - "traefik.http.routers.api.tls.certresolver=letsencrypt"

  # GPS Ingest Listeners (TCP + HTTP)
  ingest:
    image: ghcr.io/mrtnz/trackmy-ingest:latest  # Or build locally
    container_name: trackmy-ingest
    restart: always
    env_file: .env
    environment:
      - DATA_DIR=/data
    volumes:
      - "./data:/data"
    ports:
      - "5027:5027"  # Codec 8 TCP
      - "8766:8766"  # OsmAnd HTTP
    networks:
      - traefik
```

---

## Step 4: Bootstrapping the Docker Network & Starting Services

1. Initialize the required docker network:
   ```bash
   docker network create traefik
   ```
2. Start the services. They will download, configure, and dynamically provision free Let's Encrypt certificates:
   ```bash
   docker compose up -d
   ```

---

## Step 5: Provision Accounts

Create your administrator credentials and register your tracker IMEI.

### 1. Create Login User Account
```bash
docker compose run --rm api python -m tracker_core.cli.manage create-user \
  --email your-email@yourdomain.com --password "LongAndUniqueAdminPassword"
```

### 2. Register Your GPS Tracking Device
```bash
docker compose run --rm api python -m tracker_core.cli.manage create-device \
  --email your-email@yourdomain.com --imei 123456789012345 --name "My Vehicle"
```

---

## Step 6: Configure Your Tracking Clients

Now link your physical tracker or mobile app to the server!

### Option A: Traccar Client (iOS / Android App)
This is the easiest mobile tracking setup.

1. Download **Traccar Client** from the App Store or Google Play Store.
2. Open the App settings:
   - **Device Identifier**: Enter the registered IMEI (e.g. `123456789012345`).
   - **Server URL**: `http://api.track.yourdomain.com:8766/traccar_client`
   - **Frequency**: `30` (seconds).
3. Toggle the status button to **Active/On**.

### Option B: OwnTracks (iOS / Android App)
OwnTracks sends location data in standard JSON payloads.

1. Download **OwnTracks** from your app store.
2. In the app configuration, change Mode to **HTTP**:
   - **URL**: `http://api.track.yourdomain.com:8766/owntracks`
   - **Identification**: Set custom User ID or Client ID to your IMEI.
   - **Custom Headers**: Add `X-Limit-D: 123456789012345` (replace with your exact device IMEI).

### Option C: Teltonika FMC920 / FMB920 (Hardware Tracker)
For standalone, direct GPRS vehicle trackers:

1. Connect your tracker to a computer using its USB config tool.
2. Navigate to **GPRS** Settings:
   - **Domain**: Enter your server's IP address or `api.track.yourdomain.com`.
   - **Port**: `5027`
   - **Protocol**: `TCP`
3. Configure your SIM card APN settings so the tracker is connected to cellular data.

---

## Step 7: Log In!

Open a browser and navigate to `https://track.yourdomain.com`.
- Log in using the email and password you created in **Step 5**.
- You should see your user dashboard, device listing, and map showing your current live positions!
