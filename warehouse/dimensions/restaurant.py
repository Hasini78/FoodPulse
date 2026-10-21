"""DIM_RESTAURANT with location attributes. Phone and email are not loaded."""

from __future__ import annotations

import pandas as pd

from warehouse.snowflake.keys import as_utc_timestamp, flag, surrogate, text, token

COLUMNS = (
    "restaurant_sk",
    "restaurant_id",
    "name",
    "cuisine_type",
    "is_active",
    "city",
    "state",
    "country",
    "created_at",
)
EXCLUDED_COLUMNS = ("phone", "email")


def build_restaurant(restaurants: pd.DataFrame, locations: pd.DataFrame | None = None) -> pd.DataFrame:
    """Return one row per restaurant_id. Location fields are null when the join misses."""
    if restaurants.empty:
        return pd.DataFrame(columns=COLUMNS)
    city_map: dict[str, dict[str, object]] = {}
    if locations is not None and not locations.empty and "id" in locations.columns:
        for record in locations.to_dict("records"):
            key = token(record.get("id"))
            if key is None:
                continue
            city_map[key] = {
                "city": text(record.get("city")),
                "state": text(record.get("state")),
                "country": text(record.get("country")),
            }
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    ordered = restaurants.copy()
    ordered["_sk"] = ordered["id"].map(surrogate) if "id" in ordered.columns else None
    ordered = ordered.sort_values(["_sk"], kind="mergesort")
    for record in ordered.to_dict("records"):
        key = surrogate(record.get("id"))
        natural = token(record.get("id"))
        if key is None or natural is None or natural in seen:
            continue
        seen.add(natural)
        place = city_map.get(token(record.get("location_id")) or "", {})
        rows.append(
            {
                "restaurant_sk": key,
                "restaurant_id": natural,
                "name": text(record.get("name")),
                "cuisine_type": text(record.get("cuisine_type")),
                "is_active": flag(record.get("is_active")),
                "city": place.get("city"),
                "state": place.get("state"),
                "country": place.get("country"),
                "created_at": as_utc_timestamp(record.get("created_at")),
            }
        )
    return pd.DataFrame(rows, columns=COLUMNS)
