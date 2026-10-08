# FORENSIGHT AI — Architecture v1.8

**AI-Powered Digital Forensics Investigation Framework** · SUTRAM 2026
Status: Phases 0–6 implemented, Phase 4.5 core acceptance gate + Phase 5 assistant gate + Phase 6 report gate passed · This document is the approved specification for all subsequent phases.

**Standing disclaimers (appear in UI, API description, and report):**

- Research/hackathon prototype — not a certified forensic or legal-admissibility system. All findings require investigator validation.
- Integrity verification confirms the evidence file has not changed since its hash was recorded. It does not establish who created or collected the evidence.
- Machine-learning outputs are statistical indicators. Wording throughout is *"potentially suspicious"*, *"anomalous"*, *"requires investigator review"*.

---

## 1. Product language (canonical)

> FORENSIGHT AI is an AI-assisted digital forensic investigation prototype that preserves uploaded evidence, verifies file integrity through SHA-256 hashing, converts heterogeneous logs into normalized forensic events, detects suspicious patterns using transparent rules and explainable machine learning, correlates evidence across sources, reconstructs an investigator-reviewable timeline, maintains traceability from findings back to source evidence, and produces immutable, evidence-backed investigation reports.

The system is not described as operating without investigator oversight, not as a product that certifies evidence, and not as a system that establishes criminal conduct. It is a **prototype-level forensic workflow** that supports an investigator.

## 2. Problem statement

Investigators hold heterogeneous, unstructured, multi-source evidence and must manually answer: *What happened? In what order? Which evidence supports that? What is anomalous?* Manual correlation across logs is slow, error-prone, and leaves no reproducible audit trail.

FORENSIGHT AI implements: **integrity-preserving ingestion → parsing → normalization → explainable detection → cross-source correlation → reconstructed timeline → traceable reporting**, entirely local and reproducible.

## 3. Core novelty (central claim)

> **Evidence-traceable AI-assisted forensic investigation.**

```
FINDING      "FILE-001: Mass file modifications in a short window"
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
| 14 | Report generation (immutable JSON snapshots + print UI) | `services/report_service` | Secondary (implemented, Phase 6) |
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
| `forensic_events` | Normalized events | timestamp, source_type, entities, **anomaly_score**, **is_anomalous**, metadata, dedupe_hash, raw_record_id |
| `rule_findings` | Rule hits | **finding_uid (RFND-)**, run_id, rule_id, severity, confidence, explanation, reasons, **composite_suspicion_score**, **components**, triggered_event_ids, evidence_ids, **status** |
| `ml_findings` | ML findings | **finding_uid (MFND-)**, run_id, model_name/version, score, threshold, **composite_suspicion_score**, **components**, explanation, **feature_snapshot**, event_ids, evidence_ids, status |
| `classifier_results` | Segment-level predictions (planned, later phase) | window_start/end, predicted_label, class_score |
| `correlations` | Chain placements (Phase 4) | chain_uid, position, link_score, **link_reason** |
| `investigation_groups` | Phase 4 activity groups | group_uid, kind, title, explanation, member refs |
| `investigation_runs` | Pipeline runs | **run_uid (IRUN-)**, stage (Process/Analyze/Correlate/Report), status, **stats (ML methodology + fusion weights + rule config)**, error |
| `investigator_notes` | Investigator annotations | author, body, finding_uid |
| `model_metrics` | Real evaluation results | precision, recall, f1, feature_list, dataset_desc |
| `processing_runs` | Parse/normalize runs | run_id, evidence_id, parser, status, received/normalized/rejected/duplicates, warnings, error, timestamps |
| `assistant_queries` | Assistant Q&A (Phase 5, append-only) | query_id, case_id, question, intent, answer, evidence refs, basis, confidence, sources JSON, disclaimer, actor, created_at |
| `investigation_reports` | Forensic report snapshots (Phase 6, immutable, case-scoped) | **report_id (RPT-)**, case_id, title, schema, report_version, status, generated_by, **sections JSON**, recorded_at |

Relationships: `Case 1→N Evidence 1→N RawRecord/ForensicEvent` and `Evidence 1→N ProcessingRun`; every finding carries event-ID and evidence-ID arrays for direct traceability; `assistant_queries` is case-scoped and never rewritten (repeated questions append new rows).

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
ANALYZE → FeatureBuilder → 5-minute event windows → Strategy A IsolationForest
        → dual gate (normalized score + z-gate) → annotate events → RuleEngine
        → RuleFindings (RFND-) + MlFindings (MFND-) → fusion → Composite Suspicion Score
        → custody(Automated Analysis Started/Completed)
CORRELATE → reason-tagged links → chains → Reconstructed Investigation Timeline → graph
REPORT  → deterministic 15-section JSON snapshot → custody(Report Generated)
```

**Timestamp handling:** ISO-8601 (±Z), `YYYY-MM-DD HH:MM:SS[.fff]`, Apache-style, US format, epoch s/ms — tried in order; unparseable rows are rejected *with reason* and retained. **Field aliases:** `user|username|account → user`, `ip|src_ip|source_ip → source_ip`, `ts|time|timestamp|@timestamp → timestamp`, etc.

**Processing-run semantics (v1.2, hardened in v1.6):** a run reads at most `MAX_RECORDS_PER_RUN` records (default 200 000); any remainder is reported as a warning. Status is `FAILED` when the file cannot be processed safely (unknown format, unreadable content, or recorded SHA-256 no longer matching the stored bytes); `PARTIAL` when rows were rejected, no rows were produced (`received == 0`), or the record cap truncated the input; otherwise `COMPLETED`. Rejects are explained and retained (`raw_records.reject_reason`); duplicates are marked on derived events (never deleted, never silently doubled in counts); reprocessing replaces the derived rows for that evidence and appends a new run entry without modifying raw bytes. **Exception (v1.6):** when preserved history already references that evidence's events — correlation links hold a foreign key to the event rows, stored findings/groups hold event-uid lists — the rebuild is *skipped* for that evidence, the existing rows are kept, and the run records an explanatory warning (`rebuild skipped: ...`); append-only history is never rewritten and no run is failed by this condition.

## 9. ML methodology (Strategy A, single strategy)

### 9.1 Strategy A — window-level anomaly detection (implemented, Phase 3)

