import { useState } from "react";
import { shortHash } from "../state/format";

interface Props {
  value: string;
  label?: string;
  full?: boolean;
}

/** Monospace SHA-256 display with click-to-copy. */
export default function HashBadge({ value, label, full = false }: Props): JSX.Element {
  const [copied, setCopied] = useState(false);

  const copy = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };

  return (
    <span className="inline-flex max-w-full items-center gap-2">
      {label && (
        <span className="font-mono text-[10px] uppercase tracking-wider text-slate-500">{label}</span>
      )}
      <code
        className="cursor-copy select-all break-all border border-slate-700 bg-slate-900 px-2 py-1 font-mono text-[11px] text-cyan-300"
        title={value}
        onClick={() => void copy()}
      >
        {full ? value : shortHash(value)}
      </code>
      <button
        type="button"
        onClick={() => void copy()}
        className="border border-slate-700 px-2 py-1 font-mono text-[10px] uppercase text-slate-400 hover:border-cyan-700 hover:text-cyan-300"
      >
        {copied ? "Copied" : "Copy"}
      </button>
    </span>
  );
}
