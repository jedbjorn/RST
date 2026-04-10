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

from rst_lib import (
    EXT_ROOT, PROFILES_DIR, ICONS_DIR, ACTIVE_PROFILE_PATH, UI_DIR,
    safe_filename, find_profile, get_all_profile_names, get_active_profile_name,
)
from addin_scanner import (
    load_addin_lookup, get_addins_dirs, _find_all_addin_files,
    resolve_tab_to_addin, restore_all_addins,
)
from user_config import (
    get_current_username,
    load_user_config,
    save_user_config,
    build_user_config,
    write_intent_log,
    clear_intent_log,
)

_html_path = os.path.join(UI_DIR, 'profile_manager.html')
_revit_data_path = os.path.join(EXT_ROOT, 'app', '_revit_data.json')
_custom_tools_path = os.path.join(EXT_ROOT, 'app', 'custom_tools.json')
_panel_colors_path = os.path.join(EXT_ROOT, 'app', 'panel_colors.json')

os.makedirs(PROFILES_DIR, exist_ok=True)
os.makedirs(ICONS_DIR, exist_ok=True)

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


class TabCreatorAPI:

    def __init__(self):
        self._window = None

    def set_window(self, window):
        self._window = window

    def get_addin_lookup(self):
        return load_addin_lookup()

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

    def _get_username(self):
        return _revit_data.get('revit_username') or get_current_username()

    def get_user_config(self):
        """Return user add-in config. Builds on first call."""
        username = self._get_username()
        version = _revit_data.get('revit_version')
        if not version:
            return None
        config = load_user_config(username, version)
        if config is None:
            config = build_user_config(
                username, version,
                _revit_data.get('loaded_addins', []),
                _revit_data.get('all_tabs', []),
                load_addin_lookup(),
            )
            save_user_config(config)
        return config

    def get_disabled_addins(self):
        """Return list of disabled add-ins from user config.
        Used to warn admin at TabCreator launch."""
        config = self.get_user_config()
        if not config:
            return []
        disabled = []
        for name, info in config.get('addins', {}).items():
            if info.get('enabled') is False:
                disabled.append(info)
        log.info('Found %d disabled add-ins in admin config', len(disabled))
        return disabled

    def restore_addins(self):
        """Restore all disabled add-ins. Same behavior as Loader's restore."""
        version = _revit_data.get('revit_version')
        if not version:
            return {'ok': False, 'error': 'No Revit version'}
        try:
            username = get_current_username()
            write_intent_log(username, version, 'restore_all', None, [])
            restored_names = restore_all_addins(version)
            config = build_user_config(
                username, version,
                _revit_data.get('loaded_addins', []),
                _revit_data.get('all_tabs', []),
                load_addin_lookup(),
                _revit_data.get('addin_panels', []),
            )
            save_user_config(config)
            clear_intent_log(username, version)
            return {'ok': True, 'restored': restored_names}
        except Exception as e:
            import traceback
            log.error('Error in restore_addins:\n%s', traceback.format_exc())
            return {'ok': False, 'error': str(e)}

    def get_resolved_addins(self):
        """Cross-reference LoadedApplications against .addin XML files on disk.
        Returns {tabName: {addinFile, assemblyPath, url}}."""
        version = _revit_data.get('revit_version')
        if not version:
            log.warning('No Revit version — cannot resolve add-ins')
            return {}
        loaded = _revit_data.get('loaded_addins', [])
        lookup = load_addin_lookup()
        search_dirs = get_addins_dirs(version)
        fs_addins = _find_all_addin_files(search_dirs)
        resolved = resolve_tab_to_addin(loaded, fs_addins, lookup)
        log.info('Resolved %d add-in mappings for TabCreator', len(resolved))
        return resolved

    def get_custom_tools(self):
        if not os.path.exists(_custom_tools_path):
            return []
        try:
            with open(_custom_tools_path, 'r', encoding='utf-8') as f:
                tools = json.load(f)
            log.info('Loaded %d custom tools', len(tools))
            return tools
        except (json.JSONDecodeError, IOError) as e:
            log.error('Failed to load custom tools: %s', e)
            return []

    def save_custom_tools(self, json_str):
        try:
            tools = json.loads(json_str)
            with open(_custom_tools_path, 'w', encoding='utf-8') as f:
                json.dump(tools, f, indent=2)
            log.info('Saved %d custom tools', len(tools))
            return {'ok': True}
        except Exception as e:
            log.error('Failed to save custom tools: %s', e)
            return {'ok': False, 'error': str(e)}

    def get_panel_colors(self):
        try:
            with open(_panel_colors_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (IOError, json.JSONDecodeError) as e:
            log.error('Failed to load panel_colors.json: %s', e)
            return []

    def save_panel_colors(self, json_str):
        try:
            colors = json.loads(json_str)
            with open(_panel_colors_path, 'w', encoding='utf-8') as f:
                json.dump(colors, f, indent=2)
            log.info('Saved %d panel colors', len(colors))
            return {'ok': True}
        except Exception as e:
            log.error('Failed to save panel colors: %s', e)
            return {'ok': False, 'error': str(e)}

    def save_export(self, json_str):
        log.info('Exporting profile')
        try:
            profile = json.loads(json_str)
        except json.JSONDecodeError as e:
            log.error('Invalid export JSON: %s', e)
            return {'ok': False, 'error': 'Invalid JSON: ' + str(e)}

        try:
            raw_name = profile.get('profile', 'Untitled')
            profile_name = safe_filename(raw_name)
            export_date = safe_filename(profile.get('exportDate', 'unknown'))
            filename = '%s_%s.json' % (profile_name, export_date)

            # Check if a different profile with this name exists
            existing_fname, existing_data = find_profile(raw_name)
            if existing_fname:
                # Check if the active profile has this name (file may be locked by Revit)
                active_name = get_active_profile_name()
                if active_name and active_name == raw_name:
                    log.error('Cannot overwrite active profile: %s', raw_name)
                    return {'ok': False, 'error': 'Cannot overwrite a profile that is currently loaded in Revit. Use a different name.'}
                os.remove(os.path.join(PROFILES_DIR, existing_fname))
                log.info('Overwriting existing: %s', existing_fname)

            dest_path = os.path.join(PROFILES_DIR, filename)
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
            file_types=('Image Files (*.png;*.jpg;*.jpeg)',)
        )
        if not result:
            log.debug('Icon pick cancelled')
            return {'ok': False}

        src_path = result[0] if isinstance(result, (list, tuple)) else result

        # Sanitize stem and handle collisions
        stem = safe_filename(os.path.basename(tool_name))
        while os.path.exists(os.path.join(ICONS_DIR, stem + '_64.png')):
            counter = 1
            while os.path.exists(os.path.join(ICONS_DIR, '%s(%d)_64.png' % (stem, counter))):
                counter += 1
            stem = '%s(%d)' % (stem, counter)

        path_64 = os.path.join(ICONS_DIR, stem + '_64.png')
        path_32 = os.path.join(ICONS_DIR, stem + '_32.png')

        try:
            from PIL import Image
            img = Image.open(src_path).convert('RGBA')
            img.resize((64, 64), Image.LANCZOS).save(path_64, 'PNG')
            img.resize((32, 32), Image.LANCZOS).save(path_32, 'PNG')
            log.info('Icon saved (resized): %s_64.png, %s_32.png', stem, stem)
        except ImportError:
            log.warning('PIL not available — saving raw copy as 64px only')
            shutil.copy2(src_path, path_64)
            shutil.copy2(src_path, path_32)
        except Exception as e:
            log.warning('PIL resize failed — saving raw copy: %s', e)
            shutil.copy2(src_path, path_64)
            shutil.copy2(src_path, path_32)

        return {'ok': True, 'filename': stem}

    def get_profiles(self):
        profiles = []
        for fname in os.listdir(PROFILES_DIR):
            if fname.endswith('.json'):
                try:
                    with open(os.path.join(PROFILES_DIR, fname), 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    profiles.append(data.get('profile', fname))
                except (json.JSONDecodeError, IOError):
                    continue
        log.info('Available profiles: %s', profiles)
        return profiles

    def load_profile_into_editor(self, profile_name):
        log.info('Loading profile into editor: %s', profile_name)
        _, data = find_profile(profile_name)
        if not data:
            log.error('Profile not found: %s', profile_name)
            return None

        # Check if this profile is currently loaded in Revit
        active_name = get_active_profile_name()
        if active_name and active_name == profile_name:
            # Make a copy for editing
            copy_name = profile_name + ' (Copy)'
            # Ensure unique copy name
            existing = get_all_profile_names()
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
        dest_path = os.path.join(ICONS_DIR, 'branding.png')

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
        log.info('Opening profiles folder: %s', PROFILES_DIR)
        subprocess.Popen(['explorer', os.path.normpath(PROFILES_DIR)])
        return {'ok': True}

    def close_window(self):
        log.info('Close requested by UI')
        window = self._window or (webview.windows[0] if webview.windows else None)
        if window:
            window.destroy()


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
        on_top=False,
        js_api=api
    )
    api.set_window(window)
    webview.start()
    log.info('=== TabCreator closed ===')
