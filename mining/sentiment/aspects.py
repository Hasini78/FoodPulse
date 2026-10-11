"""Aspect sentiment from a keyword lexicon and clause splits.

Unmentioned aspects are ``not mentioned``. ``neutral`` is used only when the
aspect is mentioned and the clause has no positive or negative lean.

VADER scores "slow" as neutral, so aspect polarity uses this lexicon. Overall
review sentiment stays on the VADER baseline.
"""

from __future__ import annotations

import logging

from mining.sentiment.preprocess import (
    NEGATION_WORDS,
    PreparedText,
    prepare_text,
    split_clauses,
)

logger = logging.getLogger(__name__)

NOT_MENTIONED = "not mentioned"
ASPECTS = ("food", "service", "ambience", "price")

ASPECT_KEYWORDS: dict[str, frozenset[str]] = {
    "food": frozenset(
        {
            "food",
            "dish",
            "meal",
            "menu",
            "flavor",
            "flavour",
            "taste",
            "aroma",
            "texture",
            "ingredient",
            "biryani",
            "naan",
            "dosa",
            "samosa",
            "chicken",
            "shawarma",
            "pizza",
            "pasta",
            "ramen",
            "sushi",
            "taco",
            "burrito",
            "soup",
            "salad",
            "dessert",
            "roll",
            "noodle",
            "rice",
            "burger",
            "fries",
            "curry",
            "pho",
        }
    ),
    "service": frozenset(
        {
            "service",
            "server",
            "staff",
            "waiter",
            "waitress",
            "hospitality",
            "seating",
            "host",
        }
    ),
    "ambience": frozenset(
        {
            "ambience",
            "ambiance",
            "atmosphere",
            "decor",
            "décor",
            "music",
            "lighting",
            "noisy",
            "vibe",
            "interior",
        }
    ),
    "price": frozenset(
        {
            "price",
            "pricing",
            "value",
            "expensive",
            "cheap",
            "overpriced",
            "affordable",
            "cost",
            "rupee",
            "deal",
            "portion",
        }
    ),
}

ASPECT_PHRASES: dict[str, tuple[str, ...]] = {
    "food": (
        "dim sum",
        "spring roll",
        "fried rice",
        "miso soup",
        "ice cream",
        "fried chicken",
        "butter chicken",
    ),
    "service": ("wait staff",),
    "ambience": (),
    "price": ("value for money", "lunch deal"),
}

POSITIVE_WORDS = frozenset(
    {
        "amazing",
        "delicious",
        "excellent",
        "great",
        "good",
        "love",
        "loved",
        "fresh",
        "outstanding",
        "best",
        "perfect",
        "perfectly",
        "rich",
        "courteous",
        "friendly",
        "reasonable",
        "fair",
        "generous",
        "worth",
        "quick",
        "attentive",
        "professional",
        "smooth",
        "tasty",
        "flavorful",
        "recommend",
        "happy",
        "nice",
        "pleasant",
        "cozy",
    }
)
NEGATIVE_WORDS = frozenset(
    {
        "slow",
        "rude",
        "cold",
        "bland",
        "oily",
        "overcooked",
        "disappointed",
        "disappointing",
        "terrible",
        "awful",
        "bad",
        "expensive",
        "overpriced",
        "inattentive",
        "rushed",
        "tiny",
        "delayed",
        "poor",
        "worst",
        "soggy",
        "stale",
        "wait",
        "waited",
    }
)


def aspect_sentiments(value: object) -> dict[str, str]:
    """Return a label for each aspect. Missing text leaves every aspect unmentioned."""
    prepared = prepare_text(value)
    if not prepared.text:
        return {aspect: NOT_MENTIONED for aspect in ASPECTS}
    clauses = split_clauses(prepared.text) or (prepared.text,)
    labels: dict[str, str] = {}
    for aspect in ASPECTS:
        scores = [
            _clause_polarity(prepare_text(clause))
            for clause in clauses
            if _mentions(aspect, prepare_text(clause))
        ]
        if not scores:
            labels[aspect] = NOT_MENTIONED
        else:
            total = sum(scores)
            if total > 0:
                labels[aspect] = "positive"
            elif total < 0:
                labels[aspect] = "negative"
            else:
                labels[aspect] = "neutral"
    return labels


def _mentions(aspect: str, prepared: PreparedText) -> bool:
    if any(phrase in prepared.text for phrase in ASPECT_PHRASES[aspect]):
        return True
    keywords = ASPECT_KEYWORDS[aspect]
    return any(lemma in keywords or token in keywords for token, lemma in zip(prepared.tokens, prepared.lemmas, strict=True))


def _clause_polarity(prepared: PreparedText) -> int:
    """Return +1, -1, or 0 for one clause that already mentions an aspect."""
    score = 0
    found = False
    for index, lemma in enumerate(prepared.lemmas):
        polarity = _word_polarity(lemma)
        if polarity == 0:
            continue
        found = True
        if _negated(prepared.lemmas, index):
            polarity *= -1
        score += polarity
    if not found:
        return 0
    if score > 0:
        return 1
    if score < 0:
        return -1
    return 0


def _word_polarity(lemma: str) -> int:
    if lemma in POSITIVE_WORDS:
        return 1
    if lemma in NEGATIVE_WORDS:
        return -1
    return 0


def _negated(lemmas: tuple[str, ...], index: int) -> bool:
    window = lemmas[max(0, index - 3) : index]
    return any(token in NEGATION_WORDS or token.endswith("n't") for token in window)
