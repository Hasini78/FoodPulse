"""Health check schema."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """API health status."""

    status: str
    app_name: str
    environment: str
