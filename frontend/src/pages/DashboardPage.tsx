import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getDashboard } from "../api/dashboard";
import { ApiError } from "../api/client";
import ErrorBox from "../components/ErrorBox";
import { formatDateTime } from "../state/format";
import type {
  CaseKpi,
  DashboardData,
  FindingBreakdown,
  ProcessingSummary,
} from "../types/models";
import { DASHBOARD_KPI_LABEL, DASHBOARD_LABEL, DASHBOARD_NOTE } from "../types/terminology";

const cardClass =
  "border border-slate-800 bg-slate-900/50 p-4";

function StatCard({
  label,
  value,
  accent = "text-cyan-300",
}: {
  label: string;
  value: number | string;
  accent?: string;
}): JSX.Element {
  return (
    <div className={cardClass}>
      <p className="font-mono text-[10px] uppercase tracking-widest text-slate-500">{label}</p>
      <p className={`mt-1 font-mono text-2xl font-bold ${accent}`}>{value}</p>
    </div>
  );
}

function BreakdownList({
  title,
  entries,
}: {
  title: string;
  entries: Array<{ label: string; value: number }>;
}): JSX.Element {
  return (
    <div className={cardClass}>
      <h3 className="font-mono text-[10px] uppercase tracking-widest text-slate-500">{title}</h3>
      <dl className="mt-3 space-y-2">
        {entries.map((entry) => (
          <div key={entry.label} className="flex items-center justify-between gap-4">
            <dt className="text-sm text-slate-400">{entry.label}</dt>
            <dd className="font-mono text-sm text-white">{entry.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function findingsBreakdownLabels(breakdown: FindingBreakdown): Array<{ label: string; value: number }> {
  return [
    { label: "Rule findings", value: breakdown.by_kind.rule },
    { label: "ML findings", value: breakdown.by_kind.ml },
    ...(["Low", "Medium", "High", "Critical"] as const).map((severity) => ({
      label: `Severity · ${severity}`,
      value: breakdown.by_severity[severity],
    })),
    ...(["New", "Under Review", "Confirmed", "Dismissed"] as const).map((status) => ({
      label: `Status · ${status}`,
      value: breakdown.by_status[status],
    })),
  ];
}

function processingLabels(summary: ProcessingSummary): Array<{ label: string; value: number }> {
  return [
    { label: "Completed", value: summary.by_status.Completed },
    { label: "Partial", value: summary.by_status.Partial },
    { label: "Failed", value: summary.by_status.Failed },
    { label: "Records normalized", value: summary.records_normalized },
    { label: "Records rejected", value: summary.records_rejected },
  ];
}

function CaseRow({ kpi }: { kpi: CaseKpi }): JSX.Element {
  return (
    <tr className="border-b border-slate-900 hover:bg-slate-900/70">
      <td className="py-3 pr-4">
        <Link
          to={`/cases/${kpi.case_id}`}
          className="font-mono text-xs text-cyan-400 hover:text-cyan-300"
        >
          {kpi.case_id}
        </Link>
      </td>
      <td className="py-3 pr-4 text-white">{kpi.name}</td>
      <td className="py-3 pr-4">
        {kpi.synthetic_label ? (
          <span className="border border-amber-800 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-amber-400">
            {kpi.synthetic_label}
          </span>
        ) : (
          <span className="font-mono text-[10px] uppercase tracking-wider text-slate-500">
            real
          </span>
        )}
      </td>
      <td className="py-3 pr-4 font-mono text-xs text-slate-400">{kpi.severity}</td>
      <td className="py-3 pr-4 font-mono text-xs text-slate-400">{kpi.status}</td>
      <td className="py-3 pr-4 font-mono text-xs text-slate-300">{kpi.evidence_count}</td>
      <td className="py-3 pr-4 font-mono text-xs text-slate-300">{kpi.event_count}</td>
      <td className="py-3 pr-4 font-mono text-xs text-slate-300">{kpi.rule_findings}</td>
      <td className="py-3 pr-4 font-mono text-xs text-slate-300">{kpi.ml_findings}</td>
      <td className="py-3 pr-4 font-mono text-xs text-slate-300">{kpi.confirmed_findings}</td>
      <td className="py-3 pr-4 font-mono text-xs text-slate-300">{kpi.correlations}</td>
      <td className="py-3 pr-4 font-mono text-xs text-slate-300">{kpi.activity_groups}</td>
      <td className="py-3 pr-4 font-mono text-xs text-slate-300">{kpi.processing_runs}</td>
      <td className="py-3 pr-4 font-mono text-xs text-slate-300">{kpi.reports}</td>
      <td className="py-3 font-mono text-xs text-slate-500">
        {formatDateTime(kpi.last_activity)}
      </td>
    </tr>
  );
}

export default function DashboardPage(): JSX.Element {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    getDashboard()
      .then((result) => {
        setData(result);
        setError(null);
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : "Failed to load the dashboard.");
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (error) {
    return <ErrorBox message={error} />;
  }

  if (!data) {
    return <p className="font-mono text-xs uppercase tracking-widest text-slate-500">Loading dashboard…</p>;
  }

  const { totals, findings, ml, integrity, custody, processing, runs, cases } = data;
  const totalFindings = totals.rule_findings + totals.ml_findings;

  return (
    <div className="space-y-8">
      <header>
        <p className="font-mono text-xs uppercase tracking-widest text-cyan-500">
          {DASHBOARD_LABEL}
        </p>
        <h1 className="mt-1 text-2xl font-bold text-white">{DASHBOARD_LABEL}</h1>
        <p className="mt-1 text-sm text-slate-400">
          Aggregates of the data already persisted by the analysis phases — generated{" "}
          {formatDateTime(data.generated_at)}.
        </p>
      </header>

      <section>
        <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">Totals</h2>
        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          <StatCard label="Cases" value={totals.cases} />
          <StatCard label="Evidence files" value={totals.evidence} />
          <StatCard label="Normalized events" value={totals.forensic_events} />
          <StatCard label="Raw records" value={totals.raw_records} />
          <StatCard label="Findings" value={totalFindings} accent="text-amber-300" />
          <StatCard label="Rule findings" value={totals.rule_findings} />
          <StatCard label="ML findings" value={totals.ml_findings} />
          <StatCard label="Correlations" value={totals.correlations} />
          <StatCard label="Activity groups" value={totals.investigation_groups} />
          <StatCard label="Processing runs" value={totals.processing_runs} />
          <StatCard label="Analysis runs" value={totals.analysis_runs} />
          <StatCard label="Correlation runs" value={totals.correlation_runs} />
          <StatCard label="Integrity checks" value={totals.integrity_checks} />
          <StatCard label="Custody events" value={totals.custody_events} />
          <StatCard label="Reports" value={totals.investigation_reports} />
          <StatCard label="Assistant queries" value={totals.assistant_queries} />
        </div>
      </section>

      <section>
        <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">Breakdowns</h2>
        <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <BreakdownList title="Findings" entries={findingsBreakdownLabels(findings)} />
          <BreakdownList
            title="Processing"
            entries={processingLabels(processing)}
          />
          <BreakdownList
            title="Runs"
            entries={[
              ...(["Completed", "Failed", "Pending", "Running"] as const).map((status) => ({
                label: `Analyze · ${status}`,
                value: runs.analysis_by_status[status],
              })),
              ...(["Completed", "Failed"] as const).map((status) => ({
                label: `Correlate · ${status}`,
                value: runs.correlation_by_status[status],
              })),
            ]}
          />
          <BreakdownList
            title="Integrity"
            entries={[
              { label: "Verified", value: integrity.verified },
              { label: "Mismatch", value: integrity.mismatch },
              { label: "Checks", value: integrity.checks },
            ]}
          />
          <BreakdownList
            title="ML run statistics"
            entries={[
              { label: "Completed runs", value: ml.completed_runs },
              { label: "Windows total", value: ml.windows_total },
              { label: "Windows flagged", value: ml.windows_flagged },
              { label: "Abstained runs", value: ml.abstained_runs },
              { label: "ML findings", value: ml.ml_findings },
            ]}
          />
          <BreakdownList
            title="Custody"
            entries={[
              { label: "Events", value: custody.events },
              ...Object.entries(custody.by_action)
                .sort(([, a], [, b]) => b - a)
                .map(([action, count]) => ({ label: action, value: count })),
            ]}
          />
        </div>
      </section>

      <section>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">
            {DASHBOARD_KPI_LABEL}
          </h2>
          <span className="font-mono text-[10px] uppercase tracking-wider text-slate-600">
            {cases.length} case{cases.length === 1 ? "" : "s"}
          </span>
        </div>
        {cases.length === 0 ? (
          <p className="mt-3 border border-dashed border-slate-700 p-6 text-center font-mono text-xs uppercase tracking-wider text-slate-500">
            No cases have been created yet.
          </p>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-800 text-left font-mono text-[10px] uppercase tracking-widest text-slate-500">
                  <th className="py-2 pr-4">Case</th>
                  <th className="py-2 pr-4">Name</th>
                  <th className="py-2 pr-4">Type</th>
                  <th className="py-2 pr-4">Severity</th>
                  <th className="py-2 pr-4">Status</th>
                  <th className="py-2 pr-4">Evidence</th>
                  <th className="py-2 pr-4">Events</th>
                  <th className="py-2 pr-4">Rule</th>
                  <th className="py-2 pr-4">ML</th>
                  <th className="py-2 pr-4">Confirmed</th>
                  <th className="py-2 pr-4">Corr.</th>
                  <th className="py-2 pr-4">Groups</th>
                  <th className="py-2 pr-4">Runs</th>
                  <th className="py-2 pr-4">Reports</th>
                  <th className="py-2">Last activity</th>
                </tr>
              </thead>
              <tbody>
                {cases.map((kpi) => (
                  <CaseRow key={kpi.case_id} kpi={kpi} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <p className="border border-slate-800 bg-slate-900/50 p-4 font-mono text-[11px] leading-5 text-slate-500">
        {DASHBOARD_NOTE}
      </p>
    </div>
  );
}