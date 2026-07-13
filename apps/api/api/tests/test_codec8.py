import asyncio
from datetime import UTC, datetime

import pytest
from ingest.codec8.codec8 import (
    MAX_FRAME_PAYLOAD,
    AvlRecord,
    encode_codec8_packet,
    encode_imei,
    parse_avl_packet,
    parse_imei,
    read_packet,
)


def test_imei_roundtrip():
    raw = encode_imei("123456789012345")
    assert parse_imei(raw) == "123456789012345"


def test_codec8_roundtrip():
    rec = AvlRecord(
        timestamp=datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC),
        priority=1,
        lon=13.405,
        lat=52.52,
        altitude=42,
        angle=180,
        sats=9,
        speed=55,
        event_io_id=0,
    )
    frame = encode_codec8_packet([rec, rec])
    pkt = parse_avl_packet(frame)
    assert pkt.codec == 0x08
    assert len(pkt.records) == 2
    p = pkt.records[0]
    assert p.priority == 1
    assert round(p.lon, 4) == 13.405
    assert round(p.lat, 4) == 52.52
    assert p.altitude == 42
    assert p.angle == 180
    assert p.sats == 9
    assert p.speed == 55
    assert p.timestamp == rec.timestamp


def test_oversize_data_len_is_rejected():
    """Refuse a frame whose advertised data length exceeds MAX_FRAME_PAYLOAD.

    Without this guard a peer that sends `00000000 FFFFFFFF` would force the
    server into a ~4 GiB allocation per connection (real DoS vector against
    the public-facing TCP ingest).
    """
    bogus = b"\x00\x00\x00\x00" + b"\xff\xff\xff\xff" + b"\x00" * 12
    with pytest.raises(ValueError, match="data length"):
        parse_avl_packet(bogus)


def test_zero_data_len_is_rejected():
    bogus = b"\x00\x00\x00\x00" + b"\x00\x00\x00\x00" + b"\x00" * 4
    with pytest.raises(ValueError, match="data length"):
        parse_avl_packet(bogus)


async def test_read_packet_refuses_oversize_length():
    """Streaming reader applies the same cap before the second readexactly."""
    head = b"\x00\x00\x00\x00" + (MAX_FRAME_PAYLOAD + 1).to_bytes(4, "big")
    reader = asyncio.StreamReader()
    reader.feed_data(head)
    reader.feed_eof()
    with pytest.raises(ValueError, match="oversize"):
        await read_packet(reader)


async def test_read_packet_refuses_bad_preamble():
    head = b"\x01\x02\x03\x04" + (16).to_bytes(4, "big")
    reader = asyncio.StreamReader()
    reader.feed_data(head)
    reader.feed_eof()
    with pytest.raises(ValueError, match="preamble"):
        await read_packet(reader)


def test_reference_frame():
    # Reference Codec 8 frame from Teltonika docs (single record).
    hex_ = (
        "000000000000003608010000016B40D8EA30010000000000000000000000000000000105"
        "021503010101425E0F01F10000601A014E0000000000000000010000C7CF"
    )
    frame = bytes.fromhex(hex_)
    pkt = parse_avl_packet(frame)
    assert pkt.codec == 0x08
    assert len(pkt.records) == 1
    r = pkt.records[0]
    # The reference frame has lat/lon both 0, alt 0.
    assert r.lon == 0.0
    assert r.lat == 0.0
    assert r.priority == 1
