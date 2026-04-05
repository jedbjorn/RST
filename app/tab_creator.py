# -*- coding: utf-8 -*-
"""TabCreator - CPython pywebview app.
Launched by the PyRevit pushbutton script. Reads Revit data from a temp file.
"""
import webview
import os
import re
import sys
import json
import shutil
import subprocess

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

sys.path.insert(0, os.path.join(_root, 'app'))
from logger import get_logger
log = get_logger('tab_creator')

_html_path = os.path.join(_root, 'ui', 'profile_manager.html')
_profiles_dir = os.path.join(_root, 'app', 'profiles')
_icons_dir = os.path.join(_root, 'icons')
_revit_data_path = os.path.join(_root, 'app', '_revit_data.json')

os.makedirs(_profiles_dir, exist_ok=True)
os.makedirs(_icons_dir, exist_ok=True)

# pywebview file dialog constant
_OPEN_DIALOG = getattr(webview, 'OPEN_DIALOG', None)
if _OPEN_DIALOG is None:
    try:
        _OPEN_DIALOG = webview.FileDialog.OPEN
    except AttributeError:
        _OPEN_DIALOG = 0

# Load Revit data collected by IronPython
_revit_data = {}
if os.path.exists(_revit_data_path):
    try:
        with open(_revit_data_path, 'r', encoding='utf-8') as f:
            _revit_data = json.load(f)
        log.info('Loaded Revit data: version=%s, %d commands',
                 _revit_data.get('revit_version'),
                 len(_revit_data.get('commands', [])))
        # Clean up temp file
        try:
            os.remove(_revit_data_path)
        except OSError:
            pass
    except (json.JSONDecodeError, IOError) as e:
        log.error('Failed to read Revit data: %s', e)


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


class TabCreatorAPI:

    def __init__(self):
        self._window = None

    def set_window(self, window):
        self._window = window

    def get_revit_version(self):
        ver = _revit_data.get('revit_version')
        log.info('Revit version: %s', ver)
        return ver

    def get_installed_commands(self):
        commands = _revit_data.get('commands', [])
        log.info('Returning %d commands', len(commands))
        return commands

    def save_export(self, json_str):
        log.info('Exporting profile')
        try:
            profile = json.loads(json_str)
        except json.JSONDecodeError as e:
            log.error('Invalid export JSON: %s', e)
            return {'ok': False, 'error': 'Invalid JSON: ' + str(e)}

        try:
            profile_name = _safe_filename(profile.get('profile', 'Untitled'))
            export_date = _safe_filename(profile.get('exportDate', 'unknown'))
            filename = '%s_%s.json' % (profile_name, export_date)

            # Overwrite existing profile with same name
            existing_fname, _ = _find_profile(profile.get('profile', ''))
            if existing_fname:
                os.remove(os.path.join(_profiles_dir, existing_fname))
                log.info('Overwriting existing: %s', existing_fname)

            dest_path = os.path.join(_profiles_dir, filename)
            with open(dest_path, 'w', encoding='utf-8') as f:
                f.write(json_str)
            log.info('Saved to: %s', dest_path)

            desktop = os.path.join(os.environ.get('USERPROFILE', ''), 'Desktop')
            desktop_path = None
            if os.path.isdir(desktop):
                desktop_path = os.path.join(desktop, filename)
                shutil.copy2(dest_path, desktop_path)
                log.info('Copied to Desktop: %s', desktop_path)

            return {'ok': True, 'path': dest_path, 'desktop_path': desktop_path}

        except Exception as e:
            log.error('Export failed: %s', e)
            import traceback
            log.error(traceback.format_exc())
            return {'ok': False, 'error': str(e)}

    def pick_icon(self, tool_name):
        log.info('Picking icon for tool: %s', tool_name)
        window = self._window or (webview.windows[0] if webview.windows else None)
        if not window:
            return {'ok': False, 'error': 'No window available'}

        result = window.create_file_dialog(
            _OPEN_DIALOG,
            file_types=('PNG Images (*.png)',)
        )
        if not result:
            log.debug('Icon pick cancelled')
            return {'ok': False}

        src_path = result[0] if isinstance(result, (list, tuple)) else result

        # Sanitize and handle collisions
        safe_name = _safe_filename(os.path.basename(tool_name))
        base_name = safe_name + '.png'
        dest_path = os.path.join(_icons_dir, base_name)
        counter = 1
        while os.path.exists(dest_path):
            base_name = '%s(%d).png' % (safe_name, counter)
            dest_path = os.path.join(_icons_dir, base_name)
            counter += 1

        shutil.copy2(src_path, dest_path)
        log.info('Icon saved: %s', base_name)
        return {'ok': True, 'filename': base_name}

    def get_profiles(self):
        profiles = []
        for fname in os.listdir(_profiles_dir):
            if fname.endswith('.json'):
                try:
                    with open(os.path.join(_profiles_dir, fname), 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    profiles.append(data.get('profile', fname))
                except (json.JSONDecodeError, IOError):
                    continue
        log.info('Available profiles: %s', profiles)
        return profiles

    def load_profile_into_editor(self, profile_name):
        log.info('Loading profile into editor: %s', profile_name)
        _, data = _find_profile(profile_name)
        if data:
            log.info('Found profile: %s', profile_name)
            return data
        log.error('Profile not found: %s', profile_name)
        return None

    def open_profiles_folder(self):
        log.info('Opening profiles folder: %s', _profiles_dir)
        subprocess.Popen(['explorer', os.path.normpath(_profiles_dir)])
        return {'ok': True}


if __name__ == '__main__':
    log.info('=== TabCreator starting ===')
    api = TabCreatorAPI()
    window = webview.create_window(
        'RESTer - Tab Creator',
        url=_html_path,
        width=1200,
        height=1000,
        resizable=True,
        on_top=True,
        js_api=api
    )
    api.set_window(window)
    webview.start()
    log.info('=== TabCreator closed ===')
