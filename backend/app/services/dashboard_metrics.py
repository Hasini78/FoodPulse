"""Chart-ready aggregates over frames the analytics service already loaded.

These functions do not read files, train models, or connect to Snowflake.
"""

from __future__ import annotations

import pandas as pd

COMPLETED_ORDER_STATUS = "completed"


def parse_day(value: str | None, label: str) -> pd.Timestamp | None:
    """Return a UTC timestamp, or None when the filter is omitted."""
    if value is None or not str(value).strip():
        return None
    parsed = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(parsed):
        raise ValueError(f"{label} must be YYYY-MM-DD.")
    return parsed


def completed_orders(frame: pd.DataFrame) -> pd.DataFrame:
    """Keep rows whose lowercased status is exactly completed."""
    if frame.empty:
        return frame.copy()
    status = frame["status"].fillna("").astype(str).str.lower()
    return frame.loc[status == COMPLETED_ORDER_STATUS].copy()


def completed_metrics(orders: pd.DataFrame, start: str | None = None, end: str | None = None) -> dict[str, object]:
    """Completed-order count, revenue, average value, and a monthly trend."""
    start_at = parse_day(start, "start")
    end_at = parse_day(end, "end")
    if start_at is not None and end_at is not None and start_at > end_at:
        raise ValueError("start must be on or before end.")
    completed = completed_orders(orders)
    if "order_date" not in completed.columns:
        raise ValueError("orders are missing order_date.")
    dates = pd.to_datetime(completed["order_date"], utc=True, errors="coerce")
    completed = completed.assign(_date=dates)
    if start_at is not None:
        completed = completed.loc[completed["_date"] >= start_at]
    if end_at is not None:
        completed = completed.loc[completed["_date"] < end_at + pd.DateOffset(days=1)]
    amounts = pd.to_numeric(completed["total_amount"], errors="coerce")
    revenue = None if amounts.notna().sum() == 0 else float(amounts.sum())
    average = None if amounts.notna().sum() == 0 else float(amounts.mean())
    monthly = _monthly(completed, amounts)
    return {
        "completed_orders": int(len(completed)),
        "completed_revenue": revenue,
        "average_order_value": average,
        "monthly": monthly,
        "date_filter": {"start": start, "end": end},
        "definition": "Revenue and order counts include only rows whose lowercased status is completed. Other statuses are excluded.",
    }


def _monthly(completed: pd.DataFrame, amounts: pd.Series) -> list[dict[str, object]]:
    if completed.empty:
        return []
    month = completed["_date"].dt.strftime("%Y-%m")
    grouped = pd.DataFrame({"month": month, "amount": amounts}).dropna(subset=["month"])
    if grouped.empty:
        return []
    rows = (
        grouped.groupby("month", as_index=False)
        .agg(completed_orders=("amount", "size"), completed_revenue=("amount", "sum"))
        .sort_values("month")
    )
    return [
        {
            "month": str(record["month"]),
            "completed_orders": int(record["completed_orders"]),
            "completed_revenue": float(record["completed_revenue"]),
        }
        for record in rows.to_dict(orient="records")
    ]


def aspect_counts(frame: pd.DataFrame) -> list[dict[str, object]]:
    """Count stored aspect labels. Missing aspect columns are skipped."""
    columns = (
        ("food_sent", "food"),
        ("service_sent", "service"),
        ("ambience_sent", "ambience"),
        ("price_sent", "price"),
    )
    rows: list[dict[str, object]] = []
    for column, aspect in columns:
        if column not in frame.columns:
            continue
        counts = frame[column].fillna("(missing)").astype(str).value_counts()
        for label, count in counts.items():
            rows.append({"aspect": aspect, "label": str(label), "count": int(count)})
    return rows


def forecast_window(frame: pd.DataFrame) -> dict[str, object]:
    """Describe the stored forward restaurant forecast. Intervals are not in the file."""
    if frame.empty:
        return {"available": False, "intervals": None, "notice": "No stored forward restaurant forecast."}
    needed = {"level", "forecast_role", "model_name", "aggregation", "forecast_date", "restaurant_id"}
    missing = needed - set(frame.columns)
    if missing:
        raise ValueError("forecasts are missing required columns: " + ", ".join(sorted(missing)))
    forward = frame.loc[
        (frame["level"] == "restaurant")
        & (frame["forecast_role"] == "forward")
        & (frame["model_name"] == "ridge")
        & (frame["aggregation"] == "daily")
    ]
    if forward.empty:
        return {"available": False, "intervals": None, "notice": "No stored daily ridge forward forecast for restaurants."}
    dates = pd.to_datetime(forward["forecast_date"], utc=True, errors="coerce").dropna()
    horizon = None
    if "horizon" in forward.columns and forward["horizon"].notna().any():
        horizon = int(forward["horizon"].dropna().iloc[0])
    return {
        "available": True,
        "intervals": None,
        "model_name": "ridge",
        "aggregation": "daily",
        "horizon": horizon,
        "start": None if dates.empty else str(dates.min().strftime("%Y-%m-%d")),
        "end": None if dates.empty else str(dates.max().strftime("%Y-%m-%d")),
        "restaurants": int(forward["restaurant_id"].nunique()),
        "notice": "These are stored forward predictions. The forecast file does not include uncertainty intervals.",
    }
