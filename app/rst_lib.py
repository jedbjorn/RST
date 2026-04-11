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
CONFIG_PATH         = os.path.join(LOOKUP_DIR, 'config.json')
UI_DIR              = os.path.join(EXT_ROOT, 'ui')


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
                      origin, lookup_entry=None):
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
        'scope':        scope,
        'elevated':     scope == 'machine',
        'enabled':      enabled,
        'protected':    is_protected,
        'origin':       origin,
        'url':          le.get('url', ''),
        'version':      le.get('version'),
        'publisher':    le.get('publisher'),
        'installDate':  le.get('installDate'),
        'sizeKB':       le.get('sizeKB'),
    }


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
