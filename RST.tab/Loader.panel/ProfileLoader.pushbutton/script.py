# -*- coding: utf-8 -*-
"""ProfileLoader - PyRevit pushbutton script.
Launches Profile Selector, waits for it to close, then reloads pyRevit.
"""
__title__ = 'Loader'
import io
import os
import sys
import json
import subprocess

_script_dir = os.path.dirname(os.path.abspath(__file__))
_root = os.path.join(_script_dir, '..', '..', '..')
_root = os.path.normpath(_root)

sys.path.insert(0, os.path.join(_root, 'app'))
from logger import get_logger
log = get_logger('profile_loader_btn')

_active_path = os.path.join(_root, 'app', 'active_profile.json')

# Read current profile before launching
old_profile = None
if os.path.exists(_active_path):
    try:
        with io.open(_active_path, 'r', encoding='utf-8') as f:
            old_profile = json.load(f).get('profile')
    except Exception:
        pass

# Collect Revit session data for Profile Selector
_revit_version = None
try:
    _revit_version = str(__revit__.Application.VersionNumber)
except Exception:
    pass

# Collect all ribbon tabs, add-in panels, and loaded add-ins via AdWindows
_loaded_addins = []
_all_tabs = []
_addin_panels = []  # panels on built-in tabs that belong to third-party add-ins
_SKIP_TABS = {'RST'}
_BUILTIN_TABS = {
    'Architecture', 'Structure', 'Systems', 'Steel', 'Precast',
    'Insert', 'Annotate', 'Analyze', 'Massing & Site', 'Collaborate',
    'View', 'Manage', 'Modify', 'Add-Ins', 'Create', 'RST',
    'FormIt', 'FormIt Converter', 'eTransmit',
    'Modify | Walls', 'Modify | Floors', 'Modify | Roofs',
    'Modify | Structural Framing', 'Modify | Generic Models',
}
# Panels on built-in tabs that are Revit-native (not third-party)
_BUILTIN_PANELS = {
    'Align', 'Macros', 'External', 'External Tools',
    'Analysis', 'Selection', 'Visual Programming',
}
try:
    import clr
    clr.AddReference('AdWindows')
    from Autodesk.Windows import ComponentManager
    ribbon = ComponentManager.Ribbon
    if ribbon and ribbon.Tabs:
        seen = set()
        seen_panels = set()
        for tab in ribbon.Tabs:
            try:
                title = str(tab.Title) if tab.Title else ''
                if not title or title in _SKIP_TABS or title in seen:
                    continue
                is_ctx = False
                try:
                    is_ctx = bool(tab.IsContextualTab)
                except Exception:
                    pass
                if is_ctx:
                    continue
                seen.add(title)
                _all_tabs.append(title)
                if title not in _BUILTIN_TABS:
                    _loaded_addins.append({'name': title})
                else:
                    # Scan panels on built-in tabs for third-party add-ins
                    try:
                        if tab.Panels:
                            for panel in tab.Panels:
                                try:
                                    psrc = panel.Source
                                    if psrc is None:
                                        continue
                                    ptitle = str(psrc.Title) if psrc.Title else ''
                                    if ptitle and ptitle not in _BUILTIN_PANELS and ptitle not in _BUILTIN_TABS and ptitle not in _SKIP_TABS and ptitle not in seen_panels:
                                        seen_panels.add(ptitle)
                                        _addin_panels.append({'name': ptitle, 'sourceTab': title})
                                except Exception:
                                    continue
                    except Exception:
                        pass
            except Exception:
                continue
except Exception as e:
    log.warning('Could not scan ribbon for tabs: %s', e)

# Collect LoadedApplications for assembly paths
try:
    _loaded_apps = {}
    # Try multiple API paths — varies by Revit version
    _app_list = None
    if hasattr(__revit__, 'LoadedApplications'):
        _app_list = __revit__.LoadedApplications
    elif hasattr(__revit__, 'Application') and hasattr(__revit__.Application, 'LoadedApplications'):
        _app_list = __revit__.Application.LoadedApplications
    if _app_list is None:
        raise AttributeError('LoadedApplications not found on __revit__ or __revit__.Application')
    for app in _app_list:
        try:
            name = str(app.Name) if hasattr(app, 'Name') else ''
            if name:
                entry = {'name': name}
                if hasattr(app, 'AddInId'):
                    entry['addinId'] = str(app.AddInId)
                if hasattr(app, 'Assembly') and app.Assembly:
                    entry['assembly'] = str(app.Assembly.Location) if hasattr(app.Assembly, 'Location') else ''
                _loaded_apps[name.lower()] = entry
        except Exception:
            continue

    # Merge assembly info into _loaded_addins
    for addin in _loaded_addins:
        key = addin.get('name', '').lower()
        if key in _loaded_apps:
            match = _loaded_apps[key]
            if 'addinId' in match:
                addin['addinId'] = match['addinId']
            if 'assembly' in match:
                addin['assembly'] = match['assembly']
except Exception as e:
    log.warning('Could not scan LoadedApplications: %s', e)

# Get Revit username (Autodesk account name)
_revit_username = None
try:
    _revit_username = str(__revit__.Application.Username)
except Exception:
    pass

log.info('Revit %s, %d tabs, %d loaded add-ins, %d addin panels, username=%s',
         _revit_version, len(_all_tabs), len(_loaded_addins), len(_addin_panels), _revit_username)

# Write session data for CPython to read
_loader_data_path = os.path.join(_root, 'app', '_loader_data.json')
with io.open(_loader_data_path, 'w', encoding='utf-8') as f:
    json.dump({
        'revit_version': _revit_version,
        'revit_username': _revit_username,
        'loaded_addins': _loaded_addins,
        'all_tabs': _all_tabs,
        'addin_panels': _addin_panels,
    }, f)

# Launch Profile Selector and wait
launcher = os.path.join(_root, 'app', 'profile_selector.py')
log.info('Launching Profile Selector: %s', launcher)
CREATE_NO_WINDOW = 0x08000000
proc = subprocess.Popen(['python', launcher], creationflags=CREATE_NO_WINDOW)
proc.wait()
log.info('Profile Selector closed')

# Check if profile changed
new_profile = None
if os.path.exists(_active_path):
    try:
        with io.open(_active_path, 'r', encoding='utf-8') as f:
            new_profile = json.load(f).get('profile')
    except Exception:
        pass

if new_profile != old_profile:
    log.info('Profile changed: %s -> %s, reloading pyRevit...', old_profile, new_profile)
    from reload_ui import reload_with_message
    reload_with_message()
else:
    log.info('Profile unchanged, no reload needed')
