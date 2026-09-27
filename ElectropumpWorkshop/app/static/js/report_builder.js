/* ==========================================================================
   گزارش‌ساز — the report builder workspace (system admin only).

   A report is a definition, edited here step by step and previewed live on
   the right from the unsaved definition. Saving writes the working version;
   a published report keeps showing its published version to users until the
   admin publishes again. Nothing in this file knows any particular form,
   process or field: every list comes from /api/analytics/meta and the fields
   of the chosen source.
   ========================================================================== */
(function () {
  'use strict';
  var A = window.App, RV = window.ReportView, J = window.Jalali;
  var API = '/api/analytics';

  var S = {
    meta: null, reports: [], report: null, def: null,
    fields: [], fmap: {}, dirty: false, step: 'basics',
    principals: null, validation: null, previewSeq: 0
  };
  var STEPS = [
    ['basics', 'مشخصات گزارش'], ['source', 'منبع داده'], ['fields', 'فیلدها'],
    ['filters', 'فیلترها'], ['calcs', 'محاسبات و فرمول'], ['groups', 'گروه‌بندی و سنجه‌ها'],
    ['kpis', 'شاخص‌ها (KPI)'], ['charts', 'نمودارها'], ['tables', 'جداول'],
    ['rules', 'قالب‌بندی شرطی'], ['layout', 'چیدمان و تعامل'], ['access', 'دسترسی'],
    ['publish', 'بررسی، نسخه و انتشار']
  ];
  var FA_NUM = ['۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹', '۱۰', '۱۱', '۱۲', '۱۳'];
  var NUMERIC = ['integer', 'decimal', 'percent', 'calc'];
  var TEMPORAL = ['date', 'datetime'];

  /* ── small DOM helpers ── */
  function el(tag, attrs, kids) { return A.el(tag, attrs, kids); }
  function uid(p) { return p + Math.random().toString(36).slice(2, 7); }
  function txt(s) { return document.createTextNode(s); }

  function fld(label, control, hint, cls) {
    var box = el('div', { class: 'field' + (cls ? ' ' + cls : '') });
    if (label) box.appendChild(el('label', { text: label }));
    box.appendChild(control);
    if (hint) box.appendChild(el('div', { class: 'hint', text: hint }));
    return box;
  }
  function input(value, onchange, attrs) {
    var i = el('input', Object.assign({ type: 'text' }, attrs || {}));
    i.value = value === undefined || value === null ? '' : value;
    i.addEventListener('input', function () { onchange(i.type === 'number' ? (i.value === '' ? null : Number(i.value)) : i.value); });
    return i;
  }
  function textarea(value, onchange, attrs) {
    var t = el('textarea', Object.assign({ rows: 3 }, attrs || {}));
    t.value = value || '';
    t.addEventListener('input', function () { onchange(t.value); });
    return t;
  }
  function check(label, value, onchange) {
    var c = el('input', { type: 'checkbox' });
    c.checked = !!value;
    c.addEventListener('change', function () { onchange(c.checked); });
    return el('label', { class: 'mini-check' }, [c, txt(' ' + label)]);
  }
  function select(options, value, onchange, attrs) {
    var s = el('select', attrs || {});
    options.forEach(function (o) {
      if (o.group) {
        var g = el('optgroup', { label: o.group });
        o.items.forEach(function (x) { g.appendChild(el('option', { value: x[0], text: x[1] })); });
        s.appendChild(g);
      } else {
        s.appendChild(el('option', { value: o[0], text: o[1] }));
      }
    });
    s.value = value === undefined || value === null ? '' : value;
    s.addEventListener('change', function () { onchange.call(s, s.value); });
    return s;
  }
  function btn(text, onclick, cls, title) {
    return el('button', { type: 'button', class: cls || 'btn-ghost btn-sm', text: text,
      title: title || null, onclick: onclick });
  }
  function section(title, hint) {
    var box = el('div', { class: 'rb-section' });
    box.appendChild(el('div', { class: 'section-title', text: title }));
    if (hint) box.appendChild(el('div', { class: 'hint rb-hint', text: hint }));
    return box;
  }
  function itemCard(title, onRemove, onUp, onDown) {
    var card = el('div', { class: 'rb-item' });
    var head = el('div', { class: 'rb-item-head' }, [el('b', { text: title })]);
    var tools = el('span', { class: 'rb-item-tools' });
    if (onUp) tools.appendChild(btn('▲', onUp, 'btn-ghost btn-xs', 'بالا'));
    if (onDown) tools.appendChild(btn('▼', onDown, 'btn-ghost btn-xs', 'پایین'));
    if (onRemove) tools.appendChild(btn('✕', onRemove, 'btn-ghost btn-xs rb-x', 'حذف'));
    head.appendChild(tools);
    card.appendChild(head);
    var body = el('div', { class: 'rb-item-body' });
    card.appendChild(body);
    card.body = body;
    return card;
  }
  function move(list, i, d) {
    var j = i + d;
    if (j < 0 || j >= list.length) return;
    var t = list[i]; list[i] = list[j]; list[j] = t;
    changed(true);
  }

  /* ── fields ── */
  function calcFields() {
    return (S.def.calcs || []).filter(function (c) { return c.key; }).map(function (c) {
      return { key: c.key, label: c.label || c.key, type: c.result_type || 'decimal',
        group: 'محاسباتی', calc: true };
    });
  }
  function allFields() { return S.fields.concat(calcFields()); }
  function fieldOf(key) {
    if (S.fmap[key]) return S.fmap[key];
    return calcFields().filter(function (c) { return c.key === key; })[0] || null;
  }
  function labelOf(key) {
    if (key === '*') return 'ردیف‌ها';
    var f = fieldOf(key);
    return f ? f.label : key;
  }
  function isNum(f) { return f && NUMERIC.indexOf(f.type) >= 0; }
  function isDate(f) { return f && TEMPORAL.indexOf(f.type) >= 0; }

  function fieldOptions(pred, emptyLabel, includeStar) {
    var groups = {}, order = [];
    allFields().forEach(function (f) {
      if (f.key.indexOf('_center') === 0) return;
      if (pred && !pred(f)) return;
      var g = f.group || 'سایر';
      if (!groups[g]) { groups[g] = []; order.push(g); }
      groups[g].push([f.key, f.label]);
    });
    var out = [];
    if (emptyLabel !== false) out.push(['', emptyLabel || '— انتخاب فیلد —']);
    if (includeStar) out.push(['*', '(همه‌ی ردیف‌ها)']);
    order.forEach(function (g) { out.push({ group: g, items: groups[g] }); });
    return out;
  }
  function fieldSelect(value, onchange, pred, emptyLabel, includeStar) {
    return select(fieldOptions(pred, emptyLabel, includeStar), value, onchange);
  }
  function granSelect(value, onchange) {
    return select([['', '— بدون تفکیک —']].concat(S.meta.granularity.map(function (g) {
      return [g.key, g.label]; })), value, onchange);
  }
  function aggOptions(f) {
    return S.meta.aggregations.filter(function (a) {
      if (!f || f.key === '*') return ['count'].indexOf(a.key) >= 0;
      if (a.numeric) return isNum(f);
      if (a.key === 'count_true' || a.key === 'pct_true') return f.type === 'boolean';
      return true;
    }).map(function (a) { return [a.key, a.label]; });
  }

  /* ── state changes ── */
  var previewSoon = A.debounce(function () { if (A.qs('#rb-auto').checked) preview(); }, 700);
  function changed(rerender) {
    S.dirty = true;
    A.qs('#rb-dirty').textContent = '● تغییرات ذخیره نشده';
    A.qs('#rb-dirty').className = 'save-state dirty';
    if (rerender) renderStep();
    previewSoon();
  }
  function setClean() {
    S.dirty = false;
    A.qs('#rb-dirty').textContent = '✓ ذخیره شده';
    A.qs('#rb-dirty').className = 'save-state ok';
  }
  window.addEventListener('beforeunload', function (e) {
    if (S.dirty) { e.preventDefault(); e.returnValue = ''; }
  });

  /* ═════════════════════════ report list ═════════════════════════ */
  async function loadReports() {
    var res = await A.api.get(API + '/reports');
    S.reports = res.data;
    drawList();
  }
  function drawList() {
    var q = A.qs('#rb-search').value.trim(), st = A.qs('#rb-status-filter').value;
    var box = A.qs('#rb-reports');
    box.innerHTML = '';
    var list = S.reports.filter(function (r) {
      return (!q || r.name.indexOf(q) >= 0 || (r.category || '').indexOf(q) >= 0)
        && (!st || r.status === st);
    });
    if (!list.length) { box.appendChild(el('div', { class: 'muted small', text: 'گزارشی نیست.' })); return; }
    list.forEach(function (r) {
      var item = el('div', { class: 'rb-report' + (S.report && S.report.id === r.id ? ' active' : '') });
      item.innerHTML = '<b>' + A.esc(r.name) + '</b><div class="small">'
        + '<span class="badge ' + statusClass(r.status) + '">' + A.esc(r.status_label) + '</span> '
        + (r.category ? '<span class="muted">' + A.esc(r.category) + '</span> ' : '')
        + '<span class="muted">نسخه ' + A.esc(r.latest_version || '—')
        + (r.published_version ? ' · منتشر: ' + A.esc(r.published_version) : '') + '</span></div>';
      item.addEventListener('click', function () { openReport(r.id); });
      box.appendChild(item);
    });
  }
  function statusClass(s) {
    return { draft: 'muted', testing: 'warn', published: 'ok', archived: 'danger' }[s] || '';
  }

  async function openReport(id) {
    if (S.dirty && S.report && S.report.id !== id) {
      var go = await A.confirmDialog({ title: 'تغییرات ذخیره نشده', message: 'تغییرات گزارش فعلی ذخیره نشده است. بدون ذخیره ادامه می‌دهید؟', confirmText: 'بدون ذخیره' });
      if (!go) return;
    }
    try {
      var res = await A.api.get(API + '/reports/' + id);
      await setReport(res.data);
      try { history.replaceState(null, '', '/report-builder?id=' + id); } catch (e) { /* ok */ }
    } catch (err) { A.toast(err.message, 'error'); }
  }

  async function setReport(data) {
    S.report = data;
    S.def = data.definition;
    S.validation = null;
    await loadFields(S.def.source);
    A.qs('#rb-empty').classList.add('hidden');
    A.qs('#rb-editor').classList.remove('hidden');
    A.qs('#rb-preview-pane').classList.remove('hidden');
    drawHeader();
    setClean();
    drawSteps();
    renderStep();
    drawList();
    preview();
  }

  function drawHeader() {
    var r = S.report;
    A.qs('#rb-name-view').textContent = r.name;
    var st = A.qs('#rb-status');
    st.textContent = r.status_label;
    st.className = 'badge ' + statusClass(r.status);
    A.qs('#rb-version').textContent = 'نسخه‌ی کاری ' + (r.latest_version || '—')
      + (r.published_version ? ' · نسخه‌ی منتشرشده ' + r.published_version : ' · منتشر نشده')
      + (r.version_frozen ? ' · (ویرایش، نسخه‌ی تازه می‌سازد)' : '');
  }

  async function loadFields(source) {
    S.fields = []; S.fmap = {};
    if (!source) return;
    var res = await A.api.get(API + '/sources/' + encodeURIComponent(source) + '/fields');
    S.fields = res.data.fields;
    S.fields.forEach(function (f) { S.fmap[f.key] = f; });
  }

  /* ═════════════════════════ steps ═════════════════════════ */
  function stepState(key) {
    var d = S.def;
    return {
      basics: !!S.report.name, source: !!d.source, fields: (d.fields || []).length > 0,
      filters: (d.filters.items || []).length > 0 || (d.interactive_filters || []).length > 0,
      calcs: (d.calcs || []).length > 0, groups: (d.measures || []).length > 0,
      kpis: (d.kpis || []).length > 0, charts: (d.charts || []).length > 0,
      tables: (d.tables || []).length > 0, rules: (d.rules || []).length > 0,
      layout: (d.layout || []).length > 0, access: (S.report.permissions || []).length > 0,
      publish: S.report.status === 'published'
    }[key];
  }
  function drawSteps() {
    var nav = A.qs('#rb-steps');
    nav.innerHTML = '';
    STEPS.forEach(function (s, i) {
      var b = el('button', { type: 'button', class: 'rb-step' + (S.step === s[0] ? ' active' : '')
        + (stepState(s[0]) ? ' done' : '') });
      b.innerHTML = '<span class="rb-step-no">' + FA_NUM[i] + '</span><span>' + A.esc(s[1]) + '</span>';
      b.addEventListener('click', function () { S.step = s[0]; drawSteps(); renderStep(); });
      nav.appendChild(b);
    });
  }
  function renderStep() {
    var panel = A.qs('#rb-panel');
    var scroll = panel.scrollTop;
    panel.innerHTML = '';
    var idx = STEPS.map(function (s) { return s[0]; }).indexOf(S.step);
    panel.appendChild(el('h3', { class: 'rb-panel-title', text: FA_NUM[idx] + '. ' + STEPS[idx][1] }));
    try {
      ({ basics: stepBasics, source: stepSource, fields: stepFields, filters: stepFilters,
        calcs: stepCalcs, groups: stepGroups, kpis: stepKpis, charts: stepCharts,
        tables: stepTables, rules: stepRules, layout: stepLayout, access: stepAccess,
        publish: stepPublish })[S.step](panel);
    } catch (err) {
      panel.appendChild(el('div', { class: 'alert error', text: 'خطا در نمایش این مرحله: ' + err.message }));
      console.error(err);
    }
    var nav = el('div', { class: 'rb-stepnav' });
    if (idx > 0) nav.appendChild(btn('→ مرحله‌ی قبل', function () { S.step = STEPS[idx - 1][0]; drawSteps(); renderStep(); }));
    nav.appendChild(el('span', { class: 'spacer' }));
    if (idx < STEPS.length - 1) nav.appendChild(btn('مرحله‌ی بعد ←', function () { S.step = STEPS[idx + 1][0]; drawSteps(); renderStep(); }, 'btn-primary btn-sm'));
    panel.appendChild(nav);
    panel.scrollTop = scroll;
    drawSteps();
  }

  /* 1 ─ basics */
  function stepBasics(p) {
    var r = S.report;
    var cats = [['', '— بدون دسته —']].concat(S.meta.categories.map(function (c) { return [String(c.id), c.name]; }));
    p.appendChild(fld('نام گزارش', input(r.name, function (v) { r.name = v; A.qs('#rb-name-view').textContent = v; changed(); }, { maxlength: 200 })));
    p.appendChild(fld('شرح', textarea(r.description, function (v) { r.description = v; changed(); }),
      'برای کاربران در فهرست گزارش‌ها نمایش داده می‌شود.'));
    p.appendChild(fld('دسته', select(cats, r.category_id ? String(r.category_id) : '', function (v) { r.category_id = v ? Number(v) : null; changed(); })));
    p.appendChild(check('هر کاربر فقط داده‌ی مراکز (واحدهای) خودش را ببیند', r.scope_to_centers,
      function (v) { r.scope_to_centers = v; changed(); }));
    p.appendChild(el('div', { class: 'hint', text: 'این گزینه ردیف‌های خارج از مراکز کاربر را اصلاً نمی‌خواند؛ مدیر سیستم همیشه همه را می‌بیند.' }));
    var exp = S.def.export = S.def.export || {};
    var box = section('تنظیمات خروجی');
    box.appendChild(fld('جهت صفحه در PDF و Word', select([['landscape', 'افقی (Landscape)'], ['portrait', 'عمودی (Portrait)']],
      exp.orientation || 'landscape', function (v) { exp.orientation = v; changed(); })));
    box.appendChild(check('لوگو در سربرگ خروجی‌ها', exp.logo !== false, function (v) { exp.logo = v; changed(); }));
    p.appendChild(box);
  }

  /* 2 ─ source */
  function stepSource(p) {
    p.appendChild(el('div', { class: 'hint rb-hint', text: 'منبع، «هر ردیف گزارش چیست» را تعیین می‌کند. فیلدهای هر منبع از فرم‌ساز و فرایندساز خوانده می‌شوند؛ فیلدی که امروز اضافه شود، همین حالا اینجاست.' }));
    var grid = el('div', { class: 'rb-sources' });
    S.meta.sources.forEach(function (s) {
      var card = el('div', { class: 'rb-source' + (S.def.source === s.key ? ' active' : '') });
      card.innerHTML = '<b>' + A.esc(s.label) + '</b><p>' + A.esc(s.description) + '</p>'
        + '<span class="muted small">هر ردیف: ' + A.esc(s.row_label) + '</span>';
      card.addEventListener('click', async function () {
        if (S.def.source === s.key) return;
        if (S.def.source && ((S.def.fields || []).length || (S.def.measures || []).length || (S.def.charts || []).length)) {
          var ok = await A.confirmDialog({ title: 'تغییر منبع داده', message: 'با تغییر منبع، فیلدها، فیلترها، سنجه‌ها، نمودارها و جداول این گزارش پاک می‌شوند. ادامه می‌دهید؟', confirmText: 'تغییر منبع' });
          if (!ok) return;
          ['fields', 'calcs', 'groups', 'measures', 'sort', 'kpis', 'charts', 'tables', 'rules', 'layout', 'interactive_filters'].forEach(function (k) { S.def[k] = []; });
          S.def.filters = { op: 'and', items: [] };
          S.def.drill = { enabled: false, path: [] };
        }
        S.def.source = s.key;
        await loadFields(s.key);
        changed(true);
      });
      grid.appendChild(card);
    });
    p.appendChild(grid);
    if (S.def.source) {
      var byGroup = {};
      S.fields.forEach(function (f) { (byGroup[f.group] = byGroup[f.group] || []).push(f); });
      var box = section('فیلدهای این منبع (' + S.fields.length.toLocaleString('fa-IR') + ')');
      Object.keys(byGroup).forEach(function (g) {
        box.appendChild(el('div', { class: 'pal-group-title', text: g + ' (' + byGroup[g].length.toLocaleString('fa-IR') + ')' }));
        box.appendChild(el('div', { class: 'rb-chips' }, byGroup[g].map(function (f) {
          return el('span', { class: 'rb-chip', title: f.type_label || f.type, text: f.label });
        })));
      });
      p.appendChild(box);
    }
  }

  /* 3 ─ fields */
  function stepFields(p) {
    var chosen = S.def.fields;
    p.appendChild(el('div', { class: 'hint rb-hint', text: 'فیلدهایی که در جدول جزئیات، مرحله‌ی آخر Drill-down و تحلیل تخصصی نشان داده می‌شوند. برچسب، قالب و تعداد اعشار هر ستون را می‌توانید عوض کنید.' }));
    var wrap = el('div', { class: 'rb-two' });
    var left = el('div', { class: 'rb-pick' });
    var search = el('input', { type: 'search', placeholder: 'جستجوی فیلد…' });
    left.appendChild(search);
    var list = el('div', { class: 'rb-pick-list' });
    left.appendChild(list);
    function drawAvail() {
      var q = search.value.trim();
      list.innerHTML = '';
      var have = {};
      chosen.forEach(function (c) { have[c.key] = true; });
      var groups = {};
      allFields().forEach(function (f) {
        if (f.key.indexOf('_center') === 0) return;
        if (q && f.label.indexOf(q) < 0) return;
        (groups[f.group] = groups[f.group] || []).push(f);
      });
      Object.keys(groups).forEach(function (g) {
        list.appendChild(el('div', { class: 'pal-group-title', text: g }));
        groups[g].forEach(function (f) {
          var c = el('input', { type: 'checkbox' });
          c.checked = !!have[f.key];
          c.addEventListener('change', function () {
            if (c.checked) chosen.push({ key: f.key });
            else S.def.fields = chosen = chosen.filter(function (x) { return x.key !== f.key; });
            changed(); drawChosen();
          });
          list.appendChild(el('label', { class: 'rb-pick-item' }, [c, txt(' ' + f.label),
            el('span', { class: 'muted small', text: ' · ' + (f.type_label || f.type) })]));
        });
      });
    }
    search.addEventListener('input', A.debounce(drawAvail, 150));
    var right = el('div', { class: 'rb-chosen' });
    function drawChosen() {
      right.innerHTML = '<div class="pal-group-title">فیلدهای انتخاب‌شده (' + chosen.length.toLocaleString('fa-IR') + ')</div>';
      if (!chosen.length) right.appendChild(el('div', { class: 'muted small', text: 'هنوز فیلدی انتخاب نشده.' }));
      chosen.forEach(function (c, i) {
        var f = fieldOf(c.key) || {};
        var row = el('div', { class: 'rb-chosen-row' });
        row.appendChild(el('span', { class: 'rb-handle', text: (i + 1).toLocaleString('fa-IR') }));
        row.appendChild(input(c.label || '', function (v) { c.label = v || undefined; changed(); }, { placeholder: f.label || c.key }));
        if (isNum(f)) {
          row.appendChild(select([['', 'عدد'], ['percent', 'درصد']], c.format || '', function (v) { c.format = v || undefined; changed(); }));
          row.appendChild(input(c.decimals, function (v) { c.decimals = v; changed(); }, { type: 'number', min: 0, max: 6, placeholder: 'اعشار', class: 'rb-narrow' }));
        }
        row.appendChild(btn('▲', function () { move(chosen, i, -1); drawChosen(); }, 'btn-ghost btn-xs'));
        row.appendChild(btn('▼', function () { move(chosen, i, 1); drawChosen(); }, 'btn-ghost btn-xs'));
        row.appendChild(btn('✕', function () { chosen.splice(i, 1); changed(); drawChosen(); drawAvail(); }, 'btn-ghost btn-xs rb-x'));
        right.appendChild(row);
      });
    }
    wrap.appendChild(left); wrap.appendChild(right);
    p.appendChild(wrap);
    drawAvail(); drawChosen();
  }

  /* 4 ─ filters */
  function valueControl(cond, onchange) {
    var f = fieldOf(cond.field) || {};
    var op = cond.operator || 'eq';
    var box = el('span', { class: 'rb-val' });
    if (op === 'empty' || op === 'not_empty') return box;
    if (op === 'relative') {
      box.appendChild(select(S.meta.relative.map(function (r) { return [r.key, r.label]; }), cond.value || 'this_month',
        function (v) { cond.value = v; onchange(); }));
      if (!cond.value) cond.value = 'this_month';
      return box;
    }
    function one(val, set, ph) {
      if (f.options && ['eq', 'ne', 'in'].indexOf(op) >= 0) {
        if (op === 'in') {
          var s = el('select', { multiple: 'multiple', size: Math.min(6, f.options.length) });
          var cur = Array.isArray(val) ? val : (val ? [val] : []);
          f.options.forEach(function (o) {
            var opt = el('option', { value: o, text: o });
            if (cur.indexOf(o) >= 0) opt.selected = true;
            s.appendChild(opt);
          });
          s.addEventListener('change', function () {
            set(Array.prototype.slice.call(s.selectedOptions).map(function (o) { return o.value; }));
          });
          return s;
        }
        return select([['', '—']].concat(f.options.map(function (o) { return [o, o]; })), val, set);
      }
      var i = input(val, set, { placeholder: ph || 'مقدار', type: isNum(f) ? 'number' : 'text' });
      if (isDate(f) || op === 'date_on' || op === 'date_between') {
        i.placeholder = '۱۴۰۴/۰۱/۰۱';
        if (J && J.attach) setTimeout(function () { if (i.isConnected) J.attach(i); }, 0);
        i.addEventListener('change', function () { set(i.value); });
      }
      return i;
    }
    box.appendChild(one(cond.value, function (v) { cond.value = v; onchange(); }));
    if (op === 'between' || op === 'date_between') {
      box.appendChild(txt(' تا '));
      box.appendChild(one(cond.value2, function (v) { cond.value2 = v; onchange(); }, 'تا'));
    }
    return box;
  }
  function operatorsFor(f) {
    var ops = S.meta.operators;
    if (!f) return ops;
    var allow;
    if (isDate(f)) allow = ['eq', 'ne', 'gt', 'gte', 'lt', 'lte', 'date_between', 'relative', 'empty', 'not_empty'];
    else if (isNum(f)) allow = ['eq', 'ne', 'gt', 'gte', 'lt', 'lte', 'between', 'in', 'empty', 'not_empty'];
    else if (f.type === 'boolean') allow = ['eq', 'ne', 'empty', 'not_empty'];
    else allow = ['eq', 'ne', 'in', 'contains', 'not_contains', 'starts', 'ends', 'empty', 'not_empty'];
    return ops.filter(function (o) { return allow.indexOf(o.key) >= 0; });
  }
  function filterTree(node, onRemove, depth) {
    var box = el('div', { class: 'rb-fgroup depth-' + Math.min(depth, 3) });
    var head = el('div', { class: 'rb-fgroup-head' });
    head.appendChild(select([['and', 'همه‌ی شرط‌ها (AND)'], ['or', 'یکی از شرط‌ها (OR)']], node.op || 'and',
      function (v) { node.op = v; changed(); }));
    head.appendChild(btn('＋ شرط', function () { node.items.push({ field: '', operator: 'eq', value: '' }); changed(true); }));
    if (depth < 3) head.appendChild(btn('＋ گروه تو در تو', function () { node.items.push({ op: 'or', items: [] }); changed(true); }));
    if (onRemove) head.appendChild(btn('✕ حذف گروه', onRemove, 'btn-ghost btn-xs rb-x'));
    box.appendChild(head);
    if (!node.items.length) box.appendChild(el('div', { class: 'muted small', text: 'شرطی نیست — همه‌ی ردیف‌ها.' }));
    node.items.forEach(function (it, i) {
      var remove = function () { node.items.splice(i, 1); changed(true); };
      if (it && it.items) { box.appendChild(filterTree(it, remove, depth + 1)); return; }
      var row = el('div', { class: 'rb-cond' });
      row.appendChild(fieldSelect(it.field, function (v) { it.field = v; it.value = ''; it.value2 = ''; it.operator = operatorsFor(fieldOf(v))[0].key; changed(true); }));
      row.appendChild(select(operatorsFor(fieldOf(it.field)).map(function (o) { return [o.key, o.label]; }), it.operator || 'eq',
        function (v) { it.operator = v; changed(true); }));
      row.appendChild(valueControl(it, function () { changed(); }));
      row.appendChild(btn('✕', remove, 'btn-ghost btn-xs rb-x'));
      box.appendChild(row);
    });
    return box;
  }
  function stepFilters(p) {
    var s1 = section('فیلترهای ثابت گزارش', 'این شرط‌ها همیشه اعمال می‌شوند و کاربر آن‌ها را نمی‌بیند یا عوض نمی‌کند. با گروه‌های تو در تو می‌توانید AND و OR را ترکیب کنید.');
    if (!S.def.filters || !S.def.filters.items) S.def.filters = { op: 'and', items: [] };
    s1.appendChild(filterTree(S.def.filters, null, 0));
    p.appendChild(s1);
    var s2 = section('فیلترهای تعاملی (برای کاربر)', 'کنترل‌هایی که بالای داشبورد نمایش داده می‌شوند و کاربر با آن‌ها داده را محدود می‌کند — فقط روی همین فیلدها.');
    var list = S.def.interactive_filters;
    list.forEach(function (f, i) {
      var card = itemCard(f.label || labelOf(f.field) || 'فیلتر', function () { list.splice(i, 1); changed(true); },
        i > 0 ? function () { move(list, i, -1); } : null, i < list.length - 1 ? function () { move(list, i, 1); } : null);
      var g = el('div', { class: 'field-group cols-3' });
      g.appendChild(fld('فیلد', fieldSelect(f.field, function (v) {
        f.field = v; var fd = fieldOf(v);
        f.kind = isDate(fd) ? 'date_range' : isNum(fd) ? 'number_range' : (fd && fd.type === 'multi') ? 'multi' : (fd && fd.options) ? 'select' : 'text';
        changed(true); })));
      g.appendChild(fld('نوع کنترل', select([['select', 'انتخاب یکی'], ['multi', 'انتخاب چندتایی'], ['date_range', 'بازه‌ی تاریخ / نسبی'],
        ['number_range', 'بازه‌ی عددی'], ['text', 'جستجوی متن']], f.kind || 'select', function (v) { f.kind = v; changed(); })));
      g.appendChild(fld('برچسب', input(f.label, function (v) { f.label = v; changed(); }, { placeholder: labelOf(f.field) })));
      card.body.appendChild(g);
      s2.appendChild(card);
    });
    s2.appendChild(btn('＋ فیلتر تعاملی', function () { list.push({ id: uid('f'), field: '', kind: 'select' }); changed(true); }, 'btn-primary btn-sm'));
    p.appendChild(s2);
  }

  /* 5 ─ calcs */
  function refText(f) {
    var dup = allFields().filter(function (x) { return x.label === f.label; }).length > 1;
    return '[' + (dup ? f.key : f.label) + ']';
  }
  function insertAt(t, text) {
    var s = t.selectionStart || t.value.length, e = t.selectionEnd || t.value.length;
    t.value = t.value.slice(0, s) + text + t.value.slice(e);
    t.focus();
    t.selectionStart = t.selectionEnd = s + text.length;
    t.dispatchEvent(new Event('input'));
  }
  function stepCalcs(p) {
    p.appendChild(el('div', { class: 'hint rb-hint', html:
      'فیلدها با <code>[نام فیلد]</code> آورده می‌شوند. فرمول <b>سطری</b> روی هر ردیف حساب می‌شود و مثل یک فیلد در فیلتر، گروه‌بندی و سنجه به کار می‌رود — مثل <code>[دبی آزمایش] - [دبی طراحی]</code>. '
      + 'فرمول <b>تجمیعی</b> تابعی مثل SUM، COUNT یا AVG دارد و برای هر گروه یک عدد می‌دهد — مثل <code>ROUND(COUNT_IF([عملیات] = "کشیدن") / COUNT() * 100, 1)</code>.' }));
    var list = S.def.calcs;
    list.forEach(function (c, i) {
      var card = itemCard(c.label || 'فرمول', function () { list.splice(i, 1); changed(true); });
      var g = el('div', { class: 'field-group cols-3' });
      g.appendChild(fld('نام فیلد محاسباتی', input(c.label, function (v) { c.label = v; changed(); })));
      g.appendChild(fld('کلید', input(c.key, function (v) { c.key = v.replace(/[^\w]/g, '_'); changed(); }, { class: 'mono' }), 'برای ارجاع در سنجه‌ها'));
      g.appendChild(fld('نوع نتیجه', select([['decimal', 'عدد'], ['integer', 'عدد صحیح'], ['percent', 'درصد'], ['text', 'متن'], ['boolean', 'بله/خیر'], ['date', 'تاریخ']],
        c.result_type || 'decimal', function (v) { c.result_type = v; changed(); })));
      card.body.appendChild(g);
      var t = textarea(c.formula, function (v) { c.formula = v; changed(); status.textContent = ''; }, { class: 'mono rb-formula', rows: 3, dir: 'ltr' });
      card.body.appendChild(t);
      var tools = el('div', { class: 'rb-inline' });
      tools.appendChild(select(fieldOptions(function (f) { return f.key !== c.key; }, '＋ درج فیلد…'), '', function (v) {
        if (!v) return; insertAt(t, refText(fieldOf(v))); this.value = ''; }));
      tools.appendChild(select([['', '＋ درج تابع…']].concat(S.meta.functions.map(function (fn) { return [fn.name, fn.name + (fn.aggregate ? ' (تجمیعی)' : '')]; })), '',
        function (v) { if (v) { insertAt(t, v + '()'); this.value = ''; } }));
      var status = el('span', { class: 'rb-formula-status' });
      tools.appendChild(btn('✔ بررسی فرمول', async function () {
        try {
          var res = await A.api.post(API + '/formula/validate', { source: S.def.source, formula: c.formula, calcs: list, key: c.key });
          var d = res.data;
          status.className = 'rb-formula-status ' + (d.valid ? 'ok' : 'bad');
          status.textContent = d.valid ? ('✓ معتبر — ' + d.kind_label + (d.sample !== null && d.sample !== undefined ? ' · نمونه: ' + RV.fmt(d.sample) : ''))
            : ('✕ ' + d.error);
        } catch (err) { status.className = 'rb-formula-status bad'; status.textContent = err.message; }
      }));
      tools.appendChild(btn('📐 راهنما', function () { A.openModal('rb-fn-modal'); }));
      card.body.appendChild(tools);
      card.body.appendChild(status);
      p.appendChild(card);
    });
    p.appendChild(btn('＋ فیلد محاسباتی', function () {
      list.push({ key: uid('c_'), label: 'فرمول ' + (list.length + 1).toLocaleString('fa-IR'), formula: '', result_type: 'decimal' });
      changed(true); }, 'btn-primary btn-sm'));
  }

  /* 6 ─ groups & measures */
  function measureEditor(m, onRemove, i, list) {
    var card = itemCard(m.label || 'سنجه', onRemove, i > 0 ? function () { move(list, i, -1); } : null,
      i < list.length - 1 ? function () { move(list, i, 1); } : null);
    var mode = m.calc ? 'calc' : 'field';
    var g = el('div', { class: 'field-group cols-3' });
    g.appendChild(fld('نوع', select([['field', 'تجمیع روی فیلد'], ['calc', 'فیلد محاسباتی']], mode, function (v) {
      if (v === 'calc') { delete m.field; m.calc = (calcFields()[0] || {}).key || ''; m.agg = 'sum'; }
      else { delete m.calc; m.field = '*'; m.agg = 'count'; }
      changed(true); })));
    if (mode === 'field') {
      g.appendChild(fld('فیلد', fieldSelect(m.field || '*', function (v) {
        m.field = v; var opts = aggOptions(fieldOf(v) || { key: '*' });
        if (!opts.some(function (o) { return o[0] === m.agg; })) m.agg = opts[0][0];
        changed(true); }, function (f) { return !f.calc; }, false, true)));
      g.appendChild(fld('تجمیع', select(aggOptions(m.field === '*' ? { key: '*' } : fieldOf(m.field)), m.agg || 'count',
        function (v) { m.agg = v; changed(true); })));
    } else {
      g.appendChild(fld('فیلد محاسباتی', select(calcFields().map(function (c) { return [c.key, c.label]; }), m.calc, function (v) { m.calc = v; changed(); })));
      g.appendChild(fld('تجمیع (برای فرمول سطری)', select(aggOptions({ type: 'decimal', key: 'x' }), m.agg || 'sum', function (v) { m.agg = v; changed(); }),
        'فرمول تجمیعی خودش حساب می‌شود'));
    }
    if (m.agg === 'percentile') g.appendChild(fld('صدک', input(m.p || 90, function (v) { m.p = v; changed(); }, { type: 'number', min: 1, max: 99 })));
    g.appendChild(fld('برچسب', input(m.label, function (v) { m.label = v; changed(); })));
    g.appendChild(fld('قالب', select([['', 'عدد'], ['percent', 'درصد']], m.format || '', function (v) { m.format = v || undefined; changed(); })));
    g.appendChild(fld('اعشار', input(m.decimals, function (v) { m.decimals = v; changed(); }, { type: 'number', min: 0, max: 6 })));
    g.appendChild(fld('واحد', input(m.unit, function (v) { m.unit = v; changed(); }, { placeholder: 'مثلاً ساعت' })));
    card.body.appendChild(g);
    card.body.appendChild(el('div', { class: 'muted small mono', text: 'کلید: ' + m.key }));
    return card;
  }
  function stepGroups(p) {
    var d = S.def;
    var s1 = section('گروه‌بندی چندسطحی', 'ردیف‌ها بر اساس این فیلدها دسته می‌شوند؛ ترتیب مهم است (مثلاً مرکز ← سال). فیلد چندانتخابی در هر گزینه‌اش شمرده می‌شود.');
    d.groups.forEach(function (gr, i) {
      var row = el('div', { class: 'rb-cond' });
      row.appendChild(el('span', { class: 'rb-handle', text: (i + 1).toLocaleString('fa-IR') }));
      row.appendChild(fieldSelect(gr.field, function (v) { gr.field = v; if (!isDate(fieldOf(v))) delete gr.granularity; changed(true); }));
      if (isDate(fieldOf(gr.field))) row.appendChild(granSelect(gr.granularity || 'month', function (v) { gr.granularity = v || undefined; changed(); }));
      if ((fieldOf(gr.field) || {}).type === 'multi') row.appendChild(check('هر گزینه جدا', gr.explode !== false, function (v) { gr.explode = v; changed(); }));
      row.appendChild(btn('▲', function () { move(d.groups, i, -1); }, 'btn-ghost btn-xs'));
      row.appendChild(btn('▼', function () { move(d.groups, i, 1); }, 'btn-ghost btn-xs'));
      row.appendChild(btn('✕', function () { d.groups.splice(i, 1); changed(true); }, 'btn-ghost btn-xs rb-x'));
      s1.appendChild(row);
    });
    s1.appendChild(btn('＋ سطح گروه‌بندی', function () { d.groups.push({ field: '' }); changed(true); }));
    p.appendChild(s1);

    var s2 = section('سنجه‌ها (Measures)', 'عددهایی که برای هر گروه حساب می‌شوند: تعداد، جمع، میانگین، میانه، صدک، انحراف معیار… یا یک فیلد محاسباتی. نمودارها و KPIها از همین سنجه‌ها استفاده می‌کنند.');
    d.measures.forEach(function (m, i) {
      s2.appendChild(measureEditor(m, function () { d.measures.splice(i, 1); changed(true); }, i, d.measures));
    });
    s2.appendChild(btn('＋ سنجه', function () { d.measures.push({ key: uid('m_'), field: '*', agg: 'count', label: 'تعداد' }); changed(true); }, 'btn-primary btn-sm'));
    p.appendChild(s2);

    var s3 = section('مرتب‌سازی و محدودیت');
    var sortKeys = [['', '— بدون مرتب‌سازی —']].concat(d.groups.map(function (g, i) { return ['g' + i, labelOf(g.field)]; }))
      .concat(d.measures.map(function (m) { return [m.key, m.label || m.key]; }));
    var srt = d.sort[0] || {};
    var g = el('div', { class: 'field-group cols-3' });
    g.appendChild(fld('مرتب‌سازی بر اساس', select(sortKeys, srt.key || '', function (v) {
      d.sort = v ? [{ key: v, dir: srt.dir || 'desc' }] : []; changed(true); })));
    g.appendChild(fld('جهت', select([['desc', 'نزولی'], ['asc', 'صعودی']], srt.dir || 'desc', function (v) {
      if (d.sort[0]) d.sort[0].dir = v; changed(); })));
    g.appendChild(fld('حداکثر تعداد گروه (Top N)', input(d.limit, function (v) { d.limit = v || undefined; changed(); }, { type: 'number', min: 1 })));
    s3.appendChild(g);
    p.appendChild(s3);
  }

  /* 7 ─ KPIs */
  function stepKpis(p) {
    var list = S.def.kpis;
    p.appendChild(el('div', { class: 'hint rb-hint', text: 'هر KPI یک عدد مدیریتی است با هدف، وضعیت (سبز/زرد/قرمز)، مقایسه با دوره‌ی قبل و روند ۱۲ دوره‌ی اخیر.' }));
    list.forEach(function (k, i) {
      var v = k.value = k.value || { agg: 'count', field: '*' };
      var card = itemCard(k.title || 'KPI', function () { list.splice(i, 1); changed(true); },
        i > 0 ? function () { move(list, i, -1); } : null, i < list.length - 1 ? function () { move(list, i, 1); } : null);
      var mode = v.formula !== undefined ? 'formula' : v.calc ? 'calc' : 'agg';
      var g = el('div', { class: 'field-group cols-3' });
      g.appendChild(fld('عنوان', input(k.title, function (x) { k.title = x; changed(); })));
      g.appendChild(fld('آیکون', input(k.icon, function (x) { k.icon = x; changed(); }, { placeholder: 'مثلاً ⏱' })));
      g.appendChild(fld('روش محاسبه', select([['agg', 'تجمیع روی فیلد'], ['calc', 'فیلد محاسباتی'], ['formula', 'فرمول مستقیم']], mode, function (x) {
        k.value = x === 'formula' ? { formula: '' } : x === 'calc' ? { calc: (calcFields()[0] || {}).key } : { agg: 'count', field: '*' };
        changed(true); })));
      if (mode === 'agg') {
        g.appendChild(fld('فیلد', fieldSelect(v.field || '*', function (x) {
          v.field = x; var o = aggOptions(fieldOf(x) || { key: '*' });
          if (!o.some(function (a) { return a[0] === v.agg; })) v.agg = o[0][0];
          changed(true); }, function (f) { return !f.calc; }, false, true)));
        g.appendChild(fld('تجمیع', select(aggOptions(v.field === '*' ? { key: '*' } : fieldOf(v.field)), v.agg || 'count', function (x) { v.agg = x; changed(); })));
      } else if (mode === 'calc') {
        g.appendChild(fld('فیلد محاسباتی', select(calcFields().map(function (c) { return [c.key, c.label]; }), v.calc, function (x) { v.calc = x; changed(); })));
      }
      card.body.appendChild(g);
      if (mode === 'formula') {
        card.body.appendChild(fld('فرمول تجمیعی', textarea(v.formula, function (x) { v.formula = x; changed(); }, { class: 'mono', dir: 'ltr', rows: 2 }),
          'مثال: ROUND(COUNT_IF([وضعیت] = "تکمیل‌شده") / COUNT() * 100, 1)'));
      }
      var g2 = el('div', { class: 'field-group cols-3' });
      g2.appendChild(fld('هدف (Target)', input(k.target, function (x) { k.target = x; changed(); }, { type: 'number' })));
      g2.appendChild(fld('بهتر است', select([['higher', 'بیشتر باشد'], ['lower', 'کمتر باشد']], k.direction || 'higher', function (x) { k.direction = x; changed(); })));
      g2.appendChild(fld('تحمل «نزدیک هدف» (٪)', input(k.tolerance || 10, function (x) { k.tolerance = x; changed(); }, { type: 'number' })));
      g2.appendChild(fld('واحد', input(k.unit, function (x) { k.unit = x; changed(); })));
      g2.appendChild(fld('قالب', select([['', 'عدد'], ['percent', 'درصد']], k.format || '', function (x) { k.format = x || undefined; changed(); })));
      g2.appendChild(fld('اعشار', input(k.decimals, function (x) { k.decimals = x; changed(); }, { type: 'number', min: 0, max: 6 })));
      card.body.appendChild(g2);
      var g3 = el('div', { class: 'field-group cols-3' });
      g3.appendChild(fld('فیلد تاریخ برای مقایسه', fieldSelect(k.period_field, function (x) { k.period_field = x || undefined; changed(true); }, isDate, '— بدون مقایسه —')));
      if (k.period_field) {
        g3.appendChild(fld('دوره', select([['month', 'ماه'], ['quarter', 'فصل'], ['year', 'سال']], k.period || 'month', function (x) { k.period = x; changed(); })));
        var cc = el('div', {});
        cc.appendChild(check('مقایسه با دوره‌ی قبل', k.compare, function (x) { k.compare = x; changed(); }));
        cc.appendChild(check('روند ۱۲ دوره‌ی اخیر', k.trend, function (x) { k.trend = x; changed(); }));
        g3.appendChild(cc);
      }
      card.body.appendChild(g3);
      p.appendChild(card);
    });
    p.appendChild(btn('＋ KPI', function () {
      list.push({ id: uid('k'), title: 'شاخص ' + (list.length + 1).toLocaleString('fa-IR'), value: { agg: 'count', field: '*' } });
      changed(true); }, 'btn-primary btn-sm'));
  }

  /* 8 ─ charts */
  function chartNeeds(t) {
    return {
      xy: ['scatter', 'bubble'].indexOf(t) >= 0,
      value: ['histogram', 'box'].indexOf(t) >= 0,
      single: ['kpi', 'gauge', 'progress'].indexOf(t) >= 0,
      trend: t.indexOf('trend_') === 0,
      series: ['stacked_bar', 'stacked_column', 'heatmap', 'radar', 'line', 'area', 'bar', 'column', 'comparison'].indexOf(t) >= 0 || t.indexOf('trend_') === 0
    };
  }
  function stepCharts(p) {
    var list = S.def.charts;
    var measures = S.def.measures;
    if (!measures.length) p.appendChild(el('div', { class: 'alert warn', text: 'هنوز سنجه‌ای تعریف نشده؛ نمودارها «تعداد ردیف‌ها» را نشان می‌دهند. سنجه‌ها را در مرحله‌ی ۶ بسازید.' }));
    list.forEach(function (c, i) {
      var need = chartNeeds(c.type || 'bar');
      var card = itemCard((c.title || 'نمودار') + ' — ' + ((S.meta.chart_types.filter(function (t) { return t.key === c.type; })[0] || {}).label || c.type),
        function () { list.splice(i, 1); changed(true); },
        i > 0 ? function () { move(list, i, -1); } : null, i < list.length - 1 ? function () { move(list, i, 1); } : null);
      // type picker
      var fam = {}, famOrder = [];
      S.meta.chart_types.forEach(function (t) { if (!fam[t.family]) { fam[t.family] = []; famOrder.push(t.family); } fam[t.family].push(t); });
      var picker = el('div', { class: 'rb-ctypes' });
      famOrder.forEach(function (f) {
        picker.appendChild(el('span', { class: 'rb-ctype-fam', text: f }));
        fam[f].forEach(function (t) {
          picker.appendChild(el('button', { type: 'button', class: 'rb-ctype' + (c.type === t.key ? ' active' : ''), text: t.label,
            onclick: function () { c.type = t.key; changed(true); } }));
        });
      });
      card.body.appendChild(picker);
      var g = el('div', { class: 'field-group cols-3' });
      g.appendChild(fld('عنوان', input(c.title, function (v) { c.title = v; changed(); })));
      g.appendChild(fld('زیرعنوان', input(c.subtitle, function (v) { c.subtitle = v; changed(); })));
      g.appendChild(fld('ارتفاع', select([['md', 'متوسط'], ['sm', 'کوتاه'], ['lg', 'بلند']], c.height || 'md', function (v) { c.height = v; changed(); })));
      if (need.xy) {
        g.appendChild(fld('محور X (عددی)', fieldSelect((c.x || {}).field, function (v) { c.x = { field: v }; changed(); }, isNum)));
        g.appendChild(fld('محور Y (عددی)', fieldSelect(c.y_field, function (v) { c.y_field = v; changed(); }, isNum)));
        if (c.type === 'bubble') g.appendChild(fld('اندازه‌ی حباب', fieldSelect(c.size_field, function (v) { c.size_field = v; changed(); }, isNum)));
      } else if (need.value) {
        g.appendChild(fld('فیلد مقدار (عددی)', fieldSelect(c.value_field, function (v) { c.value_field = v; changed(); }, isNum)));
        if (c.type === 'histogram') g.appendChild(fld('تعداد بازه‌ها', input(c.bins || 10, function (v) { c.bins = v; changed(); }, { type: 'number', min: 2, max: 50 })));
        else g.appendChild(fld('تفکیک بر اساس', fieldSelect((c.x || {}).field, function (v) { c.x = v ? { field: v } : {}; changed(); }, null, '— بدون تفکیک —')));
      } else if (!need.single) {
        var x = c.x = c.x || {};
        g.appendChild(fld(need.trend ? 'فیلد تاریخ' : 'محور دسته‌بندی (X)', fieldSelect(x.field, function (v) { x.field = v; changed(true); }, need.trend ? isDate : null)));
        if (isDate(fieldOf(x.field)) && !need.trend) g.appendChild(fld('تفکیک زمانی', granSelect(x.granularity, function (v) { x.granularity = v || undefined; changed(); })));
        if (need.series) g.appendChild(fld('سری‌ها بر اساس (اختیاری)', fieldSelect((c.series_by || {}).field, function (v) { c.series_by = v ? { field: v } : {}; changed(); }, null, '— بدون سری —')));
      }
      card.body.appendChild(g);
      if (!need.xy && !need.value) {
        var mbox = el('div', { class: 'rb-chips' });
        var sel = c.measures = c.measures || [];
        (measures.length ? measures : []).forEach(function (m) {
          var on = sel.indexOf(m.key) >= 0;
          mbox.appendChild(el('button', { type: 'button', class: 'rb-chip toggle' + (on ? ' on' : ''), text: m.label || m.key, onclick: function () {
            if (on) sel.splice(sel.indexOf(m.key), 1); else sel.push(m.key);
            changed(true); } }));
        });
        card.body.appendChild(fld('سنجه‌های نمودار', mbox, measures.length ? 'بدون انتخاب: تعداد ردیف‌ها. با «سری‌ها» فقط سنجه‌ی اول به کار می‌رود.' : 'سنجه‌ای تعریف نشده'));
      }
      var g2 = el('div', { class: 'field-group cols-3' });
      if (need.single) {
        g2.appendChild(fld('هدف', input(c.target, function (v) { c.target = v; changed(); }, { type: 'number' })));
        g2.appendChild(fld('بیشینه‌ی گیج', input(c.max, function (v) { c.max = v; changed(); }, { type: 'number' })));
        g2.appendChild(fld('واحد', input(c.unit, function (v) { c.unit = v; changed(); })));
      } else if (!need.xy && !need.value) {
        g2.appendChild(fld('حداکثر دسته‌ها (Top N)', input(c.limit, function (v) { c.limit = v || undefined; changed(); }, { type: 'number', min: 1 })));
        g2.appendChild(fld('ترتیب', select([['', 'ترتیب طبیعی'], ['value', 'بر اساس مقدار (نزولی)']], (c.sort || {}).by || '', function (v) { c.sort = v ? { by: 'value', dir: 'desc' } : {}; changed(); })));
        var opts = el('div', {});
        opts.appendChild(check('نمایش مقدار روی نمودار', c.show_labels, function (v) { c.show_labels = v; changed(); }));
        if (c.type === 'line' || need.trend) opts.appendChild(check('منحنی نرم', c.smooth, function (v) { c.smooth = v; changed(); }));
        g2.appendChild(opts);
      }
      g2.appendChild(fld('رنگ‌ها (اختیاری)', input((c.colors || []).join(','), function (v) {
        c.colors = v.split(',').map(function (s) { return s.trim(); }).filter(Boolean); changed(); }, { placeholder: '#1f6fa5,#f39c12', class: 'mono', dir: 'ltr' })));
      card.body.appendChild(g2);
      p.appendChild(card);
    });
    p.appendChild(btn('＋ نمودار', function () {
      list.push({ id: uid('ch'), type: 'bar', title: 'نمودار ' + (list.length + 1).toLocaleString('fa-IR'),
        x: { field: (S.def.groups[0] || {}).field || '' }, measures: S.def.measures.slice(0, 1).map(function (m) { return m.key; }) });
      changed(true); }, 'btn-primary btn-sm'));
  }

  /* 9 ─ tables */
  function stepTables(p) {
    var list = S.def.tables;
    p.appendChild(el('div', { class: 'hint rb-hint', text: 'جدول «گروه‌بندی‌شده» سنجه‌ها را برای هر گروه با جمع کل و جمع‌های میانی نشان می‌دهد؛ جدول «جزئیات» ردیف‌ها را با ستون‌های دلخواه و ردیف جمع/میانگین.' }));
    if (!list.length) p.appendChild(el('div', { class: 'muted small', text: 'جدولی تعریف نشده؛ یک جدول پیش‌فرض (بر اساس گروه‌بندی یا فیلدها) نمایش داده می‌شود.' }));
    list.forEach(function (t, i) {
      var card = itemCard(t.title || 'جدول', function () { list.splice(i, 1); changed(true); },
        i > 0 ? function () { move(list, i, -1); } : null, i < list.length - 1 ? function () { move(list, i, 1); } : null);
      var g = el('div', { class: 'field-group cols-3' });
      g.appendChild(fld('عنوان', input(t.title, function (v) { t.title = v; changed(); })));
      g.appendChild(fld('نوع', select([['grouped', 'گروه‌بندی‌شده (Pivot)'], ['detail', 'جزئیات ردیف‌ها']], t.kind || 'grouped', function (v) { t.kind = v; changed(true); })));
      g.appendChild(fld('حداکثر ردیف', input(t.limit, function (v) { t.limit = v || undefined; changed(); }, { type: 'number', min: 1 })));
      g.appendChild(fld('ردیف در هر صفحه', input(t.page_size || 25, function (v) { t.page_size = v; changed(); }, { type: 'number', min: 5, max: 500 })));
      card.body.appendChild(g);
      if ((t.kind || 'grouped') === 'grouped') {
        card.body.appendChild(el('div', { class: 'muted small', text: 'گروه‌بندی: ' + (S.def.groups.map(function (x) { return labelOf(x.field); }).join(' ← ') || '(بدون گروه‌بندی)') + ' — از مرحله‌ی ۶' }));
        var mbox = el('div', { class: 'rb-chips' });
        var sel = t.measures = t.measures || [];
        S.def.measures.forEach(function (m) {
          var on = sel.indexOf(m.key) >= 0;
          mbox.appendChild(el('button', { type: 'button', class: 'rb-chip toggle' + (on ? ' on' : ''), text: m.label || m.key, onclick: function () {
            if (on) sel.splice(sel.indexOf(m.key), 1); else sel.push(m.key); changed(true); } }));
        });
        card.body.appendChild(fld('سنجه‌ها', mbox, 'بدون انتخاب: همه‌ی سنجه‌ها'));
        card.body.appendChild(check('جمع میانی برای سطح اول گروه‌بندی', t.subtotals, function (v) { t.subtotals = v; changed(); }));
      } else {
        var cols = t.columns = t.columns || [];
        var cbox = el('div', { class: 'rb-chips' });
        var pool = (S.def.fields.length ? S.def.fields.map(function (f) { return fieldOf(f.key); }).filter(Boolean) : allFields().slice(0, 40))
          .concat(calcFields().filter(function (c) { return !S.def.fields.some(function (f) { return f.key === c.key; }); }));
        pool.forEach(function (f) {
          var on = cols.indexOf(f.key) >= 0;
          cbox.appendChild(el('button', { type: 'button', class: 'rb-chip toggle' + (on ? ' on' : ''), text: f.label, onclick: function () {
            if (on) cols.splice(cols.indexOf(f.key), 1); else cols.push(f.key); changed(true); } }));
        });
        card.body.appendChild(fld('ستون‌ها', cbox, 'فهرست از فیلدهای مرحله‌ی ۳؛ بدون انتخاب: همان فیلدها.'));
        var totals = t.totals = t.totals || {};
        var tg = el('div', { class: 'field-group cols-3' });
        (cols.length ? cols : S.def.fields.map(function (f) { return f.key; })).forEach(function (k) {
          var f = fieldOf(k);
          if (!isNum(f)) return;
          tg.appendChild(fld('ردیف پایانی «' + f.label + '»', select([['', '—'], ['sum', 'جمع'], ['avg', 'میانگین'], ['min', 'کمینه'], ['max', 'بیشینه'], ['count_values', 'تعداد']],
            totals[k] || '', function (v) { if (v) totals[k] = v; else delete totals[k]; changed(); })));
        });
        card.body.appendChild(tg);
      }
      p.appendChild(card);
    });
    p.appendChild(btn('＋ جدول', function () {
      list.push({ id: uid('t'), title: 'جدول ' + (list.length + 1).toLocaleString('fa-IR'), kind: S.def.groups.length ? 'grouped' : 'detail' });
      changed(true); }, 'btn-primary btn-sm'));
  }

  /* 10 ─ conditional formatting */
  function stepRules(p) {
    var list = S.def.rules;
    p.appendChild(el('div', { class: 'hint rb-hint', text: 'رنگ‌آمیزی خودکار سلول‌های جدول و کارت‌های KPI. اولین قانونی که برقرار باشد اعمال می‌شود؛ مثلاً «تأخیر > ۴۸ → قرمز».' }));
    var targets = [['*', '(همه‌ی ستون‌ها)']];
    S.def.measures.forEach(function (m) { targets.push([m.key, 'سنجه: ' + (m.label || m.key)]); });
    S.def.kpis.forEach(function (k) { targets.push([k.id, 'KPI: ' + (k.title || k.id)]); });
    (S.def.fields || []).forEach(function (f) { targets.push([f.key, 'ستون: ' + labelOf(f.key)]); });
    calcFields().forEach(function (c) { targets.push([c.key, 'محاسباتی: ' + c.label]); });
    list.forEach(function (r, i) {
      var row = el('div', { class: 'rb-cond rb-rule' });
      row.appendChild(select(targets, r.target || '*', function (v) { r.target = v; changed(); }));
      row.appendChild(select([['>', '>'], ['>=', '≥'], ['<', '<'], ['<=', '≤'], ['=', '='], ['!=', '≠'], ['contains', 'شامل']], r.operator || '>', function (v) { r.operator = v; changed(); }));
      row.appendChild(input(r.value, function (v) { r.value = v; changed(); }, { placeholder: 'مقدار', class: 'rb-narrow' }));
      row.appendChild(select([['bad', '🔴 نامطلوب'], ['warn', '🟡 هشدار'], ['ok', '🟢 مطلوب'], ['info', '🔵 اطلاع']], r.style || 'warn', function (v) { r.style = v; changed(); }));
      row.appendChild(input(r.label, function (v) { r.label = v; changed(); }, { placeholder: 'برچسب (اختیاری)' }));
      var color = el('input', { type: 'color', value: r.color || '#ffffff', title: 'رنگ دلخواه (اختیاری)' });
      color.addEventListener('change', function () { r.color = color.value === '#ffffff' ? undefined : color.value; changed(); });
      row.appendChild(color);
      row.appendChild(btn('✕', function () { list.splice(i, 1); changed(true); }, 'btn-ghost btn-xs rb-x'));
      p.appendChild(row);
    });
    p.appendChild(btn('＋ قانون', function () { list.push({ target: (S.def.measures[0] || {}).key || '*', operator: '>', value: '', style: 'bad' }); changed(true); }, 'btn-primary btn-sm'));
  }

  /* 11 ─ layout & interaction */
  function blocks() {
    var out = [];
    S.def.kpis.forEach(function (k) { out.push(['kpi:' + k.id, 'KPI: ' + (k.title || k.id), 3]); });
    S.def.charts.forEach(function (c) { out.push(['chart:' + c.id, 'نمودار: ' + (c.title || c.id), chartNeeds(c.type || 'bar').single ? 3 : 6]); });
    (S.def.tables.length ? S.def.tables : [{ id: '_main', title: 'جدول پیش‌فرض' }]).forEach(function (t) { out.push(['table:' + t.id, 'جدول: ' + (t.title || t.id), 12]); });
    return out;
  }
  function stepLayout(p) {
    var d = S.def;
    var s1 = section('چیدمان داشبورد', 'صفحه ۱۲ ستون دارد؛ عرض هر بخش را انتخاب کنید و با ▲▼ ترتیب را عوض کنید. بخش‌هایی که در چیدمان نیستند در انتها نمایش داده می‌شوند.');
    var all = blocks();
    if (!d.layout.length) {
      s1.appendChild(el('div', { class: 'muted small', text: 'چیدمان خودکار است (KPIها در یک ردیف، نمودارها دوتایی، جدول تمام‌عرض).' }));
      s1.appendChild(btn('✎ چیدمان دستی', function () { d.layout = all.map(function (b) { return { ref: b[0], w: b[2] }; }); changed(true); }, 'btn-primary btn-sm'));
    } else {
      var labels = {};
      all.forEach(function (b) { labels[b[0]] = b[1]; });
      var preview = el('div', { class: 'rb-layout-preview' });
      d.layout.forEach(function (item, i) {
        var row = el('div', { class: 'rb-cond' });
        row.appendChild(el('b', { class: 'rb-layout-name', text: item.ref.indexOf('text:') === 0 ? 'متن: ' + (item.title || '') : (labels[item.ref] || item.ref + ' (حذف‌شده)') }));
        row.appendChild(select([['3', '¼ عرض'], ['4', '⅓ عرض'], ['6', '½ عرض'], ['8', '⅔ عرض'], ['12', 'تمام عرض']], String(item.w || 6), function (v) { item.w = Number(v); changed(true); }));
        if (item.ref.indexOf('text:') === 0) {
          row.appendChild(input(item.title, function (v) { item.title = v; changed(); }, { placeholder: 'عنوان' }));
          row.appendChild(input(item.text, function (v) { item.text = v; changed(); }, { placeholder: 'متن توضیح' }));
        }
        row.appendChild(btn('▲', function () { move(d.layout, i, -1); }, 'btn-ghost btn-xs'));
        row.appendChild(btn('▼', function () { move(d.layout, i, 1); }, 'btn-ghost btn-xs'));
        row.appendChild(btn('✕', function () { d.layout.splice(i, 1); changed(true); }, 'btn-ghost btn-xs rb-x'));
        s1.appendChild(row);
        preview.appendChild(el('div', { class: 'rb-lp-cell', style: 'grid-column: span ' + (item.w || 6), text: (labels[item.ref] || item.title || '').replace(/^[^:]+: /, '') }));
      });
      var missing = all.filter(function (b) { return !d.layout.some(function (x) { return x.ref === b[0]; }); });
      var tools = el('div', { class: 'rb-inline' });
      if (missing.length) tools.appendChild(select([['', '＋ افزودن بخش…']].concat(missing.map(function (b) { return [b[0], b[1]]; })), '', function (v) {
        if (!v) return; var b = missing.filter(function (x) { return x[0] === v; })[0]; d.layout.push({ ref: v, w: b[2] }); changed(true); }));
      tools.appendChild(btn('＋ بخش متنی', function () { d.layout.push({ ref: 'text:' + uid('x'), w: 12, title: 'توضیح', text: '' }); changed(true); }));
      tools.appendChild(btn('↺ چیدمان خودکار', function () { d.layout = []; changed(true); }));
      s1.appendChild(tools);
      s1.appendChild(preview);
    }
    p.appendChild(s1);

    var s2 = section('Drill-down (کاوش سلسله‌مراتبی)', 'مسیر کاوش؛ مثلاً مرکز ← سال ← ماه ← رکوردها. کاربر با کلیک روی هر سطر یک سطح پایین‌تر می‌رود و در انتها ردیف‌های واقعی را می‌بیند.');
    var drill = d.drill = d.drill || { enabled: false, path: [] };
    s2.appendChild(check('Drill-down فعال باشد', drill.enabled, function (v) { drill.enabled = v; changed(true); }));
    if (drill.enabled) {
      drill.path = (drill.path || []).filter(function (x) { return x !== '_detail'; });
      drill.path.forEach(function (lvl, i) {
        var parts = String(lvl).split(':');
        var row = el('div', { class: 'rb-cond' });
        row.appendChild(el('span', { class: 'rb-handle', text: (i + 1).toLocaleString('fa-IR') }));
        row.appendChild(fieldSelect(parts[0], function (v) { drill.path[i] = v; changed(true); }));
        if (isDate(fieldOf(parts[0]))) row.appendChild(granSelect(parts[1] || 'year', function (v) { drill.path[i] = parts[0] + (v ? ':' + v : ''); changed(); }));
        row.appendChild(btn('✕', function () { drill.path.splice(i, 1); changed(true); }, 'btn-ghost btn-xs rb-x'));
        s2.appendChild(row);
      });
      s2.appendChild(btn('＋ سطح', function () { drill.path.push(''); changed(true); }));
      s2.appendChild(el('div', { class: 'muted small', text: 'آخرین سطح همیشه ردیف‌های جزئی با فیلدهای مرحله‌ی ۳ است.' }));
    }
    p.appendChild(s2);

    var s3 = section('تحلیل تخصصی');
    var an = d.analysis = d.analysis || {};
    s3.appendChild(check('صفحه‌ی تحلیل تخصصی (جدول جزئیات، فیلتر و مرتب‌سازی، جستجو)', an.enabled !== false, function (v) { an.enabled = v; changed(); }));
    s3.appendChild(check('جدول متقاطع (Crosstab)', an.crosstab !== false, function (v) { an.crosstab = v; changed(); }));
    s3.appendChild(check('آمار توصیفی (میانگین، میانه، انحراف معیار…)', an.stats !== false, function (v) { an.stats = v; changed(); }));
    p.appendChild(s3);
  }

  /* 12 ─ access */
  var LEVEL_PRESETS = {
    'فقط داشبورد': ['view_dashboard', 'run', 'filter'],
    'کاربر عادی': ['view_dashboard', 'run', 'filter', 'drilldown', 'export_xlsx', 'export_pdf', 'print'],
    'تحلیلگر': ['view_dashboard', 'view_analysis', 'run', 'filter', 'drilldown', 'raw_data', 'export_xlsx', 'export_pdf', 'export_docx', 'export_csv', 'print'],
    'کامل': null
  };
  async function stepAccess(p) {
    p.appendChild(el('div', { class: 'hint rb-hint', text: 'چه کسی گزارش منتشرشده را ببیند و چه کاری بتواند بکند. دسترسی به یک کاربر، یک نقش، یک مرکز (همه‌ی کاربران آن مرکز) یا یک گروه کاربری داده می‌شود و سطوح جمع می‌شوند. دسترسی به گزارش هرگز داده‌ای را که کاربر اجازه‌ی دیدنش را ندارد باز نمی‌کند.' }));
    if (!S.principals) {
      p.appendChild(el('div', { class: 'loading', text: 'در حال بارگذاری' }));
      try { S.principals = (await A.api.get(API + '/principals')).data; } catch (err) { A.toast(err.message, 'error'); return; }
      if (S.step === 'access') renderStep();
      return;
    }
    var P = S.principals, rows = S.report.permissions = S.report.permissions || [];
    var levels = Object.keys(P.levels);
    var add = el('div', { class: 'rb-inline rb-add-principal' });
    var kindSel = select(Object.keys(P.kinds).map(function (k) { return [k, P.kinds[k]]; }), 'role', function () { fillWho(); });
    var who = el('select', {});
    function fillWho() {
      who.innerHTML = '';
      var k = kindSel.value;
      var opts = k === 'user' ? P.users.map(function (u) { return [u.id, u.name + ' (' + u.username + ')']; })
        : k === 'role' ? P.roles.filter(function (r) { return r.key !== 'admin'; }).map(function (r) { return [r.key, r.label]; })
          : k === 'center' ? P.centers.map(function (c) { return [c.id, c.label]; })
            : P.groups.map(function (g) { return [g.id, g.name + ' (' + g.member_ids.length + ' نفر)']; });
      opts.forEach(function (o) { who.appendChild(el('option', { value: o[0], text: o[1] })); });
    }
    fillWho();
    add.appendChild(kindSel); add.appendChild(who);
    add.appendChild(btn('＋ افزودن', function () {
      if (!who.value) return;
      if (rows.some(function (r) { return r.principal_kind === kindSel.value && String(r.principal) === String(who.value); })) { A.toast('این مورد از قبل در فهرست است.', 'warn'); return; }
      rows.push({ principal_kind: kindSel.value, principal: String(who.value), label: who.selectedOptions[0].text, access: ['view_dashboard', 'run', 'filter'] });
      permsDirty = true; renderStep();
    }, 'btn-primary btn-sm'));
    p.appendChild(add);
    if (!P.groups.length) p.appendChild(el('div', { class: 'muted small', html: 'گروه کاربری ندارید؛ در صفحه‌ی <a href="/users#report-access">کاربران ← دسترسی گزارش‌ها</a> می‌توانید گروه بسازید.' }));
    var wrap = el('div', { class: 'table-scroll' });
    var table = el('table', { class: 'rb-perm-table' });
    var head = '<thead><tr><th>گیرنده</th>' + levels.map(function (l) { return '<th>' + A.esc(P.levels[l]) + '</th>'; }).join('') + '<th>پیش‌تنظیم</th><th></th></tr></thead>';
    table.innerHTML = head;
    var tb = el('tbody', {});
    if (!rows.length) tb.innerHTML = '<tr><td class="table-empty" colspan="' + (levels.length + 3) + '">هنوز به کسی دسترسی داده نشده — گزارش منتشرشده فقط برای مدیر سیستم دیده می‌شود.</td></tr>';
    rows.forEach(function (r, i) {
      var tr = el('tr', {});
      tr.appendChild(el('td', { html: '<span class="badge muted">' + A.esc(P.kinds[r.principal_kind]) + '</span> ' + A.esc(r.label || r.principal) }));
      levels.forEach(function (l) {
        var c = el('input', { type: 'checkbox' });
        c.checked = (r.access || []).indexOf(l) >= 0;
        c.addEventListener('change', function () {
          r.access = r.access || [];
          if (c.checked) r.access.push(l); else r.access = r.access.filter(function (x) { return x !== l; });
          permsDirty = true; saveBtn.classList.add('pulse');
        });
        tr.appendChild(el('td', { class: 'center' }, [c]));
      });
      tr.appendChild(el('td', {}, [select([['', '…']].concat(Object.keys(LEVEL_PRESETS).map(function (k) { return [k, k]; })), '', function (v) {
        if (!v) return; r.access = LEVEL_PRESETS[v] ? LEVEL_PRESETS[v].slice() : levels.slice(); permsDirty = true; renderStep(); })]));
      tr.appendChild(el('td', {}, [btn('✕', function () { rows.splice(i, 1); permsDirty = true; renderStep(); }, 'btn-ghost btn-xs rb-x')]));
      tb.appendChild(tr);
    });
    table.appendChild(tb);
    wrap.appendChild(table);
    p.appendChild(wrap);
    var saveBtn = btn('💾 ذخیره‌ی دسترسی‌ها', async function () {
      try {
        var res = await A.api.put(API + '/reports/' + S.report.id + '/permissions', { permissions: rows });
        S.report.permissions = res.data; permsDirty = false;
        A.toast('دسترسی‌ها ذخیره شد.', 'success'); renderStep();
      } catch (err) { A.toast(err.message, 'error'); }
    }, 'btn-primary' + (permsDirty ? ' pulse' : ''));
    p.appendChild(el('div', { class: 'form-actions' }, [saveBtn]));
    p.appendChild(el('div', { class: 'muted small', text: 'دسترسی‌ها جدا از تعریف گزارش و فوراً ذخیره می‌شوند؛ نسخه‌ی تازه نمی‌سازند.' }));
  }
  var permsDirty = false;

  /* 13 ─ validate, versions, publish, schedules */
  async function stepPublish(p) {
    var r = S.report;
    var top = el('div', { class: 'rb-publish-top' });
    top.appendChild(el('div', { html: 'وضعیت فعلی: <span class="badge ' + statusClass(r.status) + '">' + A.esc(r.status_label) + '</span>'
      + (r.published_version ? ' · کاربران نسخه‌ی <b>' + r.published_version + '</b> را می‌بینند' : ' · هنوز منتشر نشده') }));
    p.appendChild(top);
    if (S.dirty) p.appendChild(el('div', { class: 'alert warn', text: 'تغییرات ذخیره نشده دارید؛ پیش از انتشار «ذخیره» را بزنید.' }));
    var s1 = section('بررسی پیش از انتشار', 'منبع، فیلدها، فرمول‌ها، تجمیع‌ها، فیلترها، نمودارها، دسترسی، اجرای کوئری و ساخت خروجی آزمایشی بررسی می‌شوند.');
    var vbox = el('div', {});
    s1.appendChild(btn('🔍 بررسی کن', async function () {
      vbox.innerHTML = '<div class="loading">در حال بررسی</div>';
      try {
        var res = await A.api.post(API + '/validate', { definition: S.def, report_id: r.id });
        S.validation = res.data; drawValidation(vbox);
      } catch (err) { vbox.innerHTML = ''; A.toast(err.message, 'error'); }
    }, 'btn-primary btn-sm'));
    s1.appendChild(vbox);
    if (S.validation) drawValidation(vbox);
    p.appendChild(s1);

    var s2 = section('چرخه‌ی عمر', 'پیش‌نویس ← در حال آزمایش ← منتشرشده ← بایگانی. انتشار نسخه‌ی کاری را قفل می‌کند؛ ویرایش بعدی نسخه‌ی تازه می‌سازد و کاربران تا انتشار دوباره نسخه‌ی قبلی را می‌بینند.');
    var acts = el('div', { class: 'rb-inline' });
    var flow = { draft: ['testing', 'published', 'archived'], testing: ['draft', 'published', 'archived'], published: ['testing', 'draft', 'archived'], archived: ['draft'] }[r.status] || [];
    var LABEL = { draft: '↩ پیش‌نویس', testing: '🧪 در حال آزمایش', published: '🚀 انتشار نسخه‌ی کاری', archived: '🗄 بایگانی' };
    flow.forEach(function (st) {
      acts.appendChild(btn(LABEL[st], async function () {
        if (S.dirty) { A.toast('اول تغییرات را ذخیره کنید.', 'warn'); return; }
        try {
          var res = await A.api.post(API + '/reports/' + r.id + '/status', { status: st });
          await afterSave(res.data);
          A.toast(st === 'published' ? 'گزارش منتشر شد.' : 'وضعیت تغییر کرد.', 'success');
        } catch (err) {
          if (err.payload && err.payload.validation) { S.validation = err.payload.validation; renderStep(); }
          A.toast(err.message, 'error');
        }
      }, st === 'published' ? 'btn-success btn-sm' : 'btn-ghost btn-sm'));
    });
    if (r.status === 'published' && r.latest_version !== r.published_version) {
      acts.appendChild(btn('🚀 انتشار نسخه‌ی ' + r.latest_version, async function () {
        if (S.dirty) { A.toast('اول تغییرات را ذخیره کنید.', 'warn'); return; }
        try { var res = await A.api.post(API + '/reports/' + r.id + '/publish'); await afterSave(res.data); A.toast('نسخه‌ی جدید منتشر شد.', 'success'); }
        catch (err) { if (err.payload && err.payload.validation) { S.validation = err.payload.validation; renderStep(); } A.toast(err.message, 'error'); }
      }, 'btn-success btn-sm'));
    }
    s2.appendChild(acts);
    p.appendChild(s2);

    var s3 = section('تاریخچه‌ی نسخه‌ها');
    var vt = el('table', { class: 'rb-versions' });
    vt.innerHTML = '<thead><tr><th>نسخه</th><th>یادداشت</th><th>سازنده</th><th>زمان</th><th>وضعیت</th><th></th></tr></thead>';
    var vb = el('tbody', {});
    (r.versions || []).forEach(function (v) {
      var tr = el('tr', {});
      tr.innerHTML = '<td><b>' + v.number + '</b></td><td>' + A.esc(v.note || '') + '</td><td>' + A.esc(v.created_by || '') + '</td><td class="nowrap">'
        + A.esc(J && J.fromISO ? J.fromISO(v.updated_at) : (v.updated_at || '').replace('T', ' ').slice(0, 16)) + '</td><td>'
        + (v.published ? '<span class="badge ok">منتشرشده</span>' : v.frozen ? '<span class="badge muted">قفل</span>' : '<span class="badge warn">کاری</span>') + '</td>';
      var td = el('td', { class: 'nowrap' });
      td.appendChild(btn('خلاصه', async function () {
        try {
          var res = await A.api.get(API + '/reports/' + r.id + '/versions/' + v.id);
          var s = res.data.summary;
          await A.confirmDialog({ title: 'نسخه ' + v.number, danger: false, confirmText: 'بستن',
            message: 'منبع: ' + (s.source || '') + ' | فیلترها: ' + ((s.filters || []).join(' و ') || '—') + ' | گروه‌بندی: ' + ((s.groups || []).join(' ← ') || '—')
              + ' | سنجه‌ها: ' + (s.measures || []).map(function (m) { return m.label; }).join('، ') + ' | فرمول‌ها: ' + (s.calcs || []).length });
        } catch (err) { A.toast(err.message, 'error'); }
      }, 'btn-ghost btn-xs'));
      if (!v.published || r.status !== 'published') {
        td.appendChild(btn('↺ بازگردانی', async function () {
          if (S.dirty && !(await A.confirmDialog({ message: 'تغییرات ذخیره نشده از بین می‌رود. ادامه؟' }))) return;
          try { var res = await A.api.post(API + '/reports/' + r.id + '/versions/' + v.id + '/restore'); await setReport(res.data); A.toast('نسخه ' + v.number + ' به‌عنوان نسخه‌ی کاری تازه بازگردانی شد.', 'success'); }
          catch (err) { A.toast(err.message, 'error'); }
        }, 'btn-ghost btn-xs', 'تعریف این نسخه را در نسخه‌ی کاری تازه‌ای باز می‌کند'));
      }
      if (v.frozen && !v.published) {
        td.appendChild(btn('🚀 انتشار دوباره', async function () {
          try { var res = await A.api.post(API + '/reports/' + r.id + '/versions/' + v.id + '/activate'); await afterSave(res.data); A.toast('نسخه ' + v.number + ' دوباره منتشر شد (Rollback).', 'success'); }
          catch (err) { A.toast(err.message, 'error'); }
        }, 'btn-ghost btn-xs', 'بازگشت کاربران به این نسخه'));
      }
      tr.appendChild(td);
      vb.appendChild(tr);
    });
    vt.appendChild(vb);
    s3.appendChild(el('div', { class: 'table-scroll' }, [vt]));
    var note = input('', function (v) { S.versionNote = v; }, { placeholder: 'یادداشت برای ذخیره‌ی بعدی (مثلاً: افزودن KPI تأخیر)' });
    s3.appendChild(fld('یادداشت نسخه', note));
    p.appendChild(s3);

    var s4 = section('اجرای زمان‌بندی‌شده', 'گزارش منتشرشده در زمان مقرر اجرا و نتیجه‌اش به‌صورت Snapshot نگه داشته می‌شود (مثلاً «گزارش ماهانه‌ی عملکرد»). کاربران Snapshotها را در صفحه‌ی خروجی می‌بینند.');
    (r.schedules || []).forEach(function (s) {
      var row = el('div', { class: 'rb-cond' });
      row.appendChild(el('b', { text: S.meta.frequencies[s.frequency] + ' — ساعت ' + s.hour }));
      row.appendChild(el('span', { class: 'muted small', text: 'اجرای بعدی: ' + (s.next_run_at || '—').replace('T', ' ').slice(0, 16) + (s.last_status ? ' · آخرین: ' + s.last_status : '') }));
      row.appendChild(check('فعال', s.is_active, async function (v) { try { await A.api.put(API + '/schedules/' + s.id, { is_active: v }); s.is_active = v; } catch (err) { A.toast(err.message, 'error'); } }));
      row.appendChild(btn('▶ اجرای الان', async function () {
        try { var res = await A.api.post(API + '/schedules/' + s.id + '/run'); A.toast(res.data.message, 'success'); Object.assign(s, res.data); renderStep(); }
        catch (err) { A.toast(err.message, 'error'); }
      }, 'btn-ghost btn-xs'));
      row.appendChild(btn('✕', async function () {
        try { await A.api.del(API + '/schedules/' + s.id); r.schedules = r.schedules.filter(function (x) { return x.id !== s.id; }); renderStep(); } catch (err) { A.toast(err.message, 'error'); }
      }, 'btn-ghost btn-xs rb-x'));
      s4.appendChild(row);
    });
    var freq = select(Object.keys(S.meta.frequencies).map(function (k) { return [k, S.meta.frequencies[k]]; }), 'monthly', function () {});
    var hour = el('input', { type: 'number', min: 0, max: 23, value: 7, class: 'rb-narrow' });
    s4.appendChild(el('div', { class: 'rb-inline' }, [freq, txt(' ساعت '), hour, btn('＋ زمان‌بندی', async function () {
      try {
        var res = await A.api.post(API + '/reports/' + r.id + '/schedules', { frequency: freq.value, hour: Number(hour.value) || 0 });
        r.schedules = (r.schedules || []).concat([res.data]); renderStep();
      } catch (err) { A.toast(err.message, 'error'); }
    }, 'btn-primary btn-sm')]));
    p.appendChild(s4);
  }
  function drawValidation(box) {
    var v = S.validation;
    box.innerHTML = '';
    box.appendChild(el('div', { class: 'alert ' + (v.ok ? 'ok' : 'error'), text: v.ok ? '✓ گزارش آماده‌ی انتشار است.' : '✕ پیش از انتشار این موارد را برطرف کنید.' }));
    var ul = el('ul', { class: 'rb-checks' });
    v.checks.forEach(function (c) {
      ul.appendChild(el('li', { class: c.ok ? 'ok' : (c.level === 'warning' ? 'warn' : 'bad'), text: (c.ok ? '✓ ' : c.level === 'warning' ? '⚠ ' : '✕ ') + c.text }));
    });
    box.appendChild(ul);
  }

  /* ═════════════════════════ preview & save ═════════════════════════ */
  async function preview() {
    if (!S.def || !S.def.source) return;
    var seq = ++S.previewSeq, started = Date.now();
    var msg = A.qs('#rb-preview-msg');
    msg.innerHTML = '<div class="loading small">در حال اجرا</div>';
    try {
      var res = await A.api.post(API + '/preview', { definition: S.def });
      if (seq !== S.previewSeq) return;
      msg.innerHTML = '';
      A.qs('#rb-preview-meta').textContent = res.data.row_count.toLocaleString('fa-IR') + ' ردیف · '
        + ((Date.now() - started) / 1000).toLocaleString('fa-IR', { maximumFractionDigits: 1 }) + ' ثانیه';
      RV.render(A.qs('#rb-preview'), S.def, res.data, {});
    } catch (err) {
      if (seq !== S.previewSeq) return;
      msg.innerHTML = '<div class="alert error">' + A.esc(err.message) + '</div>';
    }
  }

  async function afterSave(data) {
    var keepStep = S.step;
    S.report = data;
    S.def = data.definition;
    drawHeader(); setClean(); S.step = keepStep; renderStep();
    await loadReports();
  }

  async function save() {
    if (!S.report) return;
    var r = S.report, wasFrozen = r.version_frozen;
    try {
      var res = await A.api.put(API + '/reports/' + r.id, {
        name: r.name, description: r.description, category_id: r.category_id,
        scope_to_centers: r.scope_to_centers, definition: S.def, note: S.versionNote || null });
      S.versionNote = null;
      await afterSave(res.data);
      A.toast(wasFrozen ? 'ذخیره شد — نسخه‌ی کاری ' + res.data.latest_version + ' ساخته شد. کاربران تا انتشار، نسخه‌ی ' + (res.data.published_version || '—') + ' را می‌بینند.' : 'ذخیره شد.', 'success');
    } catch (err) { A.toast(err.message, 'error'); }
  }

  /* ═════════════════════════ categories & help ═════════════════════════ */
  function drawCats() {
    var box = A.qs('#rb-cat-list');
    box.innerHTML = '';
    if (!S.meta.categories.length) box.appendChild(el('div', { class: 'muted small', text: 'دسته‌ای نیست.' }));
    S.meta.categories.forEach(function (c) {
      var row = el('div', { class: 'rb-cond' });
      row.appendChild(input(c.name, A.debounce(async function (v) {
        try { await A.api.put(API + '/categories/' + c.id, { name: v }); c.name = v; } catch (err) { A.toast(err.message, 'error'); }
      }, 600)));
      row.appendChild(btn('✕', async function () {
        if (!(await A.confirmDialog({ message: 'دسته‌ی «' + c.name + '» حذف شود؟ گزارش‌های آن بدون دسته می‌شوند.' }))) { A.openModal('rb-cat-modal'); return; }
        try { await A.api.del(API + '/categories/' + c.id); S.meta.categories = S.meta.categories.filter(function (x) { return x.id !== c.id; }); drawCats(); A.openModal('rb-cat-modal'); }
        catch (err) { A.toast(err.message, 'error'); }
      }, 'btn-ghost btn-xs rb-x'));
      box.appendChild(row);
    });
  }
  function drawFunctions() {
    var box = A.qs('#rb-fn-list');
    box.innerHTML = '<p class="hint">فیلدها: <code>[نام فیلد]</code> — متن: <code>"متن"</code> — عملگرها: <code>+ - * / %</code> و مقایسه‌ی <code>= != &gt; &gt;= &lt; &lt;=</code>. تقسیم بر صفر یا مقدار خالی، نتیجه‌ی خالی می‌دهد.</p>';
    var t = el('table', { class: 'rb-fn-table' });
    t.innerHTML = '<thead><tr><th>تابع</th><th>شکل استفاده</th><th>نوع</th></tr></thead><tbody>'
      + S.meta.functions.map(function (f) {
        return '<tr><td class="mono">' + A.esc(f.name) + '</td><td class="mono" dir="ltr">' + A.esc(f.help) + '</td><td>' + (f.aggregate ? 'تجمیعی' : 'سطری') + '</td></tr>';
      }).join('') + '</tbody>';
    box.appendChild(t);
  }

  /* ═════════════════════════ boot ═════════════════════════ */
  document.addEventListener('DOMContentLoaded', async function () {
    try {
      S.meta = (await A.api.get(API + '/meta')).data;
    } catch (err) { A.toast(err.message, 'error'); return; }
    var sf = A.qs('#rb-status-filter');
    Object.keys(S.meta.statuses).forEach(function (k) { sf.appendChild(el('option', { value: k, text: S.meta.statuses[k] })); });
    sf.addEventListener('change', drawList);
    A.qs('#rb-search').addEventListener('input', A.debounce(drawList, 150));
    drawFunctions();
    await loadReports();

    A.qs('#rb-new').addEventListener('click', async function () {
      try {
        var res = await A.api.post(API + '/reports', { name: 'گزارش جدید', definition: { source: 'records' } });
        S.dirty = false; S.step = 'basics';
        await setReport(res.data); await loadReports();
        A.toast('گزارش ساخته شد؛ نام و منبع داده را تعیین کنید.', 'success');
      } catch (err) { A.toast(err.message, 'error'); }
    });
    A.qs('#rb-save').addEventListener('click', save);
    document.addEventListener('keydown', function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key === 's' && S.report) { e.preventDefault(); save(); }
    });
    A.qs('#rb-preview-btn').addEventListener('click', preview);
    A.qs('#rb-dup').addEventListener('click', async function () {
      try { var res = await A.api.post(API + '/reports/' + S.report.id + '/duplicate'); S.dirty = false; await setReport(res.data); await loadReports(); A.toast('کپی ساخته شد.', 'success'); }
      catch (err) { A.toast(err.message, 'error'); }
    });
    A.qs('#rb-open').addEventListener('click', function () { window.open('/reports?report=' + S.report.id + (S.report.status !== 'published' ? '&draft=1' : ''), '_blank'); });
    A.qs('#rb-del').addEventListener('click', async function () {
      var ok = await A.confirmDialog({ title: 'حذف گزارش', message: 'گزارش «' + S.report.name + '» با همه‌ی نسخه‌ها، دسترسی‌ها و Snapshotهایش حذف شود؟ این کار برگشت‌پذیر نیست.', confirmText: 'حذف' });
      if (!ok) return;
      try {
        await A.api.del(API + '/reports/' + S.report.id);
        S.report = null; S.def = null; S.dirty = false;
        A.qs('#rb-editor').classList.add('hidden'); A.qs('#rb-preview-pane').classList.add('hidden'); A.qs('#rb-empty').classList.remove('hidden');
        await loadReports(); A.toast('حذف شد.', 'success');
      } catch (err) { A.toast(err.message, 'error'); }
    });
    A.qs('#rb-cats').addEventListener('click', function () { drawCats(); A.openModal('rb-cat-modal'); });
    A.qs('#rb-cat-add').addEventListener('click', async function () {
      var name = A.qs('#rb-cat-name').value.trim();
      if (!name) return;
      try { var res = await A.api.post(API + '/categories', { name: name }); S.meta.categories.push(res.data); A.qs('#rb-cat-name').value = ''; drawCats(); if (S.step === 'basics' && S.report) renderStep(); }
      catch (err) { A.toast(err.message, 'error'); }
    });
    var id = new URLSearchParams(location.search).get('id');
    if (id) openReport(Number(id));
  });
})();
