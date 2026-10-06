# FORENSIGHT AI

**AI-Powered Digital Forensics Investigation Framework**
SUTRAM 2026 — flagship challenge: *Building an AI-Powered Indigenous Digital Forensics Investigation Framework*

> FORENSIGHT AI is an AI-assisted digital forensic investigation prototype that preserves uploaded evidence, verifies file integrity through SHA-256 hashing, converts heterogeneous logs into normalized forensic events, detects suspicious patterns using transparent rules and explainable machine learning, correlates evidence across sources, reconstructs an investigator-reviewable timeline, and maintains traceability from findings back to source evidence.

**Current status:** Phase 0 — project scaffolding complete (backend skeleton, data model, terminology guard, write-once evidence store, frontend skeleton). Feature phases follow the plan in [ARCHITECTURE.md](ARCHITECTURE.md).

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
│   │   ├── routers/           # Phase 0: health only
│   │   ├── services/          # Phase 1+
│   │   ├── storage/raw_store.py  # write-once raw evidence store
│   │   ├── security/          # Phase 1+ (upload validation)
│   │   └── engines/           # parsing, rules, ml, correlation, timeline,
│   │                          # graph, assistant, report (Phase 2+)
│   ├── tests/                 # pytest suite (terminology, raw store, API, models)
│   ├── data/                  # SQLite db (git-ignored)
│   ├── evidence_store/        # raw evidence, write-once (git-ignored)
│   ├── ml_artifacts/          # trained model artifacts (git-ignored)
│   └── demo/scenarios/        # synthetic demo datasets (Phase 2)
└── frontend/
    └── src/                   # React + TypeScript + Vite + Tailwind
        ├── api/ types/ state/ components/ pages/
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

Copy `.env.example` to `.env` at the repository root and adjust if needed. Defaults: SQLite at `backend/data/foresight.db`, raw evidence root `backend/evidence_store/`, upload limit 25 MB, allowed extensions `csv,json,txt,log,zip`, `ANOMALY_THRESHOLD=0.72`, `RANDOM_STATE=42`.

## Tests

```powershell
cd backend
python -m pytest                   # full suite
python -m pytest tests/test_terminology.py -v
```

The suite includes a terminology guard: banned phrases may not appear in the terminology constants, `README.md`, `ARCHITECTURE.md`, or `ATTRIBUTION.md`.

## API (Phase 0)

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | `{"status": "ok"}` |
| GET | `/` | Service descriptor |
| GET | `/docs` | Interactive OpenAPI documentation |
| GET | `/openapi.json` | OpenAPI schema |

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
