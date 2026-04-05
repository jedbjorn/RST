# -*- coding: utf-8 -*-
"""RESTer startup hook - runs on every Revit launch via PyRevit.
Reads active_profile.json, builds a custom ribbon tab if a profile is loaded.
"""
import io
import os
import sys
import json
import time
import datetime

_root = os.path.dirname(os.path.abspath(__file__))

# Add app/ to path for imports
sys.path.insert(0, os.path.join(_root, 'app'))
from logger import get_logger

log = get_logger('startup')

_active_profile_path = os.path.join(_root, 'app', 'active_profile.json')
_profiles_dir = os.path.join(_root, 'app', 'profiles')
_icons_dir = os.path.join(_root, 'icons')
_default_icon_32 = os.path.join(_root, 'icons', 'RESTer_default.png')
_default_icon_16 = os.path.join(_root, 'icons', 'RESTer_default_16.png')


def _load_active_profile():
    """Read active_profile.json. Returns (active_data, profile_data) or (None, None)."""
    if not os.path.exists(_active_profile_path):
        log.debug('No active_profile.json - nothing to build')
        return None, None

    try:
        with io.open(_active_profile_path, 'r', encoding='utf-8') as f:
            active = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        log.error('Failed to read active_profile.json: %s', e)
        return None, None

    profile_file = active.get('profile_file')
    if not profile_file:
        log.debug('No profile_file in active_profile.json')
        return None, None

    profile_path = os.path.join(_profiles_dir, profile_file)
    if not os.path.exists(profile_path):
        log.error('Profile file not found: %s', profile_path)
        return None, None

    try:
        with io.open(profile_path, 'r', encoding='utf-8') as f:
            profile = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        log.error('Failed to read profile %s: %s', profile_file, e)
        return None, None

    return active, profile


def _needs_rebuild(active, profile_path):
    """Compare profile file mtime against last_built timestamp."""
    last_built = active.get('last_built')
    if not last_built:
        log.info('No last_built timestamp - rebuild needed')
        return True

    try:
        file_mtime = os.path.getmtime(profile_path)
        built_dt = datetime.datetime.strptime(last_built, '%Y-%m-%dT%H:%M:%S')
        built_ts = time.mktime(built_dt.timetuple())
        if file_mtime >= built_ts:
            log.info('Profile modified since last build - rebuild needed')
            return True
        log.info('Profile unchanged since last build - skipping rebuild')
        return False
    except (ValueError, OSError) as e:
        log.warning('Could not compare timestamps: %s - rebuilding', e)
        return True


def _update_last_built(active):
    """Write updated last_built timestamp to active_profile.json."""
    active['last_built'] = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    with io.open(_active_profile_path, 'w', encoding='utf-8') as f:
        json.dump(active, f, indent=2)
    log.info('Updated last_built: %s', active['last_built'])


def _get_icon_path(slot, small=False):
    """Resolve icon path for a tool slot. small=True returns 16x16 icon."""
    icon_file = slot.get('iconFile')
    if icon_file:
        custom_path = os.path.join(_icons_dir, icon_file)
        if os.path.exists(custom_path):
            return custom_path
        log.warning('Custom icon not found: %s - using default', icon_file)
    return _default_icon_16 if small else _default_icon_32


def _get_revit_version():
    """Get current Revit version number."""
    try:
        return str(__revit__.Application.VersionNumber)  # noqa: F821
    except Exception:
        return None


def _load_icon(icon_path):
    """Load a PNG file as a BitmapImage for the Revit ribbon."""
    try:
        import clr
        clr.AddReference('PresentationCore')
        from System.Windows.Media.Imaging import BitmapImage
        from System import Uri, UriKind
        if icon_path and os.path.exists(icon_path):
            uri = Uri(os.path.abspath(icon_path), UriKind.Absolute)
            return BitmapImage(uri)
    except Exception as e:
        log.debug('Could not load icon %s: %s', icon_path, e)
    return None


