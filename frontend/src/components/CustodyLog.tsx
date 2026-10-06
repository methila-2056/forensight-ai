import type { CustodyEvent } from "../types/models";
import { formatDateTime } from "../state/format";

const ACTION_TONES: Record<string, string> = {
  "Evidence Added": "text-cyan-400 border-cyan-800",
  "Hash Generated": "text-sky-400 border-sky-800",
  "Integrity Verified": "text-emerald-400 border-emerald-800",
  "Integrity Mismatch": "text-red-400 border-red-800",
  "Integrity Test": "text-amber-400 border-amber-800",
};

interface Props {
  events: CustodyEvent[];
  title?: string;
}

/** Chain-of-custody history (handling record — no legal claim). */
export default function CustodyLog({ events, title = "Chain of custody" }: Props): JSX.Element {
  if (events.length === 0) {
    return (
      <p className="font-mono text-xs uppercase tracking-wider text-slate-500">
        No custody events recorded yet.
      </p>
    );
  }

  const sorted = [...events].sort((a, b) => a.id - b.id);

  return (
    <div>
      <h3 className="font-mono text-xs uppercase tracking-[0.2em] text-slate-500">{title}</h3>
      <ol className="mt-3 space-y-2 border-l border-slate-800 pl-4">
        {sorted.map((event) => (
          <li key={event.id} className="relative">
            <span className="absolute -left-[21px] top-2 h-2 w-2 rounded-full bg-slate-700" aria-hidden />
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-[11px] text-slate-500">{formatDateTime(event.timestamp)}</span>
              <span
                className={`border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider ${
                  ACTION_TONES[event.action] ?? "border-slate-700 text-slate-400"
                }`}
              >
                {event.action}
              </span>
              <span className="font-mono text-[10px] uppercase text-slate-600">actor: {event.actor}</span>
            </div>
            {event.details && (
              <p className="mt-1 break-all font-mono text-[10px] text-slate-500">
                {Object.entries(event.details)
                  .map(([key, value]) => `${key}=${String(value)}`)
                  .join(" · ")}
              </p>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}
