"""Order item schemas."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_serializer


class OrderItemRead(BaseModel):
    """Order line response schema. Customer identity is not included."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    food_item_id: int
    quantity: int
    unit_price: Decimal
    subtotal: Decimal

    @field_serializer("unit_price", "subtotal")
    def serialize_money(self, value: Decimal) -> float:
        return float(value)


class OrderItemListResponse(BaseModel):
    """Paginated order item list."""

    total: int
    items: list[OrderItemRead]
