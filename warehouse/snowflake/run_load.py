"""Load approved analytical Parquet files into Snowflake.

From the repository root, validate local files without connecting:

    python -m warehouse.snowflake.run_load
    python -m warehouse.snowflake.run_load --dry-run

A real load is explicit and is the only path that writes to Snowflake:

    python -m warehouse.snowflake.run_load --execute

Check the login without creating objects or loading data:

    python -m warehouse.snowflake.run_load --test-connection

The command does not read or write PostgreSQL and does not modify the Parquet files.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from warehouse.snowflake.catalog import EXCLUDED_FILES
from warehouse.snowflake.config import load_config, redact
from warehouse.snowflake.connection import connect, probe_connection
from warehouse.snowflake.load import build_plan, publish

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED = PROJECT_ROOT / "data" / "processed"


def run_load(processed_dir: Path, tables: list[str] | None, execute: bool) -> list[dict[str, object]]:
    """Validate the plan. Connect only when ``execute`` is true."""
    plans = build_plan(processed_dir, tables)
    report = [{"table": plan.table, "path": str(plan.path), "rows": plan.rows} for plan in plans]
    for item in report:
        logger.info("Planned %s rows=%s path=%s", item["table"], item["rows"], item["path"])
    logger.info("Excluded from the default plan: %s", ", ".join(EXCLUDED_FILES))
    if not execute:
        logger.info("Dry-run only. No Snowflake connection was opened.")
        return report
    load_dotenv(PROJECT_ROOT / ".env")
    try:
        config = load_config()
    except ValueError as exc:
        raise ValueError(redact(str(exc), ())) from None
    publish(config, plans=plans)
    return report


def run_connection_test(connector=None) -> tuple:
    """Load ``.env`` settings, read session context, and print that context."""
    if connector is None:
        connector = connect
    load_dotenv(PROJECT_ROOT / ".env")
    try:
        config = load_config()
    except ValueError as exc:
        raise ValueError(redact(str(exc), ())) from None
    version, warehouse, database, schema = probe_connection(config, connector)
    rendered = redact(
        f"version={version} warehouse={warehouse} database={database} schema={schema}",
        config.secrets(),
    )
    print(rendered)
    return (version, warehouse, database, schema)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. The default is a local dry-run."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(
        description=(
            "Validate or load FoodPulse analytical Parquet files into Snowflake. "
            "The default is a local dry-run and does not open a connection."
        )
    )
    parser.add_argument("--processed-dir", type=Path, default=PROCESSED, help="Directory that contains the approved Parquet files.")
    parser.add_argument("--tables", nargs="*", default=None, help="Optional approved table names. The default is every approved analytical table.")
    parser.add_argument("--dry-run", action="store_true", help="Validate local files and print the plan. This is the default.")
    parser.add_argument("--execute", action="store_true", help="Open Snowflake and publish snapshots. Requires SNOWFLAKE_* settings.")
    parser.add_argument(
        "--test-connection",
        action="store_true",
        help="Connect and read session context only. Does not create objects or load data.",
    )
    args = parser.parse_args(argv)
    if sum((args.dry_run, args.execute, args.test_connection)) > 1:
        logger.error("Choose one of --dry-run, --execute, or --test-connection")
        return 1
    try:
        if args.test_connection:
            run_connection_test()
        else:
            run_load(args.processed_dir, args.tables, execute=args.execute)
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        logger.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
