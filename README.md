# RST

Custom toolbar profile system for Autodesk Revit, built on PyRevit.

Admins create toolbar profiles inside Revit. Users load profiles outside Revit to configure their ribbon and manage add-ins.

---

## Install

### 1. Dependencies

- [pyRevit](https://github.com/pyrevitlabs/pyRevit) (4.8+)
- [Python 3](https://www.python.org/downloads/) — **check "Add Python to PATH" during install**
- pywebview — open PowerShell and run:
  ```powershell
  python -m pip install pywebview
  ```

To verify Python is installed and in PATH, run `python --version` in PowerShell. You should see something like `Python 3.x.x`.

### 2. Add Extension

1. Open Revit
2. pyRevit tab → Extensions → Add Extension
3. Paste this URL:
   ```
   https://github.com/jedbjorn/RESTer
   ```
4. Reload pyRevit

You should see a **RST** tab in the Revit ribbon.

---

## Usage

**Admin (inside Revit):**
Click the **Tab Creator** button in the RST ribbon tab. Build your toolbar profile, then export. The profile saves to the extension and copies to your Desktop for sharing.

**User (outside Revit):**
Run `launch_profile_loader.bat` from the extension folder to open the Profile Selector. Add the profile JSON you received, pick your Revit version, and click Load Profile. Close Revit first.

---

## Links

- [CONNECTIONS.md](CONNECTIONS.md) — full file map and API reference
- [spec/HANDOFF.md](spec/HANDOFF.md) — build spec
