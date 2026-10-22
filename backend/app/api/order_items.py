"""Order item endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.order_item import OrderItemListResponse, OrderItemRead
from app.services import order_item_service

router = APIRouter(prefix="/order-items", tags=["order-items"])


@router.get("", response_model=OrderItemListResponse)
def get_order_items(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    order_id: int | None = Query(None, ge=1),
    food_item_id: int | None = Query(None, ge=1),
    restaurant_id: int | None = Query(None, ge=1),
    db: Session = Depends(get_db),
) -> OrderItemListResponse:
    """List order lines with pagination and optional order, food, or restaurant filters."""
    total, items = order_item_service.list_order_items(
        db,
        skip=skip,
        limit=limit,
        order_id=order_id,
        food_item_id=food_item_id,
        restaurant_id=restaurant_id,
    )
    return OrderItemListResponse(
        total=total,
        items=[OrderItemRead.model_validate(item) for item in items],
    )
