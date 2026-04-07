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

_loaded_addins = []
try:
    app = __revit__.Application
    for a in app.LoadedApplications:
        try:
            name = str(a.Name) if hasattr(a, 'Name') and a.Name else ''
            addin_id = ''
            try:
                addin_id = str(a.AddInId) if hasattr(a, 'AddInId') else ''
            except Exception:
                pass
            assembly = ''
            try:
                if hasattr(a, 'Assembly') and a.Assembly:
                    assembly = str(a.Assembly.Location) if a.Assembly.Location else ''
            except Exception:
                pass
            _loaded_addins.append({
                'name': name,
                'addinId': addin_id,
                'assembly': assembly,
            })
        except Exception:
            continue
except Exception as e:
    log.warning('Could not read LoadedApplications: %s', e)

log.info('Revit %s, %d loaded add-ins', _revit_version, len(_loaded_addins))

# Write session data for CPython to read
_loader_data_path = os.path.join(_root, 'app', '_loader_data.json')
with io.open(_loader_data_path, 'w', encoding='utf-8') as f:
    json.dump({
        'revit_version': _revit_version,
        'loaded_addins': _loaded_addins,
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
