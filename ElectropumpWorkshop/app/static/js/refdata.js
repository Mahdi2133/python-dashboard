/* «بانک‌های اطلاعاتی»: the three reference databases, one well's file,
   imports and manual links. */
(function () {
  'use strict';
  var A = window.App;
  var state = { ft: 1, pr: 1, vm: 1 };
  function fa(v) { return window.Jalali ? window.Jalali.toFaDigits(v) : String(v); }
  var num = function (v, d) { return window.RefPanel.num(v, d); };

  function switchTab(name) {
    A.qsa('#rd-tabs .tab').forEach(function (t) { t.classList.toggle('active', t.dataset.tab === name); });
    A.qsa('.tab-panel').forEach(function (p) { p.classList.toggle('hidden', p.dataset.panel !== name); });
    if (name === 'flowtest') loadFt();
    if (name === 'production') loadPr();
    if (name === 'videometry') loadVm();
  }

  async function loadCards() {
    try {
      var res = await A.api.get('/api/refdata/summary');
      A.qs('#rd-cards').innerHTML = res.data.sources.map(function (s) {
        var range = (s.range || []).filter(Boolean).join(' تا ');
        return '<div class="stat-card rd-card"><div class="stat-icon">' + s.icon + '</div><div class="stat-info">'
          + '<h3>' + fa(s.rows) + '</h3><p><b>' + A.esc(s.title) + '</b>'
          + (s.points != null ? ' — ' + fa(s.points) + (s.key === 'flowtest' ? ' کارکرد' : ' ماه') : '') + '</p>'
          + '<p>چاه‌های متصل: ' + fa(s.wells || 0) + (s.unmatched ? ' · بدون اتصال: ' + fa(s.unmatched) : '') + '</p>'
          + (range ? '<p>بازه: ' + A.esc(range) + '</p>' : '')
          + '<p class="hint" dir="ltr">' + A.esc(s.file) + ' — ' + fa(Math.round((s.size || 0) / 1024)) + ' KB</p>'
          + (s.errors && s.errors.length ? '<p class="hint" style="color:var(--danger)">⚠ ' + fa(s.errors.length)
             + ' فایل خوانده نشد: ' + s.errors.map(function (e) { return A.esc(e.file); }).join('، ') + '</p>' : '')
          + '</div></div>';
      }).join('');
    } catch (err) { A.qs('#rd-cards').innerHTML = '<div class="alert error">' + A.esc(err.message) + '</div>'; }
  }

  function pager(box, page, total, size, go) {
    var pages = Math.max(1, Math.ceil(total / size));
    box.innerHTML = '<button type="button" data-p="' + (page - 1) + '"' + (page <= 1 ? ' disabled' : '') + '>‹</button>'
      + '<span class="info">صفحه ' + fa(page) + ' از ' + fa(pages) + '</span>'
      + '<button type="button" data-p="' + (page + 1) + '"' + (page >= pages ? ' disabled' : '') + '>›</button>';
    box.onclick = function (e) {
      var b = e.target.closest('button[data-p]');
      if (b && !b.disabled) go(Number(b.dataset.p));
    };
  }

  function linkCell(source, r) {
    if (r.main_well) {
      return '<span title="' + A.esc(r.match_method || '') + '">' + A.esc(r.main_well) + '</span>'
        + (window.RD_MANAGE ? ' <button type="button" class="btn-sm btn-ghost rd-link" data-src="' + source + '" data-id="' + r.id + '" title="تغییر اتصال">✎</button>' : '');
    }
    return '<span class="badge warn">بدون اتصال</span>'
      + (window.RD_MANAGE ? ' <button type="button" class="btn-sm btn-ghost rd-link" data-src="' + source + '" data-id="' + r.id + '">🔗 اتصال</button>' : '');
  }

  /* ── دبی‌سنجی ─────────────────────────────────────────────────────── */
  async function loadFt(page) {
    state.ft = page || 1;
    var q = '?page=' + state.ft + '&q=' + encodeURIComponent(A.qs('#ft-q').value.trim())
      + '&office=' + encodeURIComponent(A.qs('#ft-office').value)
      + (A.qs('#ft-unmatched').checked ? '&unmatched=1' : '');
    var res = await A.api.get('/api/refdata/flowtests' + q);
    var d = res.data;
    var sel = A.qs('#ft-office'), keep = sel.value;
    if (sel.options.length <= 1) {
      sel.innerHTML = '<option value="">همه‌ی ادارات</option>' + d.offices.map(function (o) {
        return '<option>' + A.esc(o) + '</option>';
      }).join('');
      sel.value = keep;
    }
    A.qs('#ft-count').textContent = fa(d.total);
    A.qs('#ft-body').innerHTML = d.rows.length ? d.rows.map(function (r) {
      return '<tr class="clickable" data-ft="' + r.id + '"><td>' + A.esc(r.test_date || '—') + '</td><td>' + A.esc(r.well_name) + '</td>'
        + '<td>' + A.esc(r.office || '—') + '</td><td>' + linkCell('flowtest', r) + '</td>'
        + '<td dir="ltr">' + A.esc(r.electropump || '—') + '</td><td>' + num(r.well_depth) + '</td>'
        + '<td>' + num(r.install_depth) + '</td><td>' + num(r.static_level) + '</td><td>' + num(r.net_flow) + '</td>'
        + '<td>' + num(r.net_pressure) + '</td><td>' + (r.efficiency != null ? num(r.efficiency, 1) + '٪' : '—') + '</td>'
        + '<td>' + fa(r.point_count) + '</td></tr>';
    }).join('') : '<tr><td colspan="12" class="table-empty">ردیفی پیدا نشد.</td></tr>';
    pager(A.qs('#ft-pages'), d.page, d.total, d.size, loadFt);
  }

  async function openFt(id) {
    var res = await A.api.get('/api/refdata/flowtests/' + id);
    var t = res.data, box = A.qs('#ft-detail');
    box.innerHTML = '<div class="card mt-2"><div class="section-title">💧 ' + A.esc(t.well_name) + ' — ' + A.esc(t.test_date || '')
      + (t.source_file ? ' <span class="hint">(' + A.esc(t.source_file) + ')</span>' : '') + '</div>'
      + '<div class="rp-grid"><dl class="kv rp-kv">' + (t.raw_labelled || []).map(function (x) {
        var v = typeof x.value === 'number' ? num(x.value) : A.esc(String(x.value));
        return '<dt>' + A.esc(x.label) + '</dt><dd>' + v + '</dd>';
      }).join('') + '</dl><div>' + window.RefPanel.pointsTable(t)
      + (t.expert_opinion ? '<div class="hint mt-1">نظر کارشناس: ' + A.esc(t.expert_opinion) + '</div>' : '')
      + '</div></div></div>';
    box.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  /* ── روند تولید ──────────────────────────────────────────────────── */
  async function loadPr(page) {
    state.pr = page || 1;
    var q = '?page=' + state.pr + '&q=' + encodeURIComponent(A.qs('#pr-q').value.trim())
      + (A.qs('#pr-unmatched').checked ? '&unmatched=1' : '');
    var d = (await A.api.get('/api/refdata/production' + q)).data;
    A.qs('#pr-count').textContent = fa(d.total);
    A.qs('#pr-body').innerHTML = d.rows.length ? d.rows.map(function (r) {
      return '<tr class="clickable" data-pr="' + r.id + '"><td dir="ltr">' + A.esc(r.facility_code) + '</td><td>' + A.esc(r.name) + '</td>'
        + '<td>' + linkCell('production', r) + '</td><td dir="ltr">' + A.esc(r.electropump || '—') + '</td>'
        + '<td>' + A.esc(r.pump_install_date || '—') + '</td><td>' + num(r.last_flow) + '</td>'
        + '<td>' + A.esc(r.last_flow_month || '—') + '</td><td>' + A.esc(r.last_rehab_date || '—') + '</td>'
        + '<td>' + A.esc(r.zone || '—') + '</td></tr>';
    }).join('') : '<tr><td colspan="9" class="table-empty">ردیفی پیدا نشد.</td></tr>';
    pager(A.qs('#pr-pages'), d.page, d.total, d.size, loadPr);
  }

  async function openPr(id) {
    var w = (await A.api.get('/api/refdata/production/' + id)).data, box = A.qs('#pr-detail');
    box.innerHTML = '<div class="card mt-2"><div class="section-title">📈 ' + A.esc(w.name) + ' — <span dir="ltr">'
      + A.esc(w.facility_code) + '</span></div><div class="rp-chart"></div>'
      + '<div class="table-scroll" style="max-height:300px"><table class="rp-table"><thead><tr><th>سال/ماه</th><th>تولید (m³)</th>'
      + '<th>کارکرد (ساعت)</th><th>دبی متوسط (l/s)</th><th>فشار</th><th>نوع فشار</th></tr></thead><tbody>'
      + w.months.slice().reverse().map(function (m) {
        return '<tr><td>' + fa(m.year + '/' + (m.month < 10 ? '0' : '') + m.month) + '</td><td>' + num(m.production, 0) + '</td>'
          + '<td>' + num(m.hours, 0) + '</td><td>' + num(m.avg_flow) + '</td><td>' + num(m.pressure) + '</td>'
          + '<td>' + A.esc(m.pressure_type || '—') + '</td></tr>';
      }).join('') + '</tbody></table></div></div>';
    window.RefPanel.drawProduction(box.querySelector('.rp-chart'), w.months);
    box.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  /* ── ویدئومتری ───────────────────────────────────────────────────── */
  async function loadVm(page) {
    state.vm = page || 1;
    var q = '?page=' + state.vm + '&q=' + encodeURIComponent(A.qs('#vm-q').value.trim())
      + (A.qs('#vm-unmatched').checked ? '&unmatched=1' : '');
    var d = (await A.api.get('/api/refdata/videometry' + q)).data;
    A.qs('#vm-count').textContent = fa(d.total);
    A.qs('#vm-body').innerHTML = d.rows.length ? d.rows.map(function (r) {
      return '<tr><td>' + A.esc(r.insp_date || '—') + '</td><td dir="ltr">' + A.esc(r.facility_code) + '</td>'
        + '<td>' + A.esc(r.name || '') + '</td><td>' + A.esc(r.center || '') + '</td><td>' + linkCell('videometry', r) + '</td>'
        + '<td>' + num(r.depth) + '</td><td>' + num(r.static_level) + '</td><td>' + num(r.screen_start) + '</td>'
        + '<td>' + fa(r.defect_count || 0) + '</td><td title="' + A.esc(r.notes || '') + '">' + A.esc((r.notes || '').slice(0, 40)) + '</td></tr>';
    }).join('') : '<tr><td colspan="10" class="table-empty">ردیفی پیدا نشد.</td></tr>';
    pager(A.qs('#vm-pages'), d.page, d.total, d.size, loadVm);
  }

  /* ── manual link ─────────────────────────────────────────────────── */
  async function linkRow(source, id) {
    var name = window.prompt('نام دقیق چاه در سامانه (همان‌طور که در «چاه‌ها» ثبت است)؛ خالی = برداشتن اتصال:');
    if (name === null) return;
    try {
      var res = await A.api.post('/api/refdata/' + source + '/' + id + '/link',
                                 name.trim() ? { well: name.trim() } : { unlink: true });
      A.toast(res.message, 'success');
      if (source === 'flowtest') loadFt(state.ft);
      if (source === 'production') loadPr(state.pr);
      if (source === 'videometry') loadVm(state.vm);
      loadCards();
    } catch (err) { A.toast(err.message, 'error'); }
  }

  /* ── import ──────────────────────────────────────────────────────── */
  async function importFiles(input) {
    if (!input.files.length) return;
    var form = new FormData();
    Array.prototype.forEach.call(input.files, function (f) { form.append('files', f); });
    var box = A.qs('#rd-import-result');
    box.innerHTML = '<div class="loading">در حال خواندن فایل‌ها… (فایل‌های بزرگ ممکن است چند دقیقه طول بکشد)</div>';
    try {
      var res = await A.api.upload('/api/refdata/' + input.dataset.source + '/import', form);
      box.innerHTML = '<div class="alert info">' + res.data.results.map(function (r) {
        if (r.error) return '⛔ ' + A.esc(r.file) + ': ' + A.esc(r.error);
        if (r.duplicate) return 'ℹ ' + A.esc(r.file) + ': قبلاً وارد شده است.';
        var parts = [];
        ['files', 'sheets', 'tests_added', 'tests_updated', 'unmatched', 'wells', 'months', 'rows', 'added', 'updated', 'year']
          .forEach(function (k) { if (r[k] !== undefined) parts.push(k + ': ' + fa(Array.isArray(r[k]) ? r[k].length : r[k])); });
        var errs = (r.errors || []).length ? '<br>⚠ ' + r.errors.map(A.esc).join('<br>⚠ ') : '';
        return '✓ ' + A.esc(r.file) + ' — ' + parts.join('، ') + errs;
      }).join('<br>') + '</div>';
      loadCards();
    } catch (err) { box.innerHTML = '<div class="alert error">' + A.esc(err.message) + '</div>'; }
    input.value = '';
  }

  document.addEventListener('DOMContentLoaded', function () {
    window.RD_MANAGE = window.IS_ADMIN || (window.CAN || []).indexOf('refdata.manage') !== -1;
    if (!window.RD_MANAGE) {
      var imp = A.qs('#rd-tabs [data-tab="import"]'); if (imp) imp.classList.add('hidden');
    }
    loadCards();
    A.qsa('#rd-tabs .tab').forEach(function (t) { t.addEventListener('click', function () { switchTab(t.dataset.tab); }); });
    window.FormEngine.attachAutocomplete(A.qs('#rd-well'), {});
    var show = function () { window.RefPanel.load(A.qs('#rd-well-box'), A.qs('#rd-well').value.trim()); };
    A.qs('#rd-well-go').addEventListener('click', show);
    A.qs('#rd-well').addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); show(); } });
    ['ft', 'pr', 'vm'].forEach(function (k) {
      var loader = { ft: loadFt, pr: loadPr, vm: loadVm }[k];
      A.qs('#' + k + '-q').addEventListener('input', A.debounce(function () { loader(1); }, 350));
      A.qs('#' + k + '-unmatched').addEventListener('change', function () { loader(1); });
    });
    A.qs('#ft-office').addEventListener('change', function () { loadFt(1); });
    A.qs('#ft-body').addEventListener('click', function (e) {
      if (e.target.closest('.rd-link')) return;
      var tr = e.target.closest('tr[data-ft]'); if (tr) openFt(tr.dataset.ft);
    });
    A.qs('#pr-body').addEventListener('click', function (e) {
      if (e.target.closest('.rd-link')) return;
      var tr = e.target.closest('tr[data-pr]'); if (tr) openPr(tr.dataset.pr);
    });
    document.addEventListener('click', function (e) {
      var b = e.target.closest('.rd-link'); if (b) linkRow(b.dataset.src, b.dataset.id);
    });
    A.qsa('.rd-file').forEach(function (inp) { inp.addEventListener('change', function () { importFiles(inp); }); });
    A.qs('#rd-relink').addEventListener('click', async function () {
      try {
        var res = await A.api.post('/api/refdata/relink', {});
        A.qs('#rd-import-result').innerHTML = '<div class="alert info">' + A.esc(res.message) + ' دبی‌سنجی: '
          + fa(res.data.flowtest.linked) + '، روند تولید: ' + fa(res.data.production.linked) + '، ویدئومتری: '
          + fa(res.data.videometry.linked) + ' ردیف متصل.</div>';
        loadCards();
      } catch (err) { A.toast(err.message, 'error'); }
    });
  });
})();
