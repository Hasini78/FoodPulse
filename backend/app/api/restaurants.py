"""Restaurant endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.restaurant import RestaurantListResponse, RestaurantRead
from app.services import restaurant_service

router = APIRouter(prefix="/restaurants", tags=["restaurants"])


@router.get("", response_model=RestaurantListResponse)
def get_restaurants(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> RestaurantListResponse:
    """List restaurants with pagination."""
    total, items = restaurant_service.list_restaurants(db, skip=skip, limit=limit)
    return RestaurantListResponse(
        total=total,
        items=[RestaurantRead.model_validate(item) for item in items],
    )


@router.get("/{restaurant_id}", response_model=RestaurantRead)
def get_restaurant(
    restaurant_id: int,
    db: Session = Depends(get_db),
) -> RestaurantRead:
    """Get a restaurant by id."""
    restaurant = restaurant_service.get_restaurant(db, restaurant_id)
    if restaurant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Restaurant {restaurant_id} not found",
        )
    return RestaurantRead.model_validate(restaurant)
