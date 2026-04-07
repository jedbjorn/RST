# -*- coding: utf-8 -*-
"""RSTify — toggles tab visibility based on active profile config."""
__title__ = 'RSTify'
__doc__ = 'Toggle hidden tabs on/off. Configure which tabs to hide in the Profile Loader.'

import io
import os
import json

_script_dir = os.path.dirname(os.path.abspath(__file__))
_root = os.path.join(_script_dir, '..', '..', '..')
_root = os.path.normpath(_root)

import sys
sys.path.insert(0, os.path.join(_root, 'app'))
from logger import get_logger
log = get_logger('rstify')

_active_path = os.path.join(_root, 'app', 'active_profile.json')

# Read hidden tabs from active profile
hidden_tabs = []
if os.path.exists(_active_path):
    try:
        with io.open(_active_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        hidden_tabs = data.get('hidden_tabs', [])
    except Exception:
        pass

if not hidden_tabs:
    from pyrevit import forms
    forms.alert('No tabs configured to hide.\n\nSet up tab visibility in the Profile Loader.', title='RSTify')
else:
    try:
        import clr
        clr.AddReference('AdWindows')
        from Autodesk.Windows import ComponentManager

        ribbon = ComponentManager.Ribbon
        # Check current state — if any hidden tab is currently invisible, we're in hidden mode
        currently_hidden = False
        for tab in ribbon.Tabs:
            try:
                title = str(tab.Title) if tab.Title else ''
                if title in hidden_tabs and not tab.IsVisible:
                    currently_hidden = True
                    break
            except Exception:
                continue

        # Toggle: if hidden, show all. If shown, hide configured tabs.
        new_visible = currently_hidden  # if currently hidden, make visible (True)
        count = 0
        for tab in ribbon.Tabs:
            try:
                title = str(tab.Title) if tab.Title else ''
                if title in hidden_tabs:
                    tab.IsVisible = new_visible
                    count += 1
            except Exception:
                continue

        if new_visible:
            log.info('RSTify: showing %d tabs', count)
        else:
            log.info('RSTify: hiding %d tabs', count)

    except Exception as e:
        log.error('RSTify failed: %s', e)
        from pyrevit import forms
        forms.alert('RSTify failed: %s' % e, title='RSTify')
