# RST

Custom Revit ribbon toolbar profile system built on PyRevit. Admins build curated toolbar profiles from any installed Revit tool or add-in. Users load profiles to get a clean, purpose-built ribbon — no digging through tabs. Supports custom URL buttons, company branding, colored panels with rounded corners, opacity control, tool stacks, and one-click updates.

> **DISCLAIMER: THIS IS AN ALPHA RELEASE. USE AT YOUR OWN RISK.**

---

## What It Does

- **Detect** every tool on every ribbon tab in Revit (1400+ commands across all installed add-ins)
- **Build** custom panels with tools from any source — Architecture, DiRootsOne, Kinship, pyRevit, Modify, View, Manage, etc.
- **Custom URL tools** — add company links, wikis, SharePoint, Teams, or any URL as clickable toolbar buttons (persistent across sessions)
- **Branding** — company logo on every profile tab, customizable per install
- **Color** each panel with a custom hex color and adjustable opacity (10%–100%) with rounded corners
- **Tool stacks** — group 2–3 related tools into vertically stacked small buttons (text-only, like native Revit)
- **Two-line tool names** — long names auto-split at the first space for compact display
- **Add-in detection** — live session scan shows which add-ins are loaded, flags native Revit tools
- **Export** profiles as self-contained JSON files for easy sharing (email, OneDrive, Slack, etc.)
- **Load** profiles and rebuild the ribbon live inside Revit — no restart needed
- **Profile switching** — hot-swap between profiles with automatic pyRevit reload
- **Blank profiles** — unloading or deleting the active profile creates a clean blank tab
- **One-click update** — downloads latest from GitHub (zip), preserves user data, reloads automatically
- **RSTify** — profile-aware tab hiding replaces MinifyUI; auto-activates on load, toggle on/off with icon color feedback

---

## Install

### 1. Dependencies

