import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import ReactFlow, { Background, Controls, MarkerType } from "reactflow";
import type { Edge, Node } from "reactflow";
import "reactflow/dist/style.css";
import { askAssistant } from "../api/assistant";
import { ApiError } from "../api/client";
import { reviewFinding } from "../api/analysis";
import { generateReport } from "../api/reports";
import { fetchWorkspace } from "../api/workspace";
import {
  FindingKindBadge,
  FindingStatusBadge,
  EvidenceStatusBadge,
  SeverityBadge,
  SignificanceBadge,
  SourceTypeBadge,
} from "../components/Badges";
import ErrorBox from "../components/ErrorBox";
import { formatBytes, formatDateTime } from "../state/format";
import type {
  AssistantQueryResult,
  CorrelationSummary,
  FindingStatus,
  GraphNode as GraphNodeData,
  GroupSummary,
  TimelineEntry,
  TimelineSignificance,
  WorkspaceEvidenceItem,
  WorkspaceFindingItem,
  WorkspaceResponse,
} from "../types/models";
import { ALLOWED_STATUS_TRANSITIONS, TIMELINE_SIGNIFICANCE_OPTIONS } from "../types/models";
import {
  INTEGRITY_LATEST_MISMATCH,
  INTEGRITY_LATEST_VERIFIED,
  INTEGRITY_PARTIAL,
  INTEGRITY_UNVERIFIED,
  PROCESSING_COMPLETED,
  PROCESSING_FAILED,
  PROCESSING_IN_PROGRESS,
  PROCESSING_NOT_PROCESSED,
  PROCESSING_PARTIAL,
  WORKSPACE_DISCLAIMER,
  WORKSPACE_LABEL,
  WORKSPACE_NOTE,
} from "../types/terminology";

const labelClass = "font-mono text-[10px] uppercase tracking-widest text-slate-500";
const fieldClass =
  "w-full border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-cyan-600 focus:outline-none";

const TAB_ITEMS = [
  { id: "overview", label: "Overview" },
  { id: "evidence", label: "Evidence" },
  { id: "review", label: "Findings + review" },
  { id: "timeline", label: "Timeline" },
  { id: "correlations", label: "Correlations" },
  { id: "groups", label: "Activity groups" },
  { id: "graph", label: "Graph" },
  { id: "assistant", label: "Assistant" },
  { id: "reports", label: "Reports" },
] as const;

type TabId = (typeof TAB_ITEMS)[number]["id"];

const truncate = (text: string, max: number): string =>
  text.length > max ? `${text.slice(0, max)}…` : text;

const NODE_STYLE: Record<GraphNodeData["type"], string> = {
  evidence: "border border-slate-600 bg-slate-900 text-slate-200",
  finding: "border border-amber-700 bg-amber-950/60 text-amber-200",
  event: "border border-cyan-800 bg-slate-900 text-cyan-100",
};

const EVENT_ACCENT: Record<string, string> = {
  SUSPICIOUS: "border-red-700",
  NOTABLE: "border-amber-700",
};

function ProcessingLabelBadge({ label }: { label: string }): JSX.Element {
  const tone =
    label === PROCESSING_COMPLETED
      ? "border-emerald-700 text-emerald-400"
      : label === PROCESSING_FAILED
        ? "border-red-700 text-red-400"
        : label === PROCESSING_PARTIAL
          ? "border-amber-700 text-amber-400"
          : label === PROCESSING_IN_PROGRESS
            ? "border-sky-700 text-sky-400"
            : "border-slate-600 text-slate-400";
  return (
    <span
      className={`inline-block border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider ${tone}`}
    >
      {label === PROCESSING_NOT_PROCESSED ? "Not processed" : label}
    </span>
  );
}

function IntegrityLabelBadge({ label }: { label: string }): JSX.Element {
  const tone =
    label === INTEGRITY_LATEST_VERIFIED
      ? "border-emerald-700 text-emerald-400"
      : label === INTEGRITY_LATEST_MISMATCH
        ? "border-red-700 text-red-400"
        : label === INTEGRITY_PARTIAL
          ? "border-amber-700 text-amber-400"
          : "border-slate-600 text-slate-400";
  return (
    <span className={`inline-block border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider ${tone}`}>
      {label === INTEGRITY_UNVERIFIED ? "Unverified" : label}
    </span>
  );
}

function Kpi({
  label,
  value,
  tone = "text-white",
}: {
  label: string;
  value: string | number;
  tone?: string;
}): JSX.Element {
  return (
    <div className="border border-slate-800 bg-slate-900/50 px-4 py-3">
      <p className="font-mono text-[10px] uppercase tracking-widest text-slate-500">{label}</p>
      <p className={`mt-1 font-mono text-xl ${tone}`}>{value}</p>
    </div>
  );
}

function reviewTransitions(status: string): FindingStatus[] {
  return ALLOWED_STATUS_TRANSITIONS[status as FindingStatus] ?? [];
}

