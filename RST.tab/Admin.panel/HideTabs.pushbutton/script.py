# -*- coding: utf-8 -*-
"""HideTabs - PyRevit pushbutton script.
Collects ribbon tab info, launches CPython UI, waits for result, applies visibility.
"""
import io
import os
import sys
import json
import subprocess

_script_dir = os.path.dirname(os.path.abspath(__file__))
_root = os.path.join(_script_dir, '..', '..', '..')
_root = os.path.normpath(_root)

sys.path.insert(0, os.path.join(_root, 'app'))
from logger import get_logger
log = get_logger('hide_tabs')

# Collect current tab info
tabs_data = []
rst_source_tabs = set()
try:
    import clr
    clr.AddReference('AdWindows')
    from Autodesk.Windows import ComponentManager

    ribbon = ComponentManager.Ribbon

    # Read active profile to find which source tabs have tools in RST
    active_path = os.path.join(_root, 'app', 'active_profile.json')
    if os.path.exists(active_path):
        try:
            with io.open(active_path, 'r', encoding='utf-8') as f:
                active = json.load(f)
            profile_file = active.get('profile_file', '')
            if profile_file:
                profile_path = os.path.join(_root, 'app', 'profiles', profile_file)
                if os.path.exists(profile_path):
                    with io.open(profile_path, 'r', encoding='utf-8') as f:
                        profile = json.load(f)
                    # Collect source tabs from tools + requiredAddins
                    for panel in profile.get('panels', []):
                        for slot in panel.get('slots', []):
                            st = slot.get('sourceTab')
                            if st:
                                rst_source_tabs.add(st)
                    for addin in profile.get('requiredAddins', []):
                        rst_source_tabs.add(addin)
        except Exception as e:
            log.error('Error reading profile for source tabs: %s', e)

    seen_titles = set()
    for tab in ribbon.Tabs:
        try:
            title = str(tab.Title) if tab.Title else ''
            if not title:
                continue
            # Skip contextual tabs, duplicates, and non-project tabs
            is_contextual = False
            try:
                is_contextual = bool(tab.IsContextualTab)
            except Exception:
                pass
            if is_contextual:
                continue
            # Family Editor only appears in .rfa files, RST is .rvt only
            if title in ('Family Editor', 'In-Place Model', 'In-Place Mass', 'Zone', 'Create'):
                continue
            if title in seen_titles:
                continue
            seen_titles.add(title)

            tab_id = str(tab.Id) if tab.Id else ''
            is_visible = bool(tab.IsVisible)
            tabs_data.append({
                'title': title,
                'id': tab_id,
                'visible': is_visible,
                'inRst': title in rst_source_tabs,
            })
        except Exception:
            continue

    log.info('Found %d tabs, %d source tabs in RST profile', len(tabs_data), len(rst_source_tabs))

except Exception as e:
    log.error('Failed to collect tabs: %s', e)

# Write tab data for CPython
data_path = os.path.join(_root, 'app', '_tabs_data.json')
result_path = os.path.join(_root, 'app', '_tabs_result.json')

with io.open(data_path, 'w', encoding='utf-8') as f:
    json.dump({'tabs': tabs_data, 'rstSourceTabs': list(rst_source_tabs)}, f)

# Remove old result
if os.path.exists(result_path):
    os.remove(result_path)

# Launch CPython and WAIT for it to finish
launcher = os.path.join(_root, 'app', 'hide_tabs_ui.py')
log.info('Launching Hide Tabs UI...')
CREATE_NO_WINDOW = 0x08000000
proc = subprocess.Popen(['python', launcher], creationflags=CREATE_NO_WINDOW)
proc.wait()
log.info('Hide Tabs UI closed')

# Read result and apply visibility
if os.path.exists(result_path):
    try:
        with io.open(result_path, 'r', encoding='utf-8') as f:
            result = json.load(f)

        hidden_tabs = set(result.get('hidden', []))
        ribbon = ComponentManager.Ribbon

        # Get the list of non-contextual tabs we showed in the UI
        shown_titles = set(t.get('title', '') for t in tabs_data)

        # Tabs Revit manages contextually — never touch these
        _CONTEXTUAL = {'Family Editor', 'In-Place Model', 'In-Place Mass', 'Zone', 'Create'}

        for tab in ribbon.Tabs:
            try:
                title = str(tab.Title) if tab.Title else ''
                if not title or title == 'RST' or title == 'File':
                    continue
                # Skip contextual tabs — Revit controls their visibility
                is_contextual = False
                try:
                    is_contextual = bool(tab.IsContextualTab)
                except Exception:
                    pass
                if is_contextual or title in _CONTEXTUAL:
                    continue

                if title in hidden_tabs:
                    tab.IsVisible = False
                    log.info('Hidden tab: %s', title)
                elif title in shown_titles:
                    tab.IsVisible = True
                    log.debug('Visible tab: %s', title)
            except Exception as e:
                log.error('Error setting visibility for tab: %s', e)

        log.info('Tab visibility applied')
    except Exception as e:
        log.error('Failed to apply tab visibility: %s', e)

# Cleanup temp files
try:
    if os.path.exists(data_path):
        os.remove(data_path)
    if os.path.exists(result_path):
        os.remove(result_path)
except Exception:
    pass
