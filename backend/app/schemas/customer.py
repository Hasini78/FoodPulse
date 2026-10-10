"""Customer schemas."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class CustomerRead(BaseModel):
    """Customer response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    first_name: str
    last_name: str
    email: EmailStr
    phone: str | None = None
    city: str | None = None
    date_of_birth: date | None = None
    gender: str | None = None
    created_at: datetime


class CustomerListResponse(BaseModel):
    """Paginated customer list."""

    total: int
    items: list[CustomerRead]
