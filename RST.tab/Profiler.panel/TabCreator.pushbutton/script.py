# -*- coding: utf-8 -*-
"""TabCreator - PyRevit pushbutton script.
Collects Revit data, then launches CPython with pywebview for the UI.
"""
__title__ = 'Profiler'
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
log = get_logger('tab_creator')


def get_revit_version():
    try:
        return str(__revit__.Application.VersionNumber)
    except Exception:
        return None


def _scan_items(items, source_tab, source_panel, results, depth=0):
    """Recursively scan ribbon items, descending into containers."""
    # Item type substrings that indicate layout containers, not actionable commands.
    # Matched with endswith() to avoid false positives on button types.
    _CONTAINER_SUFFIXES = ('Panel', 'RowPanel', 'FlowPanel', 'StackedPanel',
                           'SlideOut', 'PopupPanel')
    item_count = 0
    for item in items:
        item_count += 1
        try:
            item_type = type(item).__name__

            # Skip separators
            if 'Separator' in item_type:
                continue

            # Recurse into container items (RowPanel, StackedPanel, etc.)
            try:
                child_items = getattr(item, 'Items', None)
                if child_items is not None:
                    _scan_items(child_items, source_tab, source_panel, results, depth + 1)
            except Exception:
                pass

            # Skip containers — already recursed into children above
            if 'ListButton' in item_type:
                continue
            if any(item_type.endswith(s) for s in _CONTAINER_SUFFIXES):
                continue

            # Try every possible way to get a command identifier
            cmd_str = ''
            try:
                cid = getattr(item, 'CommandId', None)
                if cid is not None:
                    s = str(cid).strip()
                    if s and s != 'None' and s != '---':
                        cmd_str = s
            except Exception:
                pass

            # Fall back to Id (Kinship, some add-ins use Id instead of CommandId)
            if not cmd_str:
                try:
                    iid = getattr(item, 'Id', None)
                    if iid is not None:
                        s = str(iid).strip()
                        if s and s != 'None' and s != '---':
                            cmd_str = s
                except Exception:
                    pass

            if not cmd_str or 'RibbonListButton' in cmd_str:
                continue

            # Get display name — items without one are usually non-actionable
            name = ''
            try:
                txt = getattr(item, 'Text', None)
                if txt:
                    name = str(txt).strip()
            except Exception:
                pass
            if not name:
                try:
                    nm = getattr(item, 'Name', None)
                    if nm:
                        name = str(nm).strip()
                except Exception:
                    pass
            if not name:
                continue  # no display name — not a user-facing command

            # Build display name with source for browser disambiguation
            display_name = name
            if source_panel and source_panel != source_tab:
                display_name = '%s (%s > %s)' % (name, source_tab, source_panel)
            elif source_tab:
                display_name = '%s (%s)' % (name, source_tab)

            results.append({
                'name': display_name,
                'baseName': name,
                'commandId': cmd_str,
                'sourceTab': source_tab,
                'sourcePanel': source_panel,
                'icon': None,
            })
        except Exception as e:
            log.debug('Skipping item: %s', e)
            continue

    if depth == 0:
        log.debug('Tab %s: scanned %d raw items', source_tab, item_count)


def get_installed_commands():
    results = []
    try:
        import clr
        clr.AddReference('AdWindows')
        from Autodesk.Windows import ComponentManager

        ribbon = ComponentManager.Ribbon
        if ribbon is None or ribbon.Tabs is None or ribbon.Tabs.Count == 0:
            log.warning('Ribbon not ready or empty - Revit may still be loading')
            return results
        log.info('Ribbon found, tabs: %d', ribbon.Tabs.Count)

        # Tabs to skip entirely (contextual, non-project, or editor-only)
        SKIP_TABS = {
            'Family Editor', 'In-Place Model', 'In-Place Mass',
            'Zone', 'Create',
        }

        for tab in ribbon.Tabs:
            try:
                source_tab = tab.Title
                if not source_tab:
                    continue
                # Skip contextual and non-project tabs
                is_contextual = False
                try:
                    is_contextual = bool(tab.IsContextualTab)
                except Exception:
                    pass
                if is_contextual or source_tab in SKIP_TABS:
                    log.debug('Skipping tab: %s (contextual=%s)', source_tab, is_contextual)
                    continue
                log.debug('Scanning tab: %s', source_tab)
            except Exception as e:
                log.error('Error reading tab title: %s', e)
                continue

            for panel in tab.Panels:
                try:
                    panel_source = panel.Source
                    if panel_source is None:
                        continue
                    items = panel_source.Items
                    if items is None:
                        continue
                    panel_title = ''
                    try:
                        panel_title = str(panel_source.Title) if panel_source.Title else ''
                    except Exception:
                        pass
                except Exception as e:
                    log.debug('Skipping panel: %s', e)
                    continue

                _scan_items(items, source_tab, panel_title, results)

    except Exception as e:
        log.error('Failed to scan ribbon: %s', e)
        import traceback
        log.error(traceback.format_exc())

    # Deduplicate by commandId — same command can appear at multiple
    # nesting levels (container + child) in the ribbon.
    # Keep the LAST occurrence: recursion collects children before parents,
    # so later entries are closer to the panel surface and more likely to
    # be the directly-postable button the user sees.
    seen = {}
    for idx, cmd in enumerate(results):
        cid = cmd.get('commandId', '')
        if cid:
            seen[cid] = idx  # last one wins
    deduped = [results[i] for i in sorted(seen.values())]

    log.info('Scan complete: %d commands found (%d after dedup)', len(results), len(deduped))
    return deduped


