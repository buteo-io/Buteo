"""Teltonika Codec 8 / 8E protocol: frame parsing, encoding, and TCP ingest server.

Frame layout (after IMEI handshake), big-endian:

    [preamble: 4 bytes = 0x00000000]
    [data length: 4 bytes]   # bytes from `codec id` through last `number of data N2` (excluding CRC)
    [codec id: 1 byte]       # 0x08 (Codec 8) or 0x8E (Codec 8E)
    [number of data N1: 1 byte]
    [AVL records...]
    [number of data N2: 1 byte]   # equals N1
    [CRC-16/IBM: 4 bytes]    # over the data length region

Each AVL record (Codec 8):
    [timestamp: 8 bytes ms since epoch]
    [priority: 1]
    [longitude: 4 int32 / 1e7]
    [latitude: 4 int32 / 1e7]
    [altitude: 2 int16]
    [angle: 2 uint16]
    [satellites: 1]
    [speed: 2 uint16 km/h]
    [event io id: 1]
    [total io: 1]
    [N1 elements (id:1, val:1)]
    [N2 elements (id:1, val:2)]
    [N4 elements (id:1, val:4)]
    [N8 elements (id:1, val:8)]

Codec 8E differs: event io id and counts are 2 bytes each, plus an Nx (variable) section.

Per-connection TCP flow:

    1. Read IMEI handshake. Look up device. Reply 0x01 (accept) or 0x00 (reject).
    2. Loop: read AVL packet, parse, persist positions, reply with record count.
    3. On any error, close the connection.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tracker_core.internal.appctx.config import AppConfig
from tracker_core.store.ingest import PositionData, store_positions
from tracker_core.store.models import Device
from tracker_core.store.tenant_db_manager import get_tenant_by_imei, tenant_db_manager

logger = logging.getLogger(__name__)
CODEC_8 = 0x08
CODEC_8E = 0x8E

# Hard upper bounds on what we'll accept off the wire. Codec 8 records are
# capped by a 1-byte count (max 255) and each record is well under 256 bytes,
# so a real frame fits in a few KiB. Codec 8E uses 2-byte counts and variable
# IO blocks, but field reports rarely exceed a few KiB. We give a generous
# 64 KiB ceiling to soak up firmware quirks while still rejecting the
# obviously-bogus 4 GiB allocation a malicious peer could otherwise force.
MAX_FRAME_PAYLOAD = 65_536
# IMEI handshake. Real IMEIs are 15 ASCII digits; the field on the wire is
# bounded by a u16 length prefix (max 65535) which we deliberately do not
# trust. Allow 8-17 chars (some Teltonika firmwares pad/strip) of digits.
MAX_IMEI_LEN = 17
MIN_IMEI_LEN = 8


# ---------------- Data classes ----------------


@dataclass
class IOElement:
    id: int
    value: int


@dataclass
class AvlRecord:
    timestamp: datetime
    priority: int
    lon: float
    lat: float
    altitude: int
    angle: int
    sats: int
    speed: int
    event_io_id: int
    io: list[IOElement] = field(default_factory=list)


@dataclass
class AvlPacket:
    codec: int
    records: list[AvlRecord]


# ---------------- IMEI handshake ----------------


def parse_imei(buf: bytes) -> str:
    """Parse the device's first message: [len:2][imei ascii]."""
    if len(buf) < 2:
        raise ValueError("imei: buffer too small")
    length = int.from_bytes(buf[:2], "big")
    if len(buf) < 2 + length:
        raise ValueError("imei: short read")
    return buf[2 : 2 + length].decode("ascii")


def encode_imei(imei: str) -> bytes:
    """Encode an IMEI handshake (used by the mock tracker)."""
    raw = imei.encode("ascii")
    return len(raw).to_bytes(2, "big") + raw


# ---------------- Byte readers ----------------


def _u8(b: bytes, i: int) -> tuple[int, int]:
    return b[i], i + 1


def _u16(b: bytes, i: int) -> tuple[int, int]:
    return int.from_bytes(b[i : i + 2], "big"), i + 2


def _i16(b: bytes, i: int) -> tuple[int, int]:
    return int.from_bytes(b[i : i + 2], "big", signed=True), i + 2


def _u32(b: bytes, i: int) -> tuple[int, int]:
    return int.from_bytes(b[i : i + 4], "big"), i + 4


def _i32(b: bytes, i: int) -> tuple[int, int]:
    return int.from_bytes(b[i : i + 4], "big", signed=True), i + 4


def _u64(b: bytes, i: int) -> tuple[int, int]:
    return int.from_bytes(b[i : i + 8], "big"), i + 8


# ---------------- Parsing ----------------