def _hex_to_color(hex_str):
    """Convert hex color string like '#4f8ef7' to a System.Windows.Media.Color."""
    try:
        import clr
        clr.AddReference('PresentationCore')
        from System.Windows.Media import Color
        hex_str = hex_str.lstrip('#')
        r = int(hex_str[0:2], 16)
        g = int(hex_str[2:4], 16)
        b = int(hex_str[4:6], 16)
        return Color.FromArgb(255, r, g, b)
    except Exception as e:
        log.debug('Could not parse color %s: %s', hex_str, e)
        return None


def _make_brush(hex_color):
    """Create a SolidColorBrush from a hex color string."""
    try:
        import clr
        clr.AddReference('PresentationCore')
        from System.Windows.Media import SolidColorBrush
        color = _hex_to_color(hex_color)
        if color:
            return SolidColorBrush(color)
    except Exception as e:
        log.debug('Could not create brush for %s: %s', hex_color, e)
    return None


def _build_ribbon(profile):
    """Build a custom Revit ribbon tab using the AdWindows API."""
    try:
        import clr
        clr.AddReference('AdWindows')
        clr.AddReference('PresentationCore')
        from Autodesk.Windows import (
            ComponentManager,
            RibbonTab,
            RibbonPanel as AwRibbonPanel,
            RibbonPanelSource,
            RibbonButton,
            RibbonSplitButton,
            RibbonItemSize,
        )
    except Exception as e:
        log.error('AdWindows import failed: %s', e)
        return False

    tab_name = profile.get('tab', 'RESTer')
    panels = profile.get('panels', [])
    stacks = profile.get('stacks', {})

    log.info('Building ribbon tab: %s (%d panels)', tab_name, len(panels))

    try:
        ribbon = ComponentManager.Ribbon

        # Create the tab
        tab = RibbonTab()
        tab.Title = tab_name
        tab.Id = 'RESTer_' + tab_name.replace(' ', '_')
        ribbon.Tabs.Add(tab)
        log.info('Created ribbon tab: %s', tab_name)

        for panel_def in panels:
            panel_name = panel_def.get('name', 'Panel')
            panel_color = panel_def.get('color', '#4f8ef7')

            aw_panel = AwRibbonPanel()
            panel_source = RibbonPanelSource()
            panel_source.Title = panel_name
            panel_source.Id = 'RESTer_Panel_' + panel_name.replace(' ', '_')
            aw_panel.Source = panel_source

            # Apply panel color
            brush = _make_brush(panel_color)
            if brush:
                try:
                    aw_panel.CustomPanelBackground = brush
                    aw_panel.CustomPanelTitleBarBackground = brush
                    log.debug('Applied color %s to panel %s', panel_color, panel_name)
                except Exception as e:
                    log.debug('Could not apply panel color: %s', e)

            tab.Panels.Add(aw_panel)
            log.info('Created panel: %s (color: %s)', panel_name, panel_color)

            for slot in panel_def.get('slots', []):
                slot_type = slot.get('type')

                if slot_type == 'tool':
                    btn = _create_tool_button(slot)
                    if btn:
                        aw_panel.Source.Items.Add(btn)
                elif slot_type == 'stack':
                    stack_name = slot.get('name', '')
                    stack_def_data = stacks.get(stack_name)
                    if stack_def_data:
                        split = _create_stack_button(stack_name, stack_def_data)
                        if split:
                            aw_panel.Source.Items.Add(split)
                    else:
                        log.warning('Stack not found: %s', stack_name)

    except Exception as e:
        log.error('Ribbon build failed: %s', e)
        import traceback
        log.error(traceback.format_exc())
        return False

    log.info('Ribbon build complete')
    return True


def _create_tool_button(slot):
    """Create a large RibbonButton (32x32 icon, text below)."""
    from Autodesk.Windows import RibbonButton, RibbonItemSize

    name = slot.get('name', 'Tool')
    command_id = slot.get('commandId', '')

    try:
        btn = RibbonButton()
        btn.Text = name
        btn.Id = 'RESTer_Btn_' + name.replace(' ', '_')
        btn.ShowText = True
        btn.Size = RibbonItemSize.Large

        # 32x32 icon (Large size shows icon on top, text below by default)
        icon = _load_icon(_get_icon_path(slot, small=False))
        if icon:
            btn.LargeImage = icon
            btn.Image = icon

        # Bind click to PostCommand
        if command_id:
            handler = _make_command_handler(command_id)
            if handler:
                btn.CommandHandler = handler

        log.debug('Created tool button: %s -> %s', name, command_id)
        return btn

    except Exception as e:
        log.error('Failed to create button %s: %s', name, e)
        return None


