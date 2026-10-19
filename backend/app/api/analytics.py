"""Read-only dashboard endpoints over processed Parquet files."""

from fastapi import APIRouter, HTTPException, Query

from app.services import analytics_service
from app.services.analytics_service import AnalyticsDataError

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _call(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except AnalyticsDataError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/overview")
def get_processed_overview(
    start: str | None = Query(None),
    end: str | None = Query(None),
) -> dict:
    """Entity counts, completed-order value, and sentiment mix from Parquet."""
    return _call(analytics_service.overview, start=start, end=end)


@router.get("/restaurants")
def get_restaurant_performance(
    sort: str = Query("total_spend"),
    descending: bool = Query(True),
    cuisine: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    """Completed-order spend and stored ratings for each restaurant."""
    return _call(
        analytics_service.restaurant_performance,
        sort=sort,
        descending=descending,
        cuisine=cuisine,
        limit=limit,
        offset=offset,
    )


@router.get("/restaurants/{restaurant_id}")
def get_restaurant_detail(restaurant_id: int) -> dict:
    """Completed-order metrics and stored sentiment for one restaurant."""
    return _call(analytics_service.restaurant_detail, restaurant_id)


@router.get("/sentiment")
def get_sentiment(
    label: str | None = Query(None),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    """Stored sentiment distribution and a page of review results."""
    return _call(analytics_service.sentiment_report, label=label, limit=limit, offset=offset)


@router.get("/segments")
def get_segments() -> dict:
    """Stored customer-segment summary."""
    return _call(analytics_service.segments)


@router.get("/churn")
def get_churn(
    category: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    """Stored churn-risk categories and the highest stored scores."""
    return _call(analytics_service.churn, category=category, limit=limit)


@router.get("/recommendations/summary")
def get_recommendation_summary(limit: int = Query(10, ge=1, le=50)) -> dict:
    """How often each stored food or restaurant recommendation appears."""
    return _call(analytics_service.recommendation_summary, limit=limit)


@router.get("/recommendations/customers")
def get_recommendation_customers(limit: int = Query(50, ge=1, le=200)) -> dict:
    """Customer ids that already have stored recommendations."""
    return _call(analytics_service.recommendation_customers, limit=limit)


@router.get("/recommendations/{customer_id}")
def get_recommendations(customer_id: str) -> dict:
    """Stored food and restaurant recommendations for one customer."""
    return _call(analytics_service.recommendations_for, customer_id)


@router.get("/association/itemsets")
def get_itemsets(limit: int = Query(15, ge=1, le=50)) -> dict:
    """Stored frequent itemsets ordered by support."""
    return _call(analytics_service.association_itemsets, limit=limit)


@router.get("/association")
def get_association(
    sort: str = Query("lift"),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    """Stored association rules with support, confidence, and lift."""
    return _call(analytics_service.association_rules, sort=sort, limit=limit, offset=offset)


@router.get("/forecast/restaurants")
def get_forecast_restaurants() -> dict:
    """Restaurant ids present in the stored forecast file."""
    return _call(analytics_service.forecast_restaurants)


@router.get("/forecast")
def get_forecast(
    restaurant_id: str = Query(...),
    model_name: str = Query("ridge"),
    aggregation: str = Query("daily"),
) -> dict:
    """Stored history and forward forecast for one restaurant. Does not train."""
    return _call(
        analytics_service.forecast_series,
        restaurant_id=restaurant_id,
        model_name=model_name,
        aggregation=aggregation,
    )
