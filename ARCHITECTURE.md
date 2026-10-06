# FORENSIGHT AI — Architecture v1.2

**AI-Powered Digital Forensics Investigation Framework** · SUTRAM 2026
Status: Phases 0, 1, and 2 implemented · This document is the approved specification for all subsequent phases.

**Standing disclaimers (appear in UI, API description, and report):**

- Research/hackathon prototype — not a certified forensic or legal-admissibility system. All findings require investigator validation.
- Integrity verification confirms the evidence file has not changed since its hash was recorded. It does not establish who created or collected the evidence.
- Machine-learning outputs are statistical indicators. Wording throughout is *"potentially suspicious"*, *"anomalous"*, *"requires investigator review"*.

---

## 1. Product language (canonical)

> FORENSIGHT AI is an AI-assisted digital forensic investigation prototype that preserves uploaded evidence, verifies file integrity through SHA-256 hashing, converts heterogeneous logs into normalized forensic events, detects suspicious patterns using transparent rules and explainable machine learning, correlates evidence across sources, reconstructs an investigator-reviewable timeline, and maintains traceability from findings back to source evidence.

The system is not described as operating without investigator oversight, not as a product that certifies evidence, and not as a system that establishes criminal conduct. It is a **prototype-level forensic workflow** that supports an investigator.

## 2. Problem statement

Investigators hold heterogeneous, unstructured, multi-source evidence and must manually answer: *What happened? In what order? Which evidence supports that? What is anomalous?* Manual correlation across logs is slow, error-prone, and leaves no reproducible audit trail.

FORENSIGHT AI implements: **integrity-preserving ingestion → parsing → normalization → explainable detection → cross-source correlation → reconstructed timeline → traceable reporting**, entirely local and reproducible.

## 3. Core novelty (central claim)

> **Evidence-traceable AI-assisted forensic investigation.**

```
FINDING      "RULE-005: Rapid file modification burst"
  ↓ REASON   "1,206 write/rename events in 94 s for usr_jdoe;
              anomaly score 0.91 ≥ detection threshold 0.72;
              linked to process event via shared host + user"
  ↓ FORENSIC EVENT   normalized event (timestamp, source_type, entities)
  ↓ RAW RECORD       original row #417 of file_activity.csv (retained verbatim)
  ↓ EVIDENCE FILE    EV-004 file_activity.csv (name, size, uploader)
  ↓ RECORDED SHA-256 recorded at ingest, re-verifiable at any time
```

The ladder is rendered in the finding detail panel, in timeline/graph click-through, in assistant answers (evidence IDs), and in the report's traceability section.

## 4. System architecture

```
┌──────────────────────────────────────────────────────────────┐
│ FRONTEND — React + TypeScript + Vite + Tailwind              │
│ Landing · Dashboard · Cases · Evidence · Integrity · Events  │
│ Analysis · Findings · Timeline · Graph · Assistant · Report  │
│ Recharts · React Flow                                        │
└──────────────▲───────────────────────────────────────────────┘
               │ REST/JSON (typed DTOs)
┌──────────────┴───────────────────────────────────────────────┐
│ API LAYER — FastAPI · Pydantic validation · error envelope   │
│ /docs OpenAPI · request logging                              │
├──────────────────────────────────────────────────────────────┤
│ SERVICES — CaseService · EvidenceService · IntegrityService  │
│            PipelineService · ReportService                   │
├──────────────┬───────────────────┬───────────────────────────┤
│ PARSING      │ ANALYSIS          │ CORRELATION               │
│ registry +   │ RuleEngine        │ reason-per-link correlator │
│ normalizer   │ FeatureBuilder    │ chain builder              │
│ (rejects     │ IsolationForest   │ timeline builder           │
│  retained)   │ + statistical     │ graph builder              │
│              │   scorer          │                            │
├──────────────┴───────────────────┴───────────────────────────┤
│ STORAGE — SQLite (SQLAlchemy)                                │
│ evidence_store/{case}/raw/  WRITE-ONCE, never modified       │
│ evidence_store/{case}/derived + database = derived data      │
│ ml_artifacts/ = models + metrics                             │
└──────────────────────────────────────────────────────────────┘
```

**Invariant:** raw evidence bytes are written exactly once at ingest. Parsers read them through a read-only path. All derived data lives in the database / derived area and can be rebuilt by reprocessing. A regression test asserts raw hashes are unchanged after the full pipeline.

## 5. Module map and tiers

