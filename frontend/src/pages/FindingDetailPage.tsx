import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getFinding, getFindingTrace, reviewFinding } from "../api/analysis";
import { ApiError } from "../api/client";
import {
  FindingKindBadge,
  FindingStatusBadge,
  SeverityBadge,
  SuspicionBandBadge,
} from "../components/Badges";
import ErrorBox from "../components/ErrorBox";
import HashBadge from "../components/HashBadge";
import { formatDateTime } from "../state/format";
import type {
  FindingDetail,
  FindingStatus,
  FindingTrace,
} from "../types/models";
import { ALLOWED_STATUS_TRANSITIONS } from "../types/models";
import {
  ANOMALY_DISCLAIMER,
  ANOMALY_SCORE_DESCRIPTION,
  FUSION_DISCLAIMER,
  RULE_CONFIDENCE_NOTE,
  TRACEABILITY_STEPS,
} from "../types/terminology";

const labelClass = "font-mono text-[10px] uppercase tracking-widest text-slate-500";
const fieldClass =
  "w-full border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 focus:border-cyan-600 focus:outline-none";

const asString = (value: unknown): string | null => (typeof value === "string" ? value : null);

function FeatureTable({ snapshot }: { snapshot: Record<string, unknown> }): JSX.Element {
  const rows = Object.entries(snapshot).filter(
    ([key]) => !["feature_version", "window_start", "window_end"].includes(key),
  );
  return (
    <div className="mt-3 overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-slate-800 text-left font-mono text-[10px] uppercase tracking-widest text-slate-500">
            <th className="py-2 pr-4">Feature ({rows.length})</th>
            <th className="py-2">Value</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([name, value]) => (
            <tr key={name} className="border-b border-slate-900">
              <td className="py-1.5 pr-4 font-mono text-[11px] text-slate-400">{name}</td>
              <td className="py-1.5 font-mono text-[11px] text-slate-200">
                {String(value)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function FindingDetailPage(): JSX.Element {
  const { caseId = "", findingId = "" } = useParams();

  const [detail, setDetail] = useState<FindingDetail | null>(null);
  const [trace, setTrace] = useState<FindingTrace | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [statusDraft, setStatusDraft] = useState<FindingStatus>("New");
  const [note, setNote] = useState("");
  const [author, setAuthor] = useState("investigator");
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [reviewNotice, setReviewNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    Promise.all([getFinding(caseId, findingId), getFindingTrace(caseId, findingId)])
      .then(([finding, findingTrace]) => {
        setDetail(finding);
        setTrace(findingTrace);
        setStatusDraft(finding.status);
        setError(null);
      })
      .catch((err: unknown) =>
        setError(err instanceof ApiError ? err.message : "Failed to load the finding."),
      );
  }, [caseId, findingId]);

  useEffect(() => {
    load();
  }, [load]);

  const submitReview = async (event: React.FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    setBusy(true);
    setReviewError(null);
    setReviewNotice(null);
    try {
      const updated = await reviewFinding(caseId, findingId, {
        status: statusDraft,
        note: note.trim() || undefined,
        author: author.trim() || "investigator",
      });
      setDetail(updated);
      setNote("");
      setReviewNotice(`Status updated to ${updated.status} (recorded in chain of custody).`);
    } catch (err: unknown) {
      setReviewError(
        err instanceof ApiError ? err.message : "Review update failed.",
      );
    } finally {
      setBusy(false);
    }
  };

  if (error) {
    return <ErrorBox message={error} />;
  }
  if (!detail) {
    return (
      <p className="font-mono text-xs uppercase tracking-widest text-slate-500">
        Loading finding…
      </p>
    );
  }

  const components = detail.components;
  const transitions = ALLOWED_STATUS_TRANSITIONS[detail.status];
  const explanation = detail.explanation;
  const explanationText =
    typeof explanation === "string"
      ? explanation
      : asString((explanation as Record<string, unknown> | null)?.summary);
  const snapshot = detail.feature_snapshot;

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="font-mono text-xs uppercase tracking-widest text-cyan-500">
            {caseId} · {detail.finding_id}
          </p>
          <h1 className="mt-1 text-2xl font-bold text-white">{detail.title}</h1>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <FindingKindBadge kind={detail.kind} />
            <SeverityBadge severity={detail.severity} />
            <FindingStatusBadge status={detail.status} />
            {components && (
              <SuspicionBandBadge
                band={components.band}
                score={detail.composite_suspicion_score}
              />
            )}
            <span className="font-mono text-[11px] uppercase tracking-wider text-slate-500">
              {detail.rule_id ?? `${detail.model_name} ${detail.model_version ?? ""}`}
            </span>
            {detail.run_id && (
              <span className="font-mono text-[11px] uppercase tracking-wider text-slate-500">
                run {detail.run_id}
              </span>
            )}
          </div>
          <p className="mt-2 text-sm text-slate-500">
            {detail.timestamp_start
              ? `${formatDateTime(detail.timestamp_start)}${
                  detail.timestamp_end ? ` → ${formatDateTime(detail.timestamp_end)}` : ""
                }`
              : "No time range recorded"}
            {" · "}
            updated {formatDateTime(detail.updated_at)}
          </p>
        </div>
        <Link
          to={`/cases/${caseId}/findings`}
          className="border border-slate-700 px-4 py-2 font-mono text-xs uppercase tracking-widest text-slate-400 hover:text-slate-200"
        >
          ← Findings
        </Link>
      </div>

      <section className="border border-slate-800 bg-slate-900/50 p-5">
        <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">
          Explanation
        </h2>
        {explanationText ? (
          <p className="mt-3 max-w-4xl text-sm leading-relaxed text-slate-300">
            {explanationText}
          </p>
        ) : (
          <p className="mt-3 font-mono text-xs text-slate-500">No explanation recorded.</p>
        )}
        {detail.reasons && detail.reasons.length > 0 && (
          <ul className="mt-3 space-y-1">
            {detail.reasons.map((reason) => (
              <li key={reason} className="text-sm text-slate-400">
                · {reason}
              </li>
            ))}
          </ul>
        )}
        {detail.kind === "rule" && (
          <p className="mt-3 font-mono text-[11px] text-slate-600">{RULE_CONFIDENCE_NOTE}</p>
        )}
      </section>

      {components && (
        <section className="border border-slate-800 bg-slate-900/50 p-5">
          <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">
            Composite Suspicion Score — {components.formula_version}
          </h2>
          <p className="mt-2 font-mono text-[11px] text-slate-500">{components.formula}</p>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-800 text-left font-mono text-[10px] uppercase tracking-widest text-slate-500">
                  <th className="py-2 pr-4">Component</th>
                  <th className="py-2 pr-4">Weight</th>
                  <th className="py-2 pr-4">Value</th>
                  <th className="py-2">Contribution</th>
                </tr>
              </thead>
              <tbody>
                {(["rule", "anomaly", "correlation"] as const).map((key) => {
                  const component = components.components[key];
                  const weight = components.weights[key] ?? 0;
                  return (
                    <tr key={key} className="border-b border-slate-900">
                      <td className="py-2 pr-4 font-mono text-xs text-slate-300">{key}</td>
                      <td className="py-2 pr-4 font-mono text-xs text-slate-400">
                        {weight.toFixed(2)}
                        {key === "rule" && component.severity
                          ? ` · ${component.severity}`
                          : ""}
                        {key === "correlation" && component.distinct_evidence != null
                          ? ` · ${component.distinct_evidence} evidence`
                          : ""}
                      </td>
                      <td className="py-2 pr-4 font-mono text-xs text-slate-400">
                        {component.value.toFixed(4)}
                      </td>
                      <td className="py-2 font-mono text-xs text-slate-300">
                        {component.contribution.toFixed(4)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <span className={labelClass}>Total</span>
            <SuspicionBandBadge
              band={components.band}
              score={detail.composite_suspicion_score}
            />
          </div>
          <p className="mt-3 max-w-3xl font-mono text-[11px] leading-relaxed text-slate-600">
            {FUSION_DISCLAIMER}
          </p>
        </section>
      )}

      {detail.kind === "ml" && (
        <section className="border border-slate-800 bg-slate-900/50 p-5">
          <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">
            ML window evidence
          </h2>
          <div className="mt-3 flex flex-wrap gap-x-6 gap-y-2 font-mono text-xs text-slate-400">
            <span>
              <span className={labelClass}>Anomaly score </span>
              {detail.anomaly_score?.toFixed(4) ?? "—"}
            </span>
            <span>
              <span className={labelClass}>Threshold </span>
              {detail.threshold ?? "—"}
            </span>
            <span>
              <span className={labelClass}>Model </span>
              {detail.model_name} {detail.model_version}
            </span>
            <span>
              <span className={labelClass}>Features </span>
              {detail.feature_version ?? "—"}
            </span>
            {snapshot && (
              <span>
                <span className={labelClass}>Window </span>
                {String(snapshot.window_start ?? "")} → {String(snapshot.window_end ?? "")}
              </span>
            )}
          </div>
          <p className="mt-3 max-w-3xl font-mono text-[11px] leading-relaxed text-slate-600">
            {ANOMALY_SCORE_DESCRIPTION} {ANOMALY_DISCLAIMER}
          </p>
          {snapshot && <FeatureTable snapshot={snapshot} />}
        </section>
      )}

      <section className="border border-slate-800 bg-slate-900/50 p-5">
        <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">
          Investigator review
        </h2>
        <p className="mt-1 max-w-3xl text-sm text-slate-500">
          The system never confirms or dismisses findings on its own. Every transition below is
          an investigator action recorded in the chain of custody.
        </p>
        <form onSubmit={(event) => void submitReview(event)} className="mt-4 grid gap-4 md:grid-cols-3">
          <div>
            <label className={labelClass} htmlFor="rev-status">
              New status
            </label>
            <select
              id="rev-status"
              className={`${fieldClass} mt-1`}
              value={statusDraft}
              onChange={(event) => setStatusDraft(event.target.value as FindingStatus)}
            >
              <option value={detail.status}>{detail.status} (current)</option>
              {transitions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className={labelClass} htmlFor="rev-author">
              Investigator
            </label>
            <input
              id="rev-author"
              className={`${fieldClass} mt-1`}
              value={author}
              onChange={(event) => setAuthor(event.target.value)}
            />
          </div>
          <div className="md:col-span-1">
            <label className={labelClass} htmlFor="rev-note">
              Note
            </label>
            <input
              id="rev-note"
              className={`${fieldClass} mt-1`}
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder="Why this transition…"
            />
          </div>
          <div className="md:col-span-3">
            <button
              type="submit"
              disabled={busy || statusDraft === detail.status}
              className="border border-cyan-700 bg-cyan-950/60 px-4 py-2 font-mono text-xs uppercase tracking-widest text-cyan-300 hover:bg-cyan-900/60 disabled:opacity-50"
            >
              {busy ? "Saving…" : "Record review"}
            </button>
          </div>
        </form>
        {reviewError && (
          <div className="mt-4">
            <ErrorBox message={reviewError} />
          </div>
        )}
        {reviewNotice && (
          <p className="mt-4 border border-emerald-800 bg-emerald-950/40 px-4 py-2 font-mono text-xs text-emerald-300">
            {reviewNotice}
          </p>
        )}
        {detail.notes.length > 0 && (
          <div className="mt-4 space-y-2">
            {detail.notes.map((entry) => (
              <div
                key={`${entry.author}-${entry.created_at}`}
                className="border border-slate-800 bg-slate-950/60 px-4 py-2"
              >
                <p className="font-mono text-[10px] uppercase tracking-wider text-slate-500">
                  {entry.author} · {formatDateTime(entry.created_at)}
                </p>
                <p className="mt-1 text-sm text-slate-300">{entry.body}</p>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="border border-slate-800 bg-slate-900/50 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">
            Traceability — finding to raw evidence
          </h2>
          <div className="flex flex-wrap gap-2">
            {TRACEABILITY_STEPS.map((step, index) => (
              <span
                key={step}
                className="border border-slate-700 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-slate-500"
              >
                {index + 1}. {step}
              </span>
            ))}
          </div>
        </div>

        {trace && trace.events.length > 0 ? (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-800 text-left font-mono text-[10px] uppercase tracking-widest text-slate-500">
                  <th className="py-2 pr-4">Event time</th>
                  <th className="py-2 pr-4">Event</th>
                  <th className="py-2 pr-4">Context</th>
                  <th className="py-2 pr-4">Raw record</th>
                  <th className="py-2">Evidence</th>
                </tr>
              </thead>
              <tbody>
                {trace.events.map((event) => (
                  <tr key={event.event_id} className="border-b border-slate-900 align-top">
                    <td className="py-3 pr-4 font-mono text-[11px] text-slate-400">
                      {event.timestamp ? formatDateTime(event.timestamp) : "—"}
                    </td>
                    <td className="py-3 pr-4">
                      <span className="font-mono text-[11px] uppercase text-cyan-500">
                        {event.source_type}
                      </span>
                      <span className="ml-2 font-mono text-[11px] text-slate-300">
                        {event.action ?? event.event_type}
                      </span>
                      <p className="font-mono text-[10px] text-slate-600">{event.event_id}</p>
                    </td>
                    <td className="py-3 pr-4 font-mono text-[11px] text-slate-400">
                      {event.user ?? "—"} @ {event.host ?? "—"}
                      {event.file_path && (
                        <p className="max-w-xs truncate text-slate-500">{event.file_path}</p>
                      )}
                      {event.process && (
                        <p className="max-w-xs truncate text-slate-500">{event.process}</p>
                      )}
                    </td>
                    <td className="py-3 pr-4 font-mono text-[11px] text-slate-400">
                      {event.raw_record ? (
                        <>
                          <span className="text-slate-500">row {event.raw_record.row_index}</span>
                          <p className="max-w-sm truncate text-slate-300">
                            {event.raw_record.content}
                          </p>
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="py-3 font-mono text-[11px]">
                      {event.evidence ? (
                        <>
                          <span className="text-cyan-500">{event.evidence.evidence_id}</span>
                          <p className="text-slate-500">{event.evidence.original_filename}</p>
                          <div className="mt-1">
                            <HashBadge value={event.evidence.sha256} />
                          </div>
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="mt-4 border border-dashed border-slate-700 p-6 text-center font-mono text-xs uppercase tracking-wider text-slate-500">
            No linked events for this finding.
          </p>
        )}

        {detail.evidence.length > 0 && (
          <div className="mt-5">
            <h3 className={labelClass}>Supporting evidence files</h3>
            <div className="mt-2 overflow-x-auto">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="border-b border-slate-800 text-left font-mono text-[10px] uppercase tracking-widest text-slate-500">
                    <th className="py-2 pr-4">Evidence</th>
                    <th className="py-2 pr-4">Filename</th>
                    <th className="py-2 pr-4">Size</th>
                    <th className="py-2">SHA-256</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.evidence.map((item) => (
                    <tr key={item.evidence_id} className="border-b border-slate-900">
                      <td className="py-2 pr-4 font-mono text-xs text-cyan-400">
                        {item.evidence_id}
                      </td>
                      <td className="py-2 pr-4 text-slate-300">{item.original_filename}</td>
                      <td className="py-2 pr-4 font-mono text-xs text-slate-400">
                        {item.file_size} B
                      </td>
                      <td className="py-2">
                        <HashBadge value={item.sha256} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
