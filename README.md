# FORENSIGHT AI

**AI-Powered Digital Forensics Investigation Framework**
SUTRAM 2026 — flagship challenge: *Building an AI-Powered Indigenous Digital Forensics Investigation Framework*

> FORENSIGHT AI is an AI-assisted digital forensic investigation prototype that preserves uploaded evidence, verifies file integrity through SHA-256 hashing, converts heterogeneous logs into normalized forensic events, detects suspicious patterns using transparent rules and explainable machine learning, correlates evidence across sources, reconstructs an investigator-reviewable timeline, and maintains traceability from findings back to source evidence.

**Current status:** Phase 2 — case management, evidence upload, SHA-256 integrity verification, controlled integrity test, chain of custody, **evidence parsing and event normalization** (CSV/JSON → common forensic event schema) and a **processing log** implemented (backend + UI). Analysis (Phase 3: rules, ML, correlation, timeline, assistant, reporting) follows the plan in [ARCHITECTURE.md](ARCHITECTURE.md).

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

## Scope (per Architecture v1.1)

**MUST-HAVE CORE** — case management · evidence upload · SHA-256 integrity verification · evidence metadata · parsing · normalization · rule engine · ML anomaly detection · multi-source correlation · timeline reconstruction · evidence traceability · basic dashboard · demo scenario.

**SECONDARY** — evidence graph · PDF report · investigator notes · AI investigation assistant (deterministic, retrieval-first).

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
│   │   ├── routers/           # health, cases, evidence, processing, events (Phases 1–2)
│   │   ├── services/          # case, evidence, integrity, custody, processing (Phases 1–2)
│   │   ├── storage/raw_store.py  # write-once raw evidence store
│   │   ├── security/uploads.py   # Phase 1: upload validation
│   │   └── engines/           # parsing (Phase 2 implemented); rules, ml,
│   │                          # correlation, timeline, graph, assistant, report (Phase 3+)
│   ├── tests/                 # pytest suite (terminology, raw store, API, models,
│   │                          # timestamps, parsers, processing, demo datasets)
│   ├── data/                  # SQLite db (git-ignored)
│   ├── evidence_store/        # raw evidence, write-once (git-ignored)
│   ├── ml_artifacts/          # trained model artifacts (git-ignored)
│   └── demo/scenarios/        # 6 synthetic demo datasets + README (Phase 2)
└── frontend/
    └── src/                   # React + TypeScript + Vite + Tailwind
        ├── api/ types/ state/ components/ pages/   # incl. Events page + process UI
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

Copy `.env.example` to `.env` at the repository root and adjust if needed. Defaults: SQLite at `backend/data/foresight.db`, raw evidence root `backend/evidence_store/`, upload limit 25 MB, allowed extensions `csv,json,txt,log,zip`, `ANOMALY_THRESHOLD=0.72`, `RANDOM_STATE=42`, `MAX_RECORDS_PER_RUN=200000`.

## Tests

```powershell
cd backend
python -m pytest                   # full suite
python -m pytest tests/test_terminology.py -v
```

The suite includes a terminology guard: banned phrases may not appear in the terminology constants, `README.md`, `ARCHITECTURE.md`, or `ATTRIBUTION.md`.

## API (Phase 1 + Phase 2)

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

Planned endpoints for later phases are listed in [ARCHITECTURE.md](ARCHITECTURE.md#api-surface).

## Roadmap

| Phase | Deliverable | Tier |
|---|---|---|
| 0 | Scaffolding, data model, terminology guard, write-once store | Core |
| 1 | Case management, evidence upload, integrity verification | Core |
| 2 | Parsing + normalization + processing log | Core |
| 3 | Rule engine + ML anomaly detection + explanations | Core |
| 4 | Correlation + reconstructed timeline + dashboard | Core |
| 4.5 | **Core acceptance gate** (end-to-end core pipeline) | Core |
| 5–7 | Evidence graph, report, notes, assistant | Secondary |
| 8 | One-click demo case + polish | Core polish |
| 9 | Stretch items only if 0–8 are green | Stretch |

## Attribution

Third-party dependencies, licenses, and a description of what this team implemented are documented in [ATTRIBUTION.md](ATTRIBUTION.md).