| # | Module | Backend unit | Tier |
|---|---|---|---|
| 1 | Case management | CaseService, `cases` | Core |
| 2 | Evidence ingestion | EvidenceService, security/uploads | Core |
| 3 | Evidence integrity verification | IntegrityService, `storage/raw_store` | Core |
| 4 | Parsing | `engines/parsing` registry | Core |
| 5 | Normalization | `engines/parsing/normalizer` | Core |
| 6 | AI/ML analysis | `engines/ml` (anomaly + fusion) | Core |
| 7 | Rule engine | `engines/rules` | Core |
| 8 | Multi-source correlation | `engines/correlation` | Core |
| 9 | Incident reconstruction | `engines/timeline` | Core |
| 10 | Evidence graph | `engines/graph` + React Flow | Secondary |
| 11 | Investigator assistant | `engines/assistant` (deterministic) | Secondary |
| 12 | Explainability | finding `reasons` payloads | Core (with 6/7) |
| 13 | Dashboard | stats aggregation | Core |
| 14 | Report generation | `engines/report` | Secondary |
| — | Segment-level classifier | `engines/ml/classifier` | Secondary |
| — | Investigator notes | `investigator_notes` | Secondary |

**Scope rule:** if time is limited, cut Stretch → Secondary → never Core. A demo where the core pipeline works end-to-end is the acceptance bar.

## 6. Data model (implemented in `app/models.py`)

| Table | Purpose | Key columns |
|---|---|---|
| `cases` | Investigation cases | case_id, name, investigator, status, severity, created_at, demo |
| `evidence` | Evidence metadata | evidence_id, filename, type, size, **sha256**, **original_hash**, status, counts |
| `integrity_checks` | Verification history | computed_hash, expected_hash, result, actor, checked_at |
| `chain_of_custody` | Custody/audit events | timestamp, action, actor, details |
| `raw_records` | Retained rows incl. rejected ones | row_index, content, reject_reason |
| `forensic_events` | Normalized events | timestamp, source_type, entities, anomaly_score, metadata, dedupe_hash, raw_record_id |
| `rule_findings` | Rule hits | rule_id, severity, explanation, reasons, triggered_event_ids, evidence_ids |
| `ml_findings` | ML findings | model_name, score, threshold, composite_suspicion_score, components |
| `classifier_results` | Segment-level predictions | window_start/end, predicted_label, class_score |
| `correlations` | Chain placements | chain_uid, position, link_score, **link_reason** |
| `investigation_runs` | Pipeline runs | stage, status, **stats (ML methodology + fusion weights)**, error |
| `investigator_notes` | Investigator annotations | author, body, finding_uid |
| `model_metrics` | Real evaluation results | precision, recall, f1, feature_list, dataset_desc |
| `processing_runs` | (v1.2) Parse/normalize runs | run_id, evidence_id, parser, status, received/normalized/rejected/duplicates, warnings, error, timestamps |

Relationships: `Case 1→N Evidence 1→N RawRecord/ForensicEvent` and `Evidence 1→N ProcessingRun`; every finding carries event-ID and evidence-ID arrays for direct traceability.

## 7. Evidence integrity verification (terminology contract)

- **Record:** at ingest, stream SHA-256 over the raw bytes; store as `sha256` (and `original_hash`); write custody events *Evidence Added*, *Hash Generated*.
- **Verify:** recompute SHA-256 of stored bytes; compare with recorded hash → `INTEGRITY VERIFIED` or `INTEGRITY MISMATCH`. Always display both hashes.
- **Controlled Integrity Test:** copy raw bytes to a demonstration location, mutate **only the copy**, hash the copy, compare against the recorded original hash; label `Controlled Integrity Test - Demonstration Copy`. The stored original is never written to. No endpoint modifies raw evidence.
- **Not claimed:** origin, collector identity, collection circumstances, admissibility. See `terminology.INTEGRITY_DISCLAIMER`.

## 8. Evidence-processing pipeline

```
UPLOAD  → validate (ext/size/MIME sniff) → sanitise name → write-once store
        → SHA-256 → custody(Evidence Added, Hash Generated)
PROCESS → custody(Analysis Started) → detect type → parser registry
        → row loop: multi-format timestamp parse → field alias map → validate
        → dedupe (canonical hash) → normalize → ForensicEvent
        → rejected row → RawRecord + reject_reason   [never silently dropped]
        → processing log {received, parsed, rejected[{row,reason}], duplicates, normalized}
        → custody(Analysis Completed)
ANALYZE → FeatureBuilder → IsolationForest (fixed threshold) → annotate events
        → RuleEngine → RuleFindings → fusion → Composite Suspicion Score
        → custody(Analysis Started/Completed)
CORRELATE → reason-tagged links → chains → Reconstructed Investigation Timeline → graph
REPORT  → PDF/JSON → custody(Report Generated)
```

