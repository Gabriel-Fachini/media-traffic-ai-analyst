"""Backward-compat shim — real implementation moved to app/core/dates.py."""

from app.core.dates import (
    CALENDAR_MONTH_COMPLETE_PATTERN,
    EXPLICIT_DATE_TOKEN_PATTERN,
    LAST_MONTH_PATTERN,
    LAST_N_DAYS_PATTERN,
    LAST_N_MONTHS_PATTERN,
    LAST_N_WEEKS_PATTERN,
    LAST_YEAR_PATTERN,
    LAST_WEEK_PATTERN,
    TEMPORAL_CONTEXT_PATTERN,
    THIS_MONTH_PATTERN,
    THIS_WEEK_PATTERN,
    THIS_YEAR_PATTERN,
    TODAY_PATTERN,
    YESTERDAY_PATTERN,
    extract_relative_date_range,
    normalize_text,
    question_contains_temporal_signal,
    strip_temporal_context,
    _extract_valid_and_invalid_explicit_dates,
    _resolve_reference_date,
)

# Private alias preserved for test backward compat
_extract_relative_date_range = extract_relative_date_range

__all__ = [
    "CALENDAR_MONTH_COMPLETE_PATTERN",
    "EXPLICIT_DATE_TOKEN_PATTERN",
    "LAST_MONTH_PATTERN",
    "LAST_N_DAYS_PATTERN",
    "LAST_N_MONTHS_PATTERN",
    "LAST_N_WEEKS_PATTERN",
    "LAST_YEAR_PATTERN",
    "LAST_WEEK_PATTERN",
    "TEMPORAL_CONTEXT_PATTERN",
    "THIS_MONTH_PATTERN",
    "THIS_WEEK_PATTERN",
    "THIS_YEAR_PATTERN",
    "TODAY_PATTERN",
    "YESTERDAY_PATTERN",
    "_extract_relative_date_range",
    "_extract_valid_and_invalid_explicit_dates",
    "_resolve_reference_date",
    "extract_relative_date_range",
    "normalize_text",
    "question_contains_temporal_signal",
    "strip_temporal_context",
]
