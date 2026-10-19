"""Database-backed raw evidence store (deployment portability).

Same contract as :mod:`app.storage.raw_store`, but the raw bytes live in a
``BYTEA`` column instead of a file on disk. This exists for one reason: a
free-tier container has an ephemeral filesystem, so the default file-backed
store would lose every uploaded file the moment the container was recycled.

Design rules are inherited unchanged from Architecture §7 / §8:

* Raw evidence bytes are written EXACTLY ONCE at ingest.
* The application never rewrites, normalizes in place, truncates, or
  overwrites anything.
* This class deliberately exposes NO overwrite or truncate operation.

Write-once is enforced by the database rather than by the filesystem's
exclusive ``"xb"`` open mode: the insert is attempted inside a savepoint and
a uniqueness violation is translated into the same
:class:`RawEvidenceExistsError` the file store raises. Because the row lives
in the same transaction as the rest of the ingest, a failed ingest can no
longer leave an orphaned blob behind — which is strictly better than the file
store, where a rolled-back upload would leave the bytes on disk forever.

Hashing is byte-identical to the file store: SHA-256 over the stored content,
compared against the reference hash recorded at ingest.
"""

from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import config
from app.models import EvidenceBlob
from app.storage.raw_store import (
    IntegrityVerification,
    RawEvidenceExistsError,
    RawEvidenceNotFoundError,
    RawEvidenceStoreError,
    StoredEvidence,
    sha256_bytes,
)
from app.terminology import INTEGRITY_MISMATCH, INTEGRITY_VERIFIED

_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _sanitize(value: str, fallback: str) -> str:
    cleaned = _SAFE_RE.sub("_", value).strip("._")
    return cleaned or fallback


class DatabaseEvidenceStore:
    """Immutable-by-intent evidence store backed by the database."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def root(self) -> Path:
        """Logical location, for parity with the file store's ``root``.

        Returned so callers and tests that treat the store uniformly keep
        working. It is *not* a real filesystem path — nothing is written here.
        """
        return Path("postgres://evidence_store")

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
        """Persist raw bytes exactly once. Raises if already stored."""
        if len(data) > config.MAX_EVIDENCE_BLOB_BYTES:
            raise RawEvidenceStoreError(
                f"Evidence exceeds the database blob limit of "
                f"{config.MAX_EVIDENCE_BLOB_BYTES} bytes"
            )

        suffix = Path(original_filename).suffix.lower()
        if suffix and not re.fullmatch(r"\.[A-Za-z0-9]{1,10}", suffix):
            suffix = ""
        stored_filename = f"{_sanitize(evidence_id, 'EV')}{suffix}"

        existing = (
            self._session.query(EvidenceBlob)
            .filter_by(evidence_ref=_sanitize(evidence_id, "EV"))
            .one_or_none()
        )
        if existing is not None:
            raise RawEvidenceExistsError(
                f"Raw evidence already stored at write-once location: {stored_filename}"
            )

        blob = EvidenceBlob(
            evidence_ref=_sanitize(evidence_id, "EV"),
            stored_filename=stored_filename,
            content=data,
            sha256=sha256_bytes(data),
            size=len(data),
        )
        # The savepoint keeps a uniqueness violation from poisoning the
        # caller's outer transaction, which would otherwise force a rollback
        # of unrelated work in the same request.
        with self._session.begin_nested():
            self._session.add(blob)
        try:
            self._session.flush()
        except IntegrityError as exc:  # race guard on the unique constraint
            raise RawEvidenceExistsError(str(exc)) from exc

        return StoredEvidence(
            path=self.root / _sanitize(case_id, "CASE") / stored_filename,
            stored_filename=stored_filename,
            sha256=blob.sha256,
            size=blob.size,
        )

    # ------------------------------------------------------------------
    # Read path
    # ------------------------------------------------------------------

    def _get(self, case_id: str, evidence_id: str) -> EvidenceBlob:
        reference = _sanitize(evidence_id, "EV")
        blob = self._session.query(EvidenceBlob).filter_by(evidence_ref=reference).one_or_none()
        if blob is None:
            raise RawEvidenceNotFoundError(
                f"Evidence {evidence_id} not found for case {case_id}"
            )
        return blob

    def read_bytes(self, case_id: str, evidence_id: str) -> bytes:
        """Read the stored raw bytes (read-only; never modifies the row)."""
        blob = self._get(case_id, evidence_id)
        # psycopg/SQLite both hand back ``bytes`` here; ``memoryview`` is
        # normalised defensively because some drivers return a view.
        content = blob.content
        return bytes(content) if content is not None else b""

    # ------------------------------------------------------------------
    # Integrity verification
    # ------------------------------------------------------------------

    def verify_hash(
        self, case_id: str, evidence_id: str, expected_sha256: str
    ) -> IntegrityVerification:
        """Recompute SHA-256 of stored bytes and compare with a recorded hash."""
        blob = self._get(case_id, evidence_id)
        computed = sha256_bytes(self.read_bytes(case_id, evidence_id))
        expected = (expected_sha256 or "").strip().lower()
        result = INTEGRITY_VERIFIED if computed == expected else INTEGRITY_MISMATCH
        return IntegrityVerification(
            result=result, computed_hash=computed, expected_hash=expected
        )

    # Explicitly no overwrite / truncate / replace / delete operations exist.