| Field | Definition |
|---|---|
| Unit of scoring | **Non-overlapping 5-minute windows** (`ANALYSIS_WINDOW_MINUTES=5`, floor-aligned); each window aggregates all case events falling inside it |
| Feature set (per window, deterministic order) | hour_sin, hour_cos, event-type counts one-hot, total events, writes, failed logins, external connections, distinct users, distinct hosts, distinct IPs, inter-event gap stats, off-hours ratio, rare-IP flag, rare-user flag, entity breadth — see `engines/features.py` |
| Model | `sklearn.ensemble.IsolationForest(n_estimators=ML_N_ESTIMATORS=200, random_state=RANDOM_STATE=42, n_jobs=1)` |
| Scoring | `decision_function()` raw values min–max normalized to a **window anomaly score ∈ [0,1]** (1 = most anomalous); `score_samples` recorded alongside; formula stored with the run |
| **Dual detection gate** | A window is anomalous iff **normalized score ≥ `ANOMALY_THRESHOLD` (0.72, env)** AND **raw score < mean − `ML_Z_SIGMAS` (2.0) · std** across scored windows. Both conditions must hold (`threshold_gate` + `z_gate` recorded per window) |
| Why two gates | The fixed constant alone can fire on dense benign activity; the z-gate requires the window to be a statistical outlier *relative to this case*, keeping benign scenarios quiet while staying fully deterministic and auditable |
| **Abstention** | If fewer than `ML_MIN_WINDOWS` (8) windows exist, the model **abstains**: no scores, no ML findings, run stats record `abstained=true` with a human-readable reason — the system says nothing rather than guessing |
| Reproducibility | Fixed seed, fixed feature order, fixed thresholds, single-threaded scoring, seeded demo data → identical scores across runs (asserted by test) |

**Stored with every `InvestigationRun.stats`:** `model_name, model_version, random_state, feature_list, training_scope="case", scoring_method, score_normalization, threshold_value, threshold_method="fixed_constant", threshold_gate, z_sigmas, decision_gate, reference_mean, reference_std, window_minutes, windows_scored, abstained, sklearn_version, fusion_weights, fusion_formula_version, rule_config`.

**Anchoring to events:** each anomalous window's score is written onto the events inside it (`ForensicEvent.anomaly_score`, `is_anomalous`); an ML finding (`MFND-{n:06d}`) is created per anomalous window with the **mean score of its triggering events**, `feature_snapshot`, severity **High if score ≥ `ML_HIGH_SCORE` (0.9) else Medium**, capped at `RULE_MAX_FINDINGS_PER_RULE` (10) per run.

**UI contract:** every display shows **"Anomaly score"** *and* **"Detection threshold"** side by side, with the note: *"The anomaly score indicates statistical deviation from this case's typical event patterns. It is not proof of malicious activity and requires investigator review."* ML-metrics endpoint exposes the full stats payload (`GET /api/cases/{id}/ml-metrics`).

### 9.2 Segment-level classification (planned, later phase — not implemented)

| Field | Definition |
|---|---|
| Concept | **Case/segment-level classification** — a label for a *time segment* of case activity. Never presented alongside event anomaly scores as the same thing. |
| Training sample unit | **Fixed 10-minute window** of case activity. One sample = aggregated features of one window across all sources (counts per source type, distinct users/IPs, write rate, rename rate, external connections, off-hours ratio, mean/max event anomaly score, event-type entropy). Windows are cut identically for training and inference. |
| Labels | From scenario generator provenance: normal-scenario windows → `benign`; compromise scenario → `benign` before the anchor event, `compromise` after; ransomware-like scenario → `ransomware_like` for impact windows. |
| Model | `RandomForestClassifier(n_estimators=200, random_state=42, class_weight="balanced")` with `LogisticRegression` baseline. |
| Evaluation | Stratified 75/25 split (seed 42) + 5-fold stratified CV; precision/recall/F1/accuracy/confusion matrix stored in `model_metrics`. |
| Claims | **No real-world performance claims.** Mandatory label: **"Trained and evaluated on synthetic demonstration data."** repeated in the report's Limitations. |
| Output wording | e.g. *"Window 10:41–10:51 classified: ransomware_like (class score 0.83) — synthetic-data model, requires investigator validation."* |

### 9.3 Hybrid fusion — Composite Suspicion Score (implemented, Phase 3)

```
Composite Suspicion Score (CSS) ∈ [0,1] — uncalibrated heuristic, NOT a probability

CSS = 0.40 · RuleComponent        (0 if no rule; else 0.5 + 0.5·severity weight:
                                   Low .25 / Medium .5 / High .75 / Critical 1.0)
    + 0.35 · AnomalyComponent     (mean anomaly score of the finding's triggering
                                   events; 0 if no anomaly annotation)
    + 0.25 · CorrelationComponent (distinct supporting evidence files ÷ 5, capped 1.0;
                                   as-built keeps this Phase 3 proxy — see Changelog v1.5)

Bands: <0.35 Informational · 0.35–0.55 Low interest ·
       0.55–0.75 Anomalous — review · ≥0.75 Potentially suspicious — high priority
```

Weights live in `engines/ml/fusion.py` (`fusion_v1`), are shown verbatim in the UI explanation panel and in the report, and are stored in `InvestigationRun.stats`. Caption: *"The Composite Suspicion Score is an uncalibrated heuristic composite — not a probability and not proof of malicious activity. Requires investigator validation."*

## 10. Rule engine (transparent, implemented, Phase 3)

Deterministic, config-driven rules (`app/engines/rules/`), each producing rule_id, title, severity, confidence, triggering events, evidence IDs, timestamp span, human explanation, and structured `reasons`. Findings are capped at `RULE_MAX_FINDINGS_PER_RULE` (10) per rule per run; disabled rules produce nothing (`RULE_<ID>_ENABLED` env, e.g. `RULE_AUTH002_ENABLED=false`).

| Rule ID | Title | Severity | Trigger (config defaults) |
|---|---|---|---|
| `AUTH-001` | Repeated failed logins followed by a successful login | High (failure→success) / Medium (standalone burst) | ≥ `RULE_AUTH001_MIN_FAILURES` (3) failures for one user within `RULE_AUTH001_WINDOW_MINUTES` (15), either followed by a success in-window or as a burst without success |
| `AUTH-002` | Authentication events from an unusual external source IP | Medium | ≥ `RULE_AUTH002_MIN_EXTERNAL_LOGINS` (3) auth events from one external source IP |
| `AUTH-003` | Rapid login sequence from two distinct source addresses | Low | two logins for one user within `RULE_AUTH003_WINDOW_SECONDS` (60) from different source IPs |
| `PROC-001` | Scripting or interpreter process execution | Medium; **High** when command line carries evasion indicators (`-enc`, `-w hidden`, `frombase64`, `downloadstring`, `iex(`, …) | process event on a scripting host/interpreter (PowerShell, cmd, wscript, certutil, python, …) |
| `FILE-001` | Mass file modifications in a short window | Medium; **High** at ≥ `RULE_FILE001_HIGH_MIN` (15) | ≥ `RULE_FILE001_MIN_MODIFICATIONS` (6) modifying actions (write/delete/create/copy/…) for one host+user within `RULE_FILE001_WINDOW_MINUTES` (15) |
| `FILE-002` | Rapid file rename burst | High | ≥ `RULE_FILE002_MIN_RENAMES` (3) renames for one host+user within `RULE_FILE002_WINDOW_MINUTES` (10) |
| `NET-001` | External connection shortly after process execution | Medium | ≥ `RULE_NET001_MIN_CONNECTIONS` (2) external-connection events on a host, each within `RULE_NET001_WINDOW_MINUTES` (15) after a process event on the same host |

