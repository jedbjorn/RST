# -*- coding: utf-8 -*-
import os
import json
from logger import get_logger

log = get_logger('addin_scanner')

PROTECTED_ADDINS = {'pyRevit.addin'}

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_lookup_path = os.path.join(_root, 'lookup', 'addin_lookup.json')
_overrides_path = os.path.join(_root, 'app', 'user_addin_overrides.json')


def load_addin_lookup():
    with open(_lookup_path, 'r') as f:
        return json.load(f)


def _load_overrides():
    if os.path.exists(_overrides_path):
        with open(_overrides_path, 'r') as f:
            return json.load(f)
    return {}


def _save_overrides(overrides):
    with open(_overrides_path, 'w') as f:
        json.dump(overrides, f, indent=2)


def _record_fuzzy_match(tab_name, filename):
    log.info('Fuzzy match: %s -> %s', tab_name, filename)
    overrides = _load_overrides()
    overrides[tab_name] = filename
    _save_overrides(overrides)


def _get_appdata():
    """Get APPDATA path, return None on non-Windows."""
    return os.environ.get('APPDATA')


def get_addins_dir(revit_version):
    appdata = _get_appdata()
    if not appdata:
        log.warning('APPDATA not set — not a Windows environment')
        return None
    return os.path.join(appdata, 'Autodesk', 'Revit', 'Addins', str(revit_version))


def get_installed_revit_versions():
    appdata = _get_appdata()
    if not appdata:
        log.warning('APPDATA not set — cannot scan for Revit versions')
        return []
    addins_root = os.path.join(appdata, 'Autodesk', 'Revit', 'Addins')
    if not os.path.isdir(addins_root):
        log.warning('Revit Addins dir not found: %s', addins_root)
        return []
    versions = []
    for d in os.listdir(addins_root):
        if d.isdigit() and os.path.isdir(os.path.join(addins_root, d)):
            versions.append(d)
    log.info('Installed Revit versions: %s', versions)
    return sorted(versions)


def _fuzzy_find(tab_name, addins_dir):
    """Check overrides first, then fuzzy-match against .addin filenames."""
    overrides = _load_overrides()
    if tab_name in overrides:
        candidate = overrides[tab_name]
        if os.path.exists(os.path.join(addins_dir, candidate)):
            return candidate

    for f in os.listdir(addins_dir):
        if f.endswith('.addin') and tab_name.lower() in f.lower():
            _record_fuzzy_match(tab_name, f)
            return f
    return None


def check_addins(required_addins, revit_version):
    """Returns dict: { tabName: 'present' | 'missing' | 'unknown' }"""
    log.info('Checking addins for Revit %s: %s', revit_version, required_addins)
    lookup = load_addin_lookup()
    addins_dir = get_addins_dir(revit_version)
    if not addins_dir or not os.path.isdir(addins_dir):
        log.warning('Addins dir not found: %s', addins_dir)
        return {name: 'unknown' for name in required_addins}

    installed_files = set(os.listdir(addins_dir))
    active_files = {f for f in installed_files if f.endswith('.addin')}
    results = {}

    for tab_name in required_addins:
        entry = lookup.get(tab_name)
        if entry:
            results[tab_name] = 'present' if entry['file'] in active_files else 'missing'
        else:
            match = _fuzzy_find(tab_name, addins_dir)
            if match:
                results[tab_name] = 'present'
            else:
                results[tab_name] = 'unknown'

    log.info('Addin check results: %s', results)
    return results


def apply_hide_rules(hide_rules, revit_version):
    """Rename .addin -> .addin.inactive for each tab in hide_rules."""
    log.info('Applying hide rules for Revit %s: %s', revit_version, hide_rules)
    lookup = load_addin_lookup()
    addins_dir = get_addins_dir(revit_version)
    if not os.path.isdir(addins_dir):
        log.warning('Addins dir not found: %s', addins_dir)
        return

    for tab_name in hide_rules:
        if tab_name == 'pyRevit':
            log.debug('Skipping protected addin: pyRevit')
            continue
        entry = lookup.get(tab_name)
        filename = entry['file'] if entry else _fuzzy_find(tab_name, addins_dir)
        if not filename:
            log.warning('No .addin file found for: %s', tab_name)
            continue
        src = os.path.join(addins_dir, filename)
        dest = src + '.inactive'
        if os.path.exists(src):
            os.rename(src, dest)
            log.info('Hidden: %s -> %s', filename, filename + '.inactive')


def restore_all_addins(revit_version):
    """Rename all .addin.inactive -> .addin (skip pyRevit)."""
    log.info('Restoring all addins for Revit %s', revit_version)
    addins_dir = get_addins_dir(revit_version)
    if not os.path.isdir(addins_dir):
        log.warning('Addins dir not found: %s', addins_dir)
        return

    for f in os.listdir(addins_dir):
        if f.endswith('.addin.inactive') and f not in {p + '.inactive' for p in PROTECTED_ADDINS}:
            src = os.path.join(addins_dir, f)
            dest = src.replace('.addin.inactive', '.addin')
            os.rename(src, dest)
            log.info('Restored: %s', f.replace('.addin.inactive', '.addin'))


def disable_non_required_addins(required_addins, revit_version):
    """Disable all .addin files except required ones and protected ones."""
    log.info('Disabling non-required addins for Revit %s (keeping: %s)', revit_version, required_addins)
    lookup = load_addin_lookup()
    keep_files = {lookup[a]['file'] for a in required_addins if a in lookup}
    keep_files.update(PROTECTED_ADDINS)
    addins_dir = get_addins_dir(revit_version)
    if not os.path.isdir(addins_dir):
        log.warning('Addins dir not found: %s', addins_dir)
        return

    for f in os.listdir(addins_dir):
        if f.endswith('.addin') and f not in keep_files:
            os.rename(
                os.path.join(addins_dir, f),
                os.path.join(addins_dir, f + '.inactive')
            )
            log.info('Disabled: %s', f)
