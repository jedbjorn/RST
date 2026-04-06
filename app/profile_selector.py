# -*- coding: utf-8 -*-
import webview
import os
import re
import json
import shutil
import subprocess
import datetime

from logger import get_logger
log = get_logger('profile_selector')

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_profiles_dir = os.path.join(_root, 'app', 'profiles')
_active_profile_path = os.path.join(_root, 'app', 'active_profile.json')
_html_path = os.path.join(_root, 'ui', 'profile_loader.html')

REQUIRED_FIELDS = {'profile', 'tab', 'min_version', 'exportDate', 'requiredAddins', 'hideRules', 'stacks', 'panels'}

os.makedirs(_profiles_dir, exist_ok=True)

import sys
sys.path.insert(0, os.path.join(_root, 'app'))
from addin_scanner import (
    check_addins,
    apply_hide_rules,
    restore_all_addins,
    disable_non_required_addins,
    get_installed_revit_versions,
)

# pywebview file dialog constant
_OPEN_DIALOG = getattr(webview, 'OPEN_DIALOG', None)
if _OPEN_DIALOG is None:
    try:
        _OPEN_DIALOG = webview.FileDialog.OPEN
    except AttributeError:
        _OPEN_DIALOG = 0


def _safe_filename(s):
    """Sanitize a string for use in filenames."""
    return re.sub(r'[\\/:*?"<>|]', '_', s).strip()


