"""Optional upsert of sentiment rows by review id.

The caller supplies the engine. This function creates ``review_sentiment``
when it is missing and updates existing review ids in place. It does not drop
or truncate any table.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import Engine
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from mining.sentiment.analyze import OUTPUT_COLUMNS

logger = logging.getLogger(__name__)


def upsert_review_sentiment(scored: pd.DataFrame, engine: Engine) -> int:
    """Insert or update one row per ``review_id``. Return the number of rows written."""
    backend_dir = Path(__file__).resolve().parents[2] / "backend"
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))
    from app.models.review_sentiment import ReviewSentiment

    missing = [column for column in OUTPUT_COLUMNS if column not in scored.columns]
    if missing:
        raise ValueError(f"Cannot persist sentiment without columns: {', '.join(missing)}")
    ReviewSentiment.__table__.create(bind=engine, checkfirst=True)
    rows = [_row(record) for record in scored.loc[:, list(OUTPUT_COLUMNS)].to_dict(orient="records")]
    if not rows:
        return 0
    insert = postgres_insert if engine.dialect.name == "postgresql" else sqlite_insert
    statement = insert(ReviewSentiment).values(rows)
    update_columns = [column for column in OUTPUT_COLUMNS if column != "review_id"]
    statement = statement.on_conflict_do_update(
        index_elements=["review_id"],
        set_={column: statement.excluded[column] for column in update_columns},
    )
    with engine.begin() as connection:
        connection.execute(statement)
    logger.info("Upserted %s review sentiment rows", len(rows))
    return len(rows)


def _row(record: dict[str, object]) -> dict[str, object]:
    analyzed_at = record["analyzed_at"]
    if isinstance(analyzed_at, str):
        analyzed_at = datetime.fromisoformat(analyzed_at)
    return {
        "review_id": int(record["review_id"]),
        "overall_sentiment": record["overall_sentiment"],
        "overall_score": None if pd.isna(record["overall_score"]) else float(record["overall_score"]),
        "food_sent": record["food_sent"],
        "service_sent": record["service_sent"],
        "ambience_sent": record["ambience_sent"],
        "price_sent": record["price_sent"],
        "analyzed_at": analyzed_at,
    }