- **Entity scoping:** burst rules are keyed per user, or per host+user, or per source IP as appropriate — one noisy user cannot trigger for the whole case.
- **External IP:** outside RFC1918 private space and unobserved as a source in the case (`ipaddress` module + case scoping), stated as a statistical observation.
- **Determinism:** findings ordered by (timestamp, rule_id); UIDs `RFND-{n:06d}` assigned per analysis run in Python (session `autoflush=False`).
- **Confidence:** fixed deterministic indicator weight per severity (Low 0.4 / Medium 0.6 / High 0.8 / Critical 0.95) — not a probability (`RULE_CONFIDENCE_NOTE`).
- Rule findings and ML findings are distinct record types displayed in separate sections; fusion combines them into the Composite Suspicion Score. IDs are the stable contract used by tests, UI filters, and the terminology guard.

## 11. Multi-source correlation (reasoned, non-causal — implemented, Phase 4)

Every link carries an explicit, evidence-backed reason. Temporal association is never presented as causation.

**Correlation types (implemented order, `CORR-001` … `CORR-005`):**

| ID | Type | Rule |
|---|---|---|
| `CORR-001` | Same-host activity chain | events share `host` within `CORRELATION_WINDOW_SECONDS` (300) |
| `CORR-002` | Same-user activity chain | events share `user` within the window |
| `CORR-003` | Same-source-IP authentication cluster | auth/network events share `source_ip` within the window |
| `CORR-004` | Process → file relationship | process event on same host with file events within the window |
| `CORR-005` | Process → network relationship | process event on same host with external network events within the window |

**Confidence (additive, capped at 1.0):** same host **+0.30**, same user **+0.30**, same time window **+0.25**, same source IP **+0.15** — presented as LOW / MEDIUM / HIGH bands. Each stored correlation records `event_a_id`, `event_b_id`, type, confidence, **`reason` text**, evidence IDs, and the run that produced it. Runs are append-only, `CORR-{n:06d}`.

**Activity groups:** correlated events are clustered into `investigation_groups` (e.g. *Authentication cluster*, *Process execution cluster*, *File activity burst*, *External connection cluster*) with title, kind, time span, member events, and a human explanation. Only evidence-backed clusters are grouped — no inferred entities.

**Caption everywhere correlation appears:** *"Correlation indicates co-occurrence and shared context, not causation. Requires investigator validation."*

## 12. Reconstructed Investigation Timeline (implemented, Phase 4)

- Union of anomalous events, rule-triggering events, correlation members, plus ±2 min context.
- Ordered by **real recorded timestamps** (never fabricated); each entry carries significance (`NORMAL` / `NOTABLE` / `SUSPICIOUS`, derived from Phase 3 findings — ML anomaly → NOTABLE, rule hit or composite band ≥ 0.75 → SUSPICIOUS), an explanation, and **source evidence IDs + raw record IDs** — click-through reaches the original row.
- Heuristic phase segmentation: *Initial Access / Execution / Impact / Exfiltration / Benign Context* (ATT&CK-style labels, described as heuristic).
- Label: **"Reconstructed Investigation Timeline"** with the note: *"A reconstruction derived from the evidence available in this case. It is not an established sequence of events."*

## 13. AI investigation assistant (deterministic, retrieval-first) — implemented, Phase 5

1. Classify the question into supported intents (what happened / suspicious events / evidence for hypothesis / what preceded X / users / IPs / support finding).
2. Execute parameterized queries against actual case data.
3. Construct the answer strictly from retrieved rows.
4. Return **evidence IDs** (and event IDs where useful).
5. If the data does not support an answer: **"Insufficient evidence in the current case."**

No generative model is enabled. An optional LLM adapter interface exists but is **disabled and labelled "Prototype / Planned"**. Footer: *"Answers are constructed only from processed case evidence. No generative model is enabled."*

**As-built (v1.7, Phase 5):** a closed 14-intent catalog (`CASE_SUMMARY, TOP_FINDINGS, FINDING_EXPLANATION, FINDING_TRACE, EVIDENCE_SUPPORT, TIMELINE_CONTEXT, CORRELATION_SUMMARY, GROUP_SUMMARY, ML_EXPLANATION, REVIEW_QUEUE, INTEGRITY_STATUS, PROCESSING_STATUS` + control intents `CAPABILITIES, UNKNOWN`) with deterministic keyword/regex classification; every answer is reconstructed from bounded, case-scoped queries that reuse the analysis/correlation/processing services, and carries `evidence`, `basis`, a confidence band (`HIGH/MEDIUM/LOW`), clickable `sources`, and the standing footer. Unsupported questions return a fixed deterministic message; an empty case returns *"No forensic evidence is currently available for this case."* for all intents except CAPABILITIES/UNKNOWN. Finding references are extracted case-insensitively and uppercased; a reference that does not exist in the case returns a structured `FINDING_NOT_FOUND` 404 — never data from another case. Every query is persisted append-only in `assistant_queries` (case-scoped, 17th table), repeated questions append new rows, and history answers are served newest-first. The ML explanation intent states plainly that the score reflects statistical deviation and is not proof — SHA-256 confirms the file is unchanged and implies nothing about authenticity or admissibility.

### 13.1 Investigation report layer (evidence-backed snapshots) — implemented, Phase 6

`POST /api/cases/{case_id}/reports` generates a deterministic, case-scoped forensic report and stores it as an **immutable JSON snapshot** (`InvestigationReport`, 18th table). Generation consumes **only persisted Phase 0–5 data** — the report layer performs no analysis, no ML, and no NLP at generation time — so the section payloads (`sections`) are **byte-deterministic** for a fixed database state: every identity field (`report_id`, `generated_at`, `title`, `generated_by`) is carried as report metadata, never inside the sections.

**Contract:** report IDs `RPT-{n:06d}` come from a **single global sequence across all cases**. A report belongs to exactly one case; requesting it, or its `/json` cache, under any other case returns `REPORT_NOT_FOUND` (404). Every generation records a `Report Generated` custody action with `{report_id, title, report_version, schema}` and updates `case.last_activity`; generation must **not mutate** evidence, findings, correlations, groups, timelines, or assistant history (asserted by test). The stored JSON is served unchanged by the detail and `/json` endpoints (schema 1, `recorded_at`); re-generating reads current state and never edits an existing snapshot.

**Sections (fixed order, 15):** `header` · `executive_summary` · `evidence_inventory` · `integrity_verification` · `processing_summary` · `key_findings` · `finding_traceability` · `cross_source_correlation` · `activity_groups` · `incident_timeline` · `evidence_graph_summary` · `investigator_review` · `ai_ml_explanation` · `investigation_conclusion` · `limitations`.

