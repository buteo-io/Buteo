"""ID generation helpers with human-readable prefixes."""

import uuid
from typing import Annotated

from pydantic import AfterValidator


def validate_prefix_uuid(v: str) -> str:
    if len(v) != 39:
        raise ValueError("Must be exactly 39 characters")
    prefix = v[:3]
    if prefix not in PREFIX_TO_MODEL:
        raise ValueError(f"Invalid prefix '{prefix}'")
    try:
        uuid.UUID(v[3:])
    except ValueError as e:
        raise ValueError("Must be a valid UUID after prefix") from e
    return v


PrefixUUID = Annotated[str, AfterValidator(validate_prefix_uuid)]


def gen_public_id(prefix: str) -> str:
    """Generate a prefixed UUID string.

    Args:
        prefix: 3-character lowercase prefix (e.g., 'usr', 'trp', 'plc')

    Returns:
        String like 'usrabc123def456...'
    """
    return f"{prefix}{uuid.uuid4()}"


def gen_tenant_id() -> str:
    """Generate a tenant ID with 'tnt_' prefix."""
    return gen_public_id(prefix="tnt")


PREFIX_TO_MODEL = {
    "tnt": "tenant",
    "usr": "user",
    "ent": "entity",
    "dev": "device",
    "trp": "trip",
    "plc": "place",
    "med": "media",
    "ovs": "overnight_spot",
    "shl": "share_link",
}


def infer_type(public_id: str) -> str | None:
    """Infer model type from public_id prefix.

    Args:
        public_id: A prefixed public_id string like 'usrabc123...'

    Returns:
        Model name or None if unknown prefix.
    """
    if len(public_id) < 3:
        return None
    prefix = public_id[:3]
    return PREFIX_TO_MODEL.get(prefix)
