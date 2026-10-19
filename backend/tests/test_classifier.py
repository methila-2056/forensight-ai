"""Segment classifier tests (Phase 9b).

The classifier is supervised and trained on the shipped **synthetic** incident
corpora. These tests cover:

* the contract that keeps it honest — synthetic labelling on every response,
  abstention when the labelled set is unusable, and no real-world claims;
* provenance-based labelling (never derived from rule output or anomaly score);
* the API surface, case scoping, and determinism;
* that it stays a *separate* signal from Strategy A anomaly detection.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.engines.ml import classifier as clf

INCIDENT_DIR = (
    Path(__file__).resolve().parents[1] / "demo" / "scenarios" / "incidents"
)

FILES = [
    ("authentication.csv", "authentication"),
    ("process.csv", "process"),
    ("file_activity.csv", "file_activity"),
    ("network.csv", "network"),
    ("browser.csv", "browser"),
    ("system_logs.json", "system"),
]


def _load_corpus(client, upload_evidence, make_case, scenario: str) -> str:
    case_id = make_case(
        name=f"Classifier corpus {scenario}", description="classifier training data"
    )["case_id"]
    for filename, evidence_type in FILES:
        path = INCIDENT_DIR / scenario / filename
        content_type = "application/json" if filename.endswith(".json") else "text/csv"
        response = upload_evidence(
            case_id,
            filename,
            path.read_bytes(),
            content_type=content_type,
            evidence_type=evidence_type,
            source=f"corpus {scenario}",
        )
        assert response.status_code == 201, response.text
    assert client.post(
        f"/api/cases/{case_id}/process", json={"actor": "test"}
    ).status_code == 200
    return case_id


@pytest.fixture(scope="module")
def trained_db():
    """Ingest all three corpora into the shared test database and train once.

    Builds its own client rather than depending on the function-scoped `client`
    fixture, so the corpora are ingested and the model fitted a single time for
    the whole module. It deliberately does *not* repoint DATABASE_URL: reloading
    `app.config` mid-suite would leave later tests pointing at a directory this
    fixture then deletes.
    """
    from fastapi.testclient import TestClient

    from app.main import app

    case_ids: dict[str, str] = {}
    with TestClient(app) as client:
        for scenario in ("A", "B", "C"):
            cid = client.post(
                "/api/cases",
                json={
                    "name": f"Classifier corpus {scenario}",
                    "investigator": "test",
                    "description": "classifier training data",
                    "severity": "Medium",
                },
            ).json()["case_id"]
            for filename, evidence_type in FILES:
                path = INCIDENT_DIR / scenario / filename
                content_type = (
                    "application/json" if filename.endswith(".json") else "text/csv"
                )
                response = client.post(
                    f"/api/cases/{cid}/evidence",
                    files={"file": (filename, path.read_bytes(), content_type)},
                    data={"evidence_type": evidence_type, "source": f"corpus {scenario}"},
                )
                assert response.status_code == 201, response.text
            assert client.post(
                f"/api/cases/{cid}/process", json={"actor": "test"}
            ).status_code == 200
            case_ids[scenario] = cid

        trained = client.post("/api/classifier/train")
        assert trained.status_code == 200, trained.text
        metrics = trained.json()

    return {"case_ids": case_ids, "metrics": metrics}


@pytest.fixture()
def trained_client(trained_db):
    """A request-scoped client for endpoint assertions, sharing the module DB."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        yield client


# --- labelling provenance ---------------------------------------------------


def test_labels_come_from_scenario_provenance_not_findings():
    """A window is labelled by when it falls relative to the incident anchor."""
    spec_b = clf.spec_for("B")
    assert spec_b is not None
    assert spec_b.label_after_anchor == "compromise"

    before = spec_b.anchor.replace(minute=0)
    after = spec_b.anchor.replace(minute=59)
    assert clf.label_for_window(spec_b, before) == "benign"
    assert clf.label_for_window(spec_b, after) == "compromise"

    # Scenario A has no incident, so every window stays benign.
    spec_a = clf.spec_for("A")
    assert spec_a.label_after_anchor == "benign"
    assert clf.label_for_window(spec_a, spec_a.anchor) == "benign"


