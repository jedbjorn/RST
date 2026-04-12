# -*- coding: utf-8 -*-
"""
rst_lib.py — Shared library for RST backend modules.

Path constants, utility functions, and profile helpers.
Imported by all app/ modules. Does NOT import logger (avoids circular deps).
"""

import os
import re
import json
import socket
import uuid


# ── Path Constants ────────────────────────────────────────────────────────────

EXT_ROOT            = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILES_DIR        = os.path.join(EXT_ROOT, 'app', 'profiles')
USERS_DIR           = os.path.join(EXT_ROOT, 'app', 'users')
ICONS_DIR           = os.path.join(EXT_ROOT, 'icons')
ICONPACK_DIR        = os.path.join(EXT_ROOT, 'iconpack')
ACTIVE_PROFILE_PATH = os.path.join(EXT_ROOT, 'app', 'active_profile.json')
LOOKUP_DIR          = os.path.join(EXT_ROOT, 'lookup')
DATA_DIR            = os.path.join(EXT_ROOT, 'data')
ADDIN_LOOKUP_PATH   = os.path.join(LOOKUP_DIR, 'addin_lookup.json')
SYSTEM_SCAN_PATH    = os.path.join(DATA_DIR, 'system_scan.json')
HEALTH_SCAN_PATH    = os.path.join(DATA_DIR, 'health_scan.json')
ADDIN_DEFAULTS_PATH = os.path.join(DATA_DIR, 'addin_defaults.json')
CONFIG_PATH         = os.path.join(LOOKUP_DIR, 'config.json')
UI_DIR              = os.path.join(EXT_ROOT, 'ui')


# ── Config-Locked Add-ins ────────────────────────────────────────────────────

def _load_locked_addins():
    """Load locked_addins list from config.json. These are always locked regardless of origin."""
    try:
        with open(CONFIG_PATH, 'r') as f:
            cfg = json.load(f)
        return {a.lower() for a in cfg.get('locked_addins', [])}
    except (IOError, ValueError):
        return set()

_LOCKED_ADDINS = _load_locked_addins()

def _is_config_locked(addin_file):
    """Check if an addin file is in the config locked list."""
    if not addin_file:
        return False
    return addin_file.lower() in _LOCKED_ADDINS


# ── Profile Validation ────────────────────────────────────────────────────────

REQUIRED_PROFILE_FIELDS = {'profile', 'tab', 'min_version', 'exportDate',
                           'requiredAddins', 'hideRules', 'stacks', 'panels'}


def validate_profile(data):
    """Return set of missing required fields, or empty set if valid."""
    return REQUIRED_PROFILE_FIELDS - set(data.keys())


# ── Identity ─────────────────────────────────────────────────────────────────
#
# Standard identity block included in every scan/event JSON.
# Ensures consistent field names and presence across all data capture services.
#
# Fields:
#   windowsUsername  — OS login (DOMAIN\user or local user). Always present.
#   revitUsername    — Set in Revit Options > General > Username. May be empty
#                     if scan runs outside Revit or user never set it.
#   deviceName      — Machine hostname. Always present.
#
# For DB purposes:
#   - revitUsername is the primary key for tying a person across devices/versions.
#   - windowsUsername is the fallback when revitUsername is empty.
#   - deviceName ties machine-specific data (health, programs) to a physical box.
#

def build_identity(revit_username=None):
    """Build a standard identity dict for any scan or event payload.

    Call with revit_username when running inside Revit.
    Call without args when running standalone (Windows-only scan).
    """
    return {
        'windowsUsername': os.environ.get('USERNAME', os.environ.get('USER', '')),
        'revitUsername':   revit_username or '',
        'deviceName':     socket.gethostname(),
    }


# ── Add-in Entry Builder ─────────────────────────────────────────────────────