**Timestamp handling:** ISO-8601 (±Z), `YYYY-MM-DD HH:MM:SS[.fff]`, Apache-style, US format, epoch s/ms — tried in order; unparseable rows are rejected *with reason* and retained. **Field aliases:** `user|username|account → user`, `ip|src_ip|source_ip → source_ip`, `ts|time|timestamp|@timestamp → timestamp`, etc.

**Processing-run semantics (v1.2):** a run reads at most `MAX_RECORDS_PER_RUN` records (default 200 000); any remainder is reported as a warning. Status is `FAILED` when the file cannot be processed safely (unknown format, unreadable content, or recorded SHA-256 no longer matching the stored bytes); `PARTIAL` when rows were rejected, no rows were produced (`received == 0`), or the record cap truncated the input; otherwise `COMPLETED`. Rejects are explained and retained (`raw_records.reject_reason`); duplicates are marked on derived events (never deleted, never silently doubled in counts); reprocessing replaces the derived rows for that evidence and appends a new run entry without modifying raw bytes.

## 9. ML methodology (corrected, single strategy)

### 9.1 Event-level anomaly detection

| Field | Definition |
|---|---|
| Model | `sklearn.ensemble.IsolationForest` |
| random_state | `42` (env `RANDOM_STATE`; recorded per run) |
| Feature set (16) | hour_sin, hour_cos, event-type one-hot (6), events/5 min, writes/5 min, failed logins/5 min, external connections/5 min, inter-event gap, off-hours flag, rare-IP flag, rare-user flag, entity breadth |
| Training scope | **Case-scoped** when n ≥ 40 events; otherwise a **global model** trained once on the pooled synthetic corpus (seed 42), persisted in `ml_artifacts/`. Scope recorded per run. |
| Scoring | `score_samples()` raw scores min–max normalized to an **anomaly score ∈ [0,1]** within the fitted scope (1 = most anomalous). Formula stored with the run. |
| **Threshold** | **One deterministic strategy: fixed constant `ANOMALY_THRESHOLD = 0.72`** (env-overridable). Not `contamination="auto"`, not percentile-based. |
| Why this threshold | Percentile/contamination thresholds force a fixed *proportion* of anomalies even in wholly benign data (false positives on the normal scenario) and make the threshold shift case by case (irreproducible). A fixed constant keeps the benign scenario quiet, makes runs comparable, and is auditable by an evaluator. Value 0.72 selected during development from score distributions of the seeded scenarios — documented as a **prototype calibration**. |
| Reproducibility | Fixed seed, fixed feature order, fixed threshold, single-threaded scoring, seeded demo data → identical scores (asserted by test). |

**Stored with every `InvestigationRun.stats`:** `model_name, random_state, feature_list, training_scope, scoring_method, threshold_value, threshold_method="fixed_constant", score_normalization, sklearn_version, fusion_weights, fusion_formula_version`.

**UI contract:** every display shows **"Anomaly score"** *and* **"Detection threshold"** side by side, with the note: *"The anomaly score indicates statistical deviation from this case's typical event patterns. It is not proof of malicious activity and requires investigator review."*

### 9.2 Segment-level classification (separate concept)

| Field | Definition |
|---|---|
| Concept | **Case/segment-level classification** — a label for a *time segment* of case activity. Never presented alongside event anomaly scores as the same thing. |
| Training sample unit | **Fixed 10-minute window** of case activity. One sample = aggregated features of one window across all sources (counts per source type, distinct users/IPs, write rate, rename rate, external connections, off-hours ratio, mean/max event anomaly score, event-type entropy). Windows are cut identically for training and inference. |
| Labels | From scenario generator provenance: normal-scenario windows → `benign`; compromise scenario → `benign` before the anchor event, `compromise` after; ransomware-like scenario → `ransomware_like` for impact windows. |
| Model | `RandomForestClassifier(n_estimators=200, random_state=42, class_weight="balanced")` with `LogisticRegression` baseline. |
| Evaluation | Stratified 75/25 split (seed 42) + 5-fold stratified CV; precision/recall/F1/accuracy/confusion matrix stored in `model_metrics`. |
| Claims | **No real-world performance claims.** Mandatory label: **"Trained and evaluated on synthetic demonstration data."** repeated in the report's Limitations. |
| Output wording | e.g. *"Window 10:41–10:51 classified: ransomware_like (class score 0.83) — synthetic-data model, requires investigator validation."* |

