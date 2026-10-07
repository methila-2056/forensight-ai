"""Database engine, session factory, and initialisation (Phase 0).

Phase 4 addition: a minimal legacy-schema guard. ``create_all`` never alters
existing tables, and SQLite ``CHECK`` constraints from the Phase 0-2 schema
cannot express the Phase 3 ``FindingStatus`` values, so pre-Phase-3 tables are
recreated. That is only ever done when the table is empty; a non-empty legacy
table raises instead of silently destroying data.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app import config
from app.models import Base


def _build_engine() -> Engine:
    kwargs: dict = {"future": True}
    if config.DATABASE_URL.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(config.DATABASE_URL, **kwargs)
    if config.DATABASE_URL.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _record):  # pragma: no cover
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return engine


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)

# table -> columns that must exist for the current models to work.
_LEGACY_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "investigation_runs": ("run_uid",),
    "rule_findings": ("run_id", "description", "updated_at", "composite_suspicion_score"),
    "ml_findings": ("run_id", "model_version", "title", "severity", "feature_snapshot",
                    "updated_at"),
    "correlations": ("correlation_uid", "correlation_type"),
    "investigation_groups": ("group_uid", "title", "severity"),
    "correlation_runs": ("run_uid", "status"),
}


def _drop_stale_tables() -> None:
    """Recreate tables whose Phase 0-2 schema predates newer columns.

    Only empty tables are dropped. A non-empty stale table raises: its rows
    were written under enum/CHECK constraints that the current models cannot
    read back, so a silent drop would destroy investigator history.
    """
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    with engine.begin() as connection:
        for table, required in _LEGACY_REQUIREMENTS.items():
            if table not in existing:
                continue
            columns = {column["name"] for column in inspector.get_columns(table)}
            missing = [name for name in required if name not in columns]
            if not missing:
                continue
            count = connection.execute(
                text(f'SELECT COUNT(*) FROM "{table}"')  # noqa: S608 - fixed table name
            ).scalar()
            if count:
                raise RuntimeError(
                    f"Table '{table}' uses a pre-Phase-3 schema and contains "
                    f"{count} row(s). Remove {config.BASE_DIR / 'data' / 'foresight.db'} "
                    "and re-ingest demo evidence, or migrate the table manually."
                )
            connection.execute(text(f'DROP TABLE "{table}"'))  # noqa: S608 - fixed table name


def init_db() -> None:
    """Create all tables. Safe to call repeatedly."""
    config.ensure_directories()
    _drop_stale_tables()
    Base.metadata.create_all(engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
