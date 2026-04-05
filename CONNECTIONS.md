# RESTer — Connections Map

> Keep this file up to date as files are added, renamed, or rewired.

---

## Overview

RESTer is a two-part Revit toolbar profile system built on PyRevit.

| Component | Role | Runs |
|-----------|------|------|
| **TabCreator** (`profile_manager.html`) | Admin builds/edits toolbar profiles | Inside Revit (pywebview via PyRevit button) |
| **ProfileSelector** (`profile_loader.html`) | End user loads a profile and toggles add-ins | Outside Revit (standalone pywebview via `.bat` / `.exe`) |
| **startup.py** | Reads active profile and builds the Revit ribbon tab | On every Revit launch (PyRevit startup hook) |

---

## Install Path

```
%APPDATA%\pyRevit\Extensions\RESTer\
```

The repo `RESTer/` folder IS the install folder — user copies it directly into Extensions.

---

## Repository Structure (current)

```
RESTer/                         ← repo root & install root
├── CONNECTIONS.md              ← this file
├── spec/
│   ├── HANDOFF.md              ← full build spec (authoritative for backend)
│   └── addin_lookup.json       ← canonical addin lookup (also in both HTML files)
└── UI/
    ├── profile_manager.html    ← TabCreator UI (complete, wired to pywebview)
    └── profile_loader.html     ← ProfileSelector UI (complete, wired to pywebview)
```

## Target Structure (what we're building toward)

```
RESTer/
├── extension.json              ← PyRevit extension manifest
├── startup.py                  ← PyRevit startup hook — builds ribbon tab
├── launch_profile_loader.bat   ← Standalone launcher for ProfileSelector
│
├── RESTer.tab/
│   └── Admin.panel/
│       └── TabCreator.pushbutton/
│           ├── script.py       ← Opens profile_manager.html in pywebview inside Revit
│           └── icon.png        ← Button icon for the Admin ribbon
│
├── app/
│   ├── profile_selector.py     ← Standalone pywebview launcher for ProfileSelector
│   ├── addin_scanner.py        ← Addin presence check, suppression, restore
│   ├── active_profile.json     ← Written by ProfileSelector, read by startup.py
│   └── profiles/               ← Profile JSON files (source of truth)
│       └── (*.json)
│
├── icons/                      ← Custom tool icons (user-supplied PNGs, named {toolName}.png)
│   └── (*.png)
│
├── ui/
│   ├── profile_manager.html    ← TabCreator UI
│   └── profile_loader.html     ← ProfileSelector UI
│
├── lookup/
│   └── addin_lookup.json       ← Canonical addin-to-file mapping
│
└── spec/
    └── HANDOFF.md              ← Build spec
```

---

## File Connections

### UI → Python Backend (pywebview JS bridge)

**profile_manager.html** calls these Python methods via `window.pywebview.api.*`:

| JS Call | Python Class | Method | Purpose |
|---------|-------------|--------|---------|
| `get_revit_version()` | `TabCreatorAPI` | `get_revit_version()` | Read active Revit version |
| `get_installed_commands()` | `TabCreatorAPI` | `get_installed_commands()` | Walk Revit ribbon via AdWindows.dll |
| `save_export(json_str)` | `TabCreatorAPI` | `save_export(json_str)` | Save to `app/profiles/` + Desktop copy |
| `pick_icon(tool_name)` | `TabCreatorAPI` | `pick_icon(tool_name)` | File dialog → copy PNG to `icons/{toolName}.png` |
| `load_profile_into_editor(name)` | `TabCreatorAPI` | `load_profile_into_editor(name)` | Read profile from `app/profiles/` |
| `get_profiles()` | `TabCreatorAPI` | `get_profiles()` | List available profiles for dropdown |
| `open_profiles_folder()` | `TabCreatorAPI` | `open_profiles_folder()` | Open `app/profiles/` in Explorer |

**profile_loader.html** calls these Python methods via `window.pywebview.api.*`:

