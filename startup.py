# -*- coding: utf-8 -*-
"""RST startup hook - runs on every Revit launch via PyRevit.
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
    except (ValueError, IOError) as e:
        log.error('Failed to read active_profile.json: %s', e)
        return None, None

    # Blank profile — build empty tab with just branding
    if active.get('blank'):
        log.info('Blank profile — will build empty RST tab')
        blank_profile = {'tab': 'RST', 'panels': [], 'stacks': {}, 'panelOpacity': 100}
        return active, blank_profile

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
    except (ValueError, IOError) as e:
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


def _load_icon_sized(icon_path, width, height):
    """Load a PNG and force it to a specific pixel size via DecodePixelWidth/Height."""
    try:
        import clr
        clr.AddReference('PresentationCore')
        from System.Windows.Media.Imaging import BitmapImage, BitmapCacheOption
        from System import Uri, UriKind
        if icon_path and os.path.exists(icon_path):
            bmp = BitmapImage()
            bmp.BeginInit()
            bmp.UriSource = Uri(os.path.abspath(icon_path), UriKind.Absolute)
            bmp.DecodePixelWidth = width
            bmp.DecodePixelHeight = height
            bmp.CacheOption = BitmapCacheOption.OnLoad
            bmp.EndInit()
            return bmp
    except Exception as e:
        log.debug('Could not load sized icon %s: %s', icon_path, e)
    return _load_icon(icon_path)


def _hex_to_color(hex_str, alpha=1.0):
    """Convert hex color string like '#4f8ef7' to a System.Windows.Media.Color."""
    try:
        import clr
        clr.AddReference('PresentationCore')
        from System.Windows.Media import Color
        hex_str = hex_str.lstrip('#')
        r = int(hex_str[0:2], 16)
        g = int(hex_str[2:4], 16)
        b = int(hex_str[4:6], 16)
        a = int(max(0.0, min(1.0, alpha)) * 255)
        return Color.FromArgb(a, r, g, b)
    except Exception as e:
        log.debug('Could not parse color %s: %s', hex_str, e)
        return None


def _make_brush(hex_color, alpha=1.0):
    """Create a DrawingBrush that paints a rounded rectangle."""
    try:
        import clr
        clr.AddReference('PresentationCore')
        from System.Windows.Media import (
            SolidColorBrush, DrawingBrush, GeometryDrawing,
            BrushMappingMode, TileMode, Stretch,
        )
        from System.Windows import Rect

        color = _hex_to_color(hex_color, alpha)
        if not color:
            return None

        fill = SolidColorBrush(color)

        # RectangleGeometry with rounded corners
        from System.Windows.Media import RectangleGeometry
        rect_geo = RectangleGeometry(Rect(0, 0, 1, 1))
        rect_geo.RadiusX = 0.12
        rect_geo.RadiusY = 0.15

        drawing = GeometryDrawing(fill, None, rect_geo)

        brush = DrawingBrush(drawing)
        brush.Stretch = Stretch.Fill
        brush.ViewportUnits = BrushMappingMode.RelativeToBoundingBox
        brush.TileMode = getattr(TileMode, 'None')
        return brush
    except Exception as e:
        log.debug('Could not create rounded brush for %s: %s — falling back to solid', hex_color, e)
        # Fallback to solid brush
        try:
            from System.Windows.Media import SolidColorBrush
            color = _hex_to_color(hex_color, alpha)
            if color:
                return SolidColorBrush(color)
        except Exception:
            pass
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

    tab_name = profile.get('tab', 'RST')
    panels = profile.get('panels', [])
    stacks = profile.get('stacks', {})
    panel_opacity = max(10, min(100, profile.get('panelOpacity', 100))) / 100.0

    log.info('Building ribbon tab: %s (%d panels)', tab_name, len(panels))

    try:
        ribbon = ComponentManager.Ribbon

        # Remove ALL RST-created tabs by ID prefix (handles renames)
        to_remove = []
        for t in ribbon.Tabs:
            try:
                t_id = str(t.Id) if t.Id else ''
                if t_id.startswith('REST_'):
                    to_remove.append(t)
            except Exception:
                continue
        for old_tab in to_remove:
            try:
                old_title = str(old_tab.Title) if old_tab.Title else '?'
                ribbon.Tabs.Remove(old_tab)
                log.info('Removed old RST tab: %s (id: %s)', old_title, old_tab.Id)
            except Exception as e:
                log.warning('Could not remove tab %s: %s', old_tab.Id, e)

        # Create the tab
        tab = RibbonTab()
        tab.Title = tab_name
        tab.Id = 'REST_' + tab_name.replace(' ', '_')
        ribbon.Tabs.Add(tab)
        log.info('Created ribbon tab: %s', tab_name)

        # ── Branding panel (always leftmost, WPF Image for larger size) ──
        try:
            import clr
            clr.AddReference('PresentationFramework')
            clr.AddReference('PresentationCore')
            clr.AddReference('WindowsBase')
            from System.Windows.Controls import Image as WpfImage
            from System.Windows.Input import MouseButtonEventHandler
            from System.Windows import Thickness
            from Autodesk.Windows import RibbonCommandItem

            branding_panel = AwRibbonPanel()
            branding_source = RibbonPanelSource()
            branding_source.Title = ' '
            branding_source.Id = 'REST_Branding'
            branding_panel.Source = branding_source

            # Create a RibbonButton but override its visual with a larger WPF Image
            branding_btn = RibbonButton()
            branding_btn.Text = ''
            branding_btn.Id = 'REST_Branding_Btn'
            branding_btn.ShowText = False
            branding_btn.Size = RibbonItemSize.Large

            # Load branding.png at 48x48 for the button image
            branding_icon_path = os.path.join(_icons_dir, 'branding.png')
            icon = _load_icon_sized(branding_icon_path, 48, 48)
            if icon:
                branding_btn.LargeImage = icon
                branding_btn.Image = icon

            # Click opens GitHub
            branding_handler = _make_url_handler('https://github.com/jedbjorn/RST')
            if branding_handler:
                branding_btn.CommandHandler = branding_handler

            branding_panel.Source.Items.Add(branding_btn)
            tab.Panels.Add(branding_panel)
            log.info('Added branding panel')
        except Exception as e:
            log.warning('Could not add branding panel: %s', e)

        for panel_def in panels:
            panel_name = panel_def.get('name', 'Panel')
            panel_color = panel_def.get('color', '#4f8ef7')

            aw_panel = AwRibbonPanel()
            panel_source = RibbonPanelSource()
            panel_source.Title = panel_name
            panel_source.Id = 'REST_Panel_' + panel_name.replace(' ', '_')
            aw_panel.Source = panel_source

            # Apply panel color with opacity
            brush = _make_brush(panel_color, panel_opacity)
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

    display_name = slot.get('baseName', slot.get('name', 'Tool'))
    full_name = slot.get('name', display_name)
    command_id = slot.get('commandId', '')
    source_tab = slot.get('sourceTab', '')
    source_panel = slot.get('sourcePanel', '')

    try:
        import clr
        clr.AddReference('PresentationFramework')

        btn = RibbonButton()
        btn.Text = display_name
        btn.Id = 'REST_Btn_' + full_name.replace(' ', '_')
        btn.ShowText = True
        btn.Size = RibbonItemSize.Large

        # Tooltip shows source info on hover
        tip = display_name
        if source_panel and source_tab:
            tip = '%s\nSource: %s > %s' % (display_name, source_tab, source_panel)
        elif source_tab:
            tip = '%s\nSource: %s' % (display_name, source_tab)
        try:
            btn.ToolTip = tip
        except Exception:
            pass

        # Text below icon
        try:
            from System.Windows.Controls import Orientation
            btn.Orientation = Orientation.Vertical
        except Exception as e:
            log.debug('Could not set orientation for %s: %s', display_name, e)

        # 32x32 icon
        icon = _load_icon(_get_icon_path(slot, small=False))
        if icon:
            btn.LargeImage = icon
            btn.Image = icon

        # Bind click to PostCommand (or URL handler for custom URL tools)
        if command_id:
            if command_id.startswith('URL:'):
                handler = _make_url_handler(command_id[4:])
            else:
                handler = _make_command_handler(command_id)
            if handler:
                btn.CommandHandler = handler

        log.debug('Created tool button: %s -> %s', display_name, command_id)
        return btn

    except Exception as e:
        log.error('Failed to create button %s: %s', display_name, e)
        return None


def _create_stack_button(stack_name, stack_def):
    """Create a RibbonSplitButton with child tools (16x16 icons)."""
    from Autodesk.Windows import RibbonSplitButton, RibbonButton, RibbonItemSize

    tools = stack_def.get('tools', [])

    try:
        split = RibbonSplitButton()
        split.Text = stack_name
        split.Id = 'REST_Stack_' + stack_name.replace(' ', '_')
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
            child.Id = 'REST_StackBtn_' + tool_name.replace(' ', '_')
            child.ShowText = True
            child.Size = RibbonItemSize.Standard

            # 16x16 icon for stack items
            icon = _load_icon(_get_icon_path(tool, small=True))
            if icon:
                child.Image = icon

            if command_id:
                if command_id.startswith('URL:'):
                    handler = _make_url_handler(command_id[4:])
                else:
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


def _make_url_handler(url):
    """Create an ICommand handler that opens a URL in the default browser."""
    try:
        import clr
        clr.AddReference('PresentationCore')
        from System.Windows.Input import ICommand

        class UrlHandler(ICommand):
            def __init__(self):
                self._url = url

            def add_CanExecuteChanged(self, handler):
                pass

            def remove_CanExecuteChanged(self, handler):
                pass

            def CanExecute(self, parameter):
                return True

            def Execute(self, parameter):
                try:
                    import webbrowser
                    webbrowser.open(self._url)
                except Exception as e:
                    log.error('Could not open URL %s: %s', self._url, e)

        return UrlHandler()
    except Exception as e:
        log.error('Failed to create URL handler: %s', e)
        return None


def _style_rst_admin_panels():
    """Find the pyRevit-created RST tab and apply light grey rounded backgrounds."""
    try:
        import clr
        clr.AddReference('AdWindows')
        from Autodesk.Windows import ComponentManager

        ribbon = ComponentManager.Ribbon
        light_grey = '#8a8e96'
        brush = _make_brush(light_grey, 0.35)

        for tab in ribbon.Tabs:
            try:
                t_title = str(tab.Title) if tab.Title else ''
                if t_title != 'RST':
                    continue
                for panel in tab.Panels:
                    try:
                        pid = str(panel.Source.Id) if panel.Source and panel.Source.Id else ''
                        # Skip our custom REST_ panels (branding + user panels)
                        if pid.startswith('REST_'):
                            continue
                        # This is a pyRevit-created panel
                        if brush:
                            panel.CustomPanelBackground = brush
                            panel.CustomPanelTitleBarBackground = brush
                        # Blank the panel title
                        try:
                            panel.Source.Title = ' '
                        except Exception:
                            pass
                        log.debug('Styled RST admin panel: %s', pid)
                    except Exception as e:
                        log.debug('Could not style panel: %s', e)
                log.info('Styled RST admin panels')
                break
            except Exception:
                continue
    except Exception as e:
        log.warning('Could not style RST admin panels: %s', e)


# --- Main startup logic ---

def _on_app_initialized(sender, args):
    """Called after Revit has fully loaded all addins and ribbon items."""
    try:
        log.info('=== RST deferred build (ApplicationInitialized) ===')

        active, profile = _load_active_profile()
        if not active or not profile:
            log.info('No active profile - nothing to build')
            return

        log.info('Active profile: %s', active.get('profile'))

        # Blank profiles always rebuild (no file to cache-check)
        if not active.get('blank'):
            profile_path = os.path.join(_profiles_dir, active.get('profile_file', ''))
            if not _needs_rebuild(active, profile_path):
                return

        # Version check
        revit_version = _get_revit_version()
        min_version = profile.get('min_version')
        if revit_version and min_version:
            try:
                if int(revit_version) < int(min_version):
                    log.warning('Revit %s is below min_version %s - aborting',
                                revit_version, min_version)
                    return
            except ValueError:
                pass

        # Build the ribbon
        if _build_ribbon(profile):
            _update_last_built(active)

        # Style the pyRevit-created RST admin panels
        _style_rst_admin_panels()

        log.info('=== RST deferred build complete ===')
    except Exception as e:
        log.error('Deferred build failed: %s', e)
        import traceback
        log.error(traceback.format_exc())


# Register for ApplicationInitialized event
log.info('=== RST startup hook - registering for ApplicationInitialized ===')
try:
    __revit__.ControlledApplication.ApplicationInitialized += _on_app_initialized  # noqa: F821
    log.info('Registered ApplicationInitialized handler')
except Exception as e:
    log.warning('Could not register ApplicationInitialized: %s', e)
    log.info('Falling back to immediate build')
    # Fallback: try building immediately (may miss late-loading addins)
    active, profile = _load_active_profile()
    if active and profile:
        profile_path = os.path.join(_profiles_dir, active.get('profile_file', ''))
        if _needs_rebuild(active, profile_path):
            if _build_ribbon(profile):
                _update_last_built(active)
    _style_rst_admin_panels()
