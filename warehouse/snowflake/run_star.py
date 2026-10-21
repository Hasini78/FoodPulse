"""Build the FoodPulse star schema from processed Parquet.

From the repository root, validate the transform without connecting:

    python -m warehouse.snowflake.run_star
    python -m warehouse.snowflake.run_star --dry-run

A real load is explicit and is the only path that writes to Snowflake:

    python -m warehouse.snowflake.run_star --execute

This command does not read or write PostgreSQL and does not modify Parquet files.
Snapshot mining tables stay on ``python -m warehouse.snowflake.run_load``.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from warehouse.snowflake.config import load_config, redact
from warehouse.snowflake.star import build_star_plan, publish_star, report, validate_star
from warehouse.snowflake.star_catalog import DROPPED_TABLES

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED = PROJECT_ROOT / "data" / "processed"


def run_star(processed_dir: Path, execute: bool) -> list[dict[str, object]]:
    """Validate the star model. Connect only when ``execute`` is true."""
    plans, built = build_star_plan(processed_dir)
    problems = validate_star(built.frames)
    if problems:
        raise ValueError("; ".join(problems))
    payload = report(built, plans)
    for item in payload:
        logger.info("Planned %s rows=%s skipped=%s grain=%s", item["table"], item["rows"], item["skipped"], item["grain"])
    for name, reason in DROPPED_TABLES:
        logger.info("Dropped %s: %s", name, reason)
    if not execute:
        logger.info("Dry-run only. No Snowflake connection was opened.")
        return payload
    load_dotenv(PROJECT_ROOT / ".env")
    try:
        config = load_config()
    except ValueError as exc:
        raise ValueError(redact(str(exc), ())) from None
    publish_star(config, processed_dir)
    return payload


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. The default is a local dry-run."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(
        description=(
            "Validate or load the FoodPulse star schema from processed Parquet. "
            "The default is a local dry-run and does not open a connection."
        )
    )
    parser.add_argument("--processed-dir", type=Path, default=PROCESSED, help="Directory that contains source Parquet files.")
    parser.add_argument("--dry-run", action="store_true", help="Validate local files and print the plan. This is the default.")
    parser.add_argument("--execute", action="store_true", help="Open Snowflake and publish star tables. Requires SNOWFLAKE_* settings.")
    args = parser.parse_args(argv)
    if args.dry_run and args.execute:
        logger.error("Choose one of --dry-run or --execute")
        return 1
    try:
        run_star(args.processed_dir, execute=args.execute)
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        logger.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
