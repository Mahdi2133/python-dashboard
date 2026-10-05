/* کاتالوگ پمپ: the models list, one model's curve and its editable table. */
(function () {
  'use strict';
  var A = window.App;
  var state = { models: [], types: [], current: null };
  var FIELDS = [
    ['motor_kw', 'توان الکتروموتور (kW)'], ['motor_hp', 'توان (HP)'], ['current_a', 'جریان نامی (A)'],
    ['motor_eff', 'راندمان الکتروموتور (%)'], ['weight_kg', 'وزن (kg)'],
    ['pump_length_mm', 'طول پمپ (mm)'], ['total_length_mm', 'طول مجموعه (mm)'],
    ['trim', 'قطر پروانه (مدل a)'], ['source', 'منبع'], ['note', 'توضیحات']
  ];
  function fa(n) { return window.Jalali ? window.Jalali.toFaDigits(n) : String(n); }
  function num(v) { return v === null || v === undefined ? '' : String(v); }

  async function load() {
    var all = A.qs('#cat-inactive').checked ? '&all=1' : '';
    var res = await A.api.get('/api/catalogue?points=0' + all);
    state.models = res.data.models;
    state.types = res.data.types;
    var sel = A.qs('#cat-type'), keep = sel.value;
    sel.innerHTML = '<option value="">همه‌ی تیپ‌ها</option>' + state.types.map(function (t) {
      return '<option value="' + A.esc(t) + '">' + A.esc(t) + '</option>';
    }).join('');
    sel.value = keep;
    drawList();
  }

  function drawList() {
    var t = A.qs('#cat-type').value, q = A.qs('#cat-search').value.trim().replace(/\s+/g, '');
    var rows = state.models.filter(function (m) {
      return (!t || m.pump_type === t) && (!q || m.full_title.replace(/\s+/g, '').indexOf(q) !== -1);
    });
    A.qs('#cat-count').textContent = fa(rows.length) + ' مدل';
    A.qs('#cat-list').innerHTML = rows.length ? rows.map(function (m) {
      return '<button type="button" class="cat-item' + (state.current && state.current.id === m.id ? ' active' : '')
        + (m.is_active ? '' : ' off') + '" data-id="' + m.id + '"><b dir="ltr">' + A.esc(m.title) + '</b>'
        + '<span class="hint">' + (m.motor_kw !== null ? A.esc(m.motor_kw) + ' kW' : '')
        + (m.current_a !== null ? ' · ' + A.esc(m.current_a) + ' A' : '')
        + (m.trim ? ' · ' + A.esc(m.trim) : '') + '</span></button>';
    }).join('') : '<div class="table-empty">مدلی پیدا نشد.</div>';
  }

  async function open(id) {
    var res = await A.api.get('/api/catalogue/' + id);
    state.current = res.data;
    drawList();
    drawDetail();
  }

  function pointRow(p) {
    p = p || {};
    return '<tr><td><input type="text" inputmode="decimal" dir="ltr" class="pt-q" value="' + A.esc(num(p.q_m3h)) + '"></td>'
      + '<td class="pt-ls mono">' + (p.q_m3h !== undefined && p.q_m3h !== null ? (Math.round(p.q_m3h / 3.6 * 100) / 100) : '') + '</td>'
      + '<td><input type="text" inputmode="decimal" dir="ltr" class="pt-h" value="' + A.esc(num(p.head)) + '"></td>'
      + '<td><input type="text" inputmode="decimal" dir="ltr" class="pt-e" value="' + A.esc(num(p.pump_eff)) + '"></td>'
      + '<td><button type="button" class="btn-sm btn-del pt-del" title="حذف نقطه">✕</button></td></tr>';
  }

  function drawDetail() {
    var m = state.current, box = A.qs('#cat-detail');
    if (!m) { box.innerHTML = '<div class="table-empty">یک مدل را از فهرست انتخاب کنید.</div>'; return; }
    var canEdit = A.can('form.manage');
    box.innerHTML = '<div class="page-head"><div><h2 style="font-size:17px" dir="ltr">' + A.esc(m.full_title) + '</h2>'
      + '<div class="sub">' + A.esc(m.brand) + ' · تیپ ' + A.esc(m.pump_type) + ' · ' + A.esc(m.stages) + ' طبقه'
      + (m.is_active ? '' : ' · <span class="badge muted">غیرفعال</span>') + '</div></div>'
      + '<div class="toolbar-actions"><label class="small"><input type="checkbox" id="cm-active" style="width:auto"'
      + (m.is_active ? ' checked' : '') + '> فعال</label></div></div>'
      + '<div class="form-chart" id="cm-chart" style="height:320px"></div>'
      + '<div class="field-group cols-4 mt-1">' + FIELDS.map(function (f) {
        return '<div class="field"><label>' + A.esc(f[1]) + '</label><input type="text" id="cm-' + f[0] + '" value="'
          + A.esc(num(m[f[0]])) + '"' + (['trim', 'source', 'note'].indexOf(f[0]) === -1 ? ' dir="ltr" inputmode="decimal"' : '') + '></div>';
      }).join('') + '</div>'
      + '<div class="section-title mt-1">نقاط منحنی</div>'
      + '<div class="table-scroll"><table class="cat-points"><thead><tr><th>دبی (m³/h)</th><th>دبی (l/s)</th>'
      + '<th>هد (m)</th><th>راندمان پمپ (%)</th><th></th></tr></thead><tbody id="cm-points">'
      + m.points.map(pointRow).join('') + '</tbody></table></div>'
      + (canEdit ? '<div class="modal-actions"><button class="btn-ghost" id="cm-add-pt" type="button">➕ نقطه</button>'
        + '<button class="btn-primary" id="cm-save" type="button">ذخیره</button></div>' : '');
    if (!canEdit) A.qsa('input', box).forEach(function (i) { i.disabled = true; });
    drawCurve(m.points);
  }

  function readPoints() {
    return A.qsa('#cm-points tr').map(function (tr) {
      return { q_m3h: A.qs('.pt-q', tr).value.trim(), head: A.qs('.pt-h', tr).value.trim(),
               pump_eff: A.qs('.pt-e', tr).value.trim() };
    }).filter(function (p) { return p.q_m3h !== '' || p.head !== ''; });
  }

  function drawCurve(points) {
    var box = A.qs('#cm-chart');
    if (!box) return;
    var hq = [], eq = [];
    points.forEach(function (p) {
      var q = Number(p.q_m3h), h = Number(p.head), e = p.pump_eff === '' || p.pump_eff === null ? null : Number(p.pump_eff);
      if (isNaN(q) || isNaN(h)) return;
      hq.push([Math.round(q / 3.6 * 100) / 100, h]);
      if (e !== null && !isNaN(e)) eq.push([Math.round(q / 3.6 * 100) / 100, e]);
    });
    hq.sort(function (a, b) { return a[0] - b[0]; });
    eq.sort(function (a, b) { return a[0] - b[0]; });
    window.FormEngine.loadEcharts().then(function (ec) {
      var chart = box._chart || (box._chart = ec.init(box));
      chart.setOption({
        textStyle: { fontFamily: 'Vazirmatn, Tahoma, sans-serif' },
        tooltip: { trigger: 'axis' },
        legend: { top: 0 },
        grid: { left: 56, right: 56, top: 40, bottom: 44 },
        xAxis: { type: 'value', name: 'دبی (l/s)', nameLocation: 'middle', nameGap: 26, min: 0 },
        yAxis: [{ type: 'value', name: 'هد (m)' },
                { type: 'value', name: 'راندمان (%)', max: 100, splitLine: { show: false } }],
        series: [
          { name: 'هد–دبی', type: 'line', smooth: true, data: hq, symbolSize: 7, itemStyle: { color: '#2563eb' } },
          { name: 'راندمان پمپ', type: 'line', smooth: true, data: eq, yAxisIndex: 1, symbolSize: 5,
            lineStyle: { type: 'dashed' }, itemStyle: { color: '#16a34a' } }
        ]
      }, true);
      chart.resize();
    });
  }

  async function save() {
    var m = state.current, data = { points: readPoints(), is_active: A.qs('#cm-active').checked };
    FIELDS.forEach(function (f) { data[f[0]] = A.qs('#cm-' + f[0]).value.trim(); });
    try {
      var res = await A.api.put('/api/catalogue/' + m.id, data);
      state.current = res.data;
      A.toast('مدل ' + res.data.title + ' ذخیره شد.', 'success');
      await load();
      drawDetail();
    } catch (err) { A.toast(err.message, 'error'); }
  }

  async function addModel() {
    var t = window.prompt('تیپ پمپ (مثلاً 384):');
    if (!t) return;
    var s = window.prompt('تعداد طبقات (مثلاً 10 یا 3a):');
    if (!s) return;
    try {
      var res = await A.api.post('/api/catalogue', { pump_type: t, stages: s });
      await load();
      open(res.data.id);
    } catch (err) { A.toast(err.message, 'error'); }
  }

  document.addEventListener('DOMContentLoaded', function () {
    load().catch(function (err) { A.toast(err.message, 'error'); });
    A.qs('#cat-type').addEventListener('change', drawList);
    A.qs('#cat-search').addEventListener('input', drawList);
    A.qs('#cat-inactive').addEventListener('change', load);
    A.qs('#cat-list').addEventListener('click', function (e) {
      var b = e.target.closest('[data-id]');
      if (b) open(Number(b.dataset.id));
    });
    A.qs('#cat-detail').addEventListener('click', function (e) {
      if (e.target.id === 'cm-save') save();
      if (e.target.id === 'cm-add-pt') A.qs('#cm-points').insertAdjacentHTML('beforeend', pointRow());
      if (e.target.classList.contains('pt-del')) { e.target.closest('tr').remove(); drawCurve(readPoints()); }
    });
    A.qs('#cat-detail').addEventListener('input', function (e) {
      if (e.target.closest('#cm-points')) {
        var tr = e.target.closest('tr'), q = Number(A.qs('.pt-q', tr).value);
        A.qs('.pt-ls', tr).textContent = isNaN(q) || A.qs('.pt-q', tr).value === '' ? '' : Math.round(q / 3.6 * 100) / 100;
        drawCurve(readPoints());
      }
    });
    A.qs('#cat-add').addEventListener('click', addModel);
    A.qs('#cat-import').addEventListener('change', async function () {
      var file = this.files[0];
      if (!file) return;
      var form = new FormData();
      form.append('file', file);
      try {
        var res = await A.api.upload('/api/catalogue/import', form);
        A.toast('ورود کاتالوگ: ' + fa(res.data.added) + ' مدل جدید، ' + fa(res.data.updated) + ' مدل به‌روز شد.', 'success');
        await load();
      } catch (err) { A.toast(err.message, 'error'); }
      this.value = '';
    });
  });
})();
