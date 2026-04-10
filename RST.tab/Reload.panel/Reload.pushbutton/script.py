# -*- coding: utf-8 -*-
"""Reload — triggers pyRevit reload."""
__title__ = 'Reload'
__doc__ = 'Reload pyRevit to apply profile changes and refresh the ribbon.'

from Autodesk.Revit.UI import RevitCommandId

cmd_id = 'CustomCtrl_%CustomCtrl_%pyRevit%pyRevit%Reload'
cmd = RevitCommandId.LookupCommandId(cmd_id)
if cmd:
    __revit__.PostCommand(cmd)
else:
    from pyrevit import forms
    forms.alert('Reload command not found.\nEnsure pyRevit is installed.', title='RST')
