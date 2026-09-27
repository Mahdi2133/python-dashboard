/* ==========================================================================
   Users page → «دسترسی گزارش‌ها»: which reports a user, role, مرکز or group
   may open and at which levels, and the user groups themselves.
   The same grants are editable per report in گزارش‌ساز (step 12).
   ========================================================================== */
(function () {
  'use strict';
  var A = window.App, API = '/api/analytics';
  var P = null, rows = [], effective = null, dirty = false;

  function el(t, a, k) { return A.el(t, a, k); }

  async function load() {
    if (!A.qs('#ra-kind')) return;
    try { P = (await A.api.get(API + '/principals')).data; } catch (err) { A.toast(err.message, 'error'); return; }
    var kind = A.qs('#ra-kind');
    if (!kind.options.length) {
      Object.keys(P.kinds).forEach(function (k) { kind.appendChild(el('option', { value: k, text: P.kinds[k] })); });
      kind.value = 'role';
      kind.addEventListener('change', function () { fillWho(); loadGrants(); });
      A.qs('#ra-who').addEventListener('change', loadGrants);
    }
    fillWho();
    drawGroups();
    loadGrants();
  }

  function fillWho() {
    var who = A.qs('#ra-who'), k = A.qs('#ra-kind').value, keep = who.value;
    who.innerHTML = '';
    var opts = k === 'user' ? P.users.map(function (u) { return [u.id, u.name + ' (' + u.username + ')']; })
      : k === 'role' ? P.roles.filter(function (r) { return r.key !== 'admin'; }).map(function (r) { return [r.key, r.label]; })
        : k === 'center' ? P.centers.map(function (c) { return [c.id, c.label]; })
          : P.groups.map(function (g) { return [g.id, g.name]; });
    opts.forEach(function (o) { who.appendChild(el('option', { value: o[0], text: o[1] })); });
    if (keep && opts.some(function (o) { return String(o[0]) === keep; })) who.value = keep;
  }

  async function loadGrants() {
    var t = A.qs('#ra-table'), who = A.qs('#ra-who').value;
    if (!who) { t.innerHTML = '<tr><td class="table-empty">موردی برای انتخاب نیست.</td></tr>'; return; }
    t.innerHTML = '<tr><td class="loading">در حال بارگذاری</td></tr>';
    try {
      var res = await A.api.get(API + '/access/principal?kind=' + A.qs('#ra-kind').value + '&principal=' + encodeURIComponent(who));
      rows = res.data.reports; effective = res.data.effective; dirty = false;
      draw();
    } catch (err) { t.innerHTML = '<tr><td class="alert error">' + A.esc(err.message) + '</td></tr>'; }
  }

  function draw() {
    var t = A.qs('#ra-table'), levels = Object.keys(P.levels);
    var html = '<thead><tr><th>گزارش</th><th>وضعیت</th>' + levels.map(function (l) { return '<th>' + A.esc(P.levels[l]) + '</th>'; }).join('')
      + (effective ? '<th>نتیجه‌ی نهایی کاربر</th>' : '') + '</tr></thead><tbody>';
    if (!rows.length) html += '<tr><td class="table-empty" colspan="' + (levels.length + 2) + '">گزارشی تعریف نشده است.</td></tr>';
    rows.forEach(function (r, i) {
      html += '<tr><td><b>' + A.esc(r.name) + '</b>' + (r.category ? '<div class="muted small">' + A.esc(r.category) + '</div>' : '') + '</td>'
        + '<td><span class="badge ' + (r.status === 'published' ? 'ok' : 'muted') + '">' + A.esc(r.status_label) + '</span></td>'
        + levels.map(function (l) {
          return '<td class="center"><input type="checkbox" data-i="' + i + '" data-l="' + l + '"' + (r.access.indexOf(l) >= 0 ? ' checked' : '') + '></td>';
        }).join('');
      if (effective) {
        var eff = effective[r.id] || [];
        html += '<td class="small">' + (eff.length ? eff.map(function (l) { return A.esc(P.levels[l]); }).join('، ') : '<span class="muted">—</span>') + '</td>';
      }
      html += '</tr>';
    });
    t.innerHTML = html + '</tbody>';
    A.qsa('input[data-i]', t).forEach(function (c) {
      c.addEventListener('change', function () {
        var r = rows[Number(c.dataset.i)];
        r.access = r.access.filter(function (x) { return x !== c.dataset.l; });
        if (c.checked) r.access.push(c.dataset.l);
        r._changed = true; dirty = true;
        A.qs('#ra-save').classList.add('pulse');
      });
    });
  }

  async function save() {
    var grants = {};
    rows.forEach(function (r) { if (r._changed) grants[r.id] = r.access; });
    try {
      var res = await A.api.put(API + '/access/principal', { kind: A.qs('#ra-kind').value, principal: A.qs('#ra-who').value, grants: grants });
      A.toast('دسترسی ' + res.data.changed + ' گزارش ذخیره شد.', 'success');
      A.qs('#ra-save').classList.remove('pulse');
      loadGrants();
    } catch (err) { A.toast(err.message, 'error'); }
  }

  function drawGroups() {
    var box = A.qs('#ra-groups');
    box.innerHTML = '';
    if (!P.groups.length) box.appendChild(el('div', { class: 'muted small', text: 'هنوز گروهی نیست.' }));
    P.groups.forEach(function (g) {
      var card = el('details', { class: 'ra-group' });
      card.appendChild(el('summary', { html: '<b>' + A.esc(g.name) + '</b> <span class="muted small">(' + g.member_ids.length + ' نفر)</span>' }));
      var body = el('div', { class: 'ra-group-body' });
      var name = el('input', { type: 'text', value: g.name });
      var desc = el('input', { type: 'text', value: g.description || '', placeholder: 'توضیح' });
      body.appendChild(el('div', { class: 'rb-inline' }, [name, desc]));
      var members = el('div', { class: 'ra-members' });
      P.users.forEach(function (u) {
        var c = el('input', { type: 'checkbox', value: u.id });
        c.checked = g.member_ids.indexOf(u.id) >= 0;
        members.appendChild(el('label', { class: 'mini-check' }, [c, document.createTextNode(' ' + u.name + (u.is_active ? '' : ' (غیرفعال)'))]));
      });
      body.appendChild(members);
      body.appendChild(el('div', { class: 'rb-inline' }, [
        el('button', { type: 'button', class: 'btn-primary btn-sm', text: 'ذخیره‌ی گروه', onclick: async function () {
          var ids = A.qsa('input[type=checkbox]', members).filter(function (c) { return c.checked; }).map(function (c) { return Number(c.value); });
          try { await A.api.put(API + '/groups/' + g.id, { name: name.value, description: desc.value, member_ids: ids }); A.toast('گروه ذخیره شد.', 'success'); load(); }
          catch (err) { A.toast(err.message, 'error'); }
        } }),
        el('button', { type: 'button', class: 'btn-danger btn-sm', text: 'حذف گروه', onclick: async function () {
          if (!(await A.confirmDialog({ message: 'گروه «' + g.name + '» و دسترسی‌های گزارشِ داده‌شده به آن حذف شود؟' }))) return;
          try { await A.api.del(API + '/groups/' + g.id); load(); } catch (err) { A.toast(err.message, 'error'); }
        } })
      ]));
      card.appendChild(body);
      box.appendChild(card);
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    var tab = A.qs('#tab-report-access');
    if (!tab) return;
    var loaded = false;
    tab.addEventListener('click', function () { if (!loaded) { loaded = true; load(); } });
    A.qs('#ra-save').addEventListener('click', save);
    A.qs('#ra-group-add').addEventListener('click', async function () {
      var n = A.qs('#ra-group-name').value.trim();
      if (!n) return;
      try { await A.api.post(API + '/groups', { name: n, member_ids: [] }); A.qs('#ra-group-name').value = ''; load(); }
      catch (err) { A.toast(err.message, 'error'); }
    });
    if (location.hash === '#report-access') setTimeout(function () { tab.click(); }, 50);
  });
})();