def parse_avl_packet(frame: bytes) -> AvlPacket:
    """Parse a full AVL frame (including preamble, length, payload, crc)."""
    if len(frame) < 12:
        raise ValueError("frame too short")
    preamble, i = _u32(frame, 0)
    if preamble != 0:
        raise ValueError(f"bad preamble: {preamble:#x}")
    data_len, i = _u32(frame, i)
    if data_len == 0 or data_len > MAX_FRAME_PAYLOAD:
        raise ValueError(f"bad data length: {data_len}")
    payload_start = i
    payload_end = payload_start + data_len
    if len(frame) < payload_end + 4:
        raise ValueError("frame truncated")
    pkt = _parse_payload(frame[payload_start:payload_end])
    return pkt


def _parse_payload(p: bytes) -> AvlPacket:
    i = 0
    codec, i = _u8(p, i)
    if codec not in (CODEC_8, CODEC_8E):
        raise ValueError(f"unsupported codec {codec:#x}")
    n1, i = _u8(p, i)
    records: list[AvlRecord] = []
    for _ in range(n1):
        rec, i = _parse_record(p, i, codec)
        records.append(rec)
    n2, i = _u8(p, i)
    if n2 != n1:
        raise ValueError(f"record count mismatch: {n1} vs {n2}")
    return AvlPacket(codec=codec, records=records)


def _parse_record(p: bytes, i: int, codec: int) -> tuple[AvlRecord, int]:
    ts_ms, i = _u64(p, i)
    # Guard `datetime.fromtimestamp` against u64 values that overflow
    # Python's int->datetime conversion (year > 9999 raises OverflowError
    # which would otherwise abort the whole packet).
    try:
        ts = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
    except (OverflowError, OSError, ValueError) as e:
        raise ValueError(f"bad timestamp: {ts_ms}") from e
    priority, i = _u8(p, i)
    lon_i, i = _i32(p, i)
    lat_i, i = _i32(p, i)
    alt, i = _i16(p, i)
    angle, i = _u16(p, i)
    sats, i = _u8(p, i)
    speed, i = _u16(p, i)
    if codec == CODEC_8:
        event_id, i = _u8(p, i)
        total_io, i = _u8(p, i)
        size_reader = _u8
        count_reader = _u8
    else:  # 8E
        event_id, i = _u16(p, i)
        _total_io, i = _u16(p, i)
        size_reader = _u16
        count_reader = _u16

    io: list[IOElement] = []
    for size in (1, 2, 4, 8):
        n, i = count_reader(p, i)
        for _ in range(n):
            id_, i = size_reader(p, i)
            val_bytes = p[i : i + size]
            val = int.from_bytes(val_bytes, "big")
            i += size
            io.append(IOElement(id=id_, value=val))
    if codec == CODEC_8E:
        # variable-length section
        nx, i = count_reader(p, i)
        for _ in range(nx):
            id_, i = size_reader(p, i)
            ln, i = _u16(p, i)
            i += ln  # skip raw payload
    return (
        AvlRecord(
            timestamp=ts,
            priority=priority,
            lon=lon_i / 1e7,
            lat=lat_i / 1e7,
            altitude=alt,
            angle=angle,
            sats=sats,
            speed=speed,
            event_io_id=event_id,
            io=io,
        ),
        i,
    )


# ---------------- Encoding (used by mock tracker) ----------------


def encode_codec8_record(rec: AvlRecord) -> bytes:
    ts = int(rec.timestamp.timestamp() * 1000)
    out = bytearray()
    out += ts.to_bytes(8, "big")
    out += rec.priority.to_bytes(1, "big")
    out += round(rec.lon * 1e7).to_bytes(4, "big", signed=True)
    out += round(rec.lat * 1e7).to_bytes(4, "big", signed=True)
    out += int(rec.altitude).to_bytes(2, "big", signed=True)
    out += int(rec.angle).to_bytes(2, "big")
    out += int(rec.sats).to_bytes(1, "big")
    out += int(rec.speed).to_bytes(2, "big")
    out += rec.event_io_id.to_bytes(1, "big")
    out += (0).to_bytes(1, "big")  # total io
    # zero counts for n1, n2, n4, n8
    out += b"\x00\x00\x00\x00"
    return bytes(out)


