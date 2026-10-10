"""Restaurant schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class LocationBrief(BaseModel):
    """Nested location summary."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    city: str
    state: str
    country: str


class RestaurantRead(BaseModel):
    """Restaurant response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    cuisine_type: str
    description: str | None = None
    phone: str | None = None
    email: str | None = None
    location_id: int
    is_active: bool
    created_at: datetime
    location: LocationBrief | None = None


class RestaurantListResponse(BaseModel):
    """Paginated restaurant list."""

    total: int
    items: list[RestaurantRead]
