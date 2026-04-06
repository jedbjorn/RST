# RST — Connections Map

> Keep this file up to date as files are added, renamed, or rewired.

---

## Overview

RST is a two-part Revit toolbar profile system built on PyRevit.

| Component | Role | Runs |
|-----------|------|------|
| **TabCreator** (`profile_manager.html`) | Admin builds/edits toolbar profiles | Inside Revit (pywebview via PyRevit button) |
| **ProfileSelector** (`profile_loader.html`) | End user loads a profile and toggles add-ins | Outside Revit (standalone pywebview via `.bat` / `.exe`) |
| **startup.py** | Reads active profile and builds the Revit ribbon tab | On every Revit launch (PyRevit startup hook) |

---

## Logging

All backend activity is logged to `rester.log` at the extension root. Shared logger via `app/logger.py` — modules call `get_logger('module_name')`. Log includes timestamps, severity, module, and message.

---

## Install Path

```
%APPDATA%\pyRevit\Extensions\RESTer.extension\
```

Install via pyRevit Extension Manager using the GitHub repo URL. pyRevit clones the repo and appends `.extension` to the folder name automatically.

---

## Repository Structure

```
RESTer/                                     ← repo root & install root
├── .gitignore
├── CONNECTIONS.md                          ← this file
├── extension.json                          ← PyRevit extension manifest
├── startup.py                              ← PyRevit startup hook — builds ribbon tab
├── launch_profile_loader.bat               ← Standalone launcher for ProfileSelector
│
├── RESTer.tab/
│   └── Admin.panel/
│       └── TabCreator.pushbutton/
│           ├── script.py                   ← Opens profile_manager.html in pywebview inside Revit
│           └── icon.png                    ← Button icon for the Admin ribbon (32x32)
│
├── app/
│   ├── logger.py                           ← Shared logger → rester.log
│   ├── profile_selector.py                 ← Standalone pywebview launcher + ProfileSelectorAPI
│   ├── addin_scanner.py                    ← Addin presence check, suppression, restore
│   ├── active_profile.json                 ← Written by ProfileSelector, read by startup.py
│   └── profiles/                           ← Profile JSON files (source of truth)
│       └── (*.json)
│
├── icons/                                  ← Custom tool icons ({toolName}.png)
│   └── RESTer_default.png                  ← Default icon for all ribbon buttons (256x256)
│
├── ui/
│   ├── profile_manager.html                ← TabCreator UI (wired to pywebview)
│   └── profile_loader.html                 ← ProfileSelector UI (wired to pywebview)
│
├── lookup/
│   └── addin_lookup.json                   ← Canonical addin-to-file mapping
│
└── spec/
    ├── HANDOFF.md                          ← Build spec (authoritative for backend)
    └── addin_lookup.json                   ← Canonical copy (keep in sync with lookup/)
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
| `load_profile(name, disable, version)` | `ProfileSelectorAPI` | `load_profile(name, disable, version)` | Write `active_profile.json`, apply hideRules |
| `remove_profile(name)` | `ProfileSelectorAPI` | `remove_profile(name)` | Delete from `app/profiles/` |
| `restore_addins(version)` | `ProfileSelectorAPI` | `restore_addins(version)` | Rename `.addin.inactive` → `.addin` |

### Python → External Systems

| Python File | Reads | Writes | External |
|-------------|-------|--------|----------|
| `startup.py` | `app/active_profile.json`, `app/profiles/*.json`, `icons/*.png` | `app/active_profile.json` (last_built) | Revit API (ribbon via AdWindows.dll) |
| `script.py` | `app/profiles/*.json`, `icons/` | `app/profiles/`, Desktop copy, `icons/` | pywebview (launches profile_manager.html) |
| `profile_selector.py` | `app/profiles/*.json`, `app/active_profile.json` | `app/active_profile.json`, `app/profiles/` | pywebview (launches profile_loader.html) |
| `addin_scanner.py` | `lookup/addin_lookup.json`, `%APPDATA%\...\Addins\{ver}\` | `.addin` ↔ `.addin.inactive` renames | Filesystem |
| `logger.py` | — | `rester.log` | — |

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
| Install method | Add via pyRevit Extension Manager (git URL) — pyRevit appends `.extension` automatically |
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
| `extension.json` | Done |
| `startup.py` | Done |
| `script.py` | Done |
| `profile_selector.py` | Done |
| `addin_scanner.py` | Done |
| `launch_profile_loader.bat` | Done |
| `icons/RESTer_default.png` | Done — 256x256 default icon |
| `icon.png` (pushbutton) | Done — 32x32 |
