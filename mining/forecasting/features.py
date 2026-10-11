"""Aggregate completed-order demand and build lag features without future values."""

from __future__ import annotations

import pandas as pd

from etl.transform.feature_engineering import end_of_reference_day
from etl.transform.parsing import parse_timestamps

SEASON = {"daily": 7, "weekly": 4}
DEFAULT_MIN_HISTORY = {"daily": 28, "weekly": 8}

HISTORY_COLUMNS = [
    "level",
    "restaurant_id",
    "food_item_id",
    "period_start",
    "actual_demand",
    "aggregation",
]


def require_columns(frame: pd.DataFrame, columns: tuple[str, ...], label: str) -> None:
    """Raise when a frame is missing columns the forecast needs."""
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{label} is missing required columns: {', '.join(missing)}")


def aggregate_demand(
    orders: pd.DataFrame,
    order_items: pd.DataFrame,
    foods: pd.DataFrame,
    reference_date,
    aggregation: str,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    """Build restaurant order-count series and food-item quantity series.

    Restaurant demand is the number of completed orders. It is not joined to
    line items, so order totals are not repeated. Item demand is the sum of
    ``quantity`` on those orders. A line is dropped when the food item belongs
    to another restaurant.

    Missing periods are filled with zero only from each series' first observed
    period through the reference date. Earlier dates are left out because this
    extract does not show that the restaurant or item was already offered.
    """
    if aggregation not in SEASON:
        raise ValueError("aggregation must be 'daily' or 'weekly'")
    require_columns(orders, ("id", "restaurant_id", "status", "order_date"), "orders")
    require_columns(order_items, ("order_id", "food_item_id", "quantity"), "order items")
    require_columns(foods, ("id", "restaurant_id"), "food items")
    cutoff = end_of_reference_day(reference_date)
    completed, notes = _completed_orders(orders, cutoff)
    if completed.empty:
        restaurant_counts = pd.DataFrame(columns=["restaurant_id", "period_start", "actual_demand"])
    else:
        completed = completed.copy()
        completed["period_start"] = completed["order_timestamp"].map(lambda value: _period_start(value, aggregation))
        restaurant_counts = completed.groupby(["restaurant_id", "period_start"], as_index=False).size().rename(columns={"size": "actual_demand"})
    restaurants = _fill_series(restaurant_counts, aggregation, cutoff, ["restaurant_id"])
    restaurants["level"] = "restaurant"
    restaurants["food_item_id"] = pd.NA
    restaurants["aggregation"] = aggregation
    items, item_notes = _item_demand(completed, order_items, foods, aggregation, cutoff)
    notes.update(item_notes)
    history = pd.concat(
        [
            restaurants.loc[:, HISTORY_COLUMNS],
            items.loc[:, HISTORY_COLUMNS],
        ],
        ignore_index=True,
    )
    return restaurants, items, notes


def feature_vector(history: list[float], when: pd.Timestamp, aggregation: str) -> list[float]:
    """Features known at ``when``: lags and a calendar field. ``history`` excludes ``when``."""
    season = SEASON[aggregation]
    lag_1 = float(history[-1]) if history else 0.0
    lag_season = float(history[-season]) if len(history) >= season else lag_1
    window = history[-season:] if history else [0.0]
    rolling = float(sum(window) / len(window))
    if aggregation == "daily":
        calendar = float(pd.Timestamp(when).weekday())
    else:
        calendar = float(pd.Timestamp(when).isocalendar().week)
    return [lag_1, lag_season, rolling, calendar]


def feature_names(aggregation: str) -> list[str]:
    """Names of the columns returned by :func:`feature_vector`."""
    calendar = "day_of_week" if aggregation == "daily" else "iso_week"
    return ["lag_1", "lag_season", "rolling_mean_season", calendar]


def iter_periods(start: pd.Timestamp, end: pd.Timestamp, aggregation: str) -> list[pd.Timestamp]:
    """Inclusive period starts from ``start`` through ``end``."""
    freq = "D" if aggregation == "daily" else "7D"
    return list(pd.date_range(start, end, freq=freq, tz="UTC"))


def next_period(current: pd.Timestamp, aggregation: str) -> pd.Timestamp:
    """Period start after ``current``. No demand value is read."""
    step = pd.Timedelta(days=1 if aggregation == "daily" else 7)
    return pd.Timestamp(current) + step


def _completed_orders(orders: pd.DataFrame, cutoff: pd.Timestamp) -> tuple[pd.DataFrame, dict[str, object]]:
    working = orders.copy()
    working["order_id"] = working["id"].map(_token)
    working["restaurant_id"] = working["restaurant_id"].map(_token)
    working["order_timestamp"] = parse_timestamps(working["order_date"])
    working["status_norm"] = working["status"].astype("string").str.strip().str.lower()
    before = len(working)
    working = working.dropna(subset=["order_id", "restaurant_id", "order_timestamp"])
    working = working.drop_duplicates("order_id", keep="first")
    invalid_time = before - len(working)
    not_completed = int((working["status_norm"] != "completed").sum())
    future = int(((working["status_norm"] == "completed") & (working["order_timestamp"] > cutoff)).sum())
    kept = working.loc[(working["status_norm"] == "completed") & (working["order_timestamp"] <= cutoff)].copy()
    notes = {
        "valid_status": "completed, compared after trimming and lowercasing",
        "excluded_statuses": ["cancelled", "pending", "any other non-completed status"],
        "orders_dropped_invalid_keys_or_dates": int(invalid_time),
        "orders_not_completed": not_completed,
        "completed_orders_after_reference_date": future,
        "completed_orders_used": int(len(kept)),
        "restaurant_target": "Count of completed orders in the period. Order totals are not joined to line items.",
        "food_item_target": "Sum of quantity on completed orders. A line whose food item belongs to another restaurant is excluded.",
        "zero_fill": (
            "After a restaurant or item's first observed period, missing periods through the "
            "reference date are zero. Periods before that first observation are not filled."
        ),
    }
    return kept, notes


def _item_demand(
    completed: pd.DataFrame,
    order_items: pd.DataFrame,
    foods: pd.DataFrame,
    aggregation: str,
    cutoff: pd.Timestamp,
) -> tuple[pd.DataFrame, dict[str, object]]:
    lines = order_items.copy()
    lines["order_id"] = lines["order_id"].map(_token)
    lines["food_item_id"] = lines["food_item_id"].map(_token)
    lines["quantity"] = pd.to_numeric(lines["quantity"], errors="coerce")
    lines = lines.dropna(subset=["order_id", "food_item_id"])
    invalid_quantity = int((lines["quantity"].isna() | (lines["quantity"] <= 0)).sum())
    lines = lines.loc[lines["quantity"] > 0]
    catalog = foods.copy()
    catalog["food_item_id"] = catalog["id"].map(_token)
    catalog["item_restaurant_id"] = catalog["restaurant_id"].map(_token)
    catalog = catalog.dropna(subset=["food_item_id", "item_restaurant_id"]).drop_duplicates("food_item_id")
    if completed.empty:
        empty = pd.DataFrame(columns=HISTORY_COLUMNS)
        return empty, {"item_lines_invalid_quantity": invalid_quantity, "item_lines_unknown_or_mismatched": 0, "item_lines_used": 0}
    orders = completed.loc[:, ["order_id", "restaurant_id", "order_timestamp"]].copy()
    if aggregation == "weekly":
        orders["period_start"] = orders["order_timestamp"].map(lambda value: _period_start(value, "weekly"))
    else:
        orders["period_start"] = orders["order_timestamp"].map(lambda value: _period_start(value, "daily"))
    joined = lines.merge(orders, on="order_id", how="inner").merge(
        catalog.loc[:, ["food_item_id", "item_restaurant_id"]],
        on="food_item_id",
        how="left",
    )
    bad = joined["item_restaurant_id"].isna() | (joined["item_restaurant_id"] != joined["restaurant_id"])
    mismatched = int(bad.sum())
    clean = joined.loc[~bad]
    grouped = (
        clean.groupby(["restaurant_id", "food_item_id", "period_start"], as_index=False)["quantity"].sum()
        if not clean.empty
        else pd.DataFrame(columns=["restaurant_id", "food_item_id", "period_start", "quantity"])
    )
    grouped = grouped.rename(columns={"quantity": "actual_demand"})
    filled = _fill_series(grouped, aggregation, cutoff, ["restaurant_id", "food_item_id"])
    filled["level"] = "food_item"
    filled["aggregation"] = aggregation
    notes = {
        "item_lines_invalid_quantity": invalid_quantity,
        "item_lines_unknown_or_mismatched": mismatched,
        "item_lines_used": int(len(clean)),
    }
    return filled, notes


def _fill_series(grouped: pd.DataFrame, aggregation: str, cutoff: pd.Timestamp, keys: list[str]) -> pd.DataFrame:
    if grouped.empty:
        return grouped
    frame = grouped.copy()
    frame["period_start"] = frame["period_start"].map(lambda value: _as_utc(value, aggregation))
    end = _period_start(cutoff, aggregation)
    rows: list[pd.DataFrame] = []
    for key, group in frame.groupby(keys, sort=False):
        start = group["period_start"].min()
        index = pd.Index(iter_periods(start, end, aggregation), name="period_start")
        valued = group.drop_duplicates(keys + ["period_start"], keep="first").set_index("period_start")["actual_demand"]
        valued = valued.astype("float64").reindex(index, fill_value=0.0)
        filled = valued.rename("actual_demand").reset_index()
        if not isinstance(key, tuple):
            key = (key,)
        for name, value in zip(keys, key):
            filled[name] = value
        rows.append(filled)
    return pd.concat(rows, ignore_index=True)


def _period_start(value: pd.Timestamp, aggregation: str) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    else:
        stamp = stamp.tz_convert("UTC")
    day = stamp.floor("D")
    if aggregation == "weekly":
        day = day - pd.Timedelta(days=int(day.weekday()))
    return day


def _as_utc(value: pd.Timestamp, aggregation: str) -> pd.Timestamp:
    return _period_start(value, aggregation)


def _token(value: object) -> str | None:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    text = str(value).strip()
    try:
        number = float(text)
    except ValueError:
        return text or None
    if number.is_integer():
        return str(int(number))
    return text
