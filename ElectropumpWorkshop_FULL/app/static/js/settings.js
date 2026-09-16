(function () {
  'use strict';
  var A = window.App, J = window.Jalali;
  var auditPage = 1;

  function kv(target, pairs) {
    A.qs(target).innerHTML = pairs.map(function (p) {
      return '<dt>' + A.esc(p[0]) + '</dt><dd>' + (p[2] ? p[1] : A.esc(p[1])) + '</dd>';
    }).join('');
  }

  async function loadSystem() {
    try {
      var res = await A.api.get('/api/system');
      var d = res.data;
      kv('#db-info', [
        ['نوع پایگاه داده', d.database.type],
        ['وضعیت اتصال', d.database.connected
          ? '<span class="badge ok">متصل</span>'
          : '<span class="badge danger">قطع — ' + A.esc(d.database.error || '') + '</span>', true],
        ['مسیر فایل', '<span class="mono">' + A.esc(d.database.path) + '</span>', true],
        ['وجود فایل', d.database.exists ? 'بله' : 'خیر'],
        ['حجم', d.database.size_mb + ' مگابایت'],
        ['حالت ژورنال', d.database.journal_mode + ' (چندکاربره)']
      ]);
      kv('#net-info', [
        ['آدرس bind', d.server.host],
        ['پورت', d.server.port],
        ['آدرس محلی', '<a class="mono" href="' + A.esc(d.server.local_url) + '">'
          + A.esc(d.server.local_url) + '</a>', true],
        ['آدرس شبکه', d.server.network_urls.length
          ? d.server.network_urls.map(function (u) {
              return '<div class="mono">' + A.esc(u) + '</div>';
            }).join('')
          : '<span class="muted">آدرس شبکه‌ای شناسایی نشد</span>', true],
        ['نام رایانه', d.server.hostname],
        ['اجرا به‌صورت EXE', d.server.frozen ? 'بله' : 'خیر (حالت توسعه)']
      ]);
      A.qs('#fw-cmd').textContent =
        'netsh advfirewall firewall add rule name="ElectropumpWorkshop" '
        + 'dir=in action=allow protocol=TCP localport=' + d.server.port;
      kv('#counts-info', [
        ['رکوردهای فعال', J.toFaDigits(d.counts.records)],
        ['رکوردهای غیرفعال', J.toFaDigits(d.counts.records_inactive)],
        ['چاه‌ها', J.toFaDigits(d.counts.wells)],
        ['چاه‌های تأییدنشده', J.toFaDigits(d.counts.wells_unverified)],
        ['گزینه‌های فرم', J.toFaDigits(d.counts.lookup_items)],
        ['گزینه‌های خودکار (نیازمند بازبینی)', J.toFaDigits(d.counts.lookup_adhoc)],
        ['فیلدهای فرم', J.toFaDigits(d.counts.form_fields)],
        ['رویدادهای ثبت‌شده', J.toFaDigits(d.counts.audit_logs)]
      ]);
      kv('#paths-info', [
        ['پوشه برنامه', '<span class="mono">' + A.esc(d.paths.app_dir) + '</span>', true],
        ['فایل تنظیمات', '<span class="mono">' + A.esc(d.paths.config) + '</span>', true],
        ['فایل لاگ', '<span class="mono">' + A.esc(d.paths.logs) + '</span>', true],
        ['پوشه پشتیبان', '<span class="mono">' + A.esc(d.paths.backups) + '</span>', true],
        ['نسخه پایتون', d.server.python],
        ['سیستم‌عامل', d.server.platform],
        ['نسخه برنامه', d.app.version]
      ]);
    } catch (err) { A.toast(err.message, 'error'); }
  }

  async function loadBackups() {
    try {
      var res = await A.api.get('/api/backup');
      A.qs('#backup-body').innerHTML = res.data.length ? res.data.map(function (b, i) {
        return '<tr><td>' + J.toFaDigits(i + 1) + '</td>'
          + '<td class="mono">' + A.esc(b.filename) + '</td>'
          + '<td>' + (b.size / 1024 / 1024).toFixed(2) + ' MB</td>'
          + '<td class="mono">' + A.esc(b.modified.slice(0, 19).replace('T', ' ')) + '</td>'
          + '<td><div class="action-cell">'
          + '<button class="btn-sm btn-view" data-dl="' + A.esc(b.filename) + '">⬇ دانلود</button>'
          + '<button class="btn-sm btn-del" data-restore="' + A.esc(b.filename) + '">↩ بازیابی</button>'
          + '</div></td></tr>';
      }).join('') : '<tr><td colspan="5" class="table-empty">پشتیبانی ثبت نشده است</td></tr>';
    } catch (err) { A.toast(err.message, 'error'); }
  }

  async function loadAudit() {
    try {
      var res = await A.api.get('/api/audit?' + A.serializeQuery({
        page: auditPage, page_size: 100,
        action: A.qs('#a-action').value, entity: A.qs('#a-entity').value
      }));
      A.qs('#audit-body').innerHTML = res.data.length ? res.data.map(function (r) {
        return '<tr><td>' + r.id + '</td><td>' + A.esc(r.created_at_j) + '</td>'
          + '<td class="mono">' + A.esc(r.time) + '</td>'
          + '<td>' + A.esc(r.username || '—') + '</td>'
          + '<td><span class="badge">' + A.esc(r.action) + '</span></td>'
          + '<td>' + A.esc(r.entity || '') + '</td>'
          + '<td>' + (r.entity_id || '') + '</td>'
          + '<td title="' + A.esc(r.details || '') + '">' + A.esc(r.summary || '') + '</td>'
          + '<td class="mono">' + A.esc(r.ip_address || '') + '</td></tr>';
      }).join('') : '<tr><td colspan="9" class="table-empty">رویدادی ثبت نشده</td></tr>';
      var box = A.qs('#audit-pagination');
      box.innerHTML = res.pages > 1
        ? '<button data-p="' + Math.max(1, res.page - 1) + '">‹ قبلی</button>'
          + '<span class="info">صفحه ' + J.toFaDigits(res.page) + ' از '
          + J.toFaDigits(res.pages) + '</span>'
          + '<button data-p="' + Math.min(res.pages, res.page + 1) + '">بعدی ›</button>'
        : '<span class="info">' + J.toFaDigits(res.total) + ' رویداد</span>';
    } catch (err) { A.toast(err.message, 'error'); }
  }

  async function loadLog() {
    try {
      var res = await A.api.get('/api/logs');
      A.qs('#log-body').textContent = res.data.lines.join('\n') || '(خالی)';
    } catch (err) { A.toast(err.message, 'error'); }
  }

  function switchTab(name) {
    A.qsa('.tab').forEach(function (t) { t.classList.toggle('active', t.dataset.tab === name); });
    A.qsa('.tab-panel').forEach(function (p) {
      p.classList.toggle('hidden', p.dataset.panel !== name);
    });
    if (name === 'backup') loadBackups();
    if (name === 'audit') loadAudit();
    if (name === 'logs') loadLog();
  }

  document.addEventListener('DOMContentLoaded', function () {
    loadSystem();
    A.qsa('.tab').forEach(function (tab) {
      tab.addEventListener('click', function () { switchTab(tab.dataset.tab); });
    });

    A.qs('#btn-backup').addEventListener('click', async function () {
      var button = A.qs('#btn-backup');
      button.disabled = true;
      try {
        var res = await A.api.post('/api/backup', {});
        A.toast(res.message);
        loadBackups();
      } catch (err) { A.toast(err.message, 'error'); }
      finally { button.disabled = false; }
    });

    A.qs('#backup-body').addEventListener('click', async function (ev) {
      var dl = ev.target.closest('[data-dl]');
      if (dl) {
        A.download('/api/backup/' + encodeURIComponent(dl.dataset.dl) + '/download');
        return;
      }
      var restore = ev.target.closest('[data-restore]');
      if (restore) {
        if (!await A.confirmDialog({
          title: 'بازیابی پایگاه داده',
          message: 'پایگاه داده‌ی فعلی با «' + restore.dataset.restore
            + '» جایگزین می‌شود. یک نسخه‌ی ایمنی از وضعیت فعلی ذخیره خواهد شد. ادامه؟',
          confirmText: 'بله، بازیابی کن'
        })) return;
        try {
          var res = await A.api.post('/api/backup/restore',
            { filename: restore.dataset.restore, confirm: 'yes' });
          A.toast(res.message);
          A.qs('#restore-result').innerHTML = '<div class="alert ok">'
            + A.esc(res.message) + '</div>';
        } catch (err) { A.toast(err.message, 'error'); }
      }
    });

    A.qs('#btn-restore-upload').addEventListener('click', async function () {
      var file = A.qs('#restore-file').files[0];
      if (!file) { A.toast('ابتدا فایل را انتخاب کنید.', 'error'); return; }
      var box = A.qs('#restore-result');
      /* First call validates only; the second one, with confirm, applies it. */
      var form = new FormData();
      form.append('file', file);
      box.innerHTML = '<div class="loading">در حال بررسی فایل</div>';
      try {
        var check = await A.api.upload('/api/backup/restore', form);
        var counts = (check.data && check.data.validation && check.data.validation.counts) || {};
        if (!await A.confirmDialog({
          title: 'تأیید بازیابی',
          message: 'فایل معتبر است ('
            + Object.entries(counts).map(function (e) { return e[0] + ': ' + e[1]; }).join('، ')
            + '). پایگاه داده‌ی فعلی جایگزین می‌شود. ادامه؟',
          confirmText: 'بله، بازیابی کن'
        })) { box.innerHTML = ''; return; }
        var form2 = new FormData();
        form2.append('file', file);
        form2.append('confirm', 'yes');
        var res = await A.api.upload('/api/backup/restore', form2);
        box.innerHTML = '<div class="alert ok">' + A.esc(res.message) + '</div>';
        A.toast(res.message);
      } catch (err) {
        box.innerHTML = '<div class="alert error">' + A.esc(err.message) + '</div>';
      }
    });

    A.qsa('#a-action,#a-entity').forEach(function (s) {
      s.addEventListener('change', function () { auditPage = 1; loadAudit(); });
    });
    A.qs('#audit-pagination').addEventListener('click', function (ev) {
      var button = ev.target.closest('[data-p]');
      if (button) { auditPage = +button.dataset.p; loadAudit(); }
    });
    A.qs('#btn-refresh-log').addEventListener('click', loadLog);
  });
})();