- **Integrity status (latest check per evidence, `checked_at` desc then `id` desc):** no checks → `NO CHECK AVAILABLE`; any `INTEGRITY MISMATCH` wins; all verified → `INTEGRITY VERIFIED`; otherwise `NOT VERIFIED`. (Uploading evidence auto-records a verified check at ingest, so a "no check" report only appears when an evidence row has no check at all.)
- **Conclusion modes:** no evidence → `REPORT_NO_ANALYSIS`; zero events and zero findings → `REPORT_CONCLUSION_INSUFFICIENT`; zero findings → `REPORT_CONCLUSION_NO_FINDINGS`; otherwise `WITH_CORRELATION` / `NO_CORRELATION`; high/critical findings append `REPORT_HIGH_SEVERITY_NOTE` to the conclusion notes.
- **Honesty contract (guard-tested):** report wording never claims authenticity, admissibility, or probability; the ML explanation repeats the standing statistical-deviation disclaimer; abstention (`ML_MIN_WINDOWS`) and all caps — 200 findings, 50 trace rows, 200 correlations, 200 groups, 200 process runs, 50 graph rows (`_REPORT_MAX_*` module bounds) — are surfaced as explanatory notes; demo cases carry the `SYNTHETIC / DEMONSTRATION DATA` marker in the executive summary.
- **UI:** `/cases/{case_id}/reports` (generate with optional title + actor, newest-first list) and `/cases/{case_id}/reports/{report_id}` (a generic section renderer — field blocks, key/value pairs, and object-row tables with truncated hashes — plus a **Print report** button and a dedicated `@media print` stylesheet: `#root` forced white, `.print-hide` chrome removed, `.report-print` sections black-on-white with `break-inside: avoid`).

## 14. Demo scenarios (synthetic, seeded, labelled)

All files carry a `SYNTHETIC / DEMONSTRATION DATA` marker; fictional personas only; generated by `demo/generate_scenarios.py` with seed 42 (reproducible hashes).

- **Scenario A — Normal activity** (~150 events): expected — no high-severity findings, low anomaly scores. Proves the system does not raise alarms without cause.
- **Scenario B — Account compromise** (~220 events): failed-login burst → success from a new external IP → recon → PowerShell → targeted reads → outbound connection. Expected: AUTH-001/002/003, PROC-001, NET-001, anomalous windows.
- **Scenario C — Ransomware-like incident** (~450 events): browser download → PowerShell → 1,200 file modifications/renames in 90 s → shadow-copy deletion → external connection. Expected: PROC-001, FILE-001, FILE-002, NET-001. Conclusion wording: *"Evidence is consistent with ransomware-like activity and requires investigator validation."*

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

**Implemented (Phase 3):**

| Method | Path | Description |
|---|---|---|
| POST | `/api/cases/{case_id}/analyze` | Run automated analysis (rules + Strategy A + fusion) — append-only, custody `Automated Analysis Started` / `Automated Analysis Completed` |
| GET | `/api/cases/{case_id}/analysis-runs` | Analysis run history (newest first) with ML methodology + rule config in `stats` |
| GET | `/api/cases/{case_id}/findings` | Findings (filters: kind `rule`/`ml`, severity, status, run_id; limit/offset) |
| GET | `/api/cases/{case_id}/findings/{finding_id}` | Finding detail: reasons, components, CSS + band, traceability IDs, investigator notes |
| GET | `/api/cases/{case_id}/findings/{finding_id}/trace` | Evidence ladder: finding → events → raw records → evidence + SHA-256 |
| PATCH | `/api/cases/{case_id}/findings/{finding_id}` | Review workflow: New → Under Review → Confirmed/Dismissed (invalid transitions → 409) |
| GET | `/api/cases/{case_id}/ml-metrics` | ML methodology stats + config for the latest analysis run |

**Implemented (Phase 4):**

| Method | Path | Description |
|---|---|---|
| POST | `/api/cases/{case_id}/correlate` | Run cross-source correlation — reason-tagged links + activity groups (append-only, no custody actions) |
| GET | `/api/cases/{case_id}/correlation-runs` | Correlation run history (newest first) with stats |
| GET | `/api/cases/{case_id}/correlations` | Correlations of a case (filters: type, run_id, limit ≤ 500/offset; latest run by default) |
| GET | `/api/correlations/{correlation_id}` | One correlation with both events + raw record / evidence (SHA-256) details |
| GET | `/api/cases/{case_id}/groups` | Activity groups (filters: kind, run_id) |
| GET | `/api/groups/{group_id}` | One activity group with member events |
| GET | `/api/cases/{case_id}/timeline` | Reconstructed Investigation Timeline (significance from findings; `TIMELINE_MAX_ENTRIES` cap) |
| GET | `/api/cases/{case_id}/graph` | Evidence graph (capped nodes/edges + `table_rows` fallback) |

**Implemented (Phase 5):**

| Method | Path | Description |
|---|---|---|
| POST | `/api/cases/{case_id}/assistant/query` | Ask the deterministic assistant (question ≤ 1000 chars, actor ≤ 127); returns intent, answer, evidence, basis, confidence, sources, disclaimer (201) |
| GET | `/api/cases/{case_id}/assistant/history` | Append-only query history for the case (newest first; limit 1–500, default 100) |
| GET | `/api/cases/{case_id}/assistant/queries/{query_id}` | One stored answer (404 `ASSISTANT_QUERY_NOT_FOUND` if not in this case) |

**Implemented (Phase 6):**

| Method | Path | Description |
|---|---|---|
| POST | `/api/cases/{case_id}/reports` | Generate + store an immutable forensic snapshot (`{title? ≤255, actor? ≤127}`); 201, custody `Report Generated`, global `RPT-{n:06d}` sequence |
| GET | `/api/cases/{case_id}/reports` | Report summaries for the case (newest-first) |
| GET | `/api/cases/{case_id}/reports/{report_id}` | One report with its 15 deterministic sections (404 `REPORT_NOT_FOUND` if not in this case) |
| GET | `/api/cases/{case_id}/reports/{report_id}/json` | The raw stored snapshot `{metadata, sections}` (cached JSON, unchanged since generation) |

**Planned (later phases, subject to scope tiers):**

```
GET  /api/evidence/{ev_id}[/download|/records]
POST /api/cases/{id}/notes                     POST /api/demo/load
```

All errors use a uniform envelope `{error:{code,message,detail}}`; server paths are never exposed.

## 16. Security considerations

Upload extension allowlist + size cap (25 MB) + MIME sniff; filename sanitisation with UUID storage names (traversal-proof); zip-slip guards when ZIP lands; raw store write-once with no overwrite path; no execution of uploaded content; Pydantic validation on every input; parameterized SQL via ORM; evidence text always rendered escaped; evidence treated as data (never as instructions); request logging; report embeds every SHA-256 so a third party can re-verify independently; CSV export neutralises spreadsheet formula prefixes. Report sections are bounded by the documented caps, served from an immutable cache, and rendered with escaped text in the UI (no `dangerouslySetInnerHTML`).

## 17. Testing strategy

