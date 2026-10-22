"""Food item endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.food import FoodItemListResponse, FoodItemRead
from app.services import food_service

router = APIRouter(prefix="/food-items", tags=["food-items"])


@router.get("", response_model=FoodItemListResponse)
def get_food_items(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    restaurant_id: int | None = Query(None, ge=1),
    category: str | None = Query(None, min_length=1, max_length=100),
    db: Session = Depends(get_db),
) -> FoodItemListResponse:
    """List food items with pagination and optional restaurant/category filters."""
    total, items = food_service.list_food_items(
        db,
        skip=skip,
        limit=limit,
        restaurant_id=restaurant_id,
        category=category,
    )
    return FoodItemListResponse(
        total=total,
        items=[FoodItemRead.model_validate(item) for item in items],
    )


@router.get("/{food_item_id}", response_model=FoodItemRead)
def get_food_item(
    food_item_id: int,
    db: Session = Depends(get_db),
) -> FoodItemRead:
    """Get a food item by id."""
    food_item = food_service.get_food_item(db, food_item_id)
    if food_item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Food item {food_item_id} not found",
        )
    return FoodItemRead.model_validate(food_item)
