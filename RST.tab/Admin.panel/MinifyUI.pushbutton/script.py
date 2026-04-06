# -*- coding: utf-8 -*-
"""Minify UI — toggles pyRevit's MinifyUI to hide unused ribbon tabs."""
__title__ = 'Minify\nUI'
__doc__ = 'Toggle pyRevit Minify UI to hide unused ribbon tabs and declutter the interface.'

try:
    from pyrevit.userconfig import user_config
    from pyrevit.coreutils.ribbon import get_current_ui

    current_state = user_config.core.get_option('minifyui', default_value=False)
    new_state = not current_state
    user_config.core.minifyui = new_state
    user_config.save_changes()

    ribbon = get_current_ui()
    if new_state:
        ribbon.minify()
    else:
        ribbon.restore()

except Exception as e:
    from pyrevit import forms
    forms.alert('Could not toggle Minify UI.\n\n%s' % str(e), title='RST')
