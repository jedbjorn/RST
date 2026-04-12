# -*- coding: utf-8 -*-
"""health_scan_runner.py — CPython 3.12 CLI runner for health snapshots.

Invoked from IronPython triggers (startup.py on RST load, Snap.pushbutton on
click). Revit context is passed as CLI args since the scanner itself runs
outside Revit. Writes to rst_lib.HEALTH_SCAN_PATH.

Run standalone: py -3.12 app\\health_scan_runner.py [--revit-version 2024] ...
"""
import argparse
import os
import sys

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_root, 'app'))

from logger import get_logger
from health_scanner import capture_health_snapshot, save_health_snapshot
from rst_lib import HEALTH_SCAN_PATH

log = get_logger('health_scan_runner')


def _norm(s):
    return s if (s is not None and s != '') else None


def _norm_int(s):
    try:
        return int(s) if s not in (None, '') else None
    except (ValueError, TypeError):
        return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--revit-version')
    p.add_argument('--revit-build')
    p.add_argument('--revit-username')
    p.add_argument('--model-name')
    p.add_argument('--model-path')
    p.add_argument('--warnings-count')
    args = p.parse_args()

    log.info('=== Health scan runner start (model=%s) ===', args.model_name or '—')
    try:
        snap = capture_health_snapshot(
            revit_version=_norm(args.revit_version),
            revit_build=_norm(args.revit_build),
            revit_username=_norm(args.revit_username),
            model_name=_norm(args.model_name),
            model_path=_norm(args.model_path),
            warnings_count=_norm_int(args.warnings_count),
        )
        save_health_snapshot(snap, HEALTH_SCAN_PATH)
        log.info('=== Health scan runner done ===')
    except Exception as e:
        log.error('Health scan runner failed: %s', e)
        sys.exit(1)


if __name__ == '__main__':
    main()
