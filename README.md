<div align="center">

<img src="apps/web/public/buteo-eagle-logo-lg.svg" alt="Buteo" width="200" />

# Buteo

### Know where it is. Remember where it's been.

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)

</div>

---

Buteo is a **travel memory and location companion**. It helps you always know where your device is and easily turn your location history into trips, memories, custom places, photos, videos, and travel stories.

Built for road trips, not fleet management. Self-hosted, privacy-first, and designed to help you remember the journey.

---

## ✨ Key Features

| Feature | What it does |
|---------|-------------|
| 🗺️ **Live Device Location** | See your device's current position on a beautiful map — anytime, anywhere. |
| 📍 **Trip History** | Simple, one-click trip generation from raw GPS data. Browse and manage past adventures. |
| 🏕️ **Save Special Places** | Bookmark and remember your favorite campsites, viewpoints, water spots, or hidden gems. |
| 📸 **Photos & Memories** | Link photos and videos directly to your spots and trips. Build a visual travel journal. |
| 📱 **Bring Your Own Device** | Connect a proper hardware GPS tracker (like Teltonika) or just use an old smartphone. |
| 🔒 **Privacy-First** | Your location data stays yours. No tracking, no selling, no surprises. |
| 🐳 **Self-Hosted with Docker** | Run everything on your own hardware. Full control, no subscriptions. |
| ☁️ **Hosted Option Coming Soon** | Prefer convenience? We'll offer a managed cloud version soon. |

---

## Why Buteo?

### Not fleet software. Not surveillance.

Most GPS apps are built for businesses tracking delivery trucks. They're cold, clinical, and designed for fleet managers — not travelers. Other consumer track-and-share solutions are often overpriced, locking you into expensive, proprietary tracking hardware or charge high prices for hardware that you could get yourself for half the price.

**Buteo is different.**

- **Bring your own hardware:** Don't pay 150+€ for a locked-down tracker. Use any standard tracker (40-80€) like Teltonika FMC920, or turn an old smartphone into a tracker using free open-source apps (Traccar Client / OwnTracks / ...).
- **One-click trips:** It just works. No over-engineered, buggy "AI trip detection". Just review your raw tracking points and trigger a clean, exact trip whenever you want.
- **Built for memories, not monitoring:** Designed to help you remember where you've been, not spy on your driving or measure fleet efficiency.
- **Own your data:** If you self-host, your location history never leaves your server. Period.
- **Warm & simple:** An adventure-oriented design that feels like a travel journal, not a corporate asset-tracking dashboard.

---

## 🚀 Quick Start

### 1. Clone Buteo

```bash
git clone https://github.com/buteo-io/Buteo.git
cd Buteo
```

### 2. Configure Environment

Copy the example configuration and adjust the values (like secrets and passwords) for your deployment:

```bash
cp .env.example .env
```

Choose your `DATABASE_TYPE` and `DATA_DIR` in the `.env` file.

### 3. Start with Docker Compose

```bash
docker compose up -d --build
```

Open **http://localhost:5124** in your browser.

### 4. Create your account

```bash
docker compose run --rm api python -m tracker_core.cli.manage create-user \
  --email you@example.com --password "your-secure-password"
```

### 5. Add your tracker

```bash
docker compose run --rm api python -m tracker_core.cli.manage create-device \
  --email you@example.com --imei 123456789012345 --name "Our Camper"
```

---

## 📸 Screenshots

<div align="center">

| Map View | Trip History |
|----------|--------------|
| ![Map](docs/screenshots/map-placeholder.png) | ![Trips](docs/screenshots/trips-placeholder.png) |

| Places Panel | Share Link |
|--------------|------------|
| ![Places](docs/screenshots/places-placeholder.png) | ![Share](docs/screenshots/share-placeholder.png) |

</div>

---

## 🗺️ Roadmap

We're building Buteo in the open. Here's where we're headed:

- [x] Progressive Web App (PWA) for seamless cross-device compatibility
- [ ] **Hosted cloud version** (managed service)
- [ ] Trip export (GPX, KML)
- [ ] Offline map tiles
- [ ] Automatic travel stories from photos and videos
- [ ] Mobile app (iOS/Android)

[View full roadmap →](https://github.com/orgs/buteo-io/projects)

---

## 🤝 Contributing

We welcome contributions! Whether you're a developer, designer, or just want to share ideas.

### Development Setup

```bash
# Local development
docker compose up -d --build

# Run tests
pytest apps/api/api/tests/

# Lint
ruff check apps/api apps/ingest packages/core
```

### Ways to Contribute

- 🐛 **Report bugs** — Open an issue
- 💡 **Request features** — Start a discussion
- 🔧 **Submit PRs** — Fork and contribute
- 📖 **Improve docs** — Help others get started
- 🌍 **Translate** — Make Buteo accessible globally

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

---

## 📄 License

Buteo is licensed under the **GNU Affero General Public License v3 (AGPL-3.0)**. 
See the [LICENSE](LICENSE) file for the full text.

- **Self-host freely.**
- **Commercial licensing available upon request.**
- **Software is provided "as-is", without warranty of any kind. Use at your own risk.** Updates may introduce breaking changes.

---

## 🔗 Links

- 🌐 **Website**: [https://getbuteo.com](https://getbuteo.com) *(coming soon)*
- 🐙 **GitHub**: [https://github.com/buteo-io](https://github.com/buteo-io)
- 📖 **Documentation**: [docs/](docs/)

---

<div align="center">

**Built with ❤️ for vanlife travelers everywhere**

</div>
