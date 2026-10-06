import type { CaseStatus, EvidenceStatus, ProcessingStatus, Severity, SourceType } from "../types/models";

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
