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

# Load tab data
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
        # Close the window
        for w in webview.windows:
            w.destroy()
        return {'ok': True}


HTML = """<!DOCTYPE html>
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
    font-size: 13px; font-weight: 600;
    letter-spacing: 0.05em;
  }
  .quick-action {
    padding: 10px 16px;
    background: #1a1a2e;
    border-bottom: 1px solid #313244;
  }
  .quick-btn {
    width: 100%;
    padding: 8px 12px;
    background: rgba(245, 158, 11, 0.1);
    border: 1px solid rgba(245, 158, 11, 0.4);
    border-radius: 4px;
    color: #f59e0b;
    font-size: 11px; font-weight: 500;
    cursor: pointer;
    text-align: left;
    transition: all 0.15s;
  }
  .quick-btn:hover { background: rgba(245, 158, 11, 0.2); }
  .quick-desc {
    font-size: 9px; color: #6c7086;
    margin-top: 4px; padding-left: 2px;
  }
  .list {
    flex: 1; overflow-y: auto; padding: 6px 0;
  }
  .tab-row {
    display: flex; align-items: center; gap: 10px;
    padding: 7px 16px;
    cursor: pointer;
    transition: background 0.1s;
    font-size: 12px;
  }
  .tab-row:hover { background: #313244; }
  .tab-row.protected { opacity: 0.4; cursor: default; }
  .tab-row.in-rst { }
  .cb {
    width: 16px; height: 16px; border-radius: 3px;
    border: 1.5px solid #585b70;
    display: flex; align-items: center; justify-content: center;
    font-size: 10px; color: #a6e3a1; flex-shrink: 0;
    transition: all 0.15s;
  }
  .cb.checked { border-color: #a6e3a1; background: rgba(166,227,161,0.1); }
  .cb.hidden-cb { border-color: #f38ba8; color: #f38ba8; }
  .cb.hidden-cb.checked { background: rgba(243,139,168,0.1); }
  .tab-name { flex: 1; }
  .tab-badge {
    font-size: 9px; padding: 1px 6px; border-radius: 3px;
    background: rgba(137,180,250,0.15); color: #89b4fa;
  }
  .tab-badge.rst { background: rgba(245,158,11,0.15); color: #f59e0b; }
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

<div class="header">Hide Tabs</div>

<div class="quick-action">
  <button class="quick-btn" onclick="hideRstTabs()">Hide tabs with tools on RST</button>
  <div class="quick-desc">Hides add-in tabs that have tools placed in your RST profile</div>
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

  function render() {
    var list = document.getElementById('tabList');
    list.innerHTML = tabs.map(function(tab, i) {
      var isProtected = tab.title === 'RST' || tab.title === 'File';
      var isHidden = !!hiddenSet[tab.title];
      var inRst = tab.inRst;
      var cls = 'tab-row';
      if (isProtected) cls += ' protected';
      if (inRst) cls += ' in-rst';

      var cbCls = 'cb hidden-cb';
      if (isHidden) cbCls += ' checked';

      var badge = '';
      if (inRst) badge = '<span class="tab-badge rst">in RST</span>';

      return '<div class="' + cls + '" onclick="' + (isProtected ? '' : 'toggleTab(\\'' + tab.title.replace(/'/g, "\\\\'") + '\\')') + '">' +
        '<div class="' + cbCls + '">' + (isHidden ? '\\u2715' : '') + '</div>' +
        '<span class="tab-name">' + tab.title + '</span>' +
        badge +
      '</div>';
    }).join('');
  }

  function toggleTab(title) {
    if (hiddenSet[title]) {
      delete hiddenSet[title];
    } else {
      hiddenSet[title] = true;
    }
    render();
  }

  function hideRstTabs() {
    rstSourceTabs.forEach(function(t) {
      if (t !== 'RST' && t !== 'File') {
        hiddenSet[t] = true;
      }
    });
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

  // Init
  window.addEventListener('pywebviewready', function() {
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.get_tabs().then(function(data) {
        tabs = data.tabs || [];
        rstSourceTabs = data.rstSourceTabs || [];
        // Pre-check currently hidden tabs
        tabs.forEach(function(t) {
          if (!t.visible && t.title !== 'RST' && t.title !== 'File') {
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
        width=300,
        height=600,
        x=wx,
        y=wy,
        resizable=False,
        on_top=True,
        js_api=api
    )
    webview.start()
    log.info('=== Hide Tabs UI closed ===')
