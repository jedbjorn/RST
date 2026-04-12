# -*- coding: utf-8 -*-
"""health_viewer.py — CPython pywebview app to display the latest health snapshot.

Reads data/health_scan.json and exposes it to the UI via pywebview's JS API.
Run standalone: py -3.12 app\\health_viewer.py
"""
import os
import sys
import json
import webview

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_root, 'app'))

from logger import get_logger
from rst_lib import UI_DIR, HEALTH_SCAN_PATH

log = get_logger('health_viewer')

_html_path = os.path.join(UI_DIR, 'health_viewer.html')


class HealthViewerAPI:
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

    webview.create_window(
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
