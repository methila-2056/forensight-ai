"""Raw evidence store selection.

One factory, chosen by :data:`app.config.EVIDENCE_STORAGE_BACKEND`, so the
service layer never branches on where the bytes live:

* ``local``    — :class:`~app.storage.raw_store.RawEvidenceStore`, write-once
  files under ``EVIDENCE_STORE_DIR``. The original design, used for local
  development and for hosts with a persistent volume.
* ``database`` — :class:`~app.storage.db_store.DatabaseEvidenceStore`, raw
  bytes in a ``BYTEA`` column. Required on a host whose filesystem is
  ephemeral (Render's free tier cannot mount a disk), where the file store
  would silently lose evidence.

Both implementations expose the same surface: ``store_once``, ``read_bytes``,
``verify_hash`` and ``root``.
"""

from __future__ import annotations

from typing import Protocol, Union

from sqlalchemy.orm import Session

from app import config
from app.storage.db_store import DatabaseEvidenceStore
from app.storage.raw_store import RawEvidenceStore

EvidenceStore = Union[RawEvidenceStore, DatabaseEvidenceStore]


class EvidenceStoreProtocol(Protocol):
    """The write-once surface both backends implement."""

    @property
    def root(self): ...

    def store_once(
        self, case_id: str, evidence_id: str, original_filename: str, data: bytes
    ): ...

    def read_bytes(self, case_id: str, evidence_id: str) -> bytes: ...

    def verify_hash(self, case_id: str, evidence_id: str, expected_sha256: str): ...


def get_evidence_store(db: Session) -> EvidenceStore:
    """Return the store selected by configuration.

    ``db`` is required by the database backend and ignored by the file
    backend, so callers pass it unconditionally rather than branching.
    """
    if config.EVIDENCE_STORAGE_BACKEND == "database":
        return DatabaseEvidenceStore(db)
    return RawEvidenceStore(config.EVIDENCE_STORE_DIR)