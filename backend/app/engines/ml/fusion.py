"""Hybrid fusion — Composite Suspicion Score (Phase 3, Architecture v1.4 §9.3).

CSS is an **uncalibrated heuristic composite**, never a probability and never
proof of malicious activity. The formula and weights are stored with every
analysis run and rendered verbatim in the UI explanation panel.

    CSS  = 0.40 · RuleComponent          (0 when no rule; else 0.5 + 0.5·severity weight)
         + 0.35 · AnomalyComponent       (anomaly score of the anchor window/event)
         + 0.25 · CorrelationComponent   (distinct supporting evidence sources ÷ 5, capped 1.0)

Bands: <0.35 Informational · 0.35–0.55 Low interest ·
       0.55–0.75 Anomalous — review · ≥0.75 Potentially suspicious — high priority
"""

from __future__ import annotations

from app.models import SeverityLevel

FUSION_VERSION = "fusion_v1"

WEIGHTS: dict[str, float] = {
    "rule": 0.40,
    "anomaly": 0.35,
    "correlation": 0.25,
}

SEVERITY_WEIGHTS: dict[str, float] = {
    SeverityLevel.LOW.value: 0.25,
    SeverityLevel.MEDIUM.value: 0.5,
    SeverityLevel.HIGH.value: 0.75,
    SeverityLevel.CRITICAL.value: 1.0,
}

EVIDENCE_DIVISOR = 5.0

BANDS: tuple[tuple[float, str], ...] = (
    (0.75, "Potentially suspicious - high priority"),
    (0.55, "Anomalous - review"),
    (0.35, "Low interest"),
    (0.0, "Informational"),
)


def band(css: float) -> str:
    for cutoff, label in BANDS:
        if css >= cutoff:
            return label
    return "Informational"


def rule_component(severity: str | None) -> tuple[float, dict]:
    if not severity or severity not in SEVERITY_WEIGHTS:
        return 0.0, {"value": 0.0, "severity": None, "contribution": 0.0}
    value = 0.5 + 0.5 * SEVERITY_WEIGHTS[severity]
    return value, {"value": round(value, 4), "severity": severity, "contribution": 0.0}


def anomaly_component(score: float | None) -> tuple[float, dict]:
    value = max(0.0, min(1.0, float(score or 0.0)))
    return value, {"value": round(value, 4), "contribution": 0.0}


def correlation_component(distinct_evidence: int) -> tuple[float, dict]:
    value = min(float(distinct_evidence) / EVIDENCE_DIVISOR, 1.0)
    return value, {
        "value": round(value, 4),
        "distinct_evidence": int(distinct_evidence),
        "contribution": 0.0,
    }


def composite_suspicion_score(
    *,
    rule_severity: str | None = None,
    anomaly_score: float | None = None,
    distinct_evidence: int = 0,
) -> tuple[float, dict]:
    """Return (css, components-payload) for one finding."""
    rule_value, rule_info = rule_component(rule_severity)
    anomaly_value, anomaly_info = anomaly_component(anomaly_score)
    corr_value, corr_info = correlation_component(distinct_evidence)

    rule_part = WEIGHTS["rule"] * rule_value
    anomaly_part = WEIGHTS["anomaly"] * anomaly_value
    corr_part = WEIGHTS["correlation"] * corr_value

    rule_info["contribution"] = round(rule_part, 4)
    anomaly_info["contribution"] = round(anomaly_part, 4)
    corr_info["contribution"] = round(corr_part, 4)

    css = round(min(1.0, rule_part + anomaly_part + corr_part), 4)
    payload = {
        "formula_version": FUSION_VERSION,
        "formula": (
            "CSS = 0.40 * rule_component + 0.35 * anomaly_component "
            "+ 0.25 * correlation_component"
        ),
        "weights": dict(WEIGHTS),
        "components": {
            "rule": rule_info,
            "anomaly": anomaly_info,
            "correlation": corr_info,
        },
        "total": css,
        "band": band(css),
        "note": (
            "Uncalibrated heuristic composite - not a probability and not proof "
            "of malicious activity. Requires investigator validation."
        ),
    }
    return css, payload
