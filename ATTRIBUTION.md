# ATTRIBUTION — FORENSIGHT AI

Third-party dependencies, their licenses, and an explicit statement of what this
team implemented. Required by the SUTRAM 2026 originality requirement:
open-source libraries are allowed; the forensic framework itself is our own
original implementation.

## What our team implemented (original work)

- Case management, evidence intake policy, and the write-once raw evidence store
- SHA-256 integrity verification workflow and the chain-of-custody log design
- Forensic event schema, parsers, field-alias normalization, and rejected-row retention
- Multi-format timestamp engine (ISO/Apache/US/epoch, timezone assumptions documented, never-invent rejections)
- Format-detection registry (extension + content + columns + declared type, unknown-format errors)
- Processing-run log design with status semantics, record cap, and duplicate marking (`duplicate_of`, originals never altered)
- Rule engine definitions (AUTH-001/002/003, PROC-001, FILE-001/002, NET-001) and their explanations
- Window feature engineering, Strategy A anomaly-scoring pipeline (dual detection gate, abstention), fusion scoring, and run metadata design
- Multi-source correlation logic with per-link reasons and chain assembly
- Reconstructed timeline construction and evidence-graph generation
- Deterministic retrieval-first investigator assistant
- Immutable investigation report layer (deterministic 15-section JSON snapshots, global `RPT-` sequence, custody, printable UI)
- Read-only scenario-statistics dashboard (global totals, finding/ML/integrity/custody/processing/run breakdowns, per-case KPIs, demo-case synthetic labelling)
- Traceability ladder (Finding → Reason → Forensic Event → Raw Record → Evidence File → Recorded SHA-256)
- Synthetic demo scenario generators and the report builder
- All UI/UX, tests, and documentation

No existing forensic product, repository, or hackathon project was copied or
cloned. Dependencies below are used as libraries only.

## Backend dependencies (`backend/requirements.txt`, `requirements-dev.txt`)

| Package | License | Use in this project |
|---|---|---|
| FastAPI | MIT | HTTP API framework, OpenAPI generation |
| Uvicorn | BSD-3-Clause | ASGI server |
| Starlette (via FastAPI) | BSD-3-Clause | ASGI toolkit used by FastAPI |
| Pydantic | MIT | Request/response validation and serialisation |
| SQLAlchemy | MIT | ORM and schema definitions |
| python-dotenv | BSD-3-Clause | Loads `.env` configuration |
| python-multipart | Apache-2.0 | Multipart form parsing for evidence upload |
| NumPy | BSD-3-Clause | Numerical arrays for feature/scoring pipelines |
| scikit-learn | BSD-3-Clause | IsolationForest anomaly detection (window scoring, seeded, deterministic) |
| pytest | MIT | Test framework |
| httpx | BSD-3-Clause | Test client transport for FastAPI tests |

License identifiers above were read from the installed package metadata /
bundled LICENSE files of the exact versions in `backend/requirements*.txt`.

Planned for later phases (declared now, used when those phases land):
pandas (BSD-3-Clause) for the segment-level classifier. The report layer is
implemented with the existing stack (JSON snapshots + browser print), so no
report library (e.g. reportlab) was needed. Phase 7 (dashboard) adds no new
dependencies — the page is rendered with markup + Tailwind only.

## Frontend dependencies (`frontend/package.json`)

| Package | License | Use in this project |
|---|---|---|
| React, React DOM | MIT | UI library |
| TypeScript | Apache-2.0 | Type checking |
| Vite | MIT | Dev server and bundler |
| @vitejs/plugin-react | MIT | React support for Vite |
| Tailwind CSS, @tailwindcss/vite | MIT | Styling |
| react-router-dom | MIT | Client-side routing for case/evidence pages |
| Recharts (planned, Phase 5) | MIT | Charts |
| React Flow / reactflow (Phase 4) | MIT | Evidence graph |

Exact installed versions are recorded in `frontend/package-lock.json`.

## Data and content

- All demo datasets are **synthetic demonstration data** authored and seeded by
  this team (`backend/demo/scenarios/`). They contain no real persons, hosts, or
  incidents, and every file carries a `SYNTHETIC / DEMONSTRATION DATA` label.
- Rule identifiers, finding language, and report structure are original to this
  project.
- Any trademark or product name appearing in log fields (e.g. `powershell.exe`)
  belongs to its respective owner and appears only as descriptive log content.

## Licenses of our own project code

Project code in this repository is provided for evaluation purposes as part of
the SUTRAM 2026 submission. Attribution notices above must be retained when
dependencies are redistributed.
