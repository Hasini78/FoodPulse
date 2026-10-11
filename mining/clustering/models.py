"""Cluster comparison for customer segmentation.

K-Means is the primary algorithm. Agglomerative clustering is fit at the same
K values for comparison. DBSCAN is attempted once and kept only when it finds
at least two non-noise clusters.

The selected model is the eligible result with the highest silhouette score.
A silhouette within 0.01 of the leader prefers K-Means, then agglomerative
clustering, then fewer clusters. The winner is not chosen by having more
clusters.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.cluster import AgglomerativeClustering, DBSCAN, KMeans
from sklearn.metrics import calinski_harabasz_score, davies_bouldin_score, silhouette_score
from sklearn.neighbors import NearestNeighbors

logger = logging.getLogger(__name__)

ALGORITHM_PRIORITY = ("kmeans", "agglomerative", "dbscan")


@dataclass(frozen=True)
class ClusterRun:
    """One fitted clustering result."""

    algorithm: str
    params: dict[str, object]
    labels: np.ndarray
    metrics: dict[str, float | None]
    eligible: bool
    note: str


def evaluate_clusterings(matrix: pd.DataFrame, seed: int) -> tuple[ClusterRun, list[ClusterRun]]:
    """Fit the candidate models and return the selected run plus every run."""
    values = np.asarray(matrix, dtype=float)
    row_count = len(values)
    if row_count < 3:
        degenerate = ClusterRun(
            algorithm="none",
            params={},
            labels=np.zeros(row_count, dtype=int),
            metrics={"silhouette": None, "davies_bouldin": None, "calinski_harabasz": None},
            eligible=False,
            note="Fewer than 3 customers. Clustering metrics are undefined.",
        )
        return degenerate, [degenerate]

    runs: list[ClusterRun] = []
    upper_k = min(8, row_count - 1)
    for k in range(2, upper_k + 1):
        runs.append(_kmeans(values, k, seed))
        runs.append(_agglomerative(values, k))
    runs.append(_dbscan(values))
    selected = _select(runs)
    logger.info(
        "Selected %s silhouette=%s params=%s",
        selected.algorithm,
        selected.metrics.get("silhouette"),
        selected.params,
    )
    return selected, runs


def _kmeans(values: np.ndarray, k: int, seed: int) -> ClusterRun:
    model = KMeans(n_clusters=k, random_state=seed, n_init=10)
    labels = model.fit_predict(values)
    return _run("kmeans", {"n_clusters": k, "random_state": seed, "n_init": 10}, labels, values)


def _agglomerative(values: np.ndarray, k: int) -> ClusterRun:
    model = AgglomerativeClustering(n_clusters=k, linkage="ward")
    labels = model.fit_predict(values)
    return _run("agglomerative", {"n_clusters": k, "linkage": "ward"}, labels, values)


def _dbscan(values: np.ndarray) -> ClusterRun:
    if len(values) < 5:
        return ClusterRun(
            algorithm="dbscan",
            params={},
            labels=np.full(len(values), -1),
            metrics={"silhouette": None, "davies_bouldin": None, "calinski_harabasz": None},
            eligible=False,
            note="DBSCAN skipped because fewer than 5 customers are available.",
        )
    neighbors = min(5, len(values) - 1)
    distances, _ = NearestNeighbors(n_neighbors=neighbors).fit(values).kneighbors(values)
    eps = float(np.median(distances[:, -1]))
    if eps <= 0:
        eps = float(np.max(distances[:, -1])) or 0.5
    min_samples = max(3, min(5, len(values) // 10))
    labels = DBSCAN(eps=eps, min_samples=min_samples).fit_predict(values)
    run = _run("dbscan", {"eps": eps, "min_samples": min_samples}, labels, values, noise_label=-1)
    noise_fraction = float(np.mean(labels == -1))
    if noise_fraction >= 0.5:
        return ClusterRun(
            algorithm=run.algorithm,
            params=run.params,
            labels=run.labels,
            metrics=run.metrics,
            eligible=False,
            note=f"DBSCAN noise fraction {noise_fraction:.2f} is at least 0.50.",
        )
    return run


def _run(
    algorithm: str,
    params: dict[str, object],
    labels: np.ndarray,
    values: np.ndarray,
    noise_label: int | None = None,
) -> ClusterRun:
    working = labels
    sample = values
    if noise_label is not None:
        mask = labels != noise_label
        working = labels[mask]
        sample = values[mask]
    cluster_count = len(set(working.tolist()))
    if cluster_count < 2 or len(sample) <= cluster_count:
        return ClusterRun(
            algorithm=algorithm,
            params=params,
            labels=labels,
            metrics={"silhouette": None, "davies_bouldin": None, "calinski_harabasz": None},
            eligible=False,
            note="Fewer than two usable clusters.",
        )
    metrics = {
        "silhouette": _metric(silhouette_score, sample, working),
        "davies_bouldin": _metric(davies_bouldin_score, sample, working),
        "calinski_harabasz": _metric(calinski_harabasz_score, sample, working),
    }
    eligible = metrics["silhouette"] is not None
    return ClusterRun(algorithm, params, labels, metrics, eligible, "ok" if eligible else "metrics unavailable")


def _metric(function, values: np.ndarray, labels: np.ndarray) -> float | None:
    try:
        return float(function(values, labels))
    except ValueError:
        return None


def _select(runs: list[ClusterRun]) -> ClusterRun:
    eligible = [run for run in runs if run.eligible and run.metrics.get("silhouette") is not None]
    if not eligible:
        fallback = next(run for run in runs if run.algorithm == "kmeans")
        return ClusterRun(
            algorithm=fallback.algorithm,
            params=fallback.params,
            labels=fallback.labels,
            metrics=fallback.metrics,
            eligible=False,
            note="No clustering result produced a silhouette score.",
        )
    best = max(run.metrics["silhouette"] for run in eligible)

    def sort_key(run: ClusterRun) -> tuple:
        near_best = 0 if best - float(run.metrics["silhouette"]) <= 0.01 else 1
        priority = ALGORITHM_PRIORITY.index(run.algorithm)
        cluster_count = len(set(int(label) for label in run.labels if int(label) != -1))
        return (near_best, -float(run.metrics["silhouette"]), priority, cluster_count)

    return sorted(eligible, key=sort_key)[0]
