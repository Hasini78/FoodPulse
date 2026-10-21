"""Load processed operational Parquet into PostgreSQL.

From the repository root, validate files without writing:

    python -m etl.pipelines.run_postgres_load
    python -m etl.pipelines.run_postgres_load --dry-run

A real load is explicit and is the only path that writes:

    python -m etl.pipelines.run_postgres_load --execute

The command does not drop tables, does not delete rows, and does not modify Parquet.
It refuses hosts and database names that are not the local FoodPulse database.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from etl.load.postgres import apply_plan, build_plan, report, verify_target

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED = PROJECT_ROOT / "data" / "processed"
BACKEND = PROJECT_ROOT / "backend"


def run_load(processed_dir: Path, execute: bool, session_factory=None) -> list[dict[str, object]]:
    """Validate the plan. Connect only when ``execute`` is true."""
    plan = build_plan(processed_dir)
    payload = report(plan["summaries"], dry_run=not execute)
    for item in payload:
        logger.info(
            "Planned %s prepared=%s skipped=%s rejected=%s",
            item["table"],
            item["prepared"],
            item["skipped"],
            item["rejected"],
        )
    if not execute:
        logger.info("Dry-run only. No PostgreSQL writes were attempted.")
        return payload
    session = session_factory() if session_factory is not None else _open_session()
    try:
        summaries = apply_plan(session, plan, _models())
    finally:
        if session_factory is None:
            session.close()
    payload = report(summaries, dry_run=False)
    for item in payload:
        logger.info(
            "Loaded %s inserted=%s updated=%s skipped=%s rejected=%s",
            item["table"],
            item["inserted"],
            item["updated"],
            item["skipped"],
            item["rejected"],
        )
    return payload


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. The default is a local dry-run."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(
        description=(
            "Validate or load FoodPulse operational Parquet files into PostgreSQL. "
            "The default is a local dry-run and does not write to the database."
        )
    )
    parser.add_argument("--processed-dir", type=Path, default=PROCESSED)
    parser.add_argument("--dry-run", action="store_true", help="Validate local files. This is the default.")
    parser.add_argument("--execute", action="store_true", help="Write to the local FoodPulse PostgreSQL database.")
    args = parser.parse_args(argv)
    if args.dry_run and args.execute:
        logger.error("Choose one of --dry-run or --execute")
        return 1
    try:
        run_load(args.processed_dir, execute=args.execute)
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        logger.error("%s", exc)
        return 1
    return 0


def _open_session():
    load_dotenv(PROJECT_ROOT / ".env")
    url = (os.getenv("DATABASE_URL") or "").strip()
    if not url:
        raise ValueError("DATABASE_URL is not set")
    verify_target(url)
    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as connection:
        current = connection.execute(text("SELECT current_database()")).scalar()
        if str(current).strip().lower() != "foodpulse":
            raise ValueError("Refusing to load: current_database is not the local FoodPulse database")
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    from app.db.session import Base
    from app.models import Customer, Location, Order, Restaurant, Review  # noqa: F401

    # Creates missing tables from the existing ORM models. Never drops or truncates.
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)()


def _models() -> dict[str, type]:
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    from app.models.customer import Customer
    from app.models.location import Location
    from app.models.order import Order
    from app.models.restaurant import Restaurant
    from app.models.review import Review

    return {
        "Location": Location,
        "Restaurant": Restaurant,
        "Customer": Customer,
        "Order": Order,
        "Review": Review,
    }


if __name__ == "__main__":
    sys.exit(main())
