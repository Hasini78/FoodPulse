"""Customer query services."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Customer


def list_customers(
    db: Session,
    *,
    skip: int = 0,
    limit: int = 50,
) -> tuple[int, list[Customer]]:
    """Return total count and a page of customers."""
    total = db.scalar(select(func.count()).select_from(Customer)) or 0
    stmt = select(Customer).order_by(Customer.id).offset(skip).limit(limit)
    items = list(db.scalars(stmt).all())
    return total, items