- [pyRevit](https://github.com/pyrevitlabs/pyRevit) 4.8+
- **Python 3.12** (two versions back from the bleeding edge — 3.14 is too new for pywebview)

#### Install Python via the Python Install Manager

The Python Install Manager (`py`) is the recommended way to install and manage Python on Windows.

1. **Install the manager** — open PowerShell and run:
   ```powershell
   winget install 9NQ7512CXL7T
   ```
   > winget comes pre-installed on Windows 11 and modern Windows 10. If `winget` is not found, install [App Installer](https://apps.microsoft.com/detail/9NBLGGH4NNS1) from the Microsoft Store.

2. **Run first-launch configuration:**
   ```powershell
   py install --configure
   ```
   When prompted, allow Python to manage installations and ensure the global shortcuts directory is on your PATH.

3. **Install Python 3.12:**
   ```powershell
   py install 3.12
   ```

4. **Install pywebview:**
   ```powershell
   py -3.12 -m pip install pywebview
   ```

5. **Verify:**
   ```powershell
   py -3.12 --version
   ```
   Should show `Python 3.12.x`.

### 2. Add Extension

1. Open Revit
2. pyRevit tab → Extensions → Add Extension
3. Paste this URL:
   ```
   https://github.com/jedbjorn/RST
   ```
4. Reload pyRevit

You should see an **RST** tab in the Revit ribbon.

---

## How It Works

### Architecture

```
Revit (IronPython)              CPython 3.12 + pywebview
┌──────────────────────┐       ┌─────────────────────────┐
│ Pushbutton scripts   │─JSON─▶│ Tab Creator UI (admin)  │
│ startup.py           │ file  │ Profile Loader UI (user) │
│ (builds ribbon)      │       └─────────────────────────┘
└──────────────────────┘
```

One IronPython process inside Revit, one CPython process for UIs, temp JSON files as the bridge. No persistent services, no background processes.

### On Revit Launch (startup.py)

1. Reads `active_profile.json` → loads the referenced profile
2. Removes any existing `REST_*` tabs from the ribbon
3. Builds branding panel (logo, always leftmost)
4. Creates colored panels with rounded-corner backgrounds
5. Adds large tool buttons with PostCommand handlers
6. Adds small tool groups (standard-sized text-only buttons)
7. Deletes pyRevit's MinifyUI smartbutton folder (if it exists) to avoid conflicts
8. On Idling event: styles RST admin panels grey, hides tabs configured in RSTify, sets RSTify icon to orange

### Profiler Flow (Admin)

1. Click **Profiler** → IronPython scans ribbon (1400+ commands) + loaded add-ins → writes `_revit_data.json` → launches CPython UI
2. Admin detects tools, creates panels, picks colors, adds tools/stacks/URLs, sets branding
3. **Export** → saves profile JSON to `app/profiles/` + Desktop copy → animated overlay → window auto-closes (3s)

### Loader Flow (User)

1. Click **Loader** → IronPython collects Revit version + loaded add-ins → writes `_loader_data.json` → launches CPython UI
2. User browses profiles, sees tab preview, checks add-in compatibility (Native/Loaded/Not Loaded)
3. User configures **RSTify tab toggles** — choose which tabs to hide (source tabs and core tabs are locked visible)
4. **Load Profile** → writes `active_profile.json` with profile + hidden tabs → animated overlay → window auto-closes (3s)
5. ProfileLoader button detects the change → shows "Reloading pyRevit..." with animated dots → `sessionmgr.reload()` → ribbon rebuilds with hidden tabs applied

### Add-in Detection

Uses AdWindows ribbon tab scan from the live Revit session. Every non-builtin, non-contextual tab title is captured as a loaded add-in:

- **Native** (green) — built-in Revit tabs (Architecture, View, Manage, etc.) — always available
- **Loaded** (green) — add-in tabs detected in the current session (DiRootsOne, pyRevit, Kinship, etc.)
- **Not Loaded** (red) — required by the profile but not found in the current session

### Update Flow

1. Click **Update** → downloads zip from GitHub → extracts to staging
2. Preserves user data (profiles, active profile, branding logo, config, custom tools, log)
3. Copies new files, skips locked files
4. Shows "Reloading pyRevit..." → auto-reloads

---

## RST Tab

Five tool panels with rounded grey backgrounds:

### Profiler
Build and edit toolbar profiles:
- **Detect** scans all installed tools across every ribbon tab
- Search and filter tools by name or source tab
- Create panels with custom colors (hex input + swatches) and opacity (10%–100%)
- Add tools via checkbox, drag to reorder
- Create tool stacks (2–3 small buttons stacked vertically)
- A tool can only be in one place — adding to a stack removes it from standalone; greyed tools show "Go to [location]" on click
- **+ Add URL** for custom URL buttons (persistent across sessions)
- **Add Logo** for company branding (48x48, resized automatically)
- Export → animated overlay with file paths → auto-closes

### Loader
Load and manage profiles:
- Header: Revit version (live from session), "Add Profile from Path"
- Profile cards with tab preview, required add-ins status
- **RSTify tab toggles** — two-column layout: hide tabs (left 1/3) + required add-ins (right 2/3)
- Load Profile → auto-closes, triggers pyRevit reload
- Unload or delete profiles (creates blank tab if active)

### RSTify
Custom tab visibility manager that replaces pyRevit's MinifyUI:
- Click to **toggle** hidden tabs on/off — orange icon when hiding, blue when showing
- Tabs to hide are configured in the Profile Loader at load time
- Auto-activates on every startup/reload when a profile has hidden tabs
- No reconfigure from the button — reload profile to change which tabs are hidden

### Update
Downloads latest from GitHub (zip-only), preserves user data, reloads pyRevit with animated message.

### Reload
Triggers pyRevit reload to apply changes.

---

## Custom URL Tools

1. In the Profiler, click **+ Add URL** at the bottom of the tool list
2. Enter a name (e.g. "Company Wiki") and a URL
3. The tool appears tagged "Custom" — add to any panel like a regular tool
4. In Revit, clicking the button opens the URL in the default browser

Custom tools persist across Profiler sessions (`app/custom_tools.json`). They can be edited, deleted, and survive Detect scans and profile export/import.

---

## RSTify — Tab Visibility

RSTify replaces pyRevit's MinifyUI with profile-aware tab hiding. Instead of a global hide list, each profile load lets you choose which tabs to hide.

### How It Works

1. In the **Profile Loader**, select a profile
2. The **RSTify: Hide These Tabs** column shows all ribbon tabs with toggles
3. **Core tabs** (Modify, Manage, View, Annotate, Add-Ins) are locked — can't hide
4. **Source tabs** (tabs with tools used by the profile) are locked — hiding them would break tools
5. Everything else can be toggled off (orange = will be hidden)
6. Click **Load Profile** — hidden tab selections are saved with the profile
7. On reload, configured tabs are hidden automatically and the RSTify button turns orange

### RSTify Button

- **Orange icon** → tabs are hidden. Click to show all tabs.
- **Blue icon** → all tabs visible. Click to re-hide configured tabs.
- No configuration UI — just a toggle. Reconfigure by reloading the profile.

### Previous Selections

When you open the Loader, your previous hidden tab selections are remembered. Tabs you hid last time are pre-toggled.

### pyRevit MinifyUI

RST automatically deletes pyRevit's MinifyUI smartbutton folder when a profile is loaded to avoid conflicts.

**To restore MinifyUI:** Unload your RST profile (blank tab), then reinstall pyRevit from [pyrevitlabs.github.io/pyRevit](https://pyrevitlabs.github.io/pyRevit/).

### Important

Hiding a tab prevents tools from that tab from executing via PostCommand. RST protects source tabs (tabs with tools in your profile) from being hidden. Only tabs with **no tools** in your profile can be toggled off.

---

## Branding

Every profile tab includes a branding panel (always leftmost) with a logo.

- **Default:** RST logo ships with the extension
- **Custom:** Click **Add Logo** in the Profiler to upload your company logo (48x48 recommended)
- Logo persists across sessions and updates (`icons/branding.png`)

---

## Panel Styling

- **Colors** — custom hex color per panel with opacity control (10%–100%)
- **Rounded corners** — WPF DrawingBrush with RectangleGeometry
- **RST admin panels** — light grey rounded backgrounds, applied after pyRevit finishes loading
- **Two-line names** — tool names with spaces split at the first space

---

## Profile JSON

Profiles are self-contained JSON files:

```json
{
  "profile": "Design_2025",
  "tab": "Design",
  "min_version": "2024",
  "exportDate": "2026-04-07",
  "panelOpacity": 80,
  "requiredAddins": ["DiRootsOne", "pyRevit"],
  "hideRules": [],
  "stacks": {
    "Links": {
      "tools": [
        { "name": "SharePoint", "baseName": "SharePoint", "commandId": "URL:https://sharepoint.com", "sourceTab": "Custom" },
        { "name": "Teams", "baseName": "Teams", "commandId": "URL:https://teams.com", "sourceTab": "Custom" }
      ]
    }
  },
  "panels": [
    {
      "name": "Core Tools",
      "color": "#4f8ef7",
      "slots": [
        { "type": "tool", "baseName": "Wall", "name": "Wall (Architecture > Build)", "commandId": "ID_OBJECTS_WALL", "sourceTab": "Architecture" },
        { "type": "stack", "name": "Links" }
      ]
    }
  ]
}
```

The branding panel is not in the profile — injected automatically at runtime.

---

## Configuration

### Add-in Lookup (`lookup/addin_lookup.json`)

Maps ribbon tab names to `.addin` filenames for display purposes. Single source of truth read by both UIs.

```json
{
  "TabName": { "displayName": "Human-readable Name", "file": "Filename.addin" }
}
```

Add entries for firm-specific add-ins. Changes take effect on next Profiler/Loader open.

### Protected Add-ins & Exempt Paths (`lookup/config.json`)

```json
{
  "protected_addins": [
    "pyRevit.addin",
    "Kinship.addin",
    "Dynamo.addin",
    "DynamoForRevit.addin"
  ],
  "exempt_paths": [
    "%APPDATA%\\Dynamo"
  ]
}
```

**`protected_addins`** — never touched by RST. **`exempt_paths`** — entire directories RST will never modify. Supports environment variables.

Both files are preserved across updates.

---

## Known Limitations

- **pyRevit script-based tools** can be detected and placed but may not execute via PostCommand
- **Some OOTB Revit tools** with dropdown/list button CommandIds are filtered out automatically
- **Locked files during update** — icons loaded by Revit are skipped and overwritten on next restart
- **Tab persistence** — custom tabs don't survive Revit restart; `startup.py` rebuilds on every launch
- **Hidden tabs break tools** — tools from hidden tabs may not execute. RSTify protects source tabs from being hidden, but manually hiding a tab with pyRevit's MinifyUI (if restored) can break tools
- **MinifyUI deleted** — RST deletes the MinifyUI smartbutton folder on profile load. Reinstall pyRevit to restore MinifyUI after removing RST
- **Add-in disabling** — feature deferred; code exists but is not active

---

## Tech Stack

- **pyRevit** — extension framework, ribbon buttons, startup hooks
- **IronPython** — Revit-side scripts (ribbon scanning, ribbon building, panel styling, reload UI)
- **CPython 3.12** — UI windows via pywebview
- **AdWindows.dll** — ribbon manipulation (scan tools, build panels, detect add-ins, set colors)
- **WPF** — ImageBrush for branding, DrawingBrush for rounded corners, ToolWindow for reload message
- **pywebview** — HTML-based UI windows for Profiler and Loader

---

## Links

- [CONNECTIONS.md](CONNECTIONS.md) — file map, API reference, data flow
- Author: [Designs/OS](https://github.com/jedbjorn)
