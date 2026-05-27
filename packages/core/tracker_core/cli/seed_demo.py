"""Seed realistic dummy trips for a device.

Generates round-trips from Dresden to Stockholm, Barcelona, Albania and Toulouse
spread across 2024 -> today, including overnight stays at every leg waypoint.
Outbound and return legs use distinct waypoints so they show as different routes
on the map.

Usage:
    docker compose run --rm api python -m tracker_core.cli.seed_demo \
        --email demo@x.test --imei 123456789012345 [--wipe]
"""

from __future__ import annotations

import argparse
import asyncio
import bisect
import math
import os
import random
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone

import httpx
from sqlalchemy import delete, select

from tracker_core.custom_logger import configure_logging
from tracker_core.store.core_db import CoreSessionLocal as SessionLocal
from tracker_core.store.core_db import init_core_db as init_db
from tracker_core.store.identity_db import GPSDevice, IdentitySessionLocal, Tenant
from tracker_core.store.models import Device, Entity, Position, User
from tracker_core.store.tenant_db_manager import current_tenant_id, tenant_db_manager

OSRM_BASE = os.environ.get("OSRM_URL", "https://router.project-osrm.org")

# --- geography -------------------------------------------------------------

# (lat, lon)
DRESDEN = (51.0504, 13.7373)

ROUTES: dict[str, dict[str, list[tuple[float, float]]]] = {
    "stockholm": {
        # Dresden -> Berlin -> Magdeburg -> Rostock -> Trelleborg ferry -> Malmö -> Jönköping -> Stockholm
        "out": [
            DRESDEN,
            (52.5200, 13.4050),  # Berlin
            (52.1205, 11.6276),  # Magdeburg
            (54.0833, 12.1333),  # Rostock
            (55.3753, 13.1569),  # Trelleborg
            (55.6050, 13.0038),  # Malmö
            (57.7826, 14.1618),  # Jönköping
            (59.3293, 18.0686),  # Stockholm
        ],
        # Stockholm -> Uppsala -> Copenhagen -> Hamburg -> Hanover -> Dresden
        "back": [
            (59.3293, 18.0686),
            (59.8586, 17.6389),  # Uppsala
            (55.6761, 12.5683),  # Copenhagen
            (53.5511, 9.9937),  # Hamburg
            (52.3759, 9.7320),  # Hanover
            DRESDEN,
        ],
    },
    "barcelona": {
        # Dresden -> Leipzig -> Nürnberg -> Stuttgart -> Strasbourg -> Lyon -> Nîmes -> Barcelona
        "out": [
            DRESDEN,
            (51.3397, 12.3731),  # Leipzig
            (49.4521, 11.0767),  # Nürnberg
            (48.7758, 9.1829),  # Stuttgart
            (48.5734, 7.7521),  # Strasbourg
            (45.7640, 4.8357),  # Lyon
            (43.8387, 4.3601),  # Nîmes
            (41.3851, 2.1734),  # Barcelona
        ],
        # Barcelona -> Perpignan -> Marseille -> Turin -> Milan -> Innsbruck -> Munich -> Dresden
        "back": [
            (41.3851, 2.1734),
            (42.6980, 2.8956),  # Perpignan
            (43.2965, 5.3698),  # Marseille
            (45.0703, 7.6869),  # Turin
            (45.4642, 9.1900),  # Milan
            (47.2692, 11.4041),  # Innsbruck
            (48.1351, 11.5820),  # Munich
            DRESDEN,
        ],
    },
    "albania": {
        # Dresden -> Leipzig -> Prague -> Bratislava -> Budapest -> Subotica -> Belgrade -> Niš -> Skopje -> Tirana
        "out": [
            DRESDEN,
            (51.3397, 12.3731),  # Leipzig
            (50.0755, 14.4378),  # Prague
            (48.1486, 17.1077),  # Bratislava
            (47.4979, 19.0402),  # Budapest
            (46.1000, 19.6500),  # Subotica
            (44.7866, 20.4489),  # Belgrade
            (43.3209, 21.8954),  # Niš
            (41.9981, 21.4254),  # Skopje
            (41.3275, 19.8189),  # Tirana
        ],
        # Tirana -> Podgorica -> Dubrovnik -> Split -> Zadar -> Ljubljana -> Salzburg -> Vienna -> Prague -> Dresden
        "back": [
            (41.3275, 19.8189),
            (42.4304, 19.2594),  # Podgorica
            (42.6507, 18.0944),  # Dubrovnik
            (43.5081, 16.4402),  # Split
            (44.1194, 15.2319),  # Zadar
            (46.0569, 14.5058),  # Ljubljana
            (47.8095, 13.0550),  # Salzburg
            (48.2082, 16.3738),  # Vienna
            (50.0755, 14.4378),  # Prague
            DRESDEN,
        ],
    },
    "toulouse": {
        # Dresden -> Leipzig -> Frankfurt -> Mannheim -> Strasbourg -> Lyon -> Carcassonne -> Toulouse
        "out": [
            DRESDEN,
            (51.3397, 12.3731),  # Leipzig
            (50.1109, 8.6821),  # Frankfurt
            (49.4875, 8.4660),  # Mannheim
            (48.5734, 7.7521),  # Strasbourg
            (45.7640, 4.8357),  # Lyon
            (43.2130, 2.3500),  # Carcassonne
            (43.6047, 1.4442),  # Toulouse
        ],
        # Toulouse -> Bordeaux -> La Rochelle -> Nantes -> Rennes -> Paris -> Reims -> Cologne -> Dresden
        "back": [
            (43.6047, 1.4442),
            (44.8378, -0.5792),  # Bordeaux
            (46.1600, -1.1500),  # La Rochelle
            (47.2184, -1.5526),  # Nantes
            (48.1173, -1.6778),  # Rennes
            (48.8566, 2.3522),  # Paris
            (49.2583, 4.0311),  # Reims
            (50.9375, 6.9603),  # Cologne
            DRESDEN,
        ],
    },
}


