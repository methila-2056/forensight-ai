import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import ReactFlow, { Background, Controls, MarkerType } from "reactflow";
import type { Edge, Node } from "reactflow";
import "reactflow/dist/style.css";
import { getCase } from "../api/cases";
import {
  correlateCase,
  getCorrelation,
  getGraph,
  getGroup,
  getTimeline,
  listCorrelationRuns,
  listCorrelations,
  listGroups,
} from "../api/correlation";
import { ApiError } from "../api/client";
import {
  ConfidenceBandBadge,
  ProcessingStatusBadge,
  SeverityBadge,
  SignificanceBadge,
  SourceTypeBadge,
} from "../components/Badges";
import ErrorBox from "../components/ErrorBox";
import { formatDateTime } from "../state/format";
import type {
  CaseSummary,
  ConfidenceBand,
  CorrelationDetail,
  CorrelationListResult,
  CorrelationRun,
  CorrelationType,
  GroupDetail,
  GroupKind,
  GraphNode as GraphNodeData,
  GraphResult,
  GroupSummary,
  TimelineEntry,
  TimelineResult,
  TimelineSignificance,
} from "../types/models";
import {
  CORRELATION_TYPE_LABELS,
  CORRELATION_TYPE_OPTIONS,
  GROUP_KIND_OPTIONS,
  TIMELINE_SIGNIFICANCE_OPTIONS,
} from "../types/models";
import {
  CORRELATION_DISCLAIMER,
  CORRELATION_GROUP_NOTE,
  CORRELATION_RUN_LABEL,
  TIMELINE_DISCLAIMER,
  TIMELINE_LABEL,
} from "../types/terminology";

const fieldClass =
  "border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:border-cyan-600 focus:outline-none";

const labelClass = "mb-1 block font-mono text-[10px] uppercase tracking-widest text-slate-400";

const PAGE_SIZE = 25;

const asNumber = (value: unknown): number | null => (typeof value === "number" ? value : null);

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

