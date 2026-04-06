# -*- coding: utf-8 -*-
import os
import re
import json
from logger import get_logger

log = get_logger('addin_scanner')

PROTECTED_ADDINS = {'pyRevit.addin', 'Kinship.addin'}

# Built-in Revit ribbon tabs - these are not add-ins and have no .addin files
BUILTIN_TABS = {
    'Architecture', 'Structure', 'Systems', 'Steel', 'Precast',
    'Insert', 'Annotate', 'Analyze', 'Massing & Site', 'Collaborate',
    'View', 'Manage', 'Modify', 'Add-Ins',
    'Modify | Walls', 'Modify | Floors', 'Modify | Roofs',
    'Modify | Structural Framing', 'Modify | Generic Models',
}

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_lookup_path = os.path.join(_root, 'lookup', 'addin_lookup.json')
_overrides_path = os.path.join(_root, 'app', 'user_addin_overrides.json')


def _safe_filename(s):
    """Sanitize a string for use in filenames."""
    return re.sub(r'[\\/:*?"<>|]', '_', s).strip()


def load_addin_lookup():
    """Load addin_lookup.json, return empty dict on failure."""
    try:
        with open(_lookup_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (IOError, ValueError) as e:
        log.error('Failed to load addin_lookup.json: %s', e)
        return {}


def _load_overrides():
    if os.path.exists(_overrides_path):
        try:
            with open(_overrides_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (IOError, ValueError):
            return {}
    return {}


def _save_overrides(overrides):
    try:
        with open(_overrides_path, 'w', encoding='utf-8') as f:
            json.dump(overrides, f, indent=2)
    except IOError as e:
        log.error('Failed to save overrides: %s', e)


def _record_fuzzy_match(tab_name, addin_path):
    log.info('Fuzzy match: %s -> %s', tab_name, addin_path)
    overrides = _load_overrides()
    overrides[tab_name] = addin_path
    _save_overrides(overrides)


def _get_appdata():
    return os.environ.get('APPDATA')


def _is_readonly_dir(path):
    """Check if a path is under Program Files or ProgramData (never modify)."""
    path_lower = os.path.normpath(path).lower()
    protected = [
        os.environ.get('PROGRAMFILES', r'C:\Program Files'),
        os.environ.get('PROGRAMFILES(X86)', r'C:\Program Files (x86)'),
        os.environ.get('PROGRAMDATA', r'C:\ProgramData'),
    ]
    for d in protected:
        if path_lower.startswith(os.path.normpath(d).lower()):
            return True
    return False


def get_addins_dirs(revit_version):
    """Return all directories where .addin files may live for a given Revit version."""
    dirs = []
    ver = str(revit_version)

    # 1. User addins: %APPDATA%\Autodesk\Revit\Addins\{version}\
    appdata = _get_appdata()
    if appdata:
        user_dir = os.path.join(appdata, 'Autodesk', 'Revit', 'Addins', ver)
        if os.path.isdir(user_dir):
            dirs.append(user_dir)

    # 2. Machine addins: C:\ProgramData\Autodesk\Revit\Addins\{version}\
    programdata = os.environ.get('PROGRAMDATA', r'C:\ProgramData')
    machine_dir = os.path.join(programdata, 'Autodesk', 'Revit', 'Addins', ver)
    if os.path.isdir(machine_dir):
        dirs.append(machine_dir)

    # 3. Revit install folder (read-only scanning, never modify)
    program_files = os.environ.get('PROGRAMFILES', r'C:\Program Files')
    revit_dir = os.path.join(program_files, 'Autodesk', 'Revit ' + ver)
    if os.path.isdir(revit_dir):
        dirs.append(revit_dir)

    log.debug('Addin search dirs for Revit %s: %s', ver, dirs)
    return dirs


def get_addins_dir(revit_version):
    """Return the primary (user) addins dir."""
    appdata = _get_appdata()
    if not appdata:
        return None
    return os.path.join(appdata, 'Autodesk', 'Revit', 'Addins', str(revit_version))


def get_installed_revit_versions():
    versions = set()

    appdata = _get_appdata()
    if appdata:
        addins_root = os.path.join(appdata, 'Autodesk', 'Revit', 'Addins')
        if os.path.isdir(addins_root):
            for d in os.listdir(addins_root):
                if d.isdigit() and 2015 <= int(d) <= 2030:
                    if os.path.isdir(os.path.join(addins_root, d)):
                        versions.add(d)

    programdata = os.environ.get('PROGRAMDATA', r'C:\ProgramData')
    pd_root = os.path.join(programdata, 'Autodesk', 'Revit', 'Addins')
    if os.path.isdir(pd_root):
        for d in os.listdir(pd_root):
            if d.isdigit() and 2015 <= int(d) <= 2030:
                if os.path.isdir(os.path.join(pd_root, d)):
                    versions.add(d)

    program_files = os.environ.get('PROGRAMFILES', r'C:\Program Files')
    if os.path.isdir(program_files):
        for d in os.listdir(program_files):
            if d.startswith('Revit ') and d[6:].isdigit() and 2015 <= int(d[6:]) <= 2030:
                versions.add(d[6:])

    result = sorted(versions)
    log.info('Installed Revit versions: %s', result)
    return result


def _find_all_addin_files(search_dirs):
    """Recursively find all .addin and .addin.inactive files across all dirs."""
    addin_files = {}  # filename -> list of full paths
    for base_dir in search_dirs:
        for dirpath, dirnames, filenames in os.walk(base_dir):
            for f in filenames:
                if f.endswith('.addin') or f.endswith('.addin.inactive'):
                    full_path = os.path.join(dirpath, f)
                    if f not in addin_files:
                        addin_files[f] = []
                    addin_files[f].append(full_path)
    return addin_files


def _search_addin_contents(tab_name, addin_files):
    """Search inside .addin file contents for the tab name string."""
    tab_lower = tab_name.lower()
    for fname, paths in addin_files.items():
        if not fname.endswith('.addin'):
            continue
        for fpath in paths:
            try:
                with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                    contents = f.read().lower()
                if tab_lower in contents:
                    log.info('Content match: "%s" found in %s', tab_name, fpath)
                    return fname, fpath
            except (IOError, OSError):
                continue
    return None, None


def _fuzzy_find(tab_name, search_dirs, overrides=None):
    """Check overrides, then filename match, then content search."""
    if overrides is None:
        overrides = _load_overrides()

    if tab_name in overrides:
        cached_path = overrides[tab_name]
        if os.path.exists(cached_path):
            return os.path.basename(cached_path), cached_path

    addin_files = _find_all_addin_files(search_dirs)

    tab_lower = tab_name.lower()
    for fname, paths in addin_files.items():
        if fname.endswith('.addin') and tab_lower in fname.lower():
            fpath = paths[0]
            _record_fuzzy_match(tab_name, fpath)
            return fname, fpath

    fname, fpath = _search_addin_contents(tab_name, addin_files)
    if fname:
        _record_fuzzy_match(tab_name, fpath)
        return fname, fpath

    return None, None


def check_addins(required_addins, revit_version):
    """Returns dict: { tabName: 'present' | 'missing' | 'unknown' }"""
    log.info('Checking addins for Revit %s: %s', revit_version, required_addins)
    lookup = load_addin_lookup()
    search_dirs = get_addins_dirs(revit_version)
    overrides = _load_overrides()

    if not search_dirs:
        log.warning('No addin directories found for Revit %s', revit_version)
        return dict((name, 'unknown') for name in required_addins)

    addin_files = _find_all_addin_files(search_dirs)
    active_filenames = set(f for f in addin_files.keys() if f.endswith('.addin'))
    log.debug('Found %d unique .addin files: %s', len(active_filenames), sorted(active_filenames))

    results = {}
    for tab_name in required_addins:
        # Built-in Revit tabs are always present
        if tab_name in BUILTIN_TABS:
            results[tab_name] = 'present'
            continue

        entry = lookup.get(tab_name)
        if entry and entry['file'] in active_filenames:
            results[tab_name] = 'present'
        else:
            # Fuzzy search: filename match then content search
            fname, fpath = _fuzzy_find(tab_name, search_dirs, overrides)
            if fname:
                results[tab_name] = 'present'
            elif entry:
                results[tab_name] = 'missing'
            else:
                results[tab_name] = 'unknown'

    log.info('Addin check results: %s', results)
    return results


def apply_hide_rules(hide_rules, revit_version):
    """Rename .addin -> .addin.inactive for each tab in hide_rules.
    Only modifies files in user/ProgramData dirs, never Program Files."""
    log.info('Applying hide rules for Revit %s: %s', revit_version, hide_rules)
    lookup = load_addin_lookup()
    search_dirs = get_addins_dirs(revit_version)
    overrides = _load_overrides()

    if not search_dirs:
        log.warning('No addin directories found')
        return

    addin_files = _find_all_addin_files(search_dirs)

    for tab_name in hide_rules:
        fpath = None
        resolved_filename = None

        entry = lookup.get(tab_name)
        if entry and entry['file'] in addin_files:
            paths = addin_files[entry['file']]
            resolved_filename = entry['file']
            # Pick first non-Program-Files path
            fpath = next((p for p in paths if not _is_readonly_dir(p)), None)
        else:
            resolved_filename, fpath = _fuzzy_find(tab_name, search_dirs, overrides)

        # Check protection by filename
        if resolved_filename and resolved_filename in PROTECTED_ADDINS:
            log.debug('Skipping protected addin: %s', resolved_filename)
            continue

        if not fpath:
            log.warning('No .addin file found for: %s', tab_name)
            continue

        if _is_readonly_dir(fpath):
            log.debug('Skipping Program Files addin: %s', fpath)
            continue

        dest = fpath + '.inactive'
        if os.path.exists(fpath) and not fpath.endswith('.inactive'):
            try:
                os.rename(fpath, dest)
                log.info('Hidden: %s', fpath)
            except (OSError, IOError) as e:
                log.error('Failed to hide %s: %s', fpath, e)


def restore_all_addins(revit_version):
    """Rename all .addin.inactive -> .addin (skip protected, skip Program Files)."""
    log.info('Restoring all addins for Revit %s', revit_version)
    search_dirs = get_addins_dirs(revit_version)

    protected_inactive = set(p + '.inactive' for p in PROTECTED_ADDINS)

    for base_dir in search_dirs:
        if _is_readonly_dir(base_dir):
            continue
        for dirpath, dirnames, filenames in os.walk(base_dir):
            for f in filenames:
                if f.endswith('.addin.inactive') and f not in protected_inactive:
                    src = os.path.join(dirpath, f)
                    dest = src.replace('.addin.inactive', '.addin')
                    try:
                        os.rename(src, dest)
                        log.info('Restored: %s', dest)
                    except (OSError, IOError) as e:
                        log.error('Failed to restore %s: %s', src, e)


def disable_non_required_addins(required_addins, revit_version):
    """Disable all .addin files except required and protected (skip Program Files)."""
    log.info('Disabling non-required addins for Revit %s (keeping: %s)', revit_version, required_addins)
    lookup = load_addin_lookup()
    search_dirs = get_addins_dirs(revit_version)
    overrides = _load_overrides()

    # Build set of filenames to keep
    keep_files = set()
    for a in required_addins:
        if a in lookup:
            keep_files.add(lookup[a]['file'])
        else:
            # Resolve fuzzy-matched addins too
            fname, _ = _fuzzy_find(a, search_dirs, overrides)
            if fname:
                keep_files.add(fname)
    keep_files.update(PROTECTED_ADDINS)

    for base_dir in search_dirs:
        if _is_readonly_dir(base_dir):
            continue
        for dirpath, dirnames, filenames in os.walk(base_dir):
            for f in filenames:
                if f.endswith('.addin') and f not in keep_files:
                    src = os.path.join(dirpath, f)
                    try:
                        os.rename(src, src + '.inactive')
                        log.info('Disabled: %s', src)
                    except (OSError, IOError) as e:
                        log.error('Failed to disable %s: %s', src, e)
