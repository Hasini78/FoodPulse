"""Statistics schemas."""

from pydantic import BaseModel


class OverviewStats(BaseModel):
    """Platform-wide overview metrics."""

    total_restaurants: int
    total_customers: int
    total_orders: int
    total_reviews: int
    average_rating: float | None