export default function InvestigationPage(): JSX.Element {
  const { caseId = "" } = useParams();

  const [caseData, setCaseData] = useState<CaseSummary | null>(null);
  const [runs, setRuns] = useState<CorrelationRun[]>([]);
  const [runFilter, setRunFilter] = useState("");
  const [corrOffset, setCorrOffset] = useState(0);
  const [kindFilter, setKindFilter] = useState<GroupKind | "">("");
  const [significanceFilter, setSignificanceFilter] = useState<
    "" | TimelineSignificance
  >("");
  const [corrType, setCorrType] = useState<CorrelationType | "">("");
  const [correlations, setCorrelations] = useState<CorrelationListResult | null>(null);
  const [groups, setGroups] = useState<Awaited<ReturnType<typeof listGroups>> | null>(null);
  const [timeline, setTimeline] = useState<TimelineResult | null>(null);
  const [graph, setGraph] = useState<GraphResult | null>(null);

  const [corrDetail, setCorrDetail] = useState<CorrelationDetail | null>(null);
  const [groupDetail, setGroupDetail] = useState<GroupDetail | null>(null);
  const [selectedGroup, setSelectedGroup] = useState<string | null>(null);

  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const loadAll = useCallback(() => {
    Promise.all([
      getCase(caseId),
      listCorrelationRuns(caseId),
      listCorrelations(caseId, {
        type: corrType,
        run_id: runFilter,
        limit: PAGE_SIZE,
        offset: corrOffset,
      }),
      listGroups(caseId, { kind: kindFilter, run_id: runFilter }),
      getTimeline(caseId, runFilter || undefined),
      getGraph(caseId, runFilter || undefined),
    ])
      .then(([loadedCase, corrRuns, corrList, groupList, tl, gr]) => {
        setCaseData(loadedCase);
        setRuns(corrRuns);
        setCorrelations(corrList);
        setGroups(groupList);
        setTimeline(tl);
        setGraph(gr);
        setError(null);
      })
      .catch((err: unknown) => {
        setError(
          err instanceof ApiError ? err.message : "Failed to load investigation data.",
        );
      });
  }, [caseId, corrType, runFilter, corrOffset, kindFilter]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  useEffect(() => {
    setCorrOffset(0);
    setCorrDetail(null);
  }, [corrType, runFilter, kindFilter]);

  const runCorrelation = async (): Promise<void> => {
    setBusy(true);
    setActionError(null);
    setNotice(null);
    try {
      const run = await correlateCase(caseId, "ui");
      if (run.status === "Failed") {
        setActionError(run.error ?? "Correlation failed; see the server logs.");
      } else {
        setNotice(`Correlation run ${run.run_id} completed.`);
      }
      loadAll();
    } catch (err: unknown) {
      setActionError(
        err instanceof ApiError ? err.message : "Correlation failed.",
      );
    } finally {
      setBusy(false);
    }
  };

  const openCorrelation = (correlationId: string): void => {
    if (corrDetail?.correlation_id === correlationId) {
      setCorrDetail(null);
      return;
    }
    getCorrelation(correlationId)
      .then(setCorrDetail)
      .catch((err: unknown) =>
        setActionError(
          err instanceof ApiError ? err.message : "Failed to load the correlation.",
        ),
      );
  };

  const openGroup = (groupId: string): void => {
    if (selectedGroup === groupId) {
      setSelectedGroup(null);
      setGroupDetail(null);
      return;
    }
    setSelectedGroup(groupId);
    getGroup(groupId)
      .then(setGroupDetail)
      .catch((err: unknown) =>
        setActionError(
          err instanceof ApiError ? err.message : "Failed to load the group.",
        ),
      );
  };

  const corrRows = correlations?.correlations ?? [];
  const corrTotal = correlations?.total ?? 0;
  const groupRows = groups?.groups ?? [];
  const latestRun = runs[0] ?? null;
  const latestStats = (latestRun?.stats ?? null) as Record<string, unknown> | null;

  const timelineEntries = useMemo(() => {
    const rows = timeline?.entries ?? [];
    if (!significanceFilter) return rows;
    return rows.filter((entry) => entry.significance === significanceFilter);
  }, [timeline, significanceFilter]);

  const flowNodes = useMemo<Node[]>(() => {
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
  }, [graph]);

  const flowEdges = useMemo<Edge[]>(() => {
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
  }, [graph]);

  if (error) {
    return <ErrorBox message={error} />;
  }
  if (!caseData) {
    return (
      <p className="font-mono text-xs uppercase tracking-widest text-slate-500">
        Loading investigation…
      </p>
    );
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="font-mono text-xs uppercase tracking-widest text-cyan-500">{caseId}</p>
          <h1 className="mt-1 text-2xl font-bold text-white">Investigation</h1>
          <p className="mt-1 text-sm text-slate-400">
            {caseData.name} · cross-source correlations, activity groups, reconstructed
            timeline, and evidence graph
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

      {notice && (
        <p className="border border-emerald-800 bg-emerald-950/40 px-4 py-2 font-mono text-xs text-emerald-300">
          {notice}
        </p>
      )}
      {actionError && <ErrorBox message={actionError} />}

      {/* ---------------------------------------------------------------- */}
      {/* Correlation runs                                                  */}
      {/* ---------------------------------------------------------------- */}
      <section className="border border-slate-800 bg-slate-900/50 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">
              Cross-source correlation — reason-tagged links from real events
            </h2>
            <p className="mt-1 max-w-3xl text-sm text-slate-500">
              Sweeps this case&apos;s timestamped events inside a{" "}
              {asNumber(latestStats?.window_seconds) ?? 300}-second window and links pairs
              that share a host, user, source IP, or a typed process relation. Confidence is
              an explicit additive weight of the shared attributes; activity groups are
              union-find components over the links. Re-correlation appends a run; history is
              never rewritten.
            </p>
            <p className="mt-2 max-w-3xl font-mono text-[11px] leading-relaxed text-slate-600">
              {CORRELATION_DISCLAIMER}
            </p>
          </div>
          <button
            type="button"
            onClick={() => void runCorrelation()}
            disabled={busy}
            className="border border-cyan-700 bg-cyan-950/60 px-4 py-2 font-mono text-xs uppercase tracking-widest text-cyan-300 hover:bg-cyan-900/60 disabled:opacity-50"
          >
            {busy ? "Correlating…" : "Run correlation"}
          </button>
        </div>

        {latestRun && latestStats && (
          <div className="mt-4 flex flex-wrap gap-3">
            <span className="border border-slate-700 px-3 py-1 font-mono text-[11px] text-slate-400">
              {latestRun.run_id} · {latestRun.status}
            </span>
            <span className="border border-slate-700 px-3 py-1 font-mono text-[11px] text-slate-400">
              links {asNumber(latestStats.links) ?? 0}
            </span>
            <span className="border border-slate-700 px-3 py-1 font-mono text-[11px] text-slate-400">
              groups {asNumber(latestStats.groups) ?? 0}
            </span>
            <span className="border border-slate-700 px-3 py-1 font-mono text-[11px] text-slate-400">
              dated events {asNumber(latestStats.dated_events) ?? 0}
            </span>
            <span className="border border-slate-700 px-3 py-1 font-mono text-[11px] text-slate-400">
              window {asNumber(latestStats.window_seconds) ?? "—"}s
            </span>
          </div>
        )}

        {runs.length > 0 ? (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-800 text-left font-mono text-[10px] uppercase tracking-widest text-slate-500">
                  <th className="py-2 pr-4">Run</th>
                  <th className="py-2 pr-4">Status</th>
                  <th className="py-2 pr-4">Started</th>
                  <th className="py-2 pr-4">Finished</th>
                  <th className="py-2 pr-4">Links</th>
                  <th className="py-2">Groups</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => {
                  const stats = (run.stats ?? {}) as Record<string, unknown>;
                  return (
                    <tr key={run.run_id} className="border-b border-slate-900 align-top">
                      <td className="py-3 pr-4 font-mono text-xs text-cyan-400">{run.run_id}</td>
                      <td className="py-3 pr-4">
                        <ProcessingStatusBadge status={run.status} />
                      </td>
                      <td className="py-3 pr-4 font-mono text-xs text-slate-400">
                        {run.started_at ? formatDateTime(run.started_at) : "—"}
                      </td>
                      <td className="py-3 pr-4 font-mono text-xs text-slate-400">
                        {run.finished_at ? formatDateTime(run.finished_at) : "—"}
                      </td>
                      <td className="py-3 pr-4 font-mono text-xs text-slate-300">
                        {asNumber(stats.links) ?? "—"}
                      </td>
                      <td className="py-3 font-mono text-xs text-slate-300">
                        {asNumber(stats.groups) ?? "—"}
                        {run.error ? (
                          <p className="font-mono text-[11px] text-red-400">{run.error}</p>
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="mt-4 border border-dashed border-slate-700 p-6 text-center font-mono text-xs uppercase tracking-wider text-slate-500">
            No correlation runs yet — process evidence (and optionally run analysis), then run
            correlation.
          </p>
        )}
      </section>

      {/* ---------------------------------------------------------------- */}
      {/* Correlation links                                                 */}
      {/* ---------------------------------------------------------------- */}
      <section>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">
            Correlations {corrTotal > 0 ? `(${corrTotal})` : ""}
          </h2>
          <p className="font-mono text-[10px] uppercase tracking-wider text-slate-600">
            Select a row for the full reason and event detail
          </p>
        </div>

        <form
          className="mt-3 grid gap-3 md:grid-cols-3"
          onSubmit={(event) => {
            event.preventDefault();
            setCorrOffset(0);
            loadAll();
          }}
        >
          <div>
            <label className={labelClass} htmlFor="c-type">
              Correlation type
            </label>
            <select
              id="c-type"
              className={`${fieldClass} w-full`}
              value={corrType}
              onChange={(event) => setCorrType(event.target.value as CorrelationType | "")}
            >
              {CORRELATION_TYPE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className={labelClass} htmlFor="c-run">
              {CORRELATION_RUN_LABEL}
            </label>
            <select
              id="c-run"
              className={`${fieldClass} w-full`}
              value={runFilter}
              onChange={(event) => setRunFilter(event.target.value)}
            >
              <option value="">Latest run</option>
              {runs.map((run) => (
                <option key={run.run_id} value={run.run_id}>
                  {run.run_id}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-end">
            <button
              type="submit"
              className="border border-slate-700 px-4 py-2 font-mono text-xs uppercase tracking-widest text-slate-400 hover:text-slate-200"
            >
              Apply
            </button>
          </div>
        </form>

        {corrRows.length === 0 ? (
          <p className="mt-3 border border-dashed border-slate-700 p-6 text-center font-mono text-xs uppercase tracking-wider text-slate-500">
            No correlations match — run correlation to create the first links.
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
                  <th className="py-2 pr-4">Δt (s)</th>
                  <th className="py-2 pr-4">Confidence</th>
                  <th className="py-2">Reason</th>
                </tr>
              </thead>
              <tbody>
                {corrRows.map((row) => (
                  <tr
                    key={row.correlation_id}
                    onClick={() => openCorrelation(row.correlation_id)}
                    className={`cursor-pointer border-b border-slate-900 hover:bg-slate-900/70 ${
                      corrDetail?.correlation_id === row.correlation_id ? "bg-slate-900" : ""
                    }`}
                  >
                    <td className="py-3 pr-4 font-mono text-xs text-cyan-400">
                      {row.correlation_id}
                    </td>
                    <td className="py-3 pr-4">
                      <span className="font-mono text-[11px] text-slate-300">
                        {row.correlation_type}
                      </span>
                      <span className="block font-mono text-[10px] text-slate-500">
                        {CORRELATION_TYPE_LABELS[row.correlation_type]}
                      </span>
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
                      {row.time_delta_seconds != null
                        ? Math.round(row.time_delta_seconds)
                        : "—"}
                    </td>
                    <td className="py-3 pr-4">
                      <ConfidenceBandBadge
                        band={row.confidence_band as ConfidenceBand}
                        confidence={row.confidence}
                      />
                    </td>
                    <td className="py-3 text-xs text-slate-400">
                      {truncate(row.reason, 140)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {corrDetail && (
          <div className="mt-4 border border-slate-800 bg-slate-950/70 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="font-mono text-xs text-cyan-400">{corrDetail.correlation_id}</p>
              <button
                type="button"
                onClick={() => setCorrDetail(null)}
                className="border border-slate-700 px-3 py-1 font-mono text-[10px] uppercase tracking-widest text-slate-400 hover:text-slate-200"
              >
                Close
              </button>
            </div>
            <p className="mt-2 text-sm text-slate-300">{corrDetail.reason}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {Object.entries(corrDetail.shared_entities).map(([key, value]) => (
                <span
                  key={key}
                  className="border border-slate-700 px-2 py-0.5 font-mono text-[10px] text-slate-400"
                >
                  {key}: {value}
                </span>
              ))}
              <ConfidenceBandBadge
                band={corrDetail.confidence_band}
                confidence={corrDetail.confidence}
              />
            </div>
            <div className="mt-4 grid gap-4 lg:grid-cols-2">
              {[corrDetail.event_a_detail, corrDetail.event_b_detail].map(
                (detail, index) =>
                  detail && (
                    <div key={index} className="border border-slate-800 bg-slate-900/60 p-3">
                      <p className="font-mono text-[10px] uppercase tracking-widest text-slate-500">
                        {index === 0 ? "Event A" : "Event B"} · {detail.event_id}
                      </p>
                      <div className="mt-2 flex flex-wrap items-center gap-2">
                        <SourceTypeBadge sourceType={detail.source_type} />
                        <span className="font-mono text-[11px] text-slate-400">
                          {detail.timestamp ? formatDateTime(detail.timestamp) : "no timestamp"}
                        </span>
                        {detail.is_anomalous && (
                          <span className="border border-amber-700 px-2 py-0.5 font-mono text-[10px] uppercase text-amber-400">
                            anomalous
                          </span>
                        )}
                      </div>
                      <p className="mt-2 font-mono text-[11px] text-slate-300">
                        {[
                          detail.user,
                          detail.host,
                          detail.process,
                          detail.file_path,
                          detail.action,
                        ]
                          .filter(Boolean)
                          .join(" · ") || "—"}
                      </p>
                      {detail.raw_record && (
                        <p className="mt-2 max-h-24 overflow-y-auto whitespace-pre-wrap border border-slate-800 bg-slate-950 p-2 font-mono text-[10px] text-slate-500">
                          {detail.raw_record.content}
                        </p>
                      )}
                      {detail.evidence && (
                        <p className="mt-2 font-mono text-[10px] text-slate-500">
                          {detail.evidence.evidence_id} · {detail.evidence.original_filename} ·
                          SHA-256 {detail.evidence.sha256.slice(0, 12)}…
                        </p>
                      )}
                    </div>
                  ),
              )}
            </div>
            <p className="mt-3 font-mono text-[11px] text-slate-600">
              {corrDetail.disclaimer || CORRELATION_DISCLAIMER}
            </p>
          </div>
        )}

        <div className="mt-3 flex items-center justify-between">
          <p className="font-mono text-[10px] uppercase tracking-wider text-slate-600">
            Showing {corrRows.length} of {corrTotal}
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setCorrOffset(Math.max(0, corrOffset - PAGE_SIZE))}
              disabled={corrOffset === 0}
              className="border border-slate-700 px-3 py-1 font-mono text-xs uppercase tracking-widest text-slate-400 hover:text-slate-200 disabled:opacity-40"
            >
              ← Prev
            </button>
            <button
              type="button"
              onClick={() => setCorrOffset(corrOffset + PAGE_SIZE)}
              disabled={corrOffset + PAGE_SIZE >= corrTotal}
              className="border border-slate-700 px-3 py-1 font-mono text-xs uppercase tracking-widest text-slate-400 hover:text-slate-200 disabled:opacity-40"
            >
              Next →
            </button>
          </div>
        </div>
      </section>

      {/* ---------------------------------------------------------------- */}
      {/* Activity groups                                                   */}
      {/* ---------------------------------------------------------------- */}
      <section>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">
            Activity groups {groupRows.length > 0 ? `(${groups?.total ?? 0})` : ""}
          </h2>
          <p className="font-mono text-[10px] uppercase tracking-wider text-slate-600">
            {CORRELATION_GROUP_NOTE}
          </p>
        </div>

        <div className="mt-3 grid gap-3 md:grid-cols-3">
          <div>
            <label className={labelClass} htmlFor="g-kind">
              Kind
            </label>
            <select
              id="g-kind"
              className={`${fieldClass} w-full`}
              value={kindFilter}
              onChange={(event) => setKindFilter(event.target.value as GroupKind | "")}
            >
              {GROUP_KIND_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {groupRows.length === 0 ? (
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
                  <th className="py-2 pr-4">Links</th>
                  <th className="py-2">Window</th>
                </tr>
              </thead>
              <tbody>
                {groupRows.map((group: GroupSummary) => (
                  <tr
                    key={group.group_id}
                    onClick={() => openGroup(group.group_id)}
                    className={`cursor-pointer border-b border-slate-900 hover:bg-slate-900/70 ${
                      selectedGroup === group.group_id ? "bg-slate-900" : ""
                    }`}
                  >
                    <td className="py-3 pr-4 font-mono text-xs text-cyan-400">
                      {group.group_id}
                    </td>
                    <td className="py-3 pr-4 font-mono text-[11px] uppercase text-slate-400">
                      {group.kind}
                    </td>
                    <td className="py-3 pr-4 text-white">{group.title}</td>
                    <td className="py-3 pr-4">
                      <SeverityBadge severity={group.severity} />
                    </td>
                    <td className="py-3 pr-4 font-mono text-xs text-slate-300">
                      {group.event_count}
                    </td>
                    <td className="py-3 pr-4 font-mono text-xs text-slate-300">
                      {group.correlation_count}
                    </td>
                    <td className="py-3 font-mono text-[11px] text-slate-500">
                      {group.time_start ? formatDateTime(group.time_start) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {groupDetail && (
          <div className="mt-4 border border-slate-800 bg-slate-950/70 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap items-center gap-3">
                <p className="font-mono text-xs text-cyan-400">{groupDetail.group_id}</p>
                <SeverityBadge severity={groupDetail.severity} />
                <span className="font-mono text-[11px] uppercase text-slate-400">
                  {groupDetail.kind}
                </span>
              </div>
              <button
                type="button"
                onClick={() => {
                  setSelectedGroup(null);
                  setGroupDetail(null);
                }}
                className="border border-slate-700 px-3 py-1 font-mono text-[10px] uppercase tracking-widest text-slate-400 hover:text-slate-200"
              >
                Close
              </button>
            </div>
            <p className="mt-2 text-sm text-white">{groupDetail.title}</p>
            <p className="mt-1 max-w-4xl text-sm text-slate-400">{groupDetail.explanation}</p>
            <div className="mt-3 overflow-x-auto">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="border-b border-slate-800 text-left font-mono text-[10px] uppercase tracking-widest text-slate-500">
                    <th className="py-2 pr-4">Event</th>
                    <th className="py-2 pr-4">Timestamp</th>
                    <th className="py-2 pr-4">Source</th>
                    <th className="py-2">Who / what</th>
                  </tr>
                </thead>
                <tbody>
                  {groupDetail.member_events.map((member) => (
                    <tr key={member.event_id} className="border-b border-slate-900">
                      <td className="py-2 pr-4 font-mono text-xs text-cyan-400">
                        {member.event_id}
                      </td>
                      <td className="py-2 pr-4 font-mono text-[11px] text-slate-400">
                        {member.timestamp ? formatDateTime(member.timestamp) : "—"}
                      </td>
                      <td className="py-2 pr-4">
                        <SourceTypeBadge sourceType={member.source_type} />
                      </td>
                      <td className="py-2 font-mono text-[11px] text-slate-400">
                        {[
                          member.user,
                          member.host,
                          member.process,
                          member.file_path,
                          member.action,
                        ]
                          .filter(Boolean)
                          .join(" · ") || "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-3 font-mono text-[11px] text-slate-600">
              {groupDetail.disclaimer || CORRELATION_DISCLAIMER}
            </p>
          </div>
        )}
      </section>

      {/* ---------------------------------------------------------------- */}
      {/* Timeline                                                          */}
      {/* ---------------------------------------------------------------- */}
      <section>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">
              {TIMELINE_LABEL}
            </h2>
            <p className="mt-1 max-w-3xl font-mono text-[11px] leading-relaxed text-slate-600">
              {TIMELINE_DISCLAIMER}
            </p>
          </div>
          <div className="w-56">
            <label className={labelClass} htmlFor="t-sig">
              Significance
            </label>
            <select
              id="t-sig"
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

        {timeline?.note && (
          <p className="mt-3 border border-slate-800 bg-slate-950/60 px-4 py-2 font-mono text-[11px] text-slate-400">
            {timeline.note}
          </p>
        )}

        {timelineEntries.length === 0 ? (
          <p className="mt-3 border border-dashed border-slate-700 p-6 text-center font-mono text-xs uppercase tracking-wider text-slate-500">
            No timeline entries — process evidence, then run analysis and correlation to
            reconstruct this timeline.
          </p>
        ) : (
          <div className="mt-3 max-h-[32rem] overflow-y-auto overflow-x-auto border border-slate-900">
            <table className="w-full border-collapse text-sm">
              <thead className="sticky top-0 bg-slate-950">
                <tr className="border-b border-slate-800 text-left font-mono text-[10px] uppercase tracking-widest text-slate-500">
                  <th className="py-2 pr-4">Timestamp</th>
                  <th className="py-2 pr-4">Significance</th>
                  <th className="py-2 pr-4">Event</th>
                  <th className="py-2 pr-4">Source</th>
                  <th className="py-2 pr-4">Who / what</th>
                  <th className="py-2">Reasons</th>
                </tr>
              </thead>
              <tbody>
                {timelineEntries.map((entry: TimelineEntry) => (
                  <tr key={entry.event_id} className="border-b border-slate-900 align-top">
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
                      {entry.correlation_ids.length > 0 && (
                        <span className="mt-1 block font-mono text-[9px] text-cyan-600">
                          {entry.correlation_ids.join(", ")}
                        </span>
                      )}
                    </td>
                    <td className="py-2 pr-4">
                      <SourceTypeBadge sourceType={entry.source_type} />
                    </td>
                    <td className="py-2 pr-4 font-mono text-[11px] text-slate-400">
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
                    <td className="py-2 text-xs text-slate-400">
                      {entry.reasons.map((reason) => (
                        <p key={reason}>{reason}</p>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {timeline?.truncated && (
          <p className="mt-2 font-mono text-[11px] text-amber-500">
            {timeline.entries.length} of {timeline.total} entries shown (TIMELINE_MAX_ENTRIES).
          </p>
        )}
      </section>

      {/* ---------------------------------------------------------------- */}
      {/* Evidence graph                                                    */}
      {/* ---------------------------------------------------------------- */}
      <section>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">
              Evidence graph — evidence → findings → events → correlations
            </h2>
            <p className="mt-1 max-w-3xl font-mono text-[11px] leading-relaxed text-slate-600">
              {graph?.disclaimer || CORRELATION_DISCLAIMER}
            </p>
          </div>
          <p className="font-mono text-[10px] uppercase tracking-wider text-slate-600">
            {graph ? `${graph.nodes.length}/${graph.max_nodes} nodes · ${graph.edges.length}/${graph.max_edges} edges` : "—"}
          </p>
        </div>

        {graph?.note && (
          <p className="mt-3 border border-slate-800 bg-slate-950/60 px-4 py-2 font-mono text-[11px] text-slate-400">
            {graph.note}
          </p>
        )}

        {graph && graph.nodes.length > 0 ? (
          <>
            <div className="mt-3 h-[30rem] border border-slate-800 bg-slate-950">
              <ReactFlow
                nodes={flowNodes}
                edges={flowEdges}
                fitView
                minZoom={0.05}
                nodesDraggable
              >
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
                  {graph.table_rows.map((row, index) => (
                    <tr key={`${row.source}-${row.relation}-${row.target}-${index}`} className="border-b border-slate-900">
                      <td className="py-1.5 pr-4 font-mono text-xs text-slate-300">{row.source}</td>
                      <td className="py-1.5 pr-4 font-mono text-[11px] uppercase text-slate-500">
                        {row.relation}
                      </td>
                      <td className="py-1.5 font-mono text-xs text-slate-300">{row.target}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <p className="mt-3 border border-dashed border-slate-700 p-6 text-center font-mono text-xs uppercase tracking-wider text-slate-500">
            No graph nodes yet — process evidence, then run correlation to build the evidence
            graph.
          </p>
        )}
      </section>
    </div>
  );
}
