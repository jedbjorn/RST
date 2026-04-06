# -*- coding: utf-8 -*-
"""Minify UI — triggers pyRevit's MinifyUI toggle."""
__title__ = 'Minify\nUI'
__doc__ = 'Toggle pyRevit Minify UI to hide unused ribbon tabs and declutter the interface.'

from Autodesk.Revit.UI import RevitCommandId

cmd_id = 'CustomCtrl_%CustomCtrl_%pyRevit%Toggles%MinifyUI'
cmd = RevitCommandId.LookupCommandId(cmd_id)
if cmd:
    __revit__.PostCommand(cmd)
