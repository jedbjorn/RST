# RESTer — Claude Code Handoff Spec

## What This Is

RESTer is a two-part system that lets a **Revit admin** build a custom toolbar profile (TabCreator) and lets **end users** load that profile outside of Revit (ProfileSelector), which then instructs PyRevit to build a custom ribbon tab automatically when Revit opens.

The two HTML UIs are complete and verified. This document specifies everything Claude Code needs to build the Python / PyRevit backend that wires them up.

---

## Platform & Install

- **Windows only.**
- Installs to `%APPDATA%\pyRevit\Extensions\RESTer\`
- pyRevit provides the Python runtime and includes pywebview.
- **pyRevit is a protected add-in.** The backend must never disable, hide, or rename `pyRevit.addin` — RESTer is built on pyRevit and cannot run without it. All functions that suppress `.addin` files (`apply_hide_rules`, `disable_non_required_addins`, `restore_all_addins`) must skip `pyRevit.addin`.

---

## System Architecture

```
ADMIN SIDE (inside Revit)                END-USER SIDE (outside Revit)
──────────────────────────               ──────────────────────────────
TabCreator HTML UI                       ProfileSelector HTML UI
  └─ pywebview window                      └─ pywebview window (standalone)
       opened by PyRevit button                 OR WPF host
  └─ Record mode hook                    └─ reads profiles/ dir at launch
       adwindows.dll ItemExecuted         └─ file picker → copy to profiles/
  └─ Export → .json file                 └─ writes active_profile.json
       shared to user (any channel)      └─ toggles .addin / .addin.inactive
                                         └─ "Load Profile" → sets active profile

REVIT STARTUP
──────────────
PyRevit startup hook
  └─ reads active_profile.json
  └─ reads the referenced profile .json
  └─ cache check: skip rebuild if profile unchanged
  └─ builds custom ribbon tab + panels + buttons
  └─ applies hideRules (suppresses add-in tabs)
```

---

## Workflows

**Admin creates & distributes a profile:**
1. Admin opens TabCreator inside Revit → builds panels, tools, stacks
2. Admin clicks "Export Config →" → profile saved to `app/profiles/` **and** a copy to Desktop
3. Admin sends the Desktop copy to end users (email, Teams, etc.)

**Admin edits an existing profile:**
1. Admin picks a profile from the dropdown in TabCreator → `load_profile_into_editor()` populates the editor
2. Admin makes changes, re-exports → overwrites in `app/profiles/`, fresh copy to Desktop

**End user loads a profile:**
1. User launches ProfileSelector (via `.bat` / `.exe`)
2. User clicks "Add Profile" → file picker → selects the JSON received from admin
3. Profile is validated and copied to `app/profiles/` (now in the dropdown)
4. User selects profile, picks Revit version from dropdown, clicks "Load Profile →"
5. If Revit is running → **blocked** with error: close Revit first
6. Profile is set as active, hideRules applied, `.addin` files toggled

---

## Repository / File Structure

```
RESTer/                                     # Copy this folder into %APPDATA%\pyRevit\Extensions\
├── extension.json                          # PyRevit extension manifest
├── startup.py                              # Runs on every Revit launch — builds tab
├── launch_profile_loader.bat               # Double-click to open ProfileSelector outside Revit
├── RESTer.tab/
│   └── Admin.panel/
│       └── TabCreator.pushbutton/
│           ├── script.py                   # Opens profile_manager.html in pywebview
│           └── icon.png
│
├── app/
│   ├── profile_selector.py                 # Standalone launcher for ProfileSelector UI
│   ├── profiles/                           # User's added profile .json files live here
│   │   └── (*.json)
│   ├── active_profile.json                 # Written by ProfileSelector on "Load Profile"
│   └── addin_scanner.py                    # .addin presence check + fuzzy fallback
│
├── icons/                                  # Custom tool icons (user-supplied PNGs)
│   └── (*.png)
│
├── ui/
│   ├── profile_manager.html                     # ✅ COMPLETE — do not modify (TabCreator UI)
│   └── profile_loader.html                 # ✅ COMPLETE — do not modify (ProfileSelector UI)
│
└── lookup/
    └── addin_lookup.json                   # Canonical ADDIN_LOOKUP as JSON (see below)
