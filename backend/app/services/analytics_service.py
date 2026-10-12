"""Read-only aggregates over processed Parquet files.

The functions below never write Parquet, never open PostgreSQL, and never
connect to Snowflake. Completed-order metrics use the same status rule as
``etl.transform.feature_engineering``: ``status`` lowercased, without
trimming, equals ``completed``.
"""

from __future__ import annotations

import math
import os
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

COMPLETED_ORDER_STATUS = "completed"
PROJECT_ROOT = Path(__file__).resolve().parents[3]

RESTAURANT_SORTS = {
    "name",
    "completed_orders",
    "total_spend",
    "avg_order_value",
    "avg_rating",
}
ASSOCIATION_SORTS = {"lift", "confidence", "support"}
CHURN_NOTICE = (
    "Risk categories come from the existing rule-based score. "
    "They are model-derived classifications, not confirmed customer behavior."
)
SEGMENT_NOTICE = (
    "Segment labels are the names already stored by the clustering job. "
    "They describe measured medians. They are not a new interpretation."
)
RECOMMENDATION_NOTICE = (
    "Scores are the ranking scores already stored by the recommender. "
    "They are not purchase probabilities."
)
FORECAST_NOTICE = (
    "Historical values are actual demand from demand_forecast_history.parquet. "
    "Predicted values are the stored forward forecast for the selected model. "
    "This request does not train a model. Holdout error is copied from the forecast file."
)


class AnalyticsDataError(Exception):
    """A processed file is missing or does not have the expected columns."""

    def __init__(self, message: str, status_code: int = 404) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def processed_dir() -> Path:
    """Return the processed directory, overridable for tests."""
    override = os.environ.get("FOODPULSE_PROCESSED_DIR")
    if override:
        return Path(override)
    return PROJECT_ROOT / "data" / "processed"


def overview() -> dict[str, object]:
    """Count entities and completed-order value from processed files."""
    unavailable: list[str] = []
    restaurants = _count("restaurants.parquet", "id", unavailable)
    customers = _count("customers.parquet", "id", unavailable)
    orders = _count("orders.parquet", "id", unavailable)
    reviews = _count("reviews.parquet", "id", unavailable)
    completed_orders = None
    average_order_value = None
    try:
        frame = _read("orders.parquet", ["status", "total_amount"])
        completed = _completed(frame)
        completed_orders = int(len(completed))
        average_order_value = _mean(completed["total_amount"])
    except AnalyticsDataError as exc:
        unavailable.append(exc.message)
    sentiment = []
    try:
        sentiment = sentiment_distribution()
    except AnalyticsDataError as exc:
        unavailable.append(exc.message)
    return {
        "source": "processed_parquet",
        "restaurants": restaurants,
        "customers": customers,
        "orders": orders,
        "reviews": reviews,
        "completed_orders": completed_orders,
        "average_order_value": average_order_value,
        "sentiment": sentiment,
        "unavailable": unavailable,
    }


