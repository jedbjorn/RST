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

            # Get display name — items without one are usually non-actionable.
            # Normalize newlines to spaces: Revit uses \n for two-line ribbon
            # labels (e.g. "Floor\nPlan") which breaks HTML attribute round-trips.
            name = ''
            try:
                txt = getattr(item, 'Text', None)
                if txt:
                    name = str(txt).replace('\n', ' ').strip()
            except Exception:
                pass
            if not name:
                try:
                    nm = getattr(item, 'Name', None)
                    if nm:
                        name = str(nm).replace('\n', ' ').strip()
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

    # Validate: only keep commands that are actually postable.
    # Add-in commands (CustomCtrl_ prefix) use a separate invocation path
    # and don't need LookupCommandId validation.
    validated = []
    seen_ids = set()
    try:
        from Autodesk.Revit.UI import RevitCommandId, PostableCommand
    except Exception:
        RevitCommandId = None
        PostableCommand = None

    for cmd in results:
        cid = cmd.get('commandId', '')
        if not cid or cid in seen_ids:
            continue
        seen_ids.add(cid)

        # Add-in commands — always keep (they invoke via ExternalCommand)
        if 'CustomCtrl_' in cid:
            validated.append(cmd)
            continue

        # Revit built-in commands — verify postability via API
        if RevitCommandId is not None:
            try:
                rcmd = RevitCommandId.LookupCommandId(cid)
                if rcmd:
                    validated.append(cmd)
                    continue
            except Exception:
                pass

            # Try PostableCommand enum for ID_ style commands
            if cid.startswith('ID_') and PostableCommand is not None:
                try:
                    postable = getattr(PostableCommand, cid, None)
                    if postable is not None:
                        validated.append(cmd)
                        continue
                except Exception:
                    pass

            log.debug('Skipping non-postable command: %s', cid)
        else:
            # API unavailable — keep everything as fallback
            validated.append(cmd)

    log.info('Scan complete: %d raw, %d validated postable', len(results), len(validated))
    return validated


_BUILTIN_TABS = {
    'Architecture', 'Structure', 'Systems', 'Steel', 'Precast',
    'Insert', 'Annotate', 'Analyze', 'Massing & Site', 'Collaborate',
    'View', 'Manage', 'Modify', 'Add-Ins', 'Create', 'RSTPro',
    'FormIt', 'FormIt Converter', 'eTransmit',
    'Modify | Walls', 'Modify | Floors', 'Modify | Roofs',
    'Modify | Structural Framing', 'Modify | Generic Models',
}


_all_tabs = []
_addin_panels = []

# Panels on built-in tabs that are Revit-native (not third-party)
_BUILTIN_PANELS = {
    'Align', 'Macros', 'External', 'External Tools',
    'Analysis', 'Selection', 'Visual Programming',
}

def get_loaded_addins():
    """Collect loaded add-ins by scanning non-builtin ribbon tabs.
    Also populates _all_tabs and _addin_panels."""
    global _all_tabs, _addin_panels
    addins = []
    _all_tabs = []
    _addin_panels = []
    try:
        import clr
        clr.AddReference('AdWindows')
        from Autodesk.Windows import ComponentManager
        ribbon = ComponentManager.Ribbon
        if ribbon and ribbon.Tabs:
            seen = set()
            seen_panels = set()
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
                    else:
                        # Scan panels on built-in tabs for third-party add-ins
                        try:
                            if tab.Panels:
                                for panel in tab.Panels:
                                    try:
                                        psrc = panel.Source
                                        if psrc is None:
                                            continue
                                        ptitle = str(psrc.Title) if psrc.Title else ''
                                        if ptitle and ptitle not in _BUILTIN_PANELS and ptitle not in _BUILTIN_TABS and ptitle not in seen_panels:
                                            seen_panels.add(ptitle)
                                            _addin_panels.append({'name': ptitle, 'sourceTab': title})
                                    except Exception:
                                        continue
                        except Exception:
                            pass
                except Exception:
                    continue
    except Exception as e:
        log.warning('Could not scan ribbon for add-ins: %s', e)
    log.info('Found %d loaded add-ins, %d addin panels', len(addins), len(_addin_panels))
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

    # Merge assembly info into _addin_panels
    for panel in _addin_panels:
        key = panel.get('name', '').lower()
        if key in _loaded_apps:
            match = _loaded_apps[key]
            if 'assembly' in match:
                panel['assembly'] = match['assembly']
            if 'addinId' in match:
                panel['addinId'] = match['addinId']
except Exception as e:
    log.warning('Could not scan LoadedApplications: %s', e)

# Get Revit username
revit_username = None
try:
    revit_username = str(__revit__.Application.Username)
except Exception:
    pass

# Get Revit build
revit_build = None
try:
    revit_build = str(__revit__.Application.VersionBuild)
except Exception:
    pass

# Get active model info + warnings
_model_name = ''
_model_path = ''
_warnings_count = None
_warnings_by_severity = {}
try:
    doc = __revit__.ActiveUIDocument.Document
    if doc:
        _model_name = str(doc.Title) if doc.Title else ''
        _model_path = str(doc.PathName) if doc.PathName else ''
        try:
            _w = list(doc.GetWarnings())
            _warnings_count = len(_w)
            for fm in _w:
                try:
                    sev = str(fm.GetSeverity()).split('.')[-1]
                except Exception:
                    sev = 'Unknown'
                _warnings_by_severity[sev] = _warnings_by_severity.get(sev, 0) + 1
        except Exception as e:
            log.warning('Could not read document warnings: %s', e)
except Exception:
    pass

log.info('Revit %s, %d commands, %d loaded add-ins, username=%s',
         revit_version, len(commands), len(loaded_addins), revit_username)

# Write to temp file for CPython to read
revit_data = {
    'revit_version': revit_version,
    'revit_build': revit_build,
    'revit_username': revit_username,
    'model_name': _model_name,
    'model_path': _model_path,
    'warnings_count': _warnings_count,
    'warnings_by_severity': _warnings_by_severity,
    'commands': commands,
    'loaded_addins': loaded_addins,
    'all_tabs': _all_tabs,
    'addin_panels': _addin_panels,
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
    ['py', '-3.12', launcher],
    creationflags=CREATE_NO_WINDOW,
)
log.info('TabCreator launched')