def _create_stack_button(stack_name, stack_def):
    """Create a RibbonSplitButton with child tools (16x16 icons)."""
    from Autodesk.Windows import RibbonSplitButton, RibbonButton, RibbonItemSize

    tools = stack_def.get('tools', [])

    try:
        split = RibbonSplitButton()
        split.Text = stack_name
        split.Id = 'RESTer_Stack_' + stack_name.replace(' ', '_')
        split.Size = RibbonItemSize.Large

        try:
            split.IsSplit = True
        except Exception:
            log.debug('Could not set IsSplit for %s', stack_name)

        for tool in tools:
            tool_name = tool.get('name', 'Tool')
            command_id = tool.get('commandId', '')

            child = RibbonButton()
            child.Text = tool_name
            child.Id = 'RESTer_StackBtn_' + tool_name.replace(' ', '_')
            child.ShowText = True
            child.Size = RibbonItemSize.Standard

            # 16x16 icon for stack items
            icon = _load_icon(_get_icon_path(tool, small=True))
            if icon:
                child.Image = icon

            if command_id:
                handler = _make_command_handler(command_id)
                if handler:
                    child.CommandHandler = handler

            split.Items.Add(child)
            log.debug('  Stack tool: %s -> %s', tool_name, command_id)

        log.debug('Created stack: %s (%d tools)', stack_name, len(tools))
        return split

    except Exception as e:
        log.error('Failed to create stack %s: %s', stack_name, e)
        return None


def _make_command_handler(command_id):
    """Create an ICommand-compatible handler for IronPython."""
    try:
        import clr
        clr.AddReference('PresentationCore')
        from System.Windows.Input import ICommand

        class CommandHandler(ICommand):
            def __init__(self):
                self._command_id = command_id

            def add_CanExecuteChanged(self, handler):
                pass

            def remove_CanExecuteChanged(self, handler):
                pass

            def CanExecute(self, parameter):
                return True

            def Execute(self, parameter):
                try:
                    from Autodesk.Revit.UI import RevitCommandId, PostableCommand
                    cid = self._command_id

                    # Try direct lookup first (works for most commands)
                    cmd = RevitCommandId.LookupCommandId(cid)
                    if cmd:
                        try:
                            __revit__.PostCommand(cmd)  # noqa: F821
                            return
                        except Exception:
                            pass

                    # Try PostableCommand enum lookup (for ID_ style commands)
                    if cid.startswith('ID_'):
                        try:
                            postable = getattr(PostableCommand, cid, None)
                            if postable is not None:
                                pcmd = RevitCommandId.LookupPostableCommandId(postable)
                                if pcmd:
                                    __revit__.PostCommand(pcmd)  # noqa: F821
                                    return
                        except Exception:
                            pass

                    log.warning('Command not postable: %s', cid)
                except Exception as e:
                    log.error('PostCommand failed for %s: %s', self._command_id, e)

        return CommandHandler()
    except Exception as e:
        log.error('Failed to create command handler for %s: %s', command_id, e)
        return None


# --- Main startup logic ---

def main():
    log.info('=== RESTer startup hook ===')

    active, profile = _load_active_profile()
    if not active or not profile:
        log.info('No active profile - startup complete (no tab to build)')
        return

    log.info('Active profile: %s', active.get('profile'))

    # Cache check
    profile_path = os.path.join(_profiles_dir, active.get('profile_file', ''))
    if not _needs_rebuild(active, profile_path):
        return

    # Version check
    revit_version = _get_revit_version()
    min_version = profile.get('min_version')
    if revit_version and min_version:
        if int(revit_version) < int(min_version):
            log.warning('Revit %s is below min_version %s - aborting',
                        revit_version, min_version)
            return

    # Build the ribbon
    if _build_ribbon(profile):
        _update_last_built(active)

    log.info('=== RESTer startup complete ===')


main()
