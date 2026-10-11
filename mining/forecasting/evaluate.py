"""Chronological holdout metrics for demand forecasts."""

from __future__ import annotations

import math

import pandas as pd

from mining.forecasting.models import future_dates, ridge_forecast, seasonal_naive


def split_holdout(values: list[float], dates: list[pd.Timestamp], horizon: int, min_history: int) -> tuple[list[float], list[pd.Timestamp], list[float], list[pd.Timestamp]] | None:
    """Return train and the last ``horizon`` periods when the train length is enough.

    The test block is always the tail of the series. There is no random split.
    """
    if horizon < 1:
        raise ValueError("horizon must be an integer greater than or equal to 1")
    if min_history < 1:
        raise ValueError("min_history must be an integer greater than or equal to 1")
    if len(values) != len(dates) or len(values) < min_history + horizon:
        return None
    return values[:-horizon], dates[:-horizon], values[-horizon:], dates[-horizon:]


def regression_metrics(actual: list[float], predicted: list[float]) -> dict[str, float | None]:
    """MAE, RMSE, and WAPE. WAPE is null when total actual demand is zero."""
    if len(actual) != len(predicted) or not actual:
        raise ValueError("actual and predicted demand must be non-empty and the same length")
    errors = [abs(float(truth) - float(guess)) for truth, guess in zip(actual, predicted)]
    squared = [(float(truth) - float(guess)) ** 2 for truth, guess in zip(actual, predicted)]
    total = float(sum(actual))
    wape = None if total == 0 else float(sum(errors) / total)
    return {
        "mae": float(sum(errors) / len(errors)),
        "rmse": float(math.sqrt(sum(squared) / len(squared))),
        "wape": wape,
    }


def pooled_metrics(actual: list[float], predicted: list[float]) -> dict[str, float | None]:
    """Metrics over concatenated holdout points. Empty input returns nulls."""
    if not actual:
        return {"mae": None, "rmse": None, "wape": None, "holdout_points": 0, "holdout_actual_total": 0.0}
    metrics = regression_metrics(actual, predicted)
    metrics["holdout_points"] = len(actual)
    metrics["holdout_actual_total"] = float(sum(actual))
    return metrics


def evaluate_series(
    values: list[float],
    dates: list[pd.Timestamp],
    horizon: int,
    aggregation: str,
    min_history: int,
    seed: int,
) -> dict[str, object] | None:
    """Score the baseline and ridge model on a chronological holdout, then forecast forward.

    Holdout predictions are fit only on periods before the holdout. The forward
    forecast is a separate fit on the full history through the reference date.
    Recursive steps append predictions, not holdout or future actuals.
    """
    parts = split_holdout(values, dates, horizon, min_history)
    if parts is None:
        return None
    train_values, train_dates, test_values, test_dates = parts
    baseline_holdout = seasonal_naive(train_values, horizon, aggregation)
    model_holdout, holdout_name = ridge_forecast(train_values, train_dates, horizon, aggregation, seed)
    baseline_forward = seasonal_naive(values, horizon, aggregation)
    model_forward, forward_name = ridge_forecast(values, dates, horizon, aggregation, seed)
    return {
        "holdout_dates": test_dates,
        "holdout_actual": test_values,
        "baseline_holdout": baseline_holdout,
        "model_holdout": model_holdout,
        "holdout_model_name": holdout_name,
        "baseline_metrics": regression_metrics(test_values, baseline_holdout),
        "model_metrics": regression_metrics(test_values, model_holdout),
        "forward_dates": future_dates(dates[-1], horizon, aggregation),
        "baseline_forward": baseline_forward,
        "model_forward": model_forward,
        "forward_model_name": forward_name,
    }
