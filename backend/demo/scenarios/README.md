# SYNTHETIC / DEMONSTRATION DATA

**These files are entirely synthetic and are provided for demonstration only.**
They do not come from any real system, person, or incident. Every identity,
host, address, and URL below is fictional and reserved for documentation or
testing purposes.

## How to use

Upload each file through the FORENSIGHT AI UI (or `POST /api/cases/{case_id}/evidence`
with the matching `evidence_type`), then run **Process** on the case. The files
are stored as raw bytes and processed only as data — never executed or
interpreted as instructions.

## Identity pool (all fictional)

| Kind | Values |
| --- | --- |
| Users | `usr_alice`, `usr_bob`, `usr_dana`, `usr_charlie`, `svc_backup` |
| Hosts | `WS-01`, `WS-03`, `WS-05`, `WS-07`, `SRV-FILE01`, `SRV-WEB01`, `DC-01` |
| Internal IPs | `10.20.30.0/24` (TEST-NET-3 style documentation range: `192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24`) |
| Domains | `*.example` (RFC 2606 reserved) |

## Files

| File | `evidence_type` | Notes |
| --- | --- | --- |
| `authentication.csv` | `authentication` | 14 rows: logins/logouts across the identity pool; includes duplicate row, invalid timestamp, empty timestamp, missing required field, short row, US-format and unix-epoch timestamps |
| `file_activity.csv` | `file_activity` | 12 rows: open/write/delete/rename/copy actions; includes duplicate row, invalid timestamp, missing file path, extra-column row, `YYYY/MM/DD` timestamp |
| `process.csv` | `process` | 12 rows: process start/exit with parents and command lines; includes duplicate row, invalid timestamp, short row, unix-epoch timestamp |
| `network.csv` | `network` | 10 rows: connections to internal and documentation-range IPs; includes duplicate row, invalid timestamp, short row, `MM/DD/YYYY` timestamp |
| `browser.csv` | `browser` | 10 rows: visits/downloads/form submissions to `*.example` URLs; includes duplicate row, invalid timestamp, missing URL/domain row |
| `system_logs.json` | `system` | 11 records in an `{"events": [...]}` wrapper: ISO 8601 (`Z` and `+05:30` offsets), plain-text timestamp, nested objects, lists, `null`, booleans; includes duplicate record, broken timestamp, missing timestamp, non-object element |

## Expected processing behaviour

- Rejected (malformed) rows are **retained** and reported with row number and
  exact reason — they are never silently discarded.
- Duplicate records are **preserved and marked** in derived data with the
  event they duplicate and the reason.
- Timestamps without a timezone are assumed **UTC** and labelled accordingly
  in each event (`tz_note`); `+05:30` offsets are converted to UTC; unix
  epochs are interpreted as UTC seconds.
- A run with any rejected rows reports status **Partial**, never Completed.
