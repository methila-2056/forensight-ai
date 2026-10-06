"""Database schema tests (Phase 0 acceptance criterion 8)."""

from __future__ import annotations

from sqlalchemy import inspect

from app.db import engine, init_db
from app.models import Base

EXPECTED_TABLES = {
    "cases",
    "evidence",
    "integrity_checks",
    "chain_of_custody",
    "raw_records",
    "forensic_events",
    "rule_findings",
    "ml_findings",
    "classifier_results",
    "correlations",
    "investigation_runs",
    "investigator_notes",
    "model_metrics",
}


def test_all_architecture_tables_are_defined():
    defined = set(Base.metadata.tables)
    missing = EXPECTED_TABLES - defined
    assert not missing, f"Missing tables: {sorted(missing)}"


def test_init_db_creates_all_tables():
    init_db()
    existing = set(inspect(engine).get_table_names())
    missing = EXPECTED_TABLES - existing
    assert not missing, f"Tables not created: {sorted(missing)}"


def test_init_db_is_idempotent():
    init_db()
    init_db()
    existing = set(inspect(engine).get_table_names())
    assert EXPECTED_TABLES <= existing


def test_key_relationships_and_columns_exist():
    evidence = Base.metadata.tables["evidence"]
    assert any(fk.target_fullname.split(".")[0] == "cases" for fk in evidence.foreign_keys)
    for column in ("sha256", "original_hash", "uploaded_at", "status", "evidence_type"):
        assert column in evidence.c, f"evidence.{column} missing"

    events = Base.metadata.tables["forensic_events"]
    for column in ("timestamp", "source_type", "event_type", "anomaly_score", "metadata"):
        assert column in events.c, f"forensic_events.{column} missing"

    runs = Base.metadata.tables["investigation_runs"]
    assert "stats" in runs.c, "investigation_runs.stats (ML methodology carrier) missing"

    findings = Base.metadata.tables["rule_findings"]
    for column in ("rule_id", "explanation", "triggered_event_ids", "evidence_ids"):
        assert column in findings.c, f"rule_findings.{column} missing"

    custody = Base.metadata.tables["chain_of_custody"]
    assert {"timestamp", "action", "actor"} <= set(custody.c.keys())
