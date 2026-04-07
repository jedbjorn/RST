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
_addin_lookup_path = os.path.join(_root, 'lookup', 'addin_lookup.json')

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


_active_profile_path = os.path.join(_root, 'app', 'active_profile.json')


def _get_active_profile_name():
    """Return the name of the currently loaded profile, or None."""
    if not os.path.exists(_active_profile_path):
        return None
    try:
        with open(_active_profile_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('profile')
    except (ValueError, IOError):
        return None


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


def _get_all_profile_names():
    """Return set of all existing profile names."""
    names = set()
    for fname in os.listdir(_profiles_dir):
        if fname.endswith('.json'):
            fpath = os.path.join(_profiles_dir, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                name = data.get('profile')
                if name:
                    names.add(name)
            except (json.JSONDecodeError, IOError, UnicodeDecodeError):
                continue
    return names


class TabCreatorAPI:

    def __init__(self):
        self._window = None

    def set_window(self, window):
        self._window = window

    def get_addin_lookup(self):
        try:
            with open(_addin_lookup_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (IOError, json.JSONDecodeError) as e:
            log.error('Failed to load addin_lookup.json: %s', e)
            return {}

    def get_revit_version(self):
        ver = _revit_data.get('revit_version')
        log.info('Revit version: %s', ver)
        return ver

    def get_installed_commands(self):
        commands = _revit_data.get('commands', [])
        log.info('Returning %d commands', len(commands))
        return commands

    def get_loaded_addins(self):
        addins = _revit_data.get('loaded_addins', [])
        log.info('Returning %d loaded add-ins', len(addins))
        return addins

    def save_export(self, json_str):
        log.info('Exporting profile')
        try:
            profile = json.loads(json_str)
        except json.JSONDecodeError as e:
            log.error('Invalid export JSON: %s', e)
            return {'ok': False, 'error': 'Invalid JSON: ' + str(e)}

        try:
            raw_name = profile.get('profile', 'Untitled')
            profile_name = _safe_filename(raw_name)
            export_date = _safe_filename(profile.get('exportDate', 'unknown'))
            filename = '%s_%s.json' % (profile_name, export_date)

            # Check if a different profile with this name exists
            existing_fname, existing_data = _find_profile(raw_name)
            if existing_fname:
                # Check if the active profile has this name (file may be locked by Revit)
                active_name = _get_active_profile_name()
                if active_name and active_name == raw_name:
                    log.error('Cannot overwrite active profile: %s', raw_name)
                    return {'ok': False, 'error': 'Cannot overwrite a profile that is currently loaded in Revit. Use a different name.'}
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
        if not data:
            log.error('Profile not found: %s', profile_name)
            return None

        # Check if this profile is currently loaded in Revit
        active_name = _get_active_profile_name()
        if active_name and active_name == profile_name:
            # Make a copy for editing
            copy_name = profile_name + ' (Copy)'
            # Ensure unique copy name
            existing = _get_all_profile_names()
            counter = 1
            while copy_name in existing:
                counter += 1
                copy_name = '%s (Copy %d)' % (profile_name, counter)
            data['profile'] = copy_name
            log.info('Profile is active in Revit. Created copy: %s', copy_name)
            return {'_copied': True, '_message': 'Profile currently loaded. A copy has been made for editing.', **data}

        log.info('Found profile: %s', profile_name)
        return data

    def pick_branding_logo(self):
        log.info('Picking branding logo')
        window = self._window or (webview.windows[0] if webview.windows else None)
        if not window:
            return {'ok': False, 'error': 'No window available'}

        result = window.create_file_dialog(
            _OPEN_DIALOG,
            file_types=('Image Files (*.png;*.jpg;*.jpeg)',)
        )
        if not result:
            log.debug('Branding logo pick cancelled')
            return {'ok': False}

        src_path = result[0] if isinstance(result, (list, tuple)) else result
        dest_path = os.path.join(_icons_dir, 'branding.png')

        try:
            from PIL import Image
            img = Image.open(src_path)
            img = img.resize((48, 48), Image.LANCZOS)
            img.save(dest_path, 'PNG')
            log.info('Branding logo saved (resized 48x48): %s', dest_path)
        except ImportError:
            log.info('PIL not available, copying file directly')
            shutil.copy2(src_path, dest_path)
            log.info('Branding logo saved (raw copy): %s', dest_path)
        except Exception as e:
            log.warning('PIL resize failed, copying file directly: %s', e)
            shutil.copy2(src_path, dest_path)
            log.info('Branding logo saved (raw copy): %s', dest_path)

        return {'ok': True}

    def open_profiles_folder(self):
        log.info('Opening profiles folder: %s', _profiles_dir)
        subprocess.Popen(['explorer', os.path.normpath(_profiles_dir)])
        return {'ok': True}


if __name__ == '__main__':
    log.info('=== TabCreator starting ===')
    api = TabCreatorAPI()
    try:
        import ctypes
        user32 = ctypes.windll.user32
        sw = user32.GetSystemMetrics(0)
        sh = user32.GetSystemMetrics(1)
        wx, wy = (sw - 1350) // 2, (sh - 900) // 2
    except Exception:
        wx, wy = None, None

    window = webview.create_window(
        'RST - Tab Creator',
        url=_html_path,
        width=1350,
        height=900,
        x=wx,
        y=wy,
        resizable=True,
        on_top=True,
        js_api=api
    )
    api.set_window(window)
    webview.start()
    log.info('=== TabCreator closed ===')