```

---

## Canonical JSON Schema

This is the exact shape TabCreator exports and ProfileSelector / PyRevit consumes. Every field is required. No optional fields.

```json
{
  "profile":        "Design_2025",
  "tab":            "Design",
  "min_version":    "2024",
  "exportDate":     "2024-03-12",
  "requiredAddins": ["DiRoots", "Naviate"],
  "hideRules":      ["Naviate"],
  "stacks": {
    "Edit Stack": {
      "tools": [
        { "name": "Move",   "commandId": "ID_MODIFY_MOVE"   },
        { "name": "Rotate", "commandId": "ID_MODIFY_ROTATE" },
        { "name": "Copy",   "commandId": "ID_MODIFY_COPY"   }
      ]
    }
  },
  "panels": [
    {
      "name":  "Modify",
      "color": "#4f8ef7",
      "slots": [
        { "type": "tool",  "name": "Align",        "icon": "↔", "commandId": "ID_MODIFY_ALIGN"         },
        { "type": "tool",  "name": "Mirror",        "icon": "⊿", "commandId": "ID_MODIFY_MIRROR_PICK", "iconFile": "Mirror.png" },
        { "type": "stack", "name": "Edit Stack"                                                          },
        { "type": "tool",  "name": "Sheet Manager", "icon": "⊞", "commandId": "CustomCtrl_%CustomCtrl_%DiRoots%SheetsManager%ShtMgr" }
      ]
    }
  ]
}
```

### Field notes

| Field | Type | Notes |
|---|---|---|
| `profile` | string | Unique name. Used as filename stem when copied: `Design_2025_2024-03-12.json` |
| `tab` | string | Revit ribbon tab name PyRevit creates |
| `min_version` | string | Bare year, e.g. `"2024"`. Compare numerically against Revit version |
| `requiredAddins` | string[] | Ribbon tab names (sourceTab convention). Resolved via ADDIN_LOOKUP |
| `hideRules` | string[] | Ribbon tab names to suppress. Mechanism: rename `.addin` → `.addin.inactive` |
| `stacks` | object | Dict keyed by stack name. Only stacks actually placed in a panel slot are exported |
| `panels[].slots[].type` | `"tool"` \| `"stack"` | Tool slots are self-contained. Stack slots reference `stacks` dict by name |
| `panels[].slots[].commandId` | string | Only present on `type:"tool"` slots. Two formats: `ID_*` (native) or `CustomCtrl_%CustomCtrl_%{Tab}%{Panel}%{Button}` (add-in) |
| `panels[].slots[].icon` | string | Unicode character used as fallback display. Not present on stack slots |
| `panels[].slots[].iconFile` | string \| null | Optional. PNG filename in `icons/` dir. When present, `startup.py` uses this for the ribbon button icon instead of the generic default |

---

## ADDIN_LOOKUP (canonical)

This table must be kept in sync across: `profile_manager.html`, `profile_loader.html`, and `lookup/addin_lookup.json`. Claude Code should read from the JSON file at runtime rather than hardcoding in Python.

```json
{
  "DiRoots":    { "displayName": "DiRoots Suite",           "file": "DiRoots.addin"              },
  "Naviate":    { "displayName": "Naviate",                  "file": "Naviate.addin"              },
  "pyRevit":    { "displayName": "pyRevit",                  "file": "pyRevit.addin"              },
  "Dynamo":     { "displayName": "Dynamo for Revit",         "file": "DynamoRevitDS.addin"        },
  "Ideate":     { "displayName": "Ideate BIMLink",           "file": "Ideate.BIMLink.addin"       },
  "Guardian":   { "displayName": "Guardian",                 "file": "Guardian.addin"             },
  "Kinship":    { "displayName": "Kinship",                  "file": "Kinship.addin"              },
  "Pirros":     { "displayName": "Pirros",                   "file": "Pirros.addin"               },
  "Avail":      { "displayName": "Avail",                    "file": "Avail.addin"                },
  "Orkestra":   { "displayName": "Orkestra",                 "file": "Orkestra.addin"             },
  "BIM One":    { "displayName": "BIM One Tools",            "file": "BIMone.addin"               },
  "COINS":      { "displayName": "COINS Auto-Section View",  "file": "COINSAutoSectionView.addin" },
  "Enscape":    { "displayName": "Enscape",                  "file": "Enscape.addin"              },
  "Twinmotion": { "displayName": "Twinmotion Direct Link",   "file": "Twinmotion.addin"           }
}
```

---

## Component Specs

### 1. `startup.py` — PyRevit startup hook

Runs automatically on every Revit launch via PyRevit's startup mechanism.

**Responsibilities:**
1. Read `app/active_profile.json` — if missing or empty, do nothing (no custom tab)
2. Load the referenced profile `.json` from `app/profiles/`
3. **Cache check:** compare the profile file's modified timestamp against a stored `last_built` timestamp in `app/active_profile.json`. If unchanged, skip rebuild and use existing tab. If changed, continue to step 4
4. Validate `min_version` against current Revit version — abort and show warning balloon if version too low
5. Build a PyRevit ribbon tab using the profile's `tab` name
6. For each panel in `panels[]`: create ribbon panel, iterate slots, create buttons
7. For `type:"tool"` slots: create a `PushButton` mapped to `commandId`. If `iconFile` is set, load the PNG from `icons/`; otherwise use the generic default icon shipped with the extension
8. For `type:"stack"` slots: look up in `stacks` dict, create a `RibbonRowPanel` with up to 3 text-only standard-sized buttons (no icons, matching native Revit stacked items)
9. Apply `hideRules` after tab is built (see addin suppression spec below)

**Ribbon button creation — commandId execution:**

PyRevit does not natively fire arbitrary Revit commandIds from ribbon buttons. The correct approach is:
```python
from Autodesk.Revit.UI import PostableCommand, RevitCommandId
# For native commands (ID_* format):
cmd_id = RevitCommandId.LookupCommandId(command_id_string)
# Then bind to a PostCommand call in the button's execute handler
```
For add-in commands (`CustomCtrl_%...` format), use:
```python
from Autodesk.Revit.UI import RevitCommandId
cmd_id = RevitCommandId.LookupPostableCommandId(PostableCommand....)
# OR use the string directly:
cmd_id = RevitCommandId.LookupCommandId("CustomCtrl_%CustomCtrl_%DiRoots%...")
```
Each button's script should simply call:
```python
__revit__.PostCommand(RevitCommandId.LookupCommandId(COMMAND_ID))
```
where `COMMAND_ID` is stored in the button's extra data / metadata at build time.

**active_profile.json shape:**
```json
{
  "profile": "Design_2025",
  "profile_file": "Design_2025_2024-03-12.json",
  "loaded_at": "2025-04-01T09:30:00",
  "last_built": "2025-04-01T09:30:00",
  "disable_non_required": false
}
```

---

### 2. `script.py` — TabCreator PyRevit button

Opens profile_manager.html in a pywebview window inside Revit.

```python
import pywebview
import os

