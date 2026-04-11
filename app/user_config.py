# -*- coding: utf-8 -*-
"""
user_config.py — Per-user add-in config persistence and intent logging.

Each Revit user + version gets their own config file tracking add-in
scan results and enabled/disabled state. Intent logs record planned
rename operations for crash recovery.

Files live in app/users/:
  {username}_{version}_addins.json   — scan data + state
  {username}_{version}_intent.json   — pre-rename plan
"""

import os
import json
import datetime

from logger import get_logger

log = get_logger('user_config')

from rst_lib import USERS_DIR as _USERS_DIR, build_addin_entry


def _ensure_users_dir():
    """Create the users directory if it doesn't exist."""
    if not os.path.isdir(_USERS_DIR):
        try:
            os.makedirs(_USERS_DIR)
            log.info('Created users directory: %s', _USERS_DIR)
        except OSError as e:
            log.error('Failed to create users directory: %s', e)


def _config_path(username, version):
    """Return path to the user's add-in config file."""
    return os.path.join(_USERS_DIR, '%s_%s_addins.json' % (username, version))


def _intent_path(username, version):
    """Return path to the user's intent log file."""
    return os.path.join(_USERS_DIR, '%s_%s_intent.json' % (username, version))


def _atomic_write(path, data):
    """Write JSON atomically: write to .tmp then replace."""
    _ensure_users_dir()
    tmp_path = path + '.tmp'
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        # os.replace is atomic on NTFS (Windows target platform)
        os.replace(tmp_path, path)
    except (IOError, OSError) as e:
        log.error('Atomic write failed for %s: %s', path, e)
        # Clean up temp file if it exists
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        raise


def get_current_username():
    """Get the current OS username as fallback when Revit username unavailable."""
    return os.environ.get('USERNAME', os.environ.get('USER', 'unknown'))


# ── User Config ──────────────────────────────────────────────────────────────


