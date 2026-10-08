import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { askAssistant, listAssistantHistory } from "../api/assistant";
import { ApiError } from "../api/client";
import ErrorBox from "../components/ErrorBox";
import { formatDateTime } from "../state/format";
import type { AssistantQueryResult, AssistantSource } from "../types/models";
import { ASSISTANT_SUGGESTED_QUESTIONS } from "../types/models";
import { ASSISTANT_EMPTY_CASE, ASSISTANT_UNSUPPORTED, ASSISTANT_FOOTER } from "../types/terminology";

const fieldClass =
  "w-full border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-cyan-600 focus:outline-none";

const INTENT_LABELS: Record<string, string> = {
  CASE_SUMMARY: "Case summary",
  TOP_FINDINGS: "Top findings",
  FINDING_EXPLANATION: "Finding explanation",
  FINDING_TRACE: "Finding trace",
  EVIDENCE_SUPPORT: "Evidence support",
  TIMELINE_CONTEXT: "Timeline context",
  CORRELATION_SUMMARY: "Correlations",
  GROUP_SUMMARY: "Activity groups",
  ML_EXPLANATION: "ML explanation",
  REVIEW_QUEUE: "Review queue",
  INTEGRITY_STATUS: "Integrity",
  PROCESSING_STATUS: "Processing",
  CAPABILITIES: "Capabilities",
  UNKNOWN: "Unsupported",
};

const CONFIDENCE_STYLES: Record<string, string> = {
  HIGH: "border-emerald-700 bg-emerald-950/40 text-emerald-300",
  MEDIUM: "border-amber-700 bg-amber-950/40 text-amber-300",
  LOW: "border-slate-700 bg-slate-800/60 text-slate-400",
};

function sourceHref(caseId: string, source: AssistantSource): string | null {
  switch (source.type) {
    case "finding":
      return `/cases/${caseId}/findings/${encodeURIComponent(source.id)}`;
    case "correlation":
    case "group":
      return `/cases/${caseId}/investigation`;
    case "event":
      return `/cases/${caseId}/events`;
    case "evidence":
      return `/cases/${caseId}`;
    default:
      return null;
  }
}

function SourceChips({ caseId, sources }: { caseId: string; sources: AssistantSource[] }): JSX.Element | null {
  if (!sources.length) return null;
  return (
    <div className="mt-4">
      <p className="font-mono text-[10px] uppercase tracking-widest text-slate-500">Cited sources</p>
      <div className="mt-2 flex flex-wrap gap-2">
        {sources.map((source) => {
          const href = sourceHref(caseId, source);
          const label = `${source.type}:${source.id}`;
          const chipClass =
            "inline-flex items-center gap-2 border px-2 py-1 font-mono text-[10px] uppercase tracking-wider";
          if (!href) {
            return (
              <span key={`${source.type}-${source.id}`} className={`${chipClass} border-slate-700 text-slate-400`}>
                {label}
              </span>
            );
          }
          return (
            <Link
              key={`${source.type}-${source.id}`}
              to={href}
              className={`${chipClass} border-cyan-700 bg-cyan-950/40 text-cyan-300 hover:bg-cyan-900/40`}
            >
              {label}
            </Link>
          );
        })}
      </div>
    </div>
  );
}

