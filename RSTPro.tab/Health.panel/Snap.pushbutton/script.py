# -*- coding: utf-8 -*-
"""Snap — Capture a fresh health snapshot then launch the Health viewer."""
__title__ = 'Snap'
import os
import sys
import subprocess

_script_dir = os.path.dirname(os.path.abspath(__file__))
_root = os.path.join(_script_dir, '..', '..', '..')
_root = os.path.normpath(_root)

sys.path.insert(0, os.path.join(_root, 'app'))
from logger import get_logger
log = get_logger('health_snap_btn')

CREATE_NO_WINDOW = 0x08000000

# ── Gather Revit context for the snapshot ───────────────────────────────────
revit_version = ''
revit_build = ''
revit_username = ''
model_name = ''
model_path = ''
warnings_count = ''

try:
    app = __revit__.Application  # noqa: F821
    try:
        revit_version = str(app.VersionNumber)
    except Exception:
        pass
    try:
        revit_build = str(app.VersionBuild)
    except Exception:
        pass
    try:
        revit_username = str(app.Username)
    except Exception:
        pass
except Exception as e:
    log.debug('Could not read Application: %s', e)

model_size_mb = ''
try:
    uidoc = __revit__.ActiveUIDocument  # noqa: F821
    if uidoc:
        doc = uidoc.Document
        if doc and not doc.IsFamilyDocument:
            try:
                model_name = str(doc.Title) if doc.Title else ''
            except Exception:
                pass
            try:
                model_path = str(doc.PathName) if doc.PathName else ''
            except Exception:
                pass
            if model_path:
                try:
                    import clr
                    clr.AddReference('mscorlib')
                    from System.IO import FileInfo
                    fi = FileInfo(model_path)
                    if fi.Exists:
                        model_size_mb = str(round(fi.Length / (1024.0 * 1024.0), 1))
                except Exception as e:
                    log.debug('FileInfo size read failed for %s: %s', model_path, e)
            # ACC / cloud fallback: doc.PathName is a cloud URL, not a real
            # filesystem path. The local cache under CollaborationCache is what
            # Revit actually reads/writes. Walk the cache tree for a file
            # matching <doc.Title>.rvt, take newest mtime.
            if not model_size_mb and model_name:
                try:
                    local_appdata = os.environ.get('LOCALAPPDATA', '')
                    cache_root = os.path.join(local_appdata, 'Autodesk', 'Revit') if local_appdata else ''
                    target = model_name if model_name.lower().endswith('.rvt') else (model_name + '.rvt')
                    target_lower = target.lower()
                    best = None  # (mtime, path, size)
                    if cache_root and os.path.isdir(cache_root):
                        for ver_entry in os.listdir(cache_root):
                            cc = os.path.join(cache_root, ver_entry, 'CollaborationCache')
                            if not os.path.isdir(cc):
                                continue
                            for walk_root, _dirs, files in os.walk(cc):
                                for f in files:
                                    if f.lower() == target_lower:
                                        full = os.path.join(walk_root, f)
                                        try:
                                            st = os.stat(full)
                                            if best is None or st.st_mtime > best[0]:
                                                best = (st.st_mtime, full, st.st_size)
                                        except OSError:
                                            pass
                    if best:
                        _mt, _fp, _sz = best
                        model_size_mb = str(round(_sz / (1024.0 * 1024.0), 1))
                        log.info('Found ACC model cache: %s (%s MB)', _fp, model_size_mb)
                except Exception as e:
                    log.debug('CollaborationCache fallback failed: %s', e)
            try:
                warnings_count = str(len(list(doc.GetWarnings())))
            except Exception:
                pass
except Exception as e:
    log.debug('Could not read active document: %s', e)

# ── Run scan synchronously, then launch viewer ──────────────────────────────
runner = os.path.join(_root, 'app', 'health_scan_runner.py')
runner_argv = ['py', '-3.12', runner]
for flag, val in (
    ('--revit-version',  revit_version),
    ('--revit-build',    revit_build),
    ('--revit-username', revit_username),
    ('--model-name',     model_name),
    ('--model-path',     model_path),
    ('--model-size-mb',  model_size_mb),
    ('--warnings-count', warnings_count),
):
    if val:
        runner_argv += [flag, val]

log.info('Running health scan before launching viewer (model=%s)', model_name or '-')
try:
    rc = subprocess.call(runner_argv, creationflags=CREATE_NO_WINDOW)
    if rc != 0:
        log.warning('Health scan runner returned rc=%s', rc)
    else:
        log.info('Health scan complete')
except Exception as e:
    log.warning('Health scan failed, opening viewer with previous snapshot: %s', e)

launcher = os.path.join(_root, 'app', 'health_viewer.py')
log.info('Launching Health viewer: %s', launcher)
subprocess.Popen(
    ['py', '-3.12', launcher],
    creationflags=CREATE_NO_WINDOW,
)
log.info('Health viewer launched')