def build_addin_entry(display_name, tab_name, addin_file, addin_path,
                      assembly_path, scope, enabled, is_protected,
                      origin, lookup_entry=None, addin_id=None):
    """Build a standardized add-in entry dict.

    Single source of truth for the addin object shape used in user configs,
    profile operations, and UI rendering.
    """
    le = lookup_entry or {}
    return {
        'displayName':  display_name,
        'tabName':      tab_name,
        'addinFile':    addin_file,
        'addinPath':    addin_path,
        'assemblyPath': assembly_path,
        'addinId':      addin_id,
        'scope':        scope,
        'elevated':     scope == 'machine',
        'enabled':      enabled,
        'protected':    is_protected or origin == 'autodesk',
        'locked':       origin == 'native' or _is_config_locked(addin_file),
        'origin':       origin,
        'url':          le.get('url', ''),
        'version':      le.get('version'),
        'publisher':    le.get('publisher'),
        'installDate':  le.get('installDate'),
        'sizeKB':       le.get('sizeKB'),
    }


# ── Add-in Name Normalization & Matching ─────────────────────────────────────

# Tokens stripped during normalization (version noise, common suffixes)
_STRIP_TOKENS = {'version', 'beta', 'alpha', 'rc', 'release', 'trial',
                 'for', 'revit', 'suite'}


def normalize_addin_name(name):
    """Normalize an add-in name for fuzzy matching.

    Lowercases, strips numbers, dots, 'v', 'version', 'beta', etc.
    Returns a clean string for comparison.
      'DiRoots Suite v4.2.1' → 'diroots suite'
      'Enscape 3.5.6+45678'  → 'enscape'
    """
    if not name:
        return ''
    s = name.lower()
    # Remove version-like patterns: v1.2.3, 2024, etc.
    s = re.sub(r'v?\d[\d.]*', '', s)
    # Remove special chars
    s = re.sub(r'[.\-_+()\\/:*?"<>|]', ' ', s)
    # Remove noise tokens
    words = [w for w in s.split() if w not in _STRIP_TOKENS]
    return ' '.join(words).strip()


def match_addins(profile_addins, local_addins):
    """Match add-ins from a profile against add-ins on the local machine.

    profile_addins: list of dicts from the profile JSON, each with:
        {tabName, addinId?, addinFile?, displayName?}
    local_addins: dict from user config's 'addins', keyed by name, each with:
        {tabName, addinId?, addinFile?, assemblyPath?, displayName?}

    Returns dict: {profile_tab_name: {match, local_name, method}}
      match:      'found' | 'not_found'
      local_name: key in local_addins that matched, or None
      method:     'name' | 'addinId' | 'dll' | None
    """
    results = {}

    # Build local indexes for fast lookup
    local_by_norm_name = {}   # normalized displayName → local key
    local_by_id = {}          # addinId (GUID) → local key
    local_by_dll = {}         # dll basename → local key

    for local_key, info in local_addins.items():
        # Normalized name index (use displayName, fall back to key)
        norm = normalize_addin_name(info.get('displayName', local_key))
        if norm:
            local_by_norm_name[norm] = local_key

        # Also index by the key itself normalized
        norm_key = normalize_addin_name(local_key)
        if norm_key and norm_key not in local_by_norm_name:
            local_by_norm_name[norm_key] = local_key

        # AddInId index
        aid = info.get('addinId', '')
        if aid:
            local_by_id[aid.lower()] = local_key

        # DLL basename index
        asm = info.get('assemblyPath', '')
        if asm:
            dll_name = os.path.basename(asm).lower()
            if dll_name:
                local_by_dll[dll_name] = local_key

    for paddin in profile_addins:
        p_tab = paddin if isinstance(paddin, str) else paddin.get('tabName', '')
        if not p_tab:
            continue

        p_display = paddin.get('displayName', p_tab) if isinstance(paddin, dict) else p_tab
        p_id = paddin.get('addinId', '') if isinstance(paddin, dict) else ''
        p_file = paddin.get('addinFile', '') if isinstance(paddin, dict) else ''

        matched_key = None
        method = None

        # Tier 1: Normalized name match
        p_norm = normalize_addin_name(p_display)
        if p_norm and p_norm in local_by_norm_name:
            matched_key = local_by_norm_name[p_norm]
            method = 'name'

        # Also try normalizing the tab name itself
        if not matched_key:
            p_norm_tab = normalize_addin_name(p_tab)
            if p_norm_tab and p_norm_tab in local_by_norm_name:
                matched_key = local_by_norm_name[p_norm_tab]
                method = 'name'

        # Tier 2: AddInId (GUID) match
        if not matched_key and p_id:
            if p_id.lower() in local_by_id:
                matched_key = local_by_id[p_id.lower()]
                method = 'addinId'

        # Tier 3: DLL filename match
        if not matched_key and p_file:
            # Try using addinFile as a proxy for DLL name
            dll_guess = p_file.lower().replace('.addin', '.dll')
            if dll_guess in local_by_dll:
                matched_key = local_by_dll[dll_guess]
                method = 'dll'

        results[p_tab] = {
            'match': 'found' if matched_key else 'not_found',
            'local_name': matched_key,
            'method': method,
        }

    return results


