"""Customer endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.customer import CustomerListResponse, CustomerRead
from app.services import customer_service

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("", response_model=CustomerListResponse)
def get_customers(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> CustomerListResponse:
    """List customers with pagination."""
    total, items = customer_service.list_customers(db, skip=skip, limit=limit)
    return CustomerListResponse(
        total=total,
        items=[CustomerRead.model_validate(item) for item in items],
    )