| JS Call | Python Class | Method | Purpose |
|---------|-------------|--------|---------|
| `get_profiles()` | `ProfileSelectorAPI` | `get_profiles()` | Read all profiles from `app/profiles/` |
| `get_active_profile()` | `ProfileSelectorAPI` | `get_active_profile()` | Read `app/active_profile.json` |
| `get_revit_versions()` | `ProfileSelectorAPI` | `get_revit_versions()` | Scan `%APPDATA%\Autodesk\Revit\Addins\` for year dirs |
| `is_revit_running()` | `ProfileSelectorAPI` | `is_revit_running()` | Check for `Revit.exe` process (once at launch) |
| `add_profile()` | `ProfileSelectorAPI` | `add_profile()` | File dialog → validate → copy to `app/profiles/` |
| `load_profile(name, disable)` | `ProfileSelectorAPI` | `load_profile(name, disable)` | Write `active_profile.json`, apply hideRules |
| `remove_profile(name)` | `ProfileSelectorAPI` | `remove_profile(name)` | Delete from `app/profiles/` |
| `restore_addins(version)` | `ProfileSelectorAPI` | `restore_addins(version)` | Rename `.addin.inactive` → `.addin` |

### Python → External Systems

| Python File | Reads | Writes | External |
|-------------|-------|--------|----------|
| `startup.py` | `app/active_profile.json`, `app/profiles/*.json`, `icons/*.png` | `app/active_profile.json` (last_built) | Revit API (ribbon creation) |
| `script.py` | — | — | pywebview (launches profile_manager.html) |
| `profile_selector.py` | — | — | pywebview (launches profile_loader.html) |
| `addin_scanner.py` | `lookup/addin_lookup.json`, `%APPDATA%\Autodesk\Revit\Addins\{ver}\` | `.addin` ↔ `.addin.inactive` renames | Filesystem |

### Data Flow

```
TabCreator (admin)                    ProfileSelector (user)
      │                                      │
      │ save_export()                        │ add_profile()
      ▼                                      ▼
  app/profiles/*.json  ◄───�� file sent ────  (user's Desktop)
      │                                      │
      │                                      │ load_profile()
      │                                      ▼
      │                               active_profile.json
      │                                      │
      │                               addin_scanner.py
      │                                      │
      │                               .addin ↔ .addin.inactive
      │                                      
      └──────────► startup.py ──────► Revit ribbon tab
                   (on Revit launch)
```

---

## Protected Add-ins

**pyRevit** (`pyRevit.addin`) is always protected. The backend must never disable, hide, or rename it. Enforced in:
- `apply_hide_rules()` — skips `pyRevit`
- `disable_non_required_addins()` — always keeps `pyRevit.addin`
- `restore_all_addins()` — skips `pyRevit.addin.inactive`

---

## Key Decisions

| Decision | Detail |
|----------|--------|
| Install method | Copy `RESTer/` into `%APPDATA%\pyRevit\Extensions\` |
| Profile re-export | Overwrites existing file (matched by profile name) |
| Icon naming | `{toolName}.png`, appends `(1)` on collision |
| Revit check | Once at ProfileSelector launch, not polled |
| Cache | `startup.py` compares file mtime vs `last_built` — skips rebuild if unchanged |
| Launcher | `.bat` for alpha, `.exe` via PyInstaller for release |
| Protected addins | pyRevit only |

---

## Build Status

| File | Status |
|------|--------|
| `profile_manager.html` | Done — wired to pywebview |
| `profile_loader.html` | Done — wired to pywebview |
| `spec/HANDOFF.md` | Done — updated for build phase |
| `spec/addin_lookup.json` | Done |
| `extension.json` | Not started |
| `startup.py` | Not started |
| `script.py` | Not started |
| `profile_selector.py` | Not started |
| `addin_scanner.py` | Not started |
| `launch_profile_loader.bat` | Not started |
| `icons/` (default icon) | Not started |
