"""FoodPulse FastAPI application entrypoint."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import analytics, customers, food_items, health, order_items, restaurants, stats
from app.core.config import get_settings
from app.db.session import Base, engine

# Ensure all models are registered with Base.metadata
import app.models  # noqa: F401

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Create database tables on startup when the DB is reachable."""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database schema ensured")
    except Exception:
        # Allow the API (e.g. /health) to start even if Postgres is down during scaffold
        logger.warning("Could not connect to database on startup; continuing without schema sync")
    yield


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        description="Restaurant Intelligence & Customer Experience Mining Platform",
        version="0.1.0",
        lifespan=lifespan,
    )

    application.include_router(health.router)
    application.include_router(restaurants.router)
    application.include_router(customers.router)
    application.include_router(food_items.router)
    application.include_router(order_items.router)
    application.include_router(stats.router)
    application.include_router(analytics.router)

    return application


app = create_app()
