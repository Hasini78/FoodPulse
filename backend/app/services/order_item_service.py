"""Order item query services."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import FoodItem, Order, OrderItem


def list_order_items(
    db: Session,
    *,
    skip: int = 0,
    limit: int = 50,
    order_id: int | None = None,
    food_item_id: int | None = None,
    restaurant_id: int | None = None,
) -> tuple[int, list[OrderItem]]:
    """Return total count and a page of order lines.

    A restaurant filter inner-joins the parent order and food item and keeps
    only lines whose order and food item both belong to that restaurant.
    """
    stmt = select(OrderItem)
    count_stmt = select(func.count(OrderItem.id))

    if order_id is not None:
        stmt = stmt.where(OrderItem.order_id == order_id)
        count_stmt = count_stmt.where(OrderItem.order_id == order_id)
    if food_item_id is not None:
        stmt = stmt.where(OrderItem.food_item_id == food_item_id)
        count_stmt = count_stmt.where(OrderItem.food_item_id == food_item_id)
    if restaurant_id is not None:
        stmt = (
            stmt.join(Order, OrderItem.order_id == Order.id)
            .join(FoodItem, OrderItem.food_item_id == FoodItem.id)
            .where(Order.restaurant_id == restaurant_id)
            .where(FoodItem.restaurant_id == restaurant_id)
        )
        count_stmt = (
            count_stmt.join(Order, OrderItem.order_id == Order.id)
            .join(FoodItem, OrderItem.food_item_id == FoodItem.id)
            .where(Order.restaurant_id == restaurant_id)
            .where(FoodItem.restaurant_id == restaurant_id)
        )

    total = db.scalar(count_stmt) or 0
    items = list(db.scalars(stmt.order_by(OrderItem.id).offset(skip).limit(limit)).all())
    return total, items
