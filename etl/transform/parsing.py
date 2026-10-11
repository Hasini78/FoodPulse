"""Timestamp parsing for mixed sample-CSV formats.

Pandas infers one format from the first values. Several review timestamps
include microseconds (``2026-10-07 06:13:42.018369+00:00``) while most do not,
so parsing must use ``format='mixed'`` or those rows become missing.
"""

from __future__ import annotations

import pandas as pd


def parse_timestamps(series: pd.Series) -> pd.Series:
    """Parse timestamps to UTC. Unparseable values become ``NaT``."""
    return pd.to_datetime(series, utc=True, errors="coerce", format="mixed")


def parse_calendar_dates(series: pd.Series) -> pd.Series:
    """Parse calendar dates to midnight timestamps without shifting the day."""
    parsed = pd.to_datetime(series, errors="coerce", format="mixed")
    if getattr(parsed.dt, "tz", None) is not None:
        parsed = parsed.dt.tz_convert("UTC").dt.tz_localize(None)
    return parsed.dt.normalize()
