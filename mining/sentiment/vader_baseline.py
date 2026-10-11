"""VADER overall sentiment.

Compound score thresholds from the VADER authors:

- ``compound >= 0.05`` positive
- ``compound <= -0.05`` negative
- otherwise neutral

Empty or non-text input is ``invalid`` and has no score. It is not labeled
neutral.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from mining.sentiment.preprocess import clean_text

logger = logging.getLogger(__name__)

POSITIVE_THRESHOLD = 0.05
NEGATIVE_THRESHOLD = -0.05
_ANALYZER = None


@dataclass(frozen=True)
class SentimentScore:
    """One overall sentiment decision."""

    label: str
    compound: float | None


def score_text(value: object) -> SentimentScore:
    """Return the VADER label and compound score for one text value."""
    text = clean_text(value)
    if not text:
        logger.debug("Skipping empty review text")
        return SentimentScore(label="invalid", compound=None)
    compound = float(analyzer().polarity_scores(text)["compound"])
    return SentimentScore(label=label_from_compound(compound), compound=compound)


def label_from_compound(compound: float) -> str:
    """Map a VADER compound score to positive, negative, or neutral."""
    if compound >= POSITIVE_THRESHOLD:
        return "positive"
    if compound <= NEGATIVE_THRESHOLD:
        return "negative"
    return "neutral"


def analyzer():
    """Return a cached VADER analyzer."""
    global _ANALYZER
    if _ANALYZER is None:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

        _ANALYZER = SentimentIntensityAnalyzer()
        logger.info("Loaded VADER sentiment analyzer")
    return _ANALYZER