- **Unit:** hashing (known vectors), integrity verified/mismatch, write-once refusal, each parser, normalizer (timestamps/aliases/rejects/dedupe), rule engine positive+negative (per-rule unit tests + catalog assertions), feature windowing determinism, anomaly dual-gate + abstention + seed reproducibility, fusion formula/bands, review workflow transitions, correlation windows/link reasons, timeline ordering, graph generation, assistant intents incl. insufficient-evidence, report sections contain SHA-256 hashes.
- **Report (Phase 6):** 15-section snapshot shape with section determinism across generations (identity fields excluded), snapshot immutability while a later report reflects new state, integrity status modes (VERIFIED / MISMATCH / NO CHECK AVAILABLE), conclusion modes (no-analysis / insufficient / no-findings / correlation outcomes), title+actor limits (422/201), global `RPT-` sequence, newest-first list, cross-case isolation (404 `REPORT_NOT_FOUND`), malformed-ID 404/422, read-only generation (pipeline rows byte-unchanged), `Report Generated` custody, honest ML abstention wording, banned wording absent.
- **Parsing unit:** CSV header/encoding fallback/column normalize/row-numbering; JSON object/array/wrapper; detection precedence (JSON wins over extension, declared type, unknown-format errors); timestamp formats incl. epoch, Apache, offsets; normalizer metadata preservation of source-specific fields.
- **Processing API:** run lifecycle (COMPLETED/PARTIAL/FAILED), record cap warning, integrity mismatch → FAILED run, unknown format → 422 + FAILED, rejects retained with reasons, duplicates marked with `duplicate_of`, reprocessing replaces derived rows (or is skipped with an explanatory warning when history pins them), events list/detail + filter contract.
- **API:** CRUD + happy/error paths (413/415/404/409).
- **End-to-end:** demo load → verify → process → analyze → correlate → timeline → graph → assistant → report; asserts Scenario A quiet / C fires; raw hashes unchanged after pipeline; banned terms absent from UI strings.
- **Regression gate every phase:** `pytest` green + `npm run build` green.
- **Phase 6 report gate:** a fresh-temp-database script that drives the report endpoints over a real pipeline (empty-case contract, evidence-backed content, generation determinism + snapshot immutability, cross-case isolation and malformed-ID traversal, read-only generation, custody + global `RPT-` sequence, corruption → `INTEGRITY MISMATCH` verdict, synthetic demo marker, and a wording-honesty sweep over every captured report body).
- **Phase 4.5 core gate:** a fresh-temp-database end-to-end script that drives every API route (upload → verify → process → analyze → correlate → timeline → graph → review → re-run), checks raw-hash immutability (pre == recorded == post), finding/timeline/graph traceability chains, repeatability across two identical pipelines, empty/error/422/404/409 envelopes, append-only history on repeated operations, SQLite table/FK integrity (`PRAGMA foreign_key_check`), the three demo scenarios with honest ML abstention, a terminology harvest over every captured response, and informational performance timings.

## 18. Risks and limitations

| Risk | Mitigation |
|---|---|
| Wording drift back to overreaching claims | Single terminology constants module + banned-term test scanning constants and docs; same strings reused in UI/report |
| Fixed threshold 0.72 poorly calibrated on new data | Case-scoped scoring, always shown *with* its threshold, documented as prototype calibration; no universal detection claims |
| Segment classifier confused with event scores | Separate models, endpoints, and UI sections; window unit defined once and shared by training/inference |
| Composite score misread as a probability | Field never named "probability"; caption mandatory; components shown |
| Correlation read as causation | Per-link reasons required; caption on every correlation view |
| Raw evidence mutated by future changes | Write-once store (no overwrite API) + post-pipeline hash regression test |
| Reprocessing rewrites history that already references it | Derived rows pinned by correlation links / finding / group references are never replaced — the rebuild is skipped for that evidence with an explanatory warning (`processing_service._history_pins_events`) |
| Scope creep | Tier system with cut order; Phase 4.5 core gate before secondary work |
| Synthetic-data overclaim | Mandatory synthetic-data labels on classifier metrics and demo banners |
| Hallucinated assistant answers | Deterministic retrieval only; insufficient-evidence path; LLM disabled |

## 19. Phase plan

| Phase | Deliverable | Exit criteria |
|---|---|---|
| **0** | Scaffolding, data model, terminology guard, write-once store, frontend skeleton | 12 acceptance criteria below — **DONE** |
| **1** | Case management + upload + SHA-256 verify + controlled integrity test + custody UI | upload→hash→verify→mismatch works in UI — **DONE** |
| **2** | Parsers + normalizer + processing log + events UI | demo files → correct counts, rejects explained — **DONE** |
| **3** | Rules + Strategy A anomaly detection + fusion + findings UI | Scenario C fires, Scenario A quiet, findings reviewable — **DONE** |
| **4** | Reasoned correlation + activity groups + reconstructed timeline + evidence graph + investigation UI | multi-source chains, traceable entries — **DONE** |
| **4.5** | **Core acceptance gate** | e2e core pipeline green, raw hashes unchanged — **DONE** |
| **5** | **Investigation assistant** (deterministic, retrieval-first) | example questions answered from evidence; cross-case isolation — **DONE** |
| **6** | **Investigation report layer** (immutable JSON snapshots + print UI) | deterministic 15-section report, snapshots immutable, global sequence, cross-case 404, custody — **DONE** |
| 7 | Dashboard | scenario stats |
| 8 | Segment classifier metrics | synthetic-data-labelled metrics, no real-world claims |
| 9 | Notes (investigator annotations) | persisted annotations in the findings UI |
| 10 | Demo loader + polish + history | evaluator journey works end-to-end |
| 11 | Stretch (ZIP, EVTX, PCAP, optional LLM adapter, Docker) | only if 0–10 green |

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

### Phase 3 acceptance criteria (all 15) — status

| # | Criterion | Status |
|---|---|---|
| 1 | Rule engine with the full catalog (AUTH-001/002/003, PROC-001, FILE-001/002, NET-001), deterministic ordering, per-rule cap (10), config snapshot stored per run | ✅ |
| 2 | Rules are config-driven via env (`RULE_<ID>_ENABLED`, thresholds) with no hard-coded INT rules | ✅ |
| 3 | Strategy A: non-overlapping 5-minute windows, IsolationForest (seed 42), min-max normalized decision score | ✅ |
| 4 | Dual detection gate: normalized ≥ 0.72 AND raw < mean − 2·std; both recorded per window | ✅ |
| 5 | Abstention when windows < 8 — no ML findings, reason recorded in run stats | ✅ |
| 6 | Events annotated with `anomaly_score` / `is_anomalous`; UI shows score alongside threshold | ✅ |
| 7 | ML findings (`MFND-`) with feature snapshot, severity High ≥ 0.9 / else Medium, capped at 10 | ✅ |
| 8 | Fusion `fusion_v1`: CSS = 0.40·rule + 0.35·anomaly + 0.25·correlation proxy, band assignment, stored in finding + run | ✅ |
| 9 | `POST /analyze` creates an `IRUN-` run (append-only history), custody `Automated Analysis Started/Completed` | ✅ |
| 10 | Findings list filters (kind/severity/status/run) + pagination; detail + trace endpoints expose the full evidence ladder | ✅ |
| 11 | Review workflow enforced server-side: New → Under Review → Confirmed/Dismissed; invalid/unchanged → 409 | ✅ |
| 12 | `GET /ml-metrics` returns methodology stats + config + scope note | ✅ |
| 13 | Findings UI: list with filters/status badges, detail with reasons/components/CSS band/trace, run history on case page | ✅ |
| 14 | Tests: 17 analysis tests incl. dual-gate behavior, abstention, determinism, fusion formula/bands, review workflow, re-analysis append-only | ✅ |
| 15 | Regression gate: `pytest` green (180 tests) + `npm run build` green; docs updated to v1.4; banned terms absent from constants and docs | ✅ |

