# -*- coding: utf-8 -*-
"""ProfileLoader - PyRevit pushbutton script.
Launches the Profile Selector UI via CPython subprocess.
"""
import io
import os
import sys
import subprocess

_script_dir = os.path.dirname(os.path.abspath(__file__))
_root = os.path.join(_script_dir, '..', '..', '..')
_root = os.path.normpath(_root)

sys.path.insert(0, os.path.join(_root, 'app'))
from logger import get_logger
log = get_logger('profile_loader_btn')

launcher = os.path.join(_root, 'app', 'profile_selector.py')
log.info('Launching Profile Selector: %s', launcher)
subprocess.Popen(
    'python "{}" & pause'.format(launcher),
    shell=True,
)
log.info('Profile Selector launched')