### 9.3 Hybrid fusion — Composite Suspicion Score

```
Composite Suspicion Score (CSS) ∈ [0,1] — uncalibrated heuristic, NOT a probability

CSS = 0.40 · RuleComponent        (0 if no rule; else 0.5 + 0.5·severity weight:
                                   Low .25 / Medium .5 / High .75 / Critical 1.0)
    + 0.35 · AnomalyComponent     (anomaly score of anchor event, or chain mean)
    + 0.25 · CorrelationComponent (distinct linked evidence sources ÷ 5, capped 1.0)

Bands: <0.35 Informational · 0.35–0.55 Low interest ·
       0.55–0.75 Anomalous — review · ≥0.75 Potentially suspicious — high priority
```

Weights live in `engines/ml/fusion.py` (`fusion_v1`), are shown verbatim in the UI explanation panel and in the report, and are stored in `InvestigationRun.stats`. Caption: *"The Composite Suspicion Score is an uncalibrated heuristic composite — not a probability and not proof of malicious activity. Requires investigator validation."*

## 10. Rule engine (transparent)

Deterministic rules, each producing rule_id, title, severity, triggering events, evidence IDs, timestamp span, and a human explanation:

`RULE-001` failed logins → success · `RULE-002` unusual source IP · `RULE-003` PowerShell → suspicious process activity · `RULE-004` mass file modifications in a short window · `RULE-005` mass rename/write activity · `RULE-006` external connection shortly after process execution · `RULE-007` improbable login sequence from timestamps · `RULE-008` evidence hash mismatch.

Rule findings and ML findings are distinct record types and are displayed in separate sections; fusion combines them into the Composite Suspicion Score.

## 11. Multi-source correlation (reasoned, non-causal)

Two layers, and **every link carries its reason**:

1. **Entity links** — shared `user`, `host`, `source_ip`, `destination_ip`, `process`, `file_path`, `session`.
2. **Temporal links** — sliding window (default 15 min) over time-sorted events, plus typed progression (authentication → process → file → network → browser).

```
link_score = w1·exp(−Δt/τ) + w2·entity_overlap + w3·type_progression
```

API/UI payload per link:

```json
{ "temporal_proximity": "42 seconds",
  "shared_entity": "user = usr_jdoe",
  "event_progression": "authentication → process",
  "correlation_score": 0.78 }
```

Caption everywhere correlation appears: *"Correlation indicates co-occurrence and shared context, not causation. Requires investigator validation."* Chains are deduplicated, capped (top 10), and each hop is clickable down to the raw record.

## 12. Reconstructed Investigation Timeline

- Union of anomalous events, rule-triggering events, chain members, plus ±2 min context.
- Ordered by timestamp; each entry carries confidence (rule confidence / score band / link score), an explanation, and **source evidence IDs + raw record IDs** — click-through reaches the original row.
- Heuristic phase segmentation: *Initial Access / Execution / Impact / Exfiltration / Benign Context* (ATT&CK-style labels, described as heuristic).
- Label: **"Reconstructed Investigation Timeline"** with the note: *"A reconstruction derived from the evidence available in this case. It is not an established sequence of events."*

## 13. AI investigation assistant (deterministic, retrieval-first)

1. Classify the question into supported intents (what happened / suspicious events / evidence for hypothesis / what preceded X / users / IPs / support finding).
2. Execute parameterized queries against actual case data.
3. Construct the answer strictly from retrieved rows.
4. Return **evidence IDs** (and event IDs where useful).
5. If the data does not support an answer: **"Insufficient evidence in the current case."**

No generative model is enabled. An optional LLM adapter interface exists but is **disabled and labelled "Prototype / Planned"**. Footer: *"Answers are constructed only from processed case evidence. No generative model is enabled."*

## 14. Demo scenarios (synthetic, seeded, labelled)

All files carry a `SYNTHETIC / DEMONSTRATION DATA` marker; fictional personas only; generated by `demo/generate_scenarios.py` with seed 42 (reproducible hashes).

