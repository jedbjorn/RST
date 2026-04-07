# RST

Custom Revit ribbon toolbar profile system built on PyRevit. Admins build curated toolbar profiles from any installed Revit tool or add-in. Users load profiles to get a clean, purpose-built ribbon — no digging through tabs. Supports custom URL buttons, company branding, colored panels with rounded corners, opacity control, tool stacks, and one-click updates.

> **DISCLAIMER: THIS IS AN ALPHA RELEASE. DISABLING EXTENSIONS IS UNTESTED. USE AT YOUR OWN RISK.**

---

## What It Does

- **Detect** every tool on every ribbon tab in Revit (1400+ commands across all installed add-ins)
- **Build** custom panels with tools from any source — Architecture, DiRootsOne, Kinship, pyRevit, Modify, View, Manage, etc.
- **Custom URL tools** — add company links, wikis, SharePoint, Teams, or any URL as clickable toolbar buttons
- **Branding** — company logo on every profile tab, customizable per install, links to your GitHub
- **Color** each panel with a custom hex color and adjustable opacity (10%–100%) with rounded corners
- **Tool stacks** — group related tools into dropdown stacks
- **Two-line tool names** — long names auto-split at the first space for compact display
- **Export** profiles as self-contained JSON files for easy sharing (email, OneDrive, Slack, etc.)
- **Load** profiles and rebuild the ribbon live inside Revit — no restart needed
- **Profile switching** — hot-swap between profiles with a reload
- **Blank profiles** — deleting the active profile creates a clean blank tab
- **One-click update** — pulls latest from GitHub with no git required, skips locked files
- **Minify UI** — one-click access to pyRevit's MinifyUI to hide unused ribbon tabs
- **Protect** pyRevit and Kinship add-ins from ever being disabled

---

## Install

### 1. Dependencies

