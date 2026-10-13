"""ZIP container parser (Phase 12).

A forensic ZIP archive holds many evidence members at once, often with
*different* schemas (``authentication.csv`` next to ``network.csv``). Each
member is therefore detected, parsed, and normalized **independently** using the
ordinary CSV/JSON parsers and the normalizer registry; the results are merged
into a single batch whose records carry their own ``pre_normalized`` mapping.

Safety properties (all enforced *before* any member is expanded):

* **Path traversal** — member names are read as data only. Nothing is ever
  written to disk from an archive, and names are reduced to a basename for
  display, so ``../../etc/passwd`` cannot escape anywhere.
* **Zip bombs** — member count, per-member size, aggregate uncompressed size,
  and compression ratio are all bounded by config. A member whose declared
  expansion exceeds its allowance is rejected with a reason rather than read.
* **No recursion** — nested archives are skipped, which removes the
  zip-inside-zip amplification vector entirely.
* **Symlinks** — entries flagged as symlinks are skipped.
* **Encrypted members** — skipped, since they cannot be read.
* **Never executed** — member bytes are decoded as text data only, exactly as
  for a directly uploaded CSV or JSON file.
"""

from __future__ import annotations

import posixpath
import zipfile
from dataclasses import dataclass, field
from io import BytesIO

from app import config
from app.engines.parsing.base import (
    EvidenceParser,
    NormalizationOutcome,
    ParseBatch,
    ParsedRecord,
    UnknownFormatError,
    safe_record_repr,
)
from app.engines.parsing.csv_parser import CsvParser, decode_text
from app.engines.parsing.json_parser import JsonParser, looks_like_json
from app.engines.parsing.normalizer import canonicalize, select_normalizer

_CSV_EXTENSIONS = {".csv", ".txt", ".log"}
_MEMBER_EXTENSIONS = {".csv", ".json", ".txt", ".log"}
_CONTAINER_EXTENSIONS = {".zip"}
# Members larger than this are only summarised in warnings, never expanded.
_MAX_PREVIEW_MEMBERS = 20


class ZipSecurityError(UnknownFormatError):
    """The archive violates a decompression or safety bound."""


@dataclass
class MemberReport:
    """Per-member outcome, surfaced in run warnings for investigator review."""

    path: str
    status: str  # ok | skipped | failed
    detail: str = ""
    records: int = 0
    parser: str = ""


@dataclass
class ZipParseResult:
    batch: ParseBatch
    warnings: list[str] = field(default_factory=list)
    members: list[MemberReport] = field(default_factory=list)


# Tokens used to infer a member's source type from its filename. A forensic
# archive normally names members after their source, and that hint resolves
# genuine scoring ties between normalizers (e.g. an authentication-shaped CSV
# and a file_activity-shaped CSV score identically when columns overlap).
_FILENAME_HINTS = (
    ("auth", "authentication"),
    ("file_activity", "file_activity"),
    ("file", "file_activity"),
    ("proc", "process"),
    ("process", "process"),
    ("net", "network"),
    ("network", "network"),
    ("browser", "browser"),
    ("system", "system"),
    ("log", "system"),
)


def _hint_from_filename(display: str) -> str | None:
    stem = posixpath.splitext(posixpath.basename(display).lower())[0]
    for token, source_type in _FILENAME_HINTS:
        if token in stem:
            return source_type
    return None


def _member_kind(name: str) -> str:
    lowered = name.lower()
    if lowered.endswith(tuple(_CONTAINER_EXTENSIONS)):
        return "container"
    if lowered.endswith(tuple(_MEMBER_EXTENSIONS)):
        return "record"
    return "other"


def _safe_display(path: str) -> str:
    """Reduce an archive member name to a safe, relative display label.

    The name is never used to touch the filesystem — this is display and
    provenance metadata only.
    """
    normalized = posixpath.normpath(path.replace("\\", "/"))
    parts = [p for p in normalized.split("/") if p not in ("", ".", "..")]
    return "/".join(parts) or "unnamed"


