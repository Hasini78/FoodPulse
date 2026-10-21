"""Read-only aggregates over processed Parquet files.

The functions below never write Parquet, never open PostgreSQL, and never
connect to Snowflake. Completed-order metrics use the same status rule as
``etl.transform.feature_engineering``: ``status`` lowercased, without
trimming, equals ``completed``.
"""

from __future__ import annotations

import json
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
    "They describe measured medians from the project customer file. "
    "They are not verified real-world identities or traits."
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
ASSOCIATION_NOTICE = (
    "Support is how often the item combination appears in completed-order baskets. "
    "Confidence is how often the consequent appears when the antecedent appears. "
    "Lift is how frequently the consequent occurs relative to its baseline frequency. "
    "Association is co-occurrence, not causation."
)
SENTIMENT_NOTICE = (
    "These rows score sample review text already stored in review_sentiment.parquet. "
    "overall_score is the stored VADER compound score, typically between -1 and 1. "
    "The page does not rescore reviews, prove customer satisfaction, or reflect live public opinion. "
    "Star ratings are restaurant-level sample reviews, not dish ratings."
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


def overview(start: str | None = None, end: str | None = None) -> dict[str, object]:
    """Count entities and completed-order value from processed files."""
    from app.services.dashboard_metrics import completed_metrics, forecast_window

    unavailable: list[str] = []
    restaurants = _count("restaurants.parquet", "id", unavailable)
    customers = _count("customers.parquet", "id", unavailable)
    orders = _count("orders.parquet", "id", unavailable)
    reviews = _count("reviews.parquet", "id", unavailable)
    completed_orders = None
    average_order_value = None
    completed_revenue = None
    monthly: list[dict[str, object]] = []
    order_definition = None
    try:
        try:
            frame = _read("orders.parquet", ["status", "total_amount", "order_date"])
        except AnalyticsDataError as exc:
            if "order_date" not in exc.message:
                raise
            unavailable.append(exc.message)
            frame = _read("orders.parquet", ["status", "total_amount"])
            frame = frame.assign(order_date=pd.NaT)
        metrics = completed_metrics(frame, start, end)
        completed_orders = metrics["completed_orders"]
        average_order_value = metrics["average_order_value"]
        completed_revenue = metrics["completed_revenue"]
        monthly = metrics["monthly"]
        order_definition = metrics["definition"]
    except AnalyticsDataError as exc:
        unavailable.append(exc.message)
    except ValueError as exc:
        raise AnalyticsDataError(str(exc), status_code=422) from exc
    average_rating = _average_rating(unavailable)
    sentiment = _optional(sentiment_distribution, unavailable)
    segment_items = _optional(lambda: segments()["items"], unavailable)
    churn_items = _optional(lambda: churn()["summary"], unavailable)
    forecast = _optional_forecast(forecast_window, unavailable)
    return {
        "source": "processed_parquet",
        "restaurants": restaurants,
        "customers": customers,
        "orders": orders,
        "reviews": reviews,
        "completed_orders": completed_orders,
        "completed_revenue": completed_revenue,
        "average_order_value": average_order_value,
        "average_rating": average_rating,
        "order_definition": order_definition,
        "monthly": monthly,
        "sentiment": sentiment,
        "segments": segment_items,
        "churn": churn_items,
        "forecast": forecast,
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
        "definition": "Completed orders are rows whose lowercased status is 'completed'. Spend is the sum of total_amount. Average rating is the restaurant sample-review mean from restaurant_features.parquet, not a live public rating and not a dish rating.",
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
    from app.services.dashboard_metrics import aspect_counts

    aspects: list[dict[str, object]] = []
    aspect_note = None
    try:
        aspect_frame = _read(
            "review_sentiment.parquet",
            ["food_sent", "service_sent", "ambience_sent", "price_sent"],
        )
        aspects = aspect_counts(aspect_frame)
    except AnalyticsDataError as exc:
        aspect_note = exc.message
    by_month: list[dict[str, object]] = []
    month_note = None
    try:
        month_frame = _read(
            "sentiment_by_month.parquet",
            ["month", "review_count", "positive_count", "negative_count", "neutral_count", "invalid_count"],
        )
        by_month = [_row(record) for record in month_frame.sort_values("month").to_dict(orient="records")]
    except AnalyticsDataError as exc:
        month_note = exc.message
    return {
        "source": "processed_parquet",
        "backend": "stored_output",
        "backend_note": SENTIMENT_NOTICE,
        "distribution": distribution,
        "by_restaurant": by_restaurant,
        "by_month": by_month,
        "aspects": aspects,
        "aspects_unavailable": aspect_note,
        "monthly_unavailable": month_note,
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
    identifiers = sort_customer_ids(frame["customer_id"].dropna().tolist())
    return {"source": "processed_parquet", "total": len(identifiers), "customer_ids": identifiers[:limit]}


def sort_customer_ids(values: list[object]) -> list[str]:
    """Sort customer ids numerically when they are numbers, not lexicographically.

    ``sorted({"1", "2", "10"})`` would yield ``1, 10, 2``. Numeric sort yields
    ``1, 2, 10``. Non-numeric tokens sort after numbers. The unique set is taken
    after string conversion so ``1`` and ``"1"`` are the same id.
    """
    unique = {str(value).strip() for value in values if not _missing(value) and str(value).strip()}
    return sorted(unique, key=_customer_id_sort_key)


def _customer_id_sort_key(value: str) -> tuple:
    try:
        number = float(value)
    except ValueError:
        return (1, value.casefold(), value)
    if number.is_integer():
        return (0, int(number), value)
    return (0, number, value)


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
        "notice": ASSOCIATION_NOTICE,
        "mining": _association_mining_context(),
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
    names = _lookup("restaurants.parquet", "id", "name")
    restaurants = [{"id": identifier, "name": names.get(identifier)} for identifier in identifiers]
    return {"restaurant_ids": identifiers, "restaurants": restaurants, "models": models, "aggregations": aggregations}


def forecast_series(restaurant_id: str, model_name: str = "ridge", aggregation: str = "daily") -> dict[str, object]:
    """Join stored history to the stored forward forecast for one restaurant."""
    if not restaurant_id.strip():
        raise AnalyticsDataError("restaurant_id is required", status_code=422)
    history = _filter(
        "demand_forecast_history.parquet",
        ["level", "restaurant_id", "period_start", "actual_demand", "aggregation"],
        [("level", "=", "restaurant"), ("restaurant_id", "=", restaurant_id), ("aggregation", "=", aggregation)],
    )
    forecast_columns = [
        "level",
        "restaurant_id",
        "forecast_date",
        "predicted_demand",
        "aggregation",
        "model_name",
        "forecast_role",
        "evaluation_mae",
        "evaluation_rmse",
        "evaluation_wape",
    ]
    forecast_filters = [
        ("level", "=", "restaurant"),
        ("restaurant_id", "=", restaurant_id),
        ("aggregation", "=", aggregation),
        ("model_name", "=", model_name),
        ("forecast_role", "=", "forward"),
    ]
    try:
        forecasts = _filter("demand_forecasts.parquet", [*forecast_columns, "horizon"], forecast_filters)
    except AnalyticsDataError:
        forecasts = _filter("demand_forecasts.parquet", forecast_columns, forecast_filters)
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
    history_dates = [point["date"] for point in points if point["actual"] is not None]
    forecast_dates = [point["date"] for point in points if point["predicted"] is not None]
    overlap = sum(1 for point in points if point["actual"] is not None and point["predicted"] is not None)
    horizon = None
    if "horizon" in forecasts.columns and forecasts["horizon"].notna().any():
        horizon_values = pd.to_numeric(forecasts["horizon"], errors="coerce").dropna()
        if not horizon_values.empty:
            horizon = int(horizon_values.iloc[0])
    return {
        "source": "processed_parquet",
        "notice": FORECAST_NOTICE,
        "intervals": None,
        "restaurant_id": restaurant_id,
        "model_name": model_name,
        "aggregation": aggregation,
        "horizon": horizon,
        "history_start": history_dates[0] if history_dates else None,
        "history_end": history_dates[-1] if history_dates else None,
        "forecast_start": forecast_dates[0] if forecast_dates else None,
        "forecast_end": forecast_dates[-1] if forecast_dates else None,
        "history_points": len(history_dates),
        "forecast_points": len(forecast_dates),
        "overlap_points": overlap,
        "comparable": bool(history_dates) and bool(forecast_dates),
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


_CACHE: dict[tuple[str, tuple[str, ...]], tuple[float, pd.DataFrame]] = {}


def restaurant_detail(restaurant_id: int) -> dict[str, object]:
    """One restaurant from the same completed-order definition as the ranking."""
    page = restaurant_performance(limit=100, offset=0)
    matches = [item for item in page["items"] if int(item["restaurant_id"]) == int(restaurant_id)]
    if not matches:
        raise AnalyticsDataError(f"Restaurant {restaurant_id} is not in the processed restaurant file.", status_code=404)
    sentiment = None
    try:
        rows = _read(
            "sentiment_by_restaurant.parquet",
            ["restaurant_id", "review_count", "positive_count", "negative_count", "neutral_count", "invalid_count", "mean_score"],
        )
        match = rows.loc[pd.to_numeric(rows["restaurant_id"], errors="coerce") == int(restaurant_id)]
        if not match.empty:
            sentiment = _row(match.iloc[0].to_dict())
    except AnalyticsDataError:
        sentiment = None
    return {"source": "processed_parquet", "restaurant": matches[0], "sentiment": sentiment}


def association_itemsets(limit: int = 15) -> dict[str, object]:
    """Return the largest stored frequent itemsets by support."""
    frame = _read(
        "association_frequent_itemsets.parquet",
        ["item_names", "itemset_size", "support", "support_count"],
    )
    ordered = frame.sort_values("support", ascending=False, na_position="last").head(limit)
    return {
        "source": "processed_parquet",
        "notice": (
            "Support is the share of completed-order baskets that contain the itemset. "
            "These rows are stored Apriori output. Association is not causation."
        ),
        "mining": _association_mining_context(),
        "items": [_row(record) for record in ordered.to_dict(orient="records")],
    }


def recommendation_summary(limit: int = 10) -> dict[str, object]:
    """Count how often each stored recommendation appears. This does not re-rank."""
    foods = _read("food_recommendations.parquet", ["food_item_id", "recommendation_score"])
    restaurants = _read("restaurant_recommendations.parquet", ["restaurant_id", "recommendation_score"])
    food_names = _lookup("food_items.parquet", "id", "name")
    restaurant_names = _lookup("restaurants.parquet", "id", "name")
    return {
        "source": "processed_parquet",
        "notice": RECOMMENDATION_NOTICE,
        "foods": _ranked_names(foods, "food_item_id", food_names, limit),
        "restaurants": _ranked_names(restaurants, "restaurant_id", restaurant_names, limit),
    }


def _ranked_names(frame: pd.DataFrame, key: str, names: dict[str, str | None], limit: int) -> list[dict[str, object]]:
    if frame.empty:
        return []
    scores = pd.to_numeric(frame["recommendation_score"], errors="coerce")
    grouped = (
        frame.assign(_score=scores)
        .groupby(key, dropna=False)
        .agg(recommendations=("_score", "size"), mean_score=("_score", "mean"))
        .reset_index()
        .sort_values(["recommendations", "mean_score"], ascending=False)
        .head(limit)
    )
    rows = []
    for record in grouped.to_dict(orient="records"):
        identifier = record.get(key)
        rows.append(
            {
                "id": _json_value(identifier),
                "name": names.get(str(identifier)),
                "recommendations": int(record["recommendations"]),
                "mean_score": _json_value(record["mean_score"]),
            }
        )
    return rows


def _cached_parquet(path: Path, columns: list[str]) -> pd.DataFrame:
    """Reuse a Parquet read until the file's modification time changes."""
    stamp = path.stat().st_mtime
    key = (str(path.resolve()), tuple(columns))
    cached = _CACHE.get(key)
    if cached is not None and cached[0] == stamp:
        return cached[1].copy()
    frame = pd.read_parquet(path, columns=columns)
    _CACHE[key] = (stamp, frame)
    return frame.copy()


def _optional(func, unavailable: list[str]):
    try:
        return func()
    except AnalyticsDataError as exc:
        unavailable.append(exc.message)
        return []


def _optional_forecast(func, unavailable: list[str]) -> dict[str, object] | None:
    try:
        frame = _read(
            "demand_forecasts.parquet",
            ["level", "forecast_role", "model_name", "aggregation", "forecast_date", "restaurant_id", "horizon"],
        )
        return func(frame)
    except AnalyticsDataError as exc:
        unavailable.append(exc.message)
        return None
    except ValueError as exc:
        unavailable.append(str(exc))
        return None


def _average_rating(unavailable: list[str]) -> float | None:
    try:
        frame = _read("reviews.parquet", ["rating"])
    except AnalyticsDataError as exc:
        unavailable.append(exc.message)
        return None
    return _mean(frame["rating"])


def _count(filename: str, column: str, unavailable: list[str]) -> int | None:
    try:
        frame = _read(filename, [column])
    except AnalyticsDataError as exc:
        unavailable.append(exc.message)
        return None
    return int(frame[column].notna().sum())


def _association_mining_context() -> dict[str, object] | None:
    """Return stored mining thresholds and basket counts when the metrics file exists."""
    path = processed_dir() / "association_mining_metrics.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    filters = payload.get("filters") if isinstance(payload.get("filters"), dict) else {}
    transactions = payload.get("transactions") if isinstance(payload.get("transactions"), dict) else {}
    thresholds = payload.get("thresholds") if isinstance(payload.get("thresholds"), dict) else {}
    scope = payload.get("scope") if isinstance(payload.get("scope"), dict) else {}
    return {
        "file": "association_mining_metrics.json",
        "basket": filters.get("basket"),
        "valid_transactions": transactions.get("valid_transactions"),
        "min_support": thresholds.get("min_support"),
        "min_confidence": thresholds.get("min_confidence"),
        "min_lift": thresholds.get("min_lift"),
        "scope_mode": scope.get("mode"),
        "algorithm": payload.get("algorithm"),
    }


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
    return _cached_parquet(path, columns)


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
