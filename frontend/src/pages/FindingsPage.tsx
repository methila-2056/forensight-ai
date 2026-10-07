import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { analyzeCase, getMlMetrics, listAnalysisRuns, listFindings } from "../api/analysis";
import { getCase } from "../api/cases";
import { ApiError } from "../api/client";
import {
  FindingKindBadge,
  FindingStatusBadge,
  ProcessingStatusBadge,
  SeverityBadge,
} from "../components/Badges";
import ErrorBox from "../components/ErrorBox";
import { formatDateTime } from "../state/format";
import type {
  AnalysisRun,
  CaseSummary,
  FindingListResult,
  FindingQuery,
  FindingStatus,
  MlMetrics,
} from "../types/models";
import {
  FINDING_KIND_OPTIONS,
  FINDING_STATUS_OPTIONS,
  SEVERITY_OPTIONS,
} from "../types/models";
import {
  ANALYSIS_SCOPE_NOTE,
  ML_ABSTAIN_NOTE,
  RULE_CONFIDENCE_NOTE,
} from "../types/terminology";

const fieldClass =
  "w-full border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 focus:border-cyan-600 focus:outline-none";

const labelClass = "mb-1 block font-mono text-[10px] uppercase tracking-widest text-slate-400";

const PAGE_SIZE = 25;

const emptyQuery = (): FindingQuery => ({ kind: "", severity: "", status: "", run_id: "" });

const asNumber = (value: unknown): number | null => (typeof value === "number" ? value : null);
const asString = (value: unknown): string | null => (typeof value === "string" ? value : null);

