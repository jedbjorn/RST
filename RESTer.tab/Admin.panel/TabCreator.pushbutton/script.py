# -*- coding: utf-8 -*-
"""TabCreator - PyRevit pushbutton script.
Collects Revit data, then launches CPython with pywebview for the UI.
"""
import os
import sys
import json
import subprocess

_script_dir = os.path.dirname(os.path.abspath(__file__))
_root = os.path.join(_script_dir, '..', '..', '..')
_root = os.path.normpath(_root)

sys.path.insert(0, os.path.join(_root, 'app'))
from logger import get_logger
log = get_logger('tab_creator')


def get_revit_version():
    try:
        return str(__revit__.Application.VersionNumber)
    except Exception:
        return None


def get_installed_commands():
    results = []
    try:
        import clr
        clr.AddReference('AdWindows')
        from Autodesk.Windows import ComponentManager

        ribbon = ComponentManager.Ribbon
        for tab in ribbon.Tabs:
            source_tab = tab.Title if not tab.IsContextualTab else None
            for panel in tab.Panels:
                try:
                    items = panel.Source.Items
                except Exception:
                    continue
                for item in items:
                    if hasattr(item, 'CommandId') and item.CommandId:
                        results.append({
                            'name': item.Text or item.Id or '',
                            'commandId': str(item.CommandId),
                            'sourceTab': source_tab,
                            'icon': None,
                        })
    except Exception as e:
        log.error('Failed to scan ribbon: %s', e)
    return results


# Collect Revit data while we have access to the API
log.info('Collecting Revit data...')
revit_version = get_revit_version()
commands = get_installed_commands()
log.info('Revit %s, found %d commands', revit_version, len(commands))

# Write to temp file for CPython to read
revit_data = {
    'revit_version': revit_version,
    'commands': commands,
}
data_path = os.path.join(_root, 'app', '_revit_data.json')
with open(data_path, 'w') as f:
    json.dump(revit_data, f)
log.info('Revit data written to %s', data_path)

# Launch CPython with tab_creator.py
# Use cmd /k so the window stays open if there's an error
launcher = os.path.join(_root, 'app', 'tab_creator.py')
log.info('Launching CPython: %s', launcher)
subprocess.Popen(
    'python "{}" & pause'.format(launcher),
    shell=True,
)
log.info('TabCreator launched')
