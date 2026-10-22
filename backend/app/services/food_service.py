"""Food item query services."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import FoodItem


def list_food_items(
    db: Session,
    *,
    skip: int = 0,
    limit: int = 50,
    restaurant_id: int | None = None,
    category: str | None = None,
) -> tuple[int, list[FoodItem]]:
    """Return total count and a page of food items."""
    filters = []
    if restaurant_id is not None:
        filters.append(FoodItem.restaurant_id == restaurant_id)
    if category is not None:
        filters.append(FoodItem.category == category)

    count_stmt = select(func.count()).select_from(FoodItem)
    stmt = select(FoodItem)
    if filters:
        count_stmt = count_stmt.where(*filters)
        stmt = stmt.where(*filters)

    total = db.scalar(count_stmt) or 0
    items = list(db.scalars(stmt.order_by(FoodItem.id).offset(skip).limit(limit)).all())
    return total, items


def get_food_item(db: Session, food_item_id: int) -> FoodItem | None:
    """Return a single food item by id, or None."""
    return db.get(FoodItem, food_item_id)