HTML_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'ui', 'profile_manager.html')

def IExternalCommand_Execute(commandData, message, elements):
    window = pywebview.create_window(
        'Tab Creator',
        url=HTML_PATH,
        width=1200,
        height=800,
        resizable=True,
        js_api=TabCreatorAPI()   # see JS bridge spec below
    )
    pywebview.start()
    return IExternalCommand.Result.Succeeded
```

**JS bridge (TabCreatorAPI class) — methods the HTML calls via `window.pywebview.api.*`:**

| Method | Called when | Returns |
|---|---|---|
| `get_revit_version()` | window loads | Reads the active Revit version from the running instance, e.g. `"2024"` — populates the "detected Revit 2024" indicator |
| `get_installed_commands()` | Record mode starts | list of `{name, commandId, sourceTab, icon}` dicts captured from Revit's ribbon |
| `save_export(json_str)` | user clicks "Export Config →" | Saves profile JSON to `app/profiles/` AND copies to user's Desktop for easy transmission. Returns `{path: "...", desktop_path: "..."}` |
| `pick_icon(tool_name)` | user hovers a tool card and clicks the icon picker | Opens file dialog filtered to `*.png`. Copies selected file to `icons/` renamed as `{toolName}.png` (appends `(1)`, `(2)` etc. if name collides with existing icon), returns `{filename: "Move.png"}` or `null` if cancelled |
| `load_profile_into_editor(profile_name)` | user picks a profile from dropdown | Reads profile JSON from `app/profiles/`, returns full profile object to populate the editor state |
| `open_profiles_folder()` | user clicks "Open Profiles Folder" | Opens `app/profiles/` in Windows Explorer |

**Record mode implementation** (`get_installed_commands`):

Uses `Autodesk.Windows.ComponentManager` from `AdWindows.dll` to walk the ribbon tree and collect all `RibbonItem` entries:

```python
import clr
clr.AddReference('AdWindows')
from Autodesk.Windows import ComponentManager, RibbonTab, RibbonPanel, RibbonButton