class ZipEvidenceParser(EvidenceParser):
    """Expands a ZIP archive into one merged, per-member normalized batch."""

    name = "zip"

    def parse(self, data: bytes) -> ParseBatch:
        return self.parse_with_report(data).batch

    def parse_with_report(self, data: bytes) -> ZipParseResult:
        result = self._expand(data)
        return result

    # -- internals ---------------------------------------------------------

    def _expand(self, data: bytes) -> ZipParseResult:
        try:
            archive = zipfile.ZipFile(BytesIO(data))
        except zipfile.BadZipFile as exc:
            raise UnknownFormatError(
                f"not a readable ZIP archive: {exc}",
                hints=[
                    "a ZIP upload must be a valid archive produced by a "
                    "standard archiver",
                    "plain CSV and JSON files are also accepted directly",
                ],
            ) from exc

        warnings: list[str] = []
        members: list[MemberReport] = []
        records: list[ParsedRecord] = []
        columns: list[str] = []

        with archive:
            infos = archive.infolist()
            if len(infos) > config.ZIP_MAX_MEMBERS:
                raise ZipSecurityError(
                    "archive contains more members than the configured limit",
                    hints=[
                        f"members: {len(infos)}, limit: {config.ZIP_MAX_MEMBERS}",
                        "split the archive into smaller uploads",
                    ],
                )

            total_declared = sum(i.file_size for i in infos)
            if total_declared > config.ZIP_MAX_TOTAL_UNCOMPRESSED_BYTES:
                raise ZipSecurityError(
                    "archive expands beyond the configured total size limit",
                    hints=[
                        f"declared uncompressed total: {total_declared} bytes, "
                        f"limit: {config.ZIP_MAX_TOTAL_UNCOMPRESSED_BYTES} bytes",
                    ],
                )

            row_counter = 0
            expanded_total = 0

            for info in sorted(infos, key=lambda i: i.filename):
                display = _safe_display(info.filename)

                if info.is_dir():
                    continue
                if self._is_symlink(info):
                    members.append(MemberReport(display, "skipped", "symlink entry"))
                    warnings.append(f"member {display}: symlink entry skipped")
                    continue
                if info.flag_bits & 0x1:
                    members.append(MemberReport(display, "skipped", "encrypted entry"))
                    warnings.append(f"member {display}: encrypted entry skipped")
                    continue

                kind = _member_kind(display)
                if kind == "container":
                    members.append(
                        MemberReport(display, "skipped", "nested archive not expanded")
                    )
                    warnings.append(f"member {display}: nested archive not expanded")
                    continue
                if kind == "other":
                    detail = (
                        "unsupported member type "
                        f"(allowed: {', '.join(sorted(_MEMBER_EXTENSIONS))})"
                    )
                    members.append(MemberReport(display, "skipped", detail))
                    warnings.append(f"member {display}: {detail}")
                    # Nothing is silently discarded: the member is retained as a
                    # rejected record so the run explains why it was not read.
                    row_counter += 1
                    records.append(
                        ParsedRecord(
                            row_index=row_counter,
                            raw="",
                            parse_error=detail,
                            member_path=display,
                        )
                    )
                    continue

                reason = self._reject_reason(info)
                if reason:
                    members.append(MemberReport(display, "skipped", reason))
                    warnings.append(f"member {display}: {reason}")
                    row_counter += 1
                    records.append(
                        ParsedRecord(
                            row_index=row_counter,
                            raw="",
                            parse_error=reason,
                            member_path=display,
                        )
                    )
                    continue

                expanded_total += info.file_size
                if expanded_total > config.ZIP_MAX_TOTAL_UNCOMPRESSED_BYTES:
                    members.append(
                        MemberReport(display, "skipped", "aggregate expansion limit reached")
                    )
                    warnings.append(
                        "archive expansion limit reached; remaining members were "
                        "not read (this run is Partial)"
                    )
                    break

                try:
                    payload = archive.read(info)
                except (RuntimeError, zipfile.BadZipFile, OSError) as exc:
                    # RuntimeError covers the "password required" case.
                    detail = f"unreadable member: {type(exc).__name__}"
                    members.append(MemberReport(display, "failed", detail))
                    warnings.append(f"member {display}: {detail}")
                    continue

                row_counter, member_columns = self._consume_member(
                    display, payload, row_counter, records
                )
                for column in member_columns:
                    if column not in columns:
                        columns.append(column)
                members.append(
                    MemberReport(
                        display,
                        "ok",
                        records=len(records),
                    )
                )

        if not records and not members:
            warnings.append("archive contains no readable evidence members")

        batch = ParseBatch(records=records, warnings=[], columns=columns)
        return ZipParseResult(batch=batch, warnings=warnings, members=members)

    @staticmethod
    def _is_symlink(info: zipfile.ZipInfo) -> bool:
        # High 16 bits of external_attr hold the unix mode when present.
        return (info.external_attr >> 16) & 0o170000 == 0o120000

    @staticmethod
    def _reject_reason(info: zipfile.ZipInfo) -> str | None:
        limit = config.ZIP_MAX_MEMBER_UNCOMPRESSED_BYTES
        if info.file_size > limit:
            return f"member exceeds per-member size limit ({info.file_size} > {limit})"

        if info.compress_size > 0:
            ratio = info.file_size / info.compress_size
            if ratio > config.ZIP_MAX_COMPRESSION_RATIO:
                return (
                    "member compression ratio "
                    f"{ratio:.0f}:1 exceeds the limit "
                    f"{config.ZIP_MAX_COMPRESSION_RATIO:.0f}:1"
                )
        return None

    def _consume_member(
        self,
        display: str,
        payload: bytes,
        row_counter: int,
        records: list[ParsedRecord],
    ) -> tuple[int, list[str]]:
        """Parse and normalize one member, appending merged records."""
        # Reuse the ordinary detection rules, then run the member's own
        # normalizer so differently-shaped members coexist in one archive.
        try:
            sample = decode_text(payload[:65_536], warnings=[])
        except Exception:  # pragma: no cover - decode_text is tolerant
            sample = ""
        suffix = posixpath.splitext(display)[1].lower()
        first_line = sample.splitlines()[0] if sample else ""

        if looks_like_json(sample):
            parser = JsonParser()
        elif suffix in _CSV_EXTENSIONS or "," in first_line:
            parser = CsvParser()
        else:
            # Unrecognised member: retained as a rejected record so nothing is
            # silently discarded.
            row_counter += 1
            records.append(
                ParsedRecord(
                    row_index=row_counter,
                    raw=cap_preview(payload),
                    parse_error="member format not recognised (expected CSV or JSON)",
                    member_path=display,
                )
            )
            return row_counter, []

        try:
            sub = parser.parse(payload)
        except Exception as exc:  # pragma: no cover - defensive
            row_counter += 1
            records.append(
                ParsedRecord(
                    row_index=row_counter,
                    raw=cap_preview(payload),
                    parse_error=f"member could not be parsed: {type(exc).__name__}",
                    member_path=display,
                )
            )
            return row_counter, []

        if not sub.columns:
            row_counter += 1
            records.append(
                ParsedRecord(
                    row_index=row_counter,
                    raw=cap_preview(payload),
                    parse_error="member header could not be read",
                    member_path=display,
                )
            )
            return row_counter, []

        normalizer = select_normalizer(
            set(canonicalize({name: "" for name in sub.columns})),
            _hint_from_filename(display),
        )

        for sub_record in sub.records:
            row_counter += 1
            if sub_record.parse_error:
                records.append(
                    ParsedRecord(
                        row_index=row_counter,
                        raw=sub_record.raw,
                        parse_error=sub_record.parse_error,
                        member_path=display,
                    )
                )
                continue
            outcome: NormalizationOutcome = normalizer.normalize(
                sub_record.fields, sub_record.row_index
            )
            # Preserve which member the row came from, for traceability.
            outcome.metadata["member_path"] = display
            outcome.metadata["member_parser"] = f"{parser.name}/{normalizer.name}"
            records.append(
                ParsedRecord(
                    row_index=row_counter,
                    fields=sub_record.fields,
                    raw=sub_record.raw,
                    pre_normalized=outcome,
                    member_path=display,
                )
            )

        return row_counter, sub.columns


def cap_preview(payload: bytes, limit: int = 512) -> str:
    text, _ = decode_text(payload[:limit * 4], warnings=[])
    return safe_record_repr(text[:limit])


__all__ = ["ZipEvidenceParser", "ZipSecurityError", "MemberReport", "ZipParseResult"]