def load_user_config(username, version):
    """Load user config. Returns None if missing or username mismatch."""
    path = _config_path(username, version)
    if not os.path.exists(path):
        log.debug('No config file for %s / Revit %s', username, version)
        return None

    try:
        with open(path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except (IOError, ValueError) as e:
        log.error('Failed to read config %s: %s', path, e)
        return None

    # Username mismatch triggers rescan
    if config.get('username') != username:
        log.info('Username mismatch in config (got %s, expected %s) — rescan needed',
                 config.get('username'), username)
        return None

    return config


def save_user_config(config):
    """Persist user config atomically."""
    username = config.get('username', 'unknown')
    version = config.get('revitVersion', 'unknown')
    path = _config_path(username, version)
    _atomic_write(path, config)
    log.info('Saved user config: %s', path)


def save_addin_defaults(config):
    """Write addin defaults snapshot to data/addin_scan.json.

    On first build: sets locked/protected defaults from origin classification.
    On rescan (JSON exists): preserves admin-edited locked/protected values,
    only updates scan metadata (origin, version, publisher, etc.) and adds
    new add-ins with defaults.
    """
    from rst_lib import ADDIN_DEFAULTS_PATH, load_json_safe
    addins = config.get('addins', {})

    # Load existing defaults to preserve admin edits
    existing_data = load_json_safe(ADDIN_DEFAULTS_PATH, {})
    existing = existing_data.get('addins', {})

    defaults = {}
    for name, info in addins.items():
        entry = {
            'displayName': info.get('displayName', name),
            'origin':      info.get('origin', ''),
            'addinFile':   info.get('addinFile'),
            'addinId':     info.get('addinId'),
            'assemblyPath': info.get('assemblyPath'),
            'publisher':   info.get('publisher'),
            'version':     info.get('version'),
        }

        if name in existing:
            # Preserve admin-edited locked/protected
            entry['locked'] = existing[name].get('locked', info.get('locked', False))
            entry['protected'] = existing[name].get('protected', info.get('protected', False))
        else:
            # New add-in — use origin-derived defaults
            entry['locked'] = info.get('locked', False)
            entry['protected'] = info.get('protected', False)

        defaults[name] = entry

    os.makedirs(os.path.dirname(ADDIN_DEFAULTS_PATH), exist_ok=True)
    data = {
        'scanDate': config.get('scanDate', ''),
        'revitVersion': config.get('revitVersion', ''),
        'addinCount': len(defaults),
        'addins': defaults,
    }
    _atomic_write(ADDIN_DEFAULTS_PATH, data)
    log.info('Saved addin defaults: %s (%d add-ins, %d preserved)',
             ADDIN_DEFAULTS_PATH, len(defaults), len(existing))


def needs_rescan(username, version):
    """Check if a rescan is needed (config missing or username mismatch)."""
    return load_user_config(username, version) is None


def _list_addins_dirs(version):
    """List .addin files from user-scope and machine-scope addins directories.
    Returns {filename_lower: full_path}. Recursive — walks subdirectories to find
    add-ins installed in vendor subfolders (e.g. DiRoots/, Enscape/).
    User-scope is checked second so it takes precedence for duplicate filenames."""
    result = {}
    ver = str(version)

    def _walk_dir(base_dir):
        if not os.path.isdir(base_dir):
            return 0
        count = 0
        for dirpath, dirnames, filenames in os.walk(base_dir):
            for f in filenames:
                if f.endswith('.addin') or f.endswith('.addin.RSTdisabled'):
                    result[f.lower()] = os.path.join(dirpath, f)
                    count += 1
        return count

    # Machine-scope first (ProgramData) — read-only, for tracking
    programdata = os.environ.get('PROGRAMDATA', r'C:\ProgramData')
    machine_dir = os.path.join(programdata, 'Autodesk', 'Revit', 'Addins', ver)
    machine_count = _walk_dir(machine_dir)
    log.debug('Machine addins dir: %s (%d files)', machine_dir, machine_count)

    # User-scope second (AppData) — overwrites machine entries for same filename
    appdata = os.environ.get('APPDATA', '')
    user_dir = None
    if appdata:
        user_dir = os.path.join(appdata, 'Autodesk', 'Revit', 'Addins', ver)
        user_count = _walk_dir(user_dir)
        log.debug('User addins dir: %s (%d files)', user_dir, user_count)

    # App Store bundles (ApplicationPlugins) — user and machine scope
    if appdata:
        user_plugins = os.path.join(appdata, 'Autodesk', 'ApplicationPlugins')
        plugins_count = _walk_dir(user_plugins)
        log.debug('User ApplicationPlugins: %s (%d files)', user_plugins, plugins_count)
    machine_plugins = os.path.join(programdata, 'Autodesk', 'ApplicationPlugins')
    plugins_count = _walk_dir(machine_plugins)
    log.debug('Machine ApplicationPlugins: %s (%d files)', machine_plugins, plugins_count)

    log.debug('Total addins found: %d', len(result))
    return result, user_dir


def build_user_config(username, version, loaded_addins, all_tabs, addin_lookup,
                      addin_panels=None):
    """
    Build a user config from two fast sources:

    1. Revit session data (loaded_addins, all_tabs, addin_panels) — sub-second, in memory
    2. Flat os.listdir() on user + machine addins directories — sub-second

    addin_panels: third-party panels on built-in tabs (e.g. Kinship on Add-Ins tab).
    No recursive scan. No XML parsing.
    addin_lookup provides display names and URLs as fallback metadata.
    """
    from addin_scanner import BUILTIN_TABS, classify_addin_origin, parse_addin_ids, parse_addin_assemblies, get_addins_dirs, _find_all_addin_files
    from rst_lib import get_rst_tab_names

    log.info('Building user config for %s / Revit %s', username, version)

    # Collect tab names created by RST profiles — these are not add-ins
    rst_tabs = get_rst_tab_names()
    skip_tabs = BUILTIN_TABS | rst_tabs
    if rst_tabs:
        log.debug('RST-managed tabs excluded from scan: %s', rst_tabs)

    # Step 1: list user + machine addins directories
    dir_files, user_addins_dir = _list_addins_dirs(version)

    # Parse AddInIds and assembly-to-addin mappings from .addin XML files
    search_dirs = get_addins_dirs(version)
    all_addin_files = _find_all_addin_files(search_dirs) if search_dirs else {}
    addin_id_map = parse_addin_ids(all_addin_files) if all_addin_files else {}
    dll_to_addin, addin_to_dll = parse_addin_assemblies(all_addin_files) if all_addin_files else ({}, {})

    # Determine scope helper: is this path in user AppData?
    appdata_lower = (os.environ.get('APPDATA', '') or '').lower()

    # Step 2: index loaded_addins by name for quick lookup
    loaded_by_name = {}
    for entry in (loaded_addins or []):
        name = entry.get('name', '')
        if name:
            loaded_by_name[name.lower()] = entry

    # Step 3: build reverse lookup: addin filename → tab name
    file_to_tab = {}
    for tab_name, info in addin_lookup.items():
        fname = info.get('file', '')
        if fname:
            file_to_tab[fname.lower()] = tab_name

    addins = {}

    # Step 4: process tabs from ribbon scan (everything Revit loaded)
    for tab_name in (all_tabs or []):
        if tab_name in skip_tabs:
            continue

        lookup_entry = addin_lookup.get(tab_name, {})
        display_name = lookup_entry.get('displayName', tab_name)
        url = lookup_entry.get('url', '')
        expected_file = lookup_entry.get('file')

        # Get assembly path from session data
        loaded_entry = loaded_by_name.get(tab_name.lower(), {})
        assembly_path = loaded_entry.get('assembly')

        # Resolve addin filename: lookup first, then DLL path from session
        addin_file = expected_file
        if not addin_file and assembly_path:
            norm_assembly = os.path.normpath(assembly_path).lower()
            addin_file = dll_to_addin.get(norm_assembly)

        # Fallback: if no assembly from session, resolve from .addin XML
        if not assembly_path and addin_file:
            assembly_path = addin_to_dll.get(addin_file)

        # Check enabled/disabled state via directory listing
        addin_path = None
        enabled = True
        if addin_file:
            active_key = addin_file.lower()
            disabled_key = (addin_file + '.RSTdisabled').lower()
            if active_key in dir_files:
                addin_path = dir_files[active_key]
                enabled = True
            elif disabled_key in dir_files:
                addin_path = dir_files[disabled_key]
                enabled = False

        is_protected = False  # protection applied by profile, not at scan time
        scope = 'user'
        if addin_path and appdata_lower and not addin_path.lower().startswith(appdata_lower):
            scope = 'machine'

        addin_id = loaded_entry.get('addinId') or addin_id_map.get(addin_file, '')
        addins[tab_name] = build_addin_entry(
            display_name=display_name, tab_name=tab_name,
            addin_file=addin_file, addin_path=addin_path,
            assembly_path=assembly_path, scope=scope, enabled=enabled,
            is_protected=is_protected,
            origin=classify_addin_origin(
                addin_file=addin_file, lookup_entry=lookup_entry,
                assembly_path=assembly_path, tab_name=tab_name),
            lookup_entry=lookup_entry,
            addin_id=addin_id)

    # Step 5: process third-party panels on built-in tabs (e.g. Kinship on Add-Ins)
    for panel_info in (addin_panels or []):
        panel_name = panel_info.get('name', '')
        if not panel_name or panel_name in addins or panel_name in skip_tabs:
            continue

        lookup_entry = addin_lookup.get(panel_name, {})
        display_name = lookup_entry.get('displayName', panel_name)
        url = lookup_entry.get('url', '')
        expected_file = lookup_entry.get('file')
        assembly_path = panel_info.get('assembly')

        # Primary: resolve via assembly DLL path from LoadedApplications
        addin_file = expected_file
        if not addin_file and assembly_path:
            norm_assembly = os.path.normpath(assembly_path).lower()
            addin_file = dll_to_addin.get(norm_assembly)

        # Fallback: if no assembly from session, resolve from .addin XML
        if not assembly_path and addin_file:
            assembly_path = addin_to_dll.get(addin_file)

        # Skip panels with no resolved addin file and no lookup entry —
        # these are native Revit ribbon panels, not third-party add-ins
        if not addin_file and not lookup_entry:
            continue

        addin_path = None
        enabled = True
        if addin_file:
            active_key = addin_file.lower()
            disabled_key = (addin_file + '.RSTdisabled').lower()
            if active_key in dir_files:
                addin_path = dir_files[active_key]
                enabled = True
            elif disabled_key in dir_files:
                addin_path = dir_files[disabled_key]
                enabled = False

        is_protected = False  # protection applied by profile, not at scan time
        scope = 'user'
        if addin_path and appdata_lower and not addin_path.lower().startswith(appdata_lower):
            scope = 'machine'

        addins[panel_name] = build_addin_entry(
            display_name=display_name, tab_name=panel_info.get('sourceTab'),
            addin_file=addin_file, addin_path=addin_path,
            assembly_path=assembly_path, scope=scope, enabled=enabled,
            is_protected=is_protected,
            origin=classify_addin_origin(
                addin_file=addin_file, lookup_entry=lookup_entry,
                assembly_path=assembly_path, tab_name=panel_name),
            lookup_entry=lookup_entry,
            addin_id=addin_id_map.get(addin_file, ''))

    # Step 6: catch any .addin files in the directory not matched to a loaded tab
    matched_files = set()
    for info in addins.values():
        if info['addinFile']:
            matched_files.add(info['addinFile'].lower())
            matched_files.add((info['addinFile'] + '.RSTdisabled').lower())

    for fname_lower, fpath in dir_files.items():
        if fname_lower in matched_files:
            continue

        fname = os.path.basename(fpath)
        canonical = fname.replace('.addin.RSTdisabled', '.addin') if fname.endswith('.RSTdisabled') else fname
        base = canonical.replace('.addin', '')

        if base in addins:
            continue

        tab_from_file = file_to_tab.get(canonical.lower())
        lookup_entry = addin_lookup.get(tab_from_file, {}) if tab_from_file else {}

        scope = 'user'
        if appdata_lower and not fpath.lower().startswith(appdata_lower):
            scope = 'machine'

        dll_path = addin_to_dll.get(canonical)
        addins[base] = build_addin_entry(
            display_name=lookup_entry.get('displayName', base),
            tab_name=tab_from_file, addin_file=canonical,
            addin_path=fpath, assembly_path=dll_path, scope=scope,
            enabled=not fname.endswith('.RSTdisabled'),
            is_protected=False,  # protection applied by profile, not at scan time
            origin=classify_addin_origin(addin_file=canonical, lookup_entry=lookup_entry,
                                         assembly_path=dll_path),
            lookup_entry=lookup_entry,
            addin_id=addin_id_map.get(canonical, ''))

    # Post-process: link add-ins to their loader's assembly path
    for key, info in addins.items():
        if info.get('assemblyPath'):
            continue
        key_compact = key.lower().replace(' ', '')
        # Check other addins for a loader variant
        for other_key, other_info in addins.items():
            if other_key == key:
                continue
            other_compact = other_key.lower().replace(' ', '')
            if other_info.get('assemblyPath') and other_compact.startswith(key_compact) and 'loader' in other_compact:
                info['assemblyPath'] = other_info['assemblyPath']
                break
        if info.get('assemblyPath'):
            continue
        # Check addin_to_dll for a loader .addin file
        for addin_fname, dll_path in addin_to_dll.items():
            fname_compact = addin_fname.lower().replace('.addin', '').replace(' ', '')
            if fname_compact.startswith(key_compact) and 'loader' in fname_compact:
                info['assemblyPath'] = dll_path
                break

    config = {
        'username': username,
        'revitVersion': str(version),
        'scanDate': datetime.date.today().isoformat(),
        'addins': addins,
    }

    log.info('Built config: %d add-ins catalogued', len(addins))
    return config


def append_new_addins(config, loaded_addins, all_tabs, addin_lookup, addin_panels=None):
    """Check current Revit session against config and append any new add-ins.
    Never removes or rebuilds — only adds. Preserves enabled/disabled state."""
    from addin_scanner import BUILTIN_TABS, classify_addin_origin, parse_addin_ids, parse_addin_assemblies, get_addins_dirs, _find_all_addin_files
    from rst_lib import get_rst_tab_names

    existing = config.get('addins', {})
    version = config.get('revitVersion', '')

    # Collect RST-managed tab names
    rst_tabs = get_rst_tab_names()
    skip_tabs = BUILTIN_TABS | rst_tabs

    appdata_lower = (os.environ.get('APPDATA', '') or '').lower()

    # Get current directory listing
    dir_files, _ = _list_addins_dirs(version)

    # Parse AddInIds and assembly mappings from .addin XML files
    search_dirs = get_addins_dirs(version)
    all_addin_files = _find_all_addin_files(search_dirs) if search_dirs else {}
    addin_id_map = parse_addin_ids(all_addin_files) if all_addin_files else {}
    dll_to_addin, addin_to_dll = parse_addin_assemblies(all_addin_files) if all_addin_files else ({}, {})

    # Index loaded_addins by name
    loaded_by_name = {}
    for entry in (loaded_addins or []):
        name = entry.get('name', '')
        if name:
            loaded_by_name[name.lower()] = entry

    added = []

    # Step 1: check tabs from current session
    for tab_name in (all_tabs or []):
        if tab_name in skip_tabs:
            continue
        if tab_name in existing:
            continue

        lookup_entry = addin_lookup.get(tab_name, {})
        display_name = lookup_entry.get('displayName', tab_name)
        url = lookup_entry.get('url', '')
        expected_file = lookup_entry.get('file')

        loaded_entry = loaded_by_name.get(tab_name.lower(), {})
        assembly_path = loaded_entry.get('assembly')

        addin_file = expected_file
        if not addin_file and assembly_path:
            norm_assembly = os.path.normpath(assembly_path).lower()
            addin_file = dll_to_addin.get(norm_assembly)

        # Fallback: if no assembly from session, resolve from .addin XML
        if not assembly_path and addin_file:
            assembly_path = addin_to_dll.get(addin_file)

        addin_path = None
        enabled = True
        if addin_file:
            active_key = addin_file.lower()
            disabled_key = (addin_file + '.RSTdisabled').lower()
            if active_key in dir_files:
                addin_path = dir_files[active_key]
                enabled = True
            elif disabled_key in dir_files:
                addin_path = dir_files[disabled_key]
                enabled = False

        is_protected = False  # protection applied by profile, not at scan time
        scope = 'user'
        if addin_path and appdata_lower and not addin_path.lower().startswith(appdata_lower):
            scope = 'machine'

        existing[tab_name] = build_addin_entry(
            display_name=display_name, tab_name=tab_name,
            addin_file=addin_file, addin_path=addin_path,
            assembly_path=assembly_path, scope=scope, enabled=enabled,
            is_protected=is_protected,
            origin=classify_addin_origin(
                addin_file=addin_file, lookup_entry=lookup_entry,
                assembly_path=assembly_path, tab_name=tab_name),
            lookup_entry=lookup_entry,
            addin_id=loaded_entry.get('addinId') or addin_id_map.get(addin_file, ''))
        added.append(tab_name)

    # Step 2: check third-party panels on built-in tabs
    for panel_info in (addin_panels or []):
        panel_name = panel_info.get('name', '')
        if not panel_name or panel_name in existing or panel_name in skip_tabs:
            continue

        lookup_entry = addin_lookup.get(panel_name, {})
        display_name = lookup_entry.get('displayName', panel_name)
        url = lookup_entry.get('url', '')
        expected_file = lookup_entry.get('file')
        assembly_path = panel_info.get('assembly')

        # Primary: resolve via assembly DLL path from LoadedApplications
        addin_file = expected_file
        if not addin_file and assembly_path:
            norm_assembly = os.path.normpath(assembly_path).lower()
            addin_file = dll_to_addin.get(norm_assembly)

        # Fallback: if no assembly from session, resolve from .addin XML
        if not assembly_path and addin_file:
            assembly_path = addin_to_dll.get(addin_file)

        # Skip panels with no resolved addin file and no lookup entry —
        # these are native Revit ribbon panels, not third-party add-ins
        if not addin_file and not lookup_entry:
            continue

        addin_path = None
        enabled = True
        if addin_file:
            active_key = addin_file.lower()
            disabled_key = (addin_file + '.RSTdisabled').lower()
            if active_key in dir_files:
                addin_path = dir_files[active_key]
                enabled = True
            elif disabled_key in dir_files:
                addin_path = dir_files[disabled_key]
                enabled = False

        is_protected = False  # protection applied by profile, not at scan time
        scope = 'user'
        if addin_path and appdata_lower and not addin_path.lower().startswith(appdata_lower):
            scope = 'machine'

        existing[panel_name] = build_addin_entry(
            display_name=display_name, tab_name=panel_info.get('sourceTab'),
            addin_file=addin_file, addin_path=addin_path,
            assembly_path=assembly_path, scope=scope, enabled=enabled,
            is_protected=is_protected,
            origin=classify_addin_origin(
                addin_file=addin_file, lookup_entry=lookup_entry,
                assembly_path=assembly_path, tab_name=panel_name),
            lookup_entry=lookup_entry,
            addin_id=addin_id_map.get(addin_file, ''))
        added.append(panel_name)

    # Step 3: check directory for new .addin files not matched to any tab
    matched_files = set()
    for info in existing.values():
        if info.get('addinFile'):
            matched_files.add(info['addinFile'].lower())
            matched_files.add((info['addinFile'] + '.RSTdisabled').lower())

    file_to_tab = {}
    for t, info in addin_lookup.items():
        f = info.get('file', '')
        if f:
            file_to_tab[f.lower()] = t

    for fname_lower, fpath in dir_files.items():
        if fname_lower in matched_files:
            continue
        fname = os.path.basename(fpath)
        canonical = fname.replace('.addin.RSTdisabled', '.addin') if fname.endswith('.RSTdisabled') else fname
        base = canonical.replace('.addin', '')
        if base in existing:
            continue

        tab_from_file = file_to_tab.get(canonical.lower())
        lookup_entry = addin_lookup.get(tab_from_file, {}) if tab_from_file else {}

        scope = 'user'
        if appdata_lower and not fpath.lower().startswith(appdata_lower):
            scope = 'machine'

        dll_path = addin_to_dll.get(canonical)
        existing[base] = build_addin_entry(
            display_name=lookup_entry.get('displayName', base),
            tab_name=tab_from_file, addin_file=canonical,
            addin_path=fpath, assembly_path=dll_path, scope=scope,
            enabled=not fname.endswith('.RSTdisabled'),
            is_protected=False,  # protection applied by profile, not at scan time
            origin=classify_addin_origin(addin_file=canonical, lookup_entry=lookup_entry,
                                         assembly_path=dll_path),
            lookup_entry=lookup_entry,
            addin_id=addin_id_map.get(canonical, ''))
        added.append(base)

    # Post-process: link add-ins to their loader's assembly path
    for key, info in existing.items():
        if info.get('assemblyPath'):
            continue
        key_compact = key.lower().replace(' ', '')
        # Check other addins for a loader variant
        for other_key, other_info in existing.items():
            if other_key == key:
                continue
            other_compact = other_key.lower().replace(' ', '')
            if other_info.get('assemblyPath') and other_compact.startswith(key_compact) and 'loader' in other_compact:
                info['assemblyPath'] = other_info['assemblyPath']
                break
        if info.get('assemblyPath'):
            continue
        # Check addin_to_dll for a loader .addin file
        for addin_fname, dll in addin_to_dll.items():
            fname_compact = addin_fname.lower().replace('.addin', '').replace(' ', '')
            if fname_compact.startswith(key_compact) and 'loader' in fname_compact:
                info['assemblyPath'] = dll
                break

    if added:
        config['scanDate'] = datetime.date.today().isoformat()
        log.info('Appended %d new add-ins to config: %s', len(added), added)

    return config, added


def update_addin_states(config, disabled_files, enabled_files):
    """
    Bulk update enabled/disabled state in the config.

    disabled_files: list of .addin filenames that were renamed to .RSTdisabled
    enabled_files: list of .addin filenames that were restored from .RSTdisabled
    """
    disabled_set = set(f.lower() for f in disabled_files)
    enabled_set = set(f.lower() for f in enabled_files)

    for name, info in config.get('addins', {}).items():
        addin_path = info.get('addinPath', '')
        if not addin_path:
            continue
        basename = os.path.basename(addin_path).lower()
        # Strip .RSTdisabled suffix for matching
        clean_basename = basename.replace('.RSTdisabled', '')

        if clean_basename in disabled_set:
            info['enabled'] = False
            # Update path to reflect .RSTdisabled extension
            if not addin_path.endswith('.RSTdisabled'):
                info['addinPath'] = addin_path + '.RSTdisabled'
        elif clean_basename in enabled_set:
            info['enabled'] = True
            # Update path to reflect restored .addin extension
            if addin_path.endswith('.RSTdisabled'):
                info['addinPath'] = addin_path.replace('.addin.RSTdisabled', '.addin')

    return config


# ── Intent Log ───────────────────────────────────────────────────────────────


def write_intent_log(username, version, action, profile_name, planned_ops):
    """
    Write intent log before any rename batch.

    planned_ops: list of {path, from_state, to_state}
    """
    data = {
        'timestamp': datetime.datetime.now().isoformat(),
        'action': action,
        'profile': profile_name,
        'planned': planned_ops,
        'completed': [],
    }
    path = _intent_path(username, version)
    _atomic_write(path, data)
    log.info('Intent log written: action=%s, profile=%s, %d planned ops',
             action, profile_name, len(planned_ops))


def read_intent_log(username, version):
    """Read intent log. Returns dict or None if missing."""
    path = _intent_path(username, version)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (IOError, ValueError) as e:
        log.error('Failed to read intent log %s: %s', path, e)
        return None


def clear_intent_log(username, version):
    """Delete the intent log file."""
    path = _intent_path(username, version)
    if os.path.exists(path):
        try:
            os.remove(path)
            log.info('Intent log cleared: %s', path)
        except OSError as e:
            log.error('Failed to clear intent log %s: %s', path, e)