- **Scenario A — Normal activity** (~150 events): expected — no high-severity findings, low anomaly scores. Proves the system does not raise alarms without cause.
- **Scenario B — Account compromise** (~220 events): failed-login burst → success from a new external IP off-hours → recon → PowerShell → targeted reads → outbound connection. Expected: RULE-001/002/003/006/007.
- **Scenario C — Ransomware-like incident** (~450 events): browser download → PowerShell → 1,200 file modifications/renames in 90 s → shadow-copy deletion → external connection. Conclusion wording: *"Evidence is consistent with ransomware-like activity and requires investigator validation."*

Files per scenario: `authentication.csv, process.csv, file_activity.csv, network.csv, browser.csv` (+ `system.log` for C) — internally consistent users/hosts/IPs so correlation genuinely works.

## 15. API surface

**Implemented (Phase 0):**

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | `{"status":"ok"}` |
| GET | `/` | Service descriptor |
| GET | `/docs`, `/openapi.json` | Interactive API documentation |

**Implemented (Phase 1):**

| Method | Path | Description |
|---|---|---|
| POST/GET | `/api/cases` | Create / list cases |
| GET/PATCH | `/api/cases/{case_id}` | Case detail / status+severity update |
| GET | `/api/cases/{case_id}/custody` | Case-level chain of custody |
| POST/GET | `/api/cases/{case_id}/evidence` | Upload evidence / inventory |
| GET | `/api/evidence/{evidence_id}` | Evidence detail incl. recorded SHA-256 |
| POST | `/api/evidence/{evidence_id}/verify` | Evidence Integrity Verification |
| POST | `/api/evidence/{evidence_id}/integrity-test` | Controlled Integrity Test (copy-based) |
| GET | `/api/evidence/{evidence_id}/custody` | Evidence chain of custody |
| GET | `/api/evidence/{evidence_id}/integrity-history` | Recorded verification results |
| GET | `/api/policy` | Upload policy (size cap, allowed extensions) |

**Implemented (Phase 2):**

| Method | Path | Description |
|---|---|---|
| POST | `/api/cases/{case_id}/process` | Process selected (or all) evidence — parse, normalize, record a run per evidence item, custody `Analysis Started` / `Analysis Completed` |
| GET | `/api/cases/{case_id}/processing-runs` | Processing run history (newest first) |
| GET | `/api/cases/{case_id}/events` | Normalized events (filters: source_type, event_type, severity, user, host, time range, evidence) with limit/offset |
| GET | `/api/cases/{case_id}/events/{event_id}` | Event detail with raw record + evidence SHA-256 (traceability chain) |
| GET | `/api/evidence/{evidence_id}/processing` | Runs + parse counts for one evidence item |
| GET | `/api/evidence/{evidence_id}/rejected-records` | Retained malformed/rejected rows with reasons |

**Planned (later phases, subject to scope tiers):**

```
GET  /api/evidence/{ev_id}[/download|/records]
POST /api/cases/{id}/analyze                 GET /api/cases/{id}/findings · /ml-metrics
GET  /api/findings/{uid}/trace               PATCH /api/findings/{uid}   (Confirmed/Dismissed)
POST /api/cases/{id}/correlate               GET /api/cases/{id}/correlations · /timeline · /graph
POST /api/cases/{id}/assistant               POST /api/cases/{id}/notes
POST /api/cases/{id}/report                  POST /api/demo/load
```

All errors use a uniform envelope `{error:{code,message,detail}}`; server paths are never exposed.

## 16. Security considerations

Upload extension allowlist + size cap (25 MB) + MIME sniff; filename sanitisation with UUID storage names (traversal-proof); zip-slip guards when ZIP lands; raw store write-once with no overwrite path; no execution of uploaded content; Pydantic validation on every input; parameterized SQL via ORM; evidence text always rendered escaped; evidence treated as data (never as instructions); request logging; report embeds every SHA-256 so a third party can re-verify independently; CSV export neutralises spreadsheet formula prefixes.

## 17. Testing strategy

