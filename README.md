# RST

Custom Revit ribbon toolbar profile system built on PyRevit. Admins build curated toolbar profiles from any installed Revit tool or add-in. Users load profiles to get a clean, purpose-built ribbon — no digging through tabs. Supports custom URL buttons, company branding, colored panels with rounded corners, opacity control, tool stacks, and one-click updates.

> **v0.5.0-beta** — functional but still in active development. Use at your own risk.

**Requires:** Windows 10/11 • Revit 2024+ • pyRevit 4.8+ • Python 3.12 • Microsoft Edge WebView2 runtime (ships with Win11 and modern Win10; older systems install from [Microsoft](https://developer.microsoft.com/microsoft-edge/webview2/)).

---

## What It Does

- **Detect** every tool on every ribbon tab in Revit (1400+ commands across all installed add-ins)
- **Build** custom panels with tools from any source — Architecture, DiRootsOne, Kinship, pyRevit, Modify, View, Manage, etc.
- **Custom URL tools** — add company links, wikis, SharePoint, Teams, email (mailto:), or any URL as clickable toolbar buttons with auto-assigned icons (persistent across sessions)
- **Branding** — company logo on every profile tab, customizable per install
- **Color** each panel with a custom hex color and adjustable opacity (10%–100%) with rounded corners
- **Tool stacks** — group 2–3 related tools into vertically stacked small buttons (text-only, like native Revit)
- **Two-line tool names** — long names auto-split at the first space for compact display
- **Add-in detection** — live session scan shows which add-ins are loaded, flags native Revit tools
- **Export** profiles as self-contained JSON files for easy sharing (email, OneDrive, Slack, etc.)
- **Load** profiles and rebuild the ribbon live inside Revit — no restart needed
- **Profile switching** — hot-swap between profiles with automatic pyRevit reload
- **Blank profiles** — unloading or deleting the active profile writes a BlankRST marker so the RST tab stays alive with branding only
- **One-click update** — downloads latest from GitHub (zip), preserves user data, reloads automatically
- **RSTify** — profile-aware tab hiding replaces MinifyUI; auto-activates on load, toggle on/off with icon color feedback
- **Health** — one-click workstation + Revit session snapshot (CPU/RAM/GPU/Disk, display, network, OS, active model + size, warnings). Includes Clean Junk Files for Temp / PacCache / Journals / Collaboration Cache. All local, no telemetry.

---

## Install

**Prerequisite:** a working Revit install. Everything below runs on Windows.

### 1. Install pyRevit

Download and run the latest pyRevit installer (4.8+):
https://github.com/pyrevitlabs/pyRevit/releases/latest

After install, open Revit once to confirm the **pyRevit** tab appears on the ribbon.

### 2. Install Python 3.12 + pywebview

RST's admin and loader windows run on CPython 3.12 with pywebview (Python 3.14+ is not yet compatible).

**On ARM64 Windows** — Surface Pro X, Copilot+ PCs, Parallels on Apple Silicon — use the x64 command below. pywebview's native dependencies don't ship ARM64 builds, and Revit itself is x64.

Open PowerShell and run:

```powershell
# x64 Windows (most machines)
winget install --id Python.Python.3.12 --scope user

# ARM64 Windows — force x64 install
winget install --id Python.Python.3.12 --scope user --architecture x64
```

Then install pywebview and verify:

```powershell
py -3.12 -m pip install --user pywebview
py -3.12 -c "import webview; print('ok')"
```

The last command should print `ok`. If you see an ImportError, re-run the pywebview install step and check for network or permission errors.

> **No winget?** It ships with Windows 11 and modern Windows 10. If missing, install [App Installer](https://apps.microsoft.com/detail/9NBLGGH4NNS1) from the Microsoft Store first.

> **Optional:** `install.bat` in the repo root automates this section (winget check → Python 3.12 → pywebview). User-scope only, no admin required.

### 3. Add the RST extension

1. Open Revit.
2. **pyRevit** tab → **Extensions** → **Add Extension**.
3. Paste:
   ```
   https://github.com/jedbjorn/RST
   ```
4. Reload pyRevit (pyRevit tab → Reload, or restart Revit).

An **RST** tab should now appear on the Revit ribbon. Click **Profiler** to start building toolbar profiles, or **Loader** to open an existing one.

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
- **+ Add URL** for custom URL buttons and mailto: email links (persistent across sessions)
- **Icon picker** with 50 built-in icons and search bar for quick filtering
- **Add Logo** for company branding (48x48, resized automatically)
- **Set Protection** — admin panel for locking/protecting add-ins from disable operations
- Export → animated overlay with file paths → auto-closes. Active profiles can be re-exported with a reload warning

### Loader
Load and manage profiles:
- Header: Revit version (live from session), "Add Profile from Path"
- Profile cards with tab preview, required add-ins status
- **RSTify tab toggles** — two-column layout: hide tabs (left 1/3) + required add-ins (right 2/3)
- **Disable unused add-ins** toggle — preview which add-ins stay active vs get disabled before confirming
- Load Profile → auto-closes, triggers pyRevit reload
- **Restore All Add-ins** — one-click re-enable of all RST-disabled add-ins
- Unload or delete profiles (writes BlankRST marker, tab stays alive with branding)

### RSTify
Custom tab visibility manager that replaces pyRevit's MinifyUI:
- Click to **toggle** hidden tabs on/off — orange icon when hiding, blue when showing
- Tabs to hide are configured in the Profile Loader at load time
- Auto-activates on every startup/reload when a profile has hidden tabs
- No reconfigure from the button — reload profile to change which tabs are hidden

### Update
Downloads latest from GitHub (zip-only), preserves user data, reloads pyRevit with animated message.

### Health
Point-in-time snapshot of the workstation and Revit session. Launched via the **Snap** pushbutton; also runs automatically when RST loads so data is fresh by the time the user opens the window.

**What it shows** — four collapsible sections, each with a severity dot (ok / soft-warn / warn / danger) driven by threshold rules:

- **Hardware** — CPU (name, cores, live %used), RAM (total, used %), GPU (model, driver, VRAM), Disk C: (SSD/HDD, total, free, used %). Dynamic values are color-coded; identity fields stay neutral.
- **Display & Network** — primary resolution, monitor count, active adapter + link speed.
- **Revit** — version + build, Revit username, hardware acceleration setting (from `Revit.ini`), active model name + path + file size (with size thresholds at 1/1.5/2 GB), warnings count with severity breakdown.
- **Operating System** — Windows name, release, build.

**How it gets the data**

- **RAM / CPU%** — Win32 API via `ctypes` (`GlobalMemoryStatusEx`, `GetSystemTimes`). CPU% is a 500ms-delta snapshot.
- **CPU name / cores / OS build** — registry (`HKLM\HARDWARE\...\CentralProcessor`) + Python `platform` module.
- **GPU / Network adapter / Disk type / Monitors** — single PowerShell call against WMI (`Win32_VideoController`, `Win32_NetworkAdapter`, `Get-PhysicalDisk`, `Win32_DesktopMonitor`).
- **Revit session data** — Revit API on the IronPython side (version, build, username, active model, warnings).
- **Hardware acceleration flag** — parsed from `%APPDATA%\Autodesk\Revit\Autodesk Revit <ver>\Revit.ini`.
- **Model file size** — `.NET FileInfo` on the local file. For ACC / BIM 360 models whose `doc.PathName` is a cloud URL, falls back to walking `%LOCALAPPDATA%\Autodesk\Revit\<ver>\CollaborationCache` (matching by project/model GUID when available, otherwise newest `.rvt` mtime).

**Triggers**

- **On RST load** — fire-and-forget background scan (~1–3s), no model context since no document is open yet.
- **On Snap click** — synchronous scan with full Revit context, so the viewer opens on fresh data. Clean Junk Files and Close buttons live in the viewer footer.

**Privacy**

Everything stays on the workstation. The viewer reads `data/health_scan.json` from the extension folder. No network calls, nothing sent anywhere.

### Clean Junk Files
Bottom-right button in the Health viewer. Opens a modal with per-category toggles (all ON by default):

- **Windows Temp Files** — everything in `%LOCALAPPDATA%\Temp`
- **Revit PacCache** — Revit package cache
- **Revit Journals** — all journal files, every installed Revit version
- **Collaboration Cache** — central model cache, excluding today's activity

Confirm → delete → result message with per-category counts. Files locked by running applications are skipped automatically (matches the original Dynamo script behavior). Safe to run with Revit open — anything Revit holds open survives.

### Reload
Triggers pyRevit reload to apply changes.

---

## Custom URL Tools

1. In the Profiler, click **+ Add URL** at the bottom of the tool list
2. Enter a name (e.g. "Company Wiki") and a URL — email addresses are auto-detected and converted to `mailto:` links
3. The tool appears tagged "Custom" with a link icon (🔗) or @ icon for email — add to any panel like a regular tool
4. In Revit, clicking the button opens the URL in the default browser (or default email client for mailto:)
5. Revit ribbon automatically uses `pack:link_external` icon for URLs and `pack:at` icon for email tools

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

- **Colors** — two rows of swatches: 8 built-in presets (Blue, Green, Purple, Amber, Red, Cyan, Orange, Lime) and 8 custom slots (initially blank, shown as dashed outlines)
- **Persistent color config** — swatch colors are stored in `app/panel_colors.json` and persist across sessions. Click a swatch to select it, type a hex code (with or without `#`, spaces are stripped), then click **✓** to write the color to that swatch. Click **✕** to reset — built-in swatches restore to their factory color, custom swatches clear back to blank. All 16 swatches update live across the panel list, tab preview, and panel slot cards.
- **Opacity** — per-profile opacity slider (10%–100%) applied to all panel backgrounds
- **Rounded corners** — WPF DrawingBrush with RectangleGeometry
- **RST admin panels** — light grey rounded backgrounds, applied after pyRevit finishes loading
- **Two-line names** — tool names with spaces split at the first space

### Finding Colors

Need hex codes for your brand colors? The Profiler includes a link to [imagecolorpicker.com](https://imagecolorpicker.com/) — a free web tool that lets you upload an image (logo, brand guide, screenshot) and click any pixel to get the hex code. Useful for pulling exact colors from company branding or matching existing UI themes.

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
  "requiredAddins": [
    { "tabName": "DiRootsOne", "addinFile": "DiRoots.One.addin", "url": "https://diroots.com", "origin": "third-party" },
    { "tabName": "pyRevit", "addinFile": "pyRevit.addin", "url": "https://github.com/pyrevitlabs/pyRevit/releases", "origin": "third-party" }
  ],
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

## Uninstall

Remove the RST entry from **pyRevit → Extensions → Manage** (or delete the RST folder from any Custom Extension Directory you registered). Reload pyRevit. Python 3.12 and pywebview can stay — they're harmless and may be used by other tools.

---

## Known Limitations

- **pyRevit script-based tools** can be detected and placed but may not execute via PostCommand
- **Some OOTB Revit tools** with dropdown/list button CommandIds are filtered out automatically
- **Locked files during update** — icons loaded by Revit are skipped and overwritten on next restart
- **Tab persistence** — custom tabs don't survive Revit restart; `startup.py` rebuilds on every launch
- **Hidden tabs break tools** — tools from hidden tabs may not execute. RSTify protects source tabs from being hidden, but manually hiding a tab with pyRevit's MinifyUI (if restored) can break tools
- **MinifyUI deleted** — RST deletes the MinifyUI smartbutton folder on profile load. Reinstall pyRevit to restore MinifyUI after removing RST
- **Add-in disabling** — user-scope only. Machine-scope (ProgramData) add-ins are tracked but never disabled. Protected and Autodesk add-ins always exempt

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
