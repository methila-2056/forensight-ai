import { NavLink, Outlet, Link } from "react-router-dom";
import PrototypeBanner from "./PrototypeBanner";
import { PRODUCT_NAME, PRODUCT_SUBTITLE } from "../types/terminology";

export default function AppShell(): JSX.Element {
  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `border-b-2 px-1 pb-1 font-mono text-xs uppercase tracking-widest transition-colors ${
      isActive
        ? "border-cyan-500 text-cyan-300"
        : "border-transparent text-slate-400 hover:text-slate-200"
    }`;

  return (
    <div className="flex min-h-screen flex-col bg-slate-950 text-slate-200">
      <PrototypeBanner />
      <header className="border-b border-slate-800 bg-slate-900/70">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
          <Link to="/" className="group">
            <span className="font-mono text-lg font-bold tracking-tight text-white group-hover:text-cyan-300">
              {PRODUCT_NAME}
            </span>
            <span className="ml-3 hidden font-mono text-[10px] uppercase tracking-widest text-slate-500 md:inline">
              {PRODUCT_SUBTITLE}
            </span>
          </Link>
          <nav className="flex items-center gap-6">
            <NavLink to="/" end className={linkClass}>
              Overview
            </NavLink>
            <NavLink to="/cases" className={linkClass}>
              Cases
            </NavLink>
            <a
              href="/docs"
              target="_blank"
              rel="noreferrer"
              className="border-b-2 border-transparent pb-1 font-mono text-xs uppercase tracking-widest text-slate-400 hover:text-slate-200"
            >
              API
            </a>
          </nav>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">
        <Outlet />
      </main>

      <footer className="border-t border-slate-800 px-6 py-4 text-center font-mono text-[10px] uppercase tracking-widest text-slate-600">
        {PRODUCT_NAME} · Phase 5 · SUTRAM 2026 · Findings from rules and anomaly scores are
        statistical observations — they require investigator validation
      </footer>
    </div>
  );
}
