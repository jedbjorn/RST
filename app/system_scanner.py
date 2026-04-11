# -*- coding: utf-8 -*-
"""
system_scanner.py — Windows registry scanner for installed programs.

Scans HKLM Uninstall registry keys to discover all installed software.
Provides a filtered subset of Revit-relevant add-ins that merges with
the static addin_lookup.json, enriching entries with version, publisher,
and URL data from the registry.

Run once per session; results are cached to disk and in memory.
"""

import json
import logging
import os
import socket
from datetime import datetime, timezone

log = logging.getLogger('rst')

# Registry paths for installed programs (64-bit and 32-bit views)
# Registry paths for installed programs
# HKLM covers machine-wide installs; HKCU covers per-user installs
HKLM_UNINSTALL_KEYS = [
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
    r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
]
HKCU_UNINSTALL_KEYS = [
    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
]

# Fields to capture from each registry entry
REGISTRY_FIELDS = [
    "DisplayName",
    "Publisher",
    "DisplayVersion",
    "InstallLocation",
    "URLInfoAbout",
    "HelpLink",
    "InstallDate",
    "EstimatedSize",
]


# ── Full System Scan ─────────────────────────────────────────────────────────

def scan_installed_programs():
    """Read all installed programs from the Windows registry.

    Scans both HKLM (machine-wide) and HKCU (per-user) uninstall keys.
    Returns list of dicts, one per program, with keys from REGISTRY_FIELDS.
    Skips entries without a DisplayName.
    """
    import winreg

    programs = []
    seen = set()

    hives = [
        (winreg.HKEY_LOCAL_MACHINE, HKLM_UNINSTALL_KEYS),
        (winreg.HKEY_CURRENT_USER,  HKCU_UNINSTALL_KEYS),
    ]

    for hive, key_paths in hives:
        for key_path in key_paths:
            try:
                hkey = winreg.OpenKey(hive, key_path)
            except OSError:
                continue

            try:
                i = 0
                while True:
                    try:
                        subkey_name = winreg.EnumKey(hkey, i)
                    except OSError:
                        break
                    i += 1

                    try:
                        subkey = winreg.OpenKey(hkey, subkey_name)
                    except OSError:
                        continue

                    entry = {}
                    try:
                        for field in REGISTRY_FIELDS:
                            try:
                                value, reg_type = winreg.QueryValueEx(subkey, field)
                                if reg_type == winreg.REG_DWORD:
                                    entry[field] = value or 0
                                else:
                                    entry[field] = str(value).strip() if value else ''
                            except OSError:
                                entry[field] = '' if field != 'EstimatedSize' else 0
                    finally:
                        winreg.CloseKey(subkey)

                    name = entry.get('DisplayName', '')
                    if not name:
                        continue

                    # Deduplicate across hives and 64-bit/WOW6432Node
                    dedup_key = (name.lower(), entry.get('DisplayVersion', ''))
                    if dedup_key in seen:
                        continue
                    seen.add(dedup_key)

                    programs.append(entry)
            finally:
                winreg.CloseKey(hkey)

    log.info('Registry scan found %d installed programs', len(programs))
    return programs


# ── Disk Cache ────────────────────────────────────────────────────────────────

def save_scan(programs, path, revit_username=None):
    """Write full scan results to a JSON cache file."""
    from rst_lib import build_identity
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {
        'scanTimestamp': datetime.now(timezone.utc).isoformat(),
        'identity': build_identity(revit_username),
        'programCount': len(programs),
        'programs': programs,
    }
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)
    log.info('Saved system scan to %s (%d programs)', path, len(programs))


def load_cached_scan(path, max_age_hours=24):
    """Load a cached scan if it exists and is fresh enough.

    Returns the programs list, or None if the cache is missing/stale.
    """
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (IOError, ValueError):
        return None

    ts = data.get('scanTimestamp', '')
    if not ts:
        return None

    try:
        scan_time = datetime.fromisoformat(ts)
        age_hours = (datetime.now(timezone.utc) - scan_time).total_seconds() / 3600
        if age_hours > max_age_hours:
            log.info('Cached scan is %.1f hours old (max %d), will rescan',
                     age_hours, max_age_hours)
            return None
    except (ValueError, TypeError):
        return None

    return data.get('programs', [])


# ── Revit Add-in Filtering ───────────────────────────────────────────────────

