from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from tracker_core import analytics


def _p(
    t: datetime, lon: float, lat: float, speed: float | None = None
) -> SimpleNamespace:
    return SimpleNamespace(
        time_id=t, lon=lon, lat=lat, speed=speed, altitude=None, satellites=None
    )


def test_haversine_known_distance():
    # Berlin -> Paris ~ 878 km
    d = analytics.haversine_km(52.52, 13.405, 48.8566, 2.3522)
    assert 870 < d < 890


def test_detect_trips_simple():
    base = datetime(2025, 1, 1, 8, tzinfo=timezone.utc)
    pts = []
    # drive 0..30min
    for i in range(31):
        pts.append(
            _p(base + timedelta(minutes=i), 13.405 + i * 0.001, 52.52, speed=60.0)
        )
    # stop 30..50min same spot
    for i in range(31, 51):
        pts.append(
            _p(base + timedelta(minutes=i), 13.405 + 30 * 0.001, 52.52, speed=0.0)
        )
    # drive again 50..70min
    for i in range(51, 71):
        pts.append(
            _p(
                base + timedelta(minutes=i),
                13.405 + 30 * 0.001 + (i - 50) * 0.001,
                52.52,
                speed=60.0,
            )
        )
    trips = analytics.detect_trips(pts)
    assert len(trips) == 2
    assert all(t.distance_km > 0.5 for t in trips)


def test_overnight_detect():
    # device idle from 22:00 to 09:00 next day at lat 52, lon 13
    base = datetime(2025, 1, 1, 22, 0, tzinfo=timezone.utc)
    pts = [
        _p(base + timedelta(minutes=i * 30), 13.0, 52.0, speed=0.0) for i in range(24)
    ]
    overnights = analytics.detect_overnights(pts)
    assert len(overnights) == 1
    assert overnights[0].duration_s >= 4 * 3600


def test_mileage_buckets_by_day():
    base = datetime(2025, 1, 1, 8, tzinfo=timezone.utc)
    pts = [
        _p(base, 13.0, 52.0),
        _p(base + timedelta(minutes=10), 13.05, 52.0),  # ~3.4 km same day
        _p(base + timedelta(days=1, minutes=10), 13.1, 52.0),  # gap >1h, skipped
        _p(base + timedelta(days=1, minutes=20), 13.15, 52.0),  # ~3.4 km next day
    ]
    buckets = analytics.mileage_buckets(pts, "day")
    assert len(buckets) == 2
    assert buckets[0][1] > 2
    assert buckets[1][1] > 2


def test_gpx_csv_serialize():
    base = datetime(2025, 1, 1, 8, tzinfo=timezone.utc)
    pts = [
        _p(base, 13.0, 52.0, speed=10),
        _p(base + timedelta(minutes=1), 13.001, 52.0, speed=20),
    ]
    gpx = "".join(analytics.to_gpx(pts, name="test"))
    assert "<trkpt" in gpx
    assert 'lat="52.0"' in gpx
    csv = "".join(analytics.to_csv(pts))
    assert csv.startswith("time_id,lat,lon")
    assert csv.count("\n") == 3  # header + 2 rows + trailing newline
