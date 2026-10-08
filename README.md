# FORENSIGHT AI

**AI-Powered Digital Forensics Investigation Framework**
SUTRAM 2026 — flagship challenge: *Building an AI-Powered Indigenous Digital Forensics Investigation Framework*

> FORENSIGHT AI is an AI-assisted digital forensic investigation prototype that preserves uploaded evidence, verifies file integrity through SHA-256 hashing, converts heterogeneous logs into normalized forensic events, detects suspicious patterns using transparent rules and explainable machine learning, correlates evidence across sources, reconstructs an investigator-reviewable timeline, maintains traceability from findings back to source evidence, and produces immutable, evidence-backed investigation reports.

**Current status:** Phases 0–8 + Phase 4.5 core acceptance gate — case management, evidence upload, SHA-256 integrity verification, controlled integrity test, chain of custody, **evidence parsing and event normalization** (CSV/JSON → common forensic event schema), a **processing log**, **automated analysis** (transparent rules, Strategy A anomaly detection, Composite Suspicion Score fusion, findings review workflow), **cross-source correlation** (reason-tagged links, activity groups, reconstructed timeline, evidence graph, investigation UI), an **evidence-traceable AI investigation assistant** (deterministic, retrieval-first, case-scoped — no generative model), an **investigation report layer** (deterministic 15-section evidence-backed snapshots, immutable and case-scoped, print UI), a **read-only scenario-statistics dashboard** (global totals, finding/ML/integrity/custody/processing/run breakdowns, per-case KPIs; demo cases carry the `SYNTHETIC / DEMONSTRATION DATA` marker), and an **advanced analyst workspace** (read-only investigation console mixing overview, evidence, findings + review, timeline, correlations, activity groups, graph, assistant, and reports with deep links) implemented (backend + UI). The Phase 4.5 gate, the Phase 5 assistant gate, and the Phase 6 report gate (all fresh-database end-to-end runs incl. mandatory cross-case isolation) pass with no open issues; re-processing evidence whose events are already referenced by correlation/finding history keeps those rows and records an explanatory warning instead of failing. Next: segment classifier metrics, notes, demo loader — per [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Disclaimer

- Research/hackathon prototype — not a certified forensic or legal-admissibility system. All findings require investigator validation.
- Integrity verification confirms the evidence file has not changed since its hash was recorded. It does not establish who created or collected the evidence.
- Machine-learning outputs are statistical indicators, not proof of malicious activity. The language used throughout is *"potentially suspicious"*, *"anomalous"*, *"requires investigator review"*.

## Evidence integrity terminology

This project uses **Evidence Integrity Verification** throughout (UI, API, report):

| Statement | Meaning |
|---|---|
| `SHA-256 recorded` | The hash of the evidence file bytes was computed at ingest and stored with the evidence metadata. |
| `INTEGRITY VERIFIED` | The current bytes of the file match the previously recorded SHA-256. |
| `INTEGRITY MISMATCH` | The current bytes differ from the recorded SHA-256. |
| `Controlled Integrity Test - Demonstration Copy` | A **copy** of the evidence is altered in a controlled test; the stored original is never modified. |

SHA-256 answers one question only: *have the bytes changed since we recorded them?* Questions about origin, collection circumstances, or provenance are outside what hashing can establish and are out of scope for this prototype.

## Core novelty — evidence traceability

Every finding in the platform resolves to one unbroken chain:

```
Finding → Reason → Forensic Event → Raw Record → Evidence File → Recorded SHA-256
```

The chain is visible in the UI, in assistant answers, and in the generated report. This is the project's central claim: **evidence-traceable AI-assisted forensic investigation**.

## Scope (per Architecture v1.10)

**MUST-HAVE CORE** — case management · evidence upload · SHA-256 integrity verification · evidence metadata · parsing · normalization · rule engine · ML anomaly detection · multi-source correlation · timeline reconstruction · evidence traceability · basic dashboard · demo scenario.

**SECONDARY** — evidence graph (implemented, Phase 4) · **investigation report (evidence-backed JSON snapshots + print UI — implemented, Phase 6)** · **AI investigation assistant (deterministic, retrieval-first) — implemented (Phase 5)** · **advanced analyst workspace (read-only investigation console) — implemented (Phase 8)** · investigator notes.

**STRETCH** — ZIP support · Windows EVTX · PCAP · optional LLM adapter (disabled, labelled *Prototype / Planned*) · Docker · advanced scalability.

Cut order if time is limited: Stretch → Secondary → never Core.

## Repository structure

```
forensight-ai/
├── README.md · ARCHITECTURE.md · ATTRIBUTION.md
├── .gitignore · .env.example
├── backend/
│   ├── requirements.txt · requirements-dev.txt · pytest.ini
│   ├── app/
│   │   ├── main.py            # FastAPI app, OpenAPI, CORS, lifespan
│   │   ├── config.py · db.py · models.py · schemas.py
│   │   ├── terminology.py     # canonical wording + banned-term guard
│   │   ├── routers/           # health, cases, evidence, processing, events, analysis, correlation, assistant, reports, workspace
│   │   ├── services/          # case, evidence, integrity, custody, processing, analysis, correlation, report, workspace
│   │   ├── storage/raw_store.py  # write-once raw evidence store
│   │   ├── security/uploads.py   # Phase 1: upload validation
│   │   └── engines/           # parsing, rules, ml implemented; assistant/ implemented
│   │                          # report implemented (services/report_service); notes, demo (later phases)
│   ├── tests/                 # pytest suite (terminology, raw store, API, models,
│   │                          # timestamps, parsers, processing, analysis, assistant, reports, demo datasets)
│   ├── data/                  # SQLite db (git-ignored)
│   ├── evidence_store/        # raw evidence, write-once (git-ignored)
│   ├── ml_artifacts/          # trained model artifacts (git-ignored)
│   └── demo/scenarios/        # 6 synthetic demo datasets + README (Phase 2)
└── frontend/
    └── src/                   # React + TypeScript + Vite + Tailwind
        ├── api/ types/ state/ components/ pages/   # incl. Events, Findings, Finding detail, Assistant, Reports
```

## Setup

### Backend (Python 3.11+)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload      # http://127.0.0.1:8000  ·  docs at /docs
```

### Frontend (Node 18+)

```powershell
cd frontend
npm install
npm run dev                        # http://127.0.0.1:5173 (proxies /api to :8000)
npm run build                      # type-check + production build
```

### Configuration

Copy `.env.example` to `.env` at the repository root and adjust if needed. Defaults: SQLite at `backend/data/foresight.db`, raw evidence root `backend/evidence_store/`, upload limit 25 MB, allowed extensions `csv,json,txt,log,zip`, `ANOMALY_THRESHOLD=0.72`, `RANDOM_STATE=42`, `MAX_RECORDS_PER_RUN=200000`, `ANALYSIS_WINDOW_MINUTES=5`, `ML_Z_SIGMAS=2.0`, `ML_MIN_WINDOWS=8`, `RULE_MAX_FINDINGS_PER_RULE=10`, plus per-rule thresholds (`RULE_AUTH001_*`, `RULE_FILE001_*`, …) and assistant limits (`ASSISTANT_MAX_QUESTION_LENGTH=1000`, `ASSISTANT_HISTORY_LIMIT=100`, `ASSISTANT_TOP_N=10`) documented in [ARCHITECTURE.md](ARCHITECTURE.md).

## Tests

```powershell
cd backend
python -m pytest                   # full suite
python -m pytest tests/test_terminology.py -v
```

The suite includes a terminology guard: banned phrases may not appear in the terminology constants, `README.md`, `ARCHITECTURE.md`, or `ATTRIBUTION.md`.

## API (Phases 1–3, 7–8)

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | `{"status": "ok"}` |
| GET | `/` | Service descriptor |
| GET | `/docs` | Interactive OpenAPI documentation |
| GET | `/openapi.json` | OpenAPI schema |
| POST | `/api/cases` | Create a case (`CASE-2026-NNN`) |
| GET | `/api/cases` | List cases with evidence/finding counts |
| GET | `/api/cases/{case_id}` | Case detail |
| PATCH | `/api/cases/{case_id}` | Update status/severity |
| GET | `/api/cases/{case_id}/custody` | Case-level chain of custody |
| POST | `/api/cases/{case_id}/evidence` | Upload evidence (multipart, size/type/content checks) |
| GET | `/api/cases/{case_id}/evidence` | Evidence inventory |
| GET | `/api/evidence/{evidence_id}` | Evidence detail incl. recorded SHA-256 |
| POST | `/api/evidence/{evidence_id}/verify` | Evidence Integrity Verification |
| POST | `/api/evidence/{evidence_id}/integrity-test` | Controlled Integrity Test on a demonstration copy |
| GET | `/api/evidence/{evidence_id}/custody` | Evidence chain of custody |
| GET | `/api/evidence/{evidence_id}/integrity-history` | Recorded verification results |
| GET | `/api/policy` | Upload policy (size cap, allowed extensions) |

Phase 2 — parsing, normalization, processing log, events:

| Method | Path | Description |
|---|---|---|
| POST | `/api/cases/{case_id}/process` | Process selected (or all) evidence — parse, normalize, record runs |
| GET | `/api/cases/{case_id}/processing-runs` | Processing run history (newest first) |
| GET | `/api/cases/{case_id}/events` | Normalized events with filters (source, type, severity, user, host, time range, evidence) |
| GET | `/api/cases/{case_id}/events/{event_id}` | Event detail: raw record + evidence SHA-256 (traceability) |
| GET | `/api/evidence/{evidence_id}/processing` | Runs + parse counts for one evidence item |
| GET | `/api/evidence/{evidence_id}/rejected-records` | Retained malformed/rejected records with reasons |

Phase 3 — automated analysis and findings:

| Method | Path | Description |
|---|---|---|
| POST | `/api/cases/{case_id}/analyze` | Run rules + Strategy A anomaly detection + fusion (append-only) |
| GET | `/api/cases/{case_id}/analysis-runs` | Analysis run history with methodology stats |
| GET | `/api/cases/{case_id}/findings` | Findings with filters (kind, severity, status, run) |
| GET | `/api/cases/{case_id}/findings/{finding_id}` | Finding detail: reasons, components, suspicion band, notes |
| GET | `/api/cases/{case_id}/findings/{finding_id}/trace` | Evidence ladder: events → raw records → evidence SHA-256 |
| PATCH | `/api/cases/{case_id}/findings/{finding_id}` | Review workflow (New → Under Review → Confirmed/Dismissed) |
| GET | `/api/cases/{case_id}/ml-metrics` | ML methodology stats + configuration |
| POST | `/api/cases/{case_id}/correlate` | Run cross-source correlation (append-only) |
| GET | `/api/cases/{case_id}/correlation-runs` | Correlation run history with stats |
| GET | `/api/cases/{case_id}/correlations` | Reason-tagged links (filters: type, run) |
| GET | `/api/correlations/{correlation_id}` | Link detail: reason, shared entities, both events + evidence |
| GET | `/api/cases/{case_id}/groups` | Activity groups (filters: kind, run) |
| GET | `/api/groups/{group_id}` | Group detail with member events |
| GET | `/api/cases/{case_id}/timeline` | Reconstructed Investigation Timeline |
| GET | `/api/cases/{case_id}/graph` | Evidence graph (capped, table fallback) |

Phase 5 — evidence-traceable investigation assistant (deterministic, no generative model):

| Method | Path | Description |
|---|---|---|
| POST | `/api/cases/{case_id}/assistant/query` | Ask the assistant — returns intent, answer, evidence, basis, confidence, sources, disclaimer |
| GET | `/api/cases/{case_id}/assistant/history` | Append-only question history for the case (newest first) |
| GET | `/api/cases/{case_id}/assistant/queries/{query_id}` | One stored answer (404 for other cases' queries) |

Every answer is reconstructed from the queried case's own persisted data (case-scoped — no cross-case leakage), carries cited sources, and appends to `assistant_queries`. A reference to a finding in a different case returns a structured `FINDING_NOT_FOUND` 404.

Phase 6 — investigation report layer (immutable, evidence-backed snapshots):

| Method | Path | Description |
|---|---|---|
| POST | `/api/cases/{case_id}/reports` | Generate + store a deterministic 15-section forensic snapshot (201; optional `title`/`actor`) |
| GET | `/api/cases/{case_id}/reports` | Report summaries for the case (newest-first) |
| GET | `/api/cases/{case_id}/reports/{report_id}` | One report with its sections (404 `REPORT_NOT_FOUND` outside the owning case) |
| GET | `/api/cases/{case_id}/reports/{report_id}/json` | Raw stored snapshot `{metadata, sections}`, unchanged since generation |

Phase 7 — dashboard (read-only scenario statistics):

| Method | Path | Description |
|---|---|---|
| GET | `/api/dashboard` | Global totals, finding/ML/integrity/custody/processing/run breakdowns, and per-case KPIs — pure aggregates of persisted rows; demo cases carry the `SYNTHETIC / DEMONSTRATION DATA` marker |

Reports are read-only, case-scoped snapshots: ID `RPT-{n:06d}` comes from a global sequence, each generation records `Report Generated` custody, and re-generating never rewrites an earlier snapshot.

Phase 8 — advanced analyst workspace (read-only investigation console):

| Method | Path | Description |
|---|---|---|
| GET | `/api/cases/{case_id}/workspace` | One read-only workspace snapshot: case headline + processing/integrity rollups, evidence inventory with per-item integrity + processing, findings + open review queue, timeline/correlation/group/graph summaries, assistant history, report history — built only from rows persisted by Phases 1–6 (no analysis, correlation, assistant, or report runs; 404 `CASE_NOT_FOUND` outside the owning case) |

Building the workspace performs only `SELECT`s — it never runs the pipeline, never writes, and every empty state is reported honestly (`Not processed` / `Unverified` / zero counts / empty lists). See the `/cases/{case_id}/workspace` page in the UI.

Planned endpoints for later phases are listed in [ARCHITECTURE.md](ARCHITECTURE.md#api-surface).

## Roadmap

| Phase | Deliverable | Tier |
|---|---|---|
| 0 | Scaffolding, data model, terminology guard, write-once store | Core |
| 1 | Case management, evidence upload, integrity verification | Core |
| 2 | Parsing + normalization + processing log | Core |
| 3 | Rule engine + Strategy A anomaly detection + fusion + findings UI | Core |
| 4 | Correlation + activity groups + reconstructed timeline + evidence graph + investigation UI | Core |
| 4.5 | **Core acceptance gate** (end-to-end core pipeline) | Core |
| 5 | **Investigation assistant** — deterministic, retrieval-first, case-scoped | Secondary |
| 6 | **Investigation report layer** — immutable evidence-backed snapshots + print UI | Secondary |
| 7 | Dashboard — read-only scenario statistics + per-case KPIs | Secondary |
| 8 | **Advanced analyst workspace** — read-only investigation console (overview, evidence, findings + review, timeline, correlations, groups, graph, assistant, reports; deep links) | Secondary |
| 9 | Segment classifier metrics | Secondary |
| 10 | Notes (investigator annotations) | Secondary |
| 11 | One-click demo case + polish | Core polish |
| 12 | Stretch items only if 0–11 are green | Stretch |

## Attribution

Third-party dependencies, licenses, and a description of what this team implemented are documented in [ATTRIBUTION.md](ATTRIBUTION.md).
