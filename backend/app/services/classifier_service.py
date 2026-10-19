"""Segment classifier service (Phase 9b).

Builds a labelled training set from the **synthetic incident corpora**, trains
and evaluates the segment classifier, stores metrics in `model_metrics` and
per-window predictions in `classifier_results`, and serves both.

Two honesty properties are load-bearing here:

* The classifier never labels the same case it was trained on when producing
  "performance" figures. `evaluate` holds out a stratified split, and the API
  labels the returned numbers as synthetic-data metrics.
* Every response carries the mandatory synthetic-data label, so a metric can
  never be quoted without the caveat that travels with it.

Abstention is a first-class outcome: when the labelled set is too small,
imbalanced, or missing a label, the service returns an explicit abstention with
a reason instead of a metric computed from too few rows.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import config
from app.engines.features import FeatureBuilder
from app.engines.ml import classifier as clf
from app.models import Case, ClassifierResult, ForensicEvent, ModelMetric, utcnow

# The incident corpora are shipped with the repo. If they are absent (for
# example in a trimmed deployment) the service abstains rather than guessing.
INCIDENT_DIR = Path(__file__).resolve().parents[2] / "demo" / "scenarios" / "incidents"

EVIDENCE_TYPES = [
    ("authentication.csv", "authentication"),
    ("process.csv", "process"),
    ("file_activity.csv", "file_activity"),
    ("network.csv", "network"),
    ("browser.csv", "browser"),
    ("system_logs.json", "system"),
]

# Retained classifier results are bounded like every other stored series.
MAX_RESULTS = 500


def corpora_available() -> bool:
    if not INCIDENT_DIR.is_dir():
        return False
    return all(
        (INCIDENT_DIR / spec.key / filename).is_file()
        for spec in clf.SCENARIO_SPECS
        for filename, _ in EVIDENCE_TYPES
    )


def _load_events_for_case(db: Session, case_id: str) -> list[ForensicEvent]:
    return list(
        db.scalars(
            select(ForensicEvent)
            .where(ForensicEvent.case_id == _case_pk(db, case_id))
            .order_by(ForensicEvent.timestamp, ForensicEvent.id)
        )
    )


def _case_pk(db: Session, case_id: str) -> int:
    case = db.scalar(select(Case).where(Case.case_id == case_id))
    return case.id if case else -1


def build_labelled_windows(
    db: Session, *, window_minutes: int | None = None
) -> tuple[list[clf.LabelledWindow], list[str]]:
    """Build the labelled training set from every case that ingested a corpus.

    A case qualifies when it holds evidence whose stored raw bytes match one of
    the shipped corpora (matched by SHA-256, not filename). That keeps the
    labels tied to provenance rather than to whatever a user happened to name
    their upload.
    """
    minutes = window_minutes or clf.WINDOW_MINUTES
    builder = FeatureBuilder(window_minutes=minutes)

    corpus_hashes = _corpus_digests()
    if not corpus_hashes:
        return [], []

    windows: list[clf.LabelledWindow] = []
    used_cases: list[str] = []

    case_rows = db.scalars(select(Case).order_by(Case.id)).all()
    for case in case_rows:
        # Does this case contain a whole corpus? Matched by SHA-256 of the
        # stored bytes, not by filename, so labels follow provenance rather
        # than whatever a user happened to call their upload.
        from app.models import Evidence

        evidence_rows = db.scalars(
            select(Evidence).where(Evidence.case_id == case.id)
        ).all()
        present = {e.original_hash for e in evidence_rows if e.original_hash}

        spec = None
        for candidate in clf.SCENARIO_SPECS:
            digests = corpus_hashes.get(candidate.key)
            if digests and (digests & present):
                spec = candidate
                break
        if spec is None:
            continue

        events = list(
            db.scalars(
                select(ForensicEvent)
                .where(ForensicEvent.case_id == case.id)
                .order_by(ForensicEvent.timestamp, ForensicEvent.id)
            )
        )
        if not events:
            continue

        for window in builder.build(events):
            label = clf.label_for_window(spec, window.window_end)
            windows.append(
                clf.LabelledWindow(
                    window_start=window.window_start,
                    window_end=window.window_end,
                    features=dict(window.features),
                    label=label,
                    scenario=spec.key,
                )
            )
        used_cases.append(case.case_id)

    windows.sort(key=lambda w: (w.scenario, w.window_start))
    return windows, used_cases


def _corpus_digests() -> dict[str, set[str]]:
    """SHA-256 of each corpus's files, keyed by scenario letter."""
    import hashlib

    out: dict[str, set[str]] = {}
    for spec in clf.SCENARIO_SPECS:
        digests: set[str] = set()
        directory = INCIDENT_DIR / spec.key
        if not directory.is_dir():
            continue
        for filename, _ in EVIDENCE_TYPES:
            path = directory / filename
            if path.is_file():
                digests.add(hashlib.sha256(path.read_bytes()).hexdigest())
        if digests:
            out[spec.key] = digests
    return out


