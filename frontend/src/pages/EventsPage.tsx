import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getCase } from "../api/cases";
import { ApiError } from "../api/client";
import { listEvidence } from "../api/evidence";
import { getEvent, listEvents } from "../api/processing";
import { SeverityBadge, SourceTypeBadge } from "../components/Badges";
import ErrorBox from "../components/ErrorBox";
import HashBadge from "../components/HashBadge";
import { formatDateTime } from "../state/format";
import type {
  CaseSummary,
  EventDetail,
  EventListResult,
  EventQuery,
  EvidenceItem,
  ForensicEvent,
} from "../types/models";
import { SEVERITY_OPTIONS, SOURCE_TYPE_OPTIONS } from "../types/models";

const fieldClass =
  "w-full border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 placeholder-slate-600 focus:border-cyan-600 focus:outline-none";

const labelClass = "mb-1 block font-mono text-[10px] uppercase tracking-widest text-slate-400";

const PAGE_SIZE = 50;

const emptyQuery = (): EventQuery => ({
  source_type: "",
  severity: "",
  event_type: "",
  user: "",
  host: "",
  timestamp_from: "",
  timestamp_to: "",
  evidence_id: "",
});

export default function EventsPage(): JSX.Element {
  const { caseId = "" } = useParams();

  const [caseData, setCaseData] = useState<CaseSummary | null>(null);
  const [result, setResult] = useState<EventListResult | null>(null);
  const [evidenceList, setEvidenceList] = useState<EvidenceItem[]>([]);
  const [query, setQuery] = useState<EventQuery>(emptyQuery);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<EventDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    listEvents(caseId, { ...query, limit: PAGE_SIZE, offset })
      .then(setResult)
      .catch((err: unknown) =>
        setError(err instanceof ApiError ? err.message : "Failed to load events."),
      )
      .finally(() => setLoading(false));
  }, [caseId, query, offset]);

  useEffect(() => {
    Promise.all([getCase(caseId), listEvidence(caseId)])
      .then(([loadedCase, evidence]) => {
        setCaseData(loadedCase);
        setEvidenceList(evidence);
      })
      .catch((err: unknown) =>
        setError(err instanceof ApiError ? err.message : "Failed to load the case."),
      );
  }, [caseId]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    setOffset(0);
  }, [query]);

  const openEvent = (eventId: string): void => {
    setSelectedId(eventId);
    setDetail(null);
    setDetailError(null);
    setDetailLoading(true);
    getEvent(caseId, eventId)
      .then(setDetail)
      .catch((err: unknown) =>
        setDetailError(err instanceof ApiError ? err.message : "Failed to load the event."),
      )
      .finally(() => setDetailLoading(false));
  };

  const applyFilters = (event: React.FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    setOffset(0);
    load();
  };

  const resetFilters = (): void => {
    setQuery(emptyQuery());
    setOffset(0);
  };

  const set = (key: keyof EventQuery, value: string): void => {
    setQuery((previous) => ({ ...previous, [key]: value }));
  };

  const events = result?.events ?? [];
  const selectedEvent = events.find((event) => event.event_id === selectedId) ?? null;
  const start = result ? Math.min(offset + 1, result.total) : 0;
  const end = result ? Math.min(offset + events.length, result.total) : 0;

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="font-mono text-xs uppercase tracking-widest text-cyan-500">{caseData?.case_id ?? caseId}</p>
          <h1 className="mt-1 text-2xl font-bold text-white">Normalized events</h1>
          {caseData && (
            <p className="mt-1 text-sm text-slate-400">
              {caseData.name} · reconstructed from processed evidence
            </p>
          )}
        </div>
        <Link
          to={`/cases/${caseId}`}
          className="border border-slate-700 px-4 py-2 font-mono text-xs uppercase tracking-widest text-slate-400 hover:text-slate-200"
        >
          ← Back to case
        </Link>
      </div>

      <section className="border border-slate-800 bg-slate-900/50 p-5">
        <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">Filters</h2>
        <form onSubmit={applyFilters} className="mt-4 grid gap-3 md:grid-cols-4">
          <div>
            <label className={labelClass} htmlFor="ev-source-type">
              Source type
            </label>
            <select
              id="ev-source-type"
              className={fieldClass}
              value={query.source_type ?? ""}
              onChange={(event) => set("source_type", event.target.value)}
            >
              <option value="">All</option>
              {SOURCE_TYPE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className={labelClass} htmlFor="ev-event-type">
              Event type
            </label>
            <input
              id="ev-event-type"
              className={fieldClass}
              value={query.event_type ?? ""}
              onChange={(event) => set("event_type", event.target.value)}
              placeholder="login, connect, …"
            />
          </div>
          <div>
            <label className={labelClass} htmlFor="ev-severity">
              Severity
            </label>
            <select
              id="ev-severity"
              className={fieldClass}
              value={query.severity ?? ""}
              onChange={(event) => set("severity", event.target.value)}
            >
              <option value="">All</option>
              {SEVERITY_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className={labelClass} htmlFor="ev-evidence">
              Evidence
            </label>
            <select
              id="ev-evidence"
              className={fieldClass}
              value={query.evidence_id ?? ""}
              onChange={(event) => set("evidence_id", event.target.value)}
            >
              <option value="">All</option>
              {evidenceList.map((item) => (
                <option key={item.evidence_id} value={item.evidence_id}>
                  {item.original_filename}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className={labelClass} htmlFor="ev-user">
              User
            </label>
            <input
              id="ev-user"
              className={fieldClass}
              value={query.user ?? ""}
              onChange={(event) => set("user", event.target.value)}
              placeholder="contains…"
            />
          </div>
          <div>
            <label className={labelClass} htmlFor="ev-host">
              Host
            </label>
            <input
              id="ev-host"
              className={fieldClass}
              value={query.host ?? ""}
              onChange={(event) => set("host", event.target.value)}
              placeholder="contains…"
            />
          </div>
          <div>
            <label className={labelClass} htmlFor="ev-from">
              From (UTC)
            </label>
            <input
              id="ev-from"
              type="datetime-local"
              className={fieldClass}
              value={query.timestamp_from ?? ""}
              onChange={(event) => set("timestamp_from", event.target.value)}
            />
          </div>
          <div>
            <label className={labelClass} htmlFor="ev-to">
              To (UTC)
            </label>
            <input
              id="ev-to"
              type="datetime-local"
              className={fieldClass}
              value={query.timestamp_to ?? ""}
              onChange={(event) => set("timestamp_to", event.target.value)}
            />
          </div>
          <div className="flex flex-wrap items-end gap-2 md:col-span-4">
            <button
              type="submit"
              className="border border-cyan-700 bg-cyan-950/60 px-4 py-1.5 font-mono text-xs uppercase tracking-widest text-cyan-300 hover:bg-cyan-900/60"
            >
              Apply filters
            </button>
            <button
              type="button"
              onClick={resetFilters}
              className="border border-slate-700 px-4 py-1.5 font-mono text-xs uppercase tracking-widest text-slate-400 hover:text-slate-200"
            >
              Reset
            </button>
            {loading && (
              <span className="font-mono text-xs uppercase tracking-wider text-slate-500">Loading…</span>
            )}
            {result && (
              <span className="ml-auto font-mono text-xs text-slate-500">
                {result.total} event{result.total === 1 ? "" : "s"}
                {result.total > 0 ? ` · showing ${start}–${end}` : ""}
              </span>
            )}
          </div>
        </form>
      </section>

      {error && <ErrorBox message={error} />}

      {result && result.events.length === 0 ? (
        <p className="border border-dashed border-slate-700 p-6 text-center font-mono text-xs uppercase tracking-wider text-slate-500">
          No normalized events match the current filters.
        </p>
      ) : (
        <section className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-800 text-left font-mono text-[10px] uppercase tracking-widest text-slate-500">
                <th className="py-2 pr-4">Timestamp (UTC)</th>
                <th className="py-2 pr-4">Event</th>
                <th className="py-2 pr-4">Source</th>
                <th className="py-2 pr-4">Type</th>
                <th className="py-2 pr-4">User</th>
                <th className="py-2 pr-4">Host</th>
                <th className="py-2 pr-4">IPs</th>
                <th className="py-2 pr-4">Process / File</th>
                <th className="py-2 pr-4">Severity</th>
                <th className="py-2">Origin</th>
              </tr>
            </thead>
            <tbody>
              {events.map((event) => (
                <EventRow key={event.event_id} event={event} selected={selectedId === event.event_id} onSelect={openEvent} />
              ))}
            </tbody>
          </table>
          <div className="mt-3 flex items-center justify-between">
            <p className="font-mono text-xs text-slate-500">
              Row number in original evidence: {selectedEvent?.raw_record_reference ?? "—"}
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                disabled={offset === 0}
                onClick={() => setOffset((previous) => Math.max(0, previous - PAGE_SIZE))}
                className="border border-slate-700 px-3 py-1 font-mono text-xs uppercase tracking-widest text-slate-400 hover:text-slate-200 disabled:opacity-40"
              >
                ← Previous
              </button>
              <button
                type="button"
                disabled={!result || offset + events.length >= result.total}
                onClick={() => setOffset((previous) => previous + PAGE_SIZE)}
                className="border border-slate-700 px-3 py-1 font-mono text-xs uppercase tracking-widest text-slate-400 hover:text-slate-200 disabled:opacity-40"
              >
                Next →
              </button>
            </div>
          </div>
        </section>
      )}

      {detailLoading && (
        <p className="font-mono text-xs uppercase tracking-widest text-slate-500">Loading event detail…</p>
      )}

      {detailError && <ErrorBox message={detailError} />}

      {detail && <EventDetailPanel detail={detail} />}

      {!detail && selectedId && !detailLoading && (
        <p className="font-mono text-xs italic text-slate-500">
          Select a row in the table to open its record and evidence trace.
        </p>
      )}
    </div>
  );
}

function EventRow({
  event,
  selected,
  onSelect,
}: {
  event: ForensicEvent;
  selected: boolean;
  onSelect: (eventId: string) => void;
}): JSX.Element {
  const ips = [event.source_ip, event.destination_ip].filter(Boolean).join(" → ");
  const artifact = event.process ?? event.file_path ?? "—";
  return (
    <tr
      onClick={() => onSelect(event.event_id)}
      className={`cursor-pointer border-b border-slate-900 align-top hover:bg-slate-900/70 ${
        selected ? "bg-slate-900" : ""
      }`}
    >
      <td className="py-3 pr-4 font-mono text-xs text-slate-300">{event.timestamp ? formatDateTime(event.timestamp) : "—"}</td>
      <td className="py-3 pr-4 font-mono text-[11px] text-cyan-400">{event.event_id}</td>
      <td className="py-3 pr-4">
        <SourceTypeBadge sourceType={event.source_type} />
      </td>
      <td className="py-3 pr-4 text-slate-200">{event.event_type || "—"}</td>
      <td className="py-3 pr-4 font-mono text-xs text-slate-300">{event.user ?? "—"}</td>
      <td className="py-3 pr-4 font-mono text-xs text-slate-300">{event.host ?? "—"}</td>
      <td className="py-3 pr-4 font-mono text-[11px] text-slate-400">{ips || "—"}</td>
      <td className="py-3 pr-4 font-mono text-[11px] text-slate-400">{artifact}</td>
      <td className="py-3 pr-4">{event.severity ? <SeverityBadge severity={event.severity} /> : <span className="text-slate-600">—</span>}</td>
      <td className="py-3">
        {event.duplicate ? (
          <span className="border border-amber-700 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-amber-400">
            dup of {event.duplicate_of}
          </span>
        ) : (
          <span className="text-slate-600">—</span>
        )}
      </td>
    </tr>
  );
}

function EventDetailPanel({ detail }: { detail: EventDetail }): JSX.Element {
  const metadata = detail.metadata
    ? Object.entries(detail.metadata).filter(([key]) => key !== "duplicate")
    : [];
  return (
    <section className="space-y-4 border border-slate-800 bg-slate-900/50 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="font-mono text-xs uppercase tracking-widest text-cyan-500">{detail.event_id}</p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <SourceTypeBadge sourceType={detail.source_type} />
            <span className="border border-slate-700 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-slate-300">
              {detail.event_type || "generic"}
            </span>
            {detail.severity ? <SeverityBadge severity={detail.severity} /> : null}
            {detail.duplicate && detail.duplicate_of && (
              <span className="border border-amber-700 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-amber-400">
                duplicate of {detail.duplicate_of}
              </span>
            )}
          </div>
        </div>
        <span className="font-mono text-[11px] text-slate-500">
          {detail.timestamp ? formatDateTime(detail.timestamp) : "no timestamp"}
          {detail.tz_note ? ` · ${detail.tz_note}` : ""}
        </span>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <Field label="User" value={detail.user} />
        <Field label="Host" value={detail.host} />
        <Field label="Action" value={detail.action} />
        <Field label="Source IP" value={detail.source_ip} />
        <Field label="Destination IP" value={detail.destination_ip} />
        <Field label="Process" value={detail.process} />
        <Field label="File path" value={detail.file_path} />
        <Field label="Raw record row" value={detail.raw_record_reference?.toString() ?? null} />
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="border border-slate-800 bg-slate-950/70 p-4">
          <h3 className="font-mono text-[10px] uppercase tracking-widest text-slate-500">
            Raw record (source evidence verbatim)
          </h3>
          {detail.raw_record ? (
            <>
              <pre className="mt-2 max-h-44 overflow-auto whitespace-pre-wrap break-all font-mono text-[11px] leading-relaxed text-slate-300">
                {detail.raw_record.content}
              </pre>
              {detail.raw_record.reject_reason && (
                <p className="mt-2 border border-red-900 bg-red-950/40 px-2 py-1 font-mono text-[10px] text-red-400">
                  reject reason: {detail.raw_record.reject_reason}
                </p>
              )}
            </>
          ) : (
            <p className="mt-2 font-mono text-xs text-slate-600">No raw record linked.</p>
          )}
        </div>

        <div className="space-y-4">
          <div className="border border-slate-800 bg-slate-950/70 p-4">
            <h3 className="font-mono text-[10px] uppercase tracking-widest text-slate-500">Evidence trace</h3>
            {detail.evidence ? (
              <div className="mt-2 space-y-2">
                <p className="flex flex-wrap items-center gap-2 text-sm text-slate-300">
                  <span className="font-mono text-cyan-400">{detail.evidence.evidence_id}</span>
                  {detail.evidence.original_filename}
                </p>
                <p className="text-sm text-slate-400">
                  Uploaded {formatDateTime(detail.evidence.uploaded_at)}
                </p>
                <div className="flex flex-wrap items-center gap-3">
                  <span className="font-mono text-[10px] uppercase text-slate-500">Recorded SHA-256</span>
                  <HashBadge value={detail.evidence.sha256} full />
                </div>
                <Link
                  to={`/cases/${detail.case_id}`}
                  className="inline-block border border-slate-700 px-3 py-1 font-mono text-[10px] uppercase tracking-widest text-slate-400 hover:text-slate-200"
                >
                  Open case →
                </Link>
              </div>
            ) : (
              <p className="mt-2 font-mono text-xs text-slate-600">No evidence reference.</p>
            )}
          </div>

          {metadata.length > 0 && (
            <div className="border border-slate-800 bg-slate-950/70 p-4">
              <h3 className="font-mono text-[10px] uppercase tracking-widest text-slate-500">Source-specific fields</h3>
              <dl className="mt-2 space-y-1">
                {metadata.map(([key, value]) => (
                  <div key={key} className="flex gap-3">
                    <dt className="w-40 shrink-0 font-mono text-[11px] uppercase text-slate-500">{key}</dt>
                    <dd className="flex-1 break-all font-mono text-[11px] text-slate-300">{String(value)}</dd>
                  </div>
                ))}
              </dl>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function Field({ label, value }: { label: string; value: string | null | undefined }): JSX.Element {
  return (
    <div>
      <p className="font-mono text-[10px] uppercase tracking-widest text-slate-500">{label}</p>
      <p className="mt-1 break-all font-mono text-xs text-slate-300">{value || "—"}</p>
    </div>
  );
}