- **Unit:** hashing (known vectors), integrity verified/mismatch, write-once refusal, each parser, normalizer (timestamps/aliases/rejects/dedupe), rule engine positive+negative, feature determinism, anomaly scoring range + seed reproducibility, classifier metrics real, correlation windows/link reasons, timeline ordering, graph generation, assistant intents incl. insufficient-evidence, PDF contains hashes.
- **Parsing unit:** CSV header/encoding fallback/column normalize/row-numbering; JSON object/array/wrapper; detection precedence (JSON wins over extension, declared type, unknown-format errors); timestamp formats incl. epoch, Apache, offsets; normalizer metadata preservation of source-specific fields.
- **Processing API:** run lifecycle (COMPLETED/PARTIAL/FAILED), record cap warning, integrity mismatch → FAILED run, unknown format → 422 + FAILED, rejects retained with reasons, duplicates marked with `duplicate_of`, reprocessing replaces derived rows, events list/detail + filter contract.
- **API:** CRUD + happy/error paths (413/415/404/409).
- **End-to-end:** demo load → verify → process → analyze → correlate → timeline → graph → assistant → report; asserts Scenario A quiet / C fires; raw hashes unchanged after pipeline; banned terms absent from UI strings.
- **Regression gate every phase:** `pytest` green + `npm run build` green.

## 18. Risks and limitations

| Risk | Mitigation |
|---|---|
| Wording drift back to overreaching claims | Single terminology constants module + banned-term test scanning constants and docs; same strings reused in UI/report |
| Fixed threshold 0.72 poorly calibrated on new data | Case-scoped scoring, always shown *with* its threshold, documented as prototype calibration; no universal detection claims |
| Segment classifier confused with event scores | Separate models, endpoints, and UI sections; window unit defined once and shared by training/inference |
| Composite score misread as a probability | Field never named "probability"; caption mandatory; components shown |
| Correlation read as causation | Per-link reasons required; caption on every correlation view |
| Raw evidence mutated by future changes | Write-once store (no overwrite API) + post-pipeline hash regression test |
| Scope creep | Tier system with cut order; Phase 4.5 core gate before secondary work |
| Synthetic-data overclaim | Mandatory synthetic-data labels on classifier metrics and demo banners |
| Hallucinated assistant answers | Deterministic retrieval only; insufficient-evidence path; LLM disabled |

## 19. Phase plan

| Phase | Deliverable | Exit criteria |
|---|---|---|
| **0** | Scaffolding, data model, terminology guard, write-once store, frontend skeleton | 12 acceptance criteria below — **DONE** |
| **1** | Case management + upload + SHA-256 verify + controlled integrity test + custody UI | upload→hash→verify→mismatch works in UI — **DONE** |
| 2 | Parsers + normalizer + processing log + events UI | demo files → correct counts, rejects explained — **DONE** |
| 3 | Rules + anomaly detection + fusion + explainability UI | Scenario C fires, Scenario A quiet, metrics real |
| 4 | Reasoned correlation + reconstructed timeline + dashboard | multi-source chain, traceable entries |
| **4.5** | **Core acceptance gate** | e2e core pipeline green, raw hashes unchanged |
| 5 | Evidence graph | click-through traceability |
| 6 | Report (PDF/JSON) + segment classifier metrics | 16-section report with disclaimers |
| 7 | Notes + assistant | example questions answered from evidence |
| 8 | Demo loader + polish + history | evaluator journey works end-to-end |
| 9 | Stretch (ZIP, EVTX, PCAP, optional LLM adapter, Docker) | only if 0–8 green |

## 20. Phase 0 acceptance criteria (all 12) — status

| # | Criterion | Status |
|---|---|---|
| 1 | Approved repository/folder structure created | ✅ |
| 2 | README.md, ARCHITECTURE.md, ATTRIBUTION.md with corrected v1.1 terminology | ✅ |
| 3 | FastAPI backend skeleton | ✅ |
| 4 | `GET /api/health` → `{"status":"ok"}` | ✅ |
| 5 | FastAPI `/docs` works | ✅ |
| 6 | React + TypeScript + Vite + Tailwind frontend skeleton | ✅ |
| 7 | `npm run build` passes with zero TypeScript errors | ✅ |
| 8 | All SQLAlchemy models/tables from the architecture | ✅ (13 tables) |
| 9 | Terminology constants module + banned-term test | ✅ |
| 10 | RawEvidenceStore write-once stub (`store_once`, `read_bytes`, `verify_hash`, no overwrite/truncate) | ✅ |
| 11 | Required pytest tests, all passing | ✅ |
| 12 | `.gitignore` + `.env.example` with approved settings | ✅ |

*(Status values are re-verified at the end of each phase; see Changelog.)*

### Phase 1 acceptance criteria (all 12) — status