function FindingRow({
  caseId,
  finding,
  onSaved,
  onScrollTarget,
}: {
  caseId: string;
  finding: WorkspaceFindingItem;
  onSaved: () => Promise<void>;
  onScrollTarget: (el: HTMLDivElement | null) => void;
}): JSX.Element {
  const [statusDraft, setStatusDraft] = useState<FindingStatus>(finding.status);
  const [note, setNote] = useState("");
  const [author, setAuthor] = useState("investigator");
  const [busy, setBusy] = useState(false);
  const [rowError, setRowError] = useState<string | null>(null);
  const transitions = reviewTransitions(finding.status);

  const save = async (event: React.FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    setBusy(true);
    setRowError(null);
    try {
      await reviewFinding(caseId, finding.finding_id, {
        status: statusDraft,
        note: note.trim() || undefined,
        author: author.trim() || "investigator",
      });
      setNote("");
      await onSaved();
    } catch (err: unknown) {
      setRowError(err instanceof ApiError ? err.message : "Review update failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div ref={onScrollTarget} className="border-b border-slate-900 px-4 py-3">
      <div className="flex flex-wrap items-center gap-3">
        <Link
          to={`/cases/${caseId}/findings/${encodeURIComponent(finding.finding_id)}`}
          className="font-mono text-xs text-cyan-400 hover:underline"
        >
          {finding.finding_id}
        </Link>
        <FindingKindBadge kind={finding.kind} />
        <SeverityBadge severity={finding.severity} />
        <FindingStatusBadge status={finding.status} />
      </div>
      <p className="mt-2 text-sm text-white">{finding.title}</p>
      {finding.reasons && finding.reasons.length > 0 && (
        <ul className="mt-1 list-disc pl-5 text-xs text-slate-400">
          {finding.reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      )}
      <form onSubmit={(event) => void save(event)} className="mt-3 grid gap-3 border border-slate-800 bg-slate-950/50 p-3 md:grid-cols-4">
        <div>
          <label className={labelClass} htmlFor={`rev-status-${finding.finding_id}`}>
            New status
          </label>
          <select
            id={`rev-status-${finding.finding_id}`}
            className={`${fieldClass} mt-1`}
            value={statusDraft}
            onChange={(event) => setStatusDraft(event.target.value as FindingStatus)}
            disabled={transitions.length === 0}
          >
            <option value={finding.status}>{finding.status} (current)</option>
            {transitions.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className={labelClass} htmlFor={`rev-author-${finding.finding_id}`}>
            Investigator
          </label>
          <input
            id={`rev-author-${finding.finding_id}`}
            className={`${fieldClass} mt-1`}
            value={author}
            onChange={(event) => setAuthor(event.target.value)}
          />
        </div>
        <div>
          <label className={labelClass} htmlFor={`rev-note-${finding.finding_id}`}>
            Note
          </label>
          <input
            id={`rev-note-${finding.finding_id}`}
            className={`${fieldClass} mt-1`}
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="Why this transition…"
          />
        </div>
        <div className="flex items-end">
          <button
            type="submit"
            disabled={busy || statusDraft === finding.status || transitions.length === 0}
            className="w-full border border-cyan-700 bg-cyan-950/60 px-4 py-2 font-mono text-xs uppercase tracking-widest text-cyan-300 hover:bg-cyan-900/60 disabled:opacity-50"
          >
            {busy ? "Saving…" : "Record review"}
          </button>
        </div>
        {rowError && (
          <p className="md:col-span-4 font-mono text-xs text-red-400">{rowError}</p>
        )}
      </form>
    </div>
  );
}

export default function InvestigationWorkspacePage(): JSX.Element {
  const { caseId = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();

  const tabRaw = searchParams.get("tab") ?? "overview";
  const tab = (TAB_ITEMS.some((item) => item.id === tabRaw) ? tabRaw : "overview") as TabId;
  const deepFinding = searchParams.get("finding") ?? "";
  const deepEvidence = searchParams.get("evidence") ?? "";
  const deepEvent = searchParams.get("event") ?? "";

  const [data, setData] = useState<WorkspaceResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const [significanceFilter, setSignificanceFilter] = useState<"" | TimelineSignificance>("");

  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);

  const [reportTitle, setReportTitle] = useState("");
  const [generating, setGenerating] = useState(false);

  const loadWorkspace = useCallback((): Promise<void> => {
    return fetchWorkspace(caseId)
      .then(setData)
      .catch((err: unknown) =>
        setError(err instanceof ApiError ? err.message : "Failed to load the workspace."),
      );
  }, [caseId]);

  useEffect(() => {
    void loadWorkspace();
  }, [loadWorkspace]);

  const scrollToId = useCallback((id: string): void => {
    window.setTimeout(() => {
      const el = document.getElementById(`anchor-${id}`);
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 50);
  }, []);

  useEffect(() => {
    if (!data) return;
    if (deepFinding && tab === "review") scrollToId(deepFinding);
    if (deepEvidence && tab === "evidence") scrollToId(deepEvidence);
    if (deepEvent && tab === "timeline") scrollToId(deepEvent);
  }, [data, tab, deepFinding, deepEvidence, deepEvent, scrollToId]);

  const setTab = (next: TabId): void => {
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set("tab", next);
    setSearchParams(nextParams);
  };

  const setAnchor = (key: string, value: string): void => {
    const nextParams = new URLSearchParams(searchParams);
    if (value) nextParams.set(key, value);
    else nextParams.delete(key);
    setSearchParams(nextParams);
  };

  const afterWrite = async (): Promise<void> => {
    await loadWorkspace();
    setNotice(null);
  };

  const ask = async (text?: string): Promise<void> => {
    const trimmed = (text ?? question).trim();
    if (!trimmed) {
      setActionError("Type a question first.");
      return;
    }
    setAsking(true);
    setActionError(null);
    try {
      await askAssistant(caseId, trimmed, "ui");
      setQuestion("");
      await loadWorkspace();
    } catch (err: unknown) {
      setActionError(err instanceof ApiError ? err.message : "The assistant could not answer the question.");
    } finally {
      setAsking(false);
    }
  };

  const generate = async (): Promise<void> => {
    setGenerating(true);
    setActionError(null);
    try {
      await generateReport(caseId, {
        title: reportTitle.trim() || undefined,
        actor: "ui",
      });
      setReportTitle("");
      setNotice("Report snapshot generated from the persisted case data.");
      await loadWorkspace();
    } catch (err: unknown) {
      setActionError(
        err instanceof ApiError ? err.message : "Report generation failed.",
      );
    } finally {
      setGenerating(false);
    }
  };

  if (error) {
    return <ErrorBox message={error} />;
  }
  if (!data) {
    return (
      <p className="font-mono text-xs uppercase tracking-widest text-slate-500">
        Loading workspace…
      </p>
    );
  }

  const { case: wsCase } = data;

  const evidenceRows = data.evidence;
  const findingRows = data.review_summary.queue;
  const timelineEntries = data.timeline_summary.entries;
  const filteredTimeline = significanceFilter
    ? timelineEntries.filter((entry) => entry.significance === significanceFilter)
    : timelineEntries;
  const evidenceAnchor = data.evidence.find(
    (item) => item.evidence_id === deepEvidence,
  );

  const flowNodes = useMemo<Node[]>(() => {
    const graph = data.graph_summary;
    if (!graph || graph.nodes.length === 0) return [];
    const byType: Record<GraphNodeData["type"], GraphNodeData[]> = {
      evidence: [],
      finding: [],
      event: [],
    };
    graph.nodes.forEach((node) => byType[node.type].push(node));
    const xByType = { evidence: 30, finding: 370, event: 710 };
    const nodes: Node[] = [];
    (["evidence", "finding", "event"] as const).forEach((type) => {
      byType[type].forEach((node, index) => {
        const spacing = type === "event" ? 70 : 84;
        nodes.push({
          id: node.id,
          position: { x: xByType[type], y: 30 + index * spacing },
          className: `${NODE_STYLE[node.type]} ${
            node.type === "event" && node.significance
              ? EVENT_ACCENT[node.significance] ?? ""
              : ""
          }`,
          data: {
            label: (
              <span className="block px-2 py-1">
                <span className="block truncate font-mono text-[11px]">
                  {truncate(node.label, 52)}
                </span>
                {node.detail && (
                  <span className="mt-0.5 block truncate font-mono text-[9px] text-slate-500">
                    {truncate(node.detail, 60)}
                  </span>
                )}
              </span>
            ),
          },
          style: { width: 310, borderRadius: 2 },
        });
      });
    });
    return nodes;
  }, [data.graph_summary]);

  const flowEdges = useMemo<Edge[]>(() => {
    const graph = data.graph_summary;
    if (!graph) return [];
    const colors: Record<string, string> = {
      contains: "#475569",
      triggered: "#f59e0b",
      correlated: "#22d3ee",
    };
    return graph.edges.map((edge, index) => ({
      id: `edge-${index}`,
      source: edge.source,
      target: edge.target,
      label: edge.label,
      animated: edge.relation === "correlated",
      labelStyle: { fill: "#94a3b8", fontSize: 10, fontFamily: "monospace" },
      labelBgStyle: { fill: "#020617", fillOpacity: 0.85 },
      style: { stroke: colors[edge.relation] ?? "#475569" },
      markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14 },
    }));
  }, [data.graph_summary]);

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="font-mono text-xs uppercase tracking-widest text-cyan-500">{wsCase.case_id}</p>
          <h1 className="mt-1 text-2xl font-bold text-white">{WORKSPACE_LABEL}</h1>
          <p className="mt-1 max-w-3xl text-sm text-slate-400">
            {wsCase.name} · {wsCase.investigator}
            {wsCase.synthetic_label && (
              <span className="ml-2 border border-amber-700 bg-amber-950/40 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-amber-400">
                {wsCase.synthetic_label}
              </span>
            )}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link
            to={`/cases/${caseId}`}
            className="border border-slate-700 px-4 py-2 font-mono text-xs uppercase tracking-widest text-slate-400 hover:text-slate-200"
          >
            ← Case
          </Link>
          <Link
            to={`/cases/${caseId}/findings`}
            className="border border-slate-700 px-4 py-2 font-mono text-xs uppercase tracking-widest text-slate-400 hover:text-slate-200"
          >
            Findings →
          </Link>
        </div>
      </div>

      <p className="max-w-4xl font-mono text-[11px] leading-relaxed text-slate-600">
        {WORKSPACE_NOTE}
      </p>
      <p className="max-w-4xl border border-slate-800 bg-slate-950/50 px-3 py-2 font-mono text-[10px] uppercase tracking-wider text-slate-500">
        {WORKSPACE_DISCLAIMER}
      </p>

      <div className="flex flex-wrap gap-1">
        {TAB_ITEMS.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => setTab(item.id)}
            className={`border px-3 py-1.5 font-mono text-[11px] uppercase tracking-widest ${
              tab === item.id
                ? "border-cyan-700 bg-cyan-950/60 text-cyan-300"
                : "border-slate-800 text-slate-500 hover:text-slate-300"
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      {actionError && <ErrorBox message={actionError} />}
      {notice && (
        <p className="border border-emerald-800 bg-emerald-950/40 px-4 py-2 font-mono text-xs text-emerald-300">
          {notice}
        </p>
      )}

      {tab === "overview" && (
        <div className="space-y-8">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Kpi label="Evidence files" value={wsCase.evidence_count} />
            <Kpi label="Forensic events" value={wsCase.event_count} />
            <Kpi label="Anomalous events" value={wsCase.anomalous_event_count} />
            <Kpi label="Findings" value={wsCase.finding_count} />
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Kpi label="Open review items" value={wsCase.review_open_items} tone={wsCase.review_open_items > 0 ? "text-amber-400" : "text-white"} />
            <Kpi label="Correlations" value={wsCase.correlation_count} />
            <Kpi label="Activity groups" value={wsCase.activity_group_count} />
            <Kpi label="Report snapshots" value={wsCase.report_count} />
          </div>

          <section className="border border-slate-800 bg-slate-900/50 p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">
                Evidence processing rollup
              </h2>
              <ProcessingLabelBadge label={data.processing.label} />
            </div>
            <p className="mt-2 max-w-3xl text-sm text-slate-400">
              {data.processing.runs} run{data.processing.runs === 1 ? "" : "s"} ·{" "}
              {data.processing.evidence_processed} evidence processed ·{" "}
              {data.processing.records_normalized} records normalized ·{" "}
              {data.processing.records_rejected} rejected ·{" "}
              {data.processing.duplicates_detected} duplicates detected
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {Object.entries(data.processing.by_status).map(([status, count]) => (
                <span key={status} className="border border-slate-700 px-2 py-0.5 font-mono text-[10px] uppercase text-slate-400">
                  {status} {count}
                </span>
              ))}
              {data.processing.runs === 0 && (
                <span className="font-mono text-[11px] uppercase text-slate-600">No processing runs yet</span>
              )}
            </div>
          </section>

          <section className="border border-slate-800 bg-slate-900/50 p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">
                Evidence integrity rollup
              </h2>
              <IntegrityLabelBadge label={wsCase.integrity_status} />
            </div>
            <div className="mt-3 grid gap-3 sm:grid-cols-4">
              <Kpi label="SHA-256 checks" value={data.integrity_summary.checks} />
              <Kpi label="Verified" value={data.integrity_summary.verified} tone="text-emerald-400" />
              <Kpi label="Mismatch" value={data.integrity_summary.mismatch} tone={data.integrity_summary.mismatch > 0 ? "text-red-400" : "text-white"} />
              <Kpi label="Latest-verified evidence" value={data.evidence_summary.verified} />
            </div>
            <p className="mt-2 max-w-3xl text-sm text-slate-400">
              Uploading evidence records its hash; verification re-hashes the current bytes. A
              mismatch means the bytes differ from the recorded reference.
            </p>
          </section>

          <section className="border border-slate-800 bg-slate-900/50 p-5">
            <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">
              Finding summary
            </h2>
            <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Kpi label="Total" value={data.finding_summary.total} />
              <Kpi label="High / Critical" value={data.finding_summary.high_severity} tone={data.finding_summary.high_severity > 0 ? "text-amber-400" : "text-white"} />
              <Kpi label="Review queue" value={data.review_summary.open_items} tone={data.review_summary.open_items > 0 ? "text-amber-400" : "text-white"} />
              <Kpi label="Confirmed" value={data.finding_summary.by_status["Confirmed"] ?? 0} tone="text-emerald-400" />
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {Object.entries(data.finding_summary.by_status).map(([status, count]) => (
                <span key={status} className="border border-slate-700 px-2 py-0.5 font-mono text-[10px] uppercase text-slate-400">
                  {status} {count}
                </span>
              ))}
            </div>
            <div className="mt-4">
              <Link
                to={`/cases/${caseId}/workspace?tab=review`}
                className="border border-cyan-700 bg-cyan-950/60 px-4 py-2 font-mono text-xs uppercase tracking-widest text-cyan-300 hover:bg-cyan-900/60"
              >
                Open review queue →
              </Link>
            </div>
          </section>

          <section className="border border-slate-800 bg-slate-900/50 p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">
                Assistant + reports
              </h2>
              <span className="font-mono text-[10px] text-slate-500">
                generated {formatDateTime(data.generated_at)}
              </span>
            </div>
            <p className="mt-2 text-sm text-slate-400">
              {data.assistant_summary.query_count} assistant question
              {data.assistant_summary.query_count === 1 ? "" : "s"} ·{" "}
              {data.report_summary.count} report snapshot
              {data.report_summary.count === 1 ? "" : "s"} persisted for this case.
            </p>
            {data.report_summary.latest && (
              <div className="mt-3 border border-slate-800 bg-slate-950/50 p-3">
                <p className="font-mono text-xs text-cyan-400">{data.report_summary.latest.report_id}</p>
                <p className="mt-1 text-sm text-white">{data.report_summary.latest.title}</p>
                <p className="mt-1 font-mono text-[10px] text-slate-500">
                  {data.report_summary.latest.generated_at
                    ? formatDateTime(data.report_summary.latest.generated_at)
                    : "—"}{" "}
                  · {data.report_summary.latest.generated_by}
                </p>
              </div>
            )}
            {evidenceAnchor && (
              <div className="mt-3 border border-cyan-900 bg-cyan-950/30 p-3">
                <p className="font-mono text-[10px] uppercase tracking-widest text-cyan-400">
                  Deep-linked evidence
                </p>
                <p className="mt-1 font-mono text-xs text-slate-200">
                  {evidenceAnchor.evidence_id} · {evidenceAnchor.original_filename}
                </p>
              </div>
            )}
          </section>
        </div>
      )}

      {tab === "evidence" && (
        <section>
          <div className="flex flex-wrap items-end justify-between gap-3">
            <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">
              Evidence inventory ({evidenceRows.length})
            </h2>
            <p className="font-mono text-[10px] uppercase tracking-wider text-slate-600">
              {data.evidence_summary.processed} processed · {data.evidence_summary.verified} verified ·{" "}
              {data.evidence_summary.mismatch} mismatch · {data.evidence_summary.unverified} unverified
            </p>
          </div>
          {evidenceRows.length === 0 ? (
            <p className="mt-3 border border-dashed border-slate-700 p-6 text-center font-mono text-xs uppercase tracking-wider text-slate-500">
              No evidence in this case yet — upload evidence to begin.
            </p>
          ) : (
            <div className="mt-3 overflow-x-auto">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="border-b border-slate-800 text-left font-mono text-[10px] uppercase tracking-widest text-slate-500">
                    <th className="py-2 pr-4">Evidence</th>
                    <th className="py-2 pr-4">Filename</th>
                    <th className="py-2 pr-4">Type</th>
                    <th className="py-2 pr-4">Size</th>
                    <th className="py-2 pr-4">Status</th>
                    <th className="py-2 pr-4">Latest processing</th>
                    <th className="py-2 pr-4">Integrity</th>
                    <th className="py-2">Events</th>
                  </tr>
                </thead>
                <tbody>
                  {evidenceRows.map((item: WorkspaceEvidenceItem) => (
                    <tr
                      key={item.evidence_id}
                      id={`anchor-${item.evidence_id}`}
                      onClick={() => setAnchor("evidence", item.evidence_id)}
                      className={`cursor-pointer border-b border-slate-900 hover:bg-slate-900/70 ${
                        deepEvidence === item.evidence_id
                          ? "bg-cyan-950/30"
                          : ""
                      }`}
                    >
                      <td className="py-3 pr-4 font-mono text-xs text-cyan-400">{item.evidence_id}</td>
                      <td className="py-3 pr-4 text-white">{item.original_filename}</td>
                      <td className="py-3 pr-4 font-mono text-[11px] uppercase text-slate-400">{item.evidence_type}</td>
                      <td className="py-3 pr-4 font-mono text-xs text-slate-400">{formatBytes(item.file_size)}</td>
                      <td className="py-3 pr-4">
                        <EvidenceStatusBadge status={item.status} />
                      </td>
                      <td className="py-3 pr-4">
                        {item.latest_processing ? (
                          <ProcessingLabelBadge label={item.latest_processing} />
                        ) : (
                          <span className="font-mono text-[10px] uppercase text-slate-600">—</span>
                        )}
                      </td>
                      <td className="py-3 pr-4 font-mono text-[11px] text-slate-400">
                        {item.integrity.latest === "VERIFIED" ? (
                          <span className="text-emerald-400">verified</span>
                        ) : item.integrity.latest === "MISMATCH" ? (
                          <span className="text-red-400">mismatch</span>
                        ) : (
                          <span className="text-slate-600">unverified</span>
                        )}
                        <span className="block text-[10px] text-slate-600">
                          {item.integrity.checks} check{item.integrity.checks === 1 ? "" : "s"}
                        </span>
                      </td>
                      <td className="py-3 font-mono text-xs text-slate-300">{item.event_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {tab === "review" && (
        <section>
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">
                Review queue ({data.review_summary.open_items} open)
              </h2>
              <p className="mt-1 max-w-3xl text-sm text-slate-500">
                The system never confirms or dismisses findings on its own; each transition
                below is an investigator action recorded in the chain of custody. Transitions:
                New → Under Review → Confirmed / Dismissed.
              </p>
            </div>
          </div>
          {findingRows.length === 0 ? (
            <p className="mt-3 border border-dashed border-slate-700 p-6 text-center font-mono text-xs uppercase tracking-wider text-slate-500">
              No open review items — run analysis to create findings, then review them here.
            </p>
          ) : (
            <div className="mt-3 border border-slate-800 bg-slate-900/50">
              {findingRows.map((finding: WorkspaceFindingItem) => (
                <FindingRow
                  key={finding.finding_id}
                  caseId={caseId}
                  finding={finding}
                  onSaved={afterWrite}
                  onScrollTarget={(el) => {
                    if (deepFinding === finding.finding_id) {
                      el?.scrollIntoView({ behavior: "smooth", block: "center" });
                    }
                  }}
                />
              ))}
            </div>
          )}
        </section>
      )}

      {tab === "timeline" && (
        <section>
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">
                Reconstructed investigation timeline ({timelineEntries.length})
              </h2>
              <p className="mt-1 max-w-3xl font-mono text-[11px] leading-relaxed text-slate-600">
                {data.timeline_summary.disclaimer}
              </p>
            </div>
            <div className="w-56">
              <label className={labelClass} htmlFor="w-t-sig">
                Significance
              </label>
              <select
                id="w-t-sig"
                className={`${fieldClass} w-full`}
                value={significanceFilter}
                onChange={(event) =>
                  setSignificanceFilter(event.target.value as "" | TimelineSignificance)
                }
              >
                {TIMELINE_SIGNIFICANCE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
          {data.timeline_summary.note && (
            <p className="mt-3 border border-slate-800 bg-slate-950/60 px-4 py-2 font-mono text-[11px] text-slate-400">
              {data.timeline_summary.note}
            </p>
          )}
          {filteredTimeline.length === 0 ? (
            <p className="mt-3 border border-dashed border-slate-700 p-6 text-center font-mono text-xs uppercase tracking-wider text-slate-500">
              No timeline entries — process evidence, then run analysis and correlation.
            </p>
          ) : (
            <div className="mt-3 max-h-[36rem] overflow-y-auto border border-slate-900">
              <table className="w-full border-collapse text-sm">
                <thead className="sticky top-0 bg-slate-950">
                  <tr className="border-b border-slate-800 text-left font-mono text-[10px] uppercase tracking-widest text-slate-500">
                    <th className="py-2 pr-4">Timestamp</th>
                    <th className="py-2 pr-4">Significance</th>
                    <th className="py-2 pr-4">Event</th>
                    <th className="py-2 pr-4">Source</th>
                    <th className="py-2">Who / what</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredTimeline.map((entry: TimelineEntry) => (
                    <tr
                      key={entry.event_id}
                      id={`anchor-${entry.event_id}`}
                      onClick={() => setAnchor("event", entry.event_id)}
                      className={`cursor-pointer border-b border-slate-900 hover:bg-slate-900/70 ${
                        deepEvent === entry.event_id ? "bg-cyan-950/30" : ""
                      }`}
                    >
                      <td className="py-2 pr-4 font-mono text-xs text-slate-400">
                        {entry.timestamp ? formatDateTime(entry.timestamp) : "—"}
                      </td>
                      <td className="py-2 pr-4">
                        <SignificanceBadge significance={entry.significance} />
                        {entry.context && (
                          <span className="mt-1 block font-mono text-[9px] uppercase text-slate-600">
                            context
                          </span>
                        )}
                      </td>
                      <td className="py-2 pr-4 font-mono text-xs text-cyan-400">
                        {entry.event_id}
                        {entry.finding_ids.length > 0 && (
                          <span className="mt-1 block font-mono text-[9px] text-amber-500">
                            {entry.finding_ids.join(", ")}
                          </span>
                        )}
                      </td>
                      <td className="py-2 pr-4">
                        <SourceTypeBadge sourceType={entry.source_type} />
                      </td>
                      <td className="py-2 font-mono text-[11px] text-slate-400">
                        {[
                          entry.user,
                          entry.host,
                          entry.process,
                          entry.file_path,
                          entry.action,
                        ]
                          .filter(Boolean)
                          .join(" · ") || "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {data.timeline_summary.truncated && (
            <p className="mt-2 font-mono text-[11px] text-amber-500">
              {timelineEntries.length} of {data.timeline_summary.total} entries shown.
            </p>
          )}
        </section>
      )}

      {tab === "correlations" && (
        <section>
          <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">
            Cross-source correlations ({data.correlation_summary.total})
          </h2>
          <p className="mt-1 max-w-3xl font-mono text-[11px] leading-relaxed text-slate-600">
            {data.correlation_summary.disclaimer}
          </p>
          {data.correlation_summary.correlations.length === 0 ? (
            <p className="mt-3 border border-dashed border-slate-700 p-6 text-center font-mono text-xs uppercase tracking-wider text-slate-500">
              No correlations — run correlation to link events across sources.
            </p>
          ) : (
            <div className="mt-3 overflow-x-auto">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="border-b border-slate-800 text-left font-mono text-[10px] uppercase tracking-widest text-slate-500">
                    <th className="py-2 pr-4">Link</th>
                    <th className="py-2 pr-4">Type</th>
                    <th className="py-2 pr-4">Event A</th>
                    <th className="py-2 pr-4">Event B</th>
                    <th className="py-2 pr-4">Confidence</th>
                    <th className="py-2">Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {data.correlation_summary.correlations.map((row: CorrelationSummary) => (
                    <tr key={row.correlation_id} className="border-b border-slate-900 align-top">
                      <td className="py-3 pr-4 font-mono text-xs text-cyan-400">{row.correlation_id}</td>
                      <td className="py-3 pr-4 font-mono text-[11px] text-slate-300">
                        {row.correlation_type}
                      </td>
                      <td className="py-3 pr-4 font-mono text-xs text-slate-400">
                        {row.event_a.event_id}
                        <span className="block text-[10px] text-slate-600">
                          {row.event_a.timestamp ? formatDateTime(row.event_a.timestamp) : "—"}
                        </span>
                      </td>
                      <td className="py-3 pr-4 font-mono text-xs text-slate-400">
                        {row.event_b.event_id}
                        <span className="block text-[10px] text-slate-600">
                          {row.event_b.timestamp ? formatDateTime(row.event_b.timestamp) : "—"}
                        </span>
                      </td>
                      <td className="py-3 pr-4 font-mono text-xs text-slate-300">
                        {row.confidence.toFixed(2)}
                      </td>
                      <td className="py-3 text-xs text-slate-400">{truncate(row.reason, 140)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {tab === "groups" && (
        <section>
          <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">
            Activity groups ({data.group_summary.total})
          </h2>
          <p className="mt-1 max-w-3xl font-mono text-[11px] leading-relaxed text-slate-600">
            {data.group_summary.disclaimer}
          </p>
          {data.group_summary.groups.length === 0 ? (
            <p className="mt-3 border border-dashed border-slate-700 p-6 text-center font-mono text-xs uppercase tracking-wider text-slate-500">
              No activity groups — run correlation to cluster linked events.
            </p>
          ) : (
            <div className="mt-3 overflow-x-auto">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="border-b border-slate-800 text-left font-mono text-[10px] uppercase tracking-widest text-slate-500">
                    <th className="py-2 pr-4">Group</th>
                    <th className="py-2 pr-4">Kind</th>
                    <th className="py-2 pr-4">Title</th>
                    <th className="py-2 pr-4">Severity</th>
                    <th className="py-2 pr-4">Events</th>
                    <th className="py-2">Start</th>
                  </tr>
                </thead>
                <tbody>
                  {data.group_summary.groups.map((group: GroupSummary) => (
                    <tr key={group.group_id} className="border-b border-slate-900 align-top">
                      <td className="py-3 pr-4 font-mono text-xs text-cyan-400">{group.group_id}</td>
                      <td className="py-3 pr-4 font-mono text-[11px] uppercase text-slate-400">{group.kind}</td>
                      <td className="py-3 pr-4 text-white">{group.title}</td>
                      <td className="py-3 pr-4">
                        <SeverityBadge severity={group.severity} />
                      </td>
                      <td className="py-3 pr-4 font-mono text-xs text-slate-300">{group.event_count}</td>
                      <td className="py-3 font-mono text-[11px] text-slate-500">
                        {group.time_start ? formatDateTime(group.time_start) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {tab === "graph" && (
        <section>
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">
                Evidence graph — evidence → findings → events → correlations
              </h2>
              <p className="mt-1 max-w-3xl font-mono text-[11px] leading-relaxed text-slate-600">
                {data.graph_summary.disclaimer}
              </p>
            </div>
            <p className="font-mono text-[10px] uppercase tracking-wider text-slate-600">
              {data.graph_summary.nodes.length}/{data.graph_summary.max_nodes} nodes ·{" "}
              {data.graph_summary.edges.length}/{data.graph_summary.max_edges} edges
            </p>
          </div>
          {data.graph_summary.note && (
            <p className="mt-3 border border-slate-800 bg-slate-950/60 px-4 py-2 font-mono text-[11px] text-slate-400">
              {data.graph_summary.note}
            </p>
          )}
          {data.graph_summary.nodes.length > 0 ? (
            <>
              <div className="mt-3 h-[30rem] border border-slate-800 bg-slate-950">
                <ReactFlow nodes={flowNodes} edges={flowEdges} fitView minZoom={0.05} nodesDraggable>
                  <Background color="#1e293b" gap={18} />
                  <Controls showInteractive={false} />
                </ReactFlow>
              </div>
              <div className="mt-3 max-h-72 overflow-y-auto border border-slate-900">
                <table className="w-full border-collapse text-sm">
                  <thead className="sticky top-0 bg-slate-950">
                    <tr className="border-b border-slate-800 text-left font-mono text-[10px] uppercase tracking-widest text-slate-500">
                      <th className="py-2 pr-4">Source</th>
                      <th className="py-2 pr-4">Relation</th>
                      <th className="py-2">Target</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.graph_summary.table_rows.map((row, index) => (
                      <tr
                        key={`${row.source}-${row.relation}-${row.target}-${index}`}
                        className="border-b border-slate-900"
                      >
                        <td className="py-1.5 pr-4 font-mono text-xs text-slate-300">{row.source}</td>
                        <td className="py-1.5 pr-4 font-mono text-[11px] uppercase text-slate-500">{row.relation}</td>
                        <td className="py-1.5 font-mono text-xs text-slate-300">{row.target}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <p className="mt-3 border border-dashed border-slate-700 p-6 text-center font-mono text-xs uppercase tracking-wider text-slate-500">
              No graph nodes yet — process evidence, then run correlation to build the evidence graph.
            </p>
          )}
        </section>
      )}

      {tab === "assistant" && (
        <div className="space-y-8">
          <section className="border border-slate-800 bg-slate-900/50 p-5">
            <label className={labelClass} htmlFor="w-assistant-question">
              Ask the investigation assistant
            </label>
            <div className="mt-2">
              <textarea
                id="w-assistant-question"
                className={`${fieldClass} min-h-[96px] resize-y`}
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder="E.g. What suspicious activity was detected?"
                maxLength={1000}
              />
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => void ask()}
                disabled={asking}
                className="border border-cyan-700 bg-cyan-950/60 px-4 py-2 font-mono text-xs uppercase tracking-widest text-cyan-300 hover:bg-cyan-900/60 disabled:opacity-50"
              >
                {asking ? "Answering…" : "Ask assistant"}
              </button>
            </div>
            <p className="mt-3 max-w-3xl font-mono text-[10px] uppercase tracking-wider text-slate-600">
              Answers are persisted, append-only, and bounded to this case's evidence; no
              generative model is enabled.
            </p>
          </section>

          {data.assistant_summary.query_count === 0 ? (
            <p className="border border-dashed border-slate-700 p-6 text-center font-mono text-xs uppercase tracking-wider text-slate-500">
              No assistant questions yet for this case.
            </p>
          ) : (
            <section>
              <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">
                Assistant history ({data.assistant_summary.query_count})
              </h2>
              <div className="mt-3 space-y-3">
                {data.assistant_summary.history.map((row: AssistantQueryResult) => (
                  <div key={row.query_id} className="border border-slate-800 bg-slate-900/50 p-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <p className="font-mono text-xs text-cyan-400">#{row.query_id}</p>
                      <span className="font-mono text-[10px] uppercase tracking-widest text-slate-500">
                        {row.intent} · confidence {row.confidence}
                      </span>
                    </div>
                    <p className="mt-2 font-mono text-sm text-white">{row.question}</p>
                    <div className="mt-2 whitespace-pre-wrap border border-slate-800 bg-slate-950/70 p-4 text-sm leading-relaxed text-slate-200">
                      {row.answer}
                    </div>
                    {row.created_at && (
                      <p className="mt-2 font-mono text-[10px] text-slate-600">
                        asked {formatDateTime(row.created_at)}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>
      )}

      {tab === "reports" && (
        <div className="space-y-8">
          <section className="border border-slate-800 bg-slate-900/50 p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">
                  Generate a report snapshot
                </h2>
                <p className="mt-1 max-w-3xl text-sm text-slate-500">
                  Deterministic 15-section report built only from the persisted case data.
                  Each generation is an immutable snapshot.
                </p>
              </div>
              <button
                type="button"
                onClick={() => void generate()}
                disabled={generating}
                className="border border-emerald-700 bg-emerald-950/50 px-4 py-2 font-mono text-xs uppercase tracking-widest text-emerald-300 hover:bg-emerald-900/50 disabled:opacity-50"
              >
                {generating ? "Generating…" : "Generate report"}
              </button>
            </div>
            <div className="mt-4">
              <label className={labelClass} htmlFor="w-report-title">
                Optional title
              </label>
              <input
                id="w-report-title"
                className={`${fieldClass} mt-1 max-w-2xl`}
                value={reportTitle}
                onChange={(event) => setReportTitle(event.target.value)}
                placeholder="Leave empty for the canonical report title"
                maxLength={255}
              />
            </div>
          </section>

          <section>
            <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">
              Report snapshots ({data.report_summary.count})
            </h2>
            {data.report_summary.reports.length === 0 ? (
              <p className="mt-3 border border-dashed border-slate-700 p-6 text-center font-mono text-xs uppercase tracking-wider text-slate-500">
                No reports generated yet.
              </p>
            ) : (
              <div className="mt-3 overflow-x-auto">
                <table className="w-full border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-slate-800 text-left font-mono text-[10px] uppercase tracking-widest text-slate-500">
                      <th className="py-2 pr-4">Report</th>
                      <th className="py-2 pr-4">Title</th>
                      <th className="py-2 pr-4">Generated</th>
                      <th className="py-2">By</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.report_summary.reports.map((report) => (
                      <tr key={report.report_id} className="border-b border-slate-900 align-top">
                        <td className="py-3 pr-4">
                          <Link
                            to={`/cases/${caseId}/reports/${encodeURIComponent(report.report_id)}`}
                            className="font-mono text-xs text-cyan-400 hover:underline"
                          >
                            {report.report_id}
                          </Link>
                        </td>
                        <td className="py-3 pr-4 text-white">{report.title}</td>
                        <td className="py-3 pr-4 font-mono text-xs text-slate-400">
                          {report.generated_at ? formatDateTime(report.generated_at) : "—"}
                        </td>
                        <td className="py-3 font-mono text-xs text-slate-400">{report.generated_by}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}