import { PROTOTYPE_DISCLAIMER } from "../types/terminology";

/** Standing prototype disclaimer shown on every page. */
export default function PrototypeBanner(): JSX.Element {
  return (
    <div className="border-b border-amber-700/60 bg-amber-950/40 px-6 py-2 text-center">
      <p className="font-mono text-[11px] uppercase tracking-widest text-amber-400">
        {PROTOTYPE_DISCLAIMER}
      </p>
    </div>
  );
}
