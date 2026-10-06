import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { createCase } from "../api/cases";
import { ApiError } from "../api/client";
import ErrorBox from "../components/ErrorBox";
import { SEVERITY_OPTIONS } from "../types/models";
import type { Severity } from "../types/models";

export default function CreateCasePage(): JSX.Element {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [investigator, setInvestigator] = useState("");
  const [description, setDescription] = useState("");
  const [severity, setSeverity] = useState<Severity>("Medium");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const submit = async (event: React.FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const created = await createCase({ name, investigator, description, severity });
      navigate(`/cases/${created.case_id}`);
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Failed to create the case.");
      setSubmitting(false);
    }
  };

  const fieldClass =
    "mt-1 w-full border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-cyan-600 focus:outline-none";

  return (
    <div className="mx-auto max-w-xl">
      <h1 className="text-2xl font-bold text-white">New case</h1>
      <p className="mt-1 font-mono text-xs uppercase tracking-wider text-slate-500">
        A case is the container for evidence, custody events, and (later) findings
      </p>

      <form onSubmit={(event) => void submit(event)} className="mt-6 space-y-5">
        {error && <ErrorBox message={error} />}

        <div>
          <label className="font-mono text-[10px] uppercase tracking-widest text-slate-400" htmlFor="case-name">
            Case name *
          </label>
          <input
            id="case-name"
            className={fieldClass}
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Unauthorized login review — workstation WS-07"
            required
          />
        </div>

        <div>
          <label
            className="font-mono text-[10px] uppercase tracking-widest text-slate-400"
            htmlFor="case-investigator"
          >
            Investigator *
          </label>
          <input
            id="case-investigator"
            className={fieldClass}
            value={investigator}
            onChange={(event) => setInvestigator(event.target.value)}
            placeholder="Investigator name"
            required
          />
        </div>

        <div>
          <label className="font-mono text-[10px] uppercase tracking-widest text-slate-400" htmlFor="case-severity">
            Severity
          </label>
          <select
            id="case-severity"
            className={fieldClass}
            value={severity}
            onChange={(event) => setSeverity(event.target.value as Severity)}
          >
            {SEVERITY_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label
            className="font-mono text-[10px] uppercase tracking-widest text-slate-400"
            htmlFor="case-description"
          >
            Description
          </label>
          <textarea
            id="case-description"
            className={`${fieldClass} min-h-[96px] resize-y`}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="Scope of the investigation, sources, and any context for the team."
          />
        </div>

        <div className="flex gap-3 pt-2">
          <button
            type="submit"
            disabled={submitting}
            className="border border-cyan-700 bg-cyan-950/60 px-5 py-2 font-mono text-xs uppercase tracking-widest text-cyan-300 hover:bg-cyan-900/60 disabled:opacity-50"
          >
            {submitting ? "Creating…" : "Create case"}
          </button>
          <button
            type="button"
            onClick={() => navigate("/cases")}
            className="border border-slate-700 px-5 py-2 font-mono text-xs uppercase tracking-widest text-slate-400 hover:text-slate-200"
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
