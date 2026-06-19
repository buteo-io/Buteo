# Self-Hosting Quickstart Guide

This guide gets you from a fresh, blank Linux VPS to a fully functional, production-ready Buteo GPS logging system in under 15 minutes.

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
sudo mkdir -p /opt/buteo
sudo chown -R $USER:$USER /opt/buteo
cd /opt/buteo
```

### 1. Configure the `.env` File

Copy the template `.env.example` from the repository root to `/opt/buteo/.env`:
```bash
# Assuming you cloned or copied the repo contents
cp .env.example /opt/buteo/.env
```
Edit `.env` to set your domains, database type, and secrets. Crucial variables to set:
- **JWT_SECRET**: Generate with `openssl rand -hex 32` on your terminal.
- **DOMAIN** / **API_DOMAIN**: Set to your registered tracking domains.
- **DATA_DIR**: Set to your host data directory (e.g., `/opt/buteo/data`).
- **DATABASE_TYPE**: Set to `sqlite` or `postgres`.

### 2. Copy the `docker-compose.yml` File

Copy the production-ready `docker-compose.yml` from the repository root into `/opt/buteo/`.

The standard configuration is set up to utilize Traefik for automatic Let's Encrypt TLS certificate generation, routing `DOMAIN` to the frontend, `API_DOMAIN` to the API, and exposing tracking receiver ports (e.g. `5027`, `8766`).

A reverse proxy is recommended for the ingest service (parses incoming GPS data from tracking devices).

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

### 3. (Optional) Read-Only Account

```bash
# Create the demo account
docker compose run --rm api python -m tracker_core.cli.manage create-user \
  --email demo@yourdomain.com --password "YourPassword"

# Seed demo data (see seed-demo CLI command), then lock the account
docker compose run --rm api python -m tracker_core.cli.manage features grant \
  --email demo@yourdomain.com --feature read_only
```

A read-only account can log in and view all data normally, but every write operation (creating/editing/deleting trips, places, overnight spots, and share links) returns **403 Forbidden**. To re-enable writes at any time:

```bash
docker compose run --rm api python -m tracker_core.cli.manage features revoke \
  --email demo@yourdomain.com --feature read_only
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