# Schedule (start dates) for each round-trip. ~one trip per quarter.
SCHEDULE: list[tuple[str, datetime]] = [
    ("stockholm", datetime(2024, 3, 15, 9, 0, tzinfo=timezone.utc)),
    ("barcelona", datetime(2024, 6, 7, 9, 0, tzinfo=timezone.utc)),
    ("albania", datetime(2024, 9, 12, 9, 0, tzinfo=timezone.utc)),
    ("toulouse", datetime(2024, 11, 22, 9, 0, tzinfo=timezone.utc)),
    ("stockholm", datetime(2025, 4, 4, 9, 0, tzinfo=timezone.utc)),
    ("barcelona", datetime(2025, 7, 18, 9, 0, tzinfo=timezone.utc)),
    ("albania", datetime(2025, 10, 3, 9, 0, tzinfo=timezone.utc)),
    ("toulouse", datetime(2026, 2, 14, 9, 0, tzinfo=timezone.utc)),
]


# --- math utilities --------------------------------------------------------


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    R = 6371.0088
    la1, lo1 = math.radians(a[0]), math.radians(a[1])
    la2, lo2 = math.radians(b[0]), math.radians(b[1])
    dlat = la2 - la1
    dlon = lo2 - lo1
    h = math.sin(dlat / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def jitter(scale_deg: float = 0.0008) -> float:
    return random.gauss(0.0, scale_deg)


def jitter_within_circle(at: tuple[float, float], radius_meters: float = 20.0) -> tuple[float, float]:
    r = math.sqrt(random.uniform(0, 1)) * radius_meters
    theta = random.uniform(0, 2 * math.pi)
    dy = r * math.sin(theta)
    dx = r * math.cos(theta)
    lat = at[0] + (dy / 111000.0)
    lon = at[1] + (dx / (111000.0 * math.cos(math.radians(at[0]))))
    return lat, lon


def split_polyline_into_days(coords: list[tuple[float, float]]) -> list[list[tuple[float, float]]]:
    if not coords or len(coords) < 2:
        return [coords] if coords else []
    coords_copy = list(coords)
    days: list[list[tuple[float, float]]] = []
    current_day_coords: list[tuple[float, float]] = [coords_copy[0]]
    current_day_km = 0.0
    max_day_km = random.randint(150, 250)
    i = 0
    while i < len(coords_copy) - 1:
        p1 = coords_copy[i]
        p2 = coords_copy[i + 1]
        d = haversine_km(p1, p2)
        if current_day_km + d <= max_day_km:
            current_day_coords.append(p2)
            current_day_km += d
            i += 1
        else:
            needed = max_day_km - current_day_km
            u = needed / (d or 1e-9)
            split_lat = lerp(p1[0], p2[0], u)
            split_lon = lerp(p1[1], p2[1], u)
            split_p = (split_lat, split_lon)
            current_day_coords.append(split_p)
            days.append(current_day_coords)
            current_day_coords = [split_p]
            current_day_km = 0.0
            max_day_km = random.randint(150, 250)
            coords_copy[i] = split_p
    if len(current_day_coords) > 1:
        days.append(current_day_coords)
    return days


# --- generators ------------------------------------------------------------


@dataclass
class GenPoint:
    time_id: datetime
    lat: float
    lon: float
    speed: float
    altitude: float | None
    satellites: int


async def osrm_route(
    client: httpx.AsyncClient,
    a: tuple[float, float],
    b: tuple[float, float],
) -> list[tuple[float, float]] | None:
    """Fetch driving polyline from OSRM as list of (lat, lon). None on failure."""
    url = f"{OSRM_BASE}/route/v1/car/{a[1]:.6f},{a[0]:.6f};{b[1]:.6f},{b[0]:.6f}"
    try:
        r = await client.get(
            url,
            params={"overview": "full", "geometries": "geojson"},
            timeout=30.0,
        )
        r.raise_for_status()
        data = r.json()
        coords = data["routes"][0]["geometry"]["coordinates"]
        return [(c[1], c[0]) for c in coords]
    except Exception as e:
        print(f"  OSRM fail {a} -> {b}: {e}; falling back to straight line")
        return None


def _sample_along(
    coords: list[tuple[float, float]],
    n_samples: int,
) -> tuple[list[tuple[float, float]], float]:
    """Sample n_samples+1 evenly-spaced points along a (lat, lon) polyline.
    Returns (points, total_distance_km).
    """
    seg = [haversine_km(coords[i], coords[i + 1]) for i in range(len(coords) - 1)]
    cum = [0.0]
    for s in seg:
        cum.append(cum[-1] + s)
    total = cum[-1] or 1e-9
    out: list[tuple[float, float]] = []
    for i in range(n_samples + 1):
        d = (i / n_samples) * total
        j = max(0, min(len(coords) - 2, bisect.bisect_right(cum, d) - 1))
        seg_len = seg[j] or 1e-9
        u = (d - cum[j]) / seg_len
        lat = lerp(coords[j][0], coords[j + 1][0], u)
        lon = lerp(coords[j][1], coords[j + 1][1], u)
        out.append((lat, lon))
    return out, total


async def gen_drive_leg(
    client: httpx.AsyncClient | None,
    start_ts: datetime,
    a: tuple[float, float],
    b: tuple[float, float],
    avg_kmh: float = 85.0,
    sample_s: int = 60,
    poly: list[tuple[float, float]] | None = None,
) -> list[GenPoint]:
    """Drive from a to b along OSRM-routed roads (or straight line on failure).

    Real device-like cadence: sample every `sample_s` seconds with realistic
    speed profile (ramp up / cruise / ramp down + noise).
    """
    if poly is None:
        if client is not None:
            poly = await osrm_route(client, a, b)
        if not poly or len(poly) < 2:
            poly = [a, b]

    # actual road distance from polyline
    seg_total = sum(haversine_km(poly[i], poly[i + 1]) for i in range(len(poly) - 1))
    hours = max(0.5, seg_total / avg_kmh)
    duration = timedelta(hours=hours)
    n = max(2, int(duration.total_seconds() / sample_s))

    pts, _ = _sample_along(poly, n)
    out: list[GenPoint] = []
    for i, (lat, lon) in enumerate(pts):
        t = i / n
        if t < 0.05:
            sp = lerp(0, avg_kmh, t / 0.05)
        elif t > 0.95:
            sp = lerp(avg_kmh, 0, (t - 0.95) / 0.05)
        else:
            sp = avg_kmh + random.gauss(0, 10)
        sp = max(0.0, min(135.0, sp))
        ts = start_ts + duration * t
        out.append(
            GenPoint(
                time_id=ts,
                lat=lat + jitter(0.00005),
                lon=lon + jitter(0.00005),
                speed=sp,
                altitude=100 + random.gauss(0, 30),
                satellites=random.randint(7, 12),
            ),
        )
    return out


def gen_overnight(
    start_ts: datetime,
    at: tuple[float, float],
    hours: float = 11.0,
) -> list[GenPoint]:
    """Stationary points covering the overnight period (so detector fires)."""
    samples_per_hour = 4  # one every 15 min
    out: list[GenPoint] = []
    n = int(hours * samples_per_hour)
    for i in range(n):
        ts = start_ts + timedelta(hours=i / samples_per_hour)
        lat, lon = jitter_within_circle(at, radius_meters=20.0)
        out.append(
            GenPoint(
                time_id=ts,
                lat=lat,
                lon=lon,
                speed=0.0,
                altitude=80.0,
                satellites=random.randint(6, 10),
            ),
        )
    return out


async def gen_round_trip(
    client: httpx.AsyncClient | None,
    name: str,
    start_dt: datetime,
) -> list[GenPoint]:
    route = ROUTES[name]
    pts: list[GenPoint] = []
    cur = start_dt
    for direction in ("out", "back"):
        wps = route[direction]
        full_poly = []
        for i in range(len(wps) - 1):
            poly = None
            if client is not None:
                poly = await osrm_route(client, wps[i], wps[i + 1])
            if not poly or len(poly) < 2:
                poly = [wps[i], wps[i + 1]]

            if not full_poly:
                full_poly.extend(poly)
            else:
                full_poly.extend(poly[1:])

        day_polys = split_polyline_into_days(full_poly)
        for day_idx, day_poly in enumerate(day_polys):
            leg = await gen_drive_leg(client, cur, day_poly[0], day_poly[-1], poly=day_poly)
            pts.extend(leg)
            cur = leg[-1].time_id

            # overnight at every intermediate stop (incl. destination between out and back)
            is_last_day_of_direction = day_idx == len(day_polys) - 1
            is_last_day_of_round_trip = (direction == "back") and is_last_day_of_direction

            if not is_last_day_of_round_trip:
                if direction == "out" and is_last_day_of_direction:
                    # main destination stay: 4 to 8 nights
                    num_nights = random.randint(4, 8)
                else:
                    # intermediate stops: 1 to 3 nights
                    # 45% chance 1 night, 40% chance 2 nights, 15% chance 3 nights
                    r = random.random()
                    if r < 0.45:
                        num_nights = 1
                    elif r < 0.85:
                        num_nights = 2
                    else:
                        num_nights = 3

                departure_jitter_mins = random.randint(-30, 30)
                next_departure = datetime.combine(
                    cur.date() + timedelta(days=num_nights),
                    time(9, 0),
                    tzinfo=timezone.utc,
                ) + timedelta(minutes=departure_jitter_mins)
                stay_hours = (next_departure - cur).total_seconds() / 3600.0
                if stay_hours < 1.0:
                    stay_hours = 11.0 + random.uniform(-1, 1)
                    next_departure = cur + timedelta(hours=stay_hours)

                ov = gen_overnight(cur, day_poly[-1], hours=stay_hours)
                pts.extend(ov)
                cur = next_departure
    return pts


# --- DB writer -------------------------------------------------------------


async def insert_points(device_id: int, points: list[GenPoint]) -> int:
    BATCH = 1000
    total = 0
    async with SessionLocal() as db:
        for i in range(0, len(points), BATCH):
            chunk = points[i : i + BATCH]
            rows = [
                Position(
                    device_id=device_id,
                    time_id=p.time_id,
                    lon=p.lon,
                    lat=p.lat,
                    altitude=p.altitude,
                    speed=p.speed,
                    satellites=p.satellites,
                )
                for p in chunk
            ]
            db.add_all(rows)
            await db.commit()
            total += len(rows)
            print(f"  inserted {total}/{len(points)}")
    return total


async def main() -> None:  # noqa: C901
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True)
    ap.add_argument("--imei", required=True)
    ap.add_argument(
        "--wipe",
        action="store_true",
        help="Delete existing positions for the device",
    )
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument(
        "--no-osrm",
        action="store_true",
        help="Skip OSRM road snapping; use straight-line interpolation",
    )
    args = ap.parse_args()

    random.seed(args.seed)

    # 1. Resolve tenant from email in identity DB
    async with IdentitySessionLocal() as id_s:
        tenant = await id_s.scalar(select(Tenant).where(Tenant.email == args.email.strip().lower()))
        if not tenant:
            raise SystemExit(f"tenant with email {args.email!r} not found in identity DB")

        # 2. Register GPSDevice routing in identity DB if not registered
        existing_gps = await id_s.scalar(select(GPSDevice).where(GPSDevice.imei == args.imei))
        if not existing_gps:
            gps_device = GPSDevice(imei=args.imei, tenant_id=tenant.tenant_id)
            id_s.add(gps_device)
            await id_s.commit()
            print(f"registered device {args.imei} routing in identity DB for tenant {tenant.tenant_id}")
        elif existing_gps.tenant_id != tenant.tenant_id:
            raise SystemExit(
                f"device imei {args.imei} is already registered to a different tenant: {existing_gps.tenant_id}",
            )

        tenant_id = tenant.tenant_id

    # 3. Ensure tenant database is migrated/initialized
    tenant_url = tenant_db_manager.get_tenant_url(tenant_id)
    await init_db(tenant_url)

    # 4. Set tenant context so SessionLocal() routes correctly
    current_tenant_id.set(tenant_id)

    async with SessionLocal() as db:
        user = (await db.scalars(select(User).where(User.email == args.email))).first()
        if not user:
            raise SystemExit(f"local user {args.email!r} not found inside tenant database")

        # Find or create a Campervan entity
        entity = (await db.scalars(select(Entity).where(Entity.user_id == user.id, Entity.name == "Campervan"))).first()
        if not entity:
            entity = Entity(user_id=user.id, type="vehicle", name="Campervan")
            db.add(entity)
            await db.flush()

        device = (
            await db.scalars(
                select(Device)
                .join(Device.entity)
                .where(
                    Entity.user_id == user.id,
                    Device.imei == args.imei,
                ),
            )
        ).first()
        if not device:
            # Create device on the fly for seeder if not found
            device = Device(entity_id=entity.id, imei=args.imei, name="Demo Device")
            db.add(device)
            await db.flush()
        device_id = device.id

        if args.wipe:
            res = await db.execute(
                delete(Position).where(Position.device_id == device_id),
            )
            await db.commit()
            print(f"wiped {res.rowcount} existing positions")
        else:
            await db.commit()

    now = datetime.now(tz=timezone.utc)
    grand_total = 0
    client_ctx = httpx.AsyncClient() if not args.no_osrm else None
    if client_ctx is not None:
        print(f"using OSRM at {OSRM_BASE} for road snapping (set --no-osrm to skip)")
    try:
        for name, start_dt in SCHEDULE:
            if start_dt > now:
                print(f"skip {name} {start_dt.date()} (future)")
                continue
            # round to start at 9:00 UTC of the date
            start_dt = datetime.combine(
                start_dt.date(),
                time(9, 0),
                tzinfo=timezone.utc,
            )
            print(f"\n== {name.upper()} starting {start_dt.date()} ==")
            pts = await gen_round_trip(client_ctx, name, start_dt)
            if pts and pts[-1].time_id > now:
                # cut off in the future
                pts = [p for p in pts if p.time_id <= now]
                print(f"  trimmed to now ({now.isoformat()}); {len(pts)} pts kept")
            if pts:
                print(
                    f"  generated {len(pts)} points  |  trip window: {pts[0].time_id.date()} → {pts[-1].time_id.date()}"
                )
            else:
                print("  generated 0 points (skipped)")
                continue
            n = await insert_points(device_id, pts)
            grand_total += n
    finally:
        if client_ctx is not None:
            await client_ctx.aclose()

    print(f"\nDONE. inserted {grand_total} positions for device id={device_id}")


if __name__ == "__main__":
    configure_logging()
    asyncio.run(main())
