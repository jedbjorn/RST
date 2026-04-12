# Native Migration Roadmap

> **HISTORICAL — SUPERSEDED.** This document pre-dates the current Windows-track specs and is retained as a reference point. For the authoritative architecture, component split, data plane, and phased plan, see `RST_win/spec/`:
> - `architecture.md` (three-component architecture: RSTPro platform / RST add-in / RSTSnap tray app / silent add-in)
> - `silent_addin_capture.md`, `rstsnap_services.md`, `rst_scope.md`
> - `ui_style_guide.md`, `migration_phases.md`, `schema.md`
>
> Do not treat this document as current. Its Data Architecture section (tenant_id + RLS + Supabase/Neon) contradicts the locked per-firm on-prem Postgres decision captured in `schema.md`. Component naming and phasing have also evolved.

## Goal

Migrate RST_Pro from pyRevit/IronPython/CPython/pywebview to a native C# Revit plugin. Eliminate the pyRevit dependency. Build a plugin loader architecture that supports RST as the first tool in a multi-tool suite. Add a services layer for data capture with controlled timing. Ship a faster UX with dropdown profile switching.

See `data_capture_roadmap.md` for service schemas and data capture details.

---

## Current Stack (what we're replacing)

| Layer | Current | Why it goes |
|-------|---------|-------------|
| Extension loading | pyRevit Extension Manager | Dependency on pyRevit install |
| Ribbon/buttons | pyRevit folder convention (`.tab/`, `.panel/`, `.pushbutton/`) | Rigid structure, no runtime control |
| Startup logic | IronPython `startup.py` (~800 lines) | IronPython is slow, limited API access |
| Pushbutton scripts | IronPython scripts scan Revit API, write temp JSON | Two-process handoff is fragile |
| UI backend | CPython 3.12 + pywebview | Separate process, slow startup |
| UI frontend | HTML/CSS/JS (`profile_manager.html`, `profile_loader.html`) | Depends on pywebview |
| Scanners | Python modules writing to `data/` | Need to become managed services with timing control |

---

## Target Architecture

```
RSTPro.Loader.addin                      .addin manifest (installed to Addins dir)
|
+-- RSTPro.Loader.dll                    IExternalApplication
|   +-- discovers + loads tool DLLs
|   +-- creates ribbon tab per tool
|   +-- registers Revit event hooks
|   +-- starts in-process service manager
|
+-- RSTPro.Core.dll                      shared library (all tools depend on this)
|   +-- data models: Profile, UserConfig, AddinEntry, ScanPayload
|   +-- JSON I/O, path constants, normalize/match utilities
|   +-- service manager: timing, start/stop, health check
|   +-- identity builder (same fields as current rst_lib.build_identity)
|   +-- Azure client (future: push scan data to SaaS)
|
+-- RSTPro.Services.dll                  data capture services
|   +-- SystemScanService       registry scan (HKLM + HKCU)
|   +-- HealthScanService       RAM/CPU/GPU/disk/network/OS/Revit
|   +-- AddinScanService        addin inventory + origin classification
|   +-- SessionService          Revit open/close, session duration
|   +-- ModelService            model open/close, open time, file size
|   +-- SyncService             sync to central timing + outcome
|   +-- WarningsService         warning count snapshots
|
+-- RSTPro.RST.dll                       the profiler tool
|   +-- RibbonBuilder           builds custom tab from active profile
|   +-- ProfileSwitcher         dropdown combo on ribbon, instant switch
|   +-- ProfileManager          admin UI (WPF or WebView2 wrapping existing HTML)
|   +-- AddinDisabler           rename logic, intent log, crash recovery
|   +-- RSTify                  tab hide/show toggle
|
+-- RSTPro.Agent.exe                     out-of-Revit scanner (runs via Task Scheduler)
|   +-- SystemScanService only
|   +-- writes data/system_scan.json
|   +-- triggered every 24h or on user logon
|
+-- RSTPro.Tools.dll                     future tools (Project Health, etc.)
```

---

## Service Hosting

Two hosts, each with different timing:

### Out-of-Revit (RSTPro.Agent.exe)

Lightweight console app. Runs via Windows Task Scheduler.

| Service | Trigger | Output |
|---------|---------|--------|
| SystemScanService | Every 24h + on user logon | `data/system_scan.json` |

### In-Revit (RSTPro.Loader.dll)

Services start in the Revit process. Revit API events drive timing.

