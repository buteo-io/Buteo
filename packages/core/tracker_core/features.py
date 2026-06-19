"""Feature flag registry.

Add new flags to the ``Feature`` enum. The CLI validates against ``VALID_FEATURES``
so unknown names (e.g. typos) are rejected before touching the database.

To add plugin / additional features at runtime, update ``VALID_FEATURES`` after import:

    from tracker_core.features import Feature, VALID_FEATURES
    VALID_FEATURES |= {"my_additional_feature"}
"""

from enum import StrEnum


class Feature(StrEnum):
    """All built-in feature flags.

    Because ``Feature`` inherits from ``str``, values can be compared directly
    to the raw strings stored in the database and JWT without casting.
    """

    CAN_WRITE = "can_write"


VALID_FEATURES: frozenset[str] = frozenset(Feature)