def get_installed_commands():
    results = []
    ribbon = ComponentManager.Ribbon
    for tab in ribbon.Tabs:
        source_tab = tab.Title if not tab.IsContextualTab else None
        for panel in tab.Panels:
            for item in panel.Source.Items:
                if hasattr(item, 'CommandId') and item.CommandId:
                    results.append({
                        'name':      item.Text or item.Id,
                        'commandId': str(item.CommandId),
                        'sourceTab': source_tab,
                        'icon':      None   # icon extraction TBD
                    })
    return results
```

This populates TabCreator's `allTools` list at runtime instead of using the hardcoded demo data.

---

### 3. `profile_selector.py` — standalone launcher

Runs outside Revit. Opens profile_loader.html in a pywebview window.

**`launch_profile_loader.bat`** (at extension root — user double-clicks to launch):
```bat
@echo off
pip install pywebview >nul 2>&1
python "%~dp0app\profile_selector.py"
```

> **Future:** Replace `.bat` with a compiled `RESTer_ProfileLoader.exe` via PyInstaller (`--onefile --noconsole`) for release packaging. Python code is identical — packaging step only.

```python
import pywebview
import os

HTML_PATH = os.path.join(os.path.dirname(__file__), '..', 'ui', 'profile_loader.html')

window = pywebview.create_window(
    'Profile Selector',
    url=HTML_PATH,
    width=1100,
    height=700,
    js_api=ProfileSelectorAPI()
)
pywebview.start()
```

**JS bridge (ProfileSelectorAPI class):**

| Method | Called when | Behaviour |
|---|---|---|
| `get_profiles()` | window loads | Reads all `.json` files from `app/profiles/`, returns list of parsed profile objects |
| `get_active_profile()` | window loads | Reads `app/active_profile.json`, returns profile name string or `null` |
| `get_revit_versions()` | window loads | Scans `%APPDATA%\Autodesk\Revit\Addins\` for year subdirs, returns list e.g. `["2024","2025"]` — populates the version dropdown; user picks which to target |
| `is_revit_running()` | on launch only | Checks process list for `Revit.exe`, returns bool. When true, Load Profile is **blocked** with an error message telling the user to close Revit first. Checked once at launch — not polled |
| `add_profile(file_path)` | user selects file | Validates schema, copies to `app/profiles/` (profile is now available in the dropdown), returns profile object or error |
| `load_profile(profile_name, disable_non_required)` | "Load Profile →" | Writes `active_profile.json`, applies hideRules (addin suppression), returns `{ok, warnings[]}` |
| `remove_profile(profile_name)` | "Remove Profile" | Deletes file from `app/profiles/`, returns ok |
| `restore_addins(revit_version)` | "↺ Restore Add-ins" | Renames all `.addin.inactive` → `.addin` in the version's addin dir |

**File picker (add_profile):**
```python
import tkinter as tk
from tkinter import filedialog

def add_profile(self):
    root = tk.Tk()
    root.withdraw()
    path = filedialog.askopenfilename(
        title='Select a RESTer profile',
        filetypes=[('RESTer Profile', '*.json'), ('All files', '*.*')]
    )
    root.destroy()
    if not path:
        return {'ok': False, 'error': 'cancelled'}
    return self._validate_and_copy(path)
```

---

### 4. `addin_scanner.py` — presence check + suppression

**Addins directory:**
```
%APPDATA%\Autodesk\Revit\Addins\{version}\
```
e.g. `C:\Users\{user}\AppData\Roaming\Autodesk\Revit\Addins\2024\`

**Presence check** (called during `load_profile`):
```python
import os, json

