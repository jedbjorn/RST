/**
 * rst_messages.js — Reusable message overlays for RST UI.
 *
 * Three message types:
 *   RSTmsgConfirm(title, body)  — modal with Continue / Cancel. Returns a Promise (true/false).
 *   RSTmsgInform(title, body)   — auto-dismiss after 3 seconds.
 *   RSTmsgWait(title, body)     — loading overlay with ticking dots. Call RSTmsgWaitClose() to dismiss.
 */

(function () {
  // ── Inject styles once ──────────────────────────────────────────────────────
  var style = document.createElement('style');
  style.textContent = [
    '.rst-msg-overlay {',
    '  position: fixed; inset: 0;',
    '  background: rgba(0,0,0,0.55);',
    '  display: flex; align-items: center; justify-content: center;',
    '  z-index: 9000;',
    '  opacity: 0; pointer-events: none;',
    '  transition: opacity 0.2s;',
    '}',
    '.rst-msg-overlay.visible { opacity: 1; pointer-events: auto; }',
    '.rst-msg-card {',
    '  background: var(--surface, #1e1e2e);',
    '  border-radius: 12px;',
    '  padding: 28px 32px;',
    '  max-width: 460px;',
    '  width: 90%;',
    '  box-shadow: 0 12px 40px rgba(0,0,0,0.4);',
    '  text-align: center;',
    '}',
    '.rst-msg-title {',
    '  font-family: "DM Mono", monospace;',
    '  font-size: 13px;',
    '  font-weight: 600;',
    '  color: var(--text1, #e2e8f0);',
    '  margin-bottom: 8px;',
    '}',
    '.rst-msg-body {',
    '  font-family: "DM Mono", monospace;',
    '  font-size: 10px;',
    '  color: var(--text3, #94a3b8);',
    '  line-height: 1.6;',
    '  margin-bottom: 20px;',
    '}',
    '.rst-msg-actions {',
    '  display: flex;',
    '  gap: 10px;',
    '  justify-content: center;',
    '}',
    '.rst-msg-btn {',
    '  font-family: "DM Mono", monospace;',
    '  font-size: 10px;',
    '  letter-spacing: 0.06em;',
    '  text-transform: uppercase;',
    '  border: none;',
    '  border-radius: 6px;',
    '  padding: 8px 20px;',
    '  cursor: pointer;',
    '  transition: background 0.15s;',
    '}',
    '.rst-msg-btn-cancel {',
    '  background: var(--surface3, #2a2a3e);',
    '  color: var(--text3, #94a3b8);',
    '  border: 1px solid var(--border, #334155);',
    '}',
    '.rst-msg-btn-cancel:hover { background: var(--surface2, #333348); }',
    '.rst-msg-btn-continue {',
    '  background: var(--accent, #197AFF);',
    '  color: #fff;',
    '}',
    '.rst-msg-btn-continue:hover { opacity: 0.9; }',
    '.rst-msg-body-nomargin { margin-bottom: 0; }',
  ].join('\n');
  document.head.appendChild(style);

  // ── Overlay management ──────────────────────────────────────────────────────

  function _createOverlay(id) {
    var existing = document.getElementById(id);
    if (existing) existing.remove();
    var overlay = document.createElement('div');
    overlay.className = 'rst-msg-overlay';
    overlay.id = id;
    var card = document.createElement('div');
    card.className = 'rst-msg-card';
    overlay.appendChild(card);
    document.body.appendChild(overlay);
    return { overlay: overlay, card: card };
  }

  function _show(overlay) {
    // Force reflow before adding visible class for transition
    overlay.offsetHeight;
    overlay.classList.add('visible');
  }

  function _hide(overlay) {
    overlay.classList.remove('visible');
    setTimeout(function () { overlay.remove(); }, 200);
  }

  // ── RSTmsgConfirm ─────────────────────────────────────────────────────────
  // Returns a Promise that resolves true (Continue) or false (Cancel).

  window.RSTmsgConfirm = function (title, body) {
    return new Promise(function (resolve) {
      var el = _createOverlay('rst-msg-confirm');

      el.card.innerHTML =
        '<div class="rst-msg-title"></div>' +
        '<div class="rst-msg-body"></div>' +
        '<div class="rst-msg-actions">' +
        '  <button class="rst-msg-btn rst-msg-btn-cancel" id="rstConfirmCancel">Cancel</button>' +
        '  <button class="rst-msg-btn rst-msg-btn-continue" id="rstConfirmContinue">Continue</button>' +
        '</div>';

      el.card.querySelector('.rst-msg-title').textContent = title;
      el.card.querySelector('.rst-msg-body').textContent = body;

      document.getElementById('rstConfirmCancel').onclick = function () {
        _hide(el.overlay);
        resolve(false);
      };
      document.getElementById('rstConfirmContinue').onclick = function () {
        _hide(el.overlay);
        resolve(true);
      };

      _show(el.overlay);
    });
  };

  // ── RSTmsgInform ──────────────────────────────────────────────────────────
  // Shows a message, auto-dismisses after 3 seconds.

  window.RSTmsgInform = function (title, body) {
    var el = _createOverlay('rst-msg-inform');

    el.card.innerHTML =
      '<div class="rst-msg-title"></div>' +
      '<div class="rst-msg-body rst-msg-body-nomargin"></div>';

    el.card.querySelector('.rst-msg-title').textContent = title;
    el.card.querySelector('.rst-msg-body').textContent = body;

    _show(el.overlay);

    setTimeout(function () {
      _hide(el.overlay);
    }, 3000);
  };

  // ── RSTmsgWait ────────────────────────────────────────────────────────────
  // Loading overlay with ticking dots. Call RSTmsgWaitClose() to dismiss.

  var _waitTimer = null;

  window.RSTmsgWait = function (title, body) {
    // Close any existing wait overlay
    if (_waitTimer) {
      clearInterval(_waitTimer);
      _waitTimer = null;
    }

    var el = _createOverlay('rst-msg-wait');

    el.card.innerHTML =
      '<div class="rst-msg-title" id="rstWaitTitle"></div>' +
      '<div class="rst-msg-body rst-msg-body-nomargin" id="rstWaitBody"></div>';

    var titleEl = document.getElementById('rstWaitTitle');
    var bodyEl = document.getElementById('rstWaitBody');

    var baseTitle = title;
    titleEl.textContent = baseTitle + '.';
    bodyEl.textContent = body || '';

    var ticks = 0;
    _waitTimer = setInterval(function () {
      ticks++;
      titleEl.textContent = baseTitle + '.'.repeat((ticks % 3) + 1);
    }, 600);

    _show(el.overlay);
  };

  window.RSTmsgWaitClose = function () {
    if (_waitTimer) {
      clearInterval(_waitTimer);
      _waitTimer = null;
    }
    var overlay = document.getElementById('rst-msg-wait');
    if (overlay) _hide(overlay);
  };

})();
