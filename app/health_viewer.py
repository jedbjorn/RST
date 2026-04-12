# -*- coding: utf-8 -*-
"""health_viewer.py — CPython pywebview app to display the latest health snapshot.

Reads data/health_scan.json and exposes it to the UI via pywebview's JS API.
Run standalone: py -3.12 app\\health_viewer.py
"""
import os
import re
import sys
import json
import subprocess
import webview

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_root, 'app'))

from logger import get_logger
from rst_lib import UI_DIR, HEALTH_SCAN_PATH, HEALTH_SCAN_CONTEXT_PATH

CREATE_NO_WINDOW = 0x08000000

log = get_logger('health_viewer')

_html_path = os.path.join(UI_DIR, 'health_viewer.html')

_REVIT_APPDATA_DIR_RE = re.compile(r'^Autodesk Revit \d{4}$', re.IGNORECASE)
_RECENT_FILE_ENTRY_RE = re.compile(r'^\s*File\d+\s*=', re.IGNORECASE)


def _decode_ini_bytes(data):
    """Sniff BOM and return (text, encoding). Revit.ini is typically UTF-16 LE
    with BOM on modern Revit. Treating it as UTF-8 leaves null bytes embedded
    and breaks section-header matching."""
    if data.startswith(b'\xff\xfe'):
        return data.decode('utf-16-le'), 'utf-16-le'
    if data.startswith(b'\xfe\xff'):
        return data.decode('utf-16-be'), 'utf-16-be'
    if data.startswith(b'\xef\xbb\xbf'):
        return data.decode('utf-8-sig'), 'utf-8-sig'
    return data.decode('utf-8', errors='ignore'), 'utf-8'


def _purge_flat(path, label='purge'):
    """Walk `path` recursively and try to delete every file. Locked files
    are skipped individually — one locked file never aborts the rest.
    Directories are left in place. Returns (deleted_count, skipped_count)."""
    if not os.path.isdir(path):
        log.info('[%s] path missing, skipping: %s', label, path)
        return 0, 0
    deleted = 0
    skipped = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            full = os.path.join(root, name)
            try:
                os.unlink(full)
                deleted += 1
            except OSError as e:
                skipped += 1
                log.debug('[%s] skipped %s: %s', label, name, e)
    log.info('[%s] %s: deleted=%d skipped=%d (locked/in-use)', label, path, deleted, skipped)
    return deleted, skipped


def _purge_collab_cache(path, label='collabCache'):
    """Walk `path` recursively and try to delete every file. Locked files
    (active collaboration sessions) fail naturally with OSError and are
    skipped — no date filter. User-initiated cleanup means real clean.
    Returns (deleted_count, skipped_count)."""
    if not os.path.isdir(path):
        log.info('[%s] path missing, skipping: %s', label, path)
        return 0, 0
    deleted = 0
    skipped = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            full = os.path.join(root, name)
            try:
                os.unlink(full)
                deleted += 1
            except OSError as e:
                skipped += 1
                log.debug('[%s] skipped %s: %s', label, name, e)
    log.info('[%s] %s: deleted=%d skipped=%d (locked/in-use)',
             label, path, deleted, skipped)
    return deleted, skipped


