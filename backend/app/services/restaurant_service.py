"""Restaurant query services."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models import Restaurant


def list_restaurants(
    db: Session,
    *,
    skip: int = 0,
    limit: int = 50,
) -> tuple[int, list[Restaurant]]:
    """Return total count and a page of restaurants."""
    total = db.scalar(select(func.count()).select_from(Restaurant)) or 0
    stmt = (
        select(Restaurant)
        .options(joinedload(Restaurant.location))
        .order_by(Restaurant.id)
        .offset(skip)
        .limit(limit)
    )
    items = list(db.scalars(stmt).unique().all())
    return total, items


def get_restaurant(db: Session, restaurant_id: int) -> Restaurant | None:
    """Return a single restaurant by id, or None."""
    stmt = (
        select(Restaurant)
        .options(joinedload(Restaurant.location))
        .where(Restaurant.id == restaurant_id)
    )
    return db.scalars(stmt).unique().first()