def check_addins(required_addins, revit_version):
    """
    Returns dict: { tabName: 'present' | 'missing' | 'unknown' }
    """
    lookup = load_addin_lookup()   # reads lookup/addin_lookup.json
    addins_dir = get_addins_dir(revit_version)
    installed_files = set(os.listdir(addins_dir))   # includes .addin.inactive
    active_files = {f for f in installed_files if f.endswith('.addin')}
    results = {}

    for tab_name in required_addins:
        entry = lookup.get(tab_name)
        if entry:
            # Known addin — exact file match
            results[tab_name] = 'present' if entry['file'] in active_files else 'missing'
        else:
            # Unknown — fuzzy contains search across all .addin filenames
            match = next(
                (f for f in active_files if tab_name.lower() in f.lower()),
                None
            )
            if match:
                # Found via fuzzy — record the mapping for community sourcing
                _record_fuzzy_match(tab_name, match)
                results[tab_name] = 'present'
            else:
                results[tab_name] = 'unknown'

    return results
```

**Community sourcing on fuzzy match:**
When a fuzzy match succeeds, write the discovered mapping to a local `user_addin_overrides.json` file. On next run, check this file before falling back to fuzzy search. Structure:
```json
{ "SomeUnknownTab": "SomeUnknownTab.SomePlugin.addin" }
```
These can later be submitted to a central registry to expand the canonical lookup table.

**Addin suppression** (`hideRules` application):
```python
def apply_hide_rules(hide_rules, revit_version):
    """
    For each tab name in hide_rules, find its .addin file and rename
    it to .addin.inactive so it won't load on next Revit launch.
    Revit must be closed before calling this.
    """
    lookup = load_addin_lookup()
    addins_dir = get_addins_dir(revit_version)

    for tab_name in hide_rules:
        if tab_name == 'pyRevit':
            continue  # protected — never disable
        entry = lookup.get(tab_name)
        filename = entry['file'] if entry else _fuzzy_find(tab_name, addins_dir)
        if not filename:
            continue
        src  = os.path.join(addins_dir, filename)
        dest = src + '.inactive'
        if os.path.exists(src):
            os.rename(src, dest)

def restore_all_addins(revit_version):
    """Rename all .addin.inactive → .addin in the version folder (skip pyRevit)."""
    addins_dir = get_addins_dir(revit_version)
    for f in os.listdir(addins_dir):
        if f.endswith('.addin.inactive') and f != 'pyRevit.addin.inactive':
            src  = os.path.join(addins_dir, f)
            dest = src.replace('.addin.inactive', '.addin')
            os.rename(src, dest)
```

**`disable_non_required` toggle** (the ProfileSelector footer toggle):

When enabled, suppress every `.addin` file in the version's addin directory *except* those whose `file` names appear in the resolved `requiredAddins` list:
```python
def disable_non_required_addins(required_addins, revit_version):
    lookup = load_addin_lookup()
    keep_files = {lookup[a]['file'] for a in required_addins if a in lookup}
    keep_files.add('pyRevit.addin')  # protected — never disable
    addins_dir  = get_addins_dir(revit_version)
    for f in os.listdir(addins_dir):
        if f.endswith('.addin') and f not in keep_files:
            os.rename(
                os.path.join(addins_dir, f),
                os.path.join(addins_dir, f + '.inactive')
            )
