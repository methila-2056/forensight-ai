"""Cross-surface synthetic / demonstration detection regression tests (P3).

Report, workspace, and dashboard must label identically. The exact canonical
``terminology.DEMO_LABEL`` substring inside a case description, an evidence
source description, or an ingested raw record — or the ``demo`` flag — labels
the case on every surface. Loose words ("Synthetic identity fraud",
"Demolition site") and file names alone must never label a case.

Matching is case-sensitive. Description and source description are matched in
Python so the semantics are identical on the SQLite test database and on
production PostgreSQL (whose ``LIKE`` is case-sensitive, while SQLite's
``LIKE`` is case-insensitive for ASCII): the lowercase-marker tests below
would start failing on SQLite if these signals were ever reimplemented with
engine-dependent SQL ``LIKE``.
"""

from __future__ import annotations

from sqlalchemy import select

from app import terminology
from app.db import SessionLocal
from app.models import Case

_CLEAN_CSV = b"timestamp,user,action\n2026-01-01T00:00:00Z,alice,login\n"


def _dashboard_label(client, case_id: str) -> str | None:
    response = client.get("/api/dashboard")
    assert response.status_code == 200, response.text
    kpi = next(
        (item for item in response.json()["cases"] if item["case_id"] == case_id),
        None,
    )
    assert kpi is not None, f"case {case_id} missing from dashboard KPIs"
    return kpi["synthetic_label"]


def _workspace_label(client, case_id: str) -> str | None:
    response = client.get(f"/api/cases/{case_id}/workspace")
    assert response.status_code == 200, response.text
    return response.json()["case"]["synthetic_label"]


def _report_labels(client, case_id: str) -> tuple[str | None, str]:
    """Fresh report snapshot: (limitations.synthetic, executive overview)."""
    response = client.post(f"/api/cases/{case_id}/reports", json={})
    assert response.status_code == 201, response.text
    sections = response.json()["sections"]
    return (
        sections["limitations"]["synthetic"],
        sections["executive_summary"]["overview"],
    )


def _assert_all_surfaces(client, case_id: str, labelled: bool) -> None:
    """Dashboard, workspace, and report must agree exactly."""
    expected = terminology.DEMO_LABEL if labelled else None
    assert _dashboard_label(client, case_id) == expected
    assert _workspace_label(client, case_id) == expected
    synthetic, overview = _report_labels(client, case_id)
    assert synthetic == expected
    if labelled:
        assert terminology.DEMO_LABEL in overview
    else:
        assert terminology.DEMO_LABEL not in overview


def _process(client, case_id: str) -> None:
    response = client.post(f"/api/cases/{case_id}/process", json={})
    assert response.status_code == 200, response.text


# ---------------------------------------------------------------------------
# Positive signals — the demo flag, description, source description, content
# ---------------------------------------------------------------------------


def test_report_labels_case_when_demo_flag_set(client, make_case):
    case = make_case(name="Demo Flag Case")
    with SessionLocal() as db:
        row = db.scalar(select(Case).where(Case.case_id == case["case_id"]))
        assert row is not None
        row.demo = True
        db.commit()
    _assert_all_surfaces(client, case["case_id"], labelled=True)


def test_workspace_labels_marker_in_raw_record_content(
    client, make_case, upload_evidence
):
    case = make_case(name="Content Marker Case")
    data = (
        "timestamp,user,action,note\n"
        f"2026-01-01T00:00:00Z,alice,login,{terminology.DEMO_LABEL}\n"
    ).encode()
    response = upload_evidence(case["case_id"], "demo.csv", data)
    assert response.status_code == 201, response.text
    _process(client, case["case_id"])
    assert (
        _workspace_label(client, case["case_id"]) == terminology.DEMO_LABEL
    )
    _assert_all_surfaces(client, case["case_id"], labelled=True)


def test_exact_marker_in_case_description_labels_all_surfaces(client, make_case):
    case = make_case(
        name="Description Marker Case",
        description=(
            f"{terminology.DEMO_LABEL} ONLY. Fixture rows created to verify "
            "the live deployment end to end."
        ),
    )
    _assert_all_surfaces(client, case["case_id"], labelled=True)


def test_exact_marker_in_source_description_labels_all_surfaces(
    client, make_case, upload_evidence
):
    case = make_case(name="Source Description Marker Case")
    response = upload_evidence(
        case["case_id"],
        "fixture.csv",
        _CLEAN_CSV,
        source=f"Synthetic demonstration CSV ({terminology.DEMO_LABEL})",
    )
    assert response.status_code == 201, response.text
    assert terminology.DEMO_LABEL in response.json()["source_description"]
    _assert_all_surfaces(client, case["case_id"], labelled=True)


# ---------------------------------------------------------------------------
# Negative signals — filename tokens, loose words, wrong case
# ---------------------------------------------------------------------------


def test_filename_tokens_alone_do_not_label(client, make_case, upload_evidence):
    case = make_case(name="Filename Tokens Case")
    response = upload_evidence(
        case["case_id"],
        "SYNTHETIC-DEMO-DATA_auth_events.csv",
        _CLEAN_CSV,
    )
    assert response.status_code == 201, response.text
    _process(client, case["case_id"])
    _assert_all_surfaces(client, case["case_id"], labelled=False)


def test_loose_words_do_not_label(client, make_case, upload_evidence):
    case = make_case(
        name="Synthetic Identity Fraud",
        description=(
            "Demolition site arson investigation — witness accounts and CCTV."
        ),
    )
    response = upload_evidence(
        case["case_id"],
        "demolition_demo_notes.csv",
        _CLEAN_CSV,
        source="Demolition site photos; synthetic-id suspects",
    )
    assert response.status_code == 201, response.text
    _process(client, case["case_id"])
    _assert_all_surfaces(client, case["case_id"], labelled=False)


def test_marker_matching_is_case_sensitive_like_postgres(
    client, make_case, upload_evidence
):
    lowercase = terminology.DEMO_LABEL.lower()
    case = make_case(
        name="Lowercase Marker Case",
        description=f"{lowercase} only — must not label a case.",
    )
    response = upload_evidence(
        case["case_id"],
        "lowercase_source.csv",
        _CLEAN_CSV,
        source=f"fixture ({lowercase})",
    )
    assert response.status_code == 201, response.text
    _assert_all_surfaces(client, case["case_id"], labelled=False)

    exact = make_case(
        name="Exact Case Marker Case",
        description=f"Export contains {terminology.DEMO_LABEL}.",
    )
    _assert_all_surfaces(client, exact["case_id"], labelled=True)
