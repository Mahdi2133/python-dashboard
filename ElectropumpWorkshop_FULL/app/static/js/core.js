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

  function openModal(id) { document.getElementById(id).classList.add('show'); }
  function closeModal(id) { document.getElementById(id).classList.remove('show'); }

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

  global.App = {
    api: api, request: request, toast: toast, confirmDialog: confirmDialog,
    openModal: openModal, closeModal: closeModal, esc: esc, el: el, qs: qs, qsa: qsa,
    debounce: debounce, serializeQuery: serializeQuery, renderBarChart: renderBarChart,
    download: download, downloadPost: downloadPost, fmtNumber: fmtNumber,
    csrfToken: csrfToken, can: can
  };
})(window);
