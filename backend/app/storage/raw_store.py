"""Write-once raw evidence store (Phase 0 stub).

Design rules from Architecture §7 / §8:

* Raw evidence bytes are written EXACTLY ONCE at ingest.
* The application never rewrites, normalizes in place, truncates, or
  overwrites anything under the raw evidence root.
* All derived data (parsed records, normalized events) lives outside this
  store, in the database / derived area.
* This class deliberately exposes NO overwrite or truncate operation. The
  only write path uses exclusive creation mode ("xb") and refuses a second
  write to the same location.

Hashing: ``store_once`` computes SHA-256 while writing; ``verify_hash``
recomputes the hash of the stored bytes and compares it against a previously
recorded hash. A match yields ``INTEGRITY VERIFIED``; a difference yields
``INTEGRITY MISMATCH``. Neither result says anything about who created or
collected the file — see terminology.INTEGRITY_DISCLAIMER.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from app.terminology import HASH_ALGORITHM, INTEGRITY_MISMATCH, INTEGRITY_VERIFIED

_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")
_CHUNK = 1024 * 1024


class RawEvidenceStoreError(Exception):
    """Base error for the raw evidence store."""


class RawEvidenceExistsError(RawEvidenceStoreError):
    """Raised when a write-once location already holds evidence."""


class RawEvidenceNotFoundError(RawEvidenceStoreError):
    """Raised when the requested evidence is not present in the store."""


@dataclass(frozen=True)
class StoredEvidence:
    path: Path
    stored_filename: str
    sha256: str
    size: int


@dataclass(frozen=True)
class IntegrityVerification:
    result: str            # terminology.INTEGRITY_VERIFIED | INTEGRITY_MISMATCH
    computed_hash: str
    expected_hash: str

    @property
    def verified(self) -> bool:
        return self.result == INTEGRITY_VERIFIED


def _sanitize(value: str, fallback: str) -> str:
    cleaned = _SAFE_RE.sub("_", value).strip("._")
    return cleaned or fallback


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


class RawEvidenceStore:
    """Immutable-by-intent store for raw evidence files."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()

    @property
    def root(self) -> Path:
        return self._root

    # ------------------------------------------------------------------
    # Write path (exclusive — never overwrites)
    # ------------------------------------------------------------------

    def store_once(
        self,
        case_id: str,
        evidence_id: str,
        original_filename: str,
        data: bytes,
    ) -> StoredEvidence:
        """Write raw bytes exactly once. Raises if the location exists."""
        case_dir = self._root / _sanitize(case_id, "CASE")
        case_dir.mkdir(parents=True, exist_ok=True)

        suffix = Path(original_filename).suffix.lower()
        if suffix and not re.fullmatch(r"\.[A-Za-z0-9]{1,10}", suffix):
            suffix = ""
        stored_filename = f"{_sanitize(evidence_id, 'EV')}{suffix}"
        path = case_dir / stored_filename

        if path.exists():
            raise RawEvidenceExistsError(
                f"Raw evidence already stored at write-once location: {stored_filename}"
            )

        try:
            with path.open("xb") as handle:  # exclusive creation — no overwrite path
                handle.write(data)
        except FileExistsError as exc:  # race guard
            raise RawEvidenceExistsError(str(exc)) from exc

        return StoredEvidence(
            path=path,
            stored_filename=stored_filename,
            sha256=sha256_bytes(data),
            size=len(data),
        )

    # ------------------------------------------------------------------
    # Read path
    # ------------------------------------------------------------------

    def _resolve(self, case_id: str, evidence_id: str) -> Path:
        case_dir = self._root / _sanitize(case_id, "CASE")
        if not case_dir.is_dir():
            raise RawEvidenceNotFoundError(f"No evidence for case {case_id}")
        matches = sorted(p for p in case_dir.iterdir() if p.stem == _sanitize(evidence_id, "EV"))
        if not matches:
            raise RawEvidenceNotFoundError(f"Evidence {evidence_id} not found for case {case_id}")
        if len(matches) > 1:
            raise RawEvidenceStoreError(f"Ambiguous evidence location for {evidence_id}")
        return matches[0]

    def read_bytes(self, case_id: str, evidence_id: str) -> bytes:
        """Read the stored raw bytes (read-only; never modifies the file)."""
        return self._resolve(case_id, evidence_id).read_bytes()

    # ------------------------------------------------------------------
    # Integrity verification
    # ------------------------------------------------------------------

    def verify_hash(self, case_id: str, evidence_id: str, expected_sha256: str) -> IntegrityVerification:
        """Recompute SHA-256 of stored bytes and compare with a recorded hash."""
        computed = sha256_file(self._resolve(case_id, evidence_id))
        expected = (expected_sha256 or "").strip().lower()
        result = INTEGRITY_VERIFIED if computed == expected else INTEGRITY_MISMATCH
        return IntegrityVerification(result=result, computed_hash=computed, expected_hash=expected)

    # Explicitly no overwrite / truncate / replace / delete operations exist.
