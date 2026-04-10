# -*- coding: utf-8 -*-
import os
import json
import xml.etree.ElementTree as ET
from logger import get_logger

log = get_logger('addin_scanner')

# Built-in Revit ribbon tabs - these are not add-ins and have no .addin files
BUILTIN_TABS = {
    'Architecture', 'Structure', 'Systems', 'Steel', 'Precast',
    'Insert', 'Annotate', 'Analyze', 'Massing & Site', 'Collaborate',
    'View', 'Manage', 'Modify', 'Add-Ins', 'Create', 'RST',
    'FormIt', 'FormIt Converter', 'eTransmit',
    'Modify | Walls', 'Modify | Floors', 'Modify | Roofs',
    'Modify | Structural Framing', 'Modify | Generic Models',
}

from rst_lib import EXT_ROOT, ADDIN_LOOKUP_PATH, CONFIG_PATH

_overrides_path = os.path.join(EXT_ROOT, 'app', 'user_addin_overrides.json')


def _load_config():
    """Load lookup/config.json. Returns (protected set, autodesk set, exempt_paths list)."""
    protected = {'pyRevit.addin', 'Kinship.addin'}
    autodesk = set()
    exempt = []
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        if 'protected_addins' in cfg:
            protected = set(cfg['protected_addins'])
        if 'autodesk_addins' in cfg:
            autodesk = set(cfg['autodesk_addins'])
        if 'exempt_paths' in cfg:
            exempt = [os.path.normpath(os.path.expandvars(p)) for p in cfg['exempt_paths']]
        log.debug('Config loaded: %d protected, %d autodesk, %d exempt paths',
                  len(protected), len(autodesk), len(exempt))
    except (IOError, ValueError) as e:
        log.warning('Could not load config.json, using defaults: %s', e)
    return protected, autodesk, exempt


PROTECTED_ADDINS, AUTODESK_ADDINS, EXEMPT_PATHS = _load_config()



def load_addin_lookup():
    """Load addin_lookup.json, return empty dict on failure."""
    try:
        with open(ADDIN_LOOKUP_PATH, 'r', encoding='utf-8') as f:
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


def _is_exempt_path(path):
    """Check if a path is under any exempt directory from config."""
    path_lower = os.path.normpath(path).lower()
    for exempt in EXEMPT_PATHS:
        if path_lower.startswith(exempt.lower()):
            return True
    return False


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


def _is_hands_off(path):
    """Check if a path should never be modified (read-only, exempt, or protected)."""
    return _is_readonly_dir(path) or _is_exempt_path(path)


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
    """Recursively find all .addin and .addin.RSTdisabled files across all dirs."""
    addin_files = {}  # filename -> list of full paths
    for base_dir in search_dirs:
        for dirpath, dirnames, filenames in os.walk(base_dir):
            for f in filenames:
                if f.endswith('.addin') or f.endswith('.addin.RSTdisabled'):
                    full_path = os.path.join(dirpath, f)
                    if f not in addin_files:
                        addin_files[f] = []
                    addin_files[f].append(full_path)
    return addin_files


def parse_addin_assemblies(addin_files):
    """Parse .addin XML files and extract Assembly DLL paths.

    Returns dict: {normalized_dll_path: addin_filename}
    Each .addin file can contain multiple <AddIn> elements, each with an
    <Assembly> child pointing to a DLL.
    """
    dll_to_addin = {}
    for fname, paths in addin_files.items():
        if not (fname.endswith('.addin') or fname.endswith('.addin.RSTdisabled')):
            continue
        # Use first path for each filename
        fpath = paths[0]
        try:
            tree = ET.parse(fpath)
            root = tree.getroot()
            for addin_elem in root.iter('AddIn'):
                assembly = addin_elem.findtext('Assembly')
                if assembly:
                    dll_to_addin[os.path.normpath(assembly).lower()] = fname
        except (ET.ParseError, IOError, OSError) as e:
            log.debug('Could not parse %s: %s', fpath, e)
            continue
    log.debug('Parsed assemblies from %d .addin files', len(dll_to_addin))
    return dll_to_addin


def resolve_tab_to_addin(loaded_addins, addin_files, addin_lookup=None):
    """Cross-reference LoadedApplications assembly paths against .addin XML
    to build a definitive tab-name → .addin-filename mapping.

    loaded_addins: list of {name, assembly?, addinId?} from Revit session
    addin_files: result of _find_all_addin_files()
    addin_lookup: optional fallback lookup dict (tab_name → {file, url, ...})

    Returns dict: {tab_name: {addinFile, assemblyPath, url}}
    """
    dll_to_addin = parse_addin_assemblies(addin_files)
    if addin_lookup is None:
        addin_lookup = {}

    resolved = {}
    for entry in (loaded_addins or []):
        tab_name = entry.get('name', '')
        if not tab_name or tab_name in BUILTIN_TABS:
            continue

        assembly = entry.get('assembly', '')
        addin_file = None
        url = ''

        # Primary: match via assembly DLL path
        if assembly:
            norm_assembly = os.path.normpath(assembly).lower()
            addin_file = dll_to_addin.get(norm_assembly)

        # Fallback: addin_lookup.json
        if not addin_file and tab_name in addin_lookup:
            lookup_entry = addin_lookup[tab_name]
            expected = lookup_entry.get('file', '')
            if expected and (expected in addin_files or expected + '.RSTdisabled' in addin_files):
                addin_file = expected
            url = lookup_entry.get('url', '')

        # Fallback: fuzzy filename match
        if not addin_file:
            tab_lower = tab_name.lower()
            for fname in addin_files:
                if tab_lower in fname.lower() and (fname.endswith('.addin') or fname.endswith('.addin.RSTdisabled')):
                    addin_file = fname
                    break

        if not url and tab_name in addin_lookup:
            url = addin_lookup[tab_name].get('url', '')

        # Normalize: strip .RSTdisabled suffix for the canonical filename
        if addin_file and addin_file.endswith('.RSTdisabled'):
            addin_file = addin_file.replace('.addin.RSTdisabled', '.addin')

        resolved[tab_name] = {
            'addinFile': addin_file,
            'assemblyPath': assembly or None,
            'url': url,
        }

    log.info('Resolved %d tab-to-addin mappings (%d via assembly, %d via fallback)',
             len(resolved),
             sum(1 for r in resolved.values() if r['assemblyPath']),
             sum(1 for r in resolved.values() if not r['assemblyPath']))
    return resolved


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


