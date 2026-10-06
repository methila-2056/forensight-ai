"""Upload validation and filename safety (Phase 1, Architecture v1.1 §Security).

Rules enforced here:

* extension allowlist (config.ALLOWED_EXTENSIONS)
* filename sanitisation — basename only, control/path characters removed
  (path traversal cannot survive this function)
* size cap (config.MAX_UPLOAD_BYTES) — enforced by the caller while streaming
* content sniffing per extension: ZIP magic bytes, UTF-8 text check,
  JSON parse check; executable magic bytes always rejected
* empty files rejected
* uploaded bytes are never executed — they are stored as data only
"""

from __future__ import annotations

import json
import mimetypes
from pathlib import PurePosixPath, PureWindowsPath

from app import config
from app.errors import ApiError

_PEEK = 8192
_MAX_NAME = 200

# Explicit MIME map — mimetypes is platform dependent.
_MIME_MAP = {
    "csv": "text/csv",
    "json": "application/json",
    "txt": "text/plain",
    "log": "text/plain",
    "zip": "application/zip",
}

_EXECUTABLE_MAGIC = (
    (b"MZ", "Windows executable"),
    (b"\x7fELF", "ELF executable"),
    (b"\x89PNG", "PNG image"),
    (b"%PDF", "PDF document"),
    (b"\x1f\x8b", "gzip archive"),
)


def sanitize_filename(raw: str) -> str:
    """Return a safe display filename: basename only, no path/control chars."""
    name = (raw or "").replace("\\", "/")
    name = PurePosixPath(name).name            # strip directories (posix)
    name = PureWindowsPath(name).name          # strip directories (windows)
    name = "".join(ch for ch in name if ch.isprintable())
    name = "".join(ch if ch not in '<>:"|?*' else "_" for ch in name)
    name = " ".join(name.split())              # collapse whitespace
    name = name.lstrip(". ")                   # no hidden / dot-relative names
    if len(name) > _MAX_NAME:
        stem, dot, ext = name.rpartition(".")
        if dot and len(ext) <= 10:
            name = stem[: _MAX_NAME - len(ext) - 1] + "." + ext
        else:
            name = name[:_MAX_NAME]
    if not name:
        raise ApiError(400, "INVALID_FILENAME", "Filename is empty after sanitisation.")
    return name


def validate_extension(filename: str) -> str:
    """Return the lowercased extension or raise 415."""
    ext = PurePosixPath(filename.replace("\\", "/")).suffix.lower().lstrip(".")
    if not ext or ext not in config.ALLOWED_EXTENSIONS:
        raise ApiError(
            415,
            "UNSUPPORTED_FILE_TYPE",
            f"File extension not allowed. Supported: {', '.join(sorted(config.ALLOWED_EXTENSIONS))}.",
            detail={"filename": filename},
        )
    return ext


def guess_mime(filename: str) -> str:
    ext = PurePosixPath(filename.replace("\\", "/")).suffix.lower().lstrip(".")
    if ext in _MIME_MAP:
        return _MIME_MAP[ext]
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


def _reject_content(filename: str, reason: str) -> None:
    raise ApiError(
        415,
        "CONTENT_TYPE_MISMATCH",
        f"File content does not match the declared type: {reason}.",
        detail={"filename": filename},
    )


def _looks_like_text(chunk: bytes) -> bool:
    if b"\x00" in chunk:
        return False
    for trim in range(4):
        try:
            chunk[: len(chunk) - trim].decode("utf-8")
            return True
        except UnicodeDecodeError:
            continue
    return False


def validate_content(filename: str, data: bytes, ext: str) -> None:
    """Best-effort content validation. Raises 400/415 on problems."""
    if not data:
        raise ApiError(400, "EMPTY_FILE", "Uploaded file is empty.", detail={"filename": filename})

    head = data[:_PEEK]

    for magic, label in _EXECUTABLE_MAGIC:
        if head.startswith(magic):
            raise ApiError(
                415,
                "CONTENT_TYPE_MISMATCH",
                f"File content appears to be a {label}, which is not accepted as evidence.",
                detail={"filename": filename},
            )

    if ext == "zip":
        if not head.startswith(b"PK"):
            _reject_content(filename, "missing ZIP signature")
        return

    if ext == "json":
        if not _looks_like_text(head):
            _reject_content(filename, "not UTF-8 text")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            _reject_content(filename, "not valid UTF-8")
        try:
            json.loads(text)
            return
        except json.JSONDecodeError:
            pass
        # tolerate JSON-lines files
        lines = [line for line in text.splitlines() if line.strip()]
        try:
            for line in lines:
                json.loads(line)
            if lines:
                return
        except json.JSONDecodeError:
            pass
        _reject_content(filename, "not valid JSON")

    # csv / txt / log
    if not _looks_like_text(head):
        _reject_content(filename, "not UTF-8 text (binary content or null bytes found)")


def validate_evidence_file(raw_filename: str, data: bytes) -> tuple[str, str, str]:
    """Full validation pipeline. Returns (safe_display_name, extension, mime_type)."""
    name = sanitize_filename(raw_filename)
    ext = validate_extension(name)
    validate_content(name, data, ext)
    return name, ext, guess_mime(name)


def within_size_limit(size: int) -> bool:
    return size <= config.MAX_UPLOAD_BYTES
