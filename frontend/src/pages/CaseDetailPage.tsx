import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { analyzeCase, listAnalysisRuns } from "../api/analysis";
import { getCase, getCaseCustody, updateCase } from "../api/cases";
import { ApiError } from "../api/client";
import {
  controlledIntegrityTest,
  getEvidenceCustody,
  getUploadPolicy,
  listEvidence,
  uploadEvidenceFile,
  verifyEvidence,
} from "../api/evidence";
import { listProcessingRuns, processCase } from "../api/processing";
import { correlateCase, listCorrelationRuns } from "../api/correlation";
import { CaseStatusBadge, EvidenceStatusBadge, IntegrityResultBadge, ProcessingStatusBadge, SeverityBadge } from "../components/Badges";
import CustodyLog from "../components/CustodyLog";
import ErrorBox from "../components/ErrorBox";
import HashBadge from "../components/HashBadge";
import { formatBytes, formatDateTime } from "../state/format";
import {
  CASE_STATUS_OPTIONS,
  EVIDENCE_TYPE_OPTIONS,
  SEVERITY_OPTIONS,
} from "../types/models";
import type {
  AnalysisRun,
  CaseStatus,
  CaseSummary,
  CorrelationRun,
  CustodyEvent,
  EvidenceItem,
  EvidenceType,
  IntegrityTestResult,
  IntegrityVerifyResult,
  ProcessingRun,
  Severity,
  UploadPolicy,
} from "../types/models";
import { HASH_ALGORITHM, INTEGRITY_DISCLAIMER } from "../types/terminology";

const fieldClass =
  "w-full border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-cyan-600 focus:outline-none";

