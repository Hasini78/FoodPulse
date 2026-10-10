"""Statistics query services."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Customer, Order, Restaurant, Review
from app.schemas.stats import OverviewStats


def get_overview_stats(db: Session) -> OverviewStats:
    """Compute platform overview aggregates."""
    total_restaurants = db.scalar(select(func.count()).select_from(Restaurant)) or 0
    total_customers = db.scalar(select(func.count()).select_from(Customer)) or 0
    total_orders = db.scalar(select(func.count()).select_from(Order)) or 0
    total_reviews = db.scalar(select(func.count()).select_from(Review)) or 0
    average_rating = db.scalar(select(func.avg(Review.rating)))

    return OverviewStats(
        total_restaurants=total_restaurants,
        total_customers=total_customers,
        total_orders=total_orders,
        total_reviews=total_reviews,
        average_rating=round(float(average_rating), 2) if average_rating is not None else None,
    )