def restaurant_performance(
    sort: str = "total_spend",
    descending: bool = True,
    cuisine: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, object]:
    """Aggregate completed-order spend and attach stored average ratings."""
    _require_sort(sort, RESTAURANT_SORTS)
    orders = _read("orders.parquet", ["restaurant_id", "status", "total_amount"])
    restaurants = _read("restaurants.parquet", ["id", "name", "cuisine_type"])
    completed = _completed(orders)
    if completed.empty:
        grouped = pd.DataFrame(columns=["restaurant_id", "completed_orders", "total_spend", "avg_order_value"])
    else:
        grouped = (
            completed.groupby("restaurant_id", dropna=False)
            .agg(
                completed_orders=("total_amount", "size"),
                total_spend=("total_amount", "sum"),
                avg_order_value=("total_amount", "mean"),
            )
            .reset_index()
        )
    directory = restaurants.rename(columns={"id": "restaurant_id"})
    frame = directory.merge(grouped, on="restaurant_id", how="left")
    frame["completed_orders"] = pd.to_numeric(frame["completed_orders"], errors="coerce").fillna(0).astype(int)
    frame["total_spend"] = pd.to_numeric(frame["total_spend"], errors="coerce").fillna(0.0)
    features_note = None
    try:
        features = _read(
            "restaurant_features.parquet",
            ["restaurant_id", "avg_rating", "review_volume", "order_volume", "feature_reference_date"],
        )
        frame = frame.merge(features, on="restaurant_id", how="left")
    except AnalyticsDataError as exc:
        features_note = exc.message
        frame["avg_rating"] = None
        frame["review_volume"] = None
        frame["order_volume"] = None
        frame["feature_reference_date"] = None
    cuisines = sorted(str(value) for value in frame["cuisine_type"].dropna().unique())
    if cuisine:
        frame = frame.loc[frame["cuisine_type"] == cuisine]
    ascending = not descending if sort != "name" else not descending
    if sort == "name":
        ascending = not descending
    frame = frame.sort_values(sort, ascending=ascending, na_position="last", kind="mergesort")
    total = int(len(frame))
    page = frame.iloc[offset : offset + limit]
    return {
        "source": "processed_parquet",
        "definition": "Completed orders are rows whose lowercased status is 'completed'. Spend is the sum of total_amount. Average rating comes from restaurant_features.parquet.",
        "features_unavailable": features_note,
        "total": total,
        "cuisines": cuisines,
        "items": [_row(record) for record in page.to_dict(orient="records")],
    }


def sentiment_report(label: str | None = None, limit: int = 25, offset: int = 0) -> dict[str, object]:
    """Return stored sentiment counts and a page of review-level results."""
    distribution = sentiment_distribution()
    by_restaurant = _sentiment_by_restaurant()
    reviews = _read("review_sentiment.parquet", ["review_id", "overall_sentiment", "overall_score"])
    text = _read("reviews.parquet", ["id", "restaurant_id", "rating", "review_text"])
    merged = reviews.merge(text, left_on="review_id", right_on="id", how="left")
    if label:
        merged = merged.loc[merged["overall_sentiment"] == label]
    total = int(len(merged))
    page = merged.sort_values("review_id").iloc[offset : offset + limit]
    items = []
    for record in page.to_dict(orient="records"):
        raw_text = record.get("review_text")
        text_value = None if _missing(raw_text) else str(raw_text)[:240]
        items.append(
            {
                "review_id": _json_value(record.get("review_id")),
                "restaurant_id": _json_value(record.get("restaurant_id")),
                "rating": _json_value(record.get("rating")),
                "overall_sentiment": _json_value(record.get("overall_sentiment")),
                "overall_score": _json_value(record.get("overall_score")),
                "review_text": text_value,
            }
        )
    return {
        "source": "processed_parquet",
        "distribution": distribution,
        "by_restaurant": by_restaurant,
        "labels": sorted({item["label"] for item in distribution}),
        "total_reviews": total,
        "items": items,
    }


def sentiment_distribution() -> list[dict[str, object]]:
    """Count stored overall sentiment labels. Empty input returns an empty list."""
    frame = _read("review_sentiment.parquet", ["overall_sentiment"])
    if frame.empty:
        return []
    counts = frame["overall_sentiment"].fillna("(missing)").astype(str).value_counts()
    total = int(counts.sum())
    rows = []
    for label, count in counts.items():
        rows.append(
            {
                "label": str(label),
                "count": int(count),
                "proportion": (float(count) / total) if total else None,
            }
        )
    return rows


def segments() -> dict[str, object]:
    """Return the stored cluster summary without renaming segments."""
    frame = _read(
        "customer_segment_summary.parquet",
        [
            "cluster_id",
            "segment_label",
            "count",
            "percent",
            "median_recency_days",
            "median_order_frequency",
            "median_total_spend",
            "median_avg_order_value",
            "median_avg_rating",
        ],
    )
    return {
        "source": "processed_parquet",
        "notice": SEGMENT_NOTICE,
        "items": [_row(record) for record in frame.to_dict(orient="records")],
    }


