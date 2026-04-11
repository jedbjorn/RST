# Data Capture Services Roadmap

## Overview

RST_Pro captures machine, session, and model data for IT/manager dashboards and Project Health SaaS. Three distinct services, each with their own cadence and trigger.

---

## Identity Standard

Every scan and event JSON includes a standard `identity` block built by `rst_lib.build_identity()`. This ensures consistent field names across all services.

```json
{
  "identity": {
    "windowsUsername": "jsmith",
    "revitUsername": "John Smith",
    "deviceName": "WORKSTATION-42"
  }
}
```

| Field | Description | Always present | DB role |
|---|---|---|---|
| `revitUsername` | Set in Revit Options > General > Username | No — empty if scan runs outside Revit or user never set it | **Primary key** for tying a person across devices/versions |
| `windowsUsername` | OS login (DOMAIN\user or local user) | Yes | **Fallback PK** when revitUsername is empty |
| `deviceName` | Machine hostname | Yes | **FK to devices table** — ties machine-specific data to a physical box |

**Rules:**
- Both usernames are captured on every event, always.
- `revitUsername` is the preferred person identifier. `windowsUsername` is the fallback.
- `deviceName` is the machine identifier. One person can have multiple devices.
- Non-Revit scans (standalone mode) will have `revitUsername: ""` — this is expected.

---

## Service 1: Program Scan

**What it does:** Scans Windows registry for all installed programs on the machine.

| | Current | Future |
|---|---|---|
| **Trigger** | App load | Sign-in or every 24 hours (whichever comes first) |
| **Output** | `data/system_scan.json` | DB push |

**Captures:**
- DisplayName, Publisher, DisplayVersion
- InstallLocation, InstallDate, EstimatedSize
- URLInfoAbout, HelpLink

**Revit-specific enrichment:** Filters installed programs against known add-ins, adds publisher-based native/third-party classification, feeds addin lookup for profile management.

---

## Service 2: System Health Scan

**What it does:** Captures a hardware/OS snapshot of the machine at a point in time.

| | Current | Future |
|---|---|---|
| **Trigger** | App load (background thread) | Background service, triggered by Revit opening |
| **Output** | `data/health_scan.json` | DB push |

**Captures:**
- Identity: Windows username, Revit username, device name
- RAM: total, available, used, used %
- CPU: name, physical cores, logical cores
- GPU: name, driver version, VRAM total
- Disk: C: capacity, available, used %, type (SSD/HDD), bus type
- Display: monitor count, primary resolution
- Network: adapter name, type (WiFi/Ethernet), speed
- OS: name, version, release, build
- Revit: version, build

---

## Service 3: Session Logger (future — needs schema)

**What it does:** Runs as a background service. Tracks Revit session lifecycle and model lifecycle as separate event streams.

### 3a: Revit Session Log

Triggered when Revit opens. Tracks the application-level session.

**Captures:**
- Revit open timestamp
- Revit close timestamp
- Revit open time (seconds) — time from launch to ready
- Session length (seconds)
- Revit version + build
- Windows username, Revit username, device name
- [ ] **SCHEMA TODO:** Define additional session-level fields

### 3b: Model Session Log

Triggered when a Revit model is opened. Multiple model sessions can exist within one Revit session (user opens/closes models).

**Captures:**
- Model open timestamp
- Model close timestamp
- Model open time (seconds) — time from open command to model ready
- Model session length (seconds)
- Model name
- Model file path
- Model file size (MB)
- [ ] **SCHEMA TODO:** Define model-level fields (element counts, warnings count, worksets, links, sync times, etc.)

### Architecture Notes

- The session logger needs to be a **background service/process** — not triggered by RST_Pro UI, since it must capture events even when the user doesn't open the profile selector.
- Options: Windows service, scheduled task that polls, or a lightweight pyRevit event hook (Idling, DocumentOpened, DocumentClosing, ApplicationClosing).
- pyRevit hooks are the lightest option — `startup.py` already subscribes to Idling. DocumentOpened and ApplicationClosing events could write timestamps to a log file that the background service picks up.
- Revit open time is tricky — requires measuring from process start to first Idling event or ApplicationInitialized.
- Model open time requires measuring from DocumentOpening to DocumentOpened event.

---

## Data Directory Structure

```
RST_python/
  data/                              ← all machine-generated (gitignored)
    system_scan.json                 ← Program Scan output
    health_scan.json                 ← System Health Scan output
    revit_sessions/                  ← future: Revit Session Logs
      {date}_{session_id}.json
    model_sessions/                  ← future: Model Session Logs
      {date}_{model}_{session_id}.json
  lookup/                            ← static reference data (committed)
    addin_lookup.json
    config.json
  docs/
    data_capture_roadmap.md          ← this file
```

---

## Schema Status

| Service | Schema Defined | Implemented | DB-Ready |
|---|---|---|---|
| Program Scan | Yes | Yes | No |
| System Health Scan | Yes | Yes | No |
| Revit Session Log | **TODO** | No | No |
| Model Session Log | **TODO** | No | No |

---

## Dependencies & Blockers

- **Revit open time / model open time:** Requires pyRevit event hooks (DocumentOpened, ApplicationClosing, etc.). May need IronPython-side timestamp capture passed to CPython.
- **Session length:** Requires either persistent background process or event-driven logging with start/end timestamps.
- **DB push:** Needs Azure infrastructure (part of Project Health SaaS roadmap). Schema must be finalized before DB design.
- **ADN approval:** Multi-user testing blocked pending Autodesk Developer Network approval.