| # | Criterion | Status |
|---|---|---|
| 1 | Create/list/get/update cases (`CASE-2026-NNN`) with validation + error envelope | ✅ |
| 2 | Evidence upload (multipart) with size cap, extension allowlist, content checks, sanitised storage names | ✅ |
| 3 | SHA-256 recorded at ingest; genuine re-read verification of the stored file at ingest | ✅ |
| 4 | `POST /verify` returns `INTEGRITY VERIFIED` / `INTEGRITY MISMATCH` and is repeatable | ✅ |
| 5 | Controlled integrity test mutates a copy outside the raw store; original byte-identical afterwards | ✅ |
| 6 | Integrity history recorded (verified/mismatch results persisted) | ✅ |
| 7 | Chain of custody recorded (Evidence Added, Hash Generated, Integrity Verified/Mismatch, Integrity Test) and queryable per case and per evidence | ✅ |
| 8 | Raw evidence remains write-once; no endpoint overwrites stored files | ✅ |
| 9 | Case list + case detail + evidence inventory UI with hash display, verify button, controlled test button, custody log | ✅ |
| 10 | Structured error envelope on all error paths (400/404/413/415) | ✅ |
| 11 | `pytest` green (Phase 0 + Phase 1) and `npm run build` green | ✅ |
| 12 | Documentation updated; banned terms still absent from constants and docs | ✅ |

### Phase 2 acceptance criteria (all 18) — status

| # | Criterion | Status |
|---|---|---|
| 1 | Upload still enforces size cap, extension allowlist, content checks, sanitised storage names | ✅ |
| 2 | SHA-256 re-verified against stored bytes before every processing run; mismatch → failed run | ✅ |
| 3 | Format detection by extension + content + columns + declared type; unknown format → explicit `UNRECOGNIZED_EVIDENCE_FORMAT` error (never silent) | ✅ |
| 4 | Safe readers for CSV (encoding fallback, header/column normalization, row numbering) and JSON (object/array/wrapper forms, key normalization); no unsafe deserialization | ✅ |
| 5 | Common forensic event schema with source-specific fields preserved in `metadata` | ✅ |
| 6 | Multi-format timestamp parsing tried in documented order; timezone handling assumed-UTC / converted-with-note / epoch; never invented — rejected rows keep the exact value | ✅ |
| 7 | Required-field validation (timestamp, source_type, etc.); rejects explained via `reject_reason` | ✅ |
| 8 | Severity standardized with a documented known-severity vocabulary | ✅ |
| 9 | Duplicates detected and marked on derived events (`duplicate_of`); originals never modified or deleted | ✅ |
| 10 | Malformed/rejected rows retained as raw records (evidence_id, row, reason, original content); never silently dropped | ✅ |
| 11 | Processing run records status, parser, received/normalized/rejected/duplicate counts, warnings/error, started/completed | ✅ |
| 12 | Status semantics enforced: PARTIAL when rejects/empty-input/cap-truncation, FAILED when unsafe, COMPLETED otherwise | ✅ |
| 13 | Resource limits: `MAX_RECORDS_PER_RUN` truncation warning; retained content cap; web reader size cap | ✅ |
| 14 | Run history per case and per evidence; parse counters reflected on evidence metadata | ✅ |
| 15 | Events list with filters + pagination; event detail exposes raw record + recorded SHA-256 (traceability) | ✅ |
| 16 | UI: evidence parse counters + status, Process action, runs summary, Events page with filters and traceable detail | ✅ |
| 17 | Six synthetic, seeded, labelled demo datasets; identical counts on reprocessing; SYNTHETIC/DEMONSTRATION labels + README | ✅ |
| 18 | Regression gate: `pytest` green (Phases 0–2) + `npm run build` green; raw hashes unchanged; docs updated; banned terms absent from constants and docs | ✅ |

## 21. Changelog — v1.0 → v1.1 corrections (13 items)

