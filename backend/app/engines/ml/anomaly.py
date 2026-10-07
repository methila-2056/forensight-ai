"""Window-level anomaly detection — Strategy A (Phase 3).

Architecture v1.4 §9.1 Strategy A:

* input: deterministic feature windows from :mod:`app.engines.features`
* model: ``sklearn.ensemble.IsolationForest`` with a fixed seed
  (``RANDOM_STATE``), fit on the case's own windows (case-scoped)
* anomaly evidence = inverted ``decision_function`` min–max normalized to an
  **anomaly score in [0, 1]** over this case's windows (1 = most anomalous)
* a window is flagged only when BOTH gates pass:
    1. normalized score >= ``ANOMALY_THRESHOLD`` (fixed constant, default 0.72)
    2. raw decision score < reference_mean - ``ML_Z_SIGMAS`` * reference_std
* the detector **abstains** (no ML finding) when the case has fewer than
  ``ML_MIN_WINDOWS`` windows — too few samples for a meaningful comparison

The two-gate design keeps the fixed-threshold semantics auditable (a benign
case with uniformly low scores never crosses the z-gate) while still being
reproducible: fixed seed, fixed feature order, single-threaded scoring.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import sklearn
from sklearn.ensemble import IsolationForest

from app import config
from app.engines.features import FEATURE_NAMES, FEATURE_VERSION, FeatureWindow

MODEL_NAME = "isolation_forest"
MODEL_VERSION = "phase3-window-a1"

SCORING_METHOD = (
    "IsolationForest decision_function inverted and min-max normalized to "
    "[0,1] over this case's windows"
)


@dataclass
class WindowScore:
    window: FeatureWindow
    raw_score: float
    score: float
    flagged: bool

    @property
    def events(self):
        return self.window.events


@dataclass
class AnomalyOutcome:
    abstained: bool
    reason: str
    threshold: float
    window_scores: list[WindowScore] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    @property
    def flagged(self) -> list[WindowScore]:
        return [ws for ws in self.window_scores if ws.flagged]


def score_windows(windows: list[FeatureWindow]) -> AnomalyOutcome:
    """Score one case's windows under Strategy A. Deterministic for a seed."""
    threshold = config.ANOMALY_THRESHOLD
    base_stats: dict = {
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "random_state": config.RANDOM_STATE,
        "n_estimators": config.ML_N_ESTIMATORS,
        "contamination": config.ML_CONTAMINATION,
        "training_scope": "case",
        "feature_version": FEATURE_VERSION,
        "feature_list": list(FEATURE_NAMES),
        "scoring_method": SCORING_METHOD,
        "threshold_value": threshold,
        "threshold_method": "fixed_constant",
        "threshold_gate": "normalized_score >= threshold AND raw_score < mean - z*std",
        "z_sigmas": config.ML_Z_SIGMAS,
        "min_windows": config.ML_MIN_WINDOWS,
        "windows_total": len(windows),
        "sklearn_version": sklearn.__version__,
    }

    if len(windows) < config.ML_MIN_WINDOWS:
        return AnomalyOutcome(
            abstained=True,
            reason=(
                f"{len(windows)} event window(s) available; at least "
                f"{config.ML_MIN_WINDOWS} are required for a meaningful ML "
                "comparison. Anomaly detection abstained and no ML finding was "
                "created for this run."
            ),
            threshold=threshold,
            stats={**base_stats, "abstained": True, "windows_flagged": 0},
        )

    matrix = np.asarray(
        [[window.features[name] for name in FEATURE_NAMES] for window in windows],
        dtype=np.float64,
    )
    model = IsolationForest(
        n_estimators=config.ML_N_ESTIMATORS,
        contamination=config.ML_CONTAMINATION,
        random_state=config.RANDOM_STATE,
        n_jobs=1,
    )
    model.fit(matrix)
    raw = model.decision_function(matrix)          # higher = more normal
    inverted = -raw                                # higher = more anomalous
    lo, hi = float(inverted.min()), float(inverted.max())
    if hi > lo:
        scores = (inverted - lo) / (hi - lo)
    else:  # all windows identical — nothing is more anomalous than anything else
        scores = np.zeros_like(inverted)

    ref_mean = float(raw.mean())
    ref_std = float(raw.std(ddof=0))
    gate = ref_mean - config.ML_Z_SIGMAS * ref_std

    window_scores: list[WindowScore] = []
    for index, window in enumerate(windows):
        score = float(scores[index])
        raw_value = float(raw[index])
        window_scores.append(
            WindowScore(
                window=window,
                raw_score=raw_value,
                score=score,
                flagged=score >= threshold and raw_value < gate,
            )
        )

    stats = {
        **base_stats,
        "abstained": False,
        "reference_mean": round(ref_mean, 6),
        "reference_std": round(ref_std, 6),
        "decision_gate": round(gate, 6),
        "windows_flagged": sum(1 for ws in window_scores if ws.flagged),
    }
    return AnomalyOutcome(
        abstained=False,
        reason="",
        threshold=threshold,
        window_scores=window_scores,
        stats=stats,
    )
