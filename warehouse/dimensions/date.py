"""DIM_DATE from order and review timestamps."""

from __future__ import annotations

import calendar

import pandas as pd

from warehouse.snowflake.keys import as_utc_date, date_key

COLUMNS = (
    "date_sk",
    "date_day",
    "year",
    "quarter",
    "month",
    "month_name",
    "day",
    "day_of_week",
    "day_name",
    "is_weekend",
)


def build_date(*series: pd.Series) -> pd.DataFrame:
    """Return one row per UTC date found in the supplied timestamp series."""
    seen: set[int] = set()
    rows: list[dict[str, object]] = []
    for values in series:
        if values is None:
            continue
        for value in values:
            key = date_key(value)
            day = as_utc_date(value)
            if key is None or day is None or key in seen:
                continue
            seen.add(key)
            weekday = day.isoweekday()
            rows.append(
                {
                    "date_sk": key,
                    "date_day": day,
                    "year": day.year,
                    "quarter": (day.month - 1) // 3 + 1,
                    "month": day.month,
                    "month_name": calendar.month_name[day.month],
                    "day": day.day,
                    "day_of_week": weekday,
                    "day_name": calendar.day_name[weekday - 1],
                    "is_weekend": weekday >= 6,
                }
            )
    return pd.DataFrame(rows, columns=COLUMNS).sort_values("date_sk", kind="mergesort").reset_index(drop=True)