def _fuzzy_find(tab_name, search_dirs, overrides=None, addin_files=None):
    """Check overrides, then filename match, then content search."""
    if overrides is None:
        overrides = _load_overrides()

    if tab_name in overrides:
        cached_path = overrides[tab_name]
        if os.path.exists(cached_path):
            return os.path.basename(cached_path), cached_path

    if addin_files is None:
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
        if entry and entry.get('file') in active_filenames:
            results[tab_name] = 'present'
        else:
            # Fuzzy search: filename match then content search
            fname, fpath = _fuzzy_find(tab_name, search_dirs, overrides, addin_files)
            if fname:
                results[tab_name] = 'present'
            elif entry:
                results[tab_name] = 'missing'
            else:
                results[tab_name] = 'unknown'

    log.info('Addin check results: %s', results)
    return results


def apply_hide_rules(hide_rules, revit_version):
    """Rename .addin -> .addin.RSTdisabled for each tab in hide_rules.
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
        if entry and entry.get('file') in addin_files:
            paths = addin_files[entry.get('file')]
            resolved_filename = entry.get('file')
            # Pick first modifiable path
            fpath = next((p for p in paths if not _is_hands_off(p)), None)
        else:
            resolved_filename, fpath = _fuzzy_find(tab_name, search_dirs, overrides, addin_files)

        # Check protection by filename
        if resolved_filename and resolved_filename in PROTECTED_ADDINS:
            log.debug('Skipping protected addin: %s', resolved_filename)
            continue

        if not fpath:
            log.warning('No .addin file found for: %s', tab_name)
            continue

        if _is_hands_off(fpath):
            log.debug('Skipping protected/exempt path: %s', fpath)
            continue

        dest = fpath + '.RSTdisabled'
        if os.path.exists(fpath) and not fpath.endswith('.RSTdisabled'):
            try:
                os.rename(fpath, dest)
                log.info('Hidden: %s', fpath)
            except (OSError, IOError) as e:
                log.error('Failed to hide %s: %s', fpath, e)


def restore_all_addins(revit_version):
    """Sweep all addins directories for .addin.RSTdisabled and rename back to .addin.
    Config-independent — purely filesystem-based recovery."""
    log.info('Restoring all RST-disabled addins for Revit %s', revit_version)
    search_dirs = get_addins_dirs(revit_version)
    restored = 0

    for base_dir in search_dirs:
        if not os.path.isdir(base_dir):
            continue
        for f in os.listdir(base_dir):
            if f.endswith('.addin.RSTdisabled'):
                src = os.path.join(base_dir, f)
                dest = src.replace('.addin.RSTdisabled', '.addin')
                try:
                    os.rename(src, dest)
                    restored += 1
                    log.info('Restored: %s', dest)
                except (OSError, IOError) as e:
                    log.error('Failed to restore %s: %s', src, e)

    log.info('Restored %d add-ins', restored)


def disable_non_required_addins(required_addins, revit_version):
    """Disable all .addin files except required and protected (skip Program Files)."""
    log.info('Disabling non-required addins for Revit %s (keeping: %s)', revit_version, required_addins)
    lookup = load_addin_lookup()
    search_dirs = get_addins_dirs(revit_version)
    overrides = _load_overrides()
    addin_files = _find_all_addin_files(search_dirs)

    # Build set of filenames to keep
    keep_files = set()
    for a in required_addins:
        if a in lookup:
            keep_files.add(lookup[a]['file'])
        else:
            # Resolve fuzzy-matched addins too
            fname, _ = _fuzzy_find(a, search_dirs, overrides, addin_files)
            if fname:
                keep_files.add(fname)
    keep_files.update(PROTECTED_ADDINS)

    for base_dir in search_dirs:
        if _is_hands_off(base_dir):
            continue
        for dirpath, dirnames, filenames in os.walk(base_dir):
            if _is_exempt_path(dirpath):
                continue
            for f in filenames:
                if f.endswith('.addin') and f not in keep_files:
                    src = os.path.join(dirpath, f)
                    try:
                        os.rename(src, src + '.RSTdisabled')
                        log.info('Disabled: %s', src)
                    except (OSError, IOError) as e:
                        log.error('Failed to disable %s: %s', src, e)
