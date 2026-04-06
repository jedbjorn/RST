# -*- coding: utf-8 -*-
"""Hide Tabs UI - CPython pywebview app.
Shows a list of tabs with checkboxes for hiding/showing.
"""
import webview
import os
import json
import sys

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_root, 'app'))
from logger import get_logger
log = get_logger('hide_tabs_ui')

_data_path = os.path.join(_root, 'app', '_tabs_data.json')
_result_path = os.path.join(_root, 'app', '_tabs_result.json')

_tabs_data = {'tabs': [], 'rstSourceTabs': []}
if os.path.exists(_data_path):
    with open(_data_path, 'r', encoding='utf-8') as f:
        _tabs_data = json.load(f)


class HideTabsAPI:

    def get_tabs(self):
        return _tabs_data

    def apply(self, hidden_list):
        log.info('Applying hidden tabs: %s', hidden_list)
        with open(_result_path, 'w', encoding='utf-8') as f:
            json.dump({'hidden': hidden_list}, f)
        for w in webview.windows:
            w.destroy()
        return {'ok': True}


HTML = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>RST - Hide Tabs</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: 'Segoe UI', sans-serif;
    background: #1e1e2e; color: #cdd6f4;
    display: flex; flex-direction: column; height: 100vh;
    user-select: none;
  }
  .header {
    padding: 14px 16px;
    background: #181825;
    border-bottom: 1px solid #313244;
    display: flex; align-items: center; justify-content: space-between;
  }
  .header-title { font-size: 13px; font-weight: 600; letter-spacing: 0.05em; }
  .mode-switch {
    display: flex; border-radius: 4px; overflow: hidden;
    border: 1px solid #313244;
  }
  .mode-btn {
    padding: 4px 12px; font-size: 10px; font-weight: 500;
    cursor: pointer; border: none; transition: all 0.15s;
    background: transparent; color: #6c7086;
  }
  .mode-btn.active { background: #f38ba8; color: #1e1e2e; }
  .mode-btn:first-child.active { background: #f38ba8; }
  .mode-btn:last-child.active { background: #a6e3a1; color: #1e1e2e; }
  .list { flex: 1; overflow-y: auto; padding: 4px 0; }
  .tab-row {
    display: flex; align-items: center; gap: 10px;
    padding: 7px 16px; cursor: pointer;
    transition: background 0.1s; font-size: 12px;
  }
  .tab-row:hover { background: #313244; }
  .tab-row.protected { opacity: 0.35; cursor: default; }
  .tab-row.rst-action {
    background: #1a1a2e; border-bottom: 1px solid #313244;
    padding: 10px 16px; font-weight: 500;
  }
  .tab-row.rst-action:hover { background: #252540; }
  .cb {
    width: 16px; height: 16px; border-radius: 3px;
    border: 1.5px solid #585b70;
    display: flex; align-items: center; justify-content: center;
    font-size: 10px; flex-shrink: 0; transition: all 0.15s;
  }
  .cb.checked { border-color: #f38ba8; color: #f38ba8; background: rgba(243,139,168,0.1); }
  .tab-name { flex: 1; }
  .tab-badge {
    font-size: 9px; padding: 1px 6px; border-radius: 3px;
    background: rgba(245,158,11,0.15); color: #f59e0b;
  }
  .sep { height: 1px; background: #313244; margin: 4px 0; }
  .footer {
    padding: 10px 16px;
    border-top: 1px solid #313244;
    background: #181825;
    display: flex; gap: 8px; justify-content: flex-end;
  }
  .btn {
    padding: 7px 18px; border-radius: 4px; font-size: 11px;
    font-weight: 500; cursor: pointer; border: 1px solid #313244;
    transition: all 0.15s;
  }
  .btn-cancel { background: transparent; color: #6c7086; }
  .btn-cancel:hover { border-color: #585b70; color: #cdd6f4; }
  .btn-apply { background: #a6e3a1; color: #1e1e2e; border-color: #a6e3a1; }
  .btn-apply:hover { background: #94e2d5; border-color: #94e2d5; }
  .list::-webkit-scrollbar { width: 6px; }
  .list::-webkit-scrollbar-track { background: transparent; }
  .list::-webkit-scrollbar-thumb { background: #45475a; border-radius: 3px; }
</style>
</head>
<body>

<div class="header">
  <span class="header-title">Hide Tabs</span>
  <div class="mode-switch">
    <button class="mode-btn active" id="modeHide" onclick="setMode('hide')">Hide</button>
    <button class="mode-btn" id="modeShow" onclick="setMode('show')">Unhide</button>
  </div>
</div>

<div class="list" id="tabList"></div>

<div class="footer">
  <button class="btn btn-cancel" onclick="cancel()">Cancel</button>
  <button class="btn btn-apply" onclick="apply()">Apply</button>
</div>

<script>
  var tabs = [];
  var rstSourceTabs = [];
  var hiddenSet = {};
  var mode = 'hide'; // 'hide' or 'show'
  var PROTECTED = ['RST', 'File'];

  function setMode(m) {
    mode = m;
    document.getElementById('modeHide').className = 'mode-btn' + (m === 'hide' ? ' active' : '');
    document.getElementById('modeShow').className = 'mode-btn' + (m === 'show' ? ' active' : '');
    render();
  }

  function render() {
    var list = document.getElementById('tabList');
    var html = '';

    // First row: "Hide tabs on RST" action checkbox
    var rstChecked = rstSourceTabs.length > 0 && rstSourceTabs.every(function(t) {
      return t === 'Add-Ins' || PROTECTED.indexOf(t) >= 0 || !!hiddenSet[t];
    });
    html += '<div class="tab-row rst-action" onclick="toggleRstTabs()">' +
      '<div class="cb' + (rstChecked ? ' checked' : '') + '">' + (rstChecked ? '\u2715' : '') + '</div>' +
      '<span class="tab-name">Hide tabs on RST</span>' +
      '<span class="tab-badge">' + rstSourceTabs.length + ' tabs</span>' +
    '</div>';

    html += '<div class="sep"></div>';

    // Tab list
    var filtered = tabs;
    if (mode === 'show') {
      filtered = tabs.filter(function(t) { return !!hiddenSet[t.title]; });
    }

    filtered.forEach(function(tab) {
      var isProtected = PROTECTED.indexOf(tab.title) >= 0;
      var isHidden = !!hiddenSet[tab.title];
      var inRst = tab.inRst;

      var cls = 'tab-row';
      if (isProtected) cls += ' protected';

      var cbCls = 'cb';
      if (isHidden) cbCls += ' checked';

      var badge = inRst ? '<span class="tab-badge">in RST</span>' : '';
      var onclick = isProtected ? '' : "toggleTab('" + tab.title.replace(/'/g, "\\'") + "')";

      html += '<div class="' + cls + '" onclick="' + onclick + '">' +
        '<div class="' + cbCls + '">' + (isHidden ? '\u2715' : '') + '</div>' +
        '<span class="tab-name">' + tab.title + '</span>' +
        badge +
      '</div>';
    });

    if (mode === 'show' && filtered.length === 0) {
      html += '<div style="padding:20px 16px;color:#6c7086;font-size:11px;text-align:center">No hidden tabs</div>';
    }

    list.innerHTML = html;
  }

  function toggleTab(title) {
    if (hiddenSet[title]) {
      delete hiddenSet[title];
    } else {
      hiddenSet[title] = true;
    }
    render();
  }

  function toggleRstTabs() {
    // Check if all RST tabs are already hidden
    var allHidden = rstSourceTabs.every(function(t) {
      return t === 'Add-Ins' || PROTECTED.indexOf(t) >= 0 || !!hiddenSet[t];
    });

    if (allHidden) {
      // Unhide all RST tabs
      rstSourceTabs.forEach(function(t) {
        if (PROTECTED.indexOf(t) < 0) {
          delete hiddenSet[t];
        }
      });
    } else {
      // Hide all RST tabs except Add-Ins and protected
      rstSourceTabs.forEach(function(t) {
        if (t !== 'Add-Ins' && PROTECTED.indexOf(t) < 0) {
          hiddenSet[t] = true;
        }
      });
    }
    render();
  }

  function cancel() {
    window.close();
  }

  function apply() {
    var hidden = Object.keys(hiddenSet);
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.apply(hidden);
    }
  }

  window.addEventListener('pywebviewready', function() {
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.get_tabs().then(function(data) {
        tabs = data.tabs || [];
        rstSourceTabs = data.rstSourceTabs || [];
        // Pre-check currently hidden tabs
        tabs.forEach(function(t) {
          if (!t.visible && PROTECTED.indexOf(t.title) < 0) {
            hiddenSet[t.title] = true;
          }
        });
        render();
      });
    }
  });
</script>
</body>
</html>"""


if __name__ == '__main__':
    log.info('=== Hide Tabs UI starting ===')
    api = HideTabsAPI()

    try:
        import ctypes
        user32 = ctypes.windll.user32
        sw = user32.GetSystemMetrics(0)
        sh = user32.GetSystemMetrics(1)
        wx, wy = (sw - 300) // 2, (sh - 600) // 2
    except Exception:
        wx, wy = None, None

    window = webview.create_window(
        'RST - Hide Tabs',
        html=HTML,
        width=350,
        height=600,
        x=wx,
        y=wy,
        resizable=False,
        on_top=True,
        js_api=api
    )
    webview.start()
    log.info('=== Hide Tabs UI closed ===')
