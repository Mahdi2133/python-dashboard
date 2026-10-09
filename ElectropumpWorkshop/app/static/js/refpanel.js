/* What the reference databases know about one well — drawn on the
   «بانک‌های اطلاعاتی» page and beside the form in the کارتابل. */
(function () {
  'use strict';
  var A = window.App;

  function fa(v) { return window.Jalali ? window.Jalali.toFaDigits(v) : String(v); }
  function num(v, d) {
    if (v === null || v === undefined || v === '') return '—';
    var n = Number(v);
    if (isNaN(n)) return A.esc(String(v));
    var r = Math.round(n * Math.pow(10, d == null ? 2 : d)) / Math.pow(10, d == null ? 2 : d);
    return fa(r);
  }

  function chips(sources) {
    if (!sources || !sources.length) return '<span class="hint">در بانک‌ها اطلاعاتی برای این چاه نیست.</span>';
    return sources.map(function (s) {
      return '<span class="badge ok">' + A.esc(s.title) + (s.date ? ' — ' + A.esc(s.date) : '')
        + (s.count ? ' (' + fa(s.count) + ')' : '') + '</span>';
    }).join(' ');
  }

  function valuesGrid(labelled, keys) {
    var rows = (labelled || []).filter(function (x) { return !keys || keys.indexOf(x.key) !== -1; });
    if (!rows.length) return '';
    return '<dl class="kv rp-kv">' + rows.map(function (x) {
      var v = typeof x.value === 'number' ? num(x.value) : A.esc(String(x.value));
      return '<dt>' + A.esc(x.label) + '</dt><dd>' + v + (x.unit ? ' <span class="hint">' + A.esc(x.unit) + '</span>' : '') + '</dd>';
    }).join('') + '</dl>';
  }

  function pointsTable(t) {
    if (!t || !t.points || !t.points.length) return '';
    return '<div class="table-scroll" style="max-height:none"><table class="rp-table"><thead><tr><th>کارکرد</th><th>آبدهی (l/s)</th>'
      + '<th>سطح پویایی (m)</th><th>فشار (atm)</th><th>هد (m)</th><th>آمپر</th></tr></thead><tbody>'
      + t.points.map(function (p) {
        return '<tr' + (p.at_network ? ' class="rp-net"' : '') + '><td>' + A.esc(p.label || ('کارکرد ' + p.point_no)) + '</td>'
          + '<td>' + num(p.flow) + '</td><td>' + num(p.dynamic_level) + '</td><td>' + num(p.pressure) + '</td>'
          + '<td>' + num(p.head, 1) + '</td><td dir="ltr">' + A.esc(p.amps || '—') + '</td></tr>';
      }).join('') + '</tbody></table></div>';
  }

  function testsList(tests) {
    if (!tests || !tests.length) return '';
    return '<div class="table-scroll" style="max-height:220px"><table class="rp-table"><thead><tr><th>تاریخ</th>'
      + '<th>تیپ الکتروپمپ</th><th>عمق نصب</th><th>سطح ایستایی</th><th>آبدهی شبکه</th><th>فشار</th></tr></thead><tbody>'
      + tests.map(function (t) {
        return '<tr><td>' + A.esc(t.test_date || '—') + '</td><td dir="ltr">' + A.esc(t.electropump || '—') + '</td>'
          + '<td>' + num(t.install_depth) + '</td><td>' + num(t.static_level) + '</td>'
          + '<td>' + num(t.net_flow) + '</td><td>' + num(t.net_pressure) + '</td></tr>';
      }).join('') + '</tbody></table></div>';
  }

  function videoList(rows) {
    if (!rows || !rows.length) return '';
    function ranges(list) {
      return (list || []).map(function (r) {
        return fa(r.from) + '–' + fa(r.to) + (r.sev ? ' (' + A.esc(r.sev) + ')' : '');
      }).join('، ');
    }
    return rows.map(function (v) {
      var bits = [];
      if ((v.repair || []).length) bits.push('ترمیم: ' + ranges(v.repair));
      if ((v.tear || []).length) bits.push('پارگی: ' + ranges(v.tear));
      if ((v.change || []).length) bits.push('تغییر جدار: ' + ranges(v.change));
      if ((v.clog || []).length) bits.push('گرفتگی مشبک: ' + ranges(v.clog));
      return '<div class="rp-video"><b>' + A.esc(v.insp_date || '—') + '</b> — عمق ' + num(v.depth)
        + ' m، سطح ایستابی ' + num(v.static_level) + ' m'
        + (v.screen_start != null ? '، شروع مشبک ' + num(v.screen_start) + ' m' : '')
        + (bits.length ? '<div class="hint">' + bits.join(' | ') + '</div>' : '')
        + (v.notes ? '<div class="hint">' + A.esc(v.notes) + '</div>' : '') + '</div>';
    }).join('');
  }

  function drawProduction(box, months) {
    if (!box || !months || !months.length || !window.FormEngine) return;
    var last = months.slice(-36);
    window.FormEngine.loadEcharts().then(function (ec) {
      var chart = ec.getInstanceByDom(box);
      if (!chart) {
        chart = ec.init(box);
        window.addEventListener('resize', function () { chart.resize(); });
      }
      chart.setOption({
        textStyle: { fontFamily: 'Vazirmatn, Tahoma' },
        tooltip: { trigger: 'axis' },
        legend: { top: 0, textStyle: { fontFamily: 'Vazirmatn' } },
        grid: { left: 50, right: 50, top: 40, bottom: 50 },
        xAxis: { type: 'category', data: last.map(function (m) { return m.year + '/' + (m.month < 10 ? '0' : '') + m.month; }),
                 axisLabel: { rotate: 45, fontSize: 10 } },
        yAxis: [{ type: 'value', name: 'دبی (l/s)' }, { type: 'value', name: 'فشار', position: 'right' }],
        series: [
          { name: 'دبی متوسط (l/s)', type: 'line', smooth: true, data: last.map(function (m) { return m.avg_flow; }),
            itemStyle: { color: '#2563eb' } },
          { name: 'فشار', type: 'line', yAxisIndex: 1, data: last.map(function (m) { return m.pressure; }),
            itemStyle: { color: '#d97706' }, lineStyle: { type: 'dashed' } }
        ]
      });
    }).catch(function () { box.innerHTML = ''; });
  }

  /* data: the /api/refdata/well answer */
  function render(container, data, opts) {
    opts = opts || {};
    var p = data.profile || { values: {}, sources: [] };
    if (!p.sources || !p.sources.length) {
      container.innerHTML = '<div class="hint">' + (opts.empty || 'در بانک‌های اطلاعاتی (دبی‌سنجی، روند تولید، ویدئومتری) داده‌ای برای این چاه پیدا نشد.') + '</div>';
      return;
    }
    var latest = (data.tests || [])[0];
    var best = ['best.electropump', 'best.well_depth', 'best.static_level', 'best.install_depth',
                'best.dynamic_level', 'best.operating_flow', 'best.last_install_date',
                'pr.last_flow_month', 'pr.avg_flow_12', 'ft.test_date', 'ft.net_flow', 'ft.net_pressure',
                'ft.design_flow', 'ft.discharge_pipe', 'ft.casing', 'ft.well_type', 'ft.starter',
                'ft.efficiency', 'vm.date', 'vm.screen_start'];
    var html = '<div class="rp-sources">' + chips(p.sources) + '</div>'
      + '<div class="rp-grid">'
      + '<div><div class="rp-h">خلاصه (مقادیری که فرم‌ها پیش‌پر می‌کنند)</div>' + valuesGrid(data.labelled, best) + '</div>'
      + (latest ? '<div><div class="rp-h">آخرین دبی‌سنجی — ' + A.esc(latest.test_date || '') + '</div>' + pointsTable(latest)
        + (latest.expert_opinion ? '<div class="hint mt-1">نظر کارشناس: ' + A.esc(latest.expert_opinion) + '</div>' : '') + '</div>' : '')
      + '</div>';
    if ((data.months || []).length) html += '<div class="rp-h mt-2">روند تولید (۳۶ ماه اخیر)</div><div class="rp-chart"></div>';
    if (!opts.compact) {
      if ((data.tests || []).length > 1) html += '<div class="rp-h mt-2">همه‌ی دبی‌سنجی‌ها</div>' + testsList(data.tests);
      if ((data.inspections || []).length) html += '<div class="rp-h mt-2">ویدئومتری</div>' + videoList(data.inspections);
      html += '<details class="mt-2"><summary>همه‌ی مقادیر بانک‌ها</summary>' + valuesGrid(data.labelled) + '</details>';
    } else if ((data.inspections || []).length) {
      html += '<div class="rp-h mt-2">آخرین ویدئومتری</div>' + videoList(data.inspections.slice(0, 1));
    }
    container.innerHTML = html;
    drawProduction(container.querySelector('.rp-chart'), data.months);
  }

  async function load(container, wellName, opts) {
    if (!wellName) { container.innerHTML = ''; return null; }
    container.innerHTML = '<div class="loading">بارگذاری</div>';
    try {
      var res = await A.api.get('/api/refdata/well?well=' + encodeURIComponent(wellName));
      render(container, res.data, opts);
      return res.data;
    } catch (err) {
      container.innerHTML = '<div class="hint">' + A.esc(err.message) + '</div>';
      return null;
    }
  }

  window.RefPanel = { render: render, load: load, pointsTable: pointsTable, num: num,
                     drawProduction: drawProduction };
})();
