/* User administration: identity, credentials, permissions and activity. */
(function () {
  'use strict';
  var A = window.App, J = window.Jalali;
  var meta = null, editing = null, page = 1, sPage = 1;
  var centers = [];            // the مراکز a user can answer for

  /* Which مراکز this person answers for.

     Only a stage set to «فقط متولی مرکزِ همان چاه» reads this, and only to
     pick which of its owners gets one job. The list is the مرکز lookup, so
     adding a ninth centre in «مدیریت گزینه‌ها» puts it here too. */
  function renderCenters(selected) {
    var box = A.qs('#u-centers');
    if (!box) return;
    var on = selected || [];
    box.innerHTML = centers.length
      ? centers.map(function (c) {
          return '<label class="center-chip"><input type="checkbox" data-center="'
            + c.id + '"' + (on.indexOf(c.id) !== -1 ? ' checked' : '') + '>'
            + '<span>' + A.esc(c.label) + '</span></label>';
        }).join('')
      : '<span class="hint">هیچ مرکزی در «مدیریت گزینه‌ها» تعریف نشده است.</span>';
  }

  function selectedCenters() {
    return A.qsa('#u-centers [data-center]:checked')
      .map(function (b) { return Number(b.dataset.center); });
  }

  /* ── permission checkboxes ──────────────────────────────────────────── */
  function renderPermissions() {
    A.qs('#u-perms').innerHTML = meta.permission_groups.map(function (g) {
      return '<div class="perm-group"><h5>' + A.esc(g.group) + '</h5>'
        + g.items.map(function (p) {
            return '<label><input type="checkbox" data-perm="' + A.esc(p.code) + '">'
              + '<span>' + A.esc(p.label) + '</span></label>';
          }).join('') + '</div>';
    }).join('');
  }

  function renderRoles(selected) {
    A.qs('#u-roles').innerHTML = meta.roles.map(function (r) {
      return '<label><input type="radio" name="u-role" value="' + A.esc(r.key) + '"'
        + (r.key === selected ? ' checked' : '') + '>'
        + '<span class="btn-opt">' + A.esc(r.label) + '</span></label>';
    }).join('');
    showRoleDescription(selected);
  }

  function roleByKey(key) {
    return meta.roles.find(function (r) { return r.key === key; });
  }

  function showRoleDescription(key) {
    var role = roleByKey(key);
    A.qs('#u-role-desc').textContent = role ? role.description : '';
  }

  function setPermissionBoxes(codes) {
    A.qsa('[data-perm]').forEach(function (box) {
      box.checked = codes.indexOf(box.dataset.perm) >= 0;
    });
  }

  function applyCustomToggle() {
    var custom = A.qs('#u-custom').checked;
    A.qsa('[data-perm]').forEach(function (box) { box.disabled = !custom; });
    A.qs('#u-perms').style.opacity = custom ? '1' : '.55';
    if (!custom) {
      var role = roleByKey(selectedRole());
      setPermissionBoxes(role ? role.permissions : []);
    }
  }

  function selectedRole() {
    var picked = A.qs('input[name="u-role"]:checked');
    return picked ? picked.value : 'operator';
  }

  /* ── list ───────────────────────────────────────────────────────────── */
  async function loadUsers() {
    var body = A.qs('#users-body');
    body.innerHTML = '<tr><td colspan="10" class="table-empty">در حال بارگذاری…</td></tr>';
    try {
      var res = await A.api.get('/api/users?' + A.serializeQuery({
        page: page, page_size: 50, q: A.qs('#u-q').value.trim(),
        active: A.qs('#u-active-only').checked ? '1' : ''
      }));
      if (!res.data.length) {
        body.innerHTML = '<tr><td colspan="10" class="table-empty">کاربری یافت نشد</td></tr>';
      } else {
        body.innerHTML = res.data.map(function (u, i) {
          return '<tr class="' + (u.is_active ? '' : 'inactive') + '">'
            + '<td>' + J.toFaDigits((page - 1) * 50 + i + 1) + '</td>'
            + '<td><div class="user-row-name"><span>'
              + '<span class="' + (u.is_online ? 'dot-online' : 'dot-offline') + '"></span>'
              + A.esc(u.full_name) + '</span>'
              + (u.position ? '<small>' + A.esc(u.position) + '</small>' : '') + '</div></td>'
            + '<td class="mono">' + A.esc(u.username) + '</td>'
            + '<td>' + A.esc(u.personnel_code || '') + '</td>'
            + '<td><span class="badge">' + A.esc(u.role_label) + '</span>'
              + (u.custom_permissions ? ' <span class="badge warn">سفارشی</span>' : '') + '</td>'
            + '<td>' + (u.is_active ? '<span class="badge ok">فعال</span>'
                                    : '<span class="badge muted">غیرفعال</span>')
              + (u.is_locked ? ' <span class="badge danger">قفل</span>' : '') + '</td>'
            + '<td>' + A.esc(u.last_login_j || '—') + '</td>'
            + '<td>' + J.toFaDigits(u.login_count) + '</td>'
            + '<td>' + J.toFaDigits(u.records_created) + '</td>'
            + '<td><div class="action-cell">'
            + '<button class="btn-sm btn-edit" data-edit="' + u.id + '">✏</button>'
            + '<button class="btn-sm btn-view" data-act="' + u.id + '">📊</button>'
            + (u.is_locked
                ? '<button class="btn-sm btn-del" data-unlock="' + u.id + '">🔓</button>' : '')
            + '</div></td></tr>';
        }).join('');
      }
      var box = A.qs('#u-pagination');
      box.innerHTML = res.pages > 1
        ? '<button data-p="' + Math.max(1, res.page - 1) + '">‹ قبلی</button>'
          + '<span class="info">صفحه ' + J.toFaDigits(res.page) + ' از '
          + J.toFaDigits(res.pages) + '</span>'
          + '<button data-p="' + Math.min(res.pages, res.page + 1) + '">بعدی ›</button>'
        : '<span class="info">' + J.toFaDigits(res.total) + ' کاربر</span>';
      window.__users = res.data;
    } catch (err) {
      body.innerHTML = '<tr><td colspan="10" class="table-empty">'
        + A.esc(err.message) + '</td></tr>';
    }
  }

  /* ── decision powers in the process ──────────────────────────────────── */
  var powers = null;           // rows as loaded, to send only what changed

  async function loadPowers(user) {
    var box = A.qs('#u-powers-box');
    powers = null;
    if (!box) return;
    var allowed = user && A.can && A.can('workflow.manage');
    box.classList.toggle('hidden', !allowed);
    if (!allowed) return;
    A.qs('#u-powers').innerHTML = '<div class="loading">در حال بارگذاری</div>';
    try {
      var res = await A.api.get('/api/workflow/powers/' + user.id);
      if (!editing || editing.id !== user.id) return;
      powers = res.data.rows;
      renderPowers();
    } catch (err) {
      A.qs('#u-powers').innerHTML = '<div class="hint">' + A.esc(err.message) + '</div>';
    }
  }

  function renderPowers() {
    var box = A.qs('#u-powers');
    if (!powers.length) {
      box.innerHTML = '<div class="hint">هنوز برای هیچ مرحله‌ای اقدامی جز «ارسال» '
        + 'تعریف نشده است. در فرایندساز، بخش «⚖ اقدام‌ها و اختیارات کاربران» '
        + 'هر مرحله را باز کنید و «افزودن اقدام» را بزنید.</div>';
      return;
    }
    var last = null;
    box.innerHTML = powers.map(function (r) {
      var head = '';
      if (r.stage_number !== last) {
        last = r.stage_number;
        head = '<div class="power-stage">مرحله ' + J.toFaDigits(r.stage_number)
          + ' — ' + A.esc(r.stage_title)
          + (r.owns_stage ? ' <span class="badge">متولی این مرحله</span>'
                          : ' <span class="hint">(متولی نیست؛ فقط وقتی کاری به او ارجاع شود)</span>')
          + '</div>';
      }
      var icon = r.kind === 'stop' ? '⛔' : '↩';
      var what = r.kind === 'return'
        ? (r.target_title ? 'برگشت به «' + A.esc(r.target_title) + '»'
                          : 'برگشت به هر مرحله‌ی قبلی')
          + (r.needs_docs ? ' · مستند الزامی' : '')
        : 'توقف فرایند';
      return head + '<label class="power-row"><input type="checkbox" data-power="'
        + A.esc(r.key) + '"' + (r.allowed ? ' checked' : '') + '>'
        + '<span>' + icon + ' ' + A.esc(r.label) + '</span>'
        + '<i>' + what + (r.everyone ? ' · فعلاً برای همه‌ی متولی‌ها' : '') + '</i></label>';
    }).join('');
  }

  async function savePowers(userId) {
    if (!powers) return;
    var grants = {}, any = false;
    powers.forEach(function (r) {
      var box = A.qs('#u-powers [data-power="' + r.key + '"]');
      if (box && box.checked !== r.allowed) { grants[r.key] = box.checked; any = true; }
    });
    if (!any) return;
    await A.api.put('/api/workflow/powers/' + userId, { grants: grants });
  }

  /* ── editor ─────────────────────────────────────────────────────────── */
  function openEditor(user) {
    editing = user;
    A.qs('#user-modal-title').textContent = user
      ? 'ویرایش کاربر: ' + user.full_name : 'کاربر جدید';
    A.qs('#user-alert').innerHTML = '';
    var val = function (id, v) { A.qs(id).value = v === null || v === undefined ? '' : v; };
    val('#u-first', user && user.first_name);
    val('#u-last', user && user.last_name);
    val('#u-father', user && user.father_name);
    val('#u-nid', user && user.national_id);
    val('#u-birth', user && user.birth_date
      ? J.format.apply(null, J.toJalali(new Date(user.birth_date))) : '');
    val('#u-phone', user && user.phone);
    val('#u-email', user && user.email);
    val('#u-position', user && user.position);
    val('#u-unit', user && user.unit);
    renderCenters(user && user.center_ids);
    val('#u-username', user && user.username);
    val('#u-personnel', user && user.personnel_code);
    val('#u-notes', user && user.notes);
    val('#u-password', '');
    A.qs('#u-active').value = user && !user.is_active ? '0' : '1';
    A.qs('#u-mustchange').value = user
      ? (user.must_change_password ? '1' : '0') : '1';
    setEditWindow(user ? user.edit_window_hours : null);
    A.qs('#u-pass-label').innerHTML = user
      ? 'رمز عبور جدید' : 'رمز عبور <span class="req">*</span>';
    A.qs('#u-disable').classList.toggle('hidden', !user || !user.is_active);
    A.qs('#u-activity').classList.toggle('hidden', !user);

    renderRoles(user ? user.role : 'operator');
    A.qs('#u-custom').checked = !!(user && user.custom_permissions);
    setPermissionBoxes(user ? user.permissions : (roleByKey('operator') || {}).permissions || []);
    applyCustomToggle();
    loadPowers(user);
    A.openModal('user-modal');
  }

  /* مهلت ویرایش: یکی از گزینه‌های آماده، وگرنه «مقدار دلخواه» با ورودی ساعت. */
  function setEditWindow(hours) {
    var select = A.qs('#u-editwindow');
    var custom = A.qs('#u-editwindow-custom');
    var known = A.qsa('#u-editwindow option').some(function (o) {
      return o.value === String(hours || '');
    });
    if (!hours) { select.value = ''; custom.value = ''; }
    else if (known) { select.value = String(hours); custom.value = ''; }
    else { select.value = 'custom'; custom.value = hours; }
    custom.classList.toggle('hidden', select.value !== 'custom');
  }

  function readEditWindow() {
    var select = A.qs('#u-editwindow');
    if (select.value === 'custom') {
      return parseInt(A.qs('#u-editwindow-custom').value, 10) || null;
    }
    return select.value ? parseInt(select.value, 10) : null;
  }

  function collect() {
    var payload = {
      first_name: A.qs('#u-first').value.trim(),
      last_name: A.qs('#u-last').value.trim(),
      father_name: A.qs('#u-father').value.trim(),
      national_id: A.qs('#u-nid').value.trim(),
      birth_date: A.qs('#u-birth').value.trim(),
      phone: A.qs('#u-phone').value.trim(),
      email: A.qs('#u-email').value.trim(),
      position: A.qs('#u-position').value.trim(),
      unit: A.qs('#u-unit').value.trim(),
      center_ids: selectedCenters(),
      username: A.qs('#u-username').value.trim(),
      personnel_code: A.qs('#u-personnel').value.trim(),
      notes: A.qs('#u-notes').value.trim(),
      role: selectedRole(),
      is_active: A.qs('#u-active').value === '1',
      must_change_password: A.qs('#u-mustchange').value === '1',
      edit_window_hours: readEditWindow(),
      permissions: A.qs('#u-custom').checked
        ? A.qsa('[data-perm]:checked').map(function (b) { return b.dataset.perm; })
        : 'default'
    };
    var pw = A.qs('#u-password').value;
    if (pw) payload.password = pw;
    return payload;
  }

  async function save() {
    var payload = collect();
    if (!payload.username) {
      A.qs('#user-alert').innerHTML = '<div class="alert error">نام کاربری الزامی است.</div>';
      return;
    }
    if (!editing && !payload.password) {
      A.qs('#user-alert').innerHTML = '<div class="alert error">برای کاربر جدید رمز عبور لازم است.</div>';
      return;
    }
    var button = A.qs('#u-save');
    button.disabled = true;
    try {
      var res = editing
        ? await A.api.put('/api/users/' + editing.id, payload)
        : await A.api.post('/api/users', payload);
      if (editing) {
        try {
          await savePowers(editing.id);
        } catch (perr) {
          // The person's details are saved; only the powers change was refused.
          A.qs('#user-alert').innerHTML = '<div class="alert error">مشخصات کاربر ذخیره شد، '
            + 'اما اختیارات تغییر نکرد: ' + A.esc(perr.message) + '</div>';
          loadUsers();
          return;
        }
      }
      A.toast(res.message);
      A.closeModal('user-modal');
      loadUsers();
    } catch (err) {
      A.qs('#user-alert').innerHTML = '<div class="alert error">' + A.esc(err.message) + '</div>';
    } finally { button.disabled = false; }
  }

  /* ── activity ───────────────────────────────────────────────────────── */
  function table(headers, rows) {
    if (!rows.length) return '<p class="table-empty">موردی ثبت نشده است.</p>';
    return '<table><thead><tr>'
      + headers.map(function (h) { return '<th>' + A.esc(h) + '</th>'; }).join('')
      + '</tr></thead><tbody>' + rows.map(function (r) {
          return '<tr>' + r.map(function (c) {
            return '<td>' + (c === null || c === undefined ? '' : c) + '</td>';
          }).join('') + '</tr>';
        }).join('') + '</tbody></table>';
  }

  function duration(seconds) {
    if (!seconds) return '—';
    var h = Math.floor(seconds / 3600), m = Math.round((seconds % 3600) / 60);
    return (h ? J.toFaDigits(h) + ' ساعت ' : '') + J.toFaDigits(m) + ' دقیقه';
  }

  async function showActivity(userId) {
    try {
      var res = await A.api.get('/api/users/' + userId + '/activity');
      var d = res.data;
      A.qs('#activity-title').textContent = 'کارکرد کاربر: ' + d.user.full_name
        + ' (' + d.user.username + ')';
      A.qs('#activity-summary').innerHTML = '<div class="summary-strip">'
        + '<span>رکورد ثبت‌شده: <b>' + J.toFaDigits(d.summary.records_created) + '</b></span>'
        + '<span>رکورد ویرایش‌شده: <b>' + J.toFaDigits(d.summary.records_edited) + '</b></span>'
        + '<span>تعداد ورود: <b>' + J.toFaDigits(d.summary.logins) + '</b></span>'
        + '<span>مجموع حضور: <b>' + J.toFaDigits(d.summary.total_hours) + ' ساعت</b></span>'
        + '</div>';

      A.qs('#a-sessions').innerHTML = table(
        ['تاریخ', 'ورود', 'خروج', 'مدت', 'IP', 'وضعیت'],
        d.sessions.map(function (s) {
          return [A.esc(s.login_at_j), A.esc(s.login_time),
                  s.logout_time ? A.esc(s.logout_time) : '—',
                  duration(s.duration_seconds), A.esc(s.ip_address || ''),
                  s.is_open ? '<span class="badge ok">باز</span>'
                            : '<span class="badge muted">' + A.esc(s.end_reason || 'بسته') + '</span>'];
        }));

      A.qs('#a-records').innerHTML = table(
        ['#', 'تاریخ عملیات', 'چاه', 'زمان ثبت', 'وضعیت'],
        d.recent_records.map(function (r) {
          return [r.id, A.esc(r.date), A.esc(r.well || ''), A.esc(r.created_at_j || ''),
                  r.is_active ? '<span class="badge ok">فعال</span>'
                              : '<span class="badge muted">غیرفعال</span>'];
        }));

      A.qs('#a-audits').innerHTML = table(
        ['تاریخ', 'ساعت', 'عملیات', 'موجودیت', 'شرح'],
        d.audits.map(function (a) {
          return [A.esc(a.created_at_j), A.esc(a.time),
                  '<span class="badge">' + A.esc(a.action) + '</span>',
                  A.esc(a.entity || ''), A.esc(a.summary || '')];
        }));

      A.qsa('[data-atab]').forEach(function (t, i) {
        t.classList.toggle('active', i === 0);
      });
      A.qsa('[data-apanel]').forEach(function (p, i) {
        p.classList.toggle('hidden', i !== 0);
      });
      A.openModal('activity-modal');
    } catch (err) { A.toast(err.message, 'error'); }
  }

  /* ── sessions tab ───────────────────────────────────────────────────── */
  async function loadSessions() {
    var body = A.qs('#sessions-body');
    body.innerHTML = '<tr><td colspan="9" class="table-empty">در حال بارگذاری…</td></tr>';
    try {
      var res = await A.api.get('/api/sessions?' + A.serializeQuery({
        page: sPage, page_size: 60,
        open: A.qs('#s-open-only').checked ? '1' : ''
      }));
      body.innerHTML = res.data.length ? res.data.map(function (s, i) {
        return '<tr><td>' + J.toFaDigits((sPage - 1) * 60 + i + 1) + '</td>'
          + '<td>' + A.esc(s.full_name || s.username || '') + '</td>'
          + '<td>' + A.esc(s.login_at_j) + '</td>'
          + '<td class="mono">' + A.esc(s.login_time) + '</td>'
          + '<td class="mono">' + (s.logout_time ? A.esc(s.logout_time) : '—') + '</td>'
          + '<td>' + duration(s.duration_seconds) + '</td>'
          + '<td class="mono">' + A.esc(s.ip_address || '') + '</td>'
          + '<td>' + (s.is_open ? '<span class="badge ok">باز</span>'
                                : '<span class="badge muted">' + A.esc(s.end_reason || '') + '</span>') + '</td>'
          + '<td>' + (s.is_open
              ? '<button class="btn-sm btn-del" data-close="' + s.id + '">بستن</button>' : '')
          + '</td></tr>';
      }).join('') : '<tr><td colspan="9" class="table-empty">نشستی ثبت نشده است</td></tr>';
      var box = A.qs('#s-pagination');
      box.innerHTML = res.pages > 1
        ? '<button data-sp="' + Math.max(1, res.page - 1) + '">‹ قبلی</button>'
          + '<span class="info">صفحه ' + J.toFaDigits(res.page) + ' از '
          + J.toFaDigits(res.pages) + '</span>'
          + '<button data-sp="' + Math.min(res.pages, res.page + 1) + '">بعدی ›</button>'
        : '<span class="info">' + J.toFaDigits(res.total) + ' نشست</span>';
    } catch (err) {
      body.innerHTML = '<tr><td colspan="9" class="table-empty">' + A.esc(err.message) + '</td></tr>';
    }
  }

  /* ── init ───────────────────────────────────────────────────────────── */
  document.addEventListener('DOMContentLoaded', async function () {
    A.qsa('.jdate').forEach(function (input) { J.attach(input); });
    try {
      meta = (await A.api.get('/api/users/meta')).data;
      try {
        centers = ((await A.api.get('/api/lookups/center')).data || {}).items || [];
      } catch (err) { centers = []; }
      renderPermissions();
      renderRoles('operator');
    } catch (err) { A.toast(err.message, 'error'); return; }

    A.qs('#btn-new-user').addEventListener('click', function () { openEditor(null); });
    A.qs('#u-save').addEventListener('click', save);
    A.qs('#u-q').addEventListener('input', A.debounce(function () { page = 1; loadUsers(); }, 320));
    A.qs('#u-active-only').addEventListener('change', function () { page = 1; loadUsers(); });
    A.qs('#u-editwindow').addEventListener('change', function () {
      A.qs('#u-editwindow-custom').classList.toggle('hidden', this.value !== 'custom');
    });
    A.qs('#u-custom').addEventListener('change', applyCustomToggle);
    A.qs('#u-roles').addEventListener('change', function () {
      showRoleDescription(selectedRole());
      if (!A.qs('#u-custom').checked) applyCustomToggle();
    });

    A.qs('#u-disable').addEventListener('click', async function () {
      if (!editing) return;
      if (!await A.confirmDialog({
        title: 'غیرفعال‌سازی کاربر',
        message: 'کاربر «' + editing.full_name + '» بلافاصله از سامانه خارج می‌شود '
                 + 'و دیگر نمی‌تواند وارد شود. سوابق و رکوردهای او حفظ می‌شوند.'
      })) return;
      try {
        var res = await A.api.del('/api/users/' + editing.id);
        A.toast(res.message);
        A.closeModal('user-modal');
        loadUsers();
      } catch (err) { A.toast(err.message, 'error'); }
    });

    A.qs('#u-activity').addEventListener('click', function () {
      if (editing) showActivity(editing.id);
    });

    A.qs('#users-body').addEventListener('click', async function (ev) {
      var edit = ev.target.closest('[data-edit]');
      if (edit) {
        var user = (window.__users || []).find(function (u) {
          return u.id === +edit.dataset.edit;
        });
        if (user) openEditor(user);
        return;
      }
      var act = ev.target.closest('[data-act]');
      if (act) { showActivity(act.dataset.act); return; }
      var unlock = ev.target.closest('[data-unlock]');
      if (unlock) {
        try {
          var res = await A.api.post('/api/users/' + unlock.dataset.unlock + '/unlock', {});
          A.toast(res.message);
          loadUsers();
        } catch (err) { A.toast(err.message, 'error'); }
      }
    });

    A.qs('#u-pagination').addEventListener('click', function (ev) {
      var b = ev.target.closest('[data-p]');
      if (b) { page = +b.dataset.p; loadUsers(); }
    });
    A.qs('#s-pagination').addEventListener('click', function (ev) {
      var b = ev.target.closest('[data-sp]');
      if (b) { sPage = +b.dataset.sp; loadSessions(); }
    });
    A.qs('#sessions-body').addEventListener('click', async function (ev) {
      var b = ev.target.closest('[data-close]');
      if (!b) return;
      try {
        var res = await A.api.post('/api/sessions/' + b.dataset.close + '/close', {});
        A.toast(res.message);
        loadSessions();
      } catch (err) { A.toast(err.message, 'error'); }
    });
    A.qs('#s-refresh').addEventListener('click', loadSessions);
    A.qs('#s-open-only').addEventListener('change', function () { sPage = 1; loadSessions(); });

    A.qsa('.tab[data-tab]').forEach(function (tab) {
      tab.addEventListener('click', function () {
        A.qsa('.tab[data-tab]').forEach(function (t) {
          t.classList.toggle('active', t === tab);
        });
        A.qsa('[data-panel]').forEach(function (p) {
          p.classList.toggle('hidden', p.dataset.panel !== tab.dataset.tab);
        });
        if (tab.dataset.tab === 'sessions') loadSessions();
      });
    });
    A.qsa('.tab[data-atab]').forEach(function (tab) {
      tab.addEventListener('click', function () {
        A.qsa('.tab[data-atab]').forEach(function (t) {
          t.classList.toggle('active', t === tab);
        });
        A.qsa('[data-apanel]').forEach(function (p) {
          p.classList.toggle('hidden', p.dataset.apanel !== tab.dataset.atab);
        });
      });
    });

    loadUsers();
  });
})();
