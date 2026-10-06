"""Terminology guard tests (Phase 0 acceptance criterion 9).

* Canonical strings must exist and carry the required claims.
* Banned phrases must not appear in the values of the terminology constants,
  nor anywhere in README.md / ARCHITECTURE.md / ATTRIBUTION.md.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import app.terminology as terminology_module

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS = ("README.md", "ARCHITECTURE.md", "ATTRIBUTION.md")


def _docs_text() -> str:
    parts = []
    for name in DOCS:
        path = REPO_ROOT / name
        assert path.exists(), f"Missing required document: {name}"
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts).casefold()


def test_canonical_product_language_present():
    concept = terminology_module.PRODUCT_CONCEPT
    assert concept.startswith("FORENSIGHT AI is an AI-assisted digital forensic investigation prototype")
    for required in (
        "verifies file integrity through SHA-256 hashing",
        "normalized forensic events",
        "explainable machine learning",
        "correlates evidence across sources",
        "investigator-reviewable timeline",
        "traceability from findings back to source evidence",
    ):
        assert required in concept, f"Missing from PRODUCT_CONCEPT: {required}"


def test_required_disclaimers_and_labels_exist():
    assert "prototype" in terminology_module.PROTOTYPE_DISCLAIMER.casefold()
    assert terminology_module.INTEGRITY_VERIFIED == "INTEGRITY VERIFIED"
    assert terminology_module.INTEGRITY_MISMATCH == "INTEGRITY MISMATCH"
    assert terminology_module.INTEGRITY_TEST_LABEL.startswith("Controlled Integrity Test")
    assert terminology_module.SCORE_LABEL == "Anomaly score"
    assert terminology_module.THRESHOLD_LABEL == "Detection threshold"
    assert terminology_module.FUSION_LABEL == "Composite Suspicion Score"
    assert terminology_module.TIMELINE_LABEL == "Reconstructed Investigation Timeline"
    assert terminology_module.INSUFFICIENT_EVIDENCE == "Insufficient evidence in the current case."
    assert terminology_module.SYNTHETIC_DATA_LABEL == "Trained and evaluated on synthetic demonstration data."
    assert terminology_module.PLANNED_LABEL == "Prototype / Planned"


def test_traceability_chain_order():
    assert terminology_module.TRACEABILITY_STEPS == (
        "Finding",
        "Reason",
        "Forensic Event",
        "Raw Record",
        "Evidence File",
        "Recorded SHA-256",
    )


def test_banned_terms_absent_from_constant_values():
    banned = [term.casefold() for term in terminology_module.BANNED_TERMS]
    assert banned, "BANNED_TERMS must not be empty"
    for name in dir(terminology_module):
        if name.startswith("_") or name == "BANNED_TERMS":
            continue
        value = getattr(terminology_module, name)
        if not isinstance(value, (str, tuple, list)):
            continue
        haystack = " ".join(value).casefold() if isinstance(value, (tuple, list)) else value.casefold()
        for term in banned:
            assert term not in haystack, f"Banned term '{term}' found in constant '{name}'"


def test_banned_terms_absent_from_documents():
    haystack = _docs_text()
    for term in terminology_module.BANNED_TERMS:
        assert term.casefold() not in haystack, f"Banned term '{term}' found in project documents"


def test_terminology_module_is_importable_and_stable():
    reloaded = importlib.reload(terminology_module)
    assert reloaded.PRODUCT_NAME == "FORENSIGHT AI"
