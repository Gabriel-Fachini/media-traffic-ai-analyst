from __future__ import annotations

import calendar
import re
import unicodedata
from datetime import date, datetime, timedelta

# Matches ISO dates (2024-01-31) and Brazilian dates (31/01/2024 or 31/01/24).
EXPLICIT_DATE_TOKEN_PATTERN = re.compile(
    r"\b(?:\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{2}(?:\d{2})?)\b"
)

# Relative period keywords — each maps to a deterministic date range at runtime.
TODAY_PATTERN = re.compile(r"\bhoje\b")
YESTERDAY_PATTERN = re.compile(r"\bontem\b")
# "esta semana" / "desta semana" (de+esta contraction common in Brazilian Portuguese).
THIS_WEEK_PATTERN = re.compile(r"\b(?:desta|esta)\s+semana\b")
LAST_WEEK_PATTERN = re.compile(r"\bultima\s+semana\b")
# "este mes" / "deste mes" (de+este contraction).
THIS_MONTH_PATTERN = re.compile(r"\b(?:deste|este)\s+mes\b")
LAST_MONTH_PATTERN = re.compile(r"\bultimo\s+mes\b")
# "este ano" / "deste ano" (de+este contraction).
THIS_YEAR_PATTERN = re.compile(r"\b(?:deste|este)\s+ano\b")
LAST_YEAR_PATTERN = re.compile(r"\bultimo\s+ano\b")
# Captures N from "ultimos N dias" / "ultimo N dia" (singular tolerado).
LAST_N_DAYS_PATTERN = re.compile(r"\bultimos?\s+(\d+)\s+dias?\b")
# Captures N from "ultimas N semanas" / "ultima N semana".
LAST_N_WEEKS_PATTERN = re.compile(r"\bultimas?\s+(\d+)\s+semanas?\b")
# Captures N from "ultimos N meses" / "ultimo N mes". Distinct from LAST_MONTH_PATTERN
# ("ultimo mes" = previous calendar month); this is a rolling N-month window.
LAST_N_MONTHS_PATTERN = re.compile(r"\bultimos?\s+(\d+)\s+mes(?:es)?\b")
# Both full forms: "mes calendario completo" and shorthand "mes completo".
CALENDAR_MONTH_COMPLETE_PATTERN = re.compile(
    r"\bmes\s+calendario\s+completo\b|\bmes\s+completo\b"
)

# Broad pattern used to *strip* temporal context from a question before merging
# it with a follow-up. Matches explicit dates with prepositions, relative month/week/year
# references, "hoje", "ontem", and rolling-window expressions anywhere in the sentence.
TEMPORAL_CONTEXT_PATTERN = re.compile(
    # "entre 01/01/24 e 31/01/24" or "from 2024-01-01 to 2024-01-31"
    r"\b(?:entre|from)\s+\d{2}/\d{2}/\d{2}(?:\d{2})?\s+(?:e|a|ate|to)\s+\d{2}/\d{2}/\d{2}(?:\d{2})?\b"
    r"|\b(?:entre|from)\s+\d{4}-\d{2}-\d{2}\s+(?:e|a|ate|to)\s+\d{4}-\d{2}-\d{2}\b"
    # "em 31/01/24", "de 2024-01-01", "from 2024-01-31"
    r"|\b(?:em|in|on|de|do|da|from)\s+\d{2}/\d{2}/\d{2}(?:\d{2})?\b"
    r"|\b(?:em|in|on|de|do|da|from)\s+\d{4}-\d{2}-\d{2}\b"
    # week references
    r"|\b(?:no|na|nos|nas|em|in|desta|desta)\s+esta\s+semana\b"
    r"|\b(?:desta|esta)\s+semana\b"
    r"|\b(?:no|na|nos|nas|em|in)\s+ultima\s+semana\b"
    r"|\b(?:nos|nas|em|in)\s+ultimas?\s+\d+\s+semanas?\b"
    # month references
    r"|\b(?:no|na|nos|nas|em|in)\s+ultimo\s+mes\b"
    r"|\b(?:deste|este)\s+mes\b"
    r"|\bmes\s+calendario\s+completo\b"
    r"|\bmes\s+completo\b"
    r"|\b(?:nos|nas|em|in)\s+ultimos?\s+\d+\s+mes(?:es)?\b"
    # year references
    r"|\b(?:deste|este)\s+ano\b"
    r"|\b(?:no|na|nos|nas|em|in)\s+ultimo\s+ano\b"
    # day references
    r"|\b(?:nos|nas|em|in)\s+ultimos?\s+\d+\s+dias?\b"
    r"|\bontem\b"
    r"|\bhoje\b",
    re.IGNORECASE,
)

