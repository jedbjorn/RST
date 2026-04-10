# -*- coding: utf-8 -*-
"""
rst_lib.py — Shared library for RST backend modules.

Path constants, utility functions, and profile helpers.
Imported by all app/ modules. Does NOT import logger (avoids circular deps).
"""

import os
import re
import json


# ── Path Constants ────────────────────────────────────────────────────────────

EXT_ROOT            = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILES_DIR        = os.path.join(EXT_ROOT, 'app', 'profiles')
USERS_DIR           = os.path.join(EXT_ROOT, 'app', 'users')
ICONS_DIR           = os.path.join(EXT_ROOT, 'icons')
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

def find_profile(profile_name):
    """Find a profile by name in PROFILES_DIR. Returns (filename, data) or (None, None)."""
    for fname in os.listdir(PROFILES_DIR):
        if fname.endswith('.json'):
            fpath = os.path.join(PROFILES_DIR, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if data.get('profile') == profile_name:
                    return fname, data
            except (json.JSONDecodeError, IOError, UnicodeDecodeError):
                continue
    return None, None


def get_all_profile_names():
    """Return set of all existing profile names."""
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


def get_active_profile_name():
    """Return the name of the currently loaded profile, or None."""
    if not os.path.exists(ACTIVE_PROFILE_PATH):
        return None
    try:
        with open(ACTIVE_PROFILE_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('profile')
    except (ValueError, IOError):
        return None
