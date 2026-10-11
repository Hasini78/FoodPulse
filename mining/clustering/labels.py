"""Descriptive names for customer clusters.

Labels compare each cluster's medians with the full customer population.
They describe the measured pattern. They are not a validated business taxonomy
and they do not use the raw cluster id as the name.
"""

from __future__ import annotations

import pandas as pd

LABEL_RULES = (
    "high-value loyal: spend and frequency are both at or above the population median, and recency is not in the least-recent quartile.",
    "high-value at-risk: spend and frequency are both at or above the population median, and recency is in the least-recent quartile.",
    "frequent moderate-spend: frequency is at or above the population median and spend is below it.",
    "inactive/at-risk: recency is in the least-recent quartile and frequency is below the population median.",
    "new/promising: recency is at or below the population median and frequency is in the lowest quartile.",
    "low-frequency: frequency and spend are both below the population median.",
    "mixed behavior: none of the rules above dominate.",
)


def label_segments(frame: pd.DataFrame, labels: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return customer assignments and a per-cluster summary."""
    assigned = frame.copy()
    assigned["cluster_id"] = labels.to_numpy()
    clustered = assigned.loc[assigned["cluster_id"] != -1]
    population = _population_thresholds(clustered if len(clustered) else assigned)
    names = _names(assigned.loc[assigned["cluster_id"] != -1], population) if (assigned["cluster_id"] != -1).any() else {}
    assigned["segment_label"] = assigned["cluster_id"].map(names)
    assigned.loc[assigned["cluster_id"] == -1, "segment_label"] = "unclustered"
    summary = _summary(assigned, names)
    return assigned, summary


def _population_thresholds(frame: pd.DataFrame) -> dict[str, float]:
    return {
        "recency_median": float(frame["recency_days"].median()),
        "recency_high": float(frame["recency_days"].quantile(0.75)),
        "frequency_median": float(frame["order_frequency"].median()),
        "frequency_low": float(frame["order_frequency"].quantile(0.25)),
        "spend_median": float(frame["total_spend"].median()),
    }


def _names(frame: pd.DataFrame, population: dict[str, float]) -> dict[int, str]:
    proposed: dict[int, str] = {}
    medians: dict[int, pd.Series] = {}
    for cluster_id, group in frame.groupby("cluster_id"):
        median = group.median(numeric_only=True)
        medians[int(cluster_id)] = median
        proposed[int(cluster_id)] = _one_label(median, population)
    by_label: dict[str, list[int]] = {}
    for cluster_id, label in proposed.items():
        by_label.setdefault(label, []).append(cluster_id)
    resolved: dict[int, str] = {}
    for label, cluster_ids in by_label.items():
        ordered = sorted(cluster_ids, key=lambda item: float(medians[item]["total_spend"]))
        if len(ordered) == 1:
            resolved[ordered[0]] = label
            continue
        for index, cluster_id in enumerate(ordered, start=1):
            resolved[cluster_id] = f"{label} ({index} of {len(ordered)} by spend)"
    return resolved


def _one_label(median: pd.Series, population: dict[str, float]) -> str:
    recency = float(median["recency_days"])
    frequency = float(median["order_frequency"])
    spend = float(median["total_spend"])
    if spend >= population["spend_median"] and frequency >= population["frequency_median"]:
        if recency >= population["recency_high"]:
            return "high-value at-risk"
        return "high-value loyal"
    if frequency >= population["frequency_median"] and spend < population["spend_median"]:
        return "frequent moderate-spend"
    if recency >= population["recency_high"] and frequency < population["frequency_median"]:
        return "inactive/at-risk"
    if recency <= population["recency_median"] and frequency <= population["frequency_low"]:
        return "new/promising"
    if frequency < population["frequency_median"] and spend < population["spend_median"]:
        return "low-frequency"
    return "mixed behavior"


def _summary(frame: pd.DataFrame, names: dict[int, str]) -> pd.DataFrame:
    total = len(frame)
    rows: list[dict[str, object]] = []
    for cluster_id, group in frame.groupby("cluster_id"):
        rows.append(
            {
                "cluster_id": int(cluster_id),
                "segment_label": "unclustered" if int(cluster_id) == -1 else names[int(cluster_id)],
                "count": int(len(group)),
                "percent": float(len(group) / total) if total else 0.0,
                "mean_recency_days": float(group["recency_days"].mean()),
                "median_recency_days": float(group["recency_days"].median()),
                "mean_order_frequency": float(group["order_frequency"].mean()),
                "median_order_frequency": float(group["order_frequency"].median()),
                "mean_total_spend": float(group["total_spend"].mean()),
                "median_total_spend": float(group["total_spend"].median()),
                "mean_avg_order_value": float(group["avg_order_value"].mean()),
                "median_avg_order_value": float(group["avg_order_value"].median()),
                "mean_avg_discount": float(group["avg_discount"].mean()),
                "median_avg_discount": float(group["avg_discount"].median()),
                "mean_avg_rating": float(group["avg_rating"].mean()),
                "median_avg_rating": float(group["avg_rating"].median()),
                "mean_avg_sentiment_score": float(group["avg_sentiment_score"].mean()),
                "median_avg_sentiment_score": float(group["avg_sentiment_score"].median()),
            }
        )
    return pd.DataFrame(rows).sort_values("cluster_id").reset_index(drop=True)