def _purge_recent_file_list(ini_path, label='recentFiles'):
    """Strip FileN= entries under [Recent File List] in a Revit.ini, preserving
    everything else (including the section header). Atomic rewrite via temp file.
    Reads/writes in the file's native encoding (Revit.ini is UTF-16 LE with BOM
    on modern Revit — UTF-8 decode leaves nulls embedded and breaks matching).
    Returns (deleted_count, skipped_count) — skipped is 1 on any IO error
    (usually means Revit is running and holding the file)."""
    if not os.path.isfile(ini_path):
        log.info('[%s] ini missing, skipping: %s', label, ini_path)
        return 0, 0
    try:
        with open(ini_path, 'rb') as f:
            data = f.read()
    except OSError as e:
        log.warning('[%s] could not read %s: %s', label, ini_path, e)
        return 0, 1

    text, encoding = _decode_ini_bytes(data)
    log.info('[%s] %s: encoding=%s', label, ini_path, encoding)
    lines = text.splitlines(keepends=True)

    out = []
    in_section = False
    section_seen = False
    deleted = 0
    for raw in lines:
        stripped = raw.strip()
        if stripped.startswith('[') and stripped.endswith(']'):
            in_section = (stripped.lower() == '[recent file list]')
            if in_section:
                section_seen = True
            out.append(raw)
            continue
        if in_section and _RECENT_FILE_ENTRY_RE.match(raw):
            deleted += 1
            continue
        out.append(raw)

    if deleted == 0:
        log.info('[%s] %s: nothing to remove (section_matched=%s)',
                 label, ini_path, section_seen)
        return 0, 0

    tmp_path = ini_path + '.rsttmp'
    try:
        # Write-encoding preserves the original BOM form so Revit can still parse it.
        write_encoding = {
            'utf-16-le': 'utf-16',   # 'utf-16' writes the BOM
            'utf-16-be': 'utf-16',
            'utf-8-sig': 'utf-8-sig',
            'utf-8':     'utf-8',
        }[encoding]
        with open(tmp_path, 'w', encoding=write_encoding, newline='') as f:
            f.write(''.join(out))
        os.replace(tmp_path, ini_path)
        log.info('[%s] %s: deleted=%d', label, ini_path, deleted)
        return deleted, 0
    except OSError as e:
        log.warning('[%s] could not write %s: %s (Revit running?)', label, ini_path, e)
        try:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        except OSError:
            pass
        return 0, 1


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

        categories: {'temp': bool, 'pacCache': bool, 'journals': bool,
                     'collabCache': bool, 'recentFiles': bool}
        Journals + collabCache sweep every installed `Revit YYYY` subdir under
        AppData\\Local\\Autodesk\\Revit. recentFiles sweeps `Autodesk Revit YYYY`
        subdirs under AppData\\Roaming\\Autodesk\\Revit (where Revit.ini lives).
        """
        log.info('=== clean_junk invoked with categories=%s ===', categories)
        categories = categories or {}
        userdir = os.path.expanduser('~')
        tdir = os.path.join(userdir, 'AppData', 'Local', 'Temp')
        pcdir = os.path.join(userdir, 'AppData', 'Local', 'Autodesk', 'Revit', 'PacCache')
        revit_root = os.path.join(userdir, 'AppData', 'Local', 'Autodesk', 'Revit')
        revit_roaming = os.path.join(userdir, 'AppData', 'Roaming', 'Autodesk', 'Revit')

        deleted = {'temp': 0, 'pacCache': 0, 'journals': 0, 'collabCache': 0, 'recentFiles': 0}
        skipped = {'temp': 0, 'pacCache': 0, 'journals': 0, 'collabCache': 0, 'recentFiles': 0}

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
                if not _REVIT_APPDATA_DIR_RE.match(entry):
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

        if categories.get('recentFiles'):
            try:
                subdirs = os.listdir(revit_roaming)
            except OSError as e:
                log.warning('Could not list %s: %s', revit_roaming, e)
                subdirs = []
            for entry in subdirs:
                if not _REVIT_APPDATA_DIR_RE.match(entry):
                    continue
                ini_path = os.path.join(revit_roaming, entry, 'Revit.ini')
                d, s = _purge_recent_file_list(ini_path, label='recentFiles/%s' % entry)
                deleted['recentFiles'] += d
                skipped['recentFiles'] += s

        log.info('=== clean_junk result: deleted=%s skipped=%s ===', deleted, skipped)
        return {'deleted': deleted, 'skipped': skipped}

    def run_scan(self):
        """Run the health scan runner and return the fresh snapshot.

        Picks up optional Revit context (model name/path/size, warnings, etc.)
        from health_scan_context.json if the Snap pushbutton wrote one; otherwise
        runs with no context. Blocks until the runner finishes so the JS caller
        can render on resolve."""
        runner = os.path.join(_root, 'app', 'health_scan_runner.py')
        argv = ['py', '-3.12', runner]
        ctx = {}
        if os.path.exists(HEALTH_SCAN_CONTEXT_PATH):
            try:
                with open(HEALTH_SCAN_CONTEXT_PATH, 'r', encoding='utf-8') as f:
                    ctx = json.load(f) or {}
            except (OSError, json.JSONDecodeError) as e:
                log.warning('Failed to read scan context: %s', e)
        for key, flag in (
            ('revit_version',  '--revit-version'),
            ('revit_build',    '--revit-build'),
            ('revit_username', '--revit-username'),
            ('model_name',     '--model-name'),
            ('model_path',     '--model-path'),
            ('model_size_mb',  '--model-size-mb'),
            ('warnings_count', '--warnings-count'),
        ):
            val = ctx.get(key)
            if val:
                argv += [flag, str(val)]
        log.info('run_scan: launching runner (model=%s)', ctx.get('model_name') or '-')
        try:
            rc = subprocess.call(argv, creationflags=CREATE_NO_WINDOW)
        except Exception as e:
            log.warning('run_scan subprocess failed: %s', e)
            return {'ok': False, 'error': str(e), 'data': None}
        if rc != 0:
            log.warning('run_scan: runner returned rc=%s', rc)
            return {'ok': False, 'error': 'Runner exited with code %s' % rc, 'data': None}
        return {'ok': True, 'data': self.get_snapshot()}

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