# ── Utility Functions ─────────────────────────────────────────────────────────

def safe_filename(s):
    """Sanitize a string for use in filenames."""
    return re.sub(r'[\\/:*?"<>|]', '_', s).strip()


def load_json_safe(path, default=None):
    """Read and parse a JSON file. Returns default on failure."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (IOError, ValueError, UnicodeDecodeError):
        return default


# ── Profile Helpers ───────────────────────────────────────────────────────────

def generate_profile_id():
    return str(uuid.uuid4())


def ensure_profile_id(data):
    """Add a UUID 'id' field if missing."""
    if not data.get('id'):
        data['id'] = generate_profile_id()
    return data


def _find_profile_by(field, value):
    """Scan PROFILES_DIR for a profile where data[field] == value."""
    if not value:
        return None, None
    for fname in os.listdir(PROFILES_DIR):
        if fname.endswith('.json'):
            fpath = os.path.join(PROFILES_DIR, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if data.get(field) == value:
                    return fname, data
            except (json.JSONDecodeError, IOError, UnicodeDecodeError):
                continue
    return None, None


def find_profile(profile_name):
    return _find_profile_by('profile', profile_name)


def find_profile_by_id(profile_id):
    return _find_profile_by('id', profile_id)


def resolve_profile(profile_name, profile_id=None):
    """Find profile by ID first, falling back to name. Returns (filename, data)."""
    fname, data = find_profile_by_id(profile_id)
    if not data:
        fname, data = find_profile(profile_name)
    return fname, data


def get_all_profile_names():
    names = set()
    for fname in os.listdir(PROFILES_DIR):
        if fname.endswith('.json'):
            fpath = os.path.join(PROFILES_DIR, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                name = data.get('profile')
                if name:
                    names.add(name)
            except (json.JSONDecodeError, IOError, UnicodeDecodeError):
                continue
    return names


def get_rst_tab_names():
    """Return set of tab names created by RST profiles. These are not add-ins."""
    tabs = set()
    for fname in os.listdir(PROFILES_DIR):
        if fname.endswith('.json'):
            fpath = os.path.join(PROFILES_DIR, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                tab = data.get('tab')
                if tab:
                    tabs.add(tab)
            except (json.JSONDecodeError, IOError, UnicodeDecodeError):
                continue
    return tabs


def get_active_profile():
    """Return dict with 'id' and 'name' of the active profile, or None."""
    data = load_json_safe(ACTIVE_PROFILE_PATH)
    if not data:
        return None
    return {
        'id': data.get('profile_id'),
        'name': data.get('profile'),
    }


def is_active_profile(profile_id=None, profile_name=None):
    """Check if a profile (by ID or name) is the currently active one.
    Prefers ID match when both the profile and active_profile.json have IDs —
    prevents display-name collisions (e.g. manually duplicated files) from
    highlighting multiple profiles as active."""
    active = get_active_profile()
    if not active:
        return False
    active_id = active.get('id')
    active_name = active.get('name')
    if profile_id and active_id:
        return profile_id == active_id
    if profile_name and active_name:
        return profile_name == active_name
    return False


# ── Profile Scan: Filename Reconciliation + ID Collision Repair ──────────────

import logging as _logging
_scan_log = _logging.getLogger('rst_lib.scan')

_PROFILE_FILENAME_RE = re.compile(r'^(.*)_(\d{4}-\d{2}-\d{2})\.json$')


def _reconcile_display_name(fname, data):
    """If the filename's name portion differs from data['profile'], update
    data['profile'] to match the filename. Returns True if data was modified.

    Handles both convention-following filenames ({name}_{date}.json) and
    user-stripped ones ({name}.json). Compares against safe_filename-
    normalized display name so illegal-char sanitization doesn't trigger
    spurious updates.
    """
    m = _PROFILE_FILENAME_RE.match(fname)
    if m:
        name_from_file = m.group(1)
    else:
        name_from_file = fname[:-5] if fname.endswith('.json') else fname
    current = data.get('profile', '')
    if safe_filename(current) == name_from_file:
        return False
    data['profile'] = name_from_file
    return True


def _repair_id_collisions(entries):
    """entries: list of (fname, fpath, mtime, data) tuples.
    For each duplicated id, oldest mtime keeps the ID; others get fresh
    UUIDs written back to disk."""
    from collections import defaultdict
    by_id = defaultdict(list)
    for item in entries:
        pid = item[3].get('id')
        if pid:
            by_id[pid].append(item)
    for pid, items in by_id.items():
        if len(items) <= 1:
            continue
        items.sort(key=lambda x: x[2])
        keeper = items[0]
        _scan_log.warning('ID collision on %s: %d profiles; keeper=%s',
                          pid, len(items), keeper[0])
        for fname, fpath, _mtime, data in items[1:]:
            old_id = data.get('id')
            data['id'] = generate_profile_id()
            try:
                with open(fpath, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)
                _scan_log.info('Reassigned ID: %s (%s -> %s)',
                               fname, old_id, data['id'])
            except (IOError, OSError) as e:
                _scan_log.error('Failed to rewrite %s: %s', fname, e)


def scan_profiles():
    """Read all profiles from PROFILES_DIR. Apply migrations in order:
      1. Legacy ID assignment (profiles missing 'id')
      2. Filename reconciliation (filename-derived name overrides stale JSON)
      3. Cross-file ID collision repair (oldest keeps; others reassigned)
    Writes changes back to disk. Returns list of profile dicts with
    '_filename' attached."""
    entries = []
    for fname in sorted(os.listdir(PROFILES_DIR)):
        if not fname.endswith('.json'):
            continue
        fpath = os.path.join(PROFILES_DIR, fname)
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (IOError, ValueError, UnicodeDecodeError) as e:
            _scan_log.error('Failed to read profile %s: %s', fname, e)
            continue

        dirty = False
        if not data.get('id'):
            ensure_profile_id(data)
            dirty = True
            _scan_log.info('Assigned ID to legacy profile: %s -> %s',
                           fname, data['id'])

        if _reconcile_display_name(fname, data):
            dirty = True
            _scan_log.info('Reconciled display name from filename: %s -> %s',
                           fname, data['profile'])

        if dirty:
            try:
                with open(fpath, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)
            except (IOError, OSError) as e:
                _scan_log.error('Failed to rewrite %s: %s', fname, e)

        try:
            mtime = os.path.getmtime(fpath)
        except OSError:
            mtime = 0
        entries.append((fname, fpath, mtime, data))

    _repair_id_collisions(entries)

    profiles = []
    for fname, _fpath, _mtime, data in entries:
        data['_filename'] = fname
        profiles.append(data)
    return profiles