1. **Integrity terminology.** SHA-256 is described only as recording and verifying *file integrity*. `INTEGRITY VERIFIED` / `INTEGRITY MISMATCH` mean byte-level match/mismatch with the recorded hash. A standing disclaimer states that hashing does not establish who created or collected a file. Naming is *Evidence Integrity Verification* everywhere (module, page, endpoints `/verify`, `/integrity-test`).
2. **Legal claims removed.** All phrasing implying admissibility, origin guarantees, or certainty of criminal conduct was replaced with *investigator-explainable*, *transparent reasoning*, *evidence-traceable*, *requires investigator validation*, *prototype-level forensic workflow*. A prototype disclaimer is now mandatory in UI, API description, and report cover.
3. **Anomaly threshold.** Exactly one deterministic strategy: fixed constant `0.72`, `random_state=42`, documented feature set, documented training scope and score normalization, rationale for the choice, reproducibility rules. Methodology stored with every `InvestigationRun`. UI shows *Anomaly score* **and** *Detection threshold*.
4. **Classifier labelling.** Event-level anomaly detection and segment-level classification are separated. Training sample unit fixed as the **10-minute window** and used consistently. Mandatory label: *Trained and evaluated on synthetic demonstration data.* No real-world performance claims.
5. **Fusion naming.** The composite output is *Composite Suspicion Score* — explicitly uncalibrated, never called a probability — with formula, weights (0.40/0.35/0.25), and per-component breakdown shown in UI and report.
6. **Correlation reasons.** Every correlation link exposes temporal proximity, shared entity, and event progression plus the resulting score. Causation is explicitly disclaimed.
7. **Timeline naming.** Renamed *Reconstructed Investigation Timeline* with a note that it derives from available evidence. Every entry traces to source evidence, raw record, and normalized event.
8. **Assistant.** Deterministic retrieval-first design retained; no generative model enabled by default; answers return evidence IDs/event IDs or *Insufficient evidence in the current case.* Optional LLM adapter disabled and labelled *Prototype / Planned*.
9. **Demo tampering.** No endpoint modifies stored evidence. Mismatch demonstration uses `Controlled Integrity Test - Demonstration Copy`: copy → mutate the copy only → compare with recorded hash.
10. **Raw evidence immutability.** `evidence_store/**/raw/` is write-once by application logic; no rewrite, in-place normalization, or overwrite during processing; all derived data stored separately; regression test enforces it.
11. **Core novelty.** Centred on *evidence-traceable AI-assisted forensic investigation* with the mandatory six-step ladder Finding → Reason → Forensic Event → Raw Record → Evidence File → Recorded SHA-256 in UI and report.
12. **Scope control.** Modules divided into MUST-HAVE CORE / SECONDARY / STRETCH with an explicit cut order (Stretch → Secondary → never Core) and a core acceptance gate at Phase 4.5.
13. **Product language.** Canonical one-paragraph description adopted verbatim (§1); the product is not described as autonomous, as an evidence-certifying system, as a replacement for investigators, or as a system that establishes criminal conduct.

## 22. Changelog — v1.1 → v1.2 additions (Phase 2)

1. **`processing_runs` table added (14th).** Each parse/normalize run on one evidence item records run_id (`RUN-{n:06d}`), parser, status (PENDING/PROCESSING/COMPLETED/PARTIAL/FAILED), received/normalized/rejected/duplicate counts, warnings, error code + message, and started/completed timestamps. `Evidence` gained `parse_ok` / `parse_rejected` counters; derived per-run UIDs are independent of event UIDs (`EVT-{n:06d}`).
2. **Record cap.** `MAX_RECORDS_PER_RUN` (default 200 000) caps the records read in one run; the remainder is reported as a warning and the run is marked PARTIAL rather than silently truncated or overstating completion.
3. **Status semantics.** `FAILED` for unsafe processing (unknown format, unreadable content, or recorded SHA-256 mismatch re-checked against stored bytes before each run); `PARTIAL` when rows were rejected, no rows were produced, or the cap truncated; otherwise `COMPLETED`.
4. **Rejects retained, never deleted.** Every malformed/rejected row is stored as a raw record with `reject_reason` and the original content (cap 64 000 chars) and is exposed via `/evidence/{id}/rejected-records` and `/evidence/{id}/records`.
5. **Duplicate handling.** Duplicates are detected within a run via a canonical hash over the dedupe key fields and are *marked* on derived events (`duplicate` + `duplicate_of` pointing at the origin event) — source rows are never modified or deleted, and duplicate events remain traceable to their raw record.
6. **Reprocessing semantics.** A new run replaces the derived raw-record/event rows for that evidence and appends a run entry; raw evidence bytes and the recorded SHA-256 are never written to. Evidence status is restored across failed runs.
7. **API additions.** `POST /cases/{id}/process`, `GET /cases/{id}/processing-runs`, `GET /cases/{id}/events`, `GET /cases/{id}/events/{event_id}`, `GET /evidence/{id}/processing`, `GET /evidence/{id}/rejected-records` (the last one is an addition beyond the Phase 2 endpoint list, for direct rejects review).
8. **Timestamp assumptions documented.** Naive timestamps are treated as UTC with an explicit `assumed UTC (no timezone in source)` note; offset timestamps are converted to UTC with a note; epoch values carry `UTC (epoch value)`; unparseable timestamps are rejected without inventing a value.