| Revit Event | Service | Data Captured |
|-------------|---------|---------------|
| `OnStartup` | HealthScanService | Hardware/OS snapshot |
| `OnStartup` | AddinScanService | Add-in inventory, origin classification |
| `DocumentOpened` | ModelService | Model path, open timestamp, file size, open duration |
| `DocumentSynchronizedWithCentral` | SyncService | Sync duration, file size, outcome |
| `Idling` (throttled) | WarningsService | Warning count delta |
| `DocumentClosing` | ModelService | Model session duration |
| `OnShutdown` | SessionService | Revit close timestamp, total session duration |

Revit open time: measure from `OnStartup` to first `Idling` event (or `ApplicationInitialized` if available in target Revit version).

Model open time: measure from `DocumentOpening` to `DocumentOpened`.

---

## Profile Dropdown (key UX change)

Replace the full ProfileLoader pywebview UI with a ribbon dropdown for the 90% use case:

```
[v Architecture_2025  ] [reload] [gear]
   |-- Architecture_2025   check
   |-- Structure_2025
   |-- MEP_Coordination
   |-- ---
   +-- Manage Profiles...
```

- **Dropdown** (`RibbonComboBox` or custom `RibbonSplitButton`) lists all profiles
- **Select** writes `active_profile.json`, rebuilds ribbon in-process — sub-second
- **Reload button** forces ribbon rebuild
- **Gear button** opens full ProfileManager UI for admin tasks
- **"Manage Profiles..."** opens ProfileManager

The disable flow still needs a confirmation dialog (WPF) showing what stays active vs gets disabled. But for switching between profiles without disable toggled, the dropdown is instant — no window, no process spawn.

---

## UI Strategy

| UI | Approach | Rationale |
|----|----------|-----------|
| ProfileSwitcher | Pure ribbon control (no window) | Speed — most common user action |
| Disable confirmation | Small WPF dialog | Simple enough for native, needs to feel fast |
| ProfileManager (admin) | Native WPF (component-based) | Full rewrite — componentized architecture replaces 3,800-line HTML monolith |
| RSTify toggle | Ribbon button (no window) | Same as current — just a toggle |
| Service status / settings | WPF settings panel (future) | Admin needs visibility into service health |

---

## WPF Component Architecture

The current `profile_manager.html` is ~3,800 lines (CSS + HTML + JS in one file) and `profile_loader.html` is ~1,500 lines. In the WPF rewrite, these become focused UserControl + ViewModel pairs:

### ProfileManager (replaces profile_manager.html)

| Component | Responsibility | Estimated size |
|-----------|---------------|----------------|
| `ToolDetectionService` | Ribbon scan, command discovery, tool list state | ~200 lines |
| `PanelEditorControl` | Panel creation, color picker, slot management, drag/drop reorder | ~300 lines |
| `StackEditorControl` | Stack builder (2-3 tools per stack) | ~150 lines |
| `IconPickerControl` | Icon grid with search, selection, clear | ~150 lines |
| `ProfileSwitcherControl` | Profile dropdown, load/save/new, name editing | ~150 lines |
| `TabPreviewControl` | Live ribbon preview rendering | ~200 lines |
| `UrlToolDialog` | Add/edit URL and mailto tools, auto-detect email | ~100 lines |
| `ExportService` | JSON build, file write, desktop copy, active profile warning | ~150 lines |
| `AddinProtectionControl` | Set Protection panel (locked/protected toggles) | ~150 lines |
| `ProfileManagerViewModel` | Central state, commands, coordination between controls | ~300 lines |

### ProfileLoader (replaces profile_loader.html)

Most of the loader is replaced by the ribbon dropdown (Phase 1). What remains:

| Component | Responsibility | Estimated size |
|-----------|---------------|----------------|
| `DisableConfirmDialog` | Three-column preview (staying/disabling/skipped) | ~150 lines |
| `RSTifyToggleControl` | Tab visibility toggles with source-tab locking | ~100 lines |
| `AddinStatusCards` | Required add-in status display (Native/Loaded/Not Found) | ~100 lines |

### Design Principles

- **MVVM** — ViewModels own state, Views bind to it. No code-behind logic.
- **One responsibility per control** — each UserControl handles one feature area
- **Shared styles** — `RST.Styles.xaml` ResourceDictionary replaces `rst_components.css`
- **No monoliths** — if a control exceeds ~300 lines, split it

The current HTML files serve as the reference implementation. Read them to understand behavior, but don't try to port the structure — WPF's data binding and command model will naturally reorganize the logic.

---

## What Ports Directly

These are logic-only modules with no Revit API or UI dependencies. Straight C# port:

