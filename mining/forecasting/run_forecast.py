"""Forecast restaurant and food-item demand from completed orders.

From the repository root:

    python -m mining.forecasting.run_forecast --reference-date 2026-10-11 --horizon 7

The command reads processed Parquet files and writes new forecast outputs.
It does not modify the source files or connect to a database.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from etl.transform.feature_engineering import parse_reference_date
from mining.forecasting.evaluate import evaluate_series, pooled_metrics
from mining.forecasting.features import DEFAULT_MIN_HISTORY, HISTORY_COLUMNS, SEASON, aggregate_demand, feature_names
from mining.forecasting.models import MIN_RIDGE_ROWS

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED = PROJECT_ROOT / "data" / "processed"
ARTIFACTS = PROJECT_ROOT / "mining" / "forecasting" / "artifacts"

FORECAST_COLUMNS = [
    "level",
    "restaurant_id",
    "food_item_id",
    "forecast_date",
    "horizon_step",
    "horizon",
    "aggregation",
    "model_name",
    "predicted_demand",
    "forecast_role",
    "evaluation_mae",
    "evaluation_rmse",
    "evaluation_wape",
]


def run_forecast(
    orders_path: Path,
    order_items_path: Path,
    foods_path: Path,
    output_dir: Path,
    artifacts_dir: Path,
    reference_date: str,
    horizon: int,
    aggregation: str,
    model: str,
    seed: int,
    min_history: int | None,
) -> dict[str, object]:
    """Aggregate demand, evaluate a chronological holdout, and write forecasts."""
    _validate(horizon, aggregation, model, seed, min_history)
    for path in (orders_path, order_items_path, foods_path):
        if not path.is_file():
            raise FileNotFoundError(f"Required input file was not found: {path}")
    history_requirement = DEFAULT_MIN_HISTORY[aggregation] if min_history is None else min_history
    parsed = parse_reference_date(reference_date)
    orders = pd.read_parquet(orders_path)
    order_items = pd.read_parquet(order_items_path)
    foods = pd.read_parquet(foods_path)
    payload = forecast_frames(
        orders,
        order_items,
        foods,
        parsed,
        horizon,
        aggregation,
        model,
        seed,
        history_requirement,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    forecast_path = output_dir / "demand_forecasts.parquet"
    history_path = output_dir / "demand_forecast_history.parquet"
    metrics_path = output_dir / "demand_forecast_metrics.json"
    chart_path = artifacts_dir / "demand_forecast_holdout.png"
    payload["forecasts"].to_parquet(forecast_path, index=False)
    payload["history"].to_parquet(history_path, index=False)
    chart_written = _plot(payload["plot_frame"], chart_path)
    document = payload["metrics"]
    document["inputs"] = {
        "orders": str(orders_path),
        "order_items": str(order_items_path),
        "food_items": str(foods_path),
    }
    document["artifacts"] = {
        "forecasts": str(forecast_path),
        "history": str(history_path),
        "metrics": str(metrics_path),
        "chart": str(chart_path) if chart_written else None,
    }
    metrics_path.write_text(json.dumps(_json_ready(document), indent=2), encoding="utf-8")
    logger.info("Wrote demand forecasts to %s", forecast_path)
    return document


def forecast_frames(
    orders: pd.DataFrame,
    order_items: pd.DataFrame,
    foods: pd.DataFrame,
    reference_date,
    horizon: int,
    aggregation: str,
    model: str,
    seed: int,
    min_history: int,
) -> dict[str, object]:
    """Run the forecast from in-memory frames. Short series are skipped."""
    _validate(horizon, aggregation, model, seed, min_history)
    restaurants, items, notes = aggregate_demand(orders, order_items, foods, reference_date, aggregation)
    history = pd.concat([restaurants.loc[:, HISTORY_COLUMNS], items.loc[:, HISTORY_COLUMNS]], ignore_index=True)
    rows: list[dict[str, object]] = []
    pooled: dict[str, dict[str, list[float]]] = {
        "restaurant": {"actual": [], "seasonal_naive": [], "ridge_actual": [], "ridge": []},
        "food_item": {"actual": [], "seasonal_naive": [], "ridge_actual": [], "ridge": []},
    }
    counts = {"restaurant_scored": 0, "restaurant_skipped": 0, "food_item_scored": 0, "food_item_skipped": 0, "ridge_fallback": 0}
    plot_frame = None
    plot_volume = -1.0
    for level, frame, keys in (
        ("restaurant", restaurants, ["restaurant_id"]),
        ("food_item", items, ["restaurant_id", "food_item_id"]),
    ):
        if frame.empty:
            continue
        group_keys = keys
        for key, group in frame.groupby(group_keys, sort=False):
            ordered = group.sort_values("period_start")
            values = [float(value) for value in ordered["actual_demand"]]
            dates = [pd.Timestamp(value) for value in ordered["period_start"]]
            scored = evaluate_series(values, dates, horizon, aggregation, min_history, seed)
            if scored is None:
                counts[f"{level}_skipped"] += 1
                continue
            counts[f"{level}_scored"] += 1
            if scored["holdout_model_name"] != "ridge":
                counts["ridge_fallback"] += 1
            identity = _identity(level, key, keys)
            _append_predictions(rows, identity, aggregation, horizon, "seasonal_naive", "holdout", scored["holdout_dates"], scored["baseline_holdout"], scored["baseline_metrics"])
            _append_predictions(rows, identity, aggregation, horizon, "seasonal_naive", "forward", scored["forward_dates"], scored["baseline_forward"], scored["baseline_metrics"])
            if scored["holdout_model_name"] == "ridge":
                _append_predictions(rows, identity, aggregation, horizon, "ridge", "holdout", scored["holdout_dates"], scored["model_holdout"], scored["model_metrics"])
                _append_predictions(rows, identity, aggregation, horizon, scored["forward_model_name"], "forward", scored["forward_dates"], scored["model_forward"], scored["model_metrics"])
            pooled[level]["actual"].extend(scored["holdout_actual"])
            pooled[level]["seasonal_naive"].extend(scored["baseline_holdout"])
            if scored["holdout_model_name"] == "ridge":
                pooled[level]["ridge_actual"].extend(scored["holdout_actual"])
                pooled[level]["ridge"].extend(scored["model_holdout"])
            volume = float(sum(values))
            if level == "restaurant" and volume > plot_volume:
                plot_volume = volume
                plot_frame = _plot_frame(identity, dates, values, scored, model)
    if counts["restaurant_scored"] + counts["food_item_scored"] == 0:
        raise RuntimeError(
            "No restaurant or food-item series has enough history for this horizon. "
            f"Need at least {min_history + horizon} {aggregation} periods after the first observed order."
        )
    forecasts = pd.DataFrame(rows, columns=FORECAST_COLUMNS)
    if model == "ridge" and counts["ridge_fallback"] == counts["restaurant_scored"] + counts["food_item_scored"]:
        logger.info("Ridge did not have %s training rows on any series, so the seasonal naive forecast was used", MIN_RIDGE_ROWS)
    metrics = _metrics_document(
        reference_date,
        horizon,
        aggregation,
        model,
        seed,
        min_history,
        notes,
        counts,
        pooled,
    )
    return {"forecasts": forecasts, "history": history, "metrics": metrics, "plot_frame": plot_frame}


def _append_predictions(rows, identity, aggregation, horizon, model_name, role, dates, predictions, metrics) -> None:
    for step, (when, predicted) in enumerate(zip(dates, predictions), start=1):
        rows.append(
            {
                **identity,
                "forecast_date": pd.Timestamp(when),
                "horizon_step": step,
                "horizon": horizon,
                "aggregation": aggregation,
                "model_name": model_name,
                "predicted_demand": float(predicted),
                "forecast_role": role,
                "evaluation_mae": metrics["mae"],
                "evaluation_rmse": metrics["rmse"],
                "evaluation_wape": metrics["wape"],
            }
        )


def _identity(level: str, key, names: list[str]) -> dict[str, object]:
    if not isinstance(key, tuple):
        key = (key,)
    values = dict(zip(names, key))
    return {
        "level": level,
        "restaurant_id": values.get("restaurant_id"),
        "food_item_id": values.get("food_item_id", pd.NA),
    }


def _plot_frame(identity, dates, values, scored, selected_model: str) -> pd.DataFrame:
    frame = pd.DataFrame({"period_start": dates, "actual_demand": values, "restaurant_id": identity["restaurant_id"]})
    holdout = pd.DataFrame(
        {
            "period_start": scored["holdout_dates"],
            "baseline": scored["baseline_holdout"],
            "model": scored["model_holdout"],
        }
    )
    frame = frame.merge(holdout, on="period_start", how="left")
    frame["selected_model"] = selected_model
    frame["model_name"] = scored["holdout_model_name"]
    return frame


def _metrics_document(reference_date, horizon, aggregation, model, seed, min_history, notes, counts, pooled) -> dict[str, object]:
    levels = {}
    for level, bucket in pooled.items():
        levels[level] = {
            "series_scored": counts[f"{level}_scored"],
            "series_skipped": counts[f"{level}_skipped"],
            "seasonal_naive": pooled_metrics(bucket["actual"], bucket["seasonal_naive"]),
            "ridge": pooled_metrics(bucket["ridge_actual"], bucket["ridge"]),
        }
    return {
        "reference_date": reference_date.isoformat(),
        "aggregation": aggregation,
        "horizon": horizon,
        "selected_model": model,
        "seed": seed,
        "min_history_periods": min_history,
        "season_length": SEASON[aggregation],
        "minimum_ridge_rows": MIN_RIDGE_ROWS,
        "features": feature_names(aggregation),
        "multi_step": (
            "Each step appends that step's own prediction to the lag history. "
            "Actual demand from the holdout or from after the reference date is not used."
        ),
        "split": "The last horizon periods through the reference date are the holdout. Training uses only earlier periods.",
        "preparation": notes,
        "counts": counts,
        "metrics": levels,
        "comparison": _comparison(levels),
        "metric_definitions": {
            "mae": "Mean absolute error on holdout points. It keeps the demand units and treats every point equally.",
            "rmse": "Root mean squared error. Large misses count more than they do in MAE.",
            "wape": "Sum of absolute errors divided by sum of actual demand. Null when total actual holdout demand is zero, so an all-zero holdout is not reported as infinite error.",
        },
        "limitations": [
            "The score is an error on a chronological holdout of this extract. It is not a measure of revenue, satisfaction, or readiness to staff a restaurant.",
            "Daily restaurant series are sparse, so a small MAE can still be a weak business forecast.",
            "Zero-fill starts at the first completed order, not at a known menu-launch date.",
            "A weekly bucket that contains the reference date can be a partial week when that date is not a Sunday.",
            "Ridge uses four lag and calendar features with a fixed penalty. It is not a causal demand model.",
            "Food-item series that never reach the minimum history are omitted rather than imputed from other items.",
        ],
    }


def _comparison(levels: dict[str, dict[str, object]]) -> dict[str, str]:
    statements = {}
    for level, metrics in levels.items():
        baseline = metrics["seasonal_naive"]["wape"]
        model = metrics["ridge"]["wape"]
        if metrics["series_scored"] == 0:
            statements[level] = "No series had enough history to score."
        elif baseline is None or model is None:
            statements[level] = "WAPE is undefined because holdout actual demand summed to zero, or ridge was not fit on any series."
        elif model < baseline:
            statements[level] = "Pooled holdout WAPE is lower for ridge than for the seasonal-naive baseline."
        elif model > baseline:
            statements[level] = "Pooled holdout WAPE is lower for the seasonal-naive baseline than for ridge."
        else:
            statements[level] = "Pooled holdout WAPE is the same for ridge and the seasonal-naive baseline."
    return statements


def _validate(horizon: int, aggregation: str, model: str, seed: int, min_history: int | None) -> None:
    if horizon < 1:
        raise ValueError("horizon must be an integer greater than or equal to 1")
    if aggregation not in SEASON:
        raise ValueError("aggregation must be 'daily' or 'weekly'")
    if model not in {"ridge", "seasonal_naive"}:
        raise ValueError("model must be 'ridge' or 'seasonal_naive'")
    if seed < 0:
        raise ValueError("seed must be an integer greater than or equal to 0")
    if min_history is not None and min_history < 1:
        raise ValueError("min_history must be an integer greater than or equal to 1")


def _plot(frame: pd.DataFrame | None, path: Path) -> bool:
    if frame is None or frame.empty:
        logger.info("No restaurant series was available for the holdout chart")
        return False
    figure, axis = plt.subplots(figsize=(9, 4))
    axis.plot(frame["period_start"], frame["actual_demand"], label="Actual")
    holdout = frame.loc[frame["baseline"].notna()]
    axis.plot(holdout["period_start"], holdout["baseline"], label="Seasonal naive")
    axis.plot(holdout["period_start"], holdout["model"], label=f"Model ({frame['model_name'].iloc[0]})")
    restaurant_id = frame["restaurant_id"].iloc[0]
    axis.set_title(f"Restaurant {restaurant_id}: history and chronological holdout")
    axis.set_xlabel("Period start")
    axis.set_ylabel("Completed orders")
    axis.legend()
    figure.tight_layout()
    figure.savefig(path)
    plt.close(figure)
    logger.info("Wrote holdout chart to %s", path)
    return True


def _json_ready(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, float):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return int(value)
    if value is None or isinstance(value, str):
        return value
    return str(value)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Forecast completed-order demand by restaurant and food item. The result is a holdout error, not a staffing plan.")
    parser.add_argument("--orders", type=Path, default=PROCESSED / "orders.parquet")
    parser.add_argument("--order-items", type=Path, default=PROCESSED / "order_items.parquet")
    parser.add_argument("--food-items", type=Path, default=PROCESSED / "food_items.parquet")
    parser.add_argument("--output-dir", type=Path, default=PROCESSED)
    parser.add_argument("--artifacts-dir", type=Path, default=ARTIFACTS)
    parser.add_argument("--reference-date", default="2026-10-11", help="UTC calendar date. Orders after this date are ignored.")
    parser.add_argument("--horizon", type=int, default=7, help="Periods to hold out and to forecast after the reference date.")
    parser.add_argument("--aggregation", default="daily", help="daily or weekly.")
    parser.add_argument("--model", default="ridge", help="ridge or seasonal_naive. The seasonal-naive baseline is always scored.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--min-history", type=int, default=None, help="Minimum train periods before the holdout. Default is 28 daily periods or 8 weekly periods.")
    args = parser.parse_args(argv)
    try:
        run_forecast(
            args.orders,
            args.order_items,
            args.food_items,
            args.output_dir,
            args.artifacts_dir,
            args.reference_date,
            args.horizon,
            args.aggregation,
            args.model,
            args.seed,
            args.min_history,
        )
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        logger.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
