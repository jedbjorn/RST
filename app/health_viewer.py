# -*- coding: utf-8 -*-
"""health_viewer.py — CPython pywebview app to display the latest health snapshot.

Reads data/health_scan.json and exposes it to the UI via pywebview's JS API.
Run standalone: py -3.12 app\\health_viewer.py
"""
import os
import re
import sys
import json
import time
import shutil
import webview

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_root, 'app'))

from logger import get_logger
from rst_lib import UI_DIR, HEALTH_SCAN_PATH

log = get_logger('health_viewer')

_html_path = os.path.join(UI_DIR, 'health_viewer.html')

_REVIT_VERSION_RE = re.compile(r'^Revit\s+\d{4}$', re.IGNORECASE)


def _purge_flat(path, label='purge'):
    """Delete every file/symlink/subdir directly under `path`. Skips locked items.
    Returns (deleted_count, skipped_count). Logs reason for every skip."""
    if not os.path.isdir(path):
        log.info('[%s] path missing, skipping: %s', label, path)
        return 0, 0
    try:
        entries = os.listdir(path)
    except OSError as e:
        log.warning('[%s] could not list %s: %s', label, path, e)
        return 0, 0
    deleted = 0
    skipped = 0
    for name in entries:
        full = os.path.join(path, name)
        try:
            if os.path.isfile(full) or os.path.islink(full):
                os.unlink(full)
                deleted += 1
            elif os.path.isdir(full):
                shutil.rmtree(full)
                deleted += 1
        except OSError as e:
            skipped += 1
            log.debug('[%s] skipped %s: %s', label, name, e)
    log.info('[%s] %s: deleted=%d skipped=%d (locked/in-use)', label, path, deleted, skipped)
    return deleted, skipped


def _purge_collab_cache(path, label='collabCache'):
    """Walk `path` recursively, delete files whose mtime-date != today. Skips locked items.
    Returns (deleted_count, skipped_count)."""
    if not os.path.isdir(path):
        log.info('[%s] path missing, skipping: %s', label, path)
        return 0, 0
    deleted = 0
    skipped = 0
    kept_today = 0
    curtime = time.ctime()[:10]
    for root, _dirs, files in os.walk(path):
        for name in files:
            full = os.path.join(root, name)
            try:
                if time.ctime(os.path.getmtime(full))[:10] == curtime:
                    kept_today += 1
                    continue
                os.unlink(full)
                deleted += 1
            except OSError as e:
                skipped += 1
                log.debug('[%s] skipped %s: %s', label, name, e)
    log.info('[%s] %s: deleted=%d skipped=%d kept_today=%d',
             label, path, deleted, skipped, kept_today)
    return deleted, skipped


class HealthViewerAPI:
    def __init__(self):
        self.window = None

    def get_snapshot(self):
        """Return the parsed health snapshot, or None if the file doesn't exist."""
        if not os.path.exists(HEALTH_SCAN_PATH):
            log.info('No health snapshot at %s', HEALTH_SCAN_PATH)
            return None
        try:
            with open(HEALTH_SCAN_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            log.warning('Failed to read health snapshot: %s', e)
            return None

    def clean_junk(self, categories):
        """Delete junk files per selected categories. Returns per-category
        {deleted, skipped} counts plus per-category skipped totals.

        categories: {'temp': bool, 'pacCache': bool, 'journals': bool, 'collabCache': bool}
        Journals + collabCache sweep every installed `Revit YYYY` subdir under AppData\\Local\\Autodesk\\Revit.
        """
        log.info('=== clean_junk invoked with categories=%s ===', categories)
        categories = categories or {}
        userdir = os.path.expanduser('~')
        tdir = os.path.join(userdir, 'AppData', 'Local', 'Temp')
        pcdir = os.path.join(userdir, 'AppData', 'Local', 'Autodesk', 'Revit', 'PacCache')
        revit_root = os.path.join(userdir, 'AppData', 'Local', 'Autodesk', 'Revit')

        deleted = {'temp': 0, 'pacCache': 0, 'journals': 0, 'collabCache': 0}
        skipped = {'temp': 0, 'pacCache': 0, 'journals': 0, 'collabCache': 0}

        if categories.get('temp'):
            d, s = _purge_flat(tdir, label='temp')
            deleted['temp'], skipped['temp'] = d, s

        if categories.get('pacCache'):
            d, s = _purge_flat(pcdir, label='pacCache')
            deleted['pacCache'], skipped['pacCache'] = d, s

        if categories.get('journals') or categories.get('collabCache'):
            try:
                subdirs = os.listdir(revit_root)
            except OSError as e:
                log.warning('Could not list %s: %s', revit_root, e)
                subdirs = []
            log.info('Revit root subdirs found: %s', subdirs)
            for entry in subdirs:
                if not _REVIT_VERSION_RE.match(entry):
                    continue
                vdir = os.path.join(revit_root, entry)
                if not os.path.isdir(vdir):
                    continue
                if categories.get('journals'):
                    d, s = _purge_flat(os.path.join(vdir, 'Journals'), label='journals/%s' % entry)
                    deleted['journals']    += d
                    skipped['journals']    += s
                if categories.get('collabCache'):
                    d, s = _purge_collab_cache(os.path.join(vdir, 'CollaborationCache'),
                                               label='collabCache/%s' % entry)
                    deleted['collabCache'] += d
                    skipped['collabCache'] += s

        log.info('=== clean_junk result: deleted=%s skipped=%s ===', deleted, skipped)
        return {'deleted': deleted, 'skipped': skipped}

    def close_window(self):
        if self.window is not None:
            self.window.destroy()


if __name__ == '__main__':
    log.info('=== Health Viewer starting ===')
    log.info('HTML: %s', _html_path)
    log.info('Snapshot: %s (exists=%s)', HEALTH_SCAN_PATH, os.path.exists(HEALTH_SCAN_PATH))

    api = HealthViewerAPI()

    try:
        import ctypes
        user32 = ctypes.windll.user32
        sw = user32.GetSystemMetrics(0)
        sh = user32.GetSystemMetrics(1)
        wx, wy = (sw - 900) // 2, (sh - 800) // 2
    except Exception:
        wx, wy = None, None

    api.window = webview.create_window(
        'RST — Health',
        url=_html_path,
        width=900,
        height=800,
        x=wx,
        y=wy,
        resizable=True,
        js_api=api,
    )
    webview.start()
    log.info('=== Health Viewer closed ===')