def train_and_store(db: Session) -> clf.ClassifierMetrics:
    """Train on the synthetic corpora, persist metrics and per-window results."""
    windows, case_ids = build_labelled_windows(db)

    metrics = evaluate_windows(windows, case_ids)

    if not metrics.abstained:
        predictions, _ = clf.fit_predict(windows)
        if predictions:
            _store_results(db, windows, predictions)
    _store_metrics(db, metrics)
    db.commit()
    return metrics


def evaluate_windows(
    windows: list[clf.LabelledWindow], case_ids: list[str] | None = None
) -> clf.ClassifierMetrics:
    metrics = clf.evaluate(windows)
    if case_ids:
        metrics.dataset_desc = (
            f"{metrics.dataset_desc}; source cases {', '.join(case_ids)}"
            if metrics.dataset_desc
            else f"source cases {', '.join(case_ids)}"
        )
    if not metrics.dataset_desc:
        metrics.dataset_desc = (
            "no labelled windows could be built from the shipped incident corpora"
        )
    if metrics.abstained and windows:
        metrics.dataset_desc = (
            f"{len(windows)} labelled windows from cases "
            f"{', '.join(case_ids or [])}; {metrics.dataset_desc}"
        )
    return metrics


def _store_results(
    db: Session,
    windows: list[clf.LabelledWindow],
    predictions: list[tuple[str, float]],
) -> None:
    # Results are a derived snapshot: replace them rather than accumulate, so
    # repeated training does not inflate the count.
    db.execute(delete(ClassifierResult))

    for window, (label, score) in zip(windows, predictions):
        db.add(
            ClassifierResult(
                case_id=_case_pk_for_scenario(db, window.scenario),
                window_start=window.window_start,
                window_end=window.window_end,
                predicted_label=label,
                class_score=float(score),
                model_version=clf.MODEL_VERSION,
            )
        )
    db.flush()


def _case_pk_for_scenario(db: Session, scenario: str) -> int:
    """Attach results to the case that ingested that scenario's corpus."""
    digests = _corpus_digests().get(scenario, set())
    if not digests:
        return -1
    from app.models import Evidence

    for case in db.scalars(select(Case).order_by(Case.id)).all():
        present = {
            e.original_hash
            for e in db.scalars(
                select(Evidence).where(Evidence.case_id == case.id)
            ).all()
        }
        if present & digests:
            return case.id
    return -1


def _store_metrics(db: Session, metrics: clf.ClassifierMetrics) -> None:
    db.execute(
        delete(ModelMetric).where(ModelMetric.model_name == clf.MODEL_VERSION)
    )
    db.add(
        ModelMetric(
            model_name=clf.MODEL_VERSION,
            trained_at=utcnow(),
            dataset_desc=metrics.dataset_desc[:255],
            split_desc=metrics.split_desc[:255],
            precision=metrics.precision,
            recall=metrics.recall,
            f1=metrics.f1,
            accuracy=metrics.accuracy,
            feature_list=metrics.feature_list,
            # The whole evaluation result, so GET never has to retrain.
            metrics_json=_jsonable(metrics.as_dict()),
            # Mandatory label + abstention reason live with the stored metric.
            notes=_notes_for(metrics),
        )
    )
    db.flush()


def _jsonable(payload: dict) -> dict:
    """Keep only JSON-serialisable values (NaN/inf from sklearn are dropped)."""
    import math

    out: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            out[key] = None
        elif isinstance(value, dict):
            out[key] = _jsonable(value)
        else:
            out[key] = value
    return out


