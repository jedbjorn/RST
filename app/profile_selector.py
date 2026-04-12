# -*- coding: utf-8 -*-
import webview
import os
import json
import datetime

from logger import get_logger
log = get_logger('profile_selector')

from rst_lib import (
    EXT_ROOT, PROFILES_DIR, ACTIVE_PROFILE_PATH, UI_DIR,
    REQUIRED_PROFILE_FIELDS, validate_profile,
    safe_filename, find_profile, resolve_profile,
    ensure_profile_id, is_active_profile, get_active_profile,
    match_addins, scan_profiles,
)

_html_path = os.path.join(UI_DIR, 'profile_loader.html')


def _get_required_tab_names(profile_data):
    """Extract tab name strings from requiredAddins, handling both old (string[])
    and new (object[]) formats."""
    raw = profile_data.get('requiredAddins', [])
    result = []
    for entry in raw:
        if isinstance(entry, dict):
            tab = entry.get('tabName', '')
            if tab:
                result.append(tab)
        elif isinstance(entry, str):
            result.append(entry)
    return result


def _write_blank_profile():
    """Write a blank active profile so startup.py builds an empty RST tab."""
    blank = {
        'profile': 'BlankRST',
        'blank': True,
    }
    with open(ACTIVE_PROFILE_PATH, 'w', encoding='utf-8') as f:
        json.dump(blank, f, indent=2)
    log.info('Wrote blank active profile')


os.makedirs(PROFILES_DIR, exist_ok=True)

import sys
sys.path.insert(0, os.path.join(EXT_ROOT, 'app'))
from addin_scanner import (
    BUILTIN_TABS,
    load_addin_lookup,
    disable_non_required_addins,
    _is_readonly_dir as _is_program_files,
)
from user_config import (
    load_user_config,
    save_user_config,
    save_addin_defaults,
    build_user_config,
    append_new_addins,
    update_addin_states,
    write_intent_log,
    clear_intent_log,
    restore_profile_addins,
)

# Load session data written by the IronPython pushbutton
_loader_data_path = os.path.join(EXT_ROOT, 'app', '_loader_data.json')
_loader_data = {}
if os.path.exists(_loader_data_path):
    try:
        with open(_loader_data_path, 'r', encoding='utf-8') as f:
            _loader_data = json.load(f)
        log.info('Loaded session data: Revit %s, %d add-ins',
                 _loader_data.get('revit_version'),
                 len(_loader_data.get('loaded_addins', [])))
        try:
            os.remove(_loader_data_path)
        except OSError:
            pass
    except (json.JSONDecodeError, IOError) as e:
        log.error('Failed to read loader data: %s', e)

# pywebview file dialog constant
_OPEN_DIALOG = getattr(webview, 'OPEN_DIALOG', None)
if _OPEN_DIALOG is None:
    try:
        _OPEN_DIALOG = webview.FileDialog.OPEN
    except AttributeError:
        _OPEN_DIALOG = 0


