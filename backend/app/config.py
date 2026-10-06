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

# ML reproducibility (Architecture v1.1): one deterministic threshold strategy.
ANOMALY_THRESHOLD = float(os.getenv("ANOMALY_THRESHOLD", "0.72"))
RANDOM_STATE = int(os.getenv("RANDOM_STATE", "42"))

CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173"
    ).split(",")
    if origin.strip()
]


def ensure_directories() -> None:
    """Create runtime directories that are git-ignored."""
    EVIDENCE_STORE_DIR.mkdir(parents=True, exist_ok=True)
    (BASE_DIR / "data").mkdir(parents=True, exist_ok=True)
    (BASE_DIR / "ml_artifacts").mkdir(parents=True, exist_ok=True)