export default function FindingsPage(): JSX.Element {
  const { caseId = "" } = useParams();
  const navigate = useNavigate();

  const [caseData, setCaseData] = useState<CaseSummary | null>(null);
  const [runs, setRuns] = useState<AnalysisRun[]>([]);
  const [result, setResult] = useState<FindingListResult | null>(null);
  const [metrics, setMetrics] = useState<MlMetrics | null>(null);
  const [query, setQuery] = useState<FindingQuery>(emptyQuery);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadFindings = useCallback(() => {
    listFindings(caseId, { ...query, limit: PAGE_SIZE, offset })
      .then(setResult)
      .catch((err: unknown) =>
        setError(err instanceof ApiError ? err.message : "Failed to load findings."),
      );
  }, [caseId, query, offset]);

  const loadRuns = useCallback(() => {
    Promise.all([listAnalysisRuns(caseId), getMlMetrics(caseId)])
      .then(([analysisRuns, mlMetrics]) => {
        setRuns(analysisRuns);
        setMetrics(mlMetrics);
      })
      .catch(() => {
        /* run history is optional; findings load reports real failures */
      });
  }, [caseId]);

  useEffect(() => {
    getCase(caseId)
      .then(setCaseData)
      .catch((err: unknown) =>
        setError(err instanceof ApiError ? err.message : "Failed to load the case."),
      );
  }, [caseId]);

  useEffect(() => {
    loadFindings();
    loadRuns();
  }, [loadFindings, loadRuns]);

  useEffect(() => {
    setOffset(0);
  }, [query]);

  const runAnalysis = async (): Promise<void> => {
    setAnalyzing(true);
    setAnalyzeError(null);
    setNotice(null);
    try {
      const run = await analyzeCase(caseId, "ui");
      if (run.status === "Failed") {
        setAnalyzeError(run.error ?? "Automated analysis failed; see the server logs.");
      } else {
        setNotice(`Analysis run ${run.run_id} completed.`);
      }
      await Promise.all([loadFindings(), loadRuns()]);
    } catch (err: unknown) {
      setAnalyzeError(
        err instanceof ApiError ? err.message : "Automated analysis failed.",
      );
      loadRuns();
    } finally {
      setAnalyzing(false);
    }
  };

  const set = (key: keyof FindingQuery, value: string): void => {
    setQuery((previous) => ({ ...previous, [key]: value }));
  };

  const findings = result?.findings ?? [];
  const latest = runs[0] ?? null;
  const latestStats = (latest?.stats ?? null) as Record<string, unknown> | null;
  const total = result?.total ?? 0;
  const start = total > 0 ? Math.min(offset + 1, total) : 0;
  const end = Math.min(offset + findings.length, total);

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="font-mono text-xs uppercase tracking-widest text-cyan-500">{caseId}</p>
          <h1 className="mt-1 text-2xl font-bold text-white">Findings</h1>
          <p className="mt-1 text-sm text-slate-400">
            {caseData ? caseData.name : "Loading case…"} · rule detections and ML anomaly windows,
            fused into a Composite Suspicion Score
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
            to={`/cases/${caseId}/events`}
            className="border border-slate-700 px-4 py-2 font-mono text-xs uppercase tracking-widest text-slate-400 hover:text-slate-200"
          >
            Events →
          </Link>
        </div>
      </div>

      {error && <ErrorBox message={error} />}

      <section className="border border-slate-800 bg-slate-900/50 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">
              Automated analysis — rules + Strategy A anomaly detection
            </h2>
            <p className="mt-1 max-w-3xl text-sm text-slate-500">
              Scores deterministic feature windows with a seeded Isolation Forest (both a fixed
              threshold and a case-reference gate must pass), evaluates the transparent rule
              catalog, and fuses the results into an uncalibrated Composite Suspicion Score.
              Every finding starts as <span className="text-slate-300">New</span> and requires
              investigator review. Re-analysis appends a new run; history is never deleted.
            </p>
            <p className="mt-2 max-w-3xl font-mono text-[11px] leading-relaxed text-slate-600">
              {ANALYSIS_SCOPE_NOTE}
            </p>
          </div>
          <button
            type="button"
            onClick={() => void runAnalysis()}
            disabled={analyzing}
            className="border border-cyan-700 bg-cyan-950/60 px-4 py-2 font-mono text-xs uppercase tracking-widest text-cyan-300 hover:bg-cyan-900/60 disabled:opacity-50"
          >
            {analyzing ? "Analyzing…" : "Run analysis"}
          </button>
        </div>

        {analyzeError && (
          <div className="mt-4">
            <ErrorBox message={analyzeError} />
          </div>
        )}
        {notice && (
          <p className="mt-4 border border-emerald-800 bg-emerald-950/40 px-4 py-2 font-mono text-xs text-emerald-300">
            {notice}
          </p>
        )}

        {latest && latestStats && (
          <div className="mt-4 flex flex-wrap gap-3">
            <span className="border border-slate-700 px-3 py-1 font-mono text-[11px] text-slate-400">
              {latest.run_id} · {latest.status}
            </span>
            <span className="border border-slate-700 px-3 py-1 font-mono text-[11px] text-slate-400">
              windows {asNumber(latestStats.windows_total) ?? "—"}
              {asNumber(latestStats.windows_flagged) != null
                ? ` (${latestStats.windows_flagged} flagged)`
                : ""}
            </span>
            <span className="border border-slate-700 px-3 py-1 font-mono text-[11px] text-slate-400">
              rules {asNumber(latestStats.rule_findings) ?? 0}
            </span>
            <span className="border border-slate-700 px-3 py-1 font-mono text-[11px] text-slate-400">
              ML {asNumber(latestStats.ml_findings) ?? 0}
            </span>
            <span className="border border-slate-700 px-3 py-1 font-mono text-[11px] text-slate-400">
              threshold {asNumber(latestStats.threshold_value) ?? "—"}
            </span>
            <span className="border border-slate-700 px-3 py-1 font-mono text-[11px] text-slate-400">
              {asString(latestStats.model_name) ?? "model"} ·{" "}
              {asString(latestStats.model_version) ?? ""}
            </span>
            <span className="border border-slate-700 px-3 py-1 font-mono text-[11px] text-slate-400">
              {asString(latestStats.fusion_formula_version) ?? ""}
            </span>
          </div>
        )}
        {latestStats && latestStats.abstained === true && (
          <p className="mt-3 border border-amber-800 bg-amber-950/30 px-4 py-2 font-mono text-[11px] text-amber-300">
            {asString(latestStats.abstain_note) ?? ML_ABSTAIN_NOTE}
          </p>
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
                  <th className="py-2 pr-4">Windows</th>
                  <th className="py-2 pr-4">Rule findings</th>
                  <th className="py-2">ML findings</th>
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
                        {asNumber(stats.windows_total) ?? "—"}
                      </td>
                      <td className="py-3 pr-4 font-mono text-xs text-slate-300">
                        {asNumber(stats.rule_findings) ?? "—"}
                      </td>
                      <td className="py-3 font-mono text-xs text-slate-300">
                        {asNumber(stats.ml_findings) ?? "—"}
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
            No analysis runs yet — process evidence, then run analysis.
          </p>
        )}

        {metrics && metrics.config && (
          <div className="mt-4 border border-slate-800 bg-slate-950/60 p-4">
            <p className="font-mono text-[10px] uppercase tracking-widest text-slate-500">
              Model diagnostics (latest run {metrics.run_id ?? "—"})
            </p>
            <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 font-mono text-[11px] text-slate-400">
              <span>seed {metrics.config.random_state}</span>
              <span>estimators {metrics.config.n_estimators}</span>
              <span>z-sigmas {metrics.config.z_sigmas}</span>
              <span>min windows {metrics.config.min_windows}</span>
              <span>window {metrics.config.window_minutes} min</span>
              <span>threshold {metrics.config.threshold}</span>
              <span>max findings/rule {metrics.config.max_findings_per_rule}</span>
            </div>
            <p className="mt-2 font-mono text-[11px] leading-relaxed text-slate-600">
              {metrics.scope_note}
            </p>
          </div>
        )}
      </section>

      <section>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">
            Findings {total > 0 ? `(${total})` : ""}
          </h2>
          <p className="font-mono text-[10px] uppercase tracking-wider text-slate-600">
            {RULE_CONFIDENCE_NOTE}
          </p>
        </div>

        <form
          className="mt-3 grid gap-3 md:grid-cols-4"
          onSubmit={(event) => {
            event.preventDefault();
            setOffset(0);
            loadFindings();
          }}
        >
          <div>
            <label className={labelClass} htmlFor="f-kind">
              Kind
            </label>
            <select
              id="f-kind"
              className={fieldClass}
              value={query.kind ?? ""}
              onChange={(event) => set("kind", event.target.value)}
            >
              {FINDING_KIND_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className={labelClass} htmlFor="f-sev">
              Severity
            </label>
            <select
              id="f-sev"
              className={fieldClass}
              value={query.severity ?? ""}
              onChange={(event) => set("severity", event.target.value)}
            >
              <option value="">All severities</option>
              {SEVERITY_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className={labelClass} htmlFor="f-status">
              Status
            </label>
            <select
              id="f-status"
              className={fieldClass}
              value={query.status ?? ""}
              onChange={(event) => set("status", event.target.value as FindingStatus | "")}
            >
              <option value="">All statuses</option>
              {FINDING_STATUS_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className={labelClass} htmlFor="f-run">
              Analysis run
            </label>
            <select
              id="f-run"
              className={fieldClass}
              value={query.run_id ?? ""}
              onChange={(event) => set("run_id", event.target.value)}
            >
              <option value="">All runs</option>
              {runs.map((run) => (
                <option key={run.run_id} value={run.run_id}>
                  {run.run_id}
                </option>
              ))}
            </select>
          </div>
        </form>

        {findings.length === 0 ? (
          <p className="mt-3 border border-dashed border-slate-700 p-6 text-center font-mono text-xs uppercase tracking-wider text-slate-500">
            No findings match — run analysis to create the first findings.
          </p>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-800 text-left font-mono text-[10px] uppercase tracking-widest text-slate-500">
                  <th className="py-2 pr-4">Finding</th>
                  <th className="py-2 pr-4">Kind</th>
                  <th className="py-2 pr-4">Source</th>
                  <th className="py-2 pr-4">Title</th>
                  <th className="py-2 pr-4">Severity</th>
                  <th className="py-2 pr-4">Status</th>
                  <th className="py-2 pr-4">Score</th>
                  <th className="py-2">Events / Evidence</th>
                </tr>
              </thead>
              <tbody>
                {findings.map((finding) => (
                  <tr
                    key={finding.finding_id}
                    onClick={() => navigate(`/cases/${caseId}/findings/${finding.finding_id}`)}
                    className="cursor-pointer border-b border-slate-900 hover:bg-slate-900/70"
                  >
                    <td className="py-3 pr-4 font-mono text-xs text-cyan-400">
                      {finding.finding_id}
                    </td>
                    <td className="py-3 pr-4">
                      <FindingKindBadge kind={finding.kind} />
                    </td>
                    <td className="py-3 pr-4 font-mono text-[11px] text-slate-400">
                      {finding.rule_id ?? finding.model_name ?? "—"}
                    </td>
                    <td className="py-3 pr-4 text-white">{finding.title}</td>
                    <td className="py-3 pr-4">
                      <SeverityBadge severity={finding.severity} />
                    </td>
                    <td className="py-3 pr-4">
                      <FindingStatusBadge status={finding.status} />
                    </td>
                    <td className="py-3 pr-4 font-mono text-xs text-slate-300">
                      {finding.composite_suspicion_score != null
                        ? `CSS ${finding.composite_suspicion_score.toFixed(2)}`
                        : "—"}
                      {finding.anomaly_score != null && (
                        <span className="block text-[10px] text-slate-500">
                          anomaly {finding.anomaly_score.toFixed(2)}
                        </span>
                      )}
                    </td>
                    <td className="py-3 font-mono text-xs text-slate-400">
                      {finding.event_count} / {finding.evidence_count}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="mt-3 flex items-center justify-between">
          <p className="font-mono text-[10px] uppercase tracking-wider text-slate-600">
            Showing {start}–{end} of {total}
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              disabled={offset === 0}
              className="border border-slate-700 px-3 py-1 font-mono text-xs uppercase tracking-widest text-slate-400 hover:text-slate-200 disabled:opacity-40"
            >
              ← Prev
            </button>
            <button
              type="button"
              onClick={() => setOffset(offset + PAGE_SIZE)}
              disabled={offset + PAGE_SIZE >= total}
              className="border border-slate-700 px-3 py-1 font-mono text-xs uppercase tracking-widest text-slate-400 hover:text-slate-200 disabled:opacity-40"
            >
              Next →
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
