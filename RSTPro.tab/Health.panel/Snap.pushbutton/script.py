# -*- coding: utf-8 -*-
"""Snap - Launches the Health viewer window (CPython + pywebview)."""
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

launcher = os.path.join(_root, 'app', 'health_viewer.py')
log.info('Launching Health viewer: %s', launcher)
CREATE_NO_WINDOW = 0x08000000
subprocess.Popen(
    ['py', '-3.12', launcher],
    creationflags=CREATE_NO_WINDOW,
)
log.info('Health viewer launched')
