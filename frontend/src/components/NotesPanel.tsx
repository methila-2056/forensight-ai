/**
 * Investigator notes panel (Phase 10).
 *
 * Notes are append-only analyst annotations: there is no edit or delete
 * affordance anywhere in this component, matching the backend contract. A note
 * may optionally be pinned to a finding in the same case.
 */

import { useCallback, useEffect, useState } from "react";
import { addCaseNote, getCaseNotes } from "../api/cases";
import { ApiError } from "../api/client";
import ErrorBox from "./ErrorBox";
import { formatDateTime } from "../state/format";
import type { NoteSummary } from "../types/models";
import { NOTES_APPEND_ONLY_LABEL, NOTES_EMPTY, NOTES_PANEL_TITLE } from "../types/terminology";

const fieldClass =
  "w-full border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-cyan-600 focus:outline-none";

export default function NotesPanel({
  caseId,
  author = "investigator",
  pinnedFindingUid,
}: {
  caseId: string;
  author?: string;
  /** When set, new notes are pinned to this finding. */
  pinnedFindingUid?: string | null;
}): JSX.Element {
  const [notes, setNotes] = useState<NoteSummary[] | null>(null);
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    getCaseNotes(caseId)
      .then((result) => {
        setNotes(result.notes);
        setLoadError(null);
      })
      .catch((err: unknown) => {
        setLoadError(err instanceof ApiError ? err.message : "Failed to load notes.");
      });
  }, [caseId]);

  useEffect(() => {
    load();
  }, [load]);

  const submit = async (event: React.FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    const text = body.trim();
    if (!text) {
      setError("Note body must not be empty.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await addCaseNote(caseId, {
        body: text,
        author,
        ...(pinnedFindingUid ? { finding_uid: pinnedFindingUid } : {}),
      });
      setBody("");
      load();
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Failed to save the note.");
    } finally {
      setSaving(false);
    }
  };

  const visible = pinnedFindingUid
    ? (notes ?? []).filter((n) => n.finding_uid === pinnedFindingUid)
    : (notes ?? []);

  return (
    <section className="space-y-4">
      <div>
        <h2 className="font-mono text-xs uppercase tracking-widest text-cyan-500">
          {NOTES_PANEL_TITLE}
        </h2>
        <p className="mt-1 font-mono text-[10px] uppercase tracking-widest text-slate-500">
          {NOTES_APPEND_ONLY_LABEL}
        </p>
      </div>

      {loadError && <ErrorBox message={loadError} />}

      <form onSubmit={(event) => void submit(event)} className="space-y-2">
        {error && <ErrorBox message={error} />}
        <textarea
          className={fieldClass}
          rows={3}
          value={body}
          maxLength={4000}
          onChange={(event) => setBody(event.target.value)}
          placeholder="Record an observation, follow-up action, or context…"
          aria-label="Note body"
        />
        <div className="flex items-center justify-between gap-3">
          <span className="font-mono text-[10px] text-slate-600">
            {pinnedFindingUid ? `pinned to ${pinnedFindingUid}` : "case note"}
            {" · "}
            {body.length}/4000
          </span>
          <button
            type="submit"
            disabled={saving || body.trim().length === 0}
            className="border border-cyan-700 bg-cyan-950/60 px-4 py-2 font-mono text-xs uppercase tracking-widest text-cyan-300 hover:bg-cyan-900/60 disabled:opacity-40"
          >
            {saving ? "Saving…" : "Add note"}
          </button>
        </div>
      </form>

      {notes === null ? (
        <p className="font-mono text-xs text-slate-600">Loading notes…</p>
      ) : visible.length === 0 ? (
        <p className="border border-dashed border-slate-800 px-4 py-3 text-sm text-slate-500">
          {NOTES_EMPTY}
        </p>
      ) : (
        <ul className="space-y-3">
          {visible.map((note) => (
            <li key={note.note_id} className="border border-slate-800 bg-slate-900/40 px-4 py-3">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <span className="font-mono text-[10px] uppercase tracking-widest text-slate-400">
                  {note.author}
                </span>
                <span className="font-mono text-[10px] text-slate-600">
                  {formatDateTime(note.created_at)}
                </span>
              </div>
              <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-200">
                {note.body}
              </p>
              {note.finding_uid && (
                <p className="mt-2 font-mono text-[10px] uppercase tracking-widest text-cyan-500">
                  finding: {note.finding_uid}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}