def churn(category: str | None = None, limit: int = 20) -> dict[str, object]:
    """Return stored risk categories and the highest stored scores."""
    summary = _read(
        "customer_churn_summary.parquet",
        ["risk_category", "customer_count", "share", "median_inactivity_days", "median_order_frequency", "median_total_spend"],
    )
    detail = _read(
        "customer_churn_risk.parquet",
        ["customer_id", "risk_category", "risk_score", "inactivity_days", "order_frequency", "total_spend", "reason_codes"],
    )
    categories = sorted(str(value) for value in summary["risk_category"].dropna().unique())
    if category:
        detail = detail.loc[detail["risk_category"] == category]
    if detail.empty:
        top: list[dict[str, object]] = []
    else:
        ordered = detail.sort_values(["risk_score", "customer_id"], ascending=[False, True], na_position="last")
        top = [_row(record) for record in ordered.head(limit).to_dict(orient="records")]
    return {
        "source": "processed_parquet",
        "notice": CHURN_NOTICE,
        "categories": categories,
        "summary": [_row(record) for record in summary.to_dict(orient="records")],
        "customers": top,
    }


def recommendation_customers(limit: int = 50) -> dict[str, object]:
    """List customer ids that already have a stored recommendation."""
    frame = _read("food_recommendations.parquet", ["customer_id"])
    identifiers = sorted({str(value) for value in frame["customer_id"].dropna().unique()})
    return {"source": "processed_parquet", "total": len(identifiers), "customer_ids": identifiers[:limit]}


def recommendations_for(customer_id: str) -> dict[str, object]:
    """Return stored food and restaurant recommendations for one customer."""
    if not customer_id.strip() or "/" in customer_id or "\\" in customer_id:
        raise AnalyticsDataError("customer_id is invalid", status_code=422)
    foods = _read(
        "food_recommendations.parquet",
        ["customer_id", "food_item_id", "restaurant_id", "recommendation_score", "rank", "reason"],
    )
    restaurants = _read(
        "restaurant_recommendations.parquet",
        ["customer_id", "restaurant_id", "recommendation_score", "rank", "reason"],
    )
    food_rows = foods.loc[foods["customer_id"].astype(str) == customer_id].sort_values("rank")
    restaurant_rows = restaurants.loc[restaurants["customer_id"].astype(str) == customer_id].sort_values("rank")
    names = _lookup("food_items.parquet", "id", "name")
    restaurant_names = _lookup("restaurants.parquet", "id", "name")
    food_items = []
    for record in food_rows.to_dict(orient="records"):
        food_items.append(
            {
                "food_item_id": _json_value(record.get("food_item_id")),
                "food_name": names.get(str(record.get("food_item_id"))),
                "restaurant_id": _json_value(record.get("restaurant_id")),
                "restaurant_name": restaurant_names.get(str(record.get("restaurant_id"))),
                "recommendation_score": _json_value(record.get("recommendation_score")),
                "rank": _json_value(record.get("rank")),
                "reason": _json_value(record.get("reason")),
            }
        )
    restaurant_items = []
    for record in restaurant_rows.to_dict(orient="records"):
        restaurant_items.append(
            {
                "restaurant_id": _json_value(record.get("restaurant_id")),
                "restaurant_name": restaurant_names.get(str(record.get("restaurant_id"))),
                "recommendation_score": _json_value(record.get("recommendation_score")),
                "rank": _json_value(record.get("rank")),
                "reason": _json_value(record.get("reason")),
            }
        )
    return {
        "source": "processed_parquet",
        "notice": RECOMMENDATION_NOTICE,
        "customer_id": customer_id,
        "foods": food_items,
        "restaurants": restaurant_items,
    }


