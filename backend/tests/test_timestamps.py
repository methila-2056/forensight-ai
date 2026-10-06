"""Timestamp normalisation tests (Phase 2)."""

from datetime import datetime

from app.engines.parsing.timestamps import (
    TZ_ASSUMED_UTC,
    TZ_EPOCH_UTC,
    parse_timestamp,
)


def test_naive_datetime_is_assumed_utc():
    result = parse_timestamp("2026-10-05 08:15:00")
    assert result.ok
    assert result.value == datetime(2026, 10, 5, 8, 15, 0)
    assert result.tz_note == TZ_ASSUMED_UTC
    assert result.reason is None


def test_fractional_seconds_supported():
    result = parse_timestamp("2026-10-05 08:15:00.250")
    assert result.ok
    assert result.value.microsecond == 250_000


def test_slash_date_format_supported():
    result = parse_timestamp("2026/10/05 08:15:00")
    assert result.ok
    assert result.value == datetime(2026, 10, 5, 8, 15, 0)


def test_us_date_format_supported():
    result = parse_timestamp("10/05/2026 08:15:00")
    assert result.ok
    assert result.value == datetime(2026, 10, 5, 8, 15, 0)


def test_date_only_defaults_to_midnight():
    result = parse_timestamp("2026-10-05")
    assert result.ok
    assert result.value == datetime(2026, 10, 5, 0, 0, 0)
    assert result.tz_note == TZ_ASSUMED_UTC


def test_iso_zulu_converts_to_utc():
    result = parse_timestamp("2026-10-05T08:15:00Z")
    assert result.ok
    assert result.value == datetime(2026, 10, 5, 8, 15, 0)
    assert "source offset" in (result.tz_note or "")


def test_iso_offset_is_converted_to_utc():
    result = parse_timestamp("2026-10-05T13:05:00+05:30")
    assert result.ok
    assert result.value == datetime(2026, 10, 5, 7, 35, 0)
    assert "+0530" in (result.tz_note or "")


def test_unix_epoch_seconds():
    # 1791162000 == 2026-10-05 01:00:00 UTC
    result = parse_timestamp("1791162000")
    assert result.ok
    assert result.value == datetime(2026, 10, 5, 1, 0, 0)
    assert result.tz_note == TZ_EPOCH_UTC


def test_unix_epoch_milliseconds():
    result = parse_timestamp(str(1791162000 * 1000))
    assert result.ok
    assert result.value == datetime(2026, 10, 5, 1, 0, 0)


def test_apache_format_with_brackets_and_offset():
    result = parse_timestamp("[05/Oct/2026:08:15:00 -0700]")
    assert result.ok
    assert result.value == datetime(2026, 10, 5, 15, 15, 0)
    assert "-0700" in (result.tz_note or "")


def test_apache_format_defaults_to_utc_offset():
    result = parse_timestamp("05/Oct/2026:08:15:00")
    assert result.ok
    assert result.value == datetime(2026, 10, 5, 8, 15, 0)


def test_invalid_value_is_rejected_with_exact_value():
    result = parse_timestamp("not-a-timestamp")
    assert not result.ok
    assert result.value is None
    assert result.reason is not None
    assert "not-a-timestamp" in result.reason


def test_missing_values_reported_not_guessed():
    assert parse_timestamp(None).reason == "missing timestamp value"
    assert parse_timestamp("").reason == "missing timestamp value"
    assert parse_timestamp("   ").reason == "missing timestamp value"


def test_impossible_date_is_not_repaired():
    result = parse_timestamp("2026-99-99 99:99:99")
    assert not result.ok
    assert "2026-99-99 99:99:99" in (result.reason or "")


def test_never_returns_zoned_datetime():
    for raw in ("2026-10-05 08:15:00", "2026-10-05T08:15:00Z", "1791162000"):
        value = parse_timestamp(raw).value
        assert value is not None
        assert value.tzinfo is None