class ProfileSelectorAPI:

    def __init__(self, revit_version=None, loaded_addins=None, all_tabs=None, addin_panels=None):
        self._window = None
        self._revit_version = revit_version
        self._loaded_addins = loaded_addins or []
        self._all_tabs = all_tabs or []
        self._addin_panels = addin_panels or []

    def set_window(self, window):
        self._window = window

    def get_revit_version(self):
        return self._revit_version

    def get_loaded_addins(self):
        return self._loaded_addins

    def get_all_tabs(self):
        return self._all_tabs

    def get_addin_lookup(self):
        return load_addin_lookup()

    def _get_username(self):
        """Get the Revit username from session data."""
        username = _loader_data.get('revit_username')
        if not username:
            log.error('Revit username not available in session data')
        return username

    def get_user_config(self):
        """Return user add-in config. Builds on first call, appends new add-ins on subsequent calls."""
        try:
            username = self._get_username()
            version = self._revit_version
            if not version:
                return None

            lookup = load_addin_lookup()
            config = load_user_config(username, version)

            if config is None:
                log.info('No existing config — building user config')
                config = build_user_config(
                    username, version,
                    self._loaded_addins,
                    self._all_tabs,
                    lookup,
                    self._addin_panels,
                )
                save_user_config(config)
                save_addin_defaults(config)
            else:
                # Append any new add-ins from current session
                config, added = append_new_addins(
                    config,
                    self._loaded_addins,
                    self._all_tabs,
                    lookup,
                    self._addin_panels,
                )
                if added:
                    save_user_config(config)
                    save_addin_defaults(config)

            return config
        except Exception as e:
            import traceback
            log.error('Error in get_user_config:\n%s', traceback.format_exc())
            return None

    def get_disable_preview(self, profile_name):
        """Return what would stay active vs be disabled for a profile.
        Used by the confirmation overlay before committing.

        Buckets:
          staying     — kept enabled (required or protected)
          disabling   — will be renamed (user-writable dirs)
          tryDisable  — will be attempted in Program Files; may fail without admin
          skipped     — genuinely unactionable (no addinPath); hidden from UI
        """
        config = self.get_user_config()
        if not config:
            return {'staying': [], 'disabling': [], 'tryDisable': [], 'skipped': [], 'error': 'No config available'}

        _, profile_data = find_profile(profile_name)
        if not profile_data:
            return {'staying': [], 'disabling': [], 'tryDisable': [], 'skipped': [], 'error': 'Profile not found'}

        # The profile's own tab is RST-built — never disable it
        profile_tab = profile_data.get('tab', '')

        # Resolve profile's required and protected add-ins against local machine
        local_addins = config.get('addins', {})
        required_list = profile_data.get('requiredAddins', [])
        protected_list = profile_data.get('protectedAddins', [])

        # Load admin protection settings from addin_defaults.json
        from rst_lib import ADDIN_DEFAULTS_PATH, load_json_safe
        admin_defaults = load_json_safe(ADDIN_DEFAULTS_PATH, {}).get('addins', {})

        # Match required add-ins to local names
        required_results = match_addins(required_list, local_addins)
        required_local = set()
        for tab_name, result in required_results.items():
            if result['local_name']:
                required_local.add(result['local_name'])

        # Match protected add-ins to local names
        protected_entries = [{'tabName': n} if isinstance(n, str) else n for n in protected_list]
        protected_results = match_addins(protected_entries, local_addins)
        protected_local = set()
        for tab_name, result in protected_results.items():
            if result['local_name']:
                protected_local.add(result['local_name'])

        staying = []
        disabling = []
        try_disable = []
        skipped = []

        # Build set of names being acted on so we can suppress related loader entries
        acting_names = set()

        for name, info in local_addins.items():
            if not info.get('enabled', True):
                continue  # already disabled, skip

            tab_name = info.get('tabName', '')

            # Skip the profile's own RST-built tab entirely
            if profile_tab and (tab_name == profile_tab or name == profile_tab):
                continue

            # Check admin protection flags from addin_defaults.json
            admin_entry = admin_defaults.get(name, {})
            if admin_entry.get('locked', False) or info.get('locked', False):
                continue  # system-locked — hidden from all lists

            is_required = name in required_local
            is_protected = name in protected_local or admin_entry.get('protected', False)

            if is_protected or is_required:
                staying.append(info)
            elif not info.get('addinPath'):
                entry = dict(info)
                entry['skipReason'] = 'No file path found — cannot be disabled by RST'
                skipped.append(entry)
            elif _is_program_files(info.get('addinPath', '')):
                try_disable.append(info)
                acting_names.add(name.lower().replace(' ', ''))
            else:
                disabling.append(info)
                acting_names.add(name.lower().replace(' ', ''))

        # Suppress skipped entries whose loader is already being acted on
        # (e.g. "NonicaTab FREE" skipped but "NonicaTabFREELoader" is in tryDisable)
        skipped = [s for s in skipped
                   if not any(d.startswith(s.get('displayName', s.get('tabName', '')).lower().replace(' ', ''))
                             and 'loader' in d
                             for d in acting_names)]

        return {
            'staying': staying,
            'disabling': disabling,
            'tryDisable': try_disable,
            'skipped': skipped,
        }

    def restore_addins(self):
        """Restore all disabled add-ins and update user config."""
        version = self._revit_version
        if not version:
            return {'ok': False, 'error': 'No Revit version'}

        try:
            restored_names = restore_profile_addins(
                self._get_username(), version,
                self._loaded_addins, self._all_tabs,
                load_addin_lookup(), self._addin_panels,
            )
            return {'ok': True, 'restart_needed': True, 'restored': restored_names}
        except Exception as e:
            import traceback
            log.error('Error in restore_addins:\n%s', traceback.format_exc())
            return {'ok': False, 'error': 'Restore failed: ' + str(e)}

    def get_profiles(self):
        log.info('Loading profiles from %s', PROFILES_DIR)
        profiles = scan_profiles()
        log.info('Loaded %d profiles', len(profiles))
        return profiles

    def get_active_profile(self):
        active = get_active_profile()
        if active is None:
            return {'id': None, 'name': None, 'hidden_tabs': [], 'disable_non_required': False}
        log.info('Active profile: %s [%s] (hidden: %d tabs, disable=%s)',
                 active['name'], active['id'],
                 len(active['hidden_tabs']), active['disable_non_required'])
        return active

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

        missing = validate_profile(profile)
        if missing:
            log.error('Missing required fields: %s', missing)
            return {'ok': False, 'error': 'Missing fields: ' + ', '.join(sorted(missing))}

        ensure_profile_id(profile)

        safe_name = safe_filename(profile['profile'])
        safe_date = safe_filename(profile['exportDate'])
        dest_name = '%s_%s.json' % (safe_name, safe_date)

        existing_fname, _ = resolve_profile(profile['profile'], profile['id'])
        if existing_fname:
            os.remove(os.path.join(PROFILES_DIR, existing_fname))
            log.info('Overwriting existing profile: %s', existing_fname)

        dest_path = os.path.join(PROFILES_DIR, dest_name)
        with open(dest_path, 'w', encoding='utf-8') as f:
            json.dump(profile, f, indent=2)
        log.info('Profile saved: %s (id=%s)', dest_name, profile['id'])

        profile['_filename'] = dest_name
        return {'ok': True, 'profile': profile}

    def load_profile(self, profile_name, disable_non_required, revit_version=None, hidden_tabs=None, profile_id=None):
        log.info('Loading profile: %s [id=%s] (disable=%s, hidden_tabs=%s, revit=%s)',
                 profile_name, profile_id, disable_non_required, hidden_tabs, revit_version)
        try:
            return self._load_profile_inner(profile_name, disable_non_required, revit_version, hidden_tabs, profile_id)
        except RecursionError:
            import traceback
            log.error('RecursionError in load_profile:\n%s', traceback.format_exc())
            return {'ok': False, 'warnings': ['Internal error: maximum recursion reached. Check rst.log.']}
        except Exception as e:
            import traceback
            log.error('Unexpected error in load_profile:\n%s', traceback.format_exc())
            return {'ok': False, 'warnings': ['Internal error: ' + str(e)]}

    def _load_profile_inner(self, profile_name, disable_non_required, revit_version=None, hidden_tabs=None, profile_id=None):
        profile_filename, profile_data = resolve_profile(profile_name, profile_id)
        if not profile_data:
            log.error('Profile not found: %s (id=%s)', profile_name, profile_id)
            return {'ok': False, 'warnings': ['Profile not found: ' + profile_name]}
        ensure_profile_id(profile_data)

        if not revit_version:
            revit_version = self._revit_version

        warnings = []

        if not revit_version:
            warnings.append('No Revit version detected — add-in checks will be skipped')
        else:
            # Check required addins against local machine using three-tier matching
            required = profile_data.get('requiredAddins', [])
            config = load_user_config(self._get_username(), revit_version)
            local_addins = config.get('addins', {}) if config else {}

            if required and local_addins:
                # Filter out native entries before matching
                match_list = []
                for entry in required:
                    if isinstance(entry, dict):
                        if entry.get('native'):
                            continue
                        tab_name = entry.get('tabName', '')
                    elif isinstance(entry, str):
                        tab_name = entry
                    else:
                        continue
                    if tab_name and tab_name not in BUILTIN_TABS:
                        match_list.append(entry)

                results = match_addins(match_list, local_addins)
                for tab_name, result in results.items():
                    if result['match'] == 'not_found':
                        ver = revit_version or 'your version'
                        warnings.append(tab_name + ' not found on this machine. Install for Revit ' + str(ver) + ' and retry if needed.')


        # Re-enable disabled required add-ins (only when disable toggle is on —
        # otherwise addin state is managed exclusively via Restore button)
        restart_needed = False
        failed_disables = []
        if disable_non_required and revit_version:
            username = self._get_username()
            config = load_user_config(username, revit_version)
            if config:
                required = set(_get_required_tab_names(profile_data))
                re_enabled = []
                for name, info in config.get('addins', {}).items():
                    if info.get('enabled') is False and info.get('tabName') in required:
                        disabled_path = info.get('addinPath', '')
                        if disabled_path and disabled_path.endswith('.RSTdisabled') and os.path.exists(disabled_path):
                            restored_path = disabled_path.replace('.addin.RSTdisabled', '.addin')
                            try:
                                os.rename(disabled_path, restored_path)
                                info['enabled'] = True
                                info['addinPath'] = restored_path
                                re_enabled.append(name)
                                log.info('Re-enabled required add-in: %s', name)
                            except (OSError, IOError) as e:
                                log.error('Failed to re-enable %s: %s', name, e)
                                warnings.append('Failed to re-enable: ' + name)

                if re_enabled:
                    save_user_config(config)
                    restart_needed = True
                    log.info('Re-enabled %d disabled required add-ins', len(re_enabled))

        # Disable non-required add-ins if requested
        if disable_non_required and revit_version:
            username = self._get_username()
            required = _get_required_tab_names(profile_data)

            # Resolve protected addin filenames from profile
            protected_files = set()
            protected_list = profile_data.get('protectedAddins', [])
            config = load_user_config(username, revit_version)
            if config and protected_list:
                local_addins = config.get('addins', {})
                protected_entries = [{'tabName': n} if isinstance(n, str) else n for n in protected_list]
                prot_results = match_addins(protected_entries, local_addins)
                for _, result in prot_results.items():
                    if result['local_name']:
                        addin_file = local_addins[result['local_name']].get('addinFile', '')
                        if addin_file:
                            protected_files.add(addin_file)

            # Build planned operations list from preview (normal + tryDisable)
            preview = self.get_disable_preview(profile_name)
            planned = []
            plan_sources = preview.get('disabling', []) + preview.get('tryDisable', [])
            for info in plan_sources:
                path = info.get('addinPath', '')
                if path:
                    planned.append({
                        'path': path,
                        'from_state': 'enabled',
                        'to_state': 'disabled',
                    })

            if planned:
                # Write intent log BEFORE any renames
                write_intent_log(username, revit_version, 'disable_unused', profile_name, planned)

                # Perform the renames — pass protected files from profile
                result = disable_non_required_addins(required, revit_version, protected_addins=protected_files) or {}
                failed_paths = set(result.get('failed', []))

                # Map failed paths back to display names from preview (tryDisable mostly)
                for info in plan_sources:
                    if info.get('addinPath') in failed_paths:
                        failed_disables.append({
                            'name': info.get('displayName') or info.get('tabName') or os.path.basename(info.get('addinPath', '')),
                        })

                # Update user config — only mark successfully disabled files
                config = load_user_config(username, revit_version)
                if config:
                    disabled_files = [os.path.basename(p['path']) for p in planned
                                      if p['path'] not in failed_paths]
                    if disabled_files:
                        update_addin_states(config, disabled_files, [])
                        save_user_config(config)

                # Clear intent log on success
                clear_intent_log(username, revit_version)
                if len(planned) - len(failed_paths) > 0:
                    restart_needed = True
                log.info('Disabled %d non-required add-ins (%d failed)',
                         len(planned) - len(failed_paths), len(failed_paths))

        # Write active_profile.json
        active = {
            'profile': profile_data.get('profile', profile_name),
            'profile_id': profile_data.get('id'),
            'profile_file': profile_filename,
            'tab': profile_data.get('tab', ''),
            'loaded_at': datetime.datetime.now().isoformat(),
            'hidden_tabs': hidden_tabs or [],
            'disable_non_required': bool(disable_non_required),
        }
        try:
            with open(ACTIVE_PROFILE_PATH, 'w', encoding='utf-8') as f:
                json.dump(active, f, indent=2)
        except IOError as e:
            log.error('Failed to write active_profile.json: %s', e)
            return {'ok': False, 'warnings': ['Failed to save active profile: ' + str(e)]}

        log.info('Profile loaded: %s (warnings: %s, restart: %s)', profile_name, warnings, restart_needed)
        return {'ok': True, 'warnings': warnings, 'restart_needed': restart_needed,
                'failed_disables': failed_disables}

    def remove_profile(self, profile_name, profile_id=None):
        log.info('Removing profile: %s [id=%s]', profile_name, profile_id)
        profile_filename, _ = resolve_profile(profile_name, profile_id)
        if not profile_filename:
            log.error('Profile not found for removal: %s', profile_name)
            return {'ok': False, 'error': 'Profile not found'}

        os.remove(os.path.join(PROFILES_DIR, profile_filename))
        log.info('Deleted: %s', profile_filename)

        if is_active_profile(profile_id, profile_name):
            _write_blank_profile()
            log.info('Wrote blank profile (deleted profile was active)')

        return {'ok': True}

    def unload_profile(self):
        log.info('Unloading active profile')
        _write_blank_profile()
        return {'ok': True}

    def close_window(self):
        log.info('Close requested by UI')
        window = self._window or (webview.windows[0] if webview.windows else None)
        if window:
            window.destroy()


if __name__ == '__main__':
    _revit_ver = _loader_data.get('revit_version')
    _addins = _loader_data.get('loaded_addins', [])
    _tabs = _loader_data.get('all_tabs', [])
    _panels = _loader_data.get('addin_panels', [])
    log.info('=== RST Profile Selector starting (Revit %s, %d tabs, %d add-ins, %d panels) ===',
             _revit_ver, len(_tabs), len(_addins), len(_panels))

    log.info('HTML path: %s', _html_path)
    log.info('Profiles dir: %s', PROFILES_DIR)

    api = ProfileSelectorAPI(revit_version=_revit_ver, loaded_addins=_addins, all_tabs=_tabs, addin_panels=_panels)
    try:
        import ctypes
        user32 = ctypes.windll.user32
        sw = user32.GetSystemMetrics(0)
        sh = user32.GetSystemMetrics(1)
        wx, wy = (sw - 1400) // 2, (sh - 900) // 2
    except Exception:
        wx, wy = None, None

    window = webview.create_window(
        'RST - Profile Selector',
        url=_html_path,
        width=1450,
        height=900,
        x=wx,
        y=wy,
        js_api=api
    )
    api.set_window(window)
    webview.start()
    log.info('=== RST Profile Selector closed ===')
