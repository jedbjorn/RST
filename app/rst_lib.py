# -*- coding: utf-8 -*-
"""
rst_lib.py — Shared library for RST backend modules.

Path constants, utility functions, and profile helpers.
Imported by all app/ modules. Does NOT import logger (avoids circular deps).
"""

import os
import re
import json
import uuid


# ── Path Constants ────────────────────────────────────────────────────────────

EXT_ROOT            = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILES_DIR        = os.path.join(EXT_ROOT, 'app', 'profiles')
USERS_DIR           = os.path.join(EXT_ROOT, 'app', 'users')
ICONS_DIR           = os.path.join(EXT_ROOT, 'icons')
ICONPACK_DIR        = os.path.join(EXT_ROOT, 'iconpack')
ACTIVE_PROFILE_PATH = os.path.join(EXT_ROOT, 'app', 'active_profile.json')
LOOKUP_DIR          = os.path.join(EXT_ROOT, 'lookup')
ADDIN_LOOKUP_PATH   = os.path.join(LOOKUP_DIR, 'addin_lookup.json')
CONFIG_PATH         = os.path.join(LOOKUP_DIR, 'config.json')
UI_DIR              = os.path.join(EXT_ROOT, 'ui')


# ── Profile Validation ────────────────────────────────────────────────────────

REQUIRED_PROFILE_FIELDS = {'profile', 'tab', 'min_version', 'exportDate',
                           'requiredAddins', 'hideRules', 'stacks', 'panels'}


def validate_profile(data):
    """Return set of missing required fields, or empty set if valid."""
    return REQUIRED_PROFILE_FIELDS - set(data.keys())


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


def get_active_profile():
    """Return dict with 'id' and 'name' of the active profile, or None."""
    data = load_json_safe(ACTIVE_PROFILE_PATH)
    if not data:
        return None
    return {
        'id': data.get('profile_id'),
        'name': data.get('profile'),
    }


def get_active_profile_name():
    active = get_active_profile()
    return active['name'] if active else None


def get_active_profile_id():
    active = get_active_profile()
    return active['id'] if active else None


def is_active_profile(profile_id=None, profile_name=None):
    """Check if a profile (by ID or name) is the currently active one."""
    active = get_active_profile()
    if not active:
        return False
    if profile_id and active['id'] == profile_id:
        return True
    if profile_name and active['name'] == profile_name:
        return True
    return False
