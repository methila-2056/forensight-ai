import type {
  CaseStatus,
  EvidenceStatus,
  FindingKind,
  FindingStatus,
  ProcessingStatus,
  Severity,
  SourceType,
  TimelineSignificance,
} from "../types/models";

const SEVERITY_TONES: Record<Severity, string> = {
  Low: "border-slate-600 text-slate-400",
  Medium: "border-sky-700 text-sky-400",
  High: "border-amber-700 text-amber-400",
  Critical: "border-red-700 text-red-400",
};

export function SeverityBadge({ severity }: { severity: Severity }): JSX.Element {
  return (
    <span
      className={`inline-block border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider ${SEVERITY_TONES[severity]}`}
    >
      {severity}
    </span>
  );
}

const STATUS_TONES: Record<CaseStatus, string> = {
  Draft: "border-slate-600 text-slate-400",
  Active: "border-emerald-700 text-emerald-400",
  "Under Review": "border-amber-700 text-amber-400",
  Closed: "border-slate-700 text-slate-500",
};

export function CaseStatusBadge({ status }: { status: CaseStatus }): JSX.Element {
  return (
    <span
      className={`inline-block border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider ${STATUS_TONES[status]}`}
    >
      {status}
    </span>
  );
}

const EVIDENCE_STATUS_TONES: Record<EvidenceStatus, string> = {
  Uploaded: "border-slate-600 text-slate-400",
  Verified: "border-emerald-700 text-emerald-400",
  Processing: "border-sky-700 text-sky-400",
  Processed: "border-sky-700 text-sky-400",
  Analyzed: "border-cyan-700 text-cyan-400",
  Error: "border-red-700 text-red-400",
};

export function EvidenceStatusBadge({ status }: { status: EvidenceStatus }): JSX.Element {
  return (
    <span
      className={`inline-block border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider ${EVIDENCE_STATUS_TONES[status]}`}
    >
      {status}
    </span>
  );
}

/** INTEGRITY VERIFIED (green) / INTEGRITY MISMATCH (red) */
export function IntegrityResultBadge({ result }: { result: string }): JSX.Element {
  const verified = result.includes("VERIFIED");
  return (
    <span
      className={`inline-block border px-2 py-1 font-mono text-xs font-bold uppercase tracking-wider ${
        verified ? "border-emerald-600 bg-emerald-950/60 text-emerald-400" : "border-red-600 bg-red-950/60 text-red-400"
      }`}
    >
      {result}
    </span>
  );
}

const PROCESSING_TONES: Record<string, string> = {
  Pending: "border-slate-600 text-slate-400",
  Processing: "border-sky-700 text-sky-400",
  Completed: "border-emerald-700 text-emerald-400",
  Partial: "border-amber-700 text-amber-400",
  Failed: "border-red-700 text-red-400",
};

export function ProcessingStatusBadge({ status }: { status: ProcessingStatus | string }): JSX.Element {
  return (
    <span
      className={`inline-block border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider ${
        PROCESSING_TONES[status] ?? "border-slate-700 text-slate-400"
      }`}
    >
      {status}
    </span>
  );
}

export function SourceTypeBadge({ sourceType }: { sourceType: SourceType | string }): JSX.Element {
  return (
    <span className="inline-block border border-slate-700 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-slate-400">
      {sourceType}
    </span>
  );
}

const FINDING_STATUS_TONES: Record<FindingStatus, string> = {
  New: "border-sky-700 text-sky-400",
  "Under Review": "border-amber-700 text-amber-400",
  Confirmed: "border-emerald-700 text-emerald-400",
  Dismissed: "border-slate-600 text-slate-500",
};

export function FindingStatusBadge({ status }: { status: FindingStatus | string }): JSX.Element {
  const tone =
    FINDING_STATUS_TONES[status as FindingStatus] ?? "border-slate-600 text-slate-400";
  return (
    <span
      className={`inline-block border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider ${tone}`}
    >
      {status}
    </span>
  );
}

export function FindingKindBadge({ kind }: { kind: FindingKind }): JSX.Element {
  return (
    <span
      className={`inline-block border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider ${
        kind === "rule" ? "border-cyan-800 text-cyan-400" : "border-violet-800 text-violet-400"
      }`}
    >
      {kind === "rule" ? "Rule" : "ML"}
    </span>
  );
}

/** CSS band tone: highest band reads hottest. */
export function SuspicionBandBadge({ band, score }: { band: string; score?: number | null }): JSX.Element {
  const tone = band.startsWith("Potentially")
    ? "border-red-700 text-red-400"
    : band.startsWith("Anomalous")
      ? "border-amber-700 text-amber-400"
      : band.startsWith("Low interest")
        ? "border-sky-700 text-sky-400"
        : "border-slate-600 text-slate-400";
  return (
    <span
      className={`inline-block border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider ${tone}`}
      title={band}
    >
      {score != null ? `CSS ${score.toFixed(2)} · ${band}` : band}
    </span>
  );
}

const CONFIDENCE_BAND_TONES: Record<string, string> = {
  High: "border-red-700 text-red-400",
  Medium: "border-amber-700 text-amber-400",
  Low: "border-slate-600 text-slate-400",
};

/** Additive correlation confidence band (Phase 4) — not a probability. */
export function ConfidenceBandBadge({
  band,
  confidence,
}: {
  band: string;
  confidence?: number | null;
}): JSX.Element {
  const tone = CONFIDENCE_BAND_TONES[band] ?? "border-slate-600 text-slate-400";
  return (
    <span
      className={`inline-block border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider ${tone}`}
      title={confidence != null ? `confidence ${confidence.toFixed(4)} (additive, not a probability)` : band}
    >
      {confidence != null ? `${band} ${confidence.toFixed(2)}` : band}
    </span>
  );
}

const SIGNIFICANCE_TONES: Record<TimelineSignificance, string> = {
  SUSPICIOUS: "border-red-700 text-red-400",
  NOTABLE: "border-amber-700 text-amber-400",
  NORMAL: "border-slate-600 text-slate-400",
};

/** Timeline entry significance (Phase 4). */
export function SignificanceBadge({
  significance,
}: {
  significance: TimelineSignificance;
}): JSX.Element {
  return (
    <span
      className={`inline-block border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider ${SIGNIFICANCE_TONES[significance]}`}
    >
      {significance}
    </span>
  );
}