```

---

## JS Bridge Wiring — How the HTML calls Python

Both HTML files need to replace their current `alert()`-based stubs with pywebview API calls. The HTML files must **not** be modified structurally — all wiring happens by replacing stub functions only.

**ProfileSelector — functions to replace:**

| Current stub | Replace with |
|---|---|
| `addProfile()` | `window.pywebview.api.add_profile().then(profile => { profiles.push(profile); renderCards(); })` |
| `loadProfile()` | `window.pywebview.api.load_profile(selectedProfile.profile, disableNonRequired).then(...)` |
| `restoreAllAddins()` | `window.pywebview.api.restore_addins(currentRevitVersion).then(...)` |
| `confirmRemove()` confirm path | `window.pywebview.api.remove_profile(name).then(...)` |

**Also wire on load:**
```javascript
window.addEventListener('pywebviewready', async function() {
    const [profileList, active, versions] = await Promise.all([
        window.pywebview.api.get_profiles(),
        window.pywebview.api.get_active_profile(),
        window.pywebview.api.get_revit_versions()
    ]);
    // populate profiles[], activeProfileName, revit version dropdown
    // then renderCards() and selectCard on active profile
    // check is_revit_running() once and set blocked state if true
});
```

**TabCreator — functions to replace:**

| Current stub | Replace with |
|---|---|
| `toggleRecord()` | On start: `window.pywebview.api.get_installed_commands().then(cmds => { state.allTools = cmds; renderToolList(); })` |
| `exportConfig()` download | After building `config` object: `window.pywebview.api.save_export(JSON.stringify(config)).then(r => showSuccessToast(r.path))` |

**Revit version display in TabCreator:**
```javascript
window.addEventListener('pywebviewready', async function() {
    const ver = await window.pywebview.api.get_revit_version();
    document.getElementById('rvtVersionDisplay').textContent = 'Revit ' + ver;
});
```

---

## PyRevit Extension Manifest

`extension.json`:
```json
{
  "name": "RESTer",
  "description": "Custom toolbar profile system for Revit",
  "type": "extension",
  "startup_script": "startup.py",
  "author": "Design/OS"
}
```

---

## Tab Creator UI — Interaction Model

> **Updated from original spec.** Add Tool / Add Stack buttons have been removed. All placement is checkbox-driven.

### Tool placement
Clicking any row in the **Available Tools** list toggles that tool in the currently-selected panel. The `t-check` box shows filled (green ✓) when placed. Clicking again removes it. The slot list in the fields pane reflects the current panel's tools in order and supports drag-to-reorder via the `⠿` handle. The `×` button on a slot is a secondary removal path that stays in sync with the tool list checkboxes.

### Stack placement
Clicking any row in the **Stacks** sidebar list toggles that stack in/out of the current panel. The checkbox uses purple (matching `--accent2`) when placed.

### Panel inclusion
Each panel row in the **Panels** sidebar has a checkbox on its left edge. Checked = panel is **active**: shown in the tab canvas and included in the export. Unchecked = panel is **inactive**: shown dimmed in the sidebar, excluded from the canvas and from `exportConfig()`. Clicking the panel row (not the checkbox) selects it for editing in the fields pane without changing its active state.

### Tab canvas drag reorder
Active panels in the tab canvas are `draggable="true"`. Dragging a panel card onto another swaps their positions in `state.panels` (object key order). Dragging onto the trailing drop zone moves the panel to the end. `renderPanelList()` is called after every reorder to keep the sidebar in sync.

### Tool icons
RESTer ships with a generic default icon used for all ribbon buttons. Users can assign a custom icon per tool via the TabCreator UI: hovering a tool card in the panel slot list reveals an icon-picker button. Clicking it calls `pick_icon(tool_name)` on the JS bridge, which opens a file dialog filtered to `*.png`, copies the selected file into `icons/` renamed as `{toolName}.png`, and returns the filename. The filename is stored on the slot as `iconFile`. At export, `iconFile` is included in the JSON. At Revit startup, `startup.py` resolves `iconFile` relative to the `icons/` dir; if missing or not set, the generic default icon is used.

### `activePanels` propagation
`state.activePanels` (a `Set`) gates four places:
1. `renderTabCanvas()` — only active panels rendered
2. `getDetectedAddins()` — required addins derived only from active panels
3. `referencedStacks` in `exportConfig()` — only stacks used in active panels exported
4. `exportConfig()` panels array — only active panels written to JSON



1. **`requiredAddins` uses ribbon tab names** (sourceTab convention), not product names. ADDIN_LOOKUP is the bridge to `.addin` filenames.
2. **Stacks export resolved commandIds** — the runtime never needs to look up commandId separately. Slot objects are fully self-contained.
3. **`hideRules` are ribbon tab names**, same convention as `requiredAddins`. They suppress at the `.addin` file level, not the Revit API level.
4. **`checkExportReady` intentionally does not gate on `hideRules`** — an empty `hideRules: []` is a valid, complete profile.
5. **ProfileSelector reads the entire profiles directory at launch** — no database, no registry. Source of truth is the filesystem.
6. **`active_profile.json` is written by ProfileSelector** and read by `startup.py`. It is never written by TabCreator.
7. **TabCreator runs inside Revit** (pywebview from PyRevit button). **ProfileSelector runs outside Revit** (standalone launcher). They do not run simultaneously in the same process.
8. **Profile filenames** follow the pattern `{profile}_{exportDate}.json`, e.g. `Design_2025_2024-03-12.json`. The `profile` field inside the JSON is the canonical identifier — not the filename.
9. **Re-exporting a profile overwrites** the existing file in `app/profiles/` (matched by `profile` name). The `exportDate` is updated, and a fresh copy is placed on the Desktop.