def _crc16_ibm(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def encode_codec8_packet(records: list[AvlRecord]) -> bytes:
    body = bytearray()
    body += CODEC_8.to_bytes(1, "big")
    body += len(records).to_bytes(1, "big")
    for r in records:
        body += encode_codec8_record(r)
    body += len(records).to_bytes(1, "big")
    crc = _crc16_ibm(bytes(body))
    out = bytearray()
    out += (0).to_bytes(4, "big")  # preamble
    out += len(body).to_bytes(4, "big")  # data length
    out += body
    # Per spec: 4-byte field whose low 16 bits hold CRC16/IBM over the body.
    # We do not validate this on receive (TCP already gives us frame integrity
    # and Traccar's reference decoder also skips it), but we emit it correctly
    # so the encoder can be used by the mock tracker against real servers.
    out += crc.to_bytes(4, "big")
    return bytes(out)


# ---------------- Streaming reader ----------------


async def read_packet(reader) -> bytes:
    """Read one full AVL packet from an asyncio StreamReader. Returns raw frame.

    Enforces :data:`MAX_FRAME_PAYLOAD` on the on-wire length field. A
    misbehaving / malicious peer that sends an arbitrary u32 here would
    otherwise force the server into a multi-GiB allocation per connection.
    """
    head = await reader.readexactly(8)
    preamble = int.from_bytes(head[0:4], "big")
    if preamble != 0:
        raise ValueError(f"bad preamble: {preamble:#x}")
    data_len = int.from_bytes(head[4:8], "big")
    if data_len == 0 or data_len > MAX_FRAME_PAYLOAD:
        raise ValueError(f"refusing oversize frame: {data_len} bytes")
    rest = await reader.readexactly(data_len + 4)
    return head + rest


# ---------------- TCP server ----------------


async def _resolve_device(db: AsyncSession, imei: str) -> Device | None:
    d = await db.scalar(select(Device).where(Device.imei == imei))
    if d and d.revoked_at is not None:
        return None
    return d


def _parse_avl_packet(pkt: AvlPacket) -> list[PositionData]:
    """Convert AVL records into protocol-agnostic PositionData objects."""
    return [
        PositionData(
            time_id=r.timestamp,
            lat=r.lat,
            lon=r.lon,
            altitude=float(r.altitude) if r.altitude is not None else None,
            speed=float(r.speed) if r.speed is not None else None,
            satellites=r.sats,
        )
        for r in pkt.records
    ]


async def handle_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    peer = writer.get_extra_info("peername")
    try:
        # IMEI handshake: [len:2][ascii]. The wire-format length is u16
        # (bounded to 65535) but real IMEIs are <= MAX_IMEI_LEN digits.
        # Reject anything outside that range BEFORE allocating, so we don't
        # let drive-by connections trigger 64 KiB reads.
        len_buf = await reader.readexactly(2)
        imei_len = int.from_bytes(len_buf, "big")
        if not (MIN_IMEI_LEN <= imei_len <= MAX_IMEI_LEN):
            logger.warning(
                "reject_bad_imei_len", extra={"peer": peer, "imei_len": imei_len}
            )
            writer.write(b"\x00")
            await writer.drain()
            return
        imei = (await reader.readexactly(imei_len)).decode("ascii", errors="replace")
        if not imei.isdigit():
            logger.warning("reject_non_digit_imei", extra={"peer": peer, "imei": imei})
            writer.write(b"\x00")
            await writer.drain()
            return
        logger.info("connect", extra={"peer": peer, "imei": imei})

        tenant_id = await get_tenant_by_imei(imei)
        if not tenant_id:
            logger.warning("reject_unknown_tenant", extra={"imei": imei, "peer": peer})
            writer.write(b"\x00")
            await writer.drain()
            return

        async with tenant_db_manager.get_tenant_session(tenant_id) as db:
            device = await _resolve_device(db, imei)
            if not device:
                logger.warning("reject_unknown", extra={"imei": imei, "peer": peer})
                writer.write(b"\x00")
                await writer.drain()
                return
            writer.write(b"\x01")
            await writer.drain()
            device_id = device.id

        while True:
            try:
                frame = await read_packet(reader)
            except asyncio.IncompleteReadError:
                logger.info("disconnect", extra={"peer": peer, "imei": imei})
                return
            try:
                pkt = parse_avl_packet(frame)
            except Exception:
                logger.exception("parse_error")
                return
            logger.debug(
                "incoming",
                extra={
                    "device_id": device_id,
                    "payload": {"codec": pkt.codec, "records": len(pkt.records)},
                },
            )
            fixes = _parse_avl_packet(pkt)
            async with tenant_db_manager.get_tenant_session(tenant_id) as db:
                count = await store_positions(db, device_id, fixes)
            logger.debug("stored", extra={"imei": imei, "count": count})
            writer.write(count.to_bytes(4, "big"))
            await writer.drain()
    except (asyncio.IncompleteReadError, ConnectionResetError):
        logger.info("disconnect_reset", extra={"peer": peer})
    except Exception:
        logger.exception("handler_error")
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def serve() -> None:
    server = await asyncio.start_server(
        handle_client, AppConfig.ingest_host, AppConfig.ingest_codec8_port
    )
    async with server:
        await server.serve_forever()
