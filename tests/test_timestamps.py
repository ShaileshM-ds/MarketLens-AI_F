from datetime import datetime, timezone

import pytest

from helpers import NOW
from marketlens_core.timestamps import TimestampError, parse_source_timestamp


def test_naive_snapshot_timestamp_stays_timezone_unknown():
    ts = parse_source_timestamp("2026-11-04T10:30:00", "allow_timezone_unknown", NOW)
    assert ts.raw == "2026-11-04T10:30:00"
    assert ts.observed_at is None
    assert ts.quality == "timezone_unknown"


def test_naive_timestamp_rejected_for_history_files():
    with pytest.raises(TimestampError, match="no timezone"):
        parse_source_timestamp("2026-11-04T10:30:00", "require_utc", NOW)


def test_utc_timestamp_normalized():
    ts = parse_source_timestamp("2026-11-04T10:30:00Z", "require_utc", NOW)
    assert ts.observed_at == datetime(2026, 11, 4, 10, 30, tzinfo=timezone.utc)
    assert ts.quality == "utc"
    assert ts.raw == "2026-11-04T10:30:00Z"


def test_explicit_zero_offset_counts_as_utc():
    ts = parse_source_timestamp("2026-11-04T10:30:00+00:00", "require_utc", NOW)
    assert ts.quality == "utc"


def test_non_utc_offset_converted_only_when_allowed():
    ts = parse_source_timestamp("2026-11-04T16:00:00+05:30", "allow_timezone_unknown", NOW)
    assert ts.observed_at == datetime(2026, 11, 4, 10, 30, tzinfo=timezone.utc)
    assert ts.quality == "offset_converted"
    with pytest.raises(TimestampError, match="UTC"):
        parse_source_timestamp("2026-11-04T16:00:00+05:30", "require_utc", NOW)


@pytest.mark.parametrize("raw", ["", "yesterday", "04/11/2026 10:30", "2026-13-40T10:30:00"])
def test_invalid_timestamps(raw):
    with pytest.raises(TimestampError):
        parse_source_timestamp(raw, "allow_timezone_unknown", NOW)


def test_future_utc_timestamp_rejected():
    with pytest.raises(TimestampError, match="future"):
        parse_source_timestamp("2026-11-07T00:00:00Z", "require_utc", NOW)


def test_naive_timestamp_future_in_every_timezone_rejected():
    # More than 14 hours ahead of now: in the future whatever the timezone.
    with pytest.raises(TimestampError, match="future"):
        parse_source_timestamp("2026-11-06T15:00:00", "allow_timezone_unknown", NOW)
    # Within 14 hours: could be past in some timezone, so it is not rejected.
    assert parse_source_timestamp("2026-11-06T13:00:00", "allow_timezone_unknown", NOW).observed_at is None