def _notes_for(metrics: clf.ClassifierMetrics) -> str:
    if metrics.abstained:
        return (
            f"{clf.SYNTHETIC_LABEL} ABSTAINED: {metrics.abstained_reason}"
        )
    parts = [clf.SYNTHETIC_LABEL, clf.NO_REAL_WORLD_CLAIM]
    if metrics.baseline_accuracy is not None:
        parts.append(
            f"majority-class baseline accuracy {metrics.baseline_accuracy:.3f}."
        )
    if metrics.cv_accuracy_mean is not None:
        parts.append(
            f"{metrics.cv_folds}-fold CV accuracy "
            f"{metrics.cv_accuracy_mean:.3f} +/- {metrics.cv_accuracy_std:.3f}."
        )
    return " ".join(parts)


def latest_metrics(db: Session) -> clf.ClassifierMetrics | None:
    """Most recent stored metrics for the segment classifier, if any."""
    row = db.scalar(
        select(ModelMetric)
        .where(ModelMetric.model_name == clf.MODEL_VERSION)
        .order_by(ModelMetric.trained_at.desc(), ModelMetric.id.desc())
        .limit(1)
    )
    if row is None:
        return None
    return _metrics_from_row(row)


def _metrics_from_row(row: ModelMetric) -> clf.ClassifierMetrics:
    # Prefer the stored full payload; fall back to the scalar columns for rows
    # written before `metrics_json` existed.
    stored = row.metrics_json or {}
    if stored:
        metrics = clf.ClassifierMetrics()
        for key, value in stored.items():
            if hasattr(metrics, key):
                setattr(metrics, key, value)
        metrics.model_name = row.model_name
        return metrics

    metrics = clf.ClassifierMetrics(
        model_name=row.model_name,
        dataset_desc=row.dataset_desc,
        split_desc=row.split_desc,
        precision=row.precision,
        recall=row.recall,
        f1=row.f1,
        accuracy=row.accuracy,
        feature_list=list(row.feature_list or []),
    )
    notes = row.notes or ""
    if "ABSTAINED:" in notes:
        metrics.abstained = True
        metrics.abstained_reason = notes.split("ABSTAINED:", 1)[1].strip()
    return metrics


def classifier_results(db: Session, case_id: str, limit: int = 100) -> list[dict[str, Any]]:
    """Stored per-window predictions for one case (cross-case scoped)."""
    bounded = max(1, min(int(limit or 100), MAX_RESULTS))
    rows = db.scalars(
        select(ClassifierResult)
        .where(ClassifierResult.case_id == _case_pk(db, case_id))
        .order_by(ClassifierResult.window_start, ClassifierResult.id)
        .limit(bounded)
    ).all()
    return [
        {
            "case_id": case_id,
            "window_start": r.window_start,
            "window_end": r.window_end,
            "predicted_label": r.predicted_label,
            "class_score": r.class_score,
            "model_version": r.model_version,
            "synthetic_label": clf.SYNTHETIC_LABEL,
            "disclaimer": clf.NO_REAL_WORLD_CLAIM,
        }
        for r in rows
    ]


def metrics_payload(db: Session) -> dict[str, Any]:
    """API payload. Always carries the synthetic-data label."""
    metrics = latest_metrics(db)
    if metrics is None:
        return {
            "trained": False,
            "model_name": clf.MODEL_VERSION,
            "synthetic_label": clf.SYNTHETIC_LABEL,
            "disclaimer": clf.NO_REAL_WORLD_CLAIM,
            "reason": (
                "the segment classifier has not been trained in this database; "
                "load the synthetic incident corpora and run training"
            ),
            "corpora_available": corpora_available(),
        }
    payload = metrics.as_dict()
    payload["trained"] = True
    payload["corpora_available"] = corpora_available()
    payload["config"] = {
        "window_minutes": clf.WINDOW_MINUTES,
        "labels": list(clf.LABELS),
        "random_state": config.RANDOM_STATE,
    }
    return payload


__all__ = [
    "INCIDENT_DIR",
    "corpora_available",
    "build_labelled_windows",
    "train_and_store",
    "evaluate_windows",
    "latest_metrics",
    "classifier_results",
    "metrics_payload",
]