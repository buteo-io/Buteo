"""Media validation constants and helpers.

Deduplicated MIME type definitions and magic-byte validators.
"""

from __future__ import annotations

import logging
from pathlib import Path

import anyio
from fastapi import HTTPException, UploadFile

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1024 * 1024  # 1 MiB

ALLOWED_IMAGE_MIMES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
}
ALLOWED_VIDEO_MIMES = {"video/mp4", "video/quicktime", "video/x-msvideo"}
ALLOWED_AUDIO_MIMES = {
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/ogg",
    "audio/webm",
    "audio/x-m4a",
}
ALLOWED_MIMES = ALLOWED_IMAGE_MIMES | ALLOWED_VIDEO_MIMES | ALLOWED_AUDIO_MIMES

# MAGIC_BYTES documentation regarding known false-positive / mismatch surfaces:
# - "RIFF" (WebP, WAV, AVI) starts with 'RIFF' at offset 0. Any file within these formats matches.
#   A malicious or malformed AVI file uploaded as image/webp will pass this check due to shared RIFF header.
# - "ftyp" (HEIC, HEIF, MP4, QuickTime/MOV, M4A) starts with 'ftyp' at offset 4.
#   Since ISOBMFF containers share the same 'ftyp' signature, format-level spoofing between these types is possible.
# - "ID3" (MPEG, MP3) starts with ID3 tag signature. Naive check only detects files with optional ID3v2 tags.
MAGIC_BYTES = {
    "image/jpeg": b"\xff\xd8\xff",
    "image/png": b"\x89\x50\x4e\x47",
    "image/webp": b"RIFF",
    "image/heic": b"ftyp",
    "image/heif": b"ftyp",
    "video/mp4": b"ftyp",
    "video/quicktime": b"moov",
    "video/x-msvideo": b"RIFF",
    "audio/mpeg": b"ID3",
    "audio/mp3": b"ID3",
    "audio/wav": b"RIFF",
    "audio/ogg": b"OggS",
    "audio/webm": b"\x1aE\xdf\xa3",
    "audio/x-m4a": b"ftyp",
}


def validate_magic_bytes(content: bytes, mime_type: str) -> bool:
    """Validate file content matches claimed MIME type using magic bytes.

    NOTE on False Positives / Limits of Naive Magic Byte Validation:
    - HEIC, HEIF, MP4, and M4A all share ISOBMFF format and have 'ftyp' at offset 4.
      This function validates that 'ftyp' is present but cannot distinguish between these sub-formats.
    - WebP, WAV, and AVI share 'RIFF' headers at offset 0. Any RIFF file can pass as WebP.
    """
    magic = MAGIC_BYTES.get(mime_type)
    if not magic:
        return False
    if magic == b"ftyp":
        # ISOBMFF files (HEIC, HEIF, MP4, etc.) have 'ftyp' at offset 4.
        return len(content) > 8 and content[4:8] == b"ftyp"
    return content.startswith(magic)


async def save_upload_file(
    file: UploadFile,
    dest: Path,
    max_size: int,
    mime_type: str,
) -> int:
    """Stream ``file`` to ``dest`` in chunks while enforcing size cap.

    The first chunk is validated against ``mime_type`` magic bytes before
    anything is written. Writes run on a thread pool so the event loop is not
    blocked by large uploads.

    Args:
        file: Starlette/FastAPI upload handle.
        dest: Target path on disk.
        max_size: Maximum allowed file size in bytes.
        mime_type: Declared MIME type of the upload.

    Returns:
        Total bytes written.

    Raises:
        HTTPException: 400 for empty file or magic-byte mismatch, 413 for oversize.
    """
    first_chunk = await file.read(CHUNK_SIZE)
    if not first_chunk:
        raise HTTPException(400, "empty file")
    if not validate_magic_bytes(first_chunk, mime_type):
        raise HTTPException(400, "file content does not match declared type")

    bytes_written = len(first_chunk)
    if bytes_written > max_size:
        raise HTTPException(
            413,
            f"file too large (max {max_size // (1024 * 1024)}MB)",
        )

    with dest.open("wb") as f:
        await anyio.to_thread.run_sync(f.write, first_chunk)

        while True:
            chunk = await file.read(CHUNK_SIZE)
            if not chunk:
                break
            bytes_written += len(chunk)
            if bytes_written > max_size:
                raise HTTPException(
                    413,
                    f"file too large (max {max_size // (1024 * 1024)}MB)",
                )
            await anyio.to_thread.run_sync(f.write, chunk)

    return bytes_written