| Python module | C# equivalent | Notes |
|---------------|---------------|-------|
| `rst_lib.py` (paths, normalize, match) | `RSTPro.Core.Utilities` | All pure functions |
| `rst_lib.py` (profile helpers) | `RSTPro.Core.Profiles` | JSON read/write |
| `addin_scanner.py` (classify, parse XML) | `RSTPro.Core.Addins` | C# XML is cleaner than Python ET |
| `user_config.py` (build, append, intent) | `RSTPro.Core.UserConfig` | Same JSON structure |
| `system_scanner.py` | `RSTPro.Services.SystemScan` | `Microsoft.Win32.Registry` is native |
| `health_scanner.py` | `RSTPro.Services.HealthScan` | `System.Management` for WMI, no PowerShell needed |
| `addin_lookup.json`, `config.json` | Unchanged | Same files, same format |
| All profile JSONs | Unchanged | Same files, same format |
| All user config JSONs | Unchanged | Same files, same format |

---

## What's a Full Rewrite

| Component | Effort | Notes |
|-----------|--------|-------|
| `startup.py` ribbon builder | High | AdWindows panel coloring, DrawingBrush, PostCommand routing — same approach in C# but full rewrite |
| `profile_manager.html` | High (WPF) | Full rewrite as componentized WPF — see WPF Component Architecture below |
| `profile_loader.html` | Medium | Mostly replaced by dropdown; disable confirmation is a small WPF dialog |
| `reload_ui.py` WPF window | Low | Already WPF (IronPython), trivial port to C# |
| `RSTify` tab hiding | Low | Same AdWindows API, just C# |
| Update mechanism | Medium | Replace git zip download with MSI auto-update (Squirrel, WinGet, or custom) |

---

## Migration Phases

### Phase 1: Loader + Core + Dropdown

Build the foundation. Proves the plugin loader pattern works.

- [ ] `RSTPro.Loader.dll` — `.addin` manifest, `IExternalApplication`, ribbon tab creation
- [ ] `RSTPro.Core.dll` — path constants, JSON I/O, profile read/write, identity builder
- [ ] Profile dropdown on ribbon — list profiles, switch active, rebuild ribbon
- [ ] Port `startup.py` ribbon builder to C# `RibbonBuilder`
- [ ] Port RSTify tab hide/show

**Exit criteria:** User can install via .addin drop, see RST ribbon tab with dropdown, switch profiles, and see the custom ribbon rebuild. No pyRevit dependency.

### Phase 2: Services

Port the three existing scanners and add session tracking.

- [ ] `RSTPro.Services.dll` — service manager with timing control
- [ ] Port SystemScanService (registry scan, HKLM + HKCU)
- [ ] Port HealthScanService (hardware/OS/Revit build snapshot)
- [ ] Port AddinScanService (inventory + origin classification)
- [ ] `RSTPro.Agent.exe` — out-of-Revit scanner, Task Scheduler integration
- [ ] Add SessionService (Revit open/close, session duration)
- [ ] Add ModelService (DocumentOpened/Closing, open time)
- [ ] Add SyncService (DocumentSynchronizedWithCentral)
- [ ] Add WarningsService (Idling-throttled warning count)

**Design constraint:** Services must produce data shaped for the target DB schema even though the DB doesn't exist yet. Each service writes to local JSON now, but the payloads must match the planned table structures so connecting the API later is wiring, not redesign. See Data Architecture below.

**Exit criteria:** All current data files still produced. New session/model/sync/warning events captured. Agent runs on schedule outside Revit. Every service payload is schema-aligned.

### Phase 3: Disable Flow + Admin UI

Port the add-in management and admin profile editor.

- [ ] Port AddinDisabler — rename logic, intent log, crash recovery
- [ ] WPF disable confirmation dialog (replaces profile_loader.html overlay)
- [ ] Port user config build/append/rescan logic
- [ ] Native WPF ProfileManager — componentized rewrite (see WPF Component Architecture)
- [ ] Port Set Protection panel as `AddinProtectionControl`

**Exit criteria:** Full feature parity with current RST_Pro. Admin can build profiles, users can load profiles and disable add-ins, crash recovery works. No HTML/pywebview dependency.

### Phase 4: Installer + Polish

Ship it.

- [ ] MSI or MSIX installer (writes .addin manifest + DLLs to correct location)
- [ ] Auto-update mechanism (Squirrel, WinGet, or custom check-and-replace)
- [ ] Remove pyRevit dependency from install instructions
- [ ] Performance benchmarking vs current stack
- [ ] Multi-user testing (pending ADN approval)

**Exit criteria:** Users install via MSI, updates are automatic, pyRevit is optional (not required).

---

## Data Architecture

The DB doesn't exist yet. Services should be built so that when the backend is ready, it's just connecting a pipe — not reshaping data. Every service writes local JSON today, but the payload structure must match the planned schema.

### Multi-tenancy