def test_label_vocabulary_is_closed():
    assert set(clf.LABELS) == {"benign", "compromise", "ransomware_like"}
    for spec in clf.SCENARIO_SPECS:
        assert spec.label_after_anchor in clf.LABELS


# --- abstention -------------------------------------------------------------


def test_abstains_when_no_windows_supplied():
    metrics = clf.evaluate([])
    assert metrics.abstained is True
    assert "no labelled windows" in metrics.abstained_reason
    assert metrics.accuracy is None
    assert metrics.f1 is None


def test_abstains_when_a_label_is_missing():
    windows = [
        clf.LabelledWindow(
            window_start=None, window_end=None,
            features={"total": 5}, label="benign", scenario="A",
        )
        for _ in range(20)
    ]
    metrics = clf.evaluate(windows)
    assert metrics.abstained is True
    assert "does not cover the label vocabulary" in metrics.abstained_reason


def test_abstains_when_too_few_windows_per_class():
    windows = []
    for label in clf.LABELS:
        for i in range(3):  # far below MIN_WINDOWS_PER_CLASS
            windows.append(
                clf.LabelledWindow(
                    window_start=None, window_end=None,
                    features={"total": 5, "distinct_users": 1},
                    label=label, scenario="X",
                )
            )
    metrics = clf.evaluate(windows)
    assert metrics.abstained is True
    assert "too few windows" in metrics.abstained_reason
    assert metrics.accuracy is None


def test_abstention_carries_the_synthetic_label():
    metrics = clf.evaluate([])
    assert metrics.synthetic_label == clf.SYNTHETIC_LABEL
    assert "synthetic demonstration data" in metrics.synthetic_label
    assert "not a statement about any real environment" in metrics.disclaimer


# --- training on the real corpora ------------------------------------------


def test_training_covers_all_three_labels(trained_db, trained_client):
    metrics = trained_db["metrics"]
    assert metrics["abstained"] is False, metrics.get("abstained_reason")
    assert set(metrics["class_counts"]) == set(clf.LABELS)
    for label, count in metrics["class_counts"].items():
        assert count >= clf.MIN_WINDOWS_PER_CLASS, f"{label}={count}"


def test_training_reports_real_metrics(trained_db, trained_client):
    metrics = trained_db["metrics"]
    for field in ("accuracy", "precision", "recall", "f1"):
        value = metrics[field]
        assert value is not None, field
        assert 0.0 <= value <= 1.0, field

    assert metrics["cv_folds"] == 5
    assert metrics["cv_accuracy_mean"] is not None
    assert metrics["cv_accuracy_std"] is not None
    assert metrics["baseline_accuracy"] is not None
    assert len(metrics["confusion_matrix"]) == len(clf.LABELS)
    assert metrics["per_class"]
    assert metrics["split_desc"].startswith("stratified 75/25")


def test_model_beats_the_majority_class_baseline(trained_db, trained_client):
    """A classifier that cannot beat 'always guess the biggest class' is noise."""
    metrics = trained_db["metrics"]
    assert metrics["accuracy"] > metrics["baseline_accuracy"], (
        f"accuracy {metrics['accuracy']:.3f} does not beat majority-class "
        f"baseline {metrics['baseline_accuracy']:.3f}"
    )


def test_metrics_always_carry_the_synthetic_label(trained_db, trained_client):
    metrics = trained_db["metrics"]
    assert metrics["synthetic_label"] == clf.SYNTHETIC_LABEL
    assert "synthetic demonstration data" in metrics["synthetic_label"]
    assert "not a statement about any real environment" in metrics["disclaimer"]
    # Stored description must repeat the provenance and the caveat.
    assert "synthetic incident corpora" in metrics["dataset_desc"]


