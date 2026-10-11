"""Export hook for a future Snowflake loader.

This module only writes a local Parquet file with a stable column list.
It does not connect to Snowflake.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from mining.sentiment.analyze import OUTPUT_COLUMNS

logger = logging.getLogger(__name__)


def warehouse_frame(scored: pd.DataFrame) -> pd.DataFrame:
    """Return the column set a future Snowflake loader should read."""
    missing = [column for column in OUTPUT_COLUMNS if column not in scored.columns]
    if missing:
        raise ValueError(f"Sentiment export is missing columns: {', '.join(missing)}")
    return scored.loc[:, list(OUTPUT_COLUMNS)].copy()


def export_sentiment(scored: pd.DataFrame, path: Path) -> Path:
    """Write the warehouse-ready sentiment extract to Parquet."""
    frame = warehouse_frame(scored)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    logger.info("Exported %s sentiment rows for a future warehouse load to %s", len(frame), path)
    return path