### Phase 4 acceptance criteria — status

| # | Criterion | Status |
|---|---|---|
| 1 | Five correlation types (`CORR-001`…`CORR-005`) evaluated per event pair inside `CORRELATION_WINDOW_SECONDS` (300); precedence most-specific-first; one type per pair | ✅ |
| 2 | Additive confidence (time +0.25, host +0.30, user +0.30, IP +0.15, cap 1.0) with LOW/MEDIUM/HIGH bands; every link stores an explicit `reason` | ✅ |
| 3 | Activity groups = union-find over links (≥ 2 events), capped (`MAX_GROUPS_PER_RUN` 50, `MAX_GROUP_MEMBERS` 200), with kind, title, severity, time span, explanation | ✅ |
| 4 | Correlation runs append-only (`CORR-{n:06d}` run / `COR-{n:06d}` link / `GRP-{n:06d}` group); re-correlation never rewrites history | ✅ |
| 5 | Timeline = union of rule/ML/anomalous events + correlation members + ±2 min context, ordered by real timestamps, significance `SUSPICIOUS`/`NOTABLE`/`NORMAL`, capped at `TIMELINE_MAX_ENTRIES` (500) with a note | ✅ |
| 6 | Evidence graph: evidence → finding → event → correlation layers, capped at 200 nodes / 500 edges, always includes `table_rows` fallback | ✅ |
| 7 | API: 8 endpoints per §15 with uniform error envelope (400 `NO_NORMALIZED_EVENTS`, 404 run/correlation/group not found, 422 unknown type/kind, `correlations` limit ≤ 500) | ✅ |
| 8 | Correlation records **no** custody actions (custody CHECK constraints untouched) | ✅ |
| 9 | Investigation UI: run correlation + run history, correlation filters + row detail (reason, shared entities, both events with raw record + evidence SHA-256), group detail, timeline with significance filter, React Flow graph + table fallback | ✅ |
| 10 | Case page: Cross-source correlation section (Open investigation, Run correlation, run history) | ✅ |
| 11 | Tests: 26 correlation tests (links/groups/timeline/graph engines + API + wording guards); full suite green | ✅ |
| 12 | Regression gate: `pytest` green (206 tests) + `npm run build` green; docs updated to v1.5; banned terms absent from constants and docs | ✅ |
| 13 | Deferred (not in Phase 4 as-built): heuristic phase segmentation of the timeline; fusion still uses the Phase 3 correlation proxy (§9.3) | ⚠️ deferred |

### Phase 6 acceptance criteria — status

| # | Criterion | Status |
|---|---|---|
| 1 | `POST /api/cases/{case_id}/reports` generates and **persists** an immutable JSON snapshot (`InvestigationReport`, 18th table summarised in §6); identity fields (`report_id`, `generated_at`, `title`, `generated_by`) live in metadata only | ✅ |
| 2 | 15 fixed-order sections (§13.1) built **only from persisted Phase 0–5 data**; sections byte-deterministic across generations with different title/actor; list newest-first | ✅ |
| 3 | Report IDs `RPT-{n:06d}` from a **single global sequence across cases**; custody `Report Generated` recorded; `case.last_activity` updated; no pipeline table mutated by generation | ✅ |
| 4 | Detail + `/json` endpoints serve the cached snapshot unchanged; re-generation reads current state and never edits prior snapshots | ✅ |
| 5 | Integrity section modes: `INTEGRITY VERIFIED` / `INTEGRITY MISMATCH` / `NOT VERIFIED` / `NO CHECK AVAILABLE`, latest check wins | ✅ |
| 6 | Conclusion modes: no-analysis / insufficient / no-findings / with-correlation / no-correlation; high/critical findings append `REPORT_HIGH_SEVERITY_NOTE` | ✅ |
| 7 | Bounds enforced as module caps (200 findings / 50 traces / 200 correlations / 200 groups / 200 process runs / 50 graph rows) and reported as notes | ✅ |
| 8 | Demo cases carry the `SYNTHETIC / DEMONSTRATION DATA` marker; ML abstention and methodology stated honestly; wording never claims authenticity, admissibility, or probability | ✅ |
| 9 | Cross-case isolation: another case's report (or its `/json`) is 404 `REPORT_NOT_FOUND`; malformed IDs (`RPT-ABC`, percent-encoded traversal, `RPT-000001/../../etc`) are 404/422 | ✅ |
| 10 | UI: `/cases/{case_id}/reports` (generate + list) and `/cases/{case_id}/reports/{report_id}` (generic section renderer, table fallbacks, truncated hashes, **Print** + dedicated `@media print` stylesheet) | ✅ |
| 11 | Tests: 23 report tests in `backend/tests/test_reports.py` (backend suite now **253 passed**) | ✅ |
| 12 | Regression gate: `pytest` green (253 tests) + `npm run build` green + fresh-database `gate_phase6.py` (104 checks) green; docs updated to v1.8; banned terms absent from constants and docs | ✅ |
| 13 | No new third-party dependencies added in Phase 6 (frontend print uses the browser; backend uses stdlib + existing stack) | ✅ |

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

## 23. Changelog — v1.2 → v1.4 additions (Phase 3)

*(v1.3 was folded into this revision; the code references v1.4 section numbers.)*

