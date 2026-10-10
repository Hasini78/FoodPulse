"""Statistics endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.stats import OverviewStats
from app.services import stats_service

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/overview", response_model=OverviewStats)
def get_overview(db: Session = Depends(get_db)) -> OverviewStats:
    """Return platform overview statistics."""
    return stats_service.get_overview_stats(db)
