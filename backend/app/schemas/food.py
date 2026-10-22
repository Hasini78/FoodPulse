"""Food item schemas."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_serializer


class FoodItemRead(BaseModel):
    """Food item response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    restaurant_id: int
    name: str
    category: str
    description: str | None = None
    price: Decimal
    is_available: bool
    created_at: datetime

    @field_serializer("price")
    def serialize_price(self, value: Decimal) -> float:
        return float(value)


class FoodItemListResponse(BaseModel):
    """Paginated food item list."""

    total: int
    items: list[FoodItemRead]
