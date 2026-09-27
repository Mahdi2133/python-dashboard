/* ==========================================================================
   خروجی گزارش — the reports a person was granted, at the levels granted.

   The page only offers what the server said this person may do (levels in
   /view), and the server checks every call again regardless.
   ========================================================================== */
(function () {
  'use strict';
  var A = window.App, RV = window.ReportView, J = window.Jalali;
  var API = '/api/analytics';
  var R = {
    catalog: [], cats: [], cfg: null, report: null, levels: [], values: {},
    result: null, snapshot: null, drill: [], draft: false, tab: 'dashboard',
    an: { page: 1, sort: null, dir: 'asc', keys: null, search: '' }, raw: { page: 1 }
  };
  var FORMATS = [
    ['xlsx', '📊 Excel', 'export_xlsx', 'export-xlsx'], ['pdf', '📕 PDF', 'export_pdf', 'export-pdf'],
    ['docx', '📘 Word', 'export_docx', 'export-json'], ['csv', '📄 CSV', 'export_csv', 'export-csv'],
    ['json', '🗂 JSON', 'export_json', 'export-json'], ['print', '🖨 چاپ', 'print', 'export-print']
  ];
  function el(t, a, k) { return A.el(t, a, k); }
  function has(level) { return R.levels.indexOf(level) >= 0; }
  function fmt(v, c) { return RV.fmt(v, c); }

  /* ═════════════ catalog ═════════════ */
  async function loadCatalog() {
    try {
      var res = await A.api.get(API + '/catalog');
      R.catalog = res.data.reports;
      R.cats = res.data.categories;
      var sel = A.qs('#rp-category');
      sel.innerHTML = '<option value="">همه‌ی دسته‌ها</option>';
      R.cats.forEach(function (c) { sel.appendChild(el('option', { value: c.id, text: c.name })); });
      drawCatalog();
    } catch (err) {
      A.qs('#rp-list').innerHTML = '<div class="alert error">' + A.esc(err.message) + '</div>';
    }
  }
  function drawCatalog() {
    var q = A.qs('#rp-search').value.trim(), cat = A.qs('#rp-category').value, fav = A.qs('#rp-fav-only').checked;
    var box = A.qs('#rp-list');
    box.innerHTML = '';
    var list = R.catalog.filter(function (r) {
      return (!q || r.name.indexOf(q) >= 0 || (r.description || '').indexOf(q) >= 0)
        && (!cat || String(r.category_id) === cat) && (!fav || r.favorite);
    });
    if (!list.length) {
      box.appendChild(el('div', { class: 'muted small', text: R.catalog.length ? 'گزارشی با این جستجو نیست.' : 'هنوز گزارشی برای شما منتشر نشده است.' }));
      return;
    }
    var lastCat = null;
    list.forEach(function (r) {
      var c = r.favorite ? '★ علاقه‌مندی‌ها' : (r.category || 'بدون دسته');
      if (c !== lastCat) { box.appendChild(el('div', { class: 'pal-group-title', text: c })); lastCat = c; }
      var item = el('div', { class: 'rp-item' + (R.report && R.report.id === r.id ? ' active' : '') });
      item.innerHTML = '<b>' + A.esc(r.name) + '</b>' + (r.description ? '<p>' + A.esc(r.description) + '</p>' : '');
      item.addEventListener('click', function () { openReport(r.id); });
      box.appendChild(item);
    });
  }

  /* ═════════════ open ═════════════ */
  function storeKey() { return 'rp-filters-' + (R.report ? R.report.id : ''); }
  async function openReport(id, draft) {
    try {
      var res = await A.api.get(API + '/reports/' + id + '/view' + (draft ? '?draft=1' : ''));
      R.cfg = res.data; R.report = res.data.report; R.levels = res.data.levels;
      R.draft = !!draft; R.snapshot = null; R.drill = []; R.an = { page: 1, sort: null, dir: 'asc', keys: null, search: '' }; R.raw = { page: 1 };
      try { R.values = JSON.parse(localStorage.getItem(storeKey()) || '{}') || {}; } catch (e) { R.values = {}; }
      try { history.replaceState(null, '', '/reports?report=' + id + (draft ? '&draft=1' : '')); } catch (e) { /* ok */ }
      A.qs('#rp-empty').classList.add('hidden');
      A.qs('#rp-report').classList.remove('hidden');
      drawHead(); drawFilters(); drawTabs();
      switchTab(has('view_dashboard') || has('run') ? 'dashboard' : 'analysis');
      drawCatalog();
    } catch (err) { A.toast(err.message, 'error'); }
  }

  function drawHead() {
    var r = R.report, cfg = R.cfg;
    A.qs('#rp-name').textContent = r.name;
    A.qs('#rp-desc').textContent = r.description || '';
    var fav = R.catalog.filter(function (x) { return x.id === r.id; })[0];
    A.qs('#rp-fav').textContent = fav && fav.favorite ? '★' : '☆';
    A.qs('#rp-badges').innerHTML = (r.category ? '<span class="badge muted">' + A.esc(r.category) + '</span> ' : '')
      + '<span class="badge">نسخه ' + A.esc(cfg.version) + '</span> '
      + '<span class="badge muted">منبع: ' + A.esc(cfg.source_label || '') + '</span>'
      + (r.scope_to_centers ? ' <span class="badge warn">فقط مراکز شما</span>' : '');
    var banner = A.qs('#rp-banner');
    banner.classList.toggle('hidden', !R.draft);
    if (R.draft) banner.textContent = 'پیش‌نمایش مدیر سیستم: نسخه‌ی کاری (منتشرنشده) نمایش داده می‌شود.';
    var ex = A.qs('#rp-exports');
    ex.innerHTML = '';
    FORMATS.forEach(function (f) {
      if (!has(f[2])) return;
      ex.appendChild(el('button', { type: 'button', class: 'export-btn ' + f[3], text: f[1], onclick: function () { openExport(f[0], f[1]); } }));
    });
    A.qs('#rp-snap-btn').classList.toggle('hidden', !(has('view_dashboard') || has('run')));
  }

  function drawTabs() {
    var an = R.cfg.analysis || {}, drill = R.cfg.drill || {};
    var show = {
      dashboard: has('view_dashboard') || has('run'),
      analysis: has('view_analysis') && an.enabled !== false,
      drill: has('drilldown') && drill.enabled && (drill.path || []).length > 0,
      raw: has('raw_data'),
      snapshots: true
    };
    A.qsa('#rp-tabs .tab').forEach(function (t) { t.classList.toggle('hidden', !show[t.dataset.tab]); });
    A.qs('#an-xtab-card').classList.toggle('hidden', an.crosstab === false);
    A.qs('#an-stats-card').classList.toggle('hidden', an.stats === false);
  }

  function switchTab(tab) {
    R.tab = tab;
    A.qsa('#rp-tabs .tab').forEach(function (t) { t.classList.toggle('active', t.dataset.tab === tab); });
    A.qsa('.rp-panel').forEach(function (p) { p.classList.toggle('hidden', p.dataset.panel !== tab); });
    if (tab === 'dashboard') runDashboard();
    else if (tab === 'analysis') { loadDetail(); setupCrosstab(); }
    else if (tab === 'drill') runDrill();
    else if (tab === 'raw') loadRaw();
    else if (tab === 'snapshots') loadSnapshots();
  }

  /* ═════════════ interactive filters ═════════════ */
  function drawFilters() {
    var box = A.qs('#rp-filter-controls');
    box.innerHTML = '';
    var list = R.cfg.interactive_filters || [];
    A.qs('#rp-filters').classList.toggle('hidden', !list.length || !has('filter'));
    list.forEach(function (f) {
      var key = f.id || f.field, cur = R.values[key];
      var wrap = el('div', { class: 'field rp-filter' });
      wrap.appendChild(el('label', { text: f.label }));
      var kind = f.kind || 'select';
      if (kind === 'select') {
        var s = el('select', {});
        s.appendChild(el('option', { value: '', text: 'همه' }));
        (f.options || []).forEach(function (o) { s.appendChild(el('option', { value: o, text: o })); });
        s.value = cur || '';
        s.addEventListener('change', function () { R.values[key] = s.value || undefined; apply(); });
        wrap.appendChild(s);
      } else if (kind === 'multi') {
        var d = el('details', { class: 'rp-multi' });
        var sum = el('summary', { text: (cur && cur.length) ? cur.length.toLocaleString('fa-IR') + ' مورد' : 'همه' });
        d.appendChild(sum);
        var inner = el('div', { class: 'rp-multi-list' });
        (f.options || []).forEach(function (o) {
          var c = el('input', { type: 'checkbox' });
          c.checked = (cur || []).indexOf(o) >= 0;
          c.addEventListener('change', function () {
            var v = R.values[key] = (R.values[key] || []).filter(function (x) { return x !== o; });
            if (c.checked) v.push(o);
            sum.textContent = v.length ? v.length.toLocaleString('fa-IR') + ' مورد' : 'همه';
          });
          inner.appendChild(el('label', { class: 'mini-check' }, [c, document.createTextNode(' ' + o)]));
        });
        d.appendChild(inner);
        wrap.appendChild(d);
      } else if (kind === 'date_range') {
        cur = cur || {};
        var row = el('div', { class: 'rp-range' });
        var rel = el('select', {});
        rel.appendChild(el('option', { value: '', text: 'بازه‌ی دلخواه' }));
        [['today', 'امروز'], ['this_week', 'این هفته'], ['this_month', 'این ماه'], ['last_month', 'ماه قبل'],
          ['this_quarter', 'این فصل'], ['last_quarter', 'فصل قبل'], ['this_year', 'امسال'], ['last_year', 'سال قبل'],
          ['last_30', '۳۰ روز اخیر'], ['last_90', '۹۰ روز اخیر'], ['last_365', 'یک سال اخیر']].forEach(function (o) {
          rel.appendChild(el('option', { value: o[0], text: o[1] })); });
        rel.value = cur.relative || '';
        var from = el('input', { type: 'text', placeholder: 'از', value: cur.from || '' });
        var to = el('input', { type: 'text', placeholder: 'تا', value: cur.to || '' });
        if (J && J.attach) setTimeout(function () { J.attach(from); J.attach(to); }, 0);
        function upd() {
          R.values[key] = { relative: rel.value || undefined, from: rel.value ? undefined : from.value || undefined, to: rel.value ? undefined : to.value || undefined };
          from.disabled = to.disabled = !!rel.value;
        }
        rel.addEventListener('change', upd); from.addEventListener('change', upd); to.addEventListener('change', upd);
        from.disabled = to.disabled = !!rel.value;
        row.appendChild(rel); row.appendChild(from); row.appendChild(to);
        wrap.appendChild(row);
      } else if (kind === 'number_range') {
        cur = cur || {};
        var nr = el('div', { class: 'rp-range' });
        var mn = el('input', { type: 'number', placeholder: 'از', value: cur.min === undefined ? '' : cur.min });
        var mx = el('input', { type: 'number', placeholder: 'تا', value: cur.max === undefined ? '' : cur.max });
        function updn() { R.values[key] = { min: mn.value === '' ? undefined : Number(mn.value), max: mx.value === '' ? undefined : Number(mx.value) }; }
        mn.addEventListener('change', updn); mx.addEventListener('change', updn);
        nr.appendChild(mn); nr.appendChild(mx);
        wrap.appendChild(nr);
      } else {
        var i = el('input', { type: 'search', placeholder: 'شامل…', value: cur || '' });
        i.addEventListener('change', function () { R.values[key] = i.value || undefined; });
        wrap.appendChild(i);
      }
      box.appendChild(wrap);
    });
  }
  function cleanValues() {
    var out = {};
    Object.keys(R.values || {}).forEach(function (k) {
      var v = R.values[k];
      if (v === undefined || v === null || v === '') return;
      if (Array.isArray(v) && !v.length) return;
      if (typeof v === 'object' && !Array.isArray(v) && !Object.keys(v).some(function (x) { return v[x] !== undefined && v[x] !== ''; })) return;
      out[k] = v;
    });
    return out;
  }
  function apply() {
    try { localStorage.setItem(storeKey(), JSON.stringify(cleanValues())); } catch (e) { /* ok */ }
    R.snapshot = null; R.drill = []; R.an.page = 1; R.raw.page = 1;
    switchTab(R.tab === 'snapshots' ? 'dashboard' : R.tab);
  }
  function body(extra) {
    return Object.assign({ filters: cleanValues(), draft: R.draft ? 1 : undefined }, extra || {});
  }

  /* ═════════════ dashboard ═════════════ */
  function renderOpts() {
    return {
      onChartClick: function (def, data, idx, label) {
        var x = (def.x || {}).field;
        var f = (R.cfg.interactive_filters || []).filter(function (fl) { return fl.field === x; })[0];
        if (f && has('filter') && (f.kind === 'select' || f.kind === 'multi') && !(def.x || {}).granularity) {
          R.values[f.id || f.field] = f.kind === 'multi' ? [label] : label;
          drawFilters(); apply();
          A.toast('فیلتر «' + f.label + '» = ' + label, 'info');
          return;
        }
        var path = (R.cfg.drill || {}).path || [];
        if (has('drilldown') && (R.cfg.drill || {}).enabled && path.length && String(path[0]).split(':')[0] === x && !(def.x || {}).granularity) {
          R.drill = [{ key: label, label: label }];
          switchTab('drill');
        }
      },
      onRowClick: function (def, table, row) {
        var path = (R.cfg.drill || {}).path || [];
        var g0 = ((R.cfg.groups || [])[0] || {}).field;
        if (has('drilldown') && (R.cfg.drill || {}).enabled && path.length && String(path[0]).split(':')[0] === g0) {
          R.drill = [{ key: row._key[0], label: row.g0 }];
          switchTab('drill');
        }
      }
    };
  }
  async function runDashboard() {
    var box = A.qs('#rp-dashboard'), meta = A.qs('#rp-meta');
    if (R.snapshot) { drawSnapshot(); return; }
    box.innerHTML = '<div class="loading">در حال محاسبه</div>';
    var started = Date.now();
    try {
      var res = await A.api.post(API + '/reports/' + R.report.id + '/run', body());
      R.result = res.data;
      meta.textContent = 'ردیف‌های داده: ' + fmt(res.data.row_count) + ' · زمان اجرا: ' + res.data.generated_at
        + ' · ' + ((Date.now() - started) / 1000).toLocaleString('fa-IR', { maximumFractionDigits: 1 }) + ' ثانیه';
      RV.render(box, R.cfg, res.data, renderOpts());
    } catch (err) {
      box.innerHTML = '<div class="alert error">' + A.esc(err.message) + '</div>';
    }
  }

  /* ═════════════ analysis ═════════════ */
  function fieldLabel(k) { return (R.cfg.field_labels || {})[k] || k; }
  async function loadDetail() {
    var t = A.qs('#an-table');
    t.innerHTML = '<tr><td class="loading">در حال بارگذاری</td></tr>';
    try {
      var res = await A.api.post(API + '/reports/' + R.report.id + '/analysis/detail', body({
        page: R.an.page, page_size: 50, search: R.an.search || undefined, keys: R.an.keys || undefined,
        sort: R.an.sort ? [{ key: R.an.sort, dir: R.an.dir }] : undefined }));
      var d = res.data;
      if (!R.an.keys) R.an.keys = d.columns.map(function (c) { return c.key; });
      drawColumnPicker();
      t.innerHTML = '<thead><tr>' + d.columns.map(function (c) {
        return '<th data-k="' + A.esc(c.key) + '">' + A.esc(c.label) + (R.an.sort === c.key ? (R.an.dir === 'asc' ? ' ▲' : ' ▼') : '') + '</th>';
      }).join('') + '</tr></thead><tbody>' + (d.rows.length ? d.rows.map(function (r) {
        return '<tr>' + d.columns.map(function (c) { return '<td>' + A.esc(fmt(r[c.key])) + '</td>'; }).join('') + '</tr>';
      }).join('') : '<tr><td class="table-empty" colspan="' + d.columns.length + '">ردیفی نیست</td></tr>') + '</tbody>';
      A.qs('#an-count').textContent = fmt(d.row_count) + ' ردیف';
      A.qsa('th', t).forEach(function (th) {
        th.addEventListener('click', function () {
          if (R.an.sort === th.dataset.k) R.an.dir = R.an.dir === 'asc' ? 'desc' : 'asc'; else { R.an.sort = th.dataset.k; R.an.dir = 'asc'; }
          loadDetail();
        });
      });
      pager(A.qs('#an-pager'), d.page, Math.ceil(d.row_count / d.page_size), function (p) { R.an.page = p; loadDetail(); });
    } catch (err) { t.innerHTML = '<tr><td class="alert error">' + A.esc(err.message) + '</td></tr>'; }
  }
  function drawColumnPicker() {
    var box = A.qs('#an-cols');
    if (box.dataset.for === String(R.report.id)) return;
    box.dataset.for = String(R.report.id);
    box.innerHTML = '';
    var groups = {};
    (R.cfg.fields || []).forEach(function (f) { (groups[f.group] = groups[f.group] || []).push(f); });
    Object.keys(groups).forEach(function (g) {
      box.appendChild(el('div', { class: 'pal-group-title', text: g }));
      groups[g].forEach(function (f) {
        var c = el('input', { type: 'checkbox' });
        c.checked = R.an.keys.indexOf(f.key) >= 0;
        c.addEventListener('change', function () {
          R.an.keys = R.an.keys.filter(function (k) { return k !== f.key; });
          if (c.checked) R.an.keys.push(f.key);
          loadDetail();
        });
        box.appendChild(el('label', { class: 'mini-check' }, [c, document.createTextNode(' ' + f.label)]));
      });
    });
  }
  function pager(box, page, pages, go) {
    box.innerHTML = '';
    if (pages <= 1) return;
    box.appendChild(el('button', { type: 'button', class: 'btn-sm btn-ghost', text: '›', disabled: page <= 1 ? 'disabled' : null, onclick: function () { go(page - 1); } }));
    box.appendChild(el('span', { text: 'صفحه ' + fmt(page) + ' از ' + fmt(pages) }));
    box.appendChild(el('button', { type: 'button', class: 'btn-sm btn-ghost', text: '‹', disabled: page >= pages ? 'disabled' : null, onclick: function () { go(page + 1); } }));
  }
  function setupCrosstab() {
    var rs = A.qs('#xt-row'), cs = A.qs('#xt-col'), ag = A.qs('#xt-agg'), fs = A.qs('#xt-field');
    if (rs.dataset.for === String(R.report.id)) return;
    rs.dataset.for = String(R.report.id);
    [rs, cs, fs].forEach(function (s) { s.innerHTML = ''; });
    var dims = (R.cfg.fields || []).filter(function (f) { return ['single', 'multi', 'center', 'user', 'boolean', 'date', 'datetime'].indexOf(f.type) >= 0; });
    dims.sort(function (a, b) { var r = function (f) { return f.type === 'center' ? 0 : f.type === 'single' ? 1 : f.type === 'date' ? 2 : 3; }; return r(a) - r(b); });
    dims.forEach(function (f) { rs.appendChild(el('option', { value: f.key, text: f.label })); cs.appendChild(el('option', { value: f.key, text: f.label })); });
    if (dims[1]) cs.value = dims[1].key;
    ag.innerHTML = '';
    [['count', 'تعداد'], ['sum', 'جمع'], ['avg', 'میانگین'], ['median', 'میانه'], ['min', 'کمینه'], ['max', 'بیشینه'], ['count_distinct', 'تعداد یکتا']].forEach(function (a) {
      ag.appendChild(el('option', { value: a[0], text: a[1] })); });
    fs.appendChild(el('option', { value: '*', text: '(ردیف‌ها)' }));
    (R.cfg.fields || []).filter(function (f) { return ['integer', 'decimal', 'percent'].indexOf(f.type) >= 0; }).forEach(function (f) {
      fs.appendChild(el('option', { value: f.key, text: f.label })); });
  }
  async function runCrosstab() {
    var out = A.qs('#xt-out');
    out.innerHTML = '<div class="loading">در حال محاسبه</div>';
    var rowF = A.qs('#xt-row').value, colF = A.qs('#xt-col').value;
    var dateGran = function (k) { var f = (R.cfg.fields || []).filter(function (x) { return x.key === k; })[0]; return f && (f.type === 'date' || f.type === 'datetime') ? 'month' : undefined; };
    try {
      var res = await A.api.post(API + '/reports/' + R.report.id + '/analysis/crosstab', body({
        row_field: rowF, col_field: colF, row_granularity: dateGran(rowF), col_granularity: dateGran(colF),
        measure: { agg: A.qs('#xt-agg').value, field: A.qs('#xt-agg').value === 'count' ? '*' : A.qs('#xt-field').value } }));
      var d = res.data, max = 0;
      d.cells.forEach(function (r) { r.forEach(function (v) { max = Math.max(max, RV.num(v) || 0); }); });
      var html = '<table class="rv-grid rp-xtab"><thead><tr><th>' + A.esc(d.row_label) + ' \\ ' + A.esc(d.col_label) + '</th>'
        + d.cols.map(function (c) { return '<th>' + A.esc(c) + '</th>'; }).join('') + '<th>جمع</th></tr></thead><tbody>';
      d.rows.forEach(function (r, i) {
        html += '<tr><th>' + A.esc(r) + '</th>' + d.cells[i].map(function (v) {
          var n = RV.num(v) || 0, a = max ? n / max : 0;
          return '<td style="background:rgba(31,111,165,' + (a * 0.55).toFixed(2) + ');' + (a > .6 ? 'color:#fff' : '') + '">' + A.esc(v === null ? '' : fmt(v)) + '</td>';
        }).join('') + '<td><b>' + A.esc(fmt(d.row_totals[i])) + '</b></td></tr>';
      });
      html += '</tbody><tfoot><tr><td>جمع</td>' + d.col_totals.map(function (v) { return '<td>' + A.esc(fmt(v)) + '</td>'; }).join('')
        + '<td>' + A.esc(fmt(d.grand_total)) + '</td></tr></tfoot></table>';
      out.innerHTML = '<div class="muted small">' + A.esc(d.measure_label) + '</div>' + html;
    } catch (err) { out.innerHTML = '<div class="alert error">' + A.esc(err.message) + '</div>'; }
  }
  async function runStats() {
    var out = A.qs('#st-out');
    out.innerHTML = '<div class="loading">در حال محاسبه</div>';
    try {
      var res = await A.api.post(API + '/reports/' + R.report.id + '/analysis/stats', body());
      var cols = [['label', 'فیلد'], ['count', 'تعداد'], ['empty', 'خالی'], ['sum', 'جمع'], ['mean', 'میانگین'], ['median', 'میانه'],
        ['stddev', 'انحراف معیار'], ['min', 'کمینه'], ['p25', 'چارک اول'], ['p75', 'چارک سوم'], ['max', 'بیشینه'], ['range', 'دامنه']];
      var rows = res.data.filter(function (s) { return s.count; });
      out.innerHTML = rows.length ? '<table class="rv-grid"><thead><tr>' + cols.map(function (c) { return '<th>' + c[1] + '</th>'; }).join('')
        + '</tr></thead><tbody>' + rows.map(function (s) {
          return '<tr>' + cols.map(function (c) { return '<td>' + A.esc(c[0] === 'label' ? s.label : fmt(s[c[0]], { decimals: 2 })) + '</td>'; }).join('') + '</tr>';
        }).join('') + '</tbody></table>' : '<div class="muted">فیلد عددی با داده نیست.</div>';
    } catch (err) { out.innerHTML = '<div class="alert error">' + A.esc(err.message) + '</div>'; }
  }

  /* ═════════════ drill-down ═════════════ */
  var drillChart = null;
  async function runDrill() {
    var out = A.qs('#dr-out'), crumbs = A.qs('#dr-crumbs'), chartBox = A.qs('#dr-chart');
    out.innerHTML = '<div class="loading">در حال محاسبه</div>';
    crumbs.innerHTML = '';
    crumbs.appendChild(el('a', { href: '#', text: 'همه', onclick: function (e) { e.preventDefault(); R.drill = []; runDrill(); } }));
    R.drill.forEach(function (d, i) {
      crumbs.appendChild(document.createTextNode(' ← '));
      crumbs.appendChild(el('a', { href: '#', text: d.label, onclick: function (e) { e.preventDefault(); R.drill = R.drill.slice(0, i + 1); runDrill(); } }));
    });
    try {
      var res = await A.api.post(API + '/reports/' + R.report.id + '/run', body({ drill: { values: R.drill.map(function (d) { return d.key; }) } }));
      var lv = res.data.drill;
      if (drillChart) { try { drillChart.dispose(); } catch (e) { /* gone */ } drillChart = null; }
      out.innerHTML = '';
      if (!lv) { out.innerHTML = '<div class="muted">Drill-down برای این گزارش تعریف نشده است.</div>'; chartBox.classList.add('hidden'); return; }
      if (lv.detail) {
        chartBox.classList.add('hidden');
        out.appendChild(el('div', { class: 'muted small', text: 'ردیف‌های جزئی: ' + fmt(lv.row_count) + (lv.row_count > lv.rows.length ? ' (نمایش ' + fmt(lv.rows.length) + ' ردیف نخست)' : '') }));
        out.appendChild(RV.tableCard({ kind: 'detail', columns: lv.columns, rows: lv.rows, row_count: lv.row_count }, { title: 'رکوردها', page_size: 25 }, R.cfg.rules, {}));
        return;
      }
      out.appendChild(el('div', { class: 'section-title', text: 'سطح ' + (lv.level + 1).toLocaleString('fa-IR') + ': ' + lv.field_label + ' — روی هر ردیف بزنید تا یک سطح پایین‌تر بروید' }));
      out.appendChild(RV.tableCard(Object.assign({ kind: 'grouped' }, lv), { title: '', page_size: 30 }, R.cfg.rules, {
        onRowClick: function (def, t, row) { R.drill.push({ key: row._key[0], label: row.g0 }); runDrill(); } }));
      var mcol = lv.columns.filter(function (c) { return c.type === 'measure'; })[0];
      if (mcol && window.echarts && lv.rows.length) {
        chartBox.classList.remove('hidden');
        drillChart = window.echarts.init(chartBox);
        drillChart.setOption({ textStyle: { fontFamily: 'Vazirmatn' }, color: RV.PALETTE,
          grid: { left: 12, right: 12, top: 16, bottom: 8, containLabel: true }, tooltip: { trigger: 'axis' },
          xAxis: { type: 'category', data: lv.rows.map(function (r) { return r.g0; }), axisLabel: { rotate: lv.rows.length > 8 ? 35 : 0 } },
          yAxis: { type: 'value' }, series: [{ type: 'bar', name: mcol.label, data: lv.rows.map(function (r) { return r[mcol.key]; }) }] });
        drillChart.on('click', function (p) { var r = lv.rows[p.dataIndex]; R.drill.push({ key: r._key[0], label: r.g0 }); runDrill(); });
      } else chartBox.classList.add('hidden');
    } catch (err) { out.innerHTML = '<div class="alert error">' + A.esc(err.message) + '</div>'; }
  }

  /* ═════════════ raw ═════════════ */
  async function loadRaw() {
    var t = A.qs('#raw-table');
    t.innerHTML = '<tr><td class="loading">در حال بارگذاری</td></tr>';
    try {
      var res = await A.api.post(API + '/reports/' + R.report.id + '/raw', body({ page: R.raw.page, page_size: 100 }));
      var d = res.data;
      A.qs('#raw-count').textContent = fmt(d.row_count) + ' ردیف · ' + fmt(d.columns.length) + ' ستون';
      t.innerHTML = '<thead><tr>' + d.columns.map(function (c) { return '<th>' + A.esc(c.label) + '</th>'; }).join('') + '</tr></thead><tbody>'
        + d.rows.map(function (r) { return '<tr>' + d.columns.map(function (c) { return '<td>' + A.esc(fmt(r[c.key])) + '</td>'; }).join('') + '</tr>'; }).join('') + '</tbody>';
      pager(A.qs('#raw-pager'), d.page, Math.ceil(d.row_count / d.page_size), function (p) { R.raw.page = p; loadRaw(); });
    } catch (err) { t.innerHTML = '<tr><td class="alert error">' + A.esc(err.message) + '</td></tr>'; }
  }

  /* ═════════════ snapshots ═════════════ */
  async function loadSnapshots() {
    var box = A.qs('#snap-list');
    box.innerHTML = '<div class="loading">در حال بارگذاری</div>';
    try {
      var res = await A.api.get(API + '/reports/' + R.report.id + '/snapshots');
      box.innerHTML = '';
      if (!res.data.length) { box.appendChild(el('div', { class: 'muted', text: 'هنوز Snapshotی نیست. با دکمه‌ی «📸 Snapshot» نتیجه‌ی فعلی را نگه دارید.' })); return; }
      res.data.forEach(function (s) {
        var row = el('div', { class: 'rp-snap' });
        row.innerHTML = '<div><b>' + A.esc(s.title) + '</b><div class="muted small">' + (s.source === 'schedule' ? '⏰ زمان‌بندی‌شده · ' : '')
          + 'نسخه ' + A.esc(s.version || '—') + ' · ' + fmt(s.row_count) + ' ردیف · ' + A.esc(s.created_by || 'سیستم') + ' · '
          + A.esc((s.created_at || '').replace('T', ' ').slice(0, 16)) + ((s.filters && s.filters.texts && s.filters.texts.length) ? ' · فیلتر: ' + A.esc(s.filters.texts.join('، ')) : '') + '</div></div>';
        var acts = el('div', { class: 'toolbar-actions' });
        acts.appendChild(el('button', { type: 'button', class: 'btn-primary btn-sm', text: 'نمایش', onclick: function () { openSnapshot(s.id); } }));
        FORMATS.forEach(function (f) {
          if (!has(f[2]) || f[0] === 'json') return;
          acts.appendChild(el('button', { type: 'button', class: 'btn-ghost btn-sm', text: f[1], onclick: function () { exportSnapshot(s.id, f[0]); } }));
        });
        acts.appendChild(el('button', { type: 'button', class: 'btn-ghost btn-sm rb-x', text: '✕', title: 'حذف', onclick: async function () {
          if (!(await A.confirmDialog({ message: 'Snapshot «' + s.title + '» حذف شود؟' }))) return;
          try { await A.api.del(API + '/snapshots/' + s.id); loadSnapshots(); } catch (err) { A.toast(err.message, 'error'); }
        } }));
        row.appendChild(acts);
        box.appendChild(row);
      });
    } catch (err) { box.innerHTML = '<div class="alert error">' + A.esc(err.message) + '</div>'; }
  }
  async function openSnapshot(id) {
    try {
      var res = await A.api.get(API + '/snapshots/' + id);
      R.snapshot = res.data;
      R.tab = 'dashboard';
      A.qsa('#rp-tabs .tab').forEach(function (t) { t.classList.toggle('active', t.dataset.tab === 'dashboard'); });
      A.qsa('.rp-panel').forEach(function (p) { p.classList.toggle('hidden', p.dataset.panel !== 'dashboard'); });
      drawSnapshot();
    } catch (err) { A.toast(err.message, 'error'); }
  }
  function drawSnapshot() {
    var s = R.snapshot, box = A.qs('#rp-dashboard');
    var cfg = s.config || R.cfg;
    A.qs('#rp-meta').innerHTML = '';
    var bar = el('div', { class: 'alert info rp-snapbar' });
    bar.innerHTML = '📸 در حال مشاهده‌ی Snapshot «<b>' + A.esc(s.title) + '</b>» — نسخه ' + A.esc(s.version || '—') + ' · ' + A.esc((s.created_at || '').replace('T', ' ').slice(0, 16)) + ' ';
    bar.appendChild(el('button', { type: 'button', class: 'btn-sm btn-ghost', text: '↩ بازگشت به داده‌ی زنده', onclick: function () { R.snapshot = null; runDashboard(); } }));
    A.qs('#rp-meta').appendChild(bar);
    RV.render(box, cfg, s.result, {});
  }
  async function exportSnapshot(id, fmtKey) {
    var images = {};
    if (R.snapshot && R.snapshot.id === id) images = RV.chartImages();
    await download(API + '/snapshots/' + id + '/export/' + fmtKey, { chart_images: images }, fmtKey);
  }

  /* ═════════════ exports ═════════════ */
  var pendingFmt = null;
  function openExport(fmtKey, label) {
    pendingFmt = fmtKey;
    A.qs('#rp-export-title').textContent = 'خروجی ' + label;
    var box = A.qs('#rp-export-opts');
    box.innerHTML = '';
    var rows = [];
    if (R.snapshot) rows.push('<div class="alert info">از Snapshot «' + A.esc(R.snapshot.title) + '» خروجی گرفته می‌شود.</div>');
    else {
      var f = Object.keys(cleanValues()).length;
      rows.push('<p class="muted small">خروجی دقیقاً همان چیزی است که با فیلترهای فعلی' + (f ? ' (' + f + ' فیلتر)' : '') + ' می‌بینید؛ نمودارها به‌صورت تصویر همراه می‌شوند.</p>');
      if (has('raw_data') && ['xlsx', 'csv', 'json'].indexOf(fmtKey) >= 0) rows.push('<label class="mini-check"><input type="checkbox" id="ex-raw"> داده‌ی خام (همه‌ی ردیف‌ها و فیلدها) هم باشد</label>');
      if (has('view_analysis') && ['xlsx', 'pdf', 'docx'].indexOf(fmtKey) >= 0) rows.push('<label class="mini-check"><input type="checkbox" id="ex-an" checked> آمار توصیفی هم باشد</label>');
      if (fmtKey !== 'print') rows.push('<label class="mini-check"><input type="checkbox" id="ex-async"> در پس‌زمینه بساز (برای گزارش‌های سنگین)</label>');
    }
    box.innerHTML = rows.join('');
    A.openModal('rp-export-modal');
  }
  async function doExport() {
    A.closeModal('rp-export-modal');
    var fmtKey = pendingFmt;
    if (R.snapshot) { await exportSnapshot(R.snapshot.id, fmtKey); return; }
    var images = (R.tab === 'dashboard') ? RV.chartImages() : {};
    if (!Object.keys(images).length && (R.cfg.charts || []).length && ['pdf', 'docx', 'print', 'html'].indexOf(fmtKey) >= 0) {
      // make sure the charts exist as pictures: render the dashboard first
      switchTab('dashboard');
      await new Promise(function (r) { setTimeout(r, 1500); });
      images = RV.chartImages();
    }
    var payload = body({
      chart_images: images,
      include_raw: !!(A.qs('#ex-raw') && A.qs('#ex-raw').checked),
      include_analysis: !!(A.qs('#ex-an') && A.qs('#ex-an').checked),
      async: !!(A.qs('#ex-async') && A.qs('#ex-async').checked) || undefined
    });
    await download(API + '/reports/' + R.report.id + '/export/' + fmtKey, payload, fmtKey);
  }
  async function download(url, payload, fmtKey) {
    A.toast('در حال ساخت خروجی…', 'info');
    try {
      var resp = await fetch(url, { method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': A.csrfToken(), 'X-Requested-With': 'fetch' },
        body: JSON.stringify(payload) });
      var type = resp.headers.get('Content-Type') || '';
      if (type.indexOf('application/json') >= 0 && !(resp.headers.get('Content-Disposition') || '')) {
        var j = await resp.json();
        if (!resp.ok || j.ok === false) throw { message: j.error || 'خطا در ساخت خروجی' };
        if (j.data && j.data.async) { A.toast('خروجی در پس‌زمینه ساخته می‌شود؛ آماده که شد در پایین فهرست گزارش‌ها لینک دانلود می‌آید.', 'success'); pollJobs(); return; }
      }
      if (!resp.ok) throw { message: 'خطای سرور (' + resp.status + ')' };
      var blob = await resp.blob();
      var href = URL.createObjectURL(blob);
      if (fmtKey === 'print') {
        window.open(href, '_blank');
      } else {
        var cd = resp.headers.get('Content-Disposition') || '';
        var m = /filename\*=UTF-8''([^;]+)/i.exec(cd) || /filename="?([^";]+)"?/i.exec(cd);
        var a = document.createElement('a');
        a.href = href; a.download = m ? decodeURIComponent(m[1]) : ('report.' + fmtKey);
        document.body.appendChild(a); a.click(); a.remove();
      }
      setTimeout(function () { URL.revokeObjectURL(href); }, 60000);
      A.toast('خروجی آماده شد.', 'success');
    } catch (err) { A.toast(err.message || 'خطا در ساخت خروجی', 'error'); }
  }
  var jobTimer = null;
  async function pollJobs() {
    clearTimeout(jobTimer);
    try {
      var res = await A.api.get(API + '/jobs');
      var box = A.qs('#rp-jobs');
      var recent = res.data.slice(0, 6);
      box.innerHTML = recent.length ? '<div class="pal-group-title">خروجی‌های پس‌زمینه</div>' : '';
      var running = false;
      recent.forEach(function (j) {
        var name = (R.catalog.filter(function (r) { return r.id === j.report_id; })[0] || {}).name || ('گزارش ' + j.report_id);
        var row = el('div', { class: 'rp-job' });
        if (j.status === 'done') row.appendChild(el('a', { href: API + '/jobs/' + j.id + '/download', text: '⬇ ' + name + ' (' + j.fmt.toUpperCase() + ')' }));
        else row.appendChild(el('span', { text: (j.status === 'failed' ? '✕ ' : '⏳ ') + name + ' (' + j.fmt.toUpperCase() + ')' + (j.status === 'failed' ? ' — ' + (j.message || '') : '') }));
        box.appendChild(row);
        if (j.status === 'queued' || j.status === 'running') running = true;
      });
      if (running) jobTimer = setTimeout(pollJobs, 2500);
    } catch (e) { /* quiet */ }
  }

  /* ═════════════ info ═════════════ */
  async function showInfo() {
    var box = A.qs('#rp-info');
    box.innerHTML = '<div class="loading">در حال بارگذاری</div>';
    A.openModal('rp-info-modal');
    try {
      var res = await A.api.get(API + '/reports/' + R.report.id + '/info' + (R.draft ? '?draft=1' : ''));
      var d = res.data, h = '<dl class="kv">';
      h += '<dt>گزارش</dt><dd>' + A.esc(d.report) + ' — نسخه ' + A.esc(d.version) + (d.published_at ? ' (انتشار: ' + A.esc(d.published_at) + ')' : '') + '</dd>';
      h += '<dt>منبع داده</dt><dd>' + A.esc(d.source) + '<div class="muted small">' + A.esc(d.source_description || '') + '</div></dd>';
      h += '<dt>فیلترهای ثابت</dt><dd>' + (d.filters.length ? d.filters.map(A.esc).join('<br>') : 'ندارد — همه‌ی داده‌ها') + '</dd>';
      var cur = Object.keys(cleanValues());
      if (cur.length) h += '<dt>فیلترهای شما</dt><dd>' + cur.map(function (k) { var v = cleanValues()[k]; return A.esc(((R.cfg.interactive_filters || []).filter(function (f) { return (f.id || f.field) === k; })[0] || {}).label || k) + ': ' + A.esc(typeof v === 'object' ? JSON.stringify(v) : v); }).join('<br>') + '</dd>';
      h += '<dt>گروه‌بندی</dt><dd>' + (d.groups.length ? d.groups.map(A.esc).join(' ← ') : '—') + '</dd>';
      h += '<dt>سنجه‌ها</dt><dd>' + (d.measures.length ? d.measures.map(function (m) { return '<b>' + A.esc(m.label) + '</b>: ' + A.esc(m.definition); }).join('<br>') : '—') + '</dd>';
      h += '<dt>فرمول‌ها</dt><dd>' + (d.calcs.length ? d.calcs.map(function (c) { return '<b>' + A.esc(c.label) + '</b> = <code dir="ltr">' + A.esc(c.formula) + '</code>'; }).join('<br>') : '—') + '</dd>';
      if (d.scope_to_centers) h += '<dt>محدوده</dt><dd>فقط داده‌ی مراکز شما</dd>';
      h += '</dl>';
      box.innerHTML = h;
    } catch (err) { box.innerHTML = '<div class="alert error">' + A.esc(err.message) + '</div>'; }
  }

  /* ═════════════ boot ═════════════ */
  document.addEventListener('DOMContentLoaded', function () {
    A.qsa('#rp-main-tabs .tab').forEach(function (t) {
      t.addEventListener('click', function () {
        A.qsa('#rp-main-tabs .tab').forEach(function (x) { x.classList.toggle('active', x === t); });
        A.qs('#rp-dynamic').classList.toggle('hidden', t.dataset.main !== 'dynamic');
        A.qs('#rp-legacy').classList.toggle('hidden', t.dataset.main !== 'legacy');
        if (t.dataset.main === 'dynamic') RV.resize();
      });
    });
    A.qsa('#rp-tabs .tab').forEach(function (t) { t.addEventListener('click', function () { switchTab(t.dataset.tab); }); });
    A.qs('#rp-search').addEventListener('input', A.debounce(drawCatalog, 150));
    A.qs('#rp-category').addEventListener('change', drawCatalog);
    A.qs('#rp-fav-only').addEventListener('change', drawCatalog);
    A.qs('#rp-apply').addEventListener('click', apply);
    A.qs('#rp-reset').addEventListener('click', function () { R.values = {}; drawFilters(); apply(); });
    A.qs('#rp-info-btn').addEventListener('click', showInfo);
    A.qs('#rp-export-go').addEventListener('click', doExport);
    A.qs('#an-search').addEventListener('input', A.debounce(function () { R.an.search = A.qs('#an-search').value.trim(); R.an.page = 1; loadDetail(); }, 350));
    A.qs('#xt-run').addEventListener('click', runCrosstab);
    A.qs('#st-run').addEventListener('click', runStats);
    A.qs('#rp-fav').addEventListener('click', async function () {
      try {
        var res = await A.api.post(API + '/reports/' + R.report.id + '/favorite');
        R.catalog.forEach(function (r) { if (r.id === R.report.id) r.favorite = res.data.favorite; });
        A.qs('#rp-fav').textContent = res.data.favorite ? '★' : '☆';
        drawCatalog();
      } catch (err) { A.toast(err.message, 'error'); }
    });
    A.qs('#rp-snap-btn').addEventListener('click', async function () {
      var title = window.prompt('عنوان Snapshot (مثلاً: گزارش عملکرد مهر ۱۴۰۵):', R.report.name);
      if (title === null) return;
      try {
        await A.api.post(API + '/reports/' + R.report.id + '/snapshots', body({ title: title }));
        A.toast('Snapshot ذخیره شد.', 'success');
        if (R.tab === 'snapshots') loadSnapshots();
      } catch (err) { A.toast(err.message, 'error'); }
    });
    loadCatalog().then(function () {
      var q = new URLSearchParams(location.search);
      if (q.get('report')) openReport(Number(q.get('report')), q.get('draft') === '1');
    });
    pollJobs();
  });
})();
