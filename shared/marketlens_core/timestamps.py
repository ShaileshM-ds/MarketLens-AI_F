"""Source timestamp parsing. A missing timezone is never silently assumed."""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

TimestampPolicy = Literal["allow_timezone_unknown", "require_utc"]
TIMESTAMP_POLICIES = ("allow_timezone_unknown", "require_utc")

_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d{1,6})?)?(Z|[+-]\d{2}:?\d{2})?$")
# The furthest-ahead real timezone is UTC+14.
_MAX_AHEAD = timedelta(hours=14)


class TimestampError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedTimestamp:
    raw: str  # original string (surrounding whitespace removed)
    observed_at: datetime | None  # normalized UTC; None when the timezone is unknown
    quality: str  # "utc" | "offset_converted" | "timezone_unknown"


def parse_source_timestamp(raw: str, policy: TimestampPolicy, now: datetime) -> ParsedTimestamp:
    s = (raw or "").strip()
    if not s:
        raise TimestampError("timestamp is blank")
    if not _ISO.match(s):
        raise TimestampError(f"timestamp '{raw}' is not an ISO 8601 date and time")
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        raise TimestampError(f"timestamp '{raw}' is not a real date and time") from None

    if dt.tzinfo is None:
        if policy == "require_utc":
            raise TimestampError(
                f"timestamp '{raw}' has no timezone; this file must use ISO 8601 UTC "
                "(for example 2026-05-01T09:30:00Z)"
            )
        if dt > now.astimezone(timezone.utc).replace(tzinfo=None) + _MAX_AHEAD:
            raise TimestampError(f"timestamp '{raw}' is in the future in every timezone")
        return ParsedTimestamp(raw=s, observed_at=None, quality="timezone_unknown")

    offset = dt.utcoffset()
    if policy == "require_utc" and offset != timedelta(0):
        raise TimestampError(f"timestamp '{raw}' is not in UTC; this file must use UTC (Z or +00:00)")
    utc = dt.astimezone(timezone.utc)
    if utc > now:
        raise TimestampError(f"timestamp '{raw}' is in the future")
    return ParsedTimestamp(raw=s, observed_at=utc, quality="utc" if offset == timedelta(0) else "offset_converted")
