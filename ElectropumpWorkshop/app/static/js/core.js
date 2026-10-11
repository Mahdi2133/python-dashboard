/* ==========================================================================
   Shared front-end helpers: API client, toast, modal, small DOM utilities.
   ========================================================================== */
(function (global) {
  'use strict';

  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
  }

  /* Every API call funnels through here so a failure is reported in Persian
     once, in one place, instead of surfacing as an unhandled rejection. */
  async function request(url, options) {
    options = options || {};
    var headers = Object.assign({ 'X-Requested-With': 'fetch' }, options.headers || {});
    if (options.json !== undefined) {
      headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(options.json);
      delete options.json;
    }
    if (!['GET', 'HEAD'].includes((options.method || 'GET').toUpperCase())) {
      headers['X-CSRFToken'] = csrfToken();
    }
    options.headers = headers;

    var response;
    try {
      response = await fetch(url, options);
    } catch (err) {
      throw { message: 'ارتباط با سرور برقرار نشد. آیا سرور در حال اجراست؟', network: true };
    }
    var payload = null;
    var text = await response.text();
    if (text) {
      try { payload = JSON.parse(text); } catch (e) { payload = null; }
    }
    if (!response.ok || (payload && payload.ok === false)) {
      throw {
        message: (payload && payload.error) || ('خطای سرور (' + response.status + ')'),
        status: response.status,
        fields: payload && payload.fields,
        payload: payload
      };
    }
    return payload;
  }

  /* Mirrors AppUser.can() on the server: admins may do everything. */
  function can(permission) {
    if (window.IS_ADMIN) return true;
    return (window.CAN || []).indexOf(permission) >= 0;
  }

  var api = {
    get: function (url) { return request(url); },
    post: function (url, data) { return request(url, { method: 'POST', json: data }); },
    put: function (url, data) { return request(url, { method: 'PUT', json: data }); },
    del: function (url) { return request(url, { method: 'DELETE' }); },
    upload: function (url, formData) {
      return request(url, { method: 'POST', body: formData });
    }
  };

  var toastTimer = null;
  function toast(message, kind) {
    var el = document.getElementById('toast');
    if (!el) { return; }
    el.textContent = message;
    el.className = 'toast show' + (kind ? ' ' + kind : '');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.classList.remove('show'); }, 4200);
  }

  /* Promise-based confirm so callers can `await confirmDialog(...)`. */
  function confirmDialog(opts) {
    return new Promise(function (resolve) {
      var overlay = document.getElementById('confirm-modal');
      overlay.querySelector('#modal-title').textContent = opts.title || 'تأیید عملیات';
      overlay.querySelector('#modal-msg').textContent = opts.message || 'آیا مطمئن هستید؟';
      var okBtn = overlay.querySelector('#modal-confirm-btn');
      okBtn.textContent = opts.confirmText || 'تأیید';
      okBtn.className = opts.danger === false ? 'btn-primary' : 'btn-danger';
      function cleanup(result) {
        overlay.classList.remove('show');
        okBtn.onclick = null;
        cancel.onclick = null;
        resolve(result);
      }
      var cancel = overlay.querySelector('#modal-cancel-btn');
      okBtn.onclick = function () { cleanup(true); };
      cancel.onclick = function () { cleanup(false); };
      overlay.classList.add('show');
    });
  }

  /* «جایگزین کنم یا اضافه؟» before a file goes into a data bank: resolves to
     'replace', 'append', or null when the person cancels. ``opts``: title,
     message, replaceText/appendText (what each choice does to this bank),
     preferred ('replace' | 'append' — the highlighted one). */
  function chooseImportMode(opts) {
    opts = opts || {};
    return new Promise(function (resolve) {
      var old = document.getElementById('import-mode-modal');
      if (old) old.remove();
      var box = document.createElement('div');
      box.className = 'modal-overlay show';
      box.id = 'import-mode-modal';
      var pick = function (mode, cls, title, text) {
        return '<button type="button" class="im-choice ' + cls + (opts.preferred === mode ? ' im-preferred' : '')
          + '" data-mode="' + mode + '"><b>' + esc(title) + '</b><span>' + esc(text) + '</span></button>';
      };
      box.innerHTML = '<div class="modal im-modal"><h3>' + esc(opts.title || 'ورود فایل به بانک اطلاعاتی') + '</h3>'
        + '<p>' + esc(opts.message || 'اطلاعات این فایل جایگزین اطلاعات فعلی شود یا به آن اضافه شود؟') + '</p>'
        + '<div class="im-choices">'
        + pick('replace', 'im-replace', '♻ جایگزینی کامل',
               opts.replaceText || 'همه‌ی ردیف‌های فعلی این بانک پاک و فقط ردیف‌های فایل نگه داشته می‌شود.')
        + pick('append', 'im-append', '➕ افزودن / به‌روزرسانی',
               opts.appendText || 'ردیف‌های تازه اضافه و ردیف‌های تکراری با فایل به‌روز می‌شوند؛ بقیه می‌مانند.')
        + '</div><div class="modal-actions"><button type="button" class="btn-secondary" data-mode="">انصراف</button></div></div>';
      document.body.appendChild(box);
      box.addEventListener('click', function (ev) {
        var b = ev.target.closest('[data-mode]');
        if (!b && ev.target !== box) return;
        box.remove();
        resolve(b && b.dataset.mode ? b.dataset.mode : null);
      });
    });
  }

  function openModal(id) { document.getElementById(id).classList.add('show'); }
  function closeModal(id) {
    var el = document.getElementById(id);
    if (el) el.classList.remove('show');
  }

  /* Every dialog closes the same three ways: its × or «انصراف» (anything
     marked data-close="<dialog id>"), the Escape key, and a click on the dark
     backdrop around it. The start-process dialog had the buttons but nothing
     listening to them — it only ever closed when a start succeeded, so the
     second time somebody opened it just to look, it would not go away.

     The confirmation dialog is left out on purpose: it answers a question
     with a promise, and closing it any other way would leave that question
     hanging. */
  function closableModal(el) {
    return el && el.classList.contains('modal-overlay')
      && el.id !== 'confirm-modal' && el.id !== 'import-mode-modal';
  }
  document.addEventListener('click', function (ev) {
    var closer = ev.target.closest('[data-close]');
    if (closer) {
      var target = document.getElementById(closer.dataset.close);
      if (closableModal(target)) {
        ev.preventDefault();
        target.classList.remove('show');
        return;
      }
    }
    if (closableModal(ev.target) && ev.target.classList.contains('show')) {
      ev.target.classList.remove('show');       // the backdrop itself
    }
  });
  document.addEventListener('keydown', function (ev) {
    if (ev.key !== 'Escape') return;
    var open = Array.prototype.slice.call(
      document.querySelectorAll('.modal-overlay.show')).filter(closableModal);
    if (open.length) open[open.length - 1].classList.remove('show');
  });

  /* Never build HTML from data without going through this. */
  function esc(value) {
    if (value === null || value === undefined) return '';
    return String(value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(function (entry) {
      var key = entry[0], value = entry[1];
      if (value === null || value === undefined || value === false) return;
      if (key === 'class') node.className = value;
      else if (key === 'text') node.textContent = value;
      else if (key === 'html') node.innerHTML = value;
      else if (key.startsWith('on') && typeof value === 'function') {
        node.addEventListener(key.slice(2).toLowerCase(), value);
      } else if (key === 'dataset') Object.assign(node.dataset, value);
      else node.setAttribute(key, value);
    });
    (children || []).forEach(function (child) {
      if (child) node.appendChild(typeof child === 'string'
        ? document.createTextNode(child) : child);
    });
    return node;
  }

  function qs(sel, root) { return (root || document).querySelector(sel); }
  function qsa(sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  }

  function debounce(fn, wait) {
    var timer = null;
    return function () {
      var args = arguments, self = this;
      clearTimeout(timer);
      timer = setTimeout(function () { fn.apply(self, args); }, wait || 250);
    };
  }

  function serializeQuery(params) {
    var search = new URLSearchParams();
    Object.entries(params || {}).forEach(function (entry) {
      if (entry[1] !== '' && entry[1] !== null && entry[1] !== undefined) {
        search.append(entry[0], entry[1]);
      }
    });
    return search.toString();
  }

  function renderBarChart(container, data, emptyText) {
    if (typeof container === 'string') container = document.getElementById(container);
    if (!container) return;
    if (!data || !data.length) {
      container.innerHTML = '<p class="chart-empty">' + (emptyText || 'داده‌ای وجود ندارد') + '</p>';
      return;
    }
    var max = Math.max.apply(null, data.map(function (d) { return d.value || 0; })) || 1;
    container.innerHTML = data.map(function (d) {
      var pct = Math.max(Math.round((d.value || 0) / max * 100), d.value ? 3 : 0);
      return '<div class="bar-row">'
        + '<div class="bar-label" title="' + esc(d.label) + '">' + esc(d.label) + '</div>'
        + '<div class="bar-track"><div class="bar-fill" style="width:' + pct + '%">'
        + '<span class="bar-val">' + esc(d.value) + '</span></div></div></div>';
    }).join('');
  }

  /* Downloads must carry the CSRF header, so they go through fetch + blob
     rather than a bare link. */
  async function download(url, options) {
    try {
      var response = await fetch(url, Object.assign({
        headers: { 'X-CSRFToken': csrfToken() }
      }, options || {}));
      if (!response.ok) {
        var body = await response.text();
        var message = 'تهیه خروجی ناموفق بود.';
        try { message = JSON.parse(body).error || message; } catch (e) { /* keep default */ }
        toast(message, 'error');
        return;
      }
      var blob = await response.blob();
      var disposition = response.headers.get('Content-Disposition') || '';
      var match = /filename="?([^";]+)"?/.exec(disposition);
      var link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = match ? decodeURIComponent(match[1]) : 'export';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      setTimeout(function () { URL.revokeObjectURL(link.href); }, 4000);
      toast('فایل خروجی دانلود شد.');
    } catch (err) {
      toast('ارتباط با سرور برقرار نشد.', 'error');
    }
  }

  function downloadPost(url, data) {
    return download(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
      body: JSON.stringify(data)
    });
  }

  function fmtNumber(value) {
    if (value === null || value === undefined || value === '') return '';
    if (typeof value !== 'number') return value;
    return value.toLocaleString('fa-IR', { maximumFractionDigits: 3 });
  }

  /* ── the side nav ───────────────────────────────────────────────────── */
  /* The page's tabs run down the right-hand edge. Two things have to be kept
     honest from here: where the column starts (the header is sticky and wraps
     to two lines at some widths, so its height is measured rather than
     guessed) and whether the column is folded away (remembered per browser,
     because it is a preference about this screen, not about the data). */
  var NAV_KEY = 'ew.nav.collapsed';

  function measureHeader() {
    var header = document.querySelector('.app-header');
    if (!header) return;
    document.documentElement.style.setProperty(
      '--header-h', Math.round(header.getBoundingClientRect().height) + 'px');
  }

  function setupNav() {
    var toggle = document.getElementById('nav-toggle');
    var scrim = document.getElementById('nav-scrim');
    if (!toggle) return;
    var wide = function () { return window.innerWidth > 900; };

    var collapsed = false;
    try { collapsed = localStorage.getItem(NAV_KEY) === '1'; } catch (err) { }
    document.body.classList.toggle('nav-collapsed', collapsed);
    toggle.setAttribute('aria-expanded', String(!collapsed));

    function close() {
      document.body.classList.remove('nav-open');
      if (scrim) scrim.hidden = true;
      toggle.setAttribute('aria-expanded', 'false');
    }

    toggle.addEventListener('click', function () {
      if (wide()) {
        // On a wide screen the column folds to its icons and stays put.
        var now = !document.body.classList.contains('nav-collapsed');
        document.body.classList.toggle('nav-collapsed', now);
        toggle.setAttribute('aria-expanded', String(!now));
        try { localStorage.setItem(NAV_KEY, now ? '1' : '0'); } catch (err) { }
      } else {
        // On a narrow one it slides over the page, so it needs a way out.
        var open = !document.body.classList.contains('nav-open');
        document.body.classList.toggle('nav-open', open);
        if (scrim) scrim.hidden = !open;
        toggle.setAttribute('aria-expanded', String(open));
      }
    });
    if (scrim) scrim.addEventListener('click', close);
    document.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape' && document.body.classList.contains('nav-open')) {
        close();
      }
    });
    window.addEventListener('resize', function () {
      if (wide()) close();
    });
  }

  /* After an update the files on disk are new while the server window may
     still be running the old code: pages look new, but nothing new works.
     A server that does not even know /api/build predates this check, so it
     is old by definition. Say so in one line at the top of every page. */
  function checkBuild() {
    if (!window.fetch) return;
    fetch('/api/build', { credentials: 'same-origin' }).then(function (r) {
      if (r.status === 404) return { stale: true };
      return r.ok ? r.json().then(function (j) { return j.data || {}; }) : {};
    }).then(function (d) {
      if (!d || !d.stale || document.getElementById('stale-server')) return;
      var bar = document.createElement('div');
      bar.id = 'stale-server';
      bar.className = 'stale-server';
      bar.innerHTML = '⚠️ برنامه به‌روز شده ولی <b>سرور هنوز نسخه‌ی قبلی را اجرا '
        + 'می‌کند</b>؛ تا وقتی سرور دوباره راه‌اندازی نشود، تغییرات جدید ذخیره '
        + 'نمی‌شوند یا نمایش داده نمی‌شوند. پنجره‌ی سرور را ببندید، دوباره اجرا کنید '
        + 'و صفحه را تازه کنید (Ctrl+F5).';
      document.body.insertBefore(bar, document.body.firstChild);
    }).catch(function () {});
  }

  document.addEventListener('DOMContentLoaded', function () {
    measureHeader();
    setupNav();
    checkBuild();
  });
  window.addEventListener('resize', debounce(measureHeader, 120));
  window.addEventListener('load', measureHeader);

  global.App = {
    api: api, request: request, toast: toast, confirmDialog: confirmDialog,
    chooseImportMode: chooseImportMode,
    openModal: openModal, closeModal: closeModal, esc: esc, el: el, qs: qs, qsa: qsa,
    debounce: debounce, serializeQuery: serializeQuery, renderBarChart: renderBarChart,
    download: download, downloadPost: downloadPost, fmtNumber: fmtNumber,
    csrfToken: csrfToken, can: can
  };
})(window);