export default function CaseDetailPage(): JSX.Element {
  const { caseId = "" } = useParams();

  const [caseData, setCaseData] = useState<CaseSummary | null>(null);
  const [evidence, setEvidence] = useState<EvidenceItem[]>([]);
  const [runs, setRuns] = useState<ProcessingRun[]>([]);
  const [caseCustody, setCaseCustody] = useState<CustodyEvent[]>([]);
  const [policy, setPolicy] = useState<UploadPolicy | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [evidenceCustody, setEvidenceCustody] = useState<CustodyEvent[]>([]);
  const [verifyResult, setVerifyResult] = useState<IntegrityVerifyResult | null>(null);
  const [testResult, setTestResult] = useState<IntegrityTestResult | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [file, setFile] = useState<File | null>(null);
  const [evidenceType, setEvidenceType] = useState<EvidenceType>("authentication");
  const [source, setSource] = useState("");
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  const [statusDraft, setStatusDraft] = useState<CaseStatus>("Draft");
  const [severityDraft, setSeverityDraft] = useState<Severity>("Medium");
  const [metaError, setMetaError] = useState<string | null>(null);
  const [savingMeta, setSavingMeta] = useState(false);

  const [processingState, setProcessingState] = useState<"idle" | "running">("idle");
  const [processError, setProcessError] = useState<string | null>(null);

  const [analysisRuns, setAnalysisRuns] = useState<AnalysisRun[]>([]);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

  const [corrRuns, setCorrRuns] = useState<CorrelationRun[]>([]);
  const [correlating, setCorrelating] = useState(false);
  const [corrError, setCorrError] = useState<string | null>(null);

  const loadAll = useCallback(() => {
    Promise.all([
      getCase(caseId),
      listEvidence(caseId),
      getCaseCustody(caseId),
      getUploadPolicy(),
      listProcessingRuns(caseId),
      listAnalysisRuns(caseId),
      listCorrelationRuns(caseId),
    ])
      .then(([loadedCase, evidenceList, custody, loadedPolicy, processingRuns, runs, correlationRuns]) => {
        setCaseData(loadedCase);
        setEvidence(evidenceList);
        setCaseCustody(custody);
        setPolicy(loadedPolicy);
        setRuns(processingRuns);
        setAnalysisRuns(runs);
        setCorrRuns(correlationRuns);
        setStatusDraft(loadedCase.status);
        setSeverityDraft(loadedCase.severity);
        setError(null);
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : "Failed to load the case.");
      });
  }, [caseId]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const selectEvidence = (evidenceId: string): void => {
    setSelectedId(evidenceId);
    setVerifyResult(null);
    setTestResult(null);
    setActionError(null);
    getEvidenceCustody(evidenceId)
      .then(setEvidenceCustody)
      .catch((err: unknown) => setActionError(err instanceof ApiError ? err.message : "Failed to load custody."));
  };

  const upload = async (event: React.FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    if (!file) {
      setUploadError("Choose a file to upload.");
      return;
    }
    setUploading(true);
    setUploadError(null);
    try {
      const created = await uploadEvidenceFile(caseId, file, evidenceType, source.trim());
      setFile(null);
      setSource("");
      await loadAll();
      selectEvidence(created.evidence_id);
    } catch (err: unknown) {
      setUploadError(err instanceof ApiError ? err.message : "Upload failed.");
    } finally {
      setUploading(false);
    }
  };

  const runVerify = async (evidenceId: string): Promise<void> => {
    setBusy(true);
    setActionError(null);
    setTestResult(null);
    try {
      setVerifyResult(await verifyEvidence(evidenceId));
      await loadAll();
      setEvidenceCustody(await getEvidenceCustody(evidenceId));
    } catch (err: unknown) {
      setActionError(err instanceof ApiError ? err.message : "Verification failed.");
    } finally {
      setBusy(false);
    }
  };

  const runControlledTest = async (evidenceId: string): Promise<void> => {
    setBusy(true);
    setActionError(null);
    setVerifyResult(null);
    try {
      setTestResult(await controlledIntegrityTest(evidenceId));
      await loadAll();
      setEvidenceCustody(await getEvidenceCustody(evidenceId));
    } catch (err: unknown) {
      setActionError(err instanceof ApiError ? err.message : "Controlled test failed.");
    } finally {
      setBusy(false);
    }
  };

  const saveMeta = async (): Promise<void> => {
    setSavingMeta(true);
    setMetaError(null);
    try {
      const updated = await updateCase(caseId, { status: statusDraft, severity: severityDraft });
      setCaseData(updated);
    } catch (err: unknown) {
      setMetaError(err instanceof ApiError ? err.message : "Failed to update the case.");
    } finally {
      setSavingMeta(false);
    }
  };

  const runProcessing = async (): Promise<void> => {
    setProcessingState("running");
    setProcessError(null);
    try {
      await processCase(caseId, { actor: "ui" });
      await loadAll();
      setSelectedId(null);
    } catch (err: unknown) {
      setProcessError(
        err instanceof ApiError ? err.message : "Evidence processing failed.",
      );
      await loadAll();
    } finally {
      setProcessingState("idle");
    }
  };

  const runAutomatedAnalysis = async (): Promise<void> => {
    setAnalyzing(true);
    setAnalysisError(null);
    try {
      const run = await analyzeCase(caseId, "ui");
      if (run.status === "Failed") {
        setAnalysisError(run.error ?? "Automated analysis failed; see the server logs.");
      }
      await loadAll();
    } catch (err: unknown) {
      setAnalysisError(
        err instanceof ApiError ? err.message : "Automated analysis failed.",
      );
      await loadAll();
    } finally {
      setAnalyzing(false);
    }
  };

  const latestRunFor = (evidenceId: string): ProcessingRun | null =>
    runs.find((run) => run.evidence_id === evidenceId) ?? null;

  const runCorrelation = async (): Promise<void> => {
    setCorrelating(true);
    setCorrError(null);
    try {
      const run = await correlateCase(caseId, "ui");
      if (run.status === "Failed") {
        setCorrError(run.error ?? "Correlation failed; see the server logs.");
      }
      await loadAll();
    } catch (err: unknown) {
      setCorrError(
        err instanceof ApiError ? err.message : "Correlation failed.",
      );
      await loadAll();
    } finally {
      setCorrelating(false);
    }
  };

  const selected = evidence.find((item) => item.evidence_id === selectedId) ?? null;

  if (error) {
    return <ErrorBox message={error} />;
  }
  if (!caseData) {
    return <p className="font-mono text-xs uppercase tracking-widest text-slate-500">Loading case…</p>;
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="font-mono text-xs uppercase tracking-widest text-cyan-500">{caseData.case_id}</p>
          <h1 className="mt-1 text-2xl font-bold text-white">{caseData.name}</h1>
          <p className="mt-1 text-sm text-slate-400">
            Investigator: {caseData.investigator} · Created {formatDateTime(caseData.created_at)}
          </p>
          {caseData.description && <p className="mt-2 max-w-3xl text-sm text-slate-400">{caseData.description}</p>}
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <CaseStatusBadge status={caseData.status} />
            <SeverityBadge severity={caseData.severity} />
            <span className="font-mono text-[11px] uppercase tracking-wider text-slate-500">
              {evidence.length} evidence file{evidence.length === 1 ? "" : "s"}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <Link
            to={`/cases/${caseId}/assistant`}
            className="border border-cyan-700 bg-cyan-950/60 px-4 py-2 font-mono text-xs uppercase tracking-widest text-cyan-300 hover:bg-cyan-900/60"
          >
            Ask assistant →
          </Link>
          <Link
            to="/cases"
            className="border border-slate-700 px-4 py-2 font-mono text-xs uppercase tracking-widest text-slate-400 hover:text-slate-200"
          >
            ← All cases
          </Link>
        </div>
      </div>

      <section className="border border-slate-800 bg-slate-900/50 p-5">
        <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">Case attributes</h2>
        <div className="mt-4 flex flex-wrap items-end gap-4">
          <div>
            <label className="font-mono text-[10px] uppercase tracking-widest text-slate-400" htmlFor="case-status">
              Status
            </label>
            <select
              id="case-status"
              className={`${fieldClass} mt-1 w-44`}
              value={statusDraft}
              onChange={(event) => setStatusDraft(event.target.value as CaseStatus)}
            >
              {CASE_STATUS_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="font-mono text-[10px] uppercase tracking-widest text-slate-400" htmlFor="case-sev">
              Severity
            </label>
            <select
              id="case-sev"
              className={`${fieldClass} mt-1 w-36`}
              value={severityDraft}
              onChange={(event) => setSeverityDraft(event.target.value as Severity)}
            >
              {SEVERITY_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>
          <button
            type="button"
            onClick={() => void saveMeta()}
            disabled={savingMeta}
            className="border border-slate-600 px-4 py-2 font-mono text-xs uppercase tracking-widest text-slate-300 hover:border-cyan-700 hover:text-cyan-300 disabled:opacity-50"
          >
            {savingMeta ? "Saving…" : "Save"}
          </button>
          {metaError && <p className="font-mono text-xs text-red-400">{metaError}</p>}
        </div>
      </section>

      <section className="border border-slate-800 bg-slate-900/50 p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">
            Add evidence — write-once store
          </h2>
          {policy && (
            <p className="font-mono text-[10px] uppercase tracking-wider text-slate-600">
              Max {policy.max_upload_mb} MB · {policy.allowed_extensions.join(", ")} · hashed with{" "}
              {policy.hash_algorithm}
            </p>
          )}
        </div>
        <form onSubmit={(event) => void upload(event)} className="mt-4 grid gap-4 md:grid-cols-3">
          <div className="md:col-span-1">
            <label className="font-mono text-[10px] uppercase tracking-widest text-slate-400" htmlFor="ev-file">
              File *
            </label>
            <input
              id="ev-file"
              type="file"
              className={`${fieldClass} mt-1 file:mr-3 file:border file:border-slate-600 file:bg-slate-800 file:px-2 file:py-1 file:font-mono file:text-[10px] file:uppercase file:text-slate-300`}
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
          </div>
          <div>
            <label className="font-mono text-[10px] uppercase tracking-widest text-slate-400" htmlFor="ev-type">
              Evidence type
            </label>
            <select
              id="ev-type"
              className={`${fieldClass} mt-1`}
              value={evidenceType}
              onChange={(event) => setEvidenceType(event.target.value as EvidenceType)}
            >
              {EVIDENCE_TYPE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="font-mono text-[10px] uppercase tracking-widest text-slate-400" htmlFor="ev-source">
              Source *
            </label>
            <input
              id="ev-source"
              className={`${fieldClass} mt-1`}
              value={source}
              onChange={(event) => setSource(event.target.value)}
              placeholder="Host WS-07, exported by A. Analyst"
              required
            />
            <button
              type="submit"
              disabled={uploading}
              className="mt-3 w-full border border-cyan-700 bg-cyan-950/60 px-4 py-2 font-mono text-xs uppercase tracking-widest text-cyan-300 hover:bg-cyan-900/60 disabled:opacity-50"
            >
              {uploading ? "Uploading…" : "Upload & hash"}
            </button>
          </div>
          {uploadError && (
            <div className="md:col-span-3">
              <ErrorBox message={uploadError} />
            </div>
          )}
        </form>
      </section>

      <section>
        <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">Evidence inventory</h2>
        {evidence.length === 0 ? (
          <p className="mt-3 border border-dashed border-slate-700 p-6 text-center font-mono text-xs uppercase tracking-wider text-slate-500">
            No evidence in this case yet.
          </p>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-800 text-left font-mono text-[10px] uppercase tracking-widest text-slate-500">
                  <th className="py-2 pr-4">Evidence ID</th>
                  <th className="py-2 pr-4">Filename</th>
                  <th className="py-2 pr-4">Type</th>
                  <th className="py-2 pr-4">Size</th>
                  <th className="py-2 pr-4">Status</th>
                  <th className="py-2 pr-4">Rows / OK / Reject</th>
                  <th className="py-2">Uploaded</th>
                </tr>
              </thead>
              <tbody>
                {evidence.map((item) => {
                  const latest = latestRunFor(item.evidence_id);
                  return (
                    <tr
                      key={item.evidence_id}
                      onClick={() => selectEvidence(item.evidence_id)}
                      className={`cursor-pointer border-b border-slate-900 hover:bg-slate-900/70 ${
                        selectedId === item.evidence_id ? "bg-slate-900" : ""
                      }`}
                    >
                      <td className="py-3 pr-4 font-mono text-xs text-cyan-400">{item.evidence_id}</td>
                      <td className="py-3 pr-4 text-white">{item.original_filename}</td>
                      <td className="py-3 pr-4 font-mono text-[11px] uppercase text-slate-400">
                        {EVIDENCE_TYPE_OPTIONS.find((option) => option.value === item.evidence_type)?.label ??
                          item.evidence_type}
                      </td>
                      <td className="py-3 pr-4 font-mono text-slate-400">{formatBytes(item.file_size)}</td>
                      <td className="py-3 pr-4">
                        <EvidenceStatusBadge status={item.status} />
                        {latest && <div className="mt-1"><ProcessingStatusBadge status={latest.status} /></div>}
                      </td>
                      <td className="py-3 pr-4 font-mono text-xs text-slate-400">
                        {item.record_count != null
                          ? `${item.record_count} / ${item.parse_ok ?? 0} / ${item.parse_rejected ?? 0}`
                          : "—"}
                      </td>
                      <td className="py-3 font-mono text-xs text-slate-500">{formatDateTime(item.uploaded_at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="border border-slate-800 bg-slate-900/50 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">
              Processing — parse &amp; normalize
            </h2>
            <p className="mt-1 max-w-2xl text-sm text-slate-500">
              Parses selected evidence with a safe CSV/JSON reader, normalizes rows into the
              common forensic event schema, and records a processing run. Malformed rows are
              retained and explained. Raw evidence bytes are never modified.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Link
              to={`/cases/${caseId}/events`}
              className="border border-cyan-700 bg-cyan-950/60 px-4 py-2 font-mono text-xs uppercase tracking-widest text-cyan-300 hover:bg-cyan-900/60"
            >
              Open events →
            </Link>
            <button
              type="button"
              onClick={() => void runProcessing()}
              disabled={evidence.length === 0 || processingState === "running"}
              className="border border-emerald-700 bg-emerald-950/50 px-4 py-2 font-mono text-xs uppercase tracking-widest text-emerald-300 hover:bg-emerald-900/50 disabled:opacity-50"
            >
              {processingState === "running" ? "Processing…" : "Process case"}
            </button>
          </div>
        </div>

        {processError && (
          <div className="mt-4">
            <ErrorBox message={processError} />
          </div>
        )}

        {runs.length > 0 ? (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-800 text-left font-mono text-[10px] uppercase tracking-widest text-slate-500">
                  <th className="py-2 pr-4">Run</th>
                  <th className="py-2 pr-4">Evidence</th>
                  <th className="py-2 pr-4">Parser</th>
                  <th className="py-2 pr-4">Status</th>
                  <th className="py-2 pr-4">Received</th>
                  <th className="py-2 pr-4">Normalized</th>
                  <th className="py-2 pr-4">Rejected</th>
                  <th className="py-2 pr-4">Duplicates</th>
                  <th className="py-2">Notes</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr key={run.run_id} className="border-b border-slate-900 align-top">
                    <td className="py-3 pr-4 font-mono text-xs text-cyan-400">{run.run_id}</td>
                    <td className="py-3 pr-4">
                      <span className="font-mono text-[11px] text-slate-400">{run.evidence_id}</span>{" "}
                      <span className="text-slate-300">{run.evidence_filename}</span>
                    </td>
                    <td className="py-3 pr-4 font-mono text-[11px] text-slate-400">{run.parser || "—"}</td>
                    <td className="py-3 pr-4">
                      <ProcessingStatusBadge status={run.status} />
                    </td>
                    <td className="py-3 pr-4 font-mono text-xs text-slate-300">{run.records_received}</td>
                    <td className="py-3 pr-4 font-mono text-xs text-slate-300">{run.records_normalized}</td>
                    <td className="py-3 pr-4 font-mono text-xs text-amber-400">{run.records_rejected}</td>
                    <td className="py-3 pr-4 font-mono text-xs text-slate-300">{run.duplicates_detected}</td>
                    <td className="py-3">
                      {run.error ? (
                        <p className="font-mono text-[11px] text-red-400">{run.error}</p>
                      ) : (
                        (run.warnings ?? []).map((warning) => (
                          <p key={warning} className="font-mono text-[11px] text-amber-400/90">
                            {warning}
                          </p>
                        ))
                      )}
                      <p className="mt-1 font-mono text-[10px] text-slate-600">
                        {run.started_at ? formatDateTime(run.started_at) : "—"}
                        {run.completed_at ? ` → ${formatDateTime(run.completed_at)}` : ""}
                      </p>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="mt-4 border border-dashed border-slate-700 p-6 text-center font-mono text-xs uppercase tracking-wider text-slate-500">
            No processing runs yet — upload evidence and process it.
          </p>
        )}
      </section>

      <section className="border border-slate-800 bg-slate-900/50 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">
              Automated analysis — rules + Strategy A anomaly detection
            </h2>
            <p className="mt-1 max-w-2xl text-sm text-slate-500">
              Requires normalized events (run processing first). Scores feature windows with a
              seeded Isolation Forest, evaluates the rule catalog, and fuses both into an
              uncalibrated Composite Suspicion Score. Findings start as New and require
              investigator review; re-analysis appends a run instead of deleting history.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Link
              to={`/cases/${caseId}/findings`}
              className="border border-cyan-700 bg-cyan-950/60 px-4 py-2 font-mono text-xs uppercase tracking-widest text-cyan-300 hover:bg-cyan-900/60"
            >
              Open findings →
            </Link>
            <button
              type="button"
              onClick={() => void runAutomatedAnalysis()}
              disabled={
                runs.length === 0 || analysisRuns.some((run) => run.status === "Running") || analyzing
              }
              className="border border-violet-700 bg-violet-950/50 px-4 py-2 font-mono text-xs uppercase tracking-widest text-violet-300 hover:bg-violet-900/50 disabled:opacity-50"
              title={runs.length === 0 ? "Process evidence before running analysis." : undefined}
            >
              {analyzing ? "Analyzing…" : "Run analysis"}
            </button>
          </div>
        </div>

        {analysisError && (
          <div className="mt-4">
            <ErrorBox message={analysisError} />
          </div>
        )}

        {analysisRuns.length > 0 ? (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-800 text-left font-mono text-[10px] uppercase tracking-widest text-slate-500">
                  <th className="py-2 pr-4">Run</th>
                  <th className="py-2 pr-4">Status</th>
                  <th className="py-2 pr-4">Finished</th>
                  <th className="py-2 pr-4">Windows</th>
                  <th className="py-2 pr-4">Rule findings</th>
                  <th className="py-2">ML findings</th>
                </tr>
              </thead>
              <tbody>
                {analysisRuns.map((run) => {
                  const stats = (run.stats ?? {}) as Record<string, unknown>;
                  return (
                    <tr key={run.run_id} className="border-b border-slate-900 align-top">
                      <td className="py-3 pr-4 font-mono text-xs text-cyan-400">{run.run_id}</td>
                      <td className="py-3 pr-4">
                        <ProcessingStatusBadge status={run.status} />
                      </td>
                      <td className="py-3 pr-4 font-mono text-xs text-slate-400">
                        {run.finished_at ? formatDateTime(run.finished_at) : "—"}
                      </td>
                      <td className="py-3 pr-4 font-mono text-xs text-slate-300">
                        {typeof stats.windows_total === "number" ? stats.windows_total : "—"}
                      </td>
                      <td className="py-3 pr-4 font-mono text-xs text-slate-300">
                        {typeof stats.rule_findings === "number" ? stats.rule_findings : "—"}
                      </td>
                      <td className="py-3 font-mono text-xs text-slate-300">
                        {typeof stats.ml_findings === "number" ? stats.ml_findings : "—"}
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
      </section>

      <section className="border border-slate-800 bg-slate-900/50 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">
              Cross-source correlation — links, groups, timeline &amp; evidence graph
            </h2>
            <p className="mt-1 max-w-2xl text-sm text-slate-500">
              Links normalized events that share a host, user, source IP, or typed process
              relation inside a time window, clusters them into activity groups, and
              reconstructs the incident timeline and evidence graph for investigation.
              Re-correlation appends a run; history is never rewritten.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Link
              to={`/cases/${caseId}/investigation`}
              className="border border-cyan-700 bg-cyan-950/60 px-4 py-2 font-mono text-xs uppercase tracking-widest text-cyan-300 hover:bg-cyan-900/60"
            >
              Open investigation →
            </Link>
            <button
              type="button"
              onClick={() => void runCorrelation()}
              disabled={runs.length === 0 || correlating}
              className="border border-teal-700 bg-teal-950/50 px-4 py-2 font-mono text-xs uppercase tracking-widest text-teal-300 hover:bg-teal-900/50 disabled:opacity-50"
              title={runs.length === 0 ? "Process evidence before running correlation." : undefined}
            >
              {correlating ? "Correlating…" : "Run correlation"}
            </button>
          </div>
        </div>

        {corrError && (
          <div className="mt-4">
            <ErrorBox message={corrError} />
          </div>
        )}

        {corrRuns.length > 0 ? (
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
                {corrRuns.map((run) => {
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
                        {typeof stats.links === "number" ? stats.links : "—"}
                      </td>
                      <td className="py-3 font-mono text-xs text-slate-300">
                        {typeof stats.groups === "number" ? stats.groups : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="mt-4 border border-dashed border-slate-700 p-6 text-center font-mono text-xs uppercase tracking-wider text-slate-500">
            No correlation runs yet — process evidence, then run correlation.
          </p>
        )}
      </section>

      {selected && (
        <section className="border border-slate-800 bg-slate-900/50 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="font-mono text-xs uppercase tracking-widest text-cyan-500">{selected.evidence_id}</p>
              <h2 className="text-lg font-semibold text-white">{selected.original_filename}</h2>
              <p className="mt-1 text-sm text-slate-400">
                Source: {selected.source_description} · MIME: {selected.mime_type}
              </p>
            </div>
            <EvidenceStatusBadge status={selected.status} />
          </div>

          <div className="mt-4 space-y-2">
            <div className="flex flex-wrap items-center gap-3">
              <span className="font-mono text-[10px] uppercase tracking-widest text-slate-500">
                {HASH_ALGORITHM} (recorded)
              </span>
              <HashBadge value={selected.sha256} full />
            </div>
            <p className="max-w-3xl font-mono text-[10px] leading-relaxed text-slate-500">
              {INTEGRITY_DISCLAIMER}
            </p>
          </div>

          <div className="mt-4 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => void runVerify(selected.evidence_id)}
              disabled={busy}
              className="border border-emerald-700 bg-emerald-950/50 px-4 py-2 font-mono text-xs uppercase tracking-widest text-emerald-300 hover:bg-emerald-900/50 disabled:opacity-50"
            >
              Verify integrity
            </button>
            <button
              type="button"
              onClick={() => void runControlledTest(selected.evidence_id)}
              disabled={busy}
              className="border border-amber-700 bg-amber-950/50 px-4 py-2 font-mono text-xs uppercase tracking-widest text-amber-300 hover:bg-amber-900/50 disabled:opacity-50"
              title="Creates a mutated demonstration copy outside the raw evidence directory."
            >
              Controlled integrity test
            </button>
          </div>

          {actionError && (
            <div className="mt-4">
              <ErrorBox message={actionError} />
            </div>
          )}

          {verifyResult && (
            <div className="mt-4 border border-slate-800 bg-slate-950/70 p-4">
              <div className="flex flex-wrap items-center gap-3">
                <IntegrityResultBadge result={verifyResult.result} />
                <span className="font-mono text-[11px] text-slate-500">
                  verified_at {formatDateTime(verifyResult.verified_at)}
                </span>
              </div>
              <div className="mt-3 space-y-2">
                <div className="flex flex-wrap items-center gap-3">
                  <span className="font-mono text-[10px] uppercase text-slate-500">computed</span>
                  <HashBadge value={verifyResult.computed_hash} full />
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <span className="font-mono text-[10px] uppercase text-slate-500">recorded</span>
                  <HashBadge value={verifyResult.expected_hash} full />
                </div>
              </div>
              <p className="mt-3 text-sm text-slate-400">{verifyResult.note}</p>
            </div>
          )}

          {testResult && (
            <div className="mt-4 border border-amber-900 bg-amber-950/30 p-4">
              <p className="font-mono text-[10px] uppercase tracking-widest text-amber-500">
                {testResult.operation}
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <IntegrityResultBadge result={testResult.result} />
                <span className="font-mono text-[11px] text-slate-500">
                  original unchanged: {testResult.original_unchanged ? "yes" : "no"}
                </span>
              </div>
              <div className="mt-3 space-y-2">
                <div className="flex flex-wrap items-center gap-3">
                  <span className="font-mono text-[10px] uppercase text-slate-500">test copy hash</span>
                  <HashBadge value={testResult.test_copy_hash} full />
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <span className="font-mono text-[10px] uppercase text-slate-500">recorded hash</span>
                  <HashBadge value={testResult.recorded_hash} full />
                </div>
              </div>
              <p className="mt-3 text-sm text-slate-400">{testResult.note}</p>
            </div>
          )}

          <div className="mt-6">
            <CustodyLog events={evidenceCustody} title="Evidence chain of custody" />
          </div>
        </section>
      )}

      <section className="border border-slate-800 bg-slate-900/50 p-5">
        <CustodyLog events={caseCustody} title="Case chain of custody" />
      </section>
    </div>
  );
}
