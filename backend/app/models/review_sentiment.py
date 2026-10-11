"""Review-level sentiment scores.

This table is additive. It does not change ``reviews`` or any other existing
table. Rows are upserted by ``review_id``.
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ReviewSentiment(Base):
    """Overall and aspect sentiment for one review."""

    __tablename__ = "review_sentiment"

    review_id: Mapped[int] = mapped_column(
        ForeignKey("reviews.id", ondelete="CASCADE"),
        primary_key=True,
    )
    overall_sentiment: Mapped[str] = mapped_column(String(32), nullable=False)
    overall_score: Mapped[float | None] = mapped_column(Float)
    food_sent: Mapped[str | None] = mapped_column(String(32))
    service_sent: Mapped[str | None] = mapped_column(String(32))
    ambience_sent: Mapped[str | None] = mapped_column(String(32))
    price_sent: Mapped[str | None] = mapped_column(String(32))
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