1. **Strategy A replaces event-level scoring (§9.1).** Anomaly detection scores **non-overlapping 5-minute windows** (not individual events) with a seeded IsolationForest over a deterministic 18-feature window vector. Detection requires the **dual gate**: min-max normalized decision score ≥ `ANOMALY_THRESHOLD` (0.72) **and** raw score below `mean − ML_Z_SIGMAS (2.0)·std` for the case. The model **abstains** when a case has fewer than `ML_MIN_WINDOWS` (8) windows. Window scores are annotated onto contained events (`anomaly_score`, `is_anomalous`).
2. **Rule catalog implemented (§10).** Stable IDs `AUTH-001/002/003`, `PROC-001`, `FILE-001/002`, `NET-001` replace the placeholder `RULE-00n` list. All thresholds are env-configurable (`RULE_*`), a config snapshot is stored per run, findings are capped at 10 per rule, and confidence is a documented deterministic severity weight (not a probability).
3. **Finding identity and review workflow.** Analysis runs carry `IRUN-{n:06d}`; findings carry `RFND-{n:06d}` (rule) / `MFND-{n:06d}` (ML). Findings have a status lifecycle (New → Under Review → Confirmed/Dismissed) enforced server-side with 409 on invalid or unchanged transitions.
4. **Fusion implemented (§9.3).** `fusion_v1` computes CSS = 0.40·rule + 0.35·anomaly + 0.25·correlation (Phase 3 proxy: distinct supporting evidence ÷ 5) with documented bands; the payload carries formula, weights, per-component values, and the uncalibrated-heuristic note. Stored on every finding.
5. **Custody actions extended.** Automated analysis records `Automated Analysis Started` / `Automated Analysis Completed`; investigator review records `Investigator Reviewed`.
6. **API additions.** `POST /cases/{id}/analyze`, `GET /cases/{id}/analysis-runs`, `GET /cases/{id}/findings`, `GET /cases/{id}/findings/{finding_id}`, `GET /cases/{id}/findings/{finding_id}/trace`, `PATCH /cases/{id}/findings/{finding_id}`, `GET /cases/{id}/ml-metrics` (investigator notes are embedded in the finding detail response).
7. **Findings UI.** Case page gains a processing/analysis section (run button, run history, findings link); new findings list page (filters, status/kind/severity badges, CSS band) and finding detail page (reasons, components, event trace with per-event anomaly scores, review actions).
8. **Phase 4 spec refined (§11–§12).** Correlation is specified as five explicit types (`CORR-001`…`CORR-005`) inside `CORRELATION_WINDOW_SECONDS` (300) with additive confidence weights (host/user +0.30, time +0.25, IP +0.15), deduplicated activity groups, a significance-annotated timeline (`NORMAL`/`NOTABLE`/`SUSPICIOUS`), and a capped evidence graph (200 nodes / 500 edges, table fallback).

## 24. Changelog — v1.4 → v1.5 additions (Phase 4)

1. **Correlation engine implemented (§11).** `engines/correlation` evaluates every dated event pair inside `CORRELATION_WINDOW_SECONDS` (300) and produces reason-tagged links of type `CORR-001`…`CORR-005`, with most-specific-first precedence (`CORR-004` > `CORR-005` > `CORR-002` > `CORR-003` > `CORR-001`) so each pair carries exactly one type. Confidence is the explicit additive weight (time +0.25, host +0.30, user +0.30, source IP +0.15, cap 1.0) banded LOW/MEDIUM/HIGH (≥0.65 / ≥0.85) — an uncalibrated weight, never a probability. Caps: `CORRELATION_MAX_LINKS` 5000.
2. **Activity groups.** Union-find over the links (≥ 2 member events) into `investigation_groups` (`GRP-{n:06d}`) with kind (authentication/process/file/network/external), title, severity, time span, member events, and a human explanation; capped at `MAX_GROUPS_PER_RUN` (50) and `MAX_GROUP_MEMBERS` (200). No inferred or merged entities — only real events of the case.
3. **Runs and identity.** Correlation runs are append-only (`CORR-{n:06d}`), newest-first history with per-run stats; links `COR-{n:06d}`. Correlation records **no custody actions** (the custody action vocabulary is unchanged; extending it would violate the existing CHECK constraints for no benefit).
4. **Timeline implemented (§12, partial).** `engines/timeline` builds the union of rule-triggering events, ML/anomalous events, and correlation members plus ±`TIMELINE_CONTEXT_MINUTES` (2) of context, ordered by real recorded timestamps, each entry carrying significance (`SUSPICIOUS` from rule hits, `NOTABLE` from ML/anomalous, `NORMAL` context), reasons, finding IDs, and correlation IDs; capped at `TIMELINE_MAX_ENTRIES` (500) with an explanatory note. *Deferred:* heuristic phase segmentation (Initial Access / Execution / …) and raw-record IDs embedded per entry — the finding trace and event detail pages already reach the original row.
5. **Evidence graph implemented (§5/§15).** `engines/graph` layers evidence → findings → events with `contains` / `triggered` / `correlated` edges, capped at 200 nodes / 500 edges, and always returns a `table_rows` fallback so the graph is readable without the canvas. The UI renders it with React Flow (MIT) and shows the table underneath.
6. **API additions.** `POST /cases/{id}/correlate`, `GET /cases/{id}/correlation-runs`, `GET /cases/{id}/correlations`, `GET /correlations/{id}`, `GET /cases/{id}/groups`, `GET /groups/{id}`, `GET /cases/{id}/timeline`, `GET /cases/{id}/graph` (§15). Error envelope codes: `NO_NORMALIZED_EVENTS` (400), `CORRELATION_RUN_NOT_FOUND` / `CORRELATION_NOT_FOUND` / `GROUP_NOT_FOUND` (404), `UNKNOWN_CORRELATION_TYPE` / `UNKNOWN_GROUP_KIND` (422).
7. **Investigation UI.** New `InvestigationPage` (`/cases/{id}/investigation`): correlation run + history with stats chips, correlation list with type/run filters and row-level detail (reason, shared entities, both events with raw record + evidence SHA-256), activity groups with kind filter and member detail, timeline with significance filter, React Flow graph with table fallback and caps display. Case page gains a *Cross-source correlation* section (open investigation, run button, run history).
8. **Fusion note.** The fusion CorrelationComponent still uses the Phase 3 proxy (distinct supporting evidence ÷ 5) — real correlation links power the correlation, timeline, and graph surfaces; rewiring `fusion_v1` to consume stored links is explicitly deferred (the formula is versioned and changing it would alter Phase 3 finding scores). §9.3 updated to say so.
9. **Dependencies.** Frontend adds `reactflow` 11 (MIT, evidence graph). Legacy empty Phase 4 tables in existing databases are healed at startup by a minimal schema guard (`db.py`).

## 25. Changelog — v1.5 → v1.6 additions (Phase 4.5 core acceptance gate)