# Ordered tuple used by question_contains_temporal_signal and _extract_relative_date_range.
_RELATIVE_PATTERNS = (
    TODAY_PATTERN,
    YESTERDAY_PATTERN,
    THIS_WEEK_PATTERN,
    LAST_WEEK_PATTERN,
    THIS_MONTH_PATTERN,
    LAST_MONTH_PATTERN,
    THIS_YEAR_PATTERN,
    LAST_YEAR_PATTERN,
    CALENDAR_MONTH_COMPLETE_PATTERN,
    LAST_N_DAYS_PATTERN,
    LAST_N_WEEKS_PATTERN,
    LAST_N_MONTHS_PATTERN,
)


def normalize_text(value: str) -> str:
    """Strip accents and lowercase — makes regex matching accent-insensitive."""
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(
        character for character in normalized if not unicodedata.combining(character)
    ).lower()


def _resolve_reference_date(reference_date: date | None) -> date:
    """Return reference_date if provided, otherwise today."""
    return reference_date or date.today()


def _extract_explicit_date_tokens(question: str) -> list[str]:
    """Return raw date strings matched by EXPLICIT_DATE_TOKEN_PATTERN."""
    return [match.group(0) for match in EXPLICIT_DATE_TOKEN_PATTERN.finditer(question)]


def _parse_explicit_date_token(date_token: str) -> date:
    """Parse a single date string (ISO or Brazilian format) into a date object."""
    if "-" in date_token:
        return date.fromisoformat(date_token)
    for date_format in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(date_token, date_format).date()
        except ValueError:
            continue
    raise ValueError("Data invalida.")


def _extract_valid_and_invalid_explicit_dates(
    question: str,
) -> tuple[list[date], list[str]]:
    """Split explicit date tokens into valid date objects and unparseable strings."""
    valid_dates: list[date] = []
    invalid_dates: list[str] = []
    for date_token in _extract_explicit_date_tokens(question):
        try:
            valid_dates.append(_parse_explicit_date_token(date_token))
        except ValueError:
            invalid_dates.append(date_token)
    return valid_dates, invalid_dates


def _match_today(reference_date: date) -> tuple[date, date]:
    """Return (reference_date, reference_date) as a single-day range."""
    return reference_date, reference_date


def _match_yesterday(reference_date: date) -> tuple[date, date]:
    """Return (yesterday, yesterday) as a single-day range."""
    yesterday = reference_date - timedelta(days=1)
    return yesterday, yesterday


def _match_this_week(reference_date: date) -> tuple[date, date]:
    """Return (last Monday, reference_date). Uses ISO week (Mon=0)."""
    monday = reference_date - timedelta(days=reference_date.weekday())
    return monday, reference_date


def _match_last_week(reference_date: date) -> tuple[date, date]:
    """Return the full Mon–Sun range of the previous ISO week."""
    this_monday = reference_date - timedelta(days=reference_date.weekday())
    last_sunday = this_monday - timedelta(days=1)
    last_monday = last_sunday - timedelta(days=6)
    return last_monday, last_sunday


def _match_this_month(reference_date: date) -> tuple[date, date]:
    """Return (first day of current month, reference_date)."""
    return reference_date.replace(day=1), reference_date


def _match_last_month(reference_date: date) -> tuple[date, date]:
    """Return the full calendar range of the previous month."""
    current_month_start = reference_date.replace(day=1)
    last_month_end = current_month_start - timedelta(days=1)
    return last_month_end.replace(day=1), last_month_end


def _match_this_year(reference_date: date) -> tuple[date, date]:
    """Return (Jan 1 of current year, reference_date)."""
    return date(reference_date.year, 1, 1), reference_date


def _match_last_year(reference_date: date) -> tuple[date, date]:
    """Return the full Jan 1 – Dec 31 range of the previous year."""
    prev_year = reference_date.year - 1
    return date(prev_year, 1, 1), date(prev_year, 12, 31)


def _match_last_n_days(reference_date: date, day_count: int) -> tuple[date, date]:
    """Return a rolling window of day_count days ending on reference_date (inclusive)."""
    return reference_date - timedelta(days=day_count - 1), reference_date


def _match_last_n_weeks(reference_date: date, week_count: int) -> tuple[date, date]:
    """Return a rolling window of week_count full weeks ending on reference_date."""
    return reference_date - timedelta(weeks=week_count), reference_date


