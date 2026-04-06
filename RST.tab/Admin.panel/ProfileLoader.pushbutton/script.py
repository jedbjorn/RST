# -*- coding: utf-8 -*-
"""ProfileLoader - PyRevit pushbutton script.
Launches Profile Selector, waits for it to close, then reloads pyRevit.
"""
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
    try:
        from pyrevit.loader import sessionmgr
        sessionmgr.reload()
        log.info('pyRevit reloaded successfully')
    except Exception as e:
        log.error('Failed to reload pyRevit: %s', e)
        try:
            # Fallback: use pyRevit script command
            from pyrevit import script
            script.get_results().newsession = True
        except Exception as e2:
            log.error('Fallback reload also failed: %s', e2)
else:
    log.info('Profile unchanged, no reload needed')
