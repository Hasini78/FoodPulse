"""Sentiment counts by restaurant, city, cuisine, and month.

Joins use the columns that exist on the sample tables:

- ``reviews.id``, ``reviews.restaurant_id``, ``reviews.created_at``
- ``restaurants.id``, ``restaurants.cuisine_type``, ``restaurants.location_id``
- ``locations.id``, ``locations.city``

Dimension tables are deduped on their ids before the join so a repeated
location or restaurant row cannot multiply review counts.
"""

from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)


def aggregate_trends(
    scored: pd.DataFrame,
    reviews: pd.DataFrame,
    restaurants: pd.DataFrame,
    locations: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """Return one row-per-group trend table for each requested dimension."""
    linked = _link(scored, reviews, restaurants, locations)
    if len(linked) != scored["review_id"].nunique():
        raise RuntimeError("Aggregation changed the number of scored reviews")
    return {
        "by_restaurant": _summarize(linked, "restaurant_id"),
        "by_city": _summarize(linked, "city"),
        "by_cuisine": _summarize(linked, "cuisine_type"),
        "by_month": _summarize(linked, "month"),
    }


def _link(
    scored: pd.DataFrame,
    reviews: pd.DataFrame,
    restaurants: pd.DataFrame,
    locations: pd.DataFrame,
) -> pd.DataFrame:
    review_dim = reviews.loc[:, ["id", "restaurant_id", "created_at"]].drop_duplicates(subset=["id"])
    restaurant_dim = restaurants.loc[:, ["id", "cuisine_type", "location_id"]].drop_duplicates(subset=["id"])
    location_dim = locations.loc[:, ["id", "city"]].drop_duplicates(subset=["id"])
    linked = (
        scored.merge(review_dim, left_on="review_id", right_on="id", how="left")
        .merge(restaurant_dim, left_on="restaurant_id", right_on="id", how="left", suffixes=("", "_restaurant"))
        .merge(location_dim, left_on="location_id", right_on="id", how="left", suffixes=("", "_location"))
    )
    created = pd.to_datetime(linked["created_at"], utc=True, format="mixed")
    linked["month"] = created.dt.strftime("%Y-%m")
    return linked


def _summarize(frame: pd.DataFrame, key: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    grouped = frame.groupby(key, dropna=False)
    for name, group in grouped:
        scores = pd.to_numeric(group["overall_score"], errors="coerce")
        rows.append(
            {
                key: None if pd.isna(name) else name,
                "review_count": int(group["review_id"].nunique()),
                "positive_count": int((group["overall_sentiment"] == "positive").sum()),
                "negative_count": int((group["overall_sentiment"] == "negative").sum()),
                "neutral_count": int((group["overall_sentiment"] == "neutral").sum()),
                "invalid_count": int((group["overall_sentiment"] == "invalid").sum()),
                "mean_score": None if scores.dropna().empty else float(scores.mean()),
            }
        )
    result = pd.DataFrame(rows)
    if result.empty:
        return result
    logger.info("Aggregated sentiment by %s into %s groups", key, len(result))
    return result.sort_values(key, kind="stable").reset_index(drop=True)