def _match_last_n_months(reference_date: date, month_count: int) -> tuple[date, date]:
    """Return a rolling window of month_count months ending on reference_date.

    Uses month arithmetic instead of timedelta to avoid day-count approximations.
    The start day is clamped to the last valid day of the target month (e.g.
    Jan 31 minus 1 month → Dec 31, not Feb 28).
    """
    total_months = reference_date.year * 12 + (reference_date.month - 1) - month_count
    start_year = total_months // 12
    start_month = total_months % 12 + 1
    max_day = calendar.monthrange(start_year, start_month)[1]
    start_day = min(reference_date.day, max_day)
    return date(start_year, start_month, start_day), reference_date


def _match_calendar_month_complete(reference_date: date) -> tuple[date, date]:
    """Return the full calendar range of the current month (first to last day)."""
    current_month_start = reference_date.replace(day=1)
    if reference_date.month == 12:
        next_month_start = date(reference_date.year + 1, 1, 1)
    else:
        next_month_start = date(reference_date.year, reference_date.month + 1, 1)
    return current_month_start, next_month_start - timedelta(days=1)


def extract_relative_date_range(
    question: str,
    *,
    reference_date: date | None = None,
) -> tuple[tuple[date, date] | None, list[str]]:
    """Resolve relative date expressions in a question to a (start, end) pair.

    When multiple relative expressions are found, the last one (by position)
    wins. Returns (None, invalid_tokens) if no relative expression is found.
    """
    normalized_question = normalize_text(question)
    resolved_reference_date = _resolve_reference_date(reference_date)
    relative_matches: list[tuple[int, tuple[date, date]]] = []
    invalid_tokens: list[str] = []

    for match in TODAY_PATTERN.finditer(normalized_question):
        relative_matches.append((match.start(), _match_today(resolved_reference_date)))

    for match in YESTERDAY_PATTERN.finditer(normalized_question):
        relative_matches.append((match.start(), _match_yesterday(resolved_reference_date)))

    for match in THIS_WEEK_PATTERN.finditer(normalized_question):
        relative_matches.append((match.start(), _match_this_week(resolved_reference_date)))

    for match in LAST_WEEK_PATTERN.finditer(normalized_question):
        relative_matches.append((match.start(), _match_last_week(resolved_reference_date)))

    for match in THIS_MONTH_PATTERN.finditer(normalized_question):
        relative_matches.append((match.start(), _match_this_month(resolved_reference_date)))

    for match in LAST_MONTH_PATTERN.finditer(normalized_question):
        relative_matches.append((match.start(), _match_last_month(resolved_reference_date)))

    for match in THIS_YEAR_PATTERN.finditer(normalized_question):
        relative_matches.append((match.start(), _match_this_year(resolved_reference_date)))

    for match in LAST_YEAR_PATTERN.finditer(normalized_question):
        relative_matches.append((match.start(), _match_last_year(resolved_reference_date)))

    for match in CALENDAR_MONTH_COMPLETE_PATTERN.finditer(normalized_question):
        relative_matches.append(
            (match.start(), _match_calendar_month_complete(resolved_reference_date))
        )

    for match in LAST_N_DAYS_PATTERN.finditer(normalized_question):
        day_count = int(match.group(1))
        if day_count <= 0:
            invalid_tokens.append(match.group(0))
            continue
        relative_matches.append(
            (match.start(), _match_last_n_days(resolved_reference_date, day_count))
        )

    for match in LAST_N_WEEKS_PATTERN.finditer(normalized_question):
        week_count = int(match.group(1))
        if week_count <= 0:
            invalid_tokens.append(match.group(0))
            continue
        relative_matches.append(
            (match.start(), _match_last_n_weeks(resolved_reference_date, week_count))
        )

    for match in LAST_N_MONTHS_PATTERN.finditer(normalized_question):
        month_count = int(match.group(1))
        if month_count <= 0:
            invalid_tokens.append(match.group(0))
            continue
        relative_matches.append(
            (match.start(), _match_last_n_months(resolved_reference_date, month_count))
        )

    if not relative_matches:
        return None, invalid_tokens

    relative_matches.sort(key=lambda item: item[0])
    return relative_matches[-1][1], invalid_tokens


def question_contains_temporal_signal(question: str) -> bool:
    """Return True if the question contains any explicit date or relative period."""
    if EXPLICIT_DATE_TOKEN_PATTERN.search(question):
        return True
    normalized_question = normalize_text(question)
    return any(pattern.search(normalized_question) for pattern in _RELATIVE_PATTERNS)


def strip_temporal_context(question: str) -> str:
    """Remove temporal expressions from a question, used before merging with a follow-up."""
    stripped_question = TEMPORAL_CONTEXT_PATTERN.sub(" ", question)
    stripped_question = re.sub(r"\s+", " ", stripped_question)
    stripped_question = re.sub(r"\s+([?.!,;:])", r"\1", stripped_question)
    return stripped_question.strip()
