"""Seasonal-naive baseline and a lag-feature ridge regressor.

Later forecast steps are recursive: each step appends that step's prediction
and never reads the actual demand for a future period.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from mining.forecasting.features import SEASON, feature_vector, next_period

MIN_RIDGE_ROWS = 4


def seasonal_naive(history: list[float], horizon: int, aggregation: str) -> list[float]:
    """Repeat the value from one season earlier, using predictions for later steps.

    Daily season length is 7. Weekly season length is 4. A series shorter than
    one season uses the previous period instead.
    """
    season = SEASON[aggregation]
    extended = [float(value) for value in history]
    forecasts: list[float] = []
    for _ in range(horizon):
        if not extended:
            value = 0.0
        elif len(extended) >= season:
            value = extended[-season]
        else:
            value = extended[-1]
        value = _non_negative(value)
        forecasts.append(value)
        extended.append(value)
    return forecasts


def ridge_forecast(
    history: list[float],
    dates: list[pd.Timestamp],
    horizon: int,
    aggregation: str,
    seed: int,
) -> tuple[list[float], str]:
    """Fit ridge on past rows only, then forecast ``horizon`` steps recursively.

    The returned model name is ``ridge`` when enough past rows exist. Otherwise
    it is ``seasonal_naive`` and the baseline is used for that series.
    """
    if len(history) != len(dates):
        raise ValueError("history and dates must have the same length")
    season = SEASON[aggregation]
    features: list[list[float]] = []
    target: list[float] = []
    for index in range(season, len(history)):
        features.append(feature_vector(history[:index], dates[index], aggregation))
        target.append(float(history[index]))
    if len(features) < MIN_RIDGE_ROWS:
        return seasonal_naive(history, horizon, aggregation), "seasonal_naive"
    scaler = StandardScaler()
    model = Ridge(alpha=1.0, random_state=seed)
    model.fit(scaler.fit_transform(np.asarray(features, dtype=float)), np.asarray(target, dtype=float))
    extended = [float(value) for value in history]
    extended_dates = list(dates)
    forecasts: list[float] = []
    for _ in range(horizon):
        upcoming = next_period(extended_dates[-1], aggregation)
        row = np.asarray(feature_vector(extended, upcoming, aggregation), dtype=float).reshape(1, -1)
        predicted = _non_negative(float(model.predict(scaler.transform(row))[0]))
        forecasts.append(predicted)
        extended.append(predicted)
        extended_dates.append(upcoming)
    return forecasts, "ridge"


def future_dates(last: pd.Timestamp, horizon: int, aggregation: str) -> list[pd.Timestamp]:
    """Period starts after the last observed period."""
    dates: list[pd.Timestamp] = []
    cursor = pd.Timestamp(last)
    for _ in range(horizon):
        cursor = next_period(cursor, aggregation)
        dates.append(cursor)
    return dates


def _non_negative(value: float) -> float:
    if not np.isfinite(value):
        return 0.0
    return float(max(0.0, value))
