# -*- coding: utf-8 -*-
"""Shared reload UI — shows an animated message then triggers pyRevit reload."""
import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')

from System.Windows import (
    Window, SizeToContent, WindowStartupLocation,
    ResizeMode, Thickness, WindowStyle,
)
from System.Windows.Controls import TextBlock
from System.Windows.Media import SolidColorBrush, Color, FontFamily
from System.Windows.Threading import DispatcherTimer
from System import TimeSpan


def reload_with_message():
    """Show 'Reloading pyRevit to apply changes...' with animated dots, then reload."""
    base_text = 'Reloading pyRevit to apply changes'

    msg = TextBlock()
    msg.Text = base_text + '.'
    msg.FontFamily = FontFamily('Segoe UI')
    msg.FontSize = 13
    msg.Foreground = SolidColorBrush(Color.FromRgb(226, 232, 240))
    msg.Margin = Thickness(24, 16, 24, 16)

    win = Window()
    win.Title = 'RSTPro'
    win.Content = msg
    win.SizeToContent = SizeToContent.WidthAndHeight
    win.WindowStartupLocation = WindowStartupLocation.CenterScreen
    win.ResizeMode = ResizeMode.NoResize
    win.Background = SolidColorBrush(Color.FromRgb(22, 27, 39))
    win.Topmost = True
    try:
        win.WindowStyle = getattr(WindowStyle, 'ToolWindow')
    except Exception:
        pass

    ticks = [0]

    def on_tick(sender, args):
        ticks[0] += 1
        dots = '.' * ((ticks[0] % 3) + 1)
        msg.Text = base_text + dots
        if ticks[0] >= 3:
            timer.Stop()
            win.Close()

    timer = DispatcherTimer()
    timer.Interval = TimeSpan.FromSeconds(1)
    timer.Tick += on_tick
    timer.Start()

    win.ShowDialog()

    # Window closed — trigger reload
    from pyrevit.loader import sessionmgr
    if hasattr(sessionmgr, 'reload'):
        sessionmgr.reload()
    elif hasattr(sessionmgr, 'load_session'):
        sessionmgr.load_session()
