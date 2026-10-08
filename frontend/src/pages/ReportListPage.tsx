import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { getCase } from "../api/cases";
import { ApiError } from "../api/client";
import { generateReport, listReports } from "../api/reports";
import ErrorBox from "../components/ErrorBox";
import { formatDateTime } from "../state/format";
import type { CaseSummary, ReportSummary } from "../types/models";
import { REPORT_TITLE } from "../types/terminology";

const fieldClass =
  "w-full border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:border-cyan-600 focus:outline-none";

export default function ReportListPage(): JSX.Element {
  const { caseId = "" } = useParams();
  const navigate = useNavigate();

  const [caseData, setCaseData] = useState<CaseSummary | null>(null);
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);

  const load = useCallback(() => {
    Promise.all([getCase(caseId), listReports(caseId)])
      .then(([loadedCase, reportList]) => {
        setCaseData(loadedCase);
        setReports(reportList);
        setError(null);
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : "Failed to load reports.");
      });
  }, [caseId]);

  useEffect(() => {
    load();
  }, [load]);

  const generate = async (event?: React.FormEvent<HTMLFormElement>): Promise<void> => {
    event?.preventDefault();
    setGenerating(true);
    setActionError(null);
    try {
      const created = await generateReport(caseId, {
        title: title.trim() || undefined,
        actor: "ui",
      });
      navigate(`/cases/${caseId}/reports/${created.report_id}`);
    } catch (err: unknown) {
      setActionError(
        err instanceof ApiError ? err.message : "Failed to generate the report.",
      );
    } finally {
      setGenerating(false);
    }
  };

  if (error) {
    return <ErrorBox message={error} />;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="font-mono text-xs uppercase tracking-widest text-cyan-500">{caseId}</p>
          <h1 className="mt-1 text-2xl font-bold text-white">
            Investigation reports
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            {reports.length} report{reports.length === 1 ? "" : "s"} generated for this case —
            each is an immutable snapshot of the persisted analysis state.
          </p>
        </div>
        <Link
          to={`/cases/${caseId}`}
          className="border border-slate-700 px-4 py-2 font-mono text-xs uppercase tracking-widest text-slate-400 hover:text-slate-200"
        >
          ← Back to case
        </Link>
      </div>

      <section className="border border-slate-800 bg-slate-900/50 p-5">
        <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">
          Generate report
        </h2>
        <form onSubmit={(event) => void generate(event)} className="mt-4 flex flex-wrap items-end gap-4">
          <div className="min-w-72 flex-1">
            <label className="font-mono text-[10px] uppercase tracking-widest text-slate-400" htmlFor="report-title">
              Title (optional)
            </label>
            <input
              id="report-title"
              className={`${fieldClass} mt-1`}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder={REPORT_TITLE}
              maxLength={255}
            />
          </div>
          <button
            type="submit"
            disabled={generating}
            className="border border-cyan-700 bg-cyan-950/60 px-4 py-2 font-mono text-xs uppercase tracking-widest text-cyan-300 hover:bg-cyan-900/60 disabled:opacity-50"
          >
            {generating ? "Generating…" : "Generate snapshot →"}
          </button>
        </form>
        {actionError && (
          <div className="mt-4">
            <ErrorBox message={actionError} />
          </div>
        )}
      </section>

      <section>
        <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">
          Generated reports
        </h2>
        {reports.length === 0 ? (
          <p className="mt-3 border border-dashed border-slate-700 p-6 text-center font-mono text-xs uppercase tracking-wider text-slate-500">
            No reports were generated for this case yet.
          </p>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-800 text-left font-mono text-[10px] uppercase tracking-widest text-slate-500">
                  <th className="py-2 pr-4">Report ID</th>
                  <th className="py-2 pr-4">Title</th>
                  <th className="py-2 pr-4">Schema / Version</th>
                  <th className="py-2 pr-4">Status</th>
                  <th className="py-2 pr-4">Generated by</th>
                  <th className="py-2">Generated at</th>
                </tr>
              </thead>
              <tbody>
                {reports.map((report) => (
                  <tr key={report.report_id} className="border-b border-slate-900 hover:bg-slate-900/70">
                    <td className="py-3 pr-4">
                      <Link
                        to={`/cases/${caseId}/reports/${report.report_id}`}
                        className="font-mono text-xs text-cyan-400 hover:text-cyan-300"
                      >
                        {report.report_id}
                      </Link>
                    </td>
                    <td className="py-3 pr-4 text-white">{report.title}</td>
                    <td className="py-3 pr-4 font-mono text-[11px] text-slate-400">
                      {report.schema} · {report.report_version}
                    </td>
                    <td className="py-3 pr-4 font-mono text-xs text-emerald-400">{report.status}</td>
                    <td className="py-3 pr-4 font-mono text-xs text-slate-400">{report.generated_by}</td>
                    <td className="py-3 font-mono text-xs text-slate-500">
                      {report.generated_at ? formatDateTime(report.generated_at) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {caseData && (
        <p className="font-mono text-[11px] uppercase tracking-wider text-slate-600">
          Case: {caseData.case_id} · {caseData.name} · severity {caseData.severity}
        </p>
      )}
    </div>
  );
}