_BUILTIN_TABS = {
    'Architecture', 'Structure', 'Systems', 'Steel', 'Precast',
    'Insert', 'Annotate', 'Analyze', 'Massing & Site', 'Collaborate',
    'View', 'Manage', 'Modify', 'Add-Ins', 'Create', 'RST',
    'FormIt', 'FormIt Converter', 'eTransmit',
    'Modify | Walls', 'Modify | Floors', 'Modify | Roofs',
    'Modify | Structural Framing', 'Modify | Generic Models',
}


_all_tabs = []

def get_loaded_addins():
    """Collect loaded add-ins by scanning non-builtin ribbon tabs.
    Also populates _all_tabs with every visible tab name."""
    global _all_tabs
    addins = []
    _all_tabs = []
    try:
        import clr
        clr.AddReference('AdWindows')
        from Autodesk.Windows import ComponentManager
        ribbon = ComponentManager.Ribbon
        if ribbon and ribbon.Tabs:
            seen = set()
            for tab in ribbon.Tabs:
                try:
                    title = str(tab.Title) if tab.Title else ''
                    if not title or title in seen:
                        continue
                    is_ctx = False
                    try:
                        is_ctx = bool(tab.IsContextualTab)
                    except Exception:
                        pass
                    if is_ctx:
                        continue
                    seen.add(title)
                    _all_tabs.append(title)
                    if title not in _BUILTIN_TABS:
                        addins.append({'name': title})
                except Exception:
                    continue
    except Exception as e:
        log.warning('Could not scan ribbon for add-ins: %s', e)
    log.info('Found %d loaded add-ins', len(addins))
    return addins


# Collect Revit data while we have access to the API
log.info('Collecting Revit data...')
revit_version = get_revit_version()
commands = get_installed_commands()
loaded_addins = get_loaded_addins()
# Enrich loaded_addins with LoadedApplications assembly paths
try:
    _loaded_apps = {}
    # Try multiple API paths — varies by Revit version
    _app_list = None
    if hasattr(__revit__, 'LoadedApplications'):
        _app_list = __revit__.LoadedApplications
    elif hasattr(__revit__, 'Application') and hasattr(__revit__.Application, 'LoadedApplications'):
        _app_list = __revit__.Application.LoadedApplications
    if _app_list is None:
        raise AttributeError('LoadedApplications not found on __revit__ or __revit__.Application')
    for app in _app_list:
        try:
            name = str(app.Name) if hasattr(app, 'Name') else ''
            if name:
                entry = {'name': name}
                if hasattr(app, 'AddInId'):
                    entry['addinId'] = str(app.AddInId)
                if hasattr(app, 'Assembly') and app.Assembly:
                    entry['assembly'] = str(app.Assembly.Location) if hasattr(app.Assembly, 'Location') else ''
                _loaded_apps[name.lower()] = entry
        except Exception:
            continue

    for addin in loaded_addins:
        key = addin.get('name', '').lower()
        if key in _loaded_apps:
            match = _loaded_apps[key]
            if 'addinId' in match:
                addin['addinId'] = match['addinId']
            if 'assembly' in match:
                addin['assembly'] = match['assembly']
except Exception as e:
    log.warning('Could not scan LoadedApplications: %s', e)

# Get Revit username
revit_username = None
try:
    revit_username = str(__revit__.Application.Username)
except Exception:
    pass

log.info('Revit %s, %d commands, %d loaded add-ins, username=%s',
         revit_version, len(commands), len(loaded_addins), revit_username)

# Write to temp file for CPython to read
revit_data = {
    'revit_version': revit_version,
    'revit_username': revit_username,
    'commands': commands,
    'loaded_addins': loaded_addins,
    'all_tabs': _all_tabs,
}
data_path = os.path.join(_root, 'app', '_revit_data.json')
with io.open(data_path, 'w', encoding='utf-8') as f:
    json.dump(revit_data, f)
log.info('Revit data written to %s', data_path)

# Launch CPython with tab_creator.py
launcher = os.path.join(_root, 'app', 'tab_creator.py')
log.info('Launching CPython: %s', launcher)
CREATE_NO_WINDOW = 0x08000000
subprocess.Popen(
    ['python', launcher],
    creationflags=CREATE_NO_WINDOW,
)
log.info('TabCreator launched')
