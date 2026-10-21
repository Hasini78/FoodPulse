"""Deterministic keys for the star schema. No random surrogates."""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd


def token(value: object) -> str | None:
    """Return a stable string identifier, or None when the value is missing."""
    if _missing(value):
        return None
    text = str(value).strip()
    if text == "":
        return None
    try:
        number = float(text)
    except ValueError:
        return text
    if number.is_integer():
        return str(int(number))
    return text


def surrogate(value: object) -> int | None:
    """Return the source id as a NUMBER surrogate when it is a whole number."""
    text = token(value)
    if text is None:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if number.is_integer() and number >= 0:
        return int(number)
    return None


def date_key(value: object) -> int | None:
    """Return YYYYMMDD for a UTC timestamp."""
    day = as_utc_date(value)
    if day is None:
        return None
    return day.year * 10000 + day.month * 100 + day.day


def as_utc_date(value: object) -> date | None:
    parsed = as_utc_timestamp(value)
    if parsed is None:
        return None
    return parsed.date()


def as_utc_timestamp(value: object) -> datetime | None:
    if _missing(value):
        return None
    if isinstance(value, datetime):
        parsed = pd.Timestamp(value)
    else:
        parsed = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(parsed):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.tz_localize("UTC")
    else:
        parsed = parsed.tz_convert("UTC")
    return parsed.to_pydatetime()


def text(value: object) -> str | None:
    if _missing(value):
        return None
    rendered = str(value).strip()
    return rendered or None


def number(value: object) -> float | None:
    if _missing(value):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(parsed):
        return None
    return parsed


def flag(value: object) -> bool | None:
    if _missing(value):
        return None
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
        return None
    return bool(value)


def _missing(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return False
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        return False
    return bool(missing) if isinstance(missing, bool) else False
