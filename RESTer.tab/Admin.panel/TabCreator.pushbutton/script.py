# -*- coding: utf-8 -*-
"""TabCreator - PyRevit pushbutton script.
Opens profile_manager.html in a pywebview window inside Revit.
"""
import os
import sys
import json
import shutil
import subprocess
import webview

_script_dir = os.path.dirname(os.path.abspath(__file__))
_root = os.path.join(_script_dir, '..', '..', '..')
_root = os.path.normpath(_root)

_html_path = os.path.join(_root, 'ui', 'profile_manager.html')
_profiles_dir = os.path.join(_root, 'app', 'profiles')
_icons_dir = os.path.join(_root, 'icons')

# Ensure dirs exist
os.makedirs(_profiles_dir, exist_ok=True)
os.makedirs(_icons_dir, exist_ok=True)

# Logger
sys.path.insert(0, os.path.join(_root, 'app'))
from logger import get_logger
log = get_logger('tab_creator')


def _get_revit_app():
    """Return the Revit application object (available in PyRevit context)."""
    try:
        return __revit__  # noqa: F821 — provided by PyRevit runtime
    except NameError:
        return None


class TabCreatorAPI:

    def get_revit_version(self):
        """Read the active Revit version from the running instance."""
        app = _get_revit_app()
        if app:
            ver = str(app.Application.VersionNumber)
            log.info('Revit version: %s', ver)
            return ver
        log.warning('Revit app not available — returning None')
        return None

    def get_installed_commands(self):
        """Walk the Revit ribbon via AdWindows.dll and collect all commands."""
        log.info('Scanning Revit ribbon for commands...')
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

        log.info('Found %d commands', len(results))
        return results

    def save_export(self, json_str):
        """Save profile JSON to app/profiles/ and copy to Desktop."""
        log.info('Exporting profile')
        try:
            profile = json.loads(json_str)
        except json.JSONDecodeError as e:
            log.error('Invalid export JSON: %s', e)
            return {'ok': False, 'error': 'Invalid JSON: ' + str(e)}

        profile_name = profile.get('profile', 'Untitled')
        export_date = profile.get('exportDate', 'unknown')
        filename = '{}_{}.json'.format(profile_name, export_date)

        # Overwrite existing profile with same name
        for fname in os.listdir(_profiles_dir):
            if fname.endswith('.json'):
                try:
                    with open(os.path.join(_profiles_dir, fname), 'r') as f:
                        existing = json.load(f)
                    if existing.get('profile') == profile_name:
                        os.remove(os.path.join(_profiles_dir, fname))
                        log.info('Overwriting existing: %s', fname)
                        break
                except (json.JSONDecodeError, IOError):
                    continue

        # Save to profiles dir
        dest_path = os.path.join(_profiles_dir, filename)
        with open(dest_path, 'w') as f:
            f.write(json_str)
        log.info('Saved to: %s', dest_path)

        # Copy to Desktop
        desktop = os.path.join(os.environ.get('USERPROFILE', ''), 'Desktop')
        desktop_path = None
        if os.path.isdir(desktop):
            desktop_path = os.path.join(desktop, filename)
            shutil.copy2(dest_path, desktop_path)
            log.info('Copied to Desktop: %s', desktop_path)

        return {'ok': True, 'path': dest_path, 'desktop_path': desktop_path}

    def pick_icon(self, tool_name):
        """Open file dialog for PNG, copy to icons/ as {toolName}.png."""
        log.info('Picking icon for tool: %s', tool_name)
        result = webview.windows[0].create_file_dialog(
            webview.OPEN_DIALOG,
            file_types=('PNG Images (*.png)',)
        )
        if not result:
            log.debug('Icon pick cancelled')
            return None

        src_path = result[0] if isinstance(result, (list, tuple)) else result

        # Determine filename with collision handling
        base_name = tool_name + '.png'
        dest_path = os.path.join(_icons_dir, base_name)
        counter = 1
        while os.path.exists(dest_path):
            base_name = '{}({}).png'.format(tool_name, counter)
            dest_path = os.path.join(_icons_dir, base_name)
            counter += 1

        shutil.copy2(src_path, dest_path)
        log.info('Icon saved: %s', base_name)
        return {'filename': base_name}

    def get_profiles(self):
        """List available profiles for the dropdown."""
        profiles = []
        for fname in os.listdir(_profiles_dir):
            if fname.endswith('.json'):
                try:
                    with open(os.path.join(_profiles_dir, fname), 'r') as f:
                        data = json.load(f)
                    profiles.append(data.get('profile', fname))
                except (json.JSONDecodeError, IOError):
                    continue
        log.info('Available profiles: %s', profiles)
        return profiles

    def load_profile_into_editor(self, profile_name):
        """Read profile JSON from app/profiles/, return full profile object."""
        log.info('Loading profile into editor: %s', profile_name)
        for fname in os.listdir(_profiles_dir):
            if fname.endswith('.json'):
                fpath = os.path.join(_profiles_dir, fname)
                try:
                    with open(fpath, 'r') as f:
                        data = json.load(f)
                    if data.get('profile') == profile_name:
                        log.info('Found profile: %s', fname)
                        return data
                except (json.JSONDecodeError, IOError):
                    continue
        log.error('Profile not found: %s', profile_name)
        return None

    def open_profiles_folder(self):
        """Open app/profiles/ in Windows Explorer."""
        log.info('Opening profiles folder: %s', _profiles_dir)
        subprocess.Popen(['explorer', os.path.normpath(_profiles_dir)])
        return {'ok': True}


# PyRevit entry point
log.info('TabCreator script loaded')
api = TabCreatorAPI()
window = webview.create_window(
    'RESTer — Tab Creator',
    url=_html_path,
    width=1200,
    height=800,
    resizable=True,
    js_api=api
)
webview.start()
log.info('TabCreator window closed')