def association_rules(sort: str = "lift", limit: int = 25, offset: int = 0) -> dict[str, object]:
    """Return a page of stored association rules."""
    _require_sort(sort, ASSOCIATION_SORTS)
    frame = _read(
        "association_rules.parquet",
        ["antecedent_names", "consequent_names", "support", "confidence", "lift", "support_count", "restaurant_scope"],
    )
    frame = frame.sort_values(sort, ascending=False, na_position="last", kind="mergesort")
    total = int(len(frame))
    page = frame.iloc[offset : offset + limit]
    return {
        "source": "processed_parquet",
        "total": total,
        "items": [_row(record) for record in page.to_dict(orient="records")],
    }


def forecast_restaurants() -> dict[str, object]:
    """List restaurant ids that have a stored restaurant-level forecast."""
    frame = _read("demand_forecasts.parquet", ["level", "restaurant_id", "aggregation", "model_name"])
    subset = frame.loc[frame["level"] == "restaurant"]
    identifiers = sorted({str(value) for value in subset["restaurant_id"].dropna().unique()})
    models = sorted({str(value) for value in subset["model_name"].dropna().unique()})
    aggregations = sorted({str(value) for value in subset["aggregation"].dropna().unique()})
    return {"restaurant_ids": identifiers, "models": models, "aggregations": aggregations}


def forecast_series(restaurant_id: str, model_name: str = "ridge", aggregation: str = "daily") -> dict[str, object]:
    """Join stored history to the stored forward forecast for one restaurant."""
    if not restaurant_id.strip():
        raise AnalyticsDataError("restaurant_id is required", status_code=422)
    history = _filter(
        "demand_forecast_history.parquet",
        ["level", "restaurant_id", "period_start", "actual_demand", "aggregation"],
        [("level", "=", "restaurant"), ("restaurant_id", "=", restaurant_id), ("aggregation", "=", aggregation)],
    )
    forecasts = _filter(
        "demand_forecasts.parquet",
        ["level", "restaurant_id", "forecast_date", "predicted_demand", "aggregation", "model_name", "forecast_role", "evaluation_mae", "evaluation_rmse", "evaluation_wape"],
        [
            ("level", "=", "restaurant"),
            ("restaurant_id", "=", restaurant_id),
            ("aggregation", "=", aggregation),
            ("model_name", "=", model_name),
            ("forecast_role", "=", "forward"),
        ],
    )
    return build_forecast_series(history, forecasts, restaurant_id, model_name, aggregation)


def build_forecast_series(
    history: pd.DataFrame,
    forecasts: pd.DataFrame,
    restaurant_id: str,
    model_name: str,
    aggregation: str,
) -> dict[str, object]:
    """Combine actual history and forward predictions. Holdout predictions are excluded."""
    actual = history.copy()
    if not actual.empty:
        actual["date"] = pd.to_datetime(actual["period_start"], utc=True).dt.strftime("%Y-%m-%d")
        actual = actual.groupby("date", as_index=False)["actual_demand"].mean()
    else:
        actual = pd.DataFrame(columns=["date", "actual_demand"])
    predicted = forecasts.copy()
    if not predicted.empty and "forecast_role" in predicted.columns:
        predicted = predicted.loc[predicted["forecast_role"] == "forward"]
    if not predicted.empty:
        predicted["date"] = pd.to_datetime(predicted["forecast_date"], utc=True).dt.strftime("%Y-%m-%d")
        predicted = predicted.groupby("date", as_index=False).agg(
            predicted_demand=("predicted_demand", "mean"),
            evaluation_mae=("evaluation_mae", "first"),
            evaluation_rmse=("evaluation_rmse", "first"),
            evaluation_wape=("evaluation_wape", "first"),
        )
    else:
        predicted = pd.DataFrame(columns=["date", "predicted_demand", "evaluation_mae", "evaluation_rmse", "evaluation_wape"])
    merged = actual.merge(predicted, on="date", how="outer").sort_values("date")
    metrics = {
        "mae": _mean_first(predicted, "evaluation_mae"),
        "rmse": _mean_first(predicted, "evaluation_rmse"),
        "wape": _mean_first(predicted, "evaluation_wape"),
    }
    points = []
    for record in merged.to_dict(orient="records"):
        points.append(
            {
                "date": record.get("date"),
                "actual": _json_value(record.get("actual_demand")),
                "predicted": _json_value(record.get("predicted_demand")),
            }
        )
    return {
        "source": "processed_parquet",
        "notice": FORECAST_NOTICE,
        "restaurant_id": restaurant_id,
        "model_name": model_name,
        "aggregation": aggregation,
        "evaluation": metrics,
        "points": points,
    }


