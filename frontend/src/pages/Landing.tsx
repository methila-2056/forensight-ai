import { useEffect, useState } from "react";
import { getHealth, ApiError } from "../api/client";
import {
  INTEGRITY_DISCLAIMER,
  PRODUCT_CONCEPT,
  PRODUCT_NAME,
  PRODUCT_SUBTITLE,
  PROTOTYPE_DISCLAIMER,
  SYNTHETIC_DATA_LABEL,
  TRACEABILITY_STEPS,
} from "../types/terminology";

type HealthState = "checking" | "online" | "offline";

const PHASES: Array<{ id: string; label: string; tier: "Core" | "Secondary" | "Stretch"; done: boolean }> = [
  { id: "0", label: "Scaffolding, data model, terminology guard, write-once store", tier: "Core", done: true },
  { id: "1", label: "Case management, evidence upload, integrity verification", tier: "Core", done: true },
  { id: "2", label: "Parsing + normalization + processing log", tier: "Core", done: true },
  { id: "3", label: "Rule engine + ML anomaly detection + explanations", tier: "Core", done: true },
  { id: "4", label: "Correlation + activity groups + timeline + evidence graph", tier: "Core", done: true },
  { id: "4.5", label: "Core acceptance gate (end-to-end core pipeline)", tier: "Core", done: true },
  { id: "5", label: "Evidence-traceable investigation assistant (deterministic, case-scoped)", tier: "Secondary", done: true },
  { id: "6", label: "Investigation report layer (immutable evidence-backed snapshots + print UI)", tier: "Secondary", done: true },
  { id: "7", label: "Dashboard", tier: "Secondary", done: true },
  { id: "8", label: "Segment classifier metrics", tier: "Secondary", done: false },
  { id: "9", label: "Notes (investigator annotations)", tier: "Secondary", done: false },
  { id: "10", label: "One-click demo case + polish", tier: "Core", done: false },
  { id: "11", label: "ZIP, EVTX, PCAP, optional LLM adapter, Docker", tier: "Stretch", done: false },
];

export default function Landing(): JSX.Element {
  const [health, setHealth] = useState<HealthState>("checking");

  useEffect(() => {
    let cancelled = false;
    getHealth()
      .then((result) => {
        if (!cancelled) setHealth(result.status === "ok" ? "online" : "offline");
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setHealth(error instanceof ApiError ? "offline" : "offline");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const healthLabel =
    health === "online" ? "BACKEND ONLINE" : health === "offline" ? "BACKEND OFFLINE" : "CHECKING BACKEND…";
  const healthTone =
    health === "online" ? "text-emerald-400" : health === "offline" ? "text-red-400" : "text-slate-400";

  return (
    <div className="space-y-10">
      <header className="border-b border-slate-800 pb-8">
        <p className="font-mono text-xs uppercase tracking-[0.3em] text-cyan-500">SUTRAM 2026</p>
        <h1 className="mt-2 text-4xl font-bold tracking-tight text-white">{PRODUCT_NAME}</h1>
        <p className="mt-1 text-lg text-slate-400">{PRODUCT_SUBTITLE}</p>
        <p className="mt-4 max-w-3xl text-sm leading-6 text-slate-300">{PRODUCT_CONCEPT}</p>
        <div className="mt-4 flex flex-wrap gap-3 font-mono text-xs">
          <span className={`border border-slate-700 px-2 py-1 ${healthTone}`}>{healthLabel}</span>
          <span className="border border-slate-700 px-2 py-1 text-slate-400">PHASES 0–7 · CORE PIPELINE + ASSISTANT + REPORTS + DASHBOARD</span>
          <span className="border border-slate-700 px-2 py-1 text-amber-500">{SYNTHETIC_DATA_LABEL}</span>
        </div>
      </header>

      <section>
        <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">Core traceability chain</h2>
        <ol className="mt-3 flex flex-wrap items-center gap-2">
          {TRACEABILITY_STEPS.map((step, index) => (
            <li key={step} className="flex items-center gap-2">
              <span className="border border-cyan-800 bg-slate-900 px-3 py-2 font-mono text-xs text-cyan-300">
                {step}
              </span>
              {index < TRACEABILITY_STEPS.length - 1 && (
                <span className="text-slate-600" aria-hidden>
                  →
                </span>
              )}
            </li>
          ))}
        </ol>
      </section>

      <section className="border border-slate-800 bg-slate-900/50 p-5">
        <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">Evidence integrity</h2>
        <p className="mt-2 text-sm leading-6 text-slate-300">{INTEGRITY_DISCLAIMER}</p>
      </section>

      <section>
        <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">Roadmap</h2>
        <table className="mt-3 w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-slate-800 text-left font-mono text-xs uppercase text-slate-500">
              <th className="py-2 pr-4">Phase</th>
              <th className="py-2 pr-4">Deliverable</th>
              <th className="py-2">Tier</th>
            </tr>
          </thead>
          <tbody>
            {PHASES.map((phase) => (
              <tr key={phase.id} className="border-b border-slate-900">
                <td className="py-2 pr-4 font-mono text-cyan-400">{phase.id}</td>
                <td className="py-2 pr-4 text-slate-300">{phase.label}</td>
                <td className="py-2">
                  <span
                    className={
                      phase.tier === "Core"
                        ? "font-mono text-xs text-emerald-400"
                        : phase.tier === "Secondary"
                          ? "font-mono text-xs text-amber-400"
                          : "font-mono text-xs text-slate-500"
                    }
                  >
                    {phase.tier}
                    {phase.done ? " · DONE" : ""}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="border border-slate-800 bg-slate-900/50 p-5">
        <h2 className="font-mono text-xs uppercase tracking-[0.25em] text-slate-500">Status</h2>
        <p className="mt-2 text-sm leading-6 text-slate-300">
          Phases 0–7 are implemented: cases and write-once evidence with SHA-256 integrity
          verification and chain of custody, parsing and normalization with a processing log,
          rule-based and ML anomaly analysis with explanations, cross-source correlation
          with activity groups, reconstructed timeline, and the evidence graph, a
          case-scoped investigation assistant, immutable, evidence-backed investigation
          reports, and a read-only scenario-statistics dashboard. Segment classifier
          metrics, notes, and a one-click demo loader arrive in later phases per the
          roadmap above. API reference:{" "}
          <a className="text-cyan-400 underline" href="/docs" target="_blank" rel="noreferrer">
            /docs
          </a>
          .
        </p>
        <p className="mt-3 font-mono text-[11px] uppercase tracking-widest text-amber-500">
          {PROTOTYPE_DISCLAIMER}
        </p>
      </section>
    </div>
  );
}