Option A (tenant column + Postgres Row Level Security). One database, shared tables, `tenant_id` on every row. RLS enforces isolation at the database level — even buggy queries can't leak across tenants.

### Target schema (Postgres)

```
tenants
  tenant_id (PK), company_name, api_key, created_at

devices
  device_id (PK), tenant_id (FK), hostname, os_version, cpu, ram_gb, gpu,
  disk_total_gb, disk_free_gb, display_info, first_seen, last_seen

device_software
  device_id (FK), tenant_id (FK), software_name, version, publisher,
  install_date, source, scanned_at
  PK: (device_id, software_name)

revit_sessions
  session_id (PK), device_id (FK), tenant_id (FK), revit_version,
  revit_build, revit_username, started_at, ended_at, duration_sec,
  startup_sec, addin_count, journal_path, journal_size_kb

session_addins
  session_id (FK), tenant_id (FK), addin_name, addin_file, assembly_path, origin
  PK: (session_id, addin_name)

model_sessions
  model_session_id (PK), session_id (FK), tenant_id (FK), model_name,
  model_path, is_workshared, file_size_mb, opened_at, closed_at,
  open_duration_sec, warning_count_open, warning_count_close

sync_events
  sync_id (PK), model_session_id (FK), tenant_id (FK), synced_at,
  duration_sec, file_size_mb, success, warning_count
```

### Data hierarchy

```
Tenant (1)
  └── Device (many per tenant, changes slowly)
       └── Revit Session (many per device, one per launch)
            ├── Session Addins (snapshot of loaded add-ins)
            └── Model Session (many per Revit session)
                 └── Sync Events (many per model session)
```

### Transport (future)

```
Revit Plugin → REST API → Postgres
                              ↑
                    Dashboard UI ──┘
```

Plugin auth: API key per tenant (headless, write-only).
Dashboard auth: Email + password or SSO (read-only, user-facing).

Planned API endpoints:

```
POST /api/v1/device/heartbeat     → upserts devices + device_software
POST /api/v1/session/start        → inserts revit_sessions + session_addins
POST /api/v1/session/end          → updates revit_sessions (ended_at, duration)
POST /api/v1/model/open           → inserts model_sessions
POST /api/v1/model/close          → updates model_sessions (closed_at, warnings)
POST /api/v1/model/sync           → inserts sync_events
```

Plugin queues payloads locally and flushes in batches. Retries on network failure. No data lost.

### Decisions to make before backend build

| Decision | Options | Notes |
|----------|---------|-------|
| Postgres hosting | Supabase, Neon, Railway, Azure | Managed preferred. Supabase gives Postgres + auth + RLS out of the box |
| API hosting | Serverless (Azure Functions) vs always-on (App Service) | Serverless is cheaper at low scale |
| Dashboard frontend | React/Next.js, or TBD | Separate decision from plugin work |
| Dashboard user | BIM manager? IT admin? Firm owner? | Shapes which data surfaces first |
| PII handling | Hash hostnames/usernames? Or internal-only? | Compliance question — depends on customer expectations |
| Data retention | Keep raw data forever? Aggregate after 90 days? | Cost vs query flexibility |
| device_id generation | Hardware hash vs UUID stored locally | Hardware hash is stable across reinstalls; UUID is simpler |

### Design rule for services

Each service must:
1. Produce a payload that maps 1:1 to the target table columns
2. Include a `device_id` field (generated on first run, stored locally)
3. Write to local JSON today (same path as current scanners)
4. Be swappable to HTTP POST later without changing the payload shape

---

## Dependencies & Blockers

| Dependency | Status | Impact |
|------------|--------|--------|
| ADN approval | Pending | Blocks multi-user Revit testing |
| Brand name | Resolved | RSTPro platform, RST add-in, RSTSnap tray app (see current architecture.md §1) |
| Backend infrastructure (Postgres + API + dashboard) | Not started | Phase 2 services write local JSON. API connection is Phase 5 work — no blocker for plugin development |
| ~~WebView2 runtime~~ | ~~Ships with Win11, NuGet for Win10~~ | No longer needed — full WPF rewrite, no HTML wrapping |
| Revit API version targeting | 2024+ | Same as current; `LoadedApplications` API path already handled |

---

## Dev Environment

| Tool | Purpose |
|------|---------|
| Visual Studio 2022 | C# development, WPF designer |
| Revit 2024/2025 SDK | API references, AdWindows DLLs |
| NuGet | Newtonsoft.Json, WiX (installer) |
| Git | Same repo, `RST_win/` directory |

Code lives in `RST_win/` alongside the existing `RST_python/` until migration is complete and validated. Both stacks can coexist during development — the .addin manifests point to different DLLs.
