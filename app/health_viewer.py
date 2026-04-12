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


def _purge_flat(path):
    """Delete every file/symlink/subdir directly under `path`. Skips locked items. Returns count deleted."""
    if not os.path.isdir(path):
        return 0
    count = 0
    try:
        entries = os.listdir(path)
    except OSError:
        return 0
    for name in entries:
        full = os.path.join(path, name)
        try:
            if os.path.isfile(full) or os.path.islink(full):
                os.unlink(full)
                count += 1
            elif os.path.isdir(full):
                shutil.rmtree(full)
                count += 1
        except OSError:
            pass
    return count


def _purge_collab_cache(path):
    """Walk `path` recursively, delete files whose mtime-date != today. Skips locked items. Returns count deleted."""
    if not os.path.isdir(path):
        return 0
    count = 0
    curtime = time.ctime()[:10]
    for root, _dirs, files in os.walk(path):
        for name in files:
            full = os.path.join(root, name)
            try:
                if time.ctime(os.path.getmtime(full))[:10] != curtime:
                    os.unlink(full)
                    count += 1
            except OSError:
                pass
    return count


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
        """Delete junk files per selected categories. Returns dict of counts deleted per category.

        categories: {'temp': bool, 'pacCache': bool, 'journals': bool, 'collabCache': bool}
        Journals + collabCache sweep every installed `Revit YYYY` subdir under AppData\\Local\\Autodesk\\Revit.
        """
        categories = categories or {}
        userdir = os.path.expanduser('~')
        tdir = os.path.join(userdir, 'AppData', 'Local', 'Temp')
        pcdir = os.path.join(userdir, 'AppData', 'Local', 'Autodesk', 'Revit', 'PacCache')
        revit_root = os.path.join(userdir, 'AppData', 'Local', 'Autodesk', 'Revit')

        counts = {'temp': 0, 'pacCache': 0, 'journals': 0, 'collabCache': 0}

        if categories.get('temp'):
            counts['temp'] = _purge_flat(tdir)

        if categories.get('pacCache'):
            counts['pacCache'] = _purge_flat(pcdir)

        if categories.get('journals') or categories.get('collabCache'):
            try:
                subdirs = os.listdir(revit_root)
            except OSError:
                subdirs = []
            for entry in subdirs:
                if not _REVIT_VERSION_RE.match(entry):
                    continue
                vdir = os.path.join(revit_root, entry)
                if not os.path.isdir(vdir):
                    continue
                if categories.get('journals'):
                    counts['journals'] += _purge_flat(os.path.join(vdir, 'Journals'))
                if categories.get('collabCache'):
                    counts['collabCache'] += _purge_collab_cache(os.path.join(vdir, 'CollaborationCache'))

        log.info('clean_junk result: %s (categories=%s)', counts, categories)
        return counts

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
