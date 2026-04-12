# -*- coding: utf-8 -*-
"""TabCreator - CPython pywebview app.
Launched by the PyRevit pushbutton script. Reads Revit data from a temp file.
"""
import webview
import os
import sys
import json
import shutil
import subprocess

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

sys.path.insert(0, os.path.join(_root, 'app'))
from logger import get_logger
log = get_logger('tab_creator')

from rst_lib import (
    EXT_ROOT, PROFILES_DIR, ICONS_DIR, ICONPACK_DIR, UI_DIR,
    ACTIVE_PROFILE_PATH,
    safe_filename, resolve_profile,
    is_active_profile, ensure_profile_id,
    scan_profiles,
)
from addin_scanner import (
    load_addin_lookup, get_addins_dirs, _find_all_addin_files,
    resolve_tab_to_addin, restore_all_addins,
)
from user_config import (
    load_user_config,
    save_user_config,
    save_addin_defaults,
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

    def get_addin_defaults(self):
        """Return addin defaults from data/addin_defaults.json.
        Used by profile manager to populate protectedAddins/lockedAddins."""
        from rst_lib import ADDIN_DEFAULTS_PATH, load_json_safe
        data = load_json_safe(ADDIN_DEFAULTS_PATH, {})
        return data.get('addins', {})

    def save_addin_defaults(self, addins):
        """Save admin-edited protection settings back to data/addin_defaults.json.
        Only updates locked/protected fields — preserves all other default data."""
        from rst_lib import ADDIN_DEFAULTS_PATH, load_json_safe
        data = load_json_safe(ADDIN_DEFAULTS_PATH, {})
        existing = data.get('addins', {})

        for name, edits in addins.items():
            if name in existing:
                if 'locked' in edits:
                    existing[name]['locked'] = edits['locked']
                if 'protected' in edits:
                    existing[name]['protected'] = edits['protected']

        data['addins'] = existing
        try:
            tmp = ADDIN_DEFAULTS_PATH + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, ADDIN_DEFAULTS_PATH)
            log.info('Saved admin protection settings to %s', ADDIN_DEFAULTS_PATH)
            return {'ok': True}
        except Exception as e:
            log.error('Failed to save protection settings: %s', e)
            return {'ok': False, 'error': str(e)}

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
        username = _revit_data.get('revit_username')
        if not username:
            log.error('Revit username not available in session data')
        return username

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
            save_addin_defaults(config)
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
            username = self._get_username()
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
            ensure_profile_id(profile)

            raw_name = profile.get('profile', 'Untitled')
            profile_id = profile.get('id')
            profile_name = safe_filename(raw_name)
            export_date = safe_filename(profile.get('exportDate', 'unknown'))
            filename = '%s_%s.json' % (profile_name, export_date)

            active = is_active_profile(profile_id, raw_name)

            existing_fname, _ = resolve_profile(raw_name, profile_id)
            if existing_fname and existing_fname != filename:
                os.remove(os.path.join(PROFILES_DIR, existing_fname))
                log.info('Removed previous filename: %s', existing_fname)
            elif existing_fname:
                log.info('Overwriting existing: %s', existing_fname)

            dest_path = os.path.join(PROFILES_DIR, filename)
            with open(dest_path, 'w', encoding='utf-8') as f:
                json.dump(profile, f, indent=2)
            log.info('Saved to: %s', dest_path)

            # If this was the active profile, update active_profile.json's
            # profile_file pointer so startup.py can find the (possibly renamed)
            # file on next reload. Preserve hidden_tabs / disable_non_required
            # so a re-export doesn't wipe the loader's prior settings.
            if active:
                try:
                    current_active = {}
                    if os.path.exists(ACTIVE_PROFILE_PATH):
                        with open(ACTIVE_PROFILE_PATH, 'r', encoding='utf-8') as f:
                            current_active = json.load(f)
                    current_active['profile'] = raw_name
                    current_active['profile_id'] = profile_id
                    current_active['profile_file'] = filename
                    current_active['tab'] = profile.get('tab', current_active.get('tab', ''))
                    with open(ACTIVE_PROFILE_PATH, 'w', encoding='utf-8') as f:
                        json.dump(current_active, f, indent=2)
                    log.info('Updated active_profile.json pointer → %s', filename)
                except (OSError, ValueError) as e:
                    log.warning('Could not update active_profile.json: %s', e)

            desktop = os.path.join(os.environ.get('USERPROFILE', ''), 'Desktop')
            desktop_path = None
            if os.path.isdir(desktop):
                desktop_path = os.path.join(desktop, filename)
                shutil.copy2(dest_path, desktop_path)
                log.info('Copied to Desktop: %s', desktop_path)

            return {'ok': True, 'path': dest_path, 'desktop_path': desktop_path, 'was_active': active}

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

    _icon_pack_cache = None

    def get_icon_pack(self):
        """Return list of icon pack entries with name and base64 data URI. Cached after first call."""
        if TabCreatorAPI._icon_pack_cache is not None:
            return TabCreatorAPI._icon_pack_cache
        import base64
        icons = []
        if os.path.isdir(ICONPACK_DIR):
            for f in sorted(os.listdir(ICONPACK_DIR)):
                if f.startswith('32_') and f.endswith('.png'):
                    name = f[3:-4]
                    fpath = os.path.join(ICONPACK_DIR, f)
                    try:
                        with open(fpath, 'rb') as img:
                            b64 = base64.b64encode(img.read()).decode('ascii')
                        icons.append({'name': name, 'src': 'data:image/png;base64,' + b64})
                    except IOError:
                        continue
        TabCreatorAPI._icon_pack_cache = icons
        return icons

    def get_profiles(self):
        scanned = scan_profiles()
        profiles = [{'id': p.get('id'), 'name': p.get('profile', p.get('_filename'))}
                    for p in scanned]
        log.info('Available profiles: %d', len(profiles))
        return profiles

    def load_profile_into_editor(self, profile_name, profile_id=None):
        log.info('Loading profile into editor: %s [id=%s]', profile_name, profile_id)
        _, data = resolve_profile(profile_name, profile_id)
        if not data:
            log.error('Profile not found: %s', profile_name)
            return None

        ensure_profile_id(data)

        log.info('Found profile: %s [id=%s]', data.get('profile'), data.get('id'))
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
