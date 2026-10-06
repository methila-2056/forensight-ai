import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { listCases } from "../api/cases";
import { ApiError } from "../api/client";
import { CaseStatusBadge, SeverityBadge } from "../components/Badges";
import ErrorBox from "../components/ErrorBox";
import { formatDateTime } from "../state/format";
import type { CaseSummary } from "../types/models";

export default function CaseListPage(): JSX.Element {
  const [cases, setCases] = useState<CaseSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const load = useCallback(() => {
    listCases()
      .then((result) => {
        setCases(result);
        setError(null);
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : "Failed to load cases.");
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Cases</h1>
          <p className="mt-1 font-mono text-xs uppercase tracking-wider text-slate-500">
            Case registry · evidence held in the write-once store
          </p>
        </div>
        <Link
          to="/cases/new"
          className="border border-cyan-700 bg-cyan-950/60 px-4 py-2 font-mono text-xs uppercase tracking-widest text-cyan-300 hover:bg-cyan-900/60"
        >
          + New case
        </Link>
      </div>

      {error && (
        <div className="mt-6">
          <ErrorBox message={error} />
        </div>
      )}

      {cases !== null && cases.length === 0 && !error && (
        <div className="mt-8 border border-dashed border-slate-700 p-10 text-center">
          <p className="font-mono text-sm uppercase tracking-wider text-slate-400">No cases yet</p>
          <p className="mt-2 text-sm text-slate-500">Create your first case to begin collecting evidence.</p>
        </div>
      )}

      {cases !== null && cases.length > 0 && (
        <div className="mt-6 overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-800 text-left font-mono text-[10px] uppercase tracking-widest text-slate-500">
                <th className="py-2 pr-4">Case ID</th>
                <th className="py-2 pr-4">Name</th>
                <th className="py-2 pr-4">Investigator</th>
                <th className="py-2 pr-4">Severity</th>
                <th className="py-2 pr-4">Status</th>
                <th className="py-2 pr-4">Evidence</th>
                <th className="py-2">Last activity</th>
              </tr>
            </thead>
            <tbody>
              {cases.map((item) => (
                <tr
                  key={item.case_id}
                  onClick={() => navigate(`/cases/${item.case_id}`)}
                  className="cursor-pointer border-b border-slate-900 hover:bg-slate-900/70"
                >
                  <td className="py-3 pr-4 font-mono text-xs text-cyan-400">{item.case_id}</td>
                  <td className="py-3 pr-4 text-white">{item.name}</td>
                  <td className="py-3 pr-4 text-slate-400">{item.investigator}</td>
                  <td className="py-3 pr-4">
                    <SeverityBadge severity={item.severity} />
                  </td>
                  <td className="py-3 pr-4">
                    <CaseStatusBadge status={item.status} />
                  </td>
                  <td className="py-3 pr-4 font-mono text-slate-300">{item.evidence_count}</td>
                  <td className="py-3 font-mono text-xs text-slate-500">{formatDateTime(item.last_activity)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {cases === null && !error && (
        <p className="mt-8 font-mono text-xs uppercase tracking-widest text-slate-500">Loading cases…</p>
      )}
    </div>
  );
}
