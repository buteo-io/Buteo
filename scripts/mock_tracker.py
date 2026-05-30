"""Mock Teltonika tracker. Connects, sends IMEI, then loops sending Codec 8 frames.

Usage:
    python scripts/mock_tracker.py --imei 123456789012345 --interval 2

Path tweak: this script is standalone but imports the encoder from `backend/`.
Run it with the backend venv active so the import resolves, e.g.:

    cd backend && source .venv/bin/activate
    python ../scripts/mock_tracker.py --imei 123456789012345
"""

from __future__ import annotations

import argparse
import math
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Allow running without `pip install -e .` from the repo root.
repo_root = Path(__file__).resolve().parent.parent
# For local run or within container:
for path in [repo_root / "apps" / "ingest", repo_root / "app" / "apps" / "ingest"]:
    if (path / "ingest").is_dir():
        sys.path.insert(0, str(path))
        break

from ingest.codec8.codec8 import (  # noqa: E402
    AvlRecord,
    encode_codec8_packet,
    encode_imei,
)


def circle_point(t: float, center=(13.405, 52.52), radius_deg=0.01):
    lon = center[0] + radius_deg * math.cos(t)
    lat = center[1] + radius_deg * math.sin(t)
    return lon, lat


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5027)
    ap.add_argument("--imei", required=True)
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--center-lon", type=float, default=13.405)
    ap.add_argument("--center-lat", type=float, default=52.52)
    ap.add_argument("--radius", type=float, default=0.01)
    ap.add_argument("--count", type=int, default=0, help="0 = infinite")
    ap.add_argument("--connect-retries", type=int, default=30)
    ap.add_argument("--connect-retry-delay", type=float, default=1.0)
    args = ap.parse_args()

    sock = None
    for attempt in range(1, args.connect_retries + 1):
        try:
            sock = socket.create_connection((args.host, args.port), timeout=10)
            break
        except OSError as e:
            if attempt >= args.connect_retries:
                print(
                    f"connect failed to {args.host}:{args.port} after {attempt} attempts: {e}"
                )
                return 3
            print(
                f"connect failed to {args.host}:{args.port} (attempt {attempt}/{args.connect_retries}): {e}. "
                f"retrying in {args.connect_retry_delay:.1f}s",
            )
            time.sleep(args.connect_retry_delay)

    assert sock is not None
    print(f"connected to {args.host}:{args.port}")
    sock.sendall(encode_imei(args.imei))
    ack = sock.recv(1)
    if ack != b"\x01":
        print(f"server rejected imei: ack={ack!r}")
        return 1
    print("imei accepted")

    sent = 0
    t = 0.0
    while args.count == 0 or sent < args.count:
        lon, lat = circle_point(
            t, center=(args.center_lon, args.center_lat), radius_deg=args.radius
        )
        time_id = datetime.now(tz=timezone.utc)
        rec = AvlRecord(
            timestamp=time_id,
            priority=1,
            lon=lon,
            lat=lat,
            altitude=42,
            angle=int((math.degrees(t) + 90) % 360),
            sats=9,
            speed=int(40 + 10 * math.sin(t)),
            event_io_id=0,
        )
        frame = encode_codec8_packet([rec])
        sock.sendall(frame)
        # server replies with 4-byte record count
        resp = sock.recv(4)
        if len(resp) != 4:
            print(f"unexpected server reply: {resp!r}")
            return 2
        n = int.from_bytes(resp, "big")
        sent += 1
        print(
            f"sent #{sent} time_id={time_id.isoformat()} lon={lon:.5f} lat={lat:.5f} ack={n}"
        )
        t += 0.2
        time.sleep(args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