def filter_revit_addins(programs, static_lookup):
    """Match registry entries to known Revit add-ins and build an enriched lookup.

    programs:       list of dicts from scan_installed_programs()
    static_lookup:  dict from addin_lookup.json {tabName: {displayName, file, url}}

    Returns dict in the same shape as static_lookup, enriched with registry data:
        {tabName: {displayName, file, url, version, publisher, installDate, sizeKB}}
    """
    # Start with static lookup as baseline (copy so we don't mutate the original)
    merged = {}
    for tab_name, info in static_lookup.items():
        merged[tab_name] = {
            'displayName': info.get('displayName', tab_name),
            'file':        info.get('file', ''),
            'url':         info.get('url', ''),
            'version':     None,
            'publisher':   None,
            'installDate': None,
            'sizeKB':      None,
        }

    from rst_lib import normalize_addin_name

    # Build reverse indexes for matching
    # displayName (lowercase) -> tab_name
    display_to_tab = {}
    for tab_name, info in static_lookup.items():
        dn = info.get('displayName', '').lower()
        if dn:
            display_to_tab[dn] = tab_name

    # tab key (lowercase) -> tab_name  (for substring matching)
    tab_keys_lower = {k.lower(): k for k in static_lookup}

    # normalized name -> tab_name  (strips dots, versions, noise words)
    norm_to_tab = {}
    for tab_name, info in static_lookup.items():
        norm = normalize_addin_name(info.get('displayName', tab_name))
        if norm:
            norm_to_tab[norm] = tab_name
        norm_key = normalize_addin_name(tab_name)
        if norm_key and norm_key not in norm_to_tab:
            norm_to_tab[norm_key] = tab_name

    # Match registry entries against known add-ins
    for prog in programs:
        reg_name = prog.get('DisplayName', '')
        if not reg_name:
            continue
        reg_name_lower = reg_name.lower()

        matched_tab = None

        # Strategy 1: exact displayName match
        if reg_name_lower in display_to_tab:
            matched_tab = display_to_tab[reg_name_lower]

        # Strategy 2: normalized name match (strips dots, versions, noise)
        if not matched_tab:
            reg_norm = normalize_addin_name(reg_name)
            if reg_norm and reg_norm in norm_to_tab:
                matched_tab = norm_to_tab[reg_norm]

        # Strategy 3: registry name contains a known tab key
        if not matched_tab:
            for key_lower, key_original in tab_keys_lower.items():
                if len(key_lower) >= 3 and key_lower in reg_name_lower:
                    matched_tab = key_original
                    break

        # Strategy 4: a known tab key contains the registry name
        if not matched_tab:
            for key_lower, key_original in tab_keys_lower.items():
                if len(reg_name_lower) >= 3 and reg_name_lower in key_lower:
                    matched_tab = key_original
                    break

        if not matched_tab:
            continue

        # Enrich the entry with registry data
        entry = merged[matched_tab]
        entry['version']     = prog.get('DisplayVersion') or None
        entry['publisher']   = prog.get('Publisher') or None
        entry['installDate'] = prog.get('InstallDate') or None
        size = prog.get('EstimatedSize', 0)
        entry['sizeKB']      = size if size else None

        # Registry URL wins over static if it has one
        reg_url = prog.get('URLInfoAbout') or prog.get('HelpLink') or ''
        if reg_url and not entry['url']:
            entry['url'] = reg_url

        # Registry DisplayName wins if we had a generic fallback
        if prog.get('DisplayName'):
            entry['displayName'] = prog['DisplayName']

    log.info('Enriched %d of %d lookup entries with registry data',
             sum(1 for e in merged.values() if e.get('version')),
             len(merged))
    return merged


# ── Top-level Entry Point ────────────────────────────────────────────────────

def get_enriched_lookup(static_lookup, cache_path, revit_username=None):
    """Scan registry (or load cache), filter to Revit add-ins, merge with static lookup.

    This is the single function called by addin_scanner.load_addin_lookup().
    """
    # Try cached scan first
    programs = load_cached_scan(cache_path)

    if programs is None:
        programs = scan_installed_programs()
        try:
            save_scan(programs, cache_path, revit_username=revit_username)
        except OSError as e:
            log.warning('Could not save system scan to disk: %s', e)

    return filter_revit_addins(programs, static_lookup)
