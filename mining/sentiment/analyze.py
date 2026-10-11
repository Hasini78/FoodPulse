"""Build one sentiment row per review."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

from mining.sentiment.aspects import aspect_sentiments
from mining.sentiment.transformer_backend import score_texts, transformer_selected
from mining.sentiment.vader_baseline import score_text

logger = logging.getLogger(__name__)

OUTPUT_COLUMNS = (
    "review_id",
    "overall_sentiment",
    "overall_score",
    "food_sent",
    "service_sent",
    "ambience_sent",
    "price_sent",
    "analyzed_at",
)


def analyze_reviews(
    reviews: pd.DataFrame,
    *,
    analyzed_at: datetime | None = None,
) -> pd.DataFrame:
    """Score every review and keep the original ``id`` as ``review_id``.

    The frame is deduped on ``id`` so a review is not emitted twice. Rows are
    not dropped for empty text.
    """
    if "id" not in reviews.columns or "review_text" not in reviews.columns:
        raise ValueError("reviews must include id and review_text columns")
    stamp = analyzed_at or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    source = reviews.drop_duplicates(subset=["id"], keep="first")
    texts = source["review_text"].tolist()
    if transformer_selected():
        overall = score_texts(texts)
        logger.info("Scored %s reviews with the transformer backend", len(texts))
    else:
        overall = [score_text(text) for text in texts]
        logger.info("Scored %s reviews with VADER", len(texts))
    rows: list[dict[str, object]] = []
    for review_id, score, text in zip(source["id"].tolist(), overall, texts, strict=True):
        aspects = aspect_sentiments(text)
        rows.append(
            {
                "review_id": int(review_id),
                "overall_sentiment": score.label,
                "overall_score": score.compound,
                "food_sent": aspects["food"],
                "service_sent": aspects["service"],
                "ambience_sent": aspects["ambience"],
                "price_sent": aspects["price"],
                "analyzed_at": stamp,
            }
        )
    result = pd.DataFrame(rows, columns=list(OUTPUT_COLUMNS))
    missing = set(source["id"].astype(int)) - set(result["review_id"])
    if missing:
        raise RuntimeError(f"Sentiment output missed review ids: {sorted(missing)[:10]}")
    logger.info("Analyzed %s reviews", len(result))
    return result