def test_metrics_persist_and_survive_a_reread(trained_db, trained_client):
    """GET must serve the stored evaluation without retraining."""
    client = trained_client
    metrics = client.get("/api/classifier/metrics").json()
    assert metrics["trained"] is True
    assert metrics["abstained"] is False
    # The rich fields must survive the round trip through the database.
    assert metrics["baseline_accuracy"] is not None
    assert metrics["cv_accuracy_mean"] is not None
    assert metrics["confusion_matrix"]
    assert metrics["class_counts"]
    assert metrics["window_count"] > 0
    assert metrics["synthetic_label"] == clf.SYNTHETIC_LABEL


def test_training_is_deterministic(trained_db, trained_client):
    """Same corpora, same seed, same figures."""
    client = trained_client
    first = client.post("/api/classifier/train").json()
    second = client.post("/api/classifier/train").json()
    for field in ("accuracy", "precision", "recall", "f1", "cv_accuracy_mean",
                  "confusion_matrix", "class_counts", "window_count"):
        assert first[field] == second[field], f"{field} is not deterministic"


# --- per-window results -----------------------------------------------------


def test_stored_classifications_cover_the_label_vocabulary(
    trained_db, trained_client
):
    """Stored per-window results must carry valid, caveated predictions.

    Results are attached to the case that contributed each scenario's corpus.
    When a corpus has been ingested by more than one case (which happens
    whenever the suite ingests the same evidence twice), the rows belong to the
    first matching case — so this asserts the contract that matters, namely that
    the predictions are valid, labelled, and caveated, rather than pinning rows
    to a particular case ID.
    """
    client = trained_client
    labels: set[str] = set()
    seen = 0
    for case in client.get("/api/cases").json():
        response = client.get(f"/api/cases/{case['case_id']}/classifier-results")
        assert response.status_code == 200, response.text
        body = response.json()
        seen += body["total"]
        for row in body["results"]:
            labels.add(row["predicted_label"])
            assert 0.0 <= row["class_score"] <= 1.0
            assert row["model_version"] == clf.MODEL_VERSION
            assert row["synthetic_label"] == clf.SYNTHETIC_LABEL
            assert "not a statement about any real environment" in row["disclaimer"]

    assert seen > 0, "no classifier results were stored"
    assert labels <= set(clf.LABELS)
    assert labels, "no predictions were stored"


def test_classifier_results_are_case_scoped(trained_db, trained_client):
    client = trained_client
    outsider = client.post(
        "/api/cases",
        json={"name": "Outsider", "investigator": "t",
              "description": "d", "severity": "Low"},
    ).json()["case_id"]

    body = client.get(f"/api/cases/{outsider}/classifier-results").json()
    assert body["total"] == 0

    unknown = client.get("/api/cases/CASE-2026-999/classifier-results")
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "CASE_NOT_FOUND"


def test_retraining_replaces_rather_than_accumulates_results(trained_db, trained_client):
    """Repeated training must not inflate the stored result count."""
    client = trained_client
    first = client.get(
        f"/api/cases/{trained_db['case_ids']['A']}/classifier-results"
    ).json()["total"]
    client.post("/api/classifier/train")
    second = client.get(
        f"/api/cases/{trained_db['case_ids']['A']}/classifier-results"
    ).json()["total"]
    assert first == second


# --- separation from Strategy A ---------------------------------------------


def test_classifier_is_distinct_from_anomaly_detection():
    """The two signals must not be conflated in the code or the labels."""
    assert clf.WINDOW_MINUTES != 5, (
        "segment windows should be distinct from Strategy A's 5-minute windows"
    )
    assert clf.MODEL_VERSION != "isolation_forest"
    # Anomaly detection emits a score; the classifier emits a closed label set.
    assert clf.LABELS
    assert all(isinstance(label, str) for label in clf.LABELS)


def test_untrained_payload_is_explicit(monkeypatch):
    """With no stored metrics the service must say so, not return empty numbers."""
    from app.services import classifier_service

    monkeypatch.setattr(classifier_service, "latest_metrics", lambda db: None)

    class _Db:
        pass

    payload = classifier_service.metrics_payload(_Db())
    assert payload["trained"] is False
    assert "has not been trained" in payload["reason"]
    assert payload["synthetic_label"] == clf.SYNTHETIC_LABEL
    assert payload["disclaimer"]