1. **Reprocessing pinned by history (defect fixed).** Re-processing evidence after a correlation run failed with `FOREIGN KEY constraint failed` on `forensic_events` (recorded as a `PROCESSING_FAILED` run plus a traceback in the server log) because `correlations.event_a_id/b_id` reference those rows; stored findings and activity groups additionally pin event UIDs. `processing_service._history_pins_events` now checks correlation links (hard FK) and finding/group event references (soft) *before* rebuilding: pinned evidence keeps its rows, the run completes normally with an explanatory `rebuild skipped: ...` warning, and append-only history is never rewritten. Unpinned reprocessing behaves exactly as before (replaces derived rows, keeps run history — `test_reprocessing_replaces_derived_rows_and_keeps_run_history`).
2. **Core gate executed.** Fresh-temp-database gate covering §4–§11, §13, §14, §16: all 35 API routes exercised, raw hashes pre == recorded == post, finding/timeline/graph traceability chains verified, two identical pipelines compared event-for-event, error/empty envelopes verified (400 `NO_NORMALIZED_EVENTS`, 409 transitions, 422 filters/limits, 404s), repeated operations append-only (including pinned reprocess: no `Failed` run, history still resolvable), 16 tables + `PRAGMA foreign_key_check` clean, three demo scenarios (quiet normal / compromise links / ransomware-like rules with honest ML abstention), banned-phrase harvest over 139 captured responses empty, performance timings informational (§16).
3. **UI status copy corrected.** Landing roadmap marks Phases 2–4 `done`, badge reads `PHASES 0–4 · CORE PIPELINE`, the status paragraph matches the implemented surface, and the app-shell footer says Phase 4.
4. **Finding paths corrected in docs.** Finding detail, trace, and PATCH are case-scoped (`/api/cases/{case_id}/findings/{finding_id}…`); investigator notes are embedded in the finding detail response (no standalone notes endpoint). §15 and the README API table were corrected accordingly.
5. **Known limitations carried forward.** Fusion still uses the Phase 3 proxy (§9.3, §24 item 8); timeline phase segmentation and per-entry raw-record IDs remain deferred (§24 item 4).

## 26. Changelog — v1.6 → v1.7 additions (Phase 5 — Investigation assistant)

1. **Assistant implemented (§13).** New `backend/app/assistant/` package (`intents`, `retrieval`, `context`, `answerer`, `service`) and `routers/assistant.py`. Closed 14-intent deterministic classifier (keyword + regex) with case-insensitive anchor extraction (`RFND-`/`MFND-`/`EVT-`/`COR-`/`GRP-`/`HH:MM`); every answer is rebuilt via bounded case-scoped queries that reuse the existing analysis/correlation/case/processing services — no generative model, no LLM dependency, strictly deterministic. All canonical answer wording lives in `terminology.py` (guard-safe).
2. **API additions (§15).** `POST /api/cases/{case_id}/assistant/query` (201), `GET /api/cases/{case_id}/assistant/history` (limit 1–500, default `ASSISTANT_HISTORY_LIMIT` 100), `GET /api/cases/{case_id}/assistant/queries/{query_id}`. Error codes: `FINDING_NOT_FOUND` / `ASSISTANT_QUERY_NOT_FOUND` / `CASE_NOT_FOUND` (404), `EMPTY_QUESTION` and length validation (422). Limits: question ≤ `ASSISTANT_MAX_QUESTION_LENGTH` 1000, actor ≤ 127, retrieval bounded by `ASSISTANT_TOP_N` 10.
3. **History table.** `assistant_queries` (17th table) is append-only and case-scoped; repeated questions append new rows; persisted intent/answer/evidence/basis/confidence/sources/disclaimer; history newest-first.
4. **Honesty contract.** Empty case → `ASSISTANT_EMPTY_CASE` for all intents except `CAPABILITIES`/`UNKNOWN`; `UNKNOWN` → `ASSISTANT_UNSUPPORTED` even on an empty case; ML explanation plainly states the score is statistical deviation, not proof; every evidence-backed answer carries the standing footer ("Answers are constructed only from processed case evidence. No generative model is enabled."); SHA-256 status implies nothing about authenticity/admissibility.
5. **Cross-case isolation (mandatory).** Every query is resolved exclusively against the queried case; asking about another case's finding returns 404 `FINDING_NOT_FOUND` (verified per-intent in tests and in the Phase 5 gate).
6. **UI.** New `AssistantPage` at `/cases/{case_id}/assistant` (answer panel with evidence/basis/confidence/disclaimer, clickable source chips, suggested questions, append-only history table), App route, and a *Ask assistant →* entry button on the case page. `types/models.ts` + `api/assistant.ts` added; terminology mirror extended.
7. **Tests + gate.** `backend/tests/test_assistant.py` — 24 new tests (backend suite now 230 passed); fresh-temp-database `gate_phase5.py` run — 119 checks passing end-to-end (schema bounds, empty case, capabilities, unsupported, every data intent over a real pipeline, missing finding 404, cross-case isolation over three question families, append-only case-scoped history, repeatability/determinism).

## 27. Changelog — v1.7 → v1.8 additions (Phase 6 — Investigation report layer)

1. **Report layer implemented (§13.1).** New `services/report_service.py` + `routers/reports.py` + `InvestigationReport` model. `POST /api/cases/{case_id}/reports` builds 15 fixed-order, deterministic sections **read-only** from persisted evidence/processing/analysis/correlation/custody data, stores the JSON snapshot, records `Report Generated` custody, and assigns `RPT-{n:06d}` from a global sequence. Generation never mutates pipeline tables.
2. **API additions (§15).** `POST /api/cases/{case_id}/reports` (201, `{title? ≤255, actor? ≤127}`), `GET /api/cases/{case_id}/reports` (newest-first summaries), `GET /api/cases/{case_id}/reports/{report_id}` and `.../json` (404 `REPORT_NOT_FOUND` across cases). Preview endpoint intentionally omitted — the detail view plus the browser print route covers it.
3. **Determinism + immutability contract.** Sections exclude `report_id`/`generated_at`/`title`/`generated_by` so identical DB states produce byte-identical sections (asserted incl. two generations with different title/actor). Stored snapshots are served unchanged by `/json`; later generations read current state and never rewrite earlier snapshots. Caps are module constants (`_REPORT_MAX_*`) surfaced as notes when hit.
4. **Integrity + honesty wording.** Report integrity section resolves the latest `IntegrityCheck` per evidence (checked-at desc, id desc) into VERIFIED / MISMATCH / NOT VERIFIED / NO CHECK AVAILABLE; conclusion section picks no-analysis / insufficient / no-findings / with- or no-correlation (+ high-severity note). ML statements repeat the statistical-deviation disclaimer, abstention is reported honestly, demo cases carry the `SYNTHETIC / DEMONSTRATION DATA` marker, and a guard asserts no authenticity/admissibility/probability claims in any captured report body.
5. **UI.** `ReportListPage` (`/cases/{case_id}/reports`) and `ReportDetailPage` (`/cases/{case_id}/reports/{report_id}`) with a generic section renderer (field blocks, key/value grids, object-row tables, truncated hashes), a case-page *Investigation reports* section, and a **Print report** button backed by a dedicated `@media print` stylesheet (`#root` forced white, `.print-hide` chrome removed, `break-inside: avoid`). No `dangerouslySetInnerHTML` and no new frontend dependencies.
6. **Tests + gate.** `backend/tests/test_reports.py` — 23 new tests (backend suite now **253 passed**); fresh-temp-database `gate_phase6.py` run — **104 checks** passing (empty-case contract, evidence-backed content, determinism + snapshot immutability, scoping/404/caps, read-only generation, custody + global sequence, corruption → `INTEGRITY MISMATCH`, synthetic marker, wording bans). `npm run build` green, `test_terminology` green, docs at v1.8.
