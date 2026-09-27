/* ==========================================================================
   Report renderer — one module for the builder preview, the dashboard, the
   analysis page and snapshots, so a report looks the same everywhere.

   ReportView.render(container, cfg, result, opts)
     cfg    — the report's display definition: kpis, charts, tables, rules,
              layout, field_labels (from /view or the builder's definition)
     result — one run (/run, /preview or a snapshot)
     opts   — { onDrill(chart, key, label), onCrossFilter(field, value),
                compact }
   ReportView.chartImages() — {chart id: PNG data-URL}, for exports.

   Charts are ECharts, bundled under /static/vendor so the page works with
   no internet. Adding a chart type is one entry in BUILDERS.
   ========================================================================== */
(function (global) {
  'use strict';
  var A = global.App;
  var instances = {};           // chart id → echarts instance
  var PALETTE = ['#1f6fa5', '#f39c12', '#27ae60', '#c0392b', '#8e44ad', '#16a085',
    '#d35400', '#2c3e50', '#7f8c8d', '#e84393', '#00a8ff', '#b8860b'];
  var STYLE_CLASS = { ok: 'rv-ok', warn: 'rv-warn', bad: 'rv-bad', info: 'rv-info' };
  var STATUS_TEXT = { ok: 'مطلوب', warn: 'نزدیک هدف', bad: 'نامطلوب' };

  function esc(v) { return A.esc(v); }

  /* ── values ── */
  function num(v) {
    if (typeof v === 'number') return v;
    if (v === null || v === undefined || v === '' || typeof v === 'boolean') return null;
    var n = Number(String(v).replace(/,/g, ''));
    return isNaN(n) ? null : n;
  }
  function fmt(v, col) {
    col = col || {};
    if (v === null || v === undefined || v === '') return '—';
    if (v === true) return 'بله';
    if (v === false) return 'خیر';
    if (Array.isArray(v)) return v.map(function (x) { return fmt(x); }).join('، ');
    if (typeof v === 'number') {
      var dec = col.decimals;
      if (dec === null || dec === undefined || dec === '') dec = Number.isInteger(v) ? 0 : 2;
      var text = v.toLocaleString('fa-IR', { minimumFractionDigits: 0,
        maximumFractionDigits: Number(dec) });
      if (col.format === 'percent') text += '٪';
      if (col.unit) text += ' ' + col.unit;
      return text;
    }
    return String(v);
  }

  /* The same test as rule_style() on the server. */
  function ruleStyle(rules, target, value) {
    for (var i = 0; i < (rules || []).length; i++) {
      var r = rules[i];
      if (r.target !== target && r.target !== '*') continue;
      var v = num(value), t = num(r.value), op = r.operator || '>', ok = false;
      if (v !== null && t !== null) {
        ok = { '>': v > t, '>=': v >= t, '<': v < t, '<=': v <= t, '=': v === t, '!=': v !== t }[op];
      } else if (op === '=' || op === '!=') {
        ok = (String(value) === String(r.value)) === (op === '=');
      } else if (op === 'contains') {
        ok = String(value || '').indexOf(String(r.value)) >= 0;
      }
      if (ok) return r;
    }
    return null;
  }

  /* ── KPI cards ── */
  function kpiCard(k, cfgKpi) {
    cfgKpi = cfgKpi || {};
    var col = { format: k.format, decimals: k.decimals, unit: k.unit };
    var card = A.el('div', { class: 'rv-kpi ' + (STYLE_CLASS[k.status] || '') });
    if (k.color) card.style.borderInlineStartColor = k.color;
    if (k.error) {
      card.innerHTML = '<div class="rv-kpi-title">' + esc(k.title) + '</div>'
        + '<div class="rv-err">⚠ ' + esc(k.error) + '</div>';
      return card;
    }
    var html = '<div class="rv-kpi-title">' + esc(cfgKpi.icon ? cfgKpi.icon + ' ' : '')
      + esc(k.title) + '</div><div class="rv-kpi-value">' + esc(fmt(k.value, col)) + '</div>';
    var meta = [];
    if (k.target !== null && k.target !== undefined && k.target !== '') {
      meta.push('هدف: ' + esc(fmt(num(k.target), col)));
    }
    if (k.status) meta.push('<b>' + esc(k.rule_label || STATUS_TEXT[k.status] || '') + '</b>');
    if (meta.length) html += '<div class="rv-kpi-meta">' + meta.join(' · ') + '</div>';
    if (k.progress !== undefined && k.progress !== null) {
      html += '<div class="rv-progress"><span style="width:' + Math.max(0, Math.min(100, k.progress))
        + '%"></span></div>';
    }
    if (k.change_pct !== undefined && k.change_pct !== null) {
      var up = k.change_pct > 0, same = k.change_pct === 0;
      var good = k.direction === 'lower' ? !up : up;
      html += '<div class="rv-kpi-change ' + (same ? '' : (good ? 'up' : 'down')) + '">'
        + (same ? '＝' : (up ? '▲' : '▼')) + ' ' + esc(Math.abs(k.change_pct).toLocaleString('fa-IR'))
        + '٪ نسبت به ' + esc(k.period_label || 'دوره') + ' قبل</div>';
    }
    card.innerHTML = html;
    if (k.trend && k.trend.length > 1) {
      var spark = A.el('div', { class: 'rv-spark' });
      card.appendChild(spark);
      setTimeout(function () {
        if (!global.echarts) return;
        var ch = global.echarts.init(spark, null, { renderer: 'canvas' });
        ch.setOption({
          grid: { left: 2, right: 2, top: 4, bottom: 2 },
          xAxis: { type: 'category', show: false, data: k.trend.map(function (t) { return t.label; }) },
          yAxis: { type: 'value', show: false, scale: true },
          tooltip: { trigger: 'axis', textStyle: { fontFamily: 'Vazirmatn' } },
          series: [{ type: 'line', data: k.trend.map(function (t) { return t.value; }),
            smooth: true, symbol: 'none', lineStyle: { width: 2, color: '#1f6fa5' },
            areaStyle: { color: 'rgba(31,111,165,.12)' } }]
        });
      }, 0);
    }
    return card;
  }

  /* ── charts ── */
  var BASE_TEXT = { fontFamily: 'Vazirmatn, Tahoma, sans-serif' };

  function axisLabels(cats) {
    var rotate = cats.length > 8 ? 35 : 0;
    return { rotate: rotate, interval: cats.length > 30 ? 'auto' : 0,
      formatter: function (v) { v = String(v); return v.length > 16 ? v.slice(0, 15) + '…' : v; } };
  }

  function labelOpt(def) {
    return def.show_labels ? { show: true, position: 'top', fontSize: 10,
      formatter: function (p) { return fmt(num(p.value)); } } : { show: false };
  }

  function categorical(data, def, horizontal, stacked, kind) {
    var cats = data.categories || [];
    var series = (data.series || []).map(function (s, i) {
      var o = { name: s.name, type: kind || 'bar', data: s.data, label: labelOpt(def),
        emphasis: { focus: 'series' } };
      if (stacked) o.stack = 'total';
      if (kind === 'line') { o.smooth = !!def.smooth; o.symbolSize = 6; }
      if (def.area || kind === 'area') { o.type = 'line'; o.areaStyle = { opacity: .25 }; o.smooth = true; }
      if (horizontal && o.label.show) o.label.position = 'right';
      return o;
    });
    var catAxis = { type: 'category', data: cats, axisLabel: axisLabels(cats),
      inverse: horizontal };
    var valAxis = { type: 'value', axisLabel: { formatter: function (v) { return fmt(v); } } };
    return {
      legend: { show: series.length > 1, top: 0, type: 'scroll' },
      grid: { left: 12, right: 12, top: series.length > 1 ? 34 : 18, bottom: 8, containLabel: true },
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      xAxis: horizontal ? valAxis : catAxis,
      yAxis: horizontal ? catAxis : valAxis,
      dataZoom: cats.length > 40 ? [{ type: 'slider', height: 14, bottom: 0 }] : undefined,
      series: series
    };
  }

  function pie(data, def, donut) {
    var s = (data.series || [])[0] || { data: [] };
    return {
      legend: { type: 'scroll', orient: 'vertical', right: 0, top: 'middle' },
      tooltip: { trigger: 'item', formatter: function (p) {
        return esc(p.name) + '<br><b>' + fmt(num(p.value)) + '</b> (' + p.percent + '٪)'; } },
      series: [{ type: 'pie', radius: donut ? ['42%', '70%'] : '68%', center: ['40%', '52%'],
        data: (data.categories || []).map(function (c, i) { return { name: c, value: s.data[i] }; }),
        label: { show: def.show_labels !== false, position: 'inside', formatter: '{d}٪', fontSize: 10, color: '#fff' },
        itemStyle: { borderColor: '#fff', borderWidth: 1 } }]
    };
  }

  function pareto(data, def) {
    var s = (data.series || [])[0] || { data: [] };
    var vals = s.data.map(function (v) { return num(v) || 0; });
    var total = vals.reduce(function (a, b) { return a + b; }, 0) || 1, run = 0;
    var cum = vals.map(function (v) { run += v; return Math.round(run / total * 1000) / 10; });
    var o = categorical(data, def, false, false, 'bar');
    o.yAxis = [o.yAxis, { type: 'value', max: 100, axisLabel: { formatter: '{value}٪' } }];
    o.series.push({ name: 'درصد تجمعی', type: 'line', yAxisIndex: 1, data: cum, smooth: true,
      symbolSize: 5, lineStyle: { color: '#c0392b' }, itemStyle: { color: '#c0392b' } });
    o.legend = { show: true, top: 0 };
    o.grid.top = 34;
    return o;
  }

  function scatter(data, def) {
    var bubble = data.type === 'bubble';
    var sizes = data.points.map(function (p) { return p[2] || 0; });
    var maxSize = Math.max.apply(null, sizes.concat([1]));
    return {
      grid: { left: 12, right: 18, top: 18, bottom: 26, containLabel: true },
      tooltip: { trigger: 'item', formatter: function (p) {
        return esc(data.x_label) + ': ' + fmt(p.value[0]) + '<br>' + esc(data.y_label) + ': ' + fmt(p.value[1]); } },
      xAxis: { type: 'value', name: data.x_label, nameLocation: 'middle', nameGap: 24, scale: true },
      yAxis: { type: 'value', name: data.y_label, scale: true },
      series: [{ type: 'scatter', data: data.points,
        symbolSize: bubble ? function (v) { return 6 + 30 * ((v[2] || 0) / maxSize); } : 7,
        itemStyle: { opacity: .7 } }]
    };
  }

  function histogram(data) {
    var bins = data.bins || [];
    return {
      grid: { left: 12, right: 12, top: 18, bottom: 8, containLabel: true },
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'category', data: bins.map(function (b) { return b.label; }), axisLabel: axisLabels(bins) },
      yAxis: { type: 'value' },
      series: [{ type: 'bar', data: bins.map(function (b) { return b.value; }), barCategoryGap: '2%',
        name: data.value_label }]
    };
  }

  function box(data) {
    var boxes = (data.boxes || []).filter(function (b) { return b.stats; });
    return {
      grid: { left: 12, right: 12, top: 18, bottom: 8, containLabel: true },
      tooltip: { trigger: 'item', formatter: function (p) {
        var s = p.value.slice(-5);
        return esc(p.name) + '<br>کمینه: ' + fmt(s[0]) + '<br>چارک اول: ' + fmt(s[1])
          + '<br>میانه: ' + fmt(s[2]) + '<br>چارک سوم: ' + fmt(s[3]) + '<br>بیشینه: ' + fmt(s[4]); } },
      xAxis: { type: 'category', data: boxes.map(function (b) { return b.label; }), axisLabel: axisLabels(boxes) },
      yAxis: { type: 'value', scale: true },
      series: [{ type: 'boxplot', data: boxes.map(function (b) { return b.stats; }) }]
    };
  }

  function heatmap(data) {
    var cats = data.categories || [], series = data.series || [], cells = [], max = 0;
    series.forEach(function (s, yi) {
      (s.data || []).forEach(function (v, xi) {
        var n = num(v);
        if (n !== null) { cells.push([xi, yi, n]); max = Math.max(max, n); }
      });
    });
    return {
      grid: { left: 12, right: 12, top: 10, bottom: 50, containLabel: true },
      tooltip: { position: 'top', formatter: function (p) {
        return esc(cats[p.value[0]]) + ' × ' + esc(series[p.value[1]].name) + ': <b>' + fmt(p.value[2]) + '</b>'; } },
      xAxis: { type: 'category', data: cats, axisLabel: axisLabels(cats), splitArea: { show: true } },
      yAxis: { type: 'category', data: series.map(function (s) { return s.name; }), splitArea: { show: true } },
      visualMap: { min: 0, max: max || 1, calculable: true, orient: 'horizontal', left: 'center', bottom: 0,
        itemHeight: 90, inRange: { color: ['#eaf3fa', '#1f6fa5', '#0a3d62'] } },
      series: [{ type: 'heatmap', data: cells, label: { show: cells.length < 150, fontSize: 9,
        formatter: function (p) { return fmt(p.value[2]); } } }]
    };
  }

  function radar(data) {
    var cats = data.categories || [], series = data.series || [];
    var max = 0;
    series.forEach(function (s) { (s.data || []).forEach(function (v) { max = Math.max(max, num(v) || 0); }); });
    return {
      legend: { show: series.length > 1, top: 0 },
      tooltip: {},
      radar: { indicator: cats.map(function (c) { return { name: c, max: max * 1.1 || 1 }; }), radius: '62%' },
      series: [{ type: 'radar', data: series.map(function (s) {
        return { name: s.name, value: s.data, areaStyle: { opacity: .15 } }; }) }]
    };
  }

  function gauge(data, def) {
    var value = num(data.value) || 0;
    var max = num(data.max) || num(def.max) || (num(data.target) ? num(data.target) * 1.5 : Math.max(100, value * 1.3));
    return {
      series: [{ type: 'gauge', min: 0, max: max, progress: { show: true, width: 14 },
        axisLine: { lineStyle: { width: 14 } }, axisLabel: { fontSize: 9, formatter: function (v) { return fmt(Math.round(v)); } },
        detail: { valueAnimation: true, fontSize: 20, formatter: function (v) { return fmt(v); }, offsetCenter: [0, '65%'] },
        title: { show: false },
        data: [{ value: value }] }]
    };
  }

  function builderFor(type) {
    return {
      bar: function (d, def) { return categorical(d, def, false, false, 'bar'); },
      column: function (d, def) { return categorical(d, def, false, false, 'bar'); },
      comparison: function (d, def) { return categorical(d, def, false, false, 'bar'); },
      hbar: function (d, def) { return categorical(d, def, true, false, 'bar'); },
      ranking: function (d, def) { return categorical(d, def, true, false, 'bar'); },
      line: function (d, def) { return categorical(d, def, false, false, 'line'); },
      trend_day: function (d, def) { return categorical(d, def, false, false, 'line'); },
      trend_week: function (d, def) { return categorical(d, def, false, false, 'line'); },
      trend_month: function (d, def) { return categorical(d, def, false, false, 'line'); },
      trend_year: function (d, def) { return categorical(d, def, false, false, 'line'); },
      area: function (d, def) { return categorical(d, def, false, !!def.stack, 'area'); },
      stacked_bar: function (d, def) { return categorical(d, def, true, true, 'bar'); },
      stacked_column: function (d, def) { return categorical(d, def, false, true, 'bar'); },
      pie: function (d, def) { return pie(d, def, false); },
      donut: function (d, def) { return pie(d, def, true); },
      pareto: pareto, scatter: scatter, bubble: scatter, histogram: histogram, box: box,
      heatmap: heatmap, radar: radar, gauge: gauge
    }[type];
  }

  function chartEmpty(d) {
    if (d.points) return !d.points.length;
    if (d.bins) return !d.bins.length;
    if (d.boxes) return !d.boxes.some(function (b) { return b.stats; });
    if (['kpi', 'gauge', 'progress'].indexOf(d.type) >= 0) return d.value === null || d.value === undefined;
    return !(d.categories && d.categories.length);
  }

  function chartCard(d, def, opts) {
    def = def || {};
    var card = A.el('div', { class: 'rv-chart' });
    card.appendChild(A.el('div', { class: 'rv-chart-title', text: def.title || 'نمودار' }));
    if (def.subtitle) card.appendChild(A.el('div', { class: 'rv-sub', text: def.subtitle }));
    if (d.error) {
      card.appendChild(A.el('div', { class: 'rv-err', text: '⚠ ' + d.error }));
      return card;
    }
    if (chartEmpty(d)) {
      card.appendChild(A.el('div', { class: 'rv-empty', text: 'داده‌ای برای این نمودار نیست' }));
      return card;
    }
    if (d.type === 'kpi' || d.type === 'progress') {
      var col = { format: def.format, decimals: def.decimals, unit: def.unit };
      var box = A.el('div', { class: 'rv-bignum' });
      box.innerHTML = '<b>' + esc(fmt(num(d.value), col)) + '</b>';
      var target = num(d.target) || num(def.target);
      if (d.type === 'progress' && target) {
        var pct = Math.max(0, Math.min(100, (num(d.value) || 0) / target * 100));
        box.innerHTML += '<div class="rv-progress big"><span style="width:' + pct + '%"></span></div>'
          + '<small>' + pct.toLocaleString('fa-IR', { maximumFractionDigits: 1 }) + '٪ از هدف '
          + esc(fmt(target, col)) + '</small>';
      } else if (target) {
        box.innerHTML += '<small>هدف: ' + esc(fmt(target, col)) + '</small>';
      }
      card.appendChild(box);
      return card;
    }
    var holder = A.el('div', { class: 'rv-canvas' + (def.height === 'lg' ? ' lg' : def.height === 'sm' ? ' sm' : '') });
    card.appendChild(holder);
    var build = builderFor(d.type);
    if (!build || !global.echarts) {
      card.appendChild(A.el('div', { class: 'rv-err', text: 'نوع نمودار پشتیبانی نمی‌شود: ' + d.type }));
      return card;
    }
    setTimeout(function () {
      var option = build(d, def);
      option.textStyle = BASE_TEXT;
      option.color = def.colors && def.colors.length ? def.colors : PALETTE;
      option.animationDuration = 400;
      var inst = global.echarts.init(holder, null, { renderer: 'canvas' });
      inst.setOption(option);
      instances[d.id] = inst;
      inst.on('click', function (p) {
        if (!p || p.componentType !== 'series') return;
        var idx = p.dataIndex, label = p.name;
        if (opts && opts.onChartClick) opts.onChartClick(def, d, idx, label, p);
      });
    }, 0);
    return card;
  }

  /* ── tables ── */
  function tableCard(t, def, rules, opts) {
    def = def || {};
    var card = A.el('div', { class: 'rv-table' });
    var head = A.el('div', { class: 'rv-table-head' });
    head.appendChild(A.el('div', { class: 'rv-chart-title',
      text: def.title || (t.id === '_main' ? 'جدول' : 'جدول') }));
    card.appendChild(head);
    if (t.error) {
      card.appendChild(A.el('div', { class: 'rv-err', text: '⚠ ' + t.error }));
      return card;
    }
    var cols = t.columns || [];
    var rows = (t.rows || []).slice();
    var state = { sort: null, dir: 1, q: '', page: 1, size: def.page_size || 25 };
    var search = null;
    if (t.kind === 'detail' && rows.length > 10) {
      search = A.el('input', { type: 'search', class: 'rv-search', placeholder: 'جستجو در جدول…' });
      head.appendChild(search);
    }
    var countNote = A.el('span', { class: 'muted small' });
    head.appendChild(countNote);
    var wrap = A.el('div', { class: 'table-scroll rv-scroll' });
    var table = A.el('table', { class: 'rv-grid' });
    wrap.appendChild(table);
    card.appendChild(wrap);
    var pager = A.el('div', { class: 'rv-pager' });
    card.appendChild(pager);

    function draw() {
      var data = rows;
      if (state.q) {
        var q = state.q;
        data = data.filter(function (r) {
          return cols.some(function (c) { return String(fmt(r[c.key])).indexOf(q) >= 0; });
        });
      }
      if (state.sort) {
        var k = state.sort;
        data = data.filter(function (r) { return !r._subtotal; }).slice().sort(function (a, b) {
          var x = a[k], y = b[k];
          var nx = num(x), ny = num(y);
          if (nx !== null && ny !== null) return (nx - ny) * state.dir;
          return String(x === null || x === undefined ? '' : x).localeCompare(String(y === null || y === undefined ? '' : y), 'fa') * state.dir;
        });
      }
      var pages = Math.max(1, Math.ceil(data.length / state.size));
      state.page = Math.min(state.page, pages);
      var slice = data.slice((state.page - 1) * state.size, state.page * state.size);
      var html = '<thead><tr>' + cols.map(function (c) {
        var arrow = state.sort === c.key ? (state.dir > 0 ? ' ▲' : ' ▼') : '';
        return '<th data-k="' + esc(c.key) + '">' + esc(c.label) + arrow + '</th>';
      }).join('') + '</tr></thead><tbody>';
      if (!slice.length) {
        html += '<tr><td class="table-empty" colspan="' + (cols.length || 1) + '">داده‌ای نیست</td></tr>';
      }
      slice.forEach(function (r, i) {
        var cls = r._subtotal ? ' class="rv-subtotal"' : '';
        var drillable = t.kind === 'grouped' && r._key && opts && opts.onRowClick && !r._subtotal;
        html += '<tr' + cls + (drillable ? ' data-row="' + ((state.page - 1) * state.size + i) + '" style="cursor:pointer"' : '') + '>';
        cols.forEach(function (c) {
          var st = (rules && rules.length) ? ruleStyle(rules, c.key, r[c.key]) : null;
          var style = st && st.color ? ' style="background:' + esc(st.color) + '"' : '';
          var klass = st ? ' class="' + (STYLE_CLASS[st.style] || '') + '"' : '';
          var title = st && st.label ? ' title="' + esc(st.label) + '"' : '';
          html += '<td' + klass + style + title + '>' + esc(fmt(r[c.key], c)) + '</td>';
        });
        html += '</tr>';
      });
      html += '</tbody>';
      if (t.total && Object.keys(t.total).length) {
        html += '<tfoot><tr>' + cols.map(function (c, i) {
          var has = Object.prototype.hasOwnProperty.call(t.total, c.key);
          return '<td>' + (has ? esc(fmt(t.total[c.key], c)) : (i === 0 ? 'جمع کل' : '')) + '</td>';
        }).join('') + '</tr></tfoot>';
      }
      table.innerHTML = html;
      countNote.textContent = (t.row_count !== undefined ? 'ردیف‌های داده: ' + fmt(t.row_count) + ' · ' : '')
        + 'سطرهای جدول: ' + fmt(data.length) + (t.truncated ? ' (بخشی نمایش داده شده)' : '');
      pager.innerHTML = '';
      if (pages > 1) {
        pager.appendChild(A.el('button', { class: 'btn-sm btn-ghost', type: 'button', text: '›',
          disabled: state.page <= 1 ? 'disabled' : null,
          onclick: function () { state.page--; draw(); } }));
        pager.appendChild(A.el('span', { text: 'صفحه ' + fmt(state.page) + ' از ' + fmt(pages) }));
        pager.appendChild(A.el('button', { class: 'btn-sm btn-ghost', type: 'button', text: '‹',
          disabled: state.page >= pages ? 'disabled' : null,
          onclick: function () { state.page++; draw(); } }));
      }
      A.qsa('th', table).forEach(function (th) {
        th.addEventListener('click', function () {
          var k = th.dataset.k;
          if (state.sort === k) state.dir = -state.dir; else { state.sort = k; state.dir = 1; }
          draw();
        });
      });
      A.qsa('tr[data-row]', table).forEach(function (tr) {
        tr.addEventListener('click', function () {
          var r = data[Number(tr.dataset.row)];
          opts.onRowClick(def, t, r);
        });
      });
    }
    if (search) search.addEventListener('input', A.debounce(function () {
      state.q = search.value.trim(); state.page = 1; draw(); }, 200));
    draw();
    return card;
  }

  /* ── layout ── */
  function defaultLayout(cfg) {
    var out = [];
    (cfg.kpis || []).forEach(function (k) { out.push({ ref: 'kpi:' + k.id, w: 3 }); });
    (cfg.charts || []).forEach(function (c) {
      out.push({ ref: 'chart:' + c.id, w: ['kpi', 'gauge', 'progress'].indexOf(c.type) >= 0 ? 3 : 6 });
    });
    var tables = (cfg.tables || []).length ? cfg.tables : [{ id: '_main' }];
    tables.forEach(function (t) { out.push({ ref: 'table:' + t.id, w: 12 }); });
    return out;
  }

  function byId(list) {
    var m = {};
    (list || []).forEach(function (x) { if (x && x.id !== undefined) m[x.id] = x; });
    return m;
  }

  function dispose() {
    Object.keys(instances).forEach(function (k) {
      try { instances[k].dispose(); } catch (e) { /* gone */ }
    });
    instances = {};
  }

  function render(container, cfg, result, opts) {
    opts = opts || {};
    dispose();
    container.innerHTML = '';
    if (!result) return;
    var kDef = byId(cfg.kpis), cDef = byId(cfg.charts), tDef = byId(cfg.tables);
    var kRes = byId(result.kpis), cRes = byId(result.charts), tRes = byId(result.tables);
    var layout = (cfg.layout && cfg.layout.length) ? cfg.layout : defaultLayout(cfg);
    var used = {};
    var grid = A.el('div', { class: 'rv-grid-layout' });
    container.appendChild(grid);
    function place(item) {
      var parts = String(item.ref || '').split(':'), kind = parts[0], id = parts.slice(1).join(':');
      var node = null;
      if (kind === 'kpi' && kRes[id]) node = kpiCard(kRes[id], kDef[id]);
      else if (kind === 'chart' && cRes[id]) node = chartCard(cRes[id], cDef[id], opts);
      else if (kind === 'table' && tRes[id]) node = tableCard(tRes[id], tDef[id], cfg.rules, opts);
      else if (kind === 'text') {
        node = A.el('div', { class: 'rv-text' });
        node.innerHTML = '<div class="rv-chart-title">' + esc(item.title || '') + '</div><p>'
          + esc(item.text || '').replace(/\n/g, '<br>') + '</p>';
      }
      if (!node) return;
      used[item.ref] = true;
      var cell = A.el('div', { class: 'rv-cell', style: 'grid-column: span ' + Math.max(1, Math.min(12, item.w || 6)) });
      cell.appendChild(node);
      grid.appendChild(cell);
    }
    layout.forEach(place);
    // anything the layout forgot still shows, at the end
    defaultLayout(cfg).forEach(function (item) { if (!used[item.ref]) place(item); });
    setTimeout(function () { resize(); }, 50);
  }

  function resize() {
    Object.keys(instances).forEach(function (k) {
      try { instances[k].resize(); } catch (e) { /* gone */ }
    });
  }
  global.addEventListener('resize', A.debounce(resize, 150));

  function chartImages() {
    var out = {};
    Object.keys(instances).forEach(function (k) {
      try {
        out[k] = instances[k].getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: '#fff' });
      } catch (e) { /* skip */ }
    });
    return out;
  }

  global.ReportView = { render: render, fmt: fmt, num: num, ruleStyle: ruleStyle,
    chartImages: chartImages, resize: resize, dispose: dispose, kpiCard: kpiCard,
    tableCard: tableCard, PALETTE: PALETTE };
})(window);