def _sentiment_by_restaurant() -> list[dict[str, object]]:
    frame = _read(
        "sentiment_by_restaurant.parquet",
        ["restaurant_id", "review_count", "positive_count", "negative_count", "neutral_count", "invalid_count", "mean_score"],
    )
    names = _lookup("restaurants.parquet", "id", "name")
    ordered = frame.sort_values("review_count", ascending=False).head(15)
    items = []
    for record in ordered.to_dict(orient="records"):
        item = _row(record)
        item["restaurant_name"] = names.get(str(record.get("restaurant_id")))
        items.append(item)
    return items


def _completed(frame: pd.DataFrame) -> pd.DataFrame:
    status = frame["status"].fillna("").astype(str).str.lower()
    return frame.loc[status == COMPLETED_ORDER_STATUS].copy()


def _count(filename: str, column: str, unavailable: list[str]) -> int | None:
    try:
        frame = _read(filename, [column])
    except AnalyticsDataError as exc:
        unavailable.append(exc.message)
        return None
    return int(frame[column].notna().sum())


def _read(filename: str, columns: list[str]) -> pd.DataFrame:
    path = processed_dir() / filename
    if not path.is_file():
        raise AnalyticsDataError(f"{filename} is not available")
    schema = pq.read_schema(path)
    missing = [column for column in columns if column not in schema.names]
    if missing:
        raise AnalyticsDataError(
            f"{filename} is missing required columns: {', '.join(missing)}",
            status_code=422,
        )
    return pd.read_parquet(path, columns=columns)


def _filter(filename: str, columns: list[str], filters: list[tuple[str, str, str]]) -> pd.DataFrame:
    path = processed_dir() / filename
    if not path.is_file():
        raise AnalyticsDataError(f"{filename} is not available")
    schema = pq.read_schema(path)
    missing = [column for column in columns if column not in schema.names]
    if missing:
        raise AnalyticsDataError(
            f"{filename} is missing required columns: {', '.join(missing)}",
            status_code=422,
        )
    table = pq.read_table(path, columns=columns, filters=filters)
    return table.to_pandas()


def _lookup(filename: str, key: str, value: str) -> dict[str, str | None]:
    try:
        frame = _read(filename, [key, value])
    except AnalyticsDataError:
        return {}
    mapping: dict[str, str | None] = {}
    for record in frame.to_dict(orient="records"):
        if _missing(record.get(key)):
            continue
        mapping[str(record[key])] = None if _missing(record.get(value)) else str(record[value])
    return mapping


def _require_sort(sort: str, allowed: set[str]) -> None:
    if sort not in allowed:
        choices = ", ".join(sorted(allowed))
        raise AnalyticsDataError(f"Unsupported sort '{sort}'. Use one of: {choices}", status_code=422)


def _mean(series: pd.Series) -> float | None:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().sum() == 0:
        return None
    return float(numeric.mean())


def _mean_first(frame: pd.DataFrame, column: str) -> float | None:
    if frame.empty or column not in frame.columns:
        return None
    return _json_value(frame.iloc[0][column])


def _row(record: dict[str, object]) -> dict[str, object]:
    return {key: _json_value(value) for key, value in record.items()}


def _json_value(value: object) -> object:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def _missing(value: object) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except TypeError:
        return False