def _find_profile(profile_name):
    """Find a profile by name, return (filename, data) or (None, None)."""
    for fname in os.listdir(_profiles_dir):
        if fname.endswith('.json'):
            fpath = os.path.join(_profiles_dir, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if data.get('profile') == profile_name:
                    return fname, data
            except (json.JSONDecodeError, IOError, UnicodeDecodeError):
                continue
    return None, None


class ProfileSelectorAPI:

    def __init__(self):
        self._window = None

    def set_window(self, window):
        self._window = window

    def get_profiles(self):
        log.info('Loading profiles from %s', _profiles_dir)
        profiles = []
        for fname in os.listdir(_profiles_dir):
            if fname.endswith('.json'):
                fpath = os.path.join(_profiles_dir, fname)
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        profile = json.load(f)
                    profile['_filename'] = fname
                    profiles.append(profile)
                except (json.JSONDecodeError, IOError, UnicodeDecodeError) as e:
                    log.error('Failed to read profile %s: %s', fname, e)
                    continue
        log.info('Loaded %d profiles', len(profiles))
        return profiles

    def get_active_profile(self):
        if not os.path.exists(_active_profile_path):
            log.debug('No active_profile.json found')
            return None
        try:
            with open(_active_profile_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            name = data.get('profile')
            log.info('Active profile: %s', name)
            return name
        except (json.JSONDecodeError, IOError) as e:
            log.error('Failed to read active_profile.json: %s', e)
            return None

    def get_revit_versions(self):
        return get_installed_revit_versions()

    def is_revit_running(self):
        try:
            output = subprocess.check_output(
                ['tasklist', '/FI', 'IMAGENAME eq Revit.exe', '/NH'],
                stderr=subprocess.DEVNULL,
                text=True
            )
            running = any(
                line.strip().lower().startswith('revit.exe')
                for line in output.splitlines()
            )
            log.info('Revit running: %s', running)
            return running
        except subprocess.SubprocessError as e:
            log.error('Failed to check Revit process: %s', e)
            return False

    def add_profile(self):
        log.info('Opening file dialog for profile import')
        window = self._window or (webview.windows[0] if webview.windows else None)
        if not window:
            return {'ok': False, 'error': 'No window available'}

        result = window.create_file_dialog(
            _OPEN_DIALOG,
            file_types=('JSON Files (*.json)',)
        )
        if not result:
            log.debug('File dialog cancelled')
            return {'ok': False, 'error': 'cancelled'}

        file_path = result[0] if isinstance(result, (list, tuple)) else result
        log.info('Selected file: %s', file_path)

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                profile = json.load(f)
        except (json.JSONDecodeError, IOError, UnicodeDecodeError) as e:
            log.error('Invalid JSON: %s', e)
            return {'ok': False, 'error': 'Invalid JSON: ' + str(e)}

        missing = REQUIRED_FIELDS - set(profile.keys())
        if missing:
            log.error('Missing required fields: %s', missing)
            return {'ok': False, 'error': 'Missing fields: ' + ', '.join(sorted(missing))}

        safe_name = _safe_filename(profile['profile'])
        safe_date = _safe_filename(profile['exportDate'])
        dest_name = '%s_%s.json' % (safe_name, safe_date)

        # Overwrite existing profile with same name
        existing_fname, _ = _find_profile(profile['profile'])
        if existing_fname:
            os.remove(os.path.join(_profiles_dir, existing_fname))
            log.info('Overwriting existing profile: %s', existing_fname)

        dest_path = os.path.join(_profiles_dir, dest_name)
        shutil.copy2(file_path, dest_path)
        log.info('Profile saved: %s', dest_name)

        profile['_filename'] = dest_name
        return {'ok': True, 'profile': profile}

    def load_profile(self, profile_name, disable_non_required, revit_version=None):
        log.info('Loading profile: %s (disable_non_required=%s, revit=%s)',
                 profile_name, disable_non_required, revit_version)

        profile_filename, profile_data = _find_profile(profile_name)
        if not profile_data:
            log.error('Profile not found: %s', profile_name)
            return {'ok': False, 'warnings': ['Profile not found: ' + profile_name]}

        if not revit_version:
            versions = get_installed_revit_versions()
            revit_version = versions[0] if versions else None

        warnings = []

        if not revit_version:
            warnings.append('No Revit version selected - add-in toggling skipped')
        else:
            # Check required addins
            addin_status = check_addins(profile_data.get('requiredAddins', []), revit_version)
            for name, status in addin_status.items():
                if status == 'missing':
                    warnings.append('Required add-in missing: ' + name)
                elif status == 'unknown':
                    warnings.append('Unknown add-in (not in lookup): ' + name)

            # Apply hide rules and disable non-required (wrapped for safety)
            try:
                apply_hide_rules(profile_data.get('hideRules', []), revit_version)
                if disable_non_required:
                    disable_non_required_addins(
                        profile_data.get('requiredAddins', []), revit_version
                    )
            except Exception as e:
                log.error('Addin operation failed: %s', e)
                warnings.append('Add-in operation failed: ' + str(e))

        # Write active_profile.json
        active = {
            'profile': profile_name,
            'profile_file': profile_filename,
            'loaded_at': datetime.datetime.now().isoformat(),
            'last_built': None,
            'disable_non_required': bool(disable_non_required),
        }
        try:
            with open(_active_profile_path, 'w', encoding='utf-8') as f:
                json.dump(active, f, indent=2)
        except IOError as e:
            log.error('Failed to write active_profile.json: %s', e)
            return {'ok': False, 'warnings': ['Failed to save active profile: ' + str(e)]}

        log.info('Profile loaded: %s (warnings: %s)', profile_name, warnings)
        return {'ok': True, 'warnings': warnings}

    def remove_profile(self, profile_name):
        log.info('Removing profile: %s', profile_name)
        profile_filename, _ = _find_profile(profile_name)
        if not profile_filename:
            log.error('Profile not found for removal: %s', profile_name)
            return {'ok': False, 'error': 'Profile not found'}

        os.remove(os.path.join(_profiles_dir, profile_filename))
        log.info('Deleted: %s', profile_filename)

        # Clear active if it was the active one
        try:
            if os.path.exists(_active_profile_path):
                with open(_active_profile_path, 'r', encoding='utf-8') as f:
                    active = json.load(f)
                if active.get('profile') == profile_name:
                    os.remove(_active_profile_path)
                    log.info('Cleared active_profile.json')
        except (json.JSONDecodeError, IOError) as e:
            log.error('Error checking active profile: %s', e)

        return {'ok': True}

    def unload_profile(self):
        log.info('Unloading active profile')
        if os.path.exists(_active_profile_path):
            os.remove(_active_profile_path)
            log.info('Deleted active_profile.json')
        else:
            log.debug('No active profile to unload')
        return {'ok': True}

    def restore_addins(self, revit_version):
        log.info('Restoring addins for Revit %s', revit_version)
        restore_all_addins(revit_version)
        return {'ok': True}


if __name__ == '__main__':
    log.info('=== RESTer Profile Selector starting ===')
    log.info('HTML path: %s', _html_path)
    log.info('Profiles dir: %s', _profiles_dir)

    api = ProfileSelectorAPI()
    window = webview.create_window(
        'RESTer - Profile Selector',
        url=_html_path,
        width=1350,
        height=850,
        js_api=api
    )
    api.set_window(window)
    webview.start()
    log.info('=== RESTer Profile Selector closed ===')