- [pyRevit](https://github.com/pyrevitlabs/pyRevit) 4.8+
- [Python 3.12](https://www.python.org/downloads/) — **check "Add Python to PATH" during install** (3.14 is too new)
- pywebview:
  ```powershell
  python -m pip install pywebview
  ```

Verify: `python --version` in PowerShell should show `Python 3.12.x`.

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

## RST Tab

The RST tab contains five tool panels, each with its own icon and rounded grey background:

### Profiler
Build and edit toolbar profiles. Opens a full editor UI where you:
- Click **Detect** to scan all installed tools across every ribbon tab (1400+ commands)
- Search and filter tools by name, source tab, or "Custom" for URL tools
- Create panels, assign colors with hex input, set opacity (10%–100%)
- Drag panels to reorder in the tab preview
- Add tools to panels via checkbox — display names in panels, full source info in tooltips
- Create tool stacks (grouped dropdown buttons)
- **+ Add URL** — create custom URL buttons (company wikis, project links, standards portals)
- **Add Logo** — upload a company logo (48x48) for the branding panel
- Export profiles as JSON — auto-saves to extension folder + Desktop copy
- Auto-closes 4 seconds after successful export

### Loader
Switch between profiles without leaving Revit:
- Browse saved profiles with full tab preview showing panels, tools, and stacks
- Load a profile — success overlay with pyRevit reload instructions, auto-closes after 4 seconds
- Add profiles received from your admin via file picker
- Unload or delete profiles (warns and creates blank tab if deleting the active profile)
- Restore all disabled add-ins
- Toggle "disable non-required add-ins" per profile

> **WARNING: DISABLING ADD-INS IS UNTESTED. USE WITH CAUTION.**

### Minify
One-click toggle for pyRevit's built-in MinifyUI. Hides unused ribbon tabs to declutter the interface. Alerts if pyRevit command not found.

### Update
One-click update for the extension:
- Tries pyRevit git, then system git, then downloads zip from GitHub (no git required)
- Copies files directly, skips any locked files (icons, log)
- Preserves user data: profiles, active profile, branding logo, log
- Reloads pyRevit automatically after update
- Shows actual error details if something fails

### Reload
Triggers a pyRevit reload to apply profile changes and refresh the ribbon. Use after loading a new profile or switching profiles.

---

## Custom URL Tools

Add company-specific URL links directly to your toolbar:

1. In the Profiler, click **+ Add URL** at the bottom of the tool list
2. Enter a name (e.g. "Company Wiki") and a URL
3. The tool appears in the list tagged "Custom" with a link icon
4. Add it to any panel like a regular tool
5. In Revit, clicking the button opens the URL in the default browser

Custom tools can be edited or deleted at any time. They survive the Detect scan and round-trip cleanly through profile export/import. Filter the tool list to "Custom" to see only your URL tools.

---

## Branding

Every profile tab includes a branding panel (always leftmost) with a logo that links to the RST GitHub page.

- **Default:** RST logo ships with the extension
- **Custom:** Click **Add Logo** in the Profiler header to upload your company logo (48x48 recommended, resized automatically)
- The logo is set as the panel background via WPF ImageBrush
- A transparent button on top handles the click → opens [github.com/jedbjorn/RST](https://github.com/jedbjorn/RST)
- Logo persists across sessions and profile switches (`icons/branding.png`)

---

## Panel Styling

- **Colors** — each panel gets a custom hex color, applied with opacity control (10%–100%)
- **Rounded corners** — panel backgrounds use a WPF DrawingBrush with RectangleGeometry for rounded corners
- **RST admin panels** — styled with light grey rounded backgrounds, applied via Idling event after pyRevit finishes creating them
- **Two-line names** — tool names with spaces auto-split at the first space for compact ribbon display

---

## Workflow

### Admin
1. Open Revit → RST tab → **Profiler**
2. Click **Detect** to scan all available tools
3. Create panels, pick colors, set opacity, add tools
4. Optionally add custom URL tools and a company logo
5. **Export Config** → saves profile JSON + Desktop copy
6. Send the Desktop copy to users (email, OneDrive, Slack, etc.)

### User
1. Open Revit → RST tab → **Loader**
2. **Add Profile** → select the JSON from admin
3. Select profile → **Load Profile**
4. Click **Reload** on the RST tab → custom ribbon appears
5. Use **Minify** to hide unused tabs

### Profile Switching
1. RST tab → **Loader** → select different profile → **Load Profile**
2. Click **Reload** → ribbon updates to new profile
3. Previous tab is removed, new tab appears with branding

### External Use
The Profile Loader also works outside Revit via `launch_profile_loader.bat` in the extension folder.

---

## Profile JSON

Profiles are self-contained JSON files:

```json
{
  "profile": "Design_2025",
  "tab": "Design",
  "min_version": "2024",
  "exportDate": "2025-04-05",
  "panelOpacity": 80,
  "requiredAddins": ["DiRootsOne", "pyRevit"],
  "hideRules": [],
  "stacks": {
    "Edit Stack": {
      "tools": [
        { "name": "Move", "baseName": "Move", "commandId": "ID_MODIFY_MOVE", "sourceTab": null }
      ]
    }
  },
  "panels": [
    {
      "name": "Core Tools",
      "color": "#4f8ef7",
      "slots": [
        { "type": "tool", "baseName": "Wall", "name": "Wall (Architecture > Build)", "commandId": "ID_OBJECTS_WALL", "sourceTab": "Architecture" },
        { "type": "tool", "baseName": "Wiki", "name": "Wiki", "commandId": "URL:https://company.wiki", "sourceTab": "Custom" },
        { "type": "stack", "name": "Edit Stack" }
      ]
    }
  ]
}
```

The branding panel is **not** in the profile JSON — it is injected automatically by `startup.py` at runtime.

---

## Known Limitations

- **pyRevit script-based tools** (e.g. pyRevit Selection tools) can be detected and placed but may not execute via PostCommand — they use pyRevit's internal execution engine
- **Some OOTB Revit tools** with dropdown/list button CommandIds (e.g. `ID_OBJECTS_WALL_RibbonListButton`) are filtered out automatically
- **UIState persistence** — Revit saves ribbon state to UIState.dat on session close, which can interfere with tab visibility between sessions
- **Locked files during update** — icons loaded by Revit (PNGs) are skipped during update and overwritten on next restart
- **Panel ordering** — `bundle.yaml` controls RST tab panel order; custom profile tab panel order follows the profile JSON
- **Tab persistence** — custom tabs built via AdWindows don't survive Revit restart; `startup.py` rebuilds on every launch

> **WARNING: DISABLING EXTENSIONS IS UNTESTED. THIS FEATURE MAY CAUSE ISSUES WITH YOUR REVIT INSTALLATION. USE AT YOUR OWN RISK.**

---

## Add-in Lookup

RST maps Revit ribbon tab names to `.addin` filenames so it can check presence, suppress, and restore add-ins. This mapping lives in a single file:

```
lookup/addin_lookup.json
```

Both UIs (Profiler and Loader) and the Python backend read from this file. The format is:

```json
{
  "TabName": { "displayName": "Human-readable Name", "file": "Filename.addin" }
}
```

**Adding entries:** If your firm uses add-ins not in the default list, you can add them to `addin_lookup.json`. Find the `.addin` filename in `%APPDATA%\Autodesk\Revit\Addins\{version}\` and the ribbon tab name it creates in Revit. Add an entry mapping the tab name to the file. Changes take effect the next time you open the Profiler or Loader.

Add-ins not in the lookup will show as "Unknown" in the UI. RST will still attempt a fuzzy match by searching `.addin` file names and contents at load time, but an explicit entry is more reliable.

> **Editing this file is at your own risk.** Invalid JSON will prevent add-in detection from working. Back up the file before making changes.

---

## Protected Add-ins & Exempt Paths

Configured in `lookup/config.json`:

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

**`protected_addins`** — these `.addin` files are never renamed, disabled, or touched by RST. Add any filenames your firm needs to keep safe.

**`exempt_paths`** — entire directories RST will never modify. Files under these paths are skipped during disable, restore, and hide operations. Supports environment variables (`%APPDATA%`, `%PROGRAMFILES%`, etc.).

Defaults ship with pyRevit, Kinship, and Dynamo protected. Edit `config.json` to add your own entries.

---

## Tech Stack

- **pyRevit** — extension framework, ribbon buttons, startup hooks
- **IronPython** — Revit-side scripts (tab scanning, ribbon building, panel styling)
- **CPython 3.12** — UI windows via pywebview
- **AdWindows.dll** — Revit ribbon manipulation (scan tools, build panels, set colors, rounded corners)
- **WPF** — ImageBrush for branding, DrawingBrush for rounded panel backgrounds
- **pywebview** — HTML-based UI windows for Profiler and Loader

---

## Links

- [CONNECTIONS.md](CONNECTIONS.md) — file map, API reference, data flow
- Author: [Designs/OS](https://github.com/jedbjorn)
