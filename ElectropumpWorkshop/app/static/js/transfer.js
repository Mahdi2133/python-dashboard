(function () {
  'use strict';
  var A = window.App, J = window.Jalali;
  var uploaded = null, preview = null;

  function switchTab(name) {
    A.qsa('.tab').forEach(function (t) { t.classList.toggle('active', t.dataset.tab === name); });
    A.qsa('.tab-panel').forEach(function (p) {
      p.classList.toggle('hidden', p.dataset.panel !== name);
    });
    if (name === 'history') loadHistory();
  }

  /* ── upload ─────────────────────────────────────────────────────────── */
  async function upload(file) {
    var status = A.qs('#upload-status');
    status.innerHTML = '<div class="loading">در حال بارگذاری</div>';
    var form = new FormData();
    form.append('file', file);
    try {
      var res = await A.api.upload('/api/import/upload', form);
      uploaded = res.data;
      status.innerHTML = '<div class="alert ok">فایل «' + A.esc(uploaded.filename)
        + '» بارگذاری شد — ' + uploaded.sheets.length + ' شیت.</div>';
      A.qs('#sheet-select').innerHTML = uploaded.sheets.map(function (s) {
        return '<option value="' + A.esc(s) + '">' + A.esc(s) + '</option>';
      }).join('');
      A.qs('#sheet-card').classList.remove('hidden');
    } catch (err) {
      status.innerHTML = '<div class="alert error">' + A.esc(err.message) + '</div>';
    }
  }

  async function runPreview() {
    if (!uploaded) return;
    var button = A.qs('#btn-preview');
    button.disabled = true;
    try {
      var res = await A.api.get('/api/import/preview?' + A.serializeQuery({
        filename: uploaded.filename, sheet: A.qs('#sheet-select').value, limit: 12
      }));
      preview = res.data;
      renderMapping();
      renderPreview();
      A.qs('#mapping-card').classList.remove('hidden');
      A.qs('#preview-card').classList.remove('hidden');
      A.qs('#commit-card').classList.remove('hidden');
    } catch (err) { A.toast(err.message, 'error'); }
    finally { button.disabled = false; }
  }

  function renderMapping() {
    var mapped = Object.values(preview.mapping).filter(Boolean).length;
    A.qs('#map-count').textContent = mapped + ' از ' + preview.columns.length
      + ' ستون تشخیص داده شد';
    A.qs('#map-warning').innerHTML = preview.warning
      ? '<div class="alert warn">' + A.esc(preview.warning) + '</div>'
      : '<div class="alert info">نگاشت پیشنهادی زیر را بررسی و در صورت نیاز اصلاح کنید. '
        + 'ستون‌های بدون نگاشت وارد نمی‌شوند.</div>';

    var options = '<option value="">— وارد نشود —</option>'
      + (preview.targets || []).map(function (t) {
          return '<option value="' + A.esc(t.key) + '">' + A.esc(t.label) + '</option>';
        }).join('');
    var sample = (preview.rows[0] || []);
    A.qs('#mapping-body').innerHTML = preview.columns.map(function (col) {
      var current = preview.mapping[String(col.index)] || '';
      return '<tr><td>' + col.index + '</td>'
        + '<td>' + A.esc(col.group || '') + '</td>'
        + '<td>' + A.esc(col.title || '') + '</td>'
        + '<td class="muted small">' + A.esc((sample[col.index] || '').slice(0, 28)) + '</td>'
        + '<td><select data-col="' + col.index + '">' + options + '</select></td></tr>';
    }).join('');
    preview.columns.forEach(function (col) {
      var select = A.qs('[data-col="' + col.index + '"]');
      if (select) select.value = preview.mapping[String(col.index)] || '';
    });
  }

  function renderPreview() {
    A.qs('#preview-head').innerHTML = preview.columns
      .map(function (c) { return '<th>' + A.esc(c.title || c.index) + '</th>'; }).join('');
    A.qs('#preview-body').innerHTML = preview.rows.map(function (row) {
      return '<tr>' + preview.columns.map(function (c) {
        return '<td>' + A.esc((row[c.index] || '').slice(0, 24)) + '</td>';
      }).join('') + '</tr>';
    }).join('');
  }

  function currentMapping() {
    var mapping = {};
    A.qsa('[data-col]').forEach(function (select) {
      mapping[select.dataset.col] = select.value || null;
    });
    return mapping;
  }

  async function commit(dryRun) {
    var box = A.qs('#commit-result');
    box.innerHTML = '<div class="loading">در حال پردازش</div>';
    try {
      var res = await A.api.post('/api/import/commit', {
        filename: uploaded.filename, sheet: A.qs('#sheet-select').value,
        mapping: currentMapping(), data_start: preview.data_start,
        skip_duplicates: A.qs('#skip-dupes').checked, dry_run: dryRun
      });
      var d = res.data;
      var html = '<div class="alert ' + (d.failed ? 'warn' : 'ok') + '">'
        + A.esc(res.message) + '</div>'
        + '<div class="summary-strip">'
        + '<span>کل سطر: <b>' + J.toFaDigits(d.total_rows) + '</b></span>'
        + '<span>درج‌شده: <b>' + J.toFaDigits(d.inserted) + '</b></span>'
        + '<span>ردشده: <b>' + J.toFaDigits(d.skipped) + '</b></span>'
        + '<span>خطا: <b>' + J.toFaDigits(d.failed) + '</b></span>'
        + '<span>هشدار: <b>' + J.toFaDigits(d.warnings || 0) + '</b></span></div>';
      if (d.errors && d.errors.length) {
        html += '<div class="table-scroll" style="max-height:260px"><table>'
          + '<thead><tr><th>سطر</th><th>نوع</th><th>پیام</th></tr></thead><tbody>'
          + d.errors.map(function (e) {
              var badge = e.level === 'error' ? 'danger'
                : (e.level === 'warning' ? 'warn' : 'muted');
              return '<tr><td>' + e.row + '</td><td><span class="badge ' + badge + '">'
                + A.esc(e.level) + '</span></td><td>' + A.esc(e.message) + '</td></tr>';
            }).join('') + '</tbody></table></div>';
      }
      box.innerHTML = html;
      A.toast(res.message, d.failed ? 'warn' : undefined);
    } catch (err) {
      box.innerHTML = '<div class="alert error">' + A.esc(err.message) + '</div>';
    }
  }

  /* ── localStorage ───────────────────────────────────────────────────── */
  function detectLocal() {
    var raw = null;
    try { raw = localStorage.getItem('electropump_records_v1'); }
    catch (e) { raw = null; }
    if (!raw) {
      A.qs('#local-result').innerHTML = '<div class="alert warn">'
        + 'در این مرورگر داده‌ای با کلید <code>electropump_records_v1</code> پیدا نشد. '
        + 'اگر داده روی رایانه‌ی دیگری است، فایل JSON آن را در کادر بالا بچسبانید.</div>';
      return;
    }
    A.qs('#local-json').value = raw;
    var count = 0;
    try { count = JSON.parse(raw).length; } catch (e) { count = 0; }
    A.qs('#local-result').innerHTML = '<div class="alert ok">'
      + J.toFaDigits(count) + ' رکورد در این مرورگر پیدا شد و در کادر بالا قرار گرفت.</div>';
  }

  async function migrateLocal() {
    var text = A.qs('#local-json').value.trim();
    if (!text) { A.toast('ابتدا محتوای JSON را وارد کنید.', 'error'); return; }
    var box = A.qs('#local-result');
    box.innerHTML = '<div class="loading">در حال انتقال</div>';
    try {
      var res = await A.api.post('/api/import/localstorage',
        { records: text, skip_duplicates: true });
      var d = res.data;
      box.innerHTML = '<div class="alert ok">' + A.esc(res.message) + '</div>'
        + '<div class="summary-strip"><span>درج: <b>' + J.toFaDigits(d.inserted)
        + '</b></span><span>تکراری: <b>' + J.toFaDigits(d.skipped)
        + '</b></span><span>خطا: <b>' + J.toFaDigits(d.failed) + '</b></span></div>';
      A.toast(res.message);
    } catch (err) {
      box.innerHTML = '<div class="alert error">' + A.esc(err.message) + '</div>';
    }
  }

  async function loadHistory() {
    try {
      var res = await A.api.get('/api/imports');
      A.qs('#history-body').innerHTML = res.data.length ? res.data.map(function (b) {
        return '<tr><td>' + b.id + '</td><td>' + A.esc(b.filename || '') + '</td>'
          + '<td>' + A.esc(b.sheet_name || '') + '</td>'
          + '<td>' + J.toFaDigits(b.total_rows) + '</td>'
          + '<td>' + J.toFaDigits(b.inserted) + '</td>'
          + '<td>' + J.toFaDigits(b.skipped) + '</td>'
          + '<td>' + J.toFaDigits(b.failed) + '</td>'
          + '<td><span class="badge">' + A.esc(b.status) + '</span></td>'
          + '<td>' + A.esc(b.message || '') + '</td></tr>';
      }).join('') : '<tr><td colspan="9" class="table-empty">تاریخچه‌ای وجود ندارد</td></tr>';
    } catch (err) { A.toast(err.message, 'error'); }
  }

  document.addEventListener('DOMContentLoaded', function () {
    A.qsa('.jdate').forEach(function (input) { J.attach(input); });
    A.qsa('.tab').forEach(function (tab) {
      tab.addEventListener('click', function () { switchTab(tab.dataset.tab); });
    });

    var zone = A.qs('#drop-zone'), input = A.qs('#file-input');
    zone.addEventListener('click', function () { input.click(); });
    input.addEventListener('change', function () {
      if (input.files[0]) upload(input.files[0]);
    });
    ['dragenter', 'dragover'].forEach(function (evt) {
      zone.addEventListener(evt, function (ev) {
        ev.preventDefault(); zone.classList.add('over');
      });
    });
    ['dragleave', 'drop'].forEach(function (evt) {
      zone.addEventListener(evt, function (ev) {
        ev.preventDefault(); zone.classList.remove('over');
      });
    });
    zone.addEventListener('drop', function (ev) {
      if (ev.dataTransfer.files[0]) upload(ev.dataTransfer.files[0]);
    });

    A.qs('#btn-preview').addEventListener('click', runPreview);
    A.qs('#btn-dryrun').addEventListener('click', function () { commit(true); });
    A.qs('#btn-commit').addEventListener('click', async function () {
      if (!await A.confirmDialog({
        title: 'ورود داده', danger: false, confirmText: 'شروع ورود داده',
        message: 'رکوردها به پایگاه داده افزوده می‌شوند. '
                 + 'پیشنهاد می‌شود ابتدا «بررسی آزمایشی» را اجرا کنید.'
      })) return;
      commit(false);
    });

    A.qs('#btn-detect-local').addEventListener('click', detectLocal);
    A.qs('#btn-migrate-local').addEventListener('click', migrateLocal);

    A.qsa('[data-raw]').forEach(function (button) {
      button.addEventListener('click', function () {
        A.download('/api/export.' + button.dataset.raw + '?' + A.serializeQuery({
          date_from: A.qs('#e-date-from').value.trim(),
          date_to: A.qs('#e-date-to').value.trim(),
          year: A.qs('#e-year').value
        }));
      });
    });
    var y = J.today()[0];
    for (var i = y; i >= y - 12; i--) {
      A.qs('#e-year').appendChild(A.el('option', { value: i, text: i }));
    }
  });
})();