function AnswerPanel({ caseId, row }: { caseId: string; row: AssistantQueryResult }): JSX.Element {
  const hasEmpty = row.answer === ASSISTANT_EMPTY_CASE;
  const hasUnsupported = row.answer === ASSISTANT_UNSUPPORTED;
  return (
    <section className="border border-slate-800 bg-slate-900/50 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">
            {INTENT_LABELS[row.intent] ?? row.intent}
          </h2>
          <p className="mt-2 font-mono text-xs text-cyan-400">#{row.query_id}</p>
        </div>
        <span className={`border px-2 py-1 font-mono text-[10px] uppercase tracking-widest ${CONFIDENCE_STYLES[row.confidence] ?? CONFIDENCE_STYLES.LOW}`}>
          confidence {row.confidence}
        </span>
      </div>

      <div
        className="mt-4 whitespace-pre-wrap border border-slate-800 bg-slate-950/70 p-4 text-sm leading-relaxed text-slate-200"
        data-testid="assistant-answer"
      >
        {row.answer}
      </div>

      {(row.evidence ?? []).length > 0 && (
        <div className="mt-4">
          <p className="font-mono text-[10px] uppercase tracking-widest text-slate-500">Evidence basis</p>
          <ul className="mt-2 space-y-1 font-mono text-xs text-slate-400">
            {row.evidence.map((line) => (
              <li key={line} className="break-all">
                • {line}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-4">
        <p className="font-mono text-[10px] uppercase tracking-widest text-slate-500">Basis</p>
        <ul className="mt-2 space-y-1 text-xs text-slate-400">
          {(row.basis ?? []).map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </div>

      <SourceChips caseId={caseId} sources={row.sources ?? []} />

      {!hasEmpty && !hasUnsupported && (
        <p className="mt-4 font-mono text-[10px] uppercase tracking-wider text-slate-600">{ASSISTANT_FOOTER}</p>
      )}
      {row.created_at && (
        <p className="mt-2 font-mono text-[10px] text-slate-600">asked {formatDateTime(row.created_at)}</p>
      )}
    </section>
  );
}

export default function AssistantPage(): JSX.Element {
  const { caseId = "" } = useParams();

  const [question, setQuestion] = useState("");
  const [current, setCurrent] = useState<AssistantQueryResult | null>(null);
  const [history, setHistory] = useState<AssistantQueryResult[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);

  const refreshHistory = useCallback((): Promise<void> => {
    return listAssistantHistory(caseId, 100)
      .then(setHistory)
      .catch(() => {
        // History is best-effort; the last answer still renders.
      });
  }, [caseId]);

  useEffect(() => {
    void refreshHistory();
  }, [refreshHistory]);

  const ask = async (text?: string): Promise<void> => {
    const trimmed = (text ?? question).trim();
    if (!trimmed) {
      setError("Type a question first.");
      return;
    }
    setAsking(true);
    setError(null);
    try {
      const row = await askAssistant(caseId, trimmed, "ui");
      setCurrent(row);
      setQuestion("");
      await refreshHistory();
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "The assistant could not answer the question.");
      if (err instanceof ApiError && err.code === "FINDING_NOT_FOUND") {
        setError(`${err.message} The finding does not exist in this case - references are case-scoped.`);
      }
    } finally {
      setAsking(false);
    }
  };

  const pickHistory = (row: AssistantQueryResult): void => {
    setCurrent(row);
    setError(null);
  };

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="font-mono text-xs uppercase tracking-widest text-cyan-500">{caseId}</p>
          <h1 className="mt-1 text-2xl font-bold text-white">Investigation assistant</h1>
          <p className="mt-1 max-w-3xl text-sm text-slate-400">
            Evidence-traceable answers reconstructed only from this case's processed evidence.
            No generative model is enabled — every answer is deterministic and cites its sources.
          </p>
        </div>
        <Link
          to={`/cases/${caseId}`}
          className="border border-slate-700 px-4 py-2 font-mono text-xs uppercase tracking-widest text-slate-400 hover:text-slate-200"
        >
          ← Case overview
        </Link>
      </div>

      <section className="border border-slate-800 bg-slate-900/50 p-5">
        <label className="font-mono text-[10px] uppercase tracking-widest text-slate-400" htmlFor="assistant-question">
          Ask a question
        </label>
        <div className="mt-2">
          <textarea
            id="assistant-question"
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
          <button
            type="button"
            onClick={() => setQuestion("What can you help me with?")}
            className="border border-slate-700 px-4 py-2 font-mono text-xs uppercase tracking-widest text-slate-400 hover:text-slate-200"
          >
            Show capabilities
          </button>
        </div>
        {error && (
          <div className="mt-4">
            <ErrorBox message={error} />
          </div>
        )}
        <div className="mt-4">
          <p className="font-mono text-[10px] uppercase tracking-widest text-slate-500">Suggested questions</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {ASSISTANT_SUGGESTED_QUESTIONS.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                onClick={() => void ask(suggestion)}
                disabled={asking}
                className="border border-slate-800 bg-slate-900 px-3 py-1.5 text-left font-mono text-[11px] text-slate-400 hover:border-cyan-800 hover:text-cyan-300 disabled:opacity-50"
              >
                {suggestion}
              </button>
            ))}
          </div>
        </div>
      </section>

      {current && <AnswerPanel caseId={caseId} row={current} />}

      <section>
        <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">Question history (append-only)</h2>
        {history.length === 0 ? (
          <p className="mt-3 border border-dashed border-slate-700 p-6 text-center font-mono text-xs uppercase tracking-wider text-slate-500">
            No assistant questions yet for this case.
          </p>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-800 text-left font-mono text-[10px] uppercase tracking-widest text-slate-500">
                  <th className="py-2 pr-4">#</th>
                  <th className="py-2 pr-4">Question</th>
                  <th className="py-2 pr-4">Intent</th>
                  <th className="py-2 pr-4">Confidence</th>
                  <th className="py-2">Asked</th>
                </tr>
              </thead>
              <tbody>
                {history.map((row) => (
                  <tr
                    key={row.query_id}
                    onClick={() => pickHistory(row)}
                    className={`cursor-pointer border-b border-slate-900 hover:bg-slate-900/70 ${
                      current?.query_id === row.query_id ? "bg-slate-900" : ""
                    }`}
                  >
                    <td className="py-3 pr-4 font-mono text-xs text-cyan-400">#{row.query_id}</td>
                    <td className="py-3 pr-4 text-white">{row.question}</td>
                    <td className="py-3 pr-4 font-mono text-[11px] uppercase text-slate-400">
                      {INTENT_LABELS[row.intent] ?? row.intent}
                    </td>
                    <td className="py-3 pr-4">
                      <span className={`border px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest ${CONFIDENCE_STYLES[row.confidence] ?? CONFIDENCE_STYLES.LOW}`}>
                        {row.confidence}
                      </span>
                    </td>
                    <td className="py-3 font-mono text-xs text-slate-500">
                      {row.created_at ? formatDateTime(row.created_at) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}