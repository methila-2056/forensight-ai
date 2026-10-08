"""Application configuration (Phase 0).

Values come from environment variables, optionally loaded from a `.env` file at
the repository root (see .env.example). Relative paths resolve against the
backend directory so the app behaves the same regardless of working directory.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]  # .../backend
ROOT_DIR = BASE_DIR.parent                      # repository root

load_dotenv(ROOT_DIR / ".env")

APP_NAME = os.getenv("APP_NAME", "FORENSIGHT AI")
APP_VERSION = os.getenv("APP_VERSION", "0.1.0")
API_PREFIX = "/api"


def _resolve_path(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (BASE_DIR / path).resolve()


def _resolve_sqlite_url(raw: str) -> str:
    """Resolve relative sqlite paths against the backend directory."""
    marker = "sqlite:///"
    if not raw.startswith(marker):
        return raw
    tail = raw[len(marker):]
    if not tail or tail == ":memory:":
        return raw
    return f"sqlite:///{_resolve_path(tail).as_posix()}"


DATABASE_URL = _resolve_sqlite_url(os.getenv("DATABASE_URL", "sqlite:///./data/foresight.db"))

EVIDENCE_STORE_DIR = _resolve_path(os.getenv("EVIDENCE_STORE_DIR", "./evidence_store"))

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "25"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

ALLOWED_EXTENSIONS = frozenset(
    ext.strip().lower().lstrip(".")
    for ext in os.getenv("ALLOWED_EXTENSIONS", "csv,json,txt,log,zip").split(",")
    if ext.strip()
)

# ML reproducibility (Architecture §9): one deterministic threshold strategy.
ANOMALY_THRESHOLD = float(os.getenv("ANOMALY_THRESHOLD", "0.72"))
RANDOM_STATE = int(os.getenv("RANDOM_STATE", "42"))

# Parser resource limit (Phase 2): a single processing run reads at most this
# many records; the remainder is reported as a warning and the run is marked
# Partial instead of silently continuing or claiming completion.
MAX_RECORDS_PER_RUN = int(os.getenv("MAX_RECORDS_PER_RUN", "200000"))

# ---------------------------------------------------------------------------
# Automated analysis (Phase 3) — deterministic feature windows + ML strategy A
# ---------------------------------------------------------------------------

# Normalized events are grouped into fixed-length windows for feature building.
ANALYSIS_WINDOW_MINUTES = int(os.getenv("ANALYSIS_WINDOW_MINUTES", "5"))

# ML threshold strategy A (documented in ARCHITECTURE.md §Strategy A):
# * anomaly score = min-max normalized IsolationForest decision_function over
#   the case's own windows
# * a window is flagged only when normalized_score >= ANOMALY_THRESHOLD AND the
#   raw decision score sits below reference_mean - ML_Z_SIGMAS * reference_std
# * the model abstains (no ML finding) when the case has fewer than
#   ML_MIN_WINDOWS windows
# These constants do not affect RANDOM_STATE-seeded rule detection.
ML_Z_SIGMAS = float(os.getenv("ML_Z_SIGMAS", "2.0"))
ML_MIN_WINDOWS = int(os.getenv("ML_MIN_WINDOWS", "8"))
ML_N_ESTIMATORS = int(os.getenv("ML_N_ESTIMATORS", "200"))
ML_CONTAMINATION = float(os.getenv("ML_CONTAMINATION", "0.1"))

# ---------------------------------------------------------------------------
# Rule configuration (Phase 3) — env-overridable, snapshot per analysis run
# ---------------------------------------------------------------------------

RULE_MAX_FINDINGS_PER_RULE = int(os.getenv("RULE_MAX_FINDINGS_PER_RULE", "10"))
RULE_AUTH001_MIN_FAILURES = int(os.getenv("RULE_AUTH001_MIN_FAILURES", "3"))
RULE_AUTH001_WINDOW_MINUTES = int(os.getenv("RULE_AUTH001_WINDOW_MINUTES", "15"))
RULE_AUTH002_MIN_EXTERNAL_LOGINS = int(os.getenv("RULE_AUTH002_MIN_EXTERNAL_LOGINS", "3"))
RULE_AUTH003_WINDOW_SECONDS = int(os.getenv("RULE_AUTH003_WINDOW_SECONDS", "60"))
RULE_FILE001_MIN_MODIFICATIONS = int(os.getenv("RULE_FILE001_MIN_MODIFICATIONS", "6"))
RULE_FILE001_WINDOW_MINUTES = int(os.getenv("RULE_FILE001_WINDOW_MINUTES", "15"))
RULE_FILE001_HIGH_MIN = int(os.getenv("RULE_FILE001_HIGH_MIN", "15"))
RULE_FILE002_MIN_RENAMES = int(os.getenv("RULE_FILE002_MIN_RENAMES", "3"))
RULE_FILE002_WINDOW_MINUTES = int(os.getenv("RULE_FILE002_WINDOW_MINUTES", "10"))
RULE_NET001_MIN_CONNECTIONS = int(os.getenv("RULE_NET001_MIN_CONNECTIONS", "2"))
RULE_NET001_WINDOW_MINUTES = int(os.getenv("RULE_NET001_WINDOW_MINUTES", "15"))

# ---------------------------------------------------------------------------
# Cross-source correlation, timeline, graph (Phase 4)
# ---------------------------------------------------------------------------

# Two events are considered for correlation when they are at most this many
# seconds apart (Architecture §11). Timestamps must be real, recorded
# values — events without a timestamp are never correlated.
CORRELATION_WINDOW_SECONDS = int(os.getenv("CORRELATION_WINDOW_SECONDS", "300"))

# Deterministic additive confidence weights (sum to 1.0; never a probability).
CORRELATION_WEIGHT_SAME_HOST = float(os.getenv("CORRELATION_WEIGHT_SAME_HOST", "0.30"))
CORRELATION_WEIGHT_SAME_USER = float(os.getenv("CORRELATION_WEIGHT_SAME_USER", "0.30"))
CORRELATION_WEIGHT_TIME_WINDOW = float(os.getenv("CORRELATION_WEIGHT_TIME_WINDOW", "0.25"))
CORRELATION_WEIGHT_SAME_SOURCE_IP = float(os.getenv("CORRELATION_WEIGHT_SAME_SOURCE_IP", "0.15"))

# Reconstructed timeline: events within this many minutes of a flagged event
# are included as context (significance NORMAL).
TIMELINE_CONTEXT_MINUTES = int(os.getenv("TIMELINE_CONTEXT_MINUTES", "2"))
# Safety cap on rendered timeline entries (the response reports truncation).
TIMELINE_MAX_ENTRIES = int(os.getenv("TIMELINE_MAX_ENTRIES", "500"))

# Evidence graph payload caps; responses beyond the caps set ``truncated``
# and include a table fallback for the UI.
MAX_GRAPH_NODES = int(os.getenv("MAX_GRAPH_NODES", "200"))
MAX_GRAPH_EDGES = int(os.getenv("MAX_GRAPH_EDGES", "500"))

CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173"
    ).split(",")
    if origin.strip()
]

# ---------------------------------------------------------------------------
# Investigation assistant (Phase 5) — deterministic, retrieval-first
# ---------------------------------------------------------------------------

# Question length cap (validated by the request schema).
ASSISTANT_MAX_QUESTION_LENGTH = int(os.getenv("ASSISTANT_MAX_QUESTION_LENGTH", "1000"))
# Newest-first history returned per case; persisted history is never rewritten.
ASSISTANT_HISTORY_LIMIT = int(os.getenv("ASSISTANT_HISTORY_LIMIT", "100"))
# Bounded retrieval: maximum number of findings/correlations/groups cited in
# one answer (the pipeline's own caps still apply to timeline and graph).
ASSISTANT_TOP_N = int(os.getenv("ASSISTANT_TOP_N", "10"))


def ensure_directories() -> None:
    """Create runtime directories that are git-ignored."""
    EVIDENCE_STORE_DIR.mkdir(parents=True, exist_ok=True)
    (BASE_DIR / "data").mkdir(parents=True, exist_ok=True)
    (BASE_DIR / "ml_artifacts").mkdir(parents=True, exist_ok=True)
