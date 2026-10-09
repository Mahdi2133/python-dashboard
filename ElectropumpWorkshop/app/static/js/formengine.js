/* ==========================================================================
   The form engine shared by the data-entry page and the process کارتابل.

   Both draw the same fields from the same form-builder schema; only the shape
   of what they submit differs. Keeping one renderer means a field type added
   in the form builder appears in both places, and a fix to radio clearing or
   the well autocomplete is a fix in both.

   Every selector is scoped to the engine's own root element, so two engines
   can live on one page without fighting over field ids.
   ========================================================================== */
(function () {
  'use strict';
  var A = window.App, J = window.Jalali;

  /* Keys the record API takes at the top level rather than as dynamic values.
     The flat mode used by the workflow sends everything by field name and lets
     the server sort it out, so this only matters for the entry page. */
  var TAG_FIELDS = ['failure', 'workshop_opinion', 'desc_tags', 'install_relates_to'];

  /* ── the pump catalogue, read by CAT_* formulas and «کاتالوگ» chart curves ──
     Loaded once per page; flows are l/s, as on the server (catalogue/services). */
  var Catalogue = {
    data: null, loading: null,
    load: function () {
      if (Catalogue.data) return Promise.resolve(Catalogue.data);
      if (!Catalogue.loading) {
        Catalogue.loading = A.api.get('/api/catalogue/compact').then(function (res) {
          Catalogue.data = (res.data || {}).models || {};
          return Catalogue.data;
        }).catch(function () { Catalogue.data = {}; return Catalogue.data; });
      }
      return Catalogue.loading;
    },
    normType: function (v) {
      var t = String(v === null || v === undefined ? '' : v).trim().replace('٫', '.');
      var n = Number(t);
      return t !== '' && !isNaN(n) && Math.floor(n) === n ? String(n) : t.toUpperCase();
    },
    normStages: function (v) {
      var t = String(v === null || v === undefined ? '' : v).replace(/\s+/g, '')
        .replace(/[A-Z]/g, function (c) { return c.toLowerCase(); });
      var n = Number(t);
      return t !== '' && !isNaN(n) && Math.floor(n) === n ? String(n) : t;
    },
    model: function (type, stages) {
      if (Array.isArray(type)) type = type[0];
      if (Array.isArray(stages)) stages = stages[0];
      if (!Catalogue.data || type === null || type === undefined || type === ''
          || stages === null || stages === undefined || stages === '') return null;
      return Catalogue.data[Catalogue.normType(type) + '|' + Catalogue.normStages(stages)] || null;
    },
    interp: function (x, x1, y1, x2, y2) { return x2 === x1 ? y1 : y1 + (y2 - y1) * (x - x1) / (x2 - x1); },
    flowAtHead: function (m, h) {
      if (!m || h === null) return null;
      for (var i = 0; i + 1 < m.pts.length; i++) {
        var a = m.pts[i], b = m.pts[i + 1];
        if (Math.min(a[1], b[1]) - 1e-9 <= h && h <= Math.max(a[1], b[1]) + 1e-9)
          return Catalogue.interp(h, a[1], a[0], b[1], b[0]);
      }
      return null;
    },
    headAtFlow: function (m, q) {
      if (!m || q === null) return null;
      for (var i = 0; i + 1 < m.pts.length; i++) {
        var a = m.pts[i], b = m.pts[i + 1];
        if (a[0] - 1e-9 <= q && q <= b[0] + 1e-9) return Catalogue.interp(q, a[0], a[1], b[0], b[1]);
      }
      return null;
    },
    effAtFlow: function (m, q) {
      if (!m || q === null) return null;
      var pts = m.pts.filter(function (p) { return p[2] !== null && p[2] !== undefined; });
      for (var i = 0; i + 1 < pts.length; i++) {
        var a = pts[i], b = pts[i + 1];
        if (a[0] - 1e-9 <= q && q <= b[0] + 1e-9) return Catalogue.interp(q, a[0], a[2], b[0], b[2]);
      }
      return null;
    },
    call: function (name, args, toNum) {
      var m = Catalogue.model(args[0], args[1]);
      if (!m) return null;
      var x = toNum(args[2]);
      switch (name) {
        case 'CAT_Q': return Catalogue.flowAtHead(m, x);
        case 'CAT_H': return Catalogue.headAtFlow(m, x);
        case 'CAT_EFF': return Catalogue.effAtFlow(m, x);
        case 'CAT_KW': return m.kw;
        case 'CAT_A': return m.a;
        case 'CAT_MEFF': return m.motor_eff === null || m.motor_eff === undefined ? 90 : m.motor_eff;
        case 'CAT_TITLE': return m.full_title;
      }
      return null;
    }
  };

  function qfit(vals, wantA) {
    if (vals.length % 2) return null;
    var n = vals.length / 2, x2 = 0, x3 = 0, x4 = 0, yx = 0, yx2 = 0, k = 0;
    for (var q = 0; q < n; q++) {
      var x = vals[q], y = vals[n + q];
      if (x === null || x === 0 || y === null) continue;
      k++; x2 += x * x; x3 += x * x * x; x4 += x * x * x * x; yx += y * x; yx2 += y * x * x;
    }
    var det = x4 * x2 - x3 * x3;
    if (k < 2 || Math.abs(det) < 1e-12) return null;
    return wantA ? (yx2 * x2 - yx * x3) / det : (x4 * yx - x3 * yx2) / det;
  }
  var echartsLoading = null;
  function loadEcharts() {
    if (window.echarts) return Promise.resolve(window.echarts);
    if (echartsLoading) return echartsLoading;
    var me = document.querySelector('script[src*="js/formengine.js"]');
    var src = me ? me.getAttribute('src').replace(/js\/formengine\.js.*$/, 'vendor/echarts.min.js')
      : '/static/vendor/echarts.min.js';
    echartsLoading = new Promise(function (resolve, reject) {
      var tag = document.createElement('script');
      tag.src = src;
      tag.onload = function () { resolve(window.echarts); };
      tag.onerror = reject;
      document.head.appendChild(tag);
    });
    return echartsLoading;
  }
  function solve3(m, v) {
    /* Cramer's rule for the 3×3 normal equations of a full quadratic. */
    function det(a) {
      return a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1])
        - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
        + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]);
    }
    var d = det(m);
    if (Math.abs(d) < 1e-12) return null;
    return [0, 1, 2].map(function (k) {
      var c = m.map(function (row, r) { return row.map(function (x, j) { return j === k ? v[r] : x; }); });
      return det(c) / d;
    });
  }
  function fmtC(n) {
    var a = Math.abs(n);
    return String(a >= 100 ? Math.round(a * 100) / 100 : a >= 1 ? Math.round(a * 10000) / 10000
      : Number(a.toPrecision(4)));
  }
  function sgn(n, first) { return n < 0 ? (first ? '-' : ' - ') : (first ? '' : ' + '); }
  function fitTrend(kind, pts) {
    var xs = pts.map(function (q) { return q[0]; }), ys = pts.map(function (q) { return q[1]; });
    var n = pts.length;
    function S(f) { var t = 0; for (var q = 0; q < n; q++) t += f(xs[q], ys[q]); return t; }
    if (kind === 'poly2_0') {
      var flat = xs.concat(ys), a = qfit(flat, true), b = qfit(flat, false);
      if (a === null) return null;
      return { f: function (x) { return a * x * x + b * x; }, from0: true,
               eq: 'y = ' + sgn(a, true) + fmtC(a) + 'x²' + sgn(b) + fmtC(b) + 'x' };
    }
    if (kind === 'poly2' && n >= 3) {
      var c = solve3([[S(function (x) { return Math.pow(x, 4); }), S(function (x) { return Math.pow(x, 3); }), S(function (x) { return x * x; })],
                      [S(function (x) { return Math.pow(x, 3); }), S(function (x) { return x * x; }), S(function (x) { return x; })],
                      [S(function (x) { return x * x; }), S(function (x) { return x; }), n]],
                     [S(function (x, y) { return y * x * x; }), S(function (x, y) { return y * x; }), S(function (x, y) { return y; })]);
      if (!c) return null;
      return { f: function (x) { return c[0] * x * x + c[1] * x + c[2]; },
               eq: 'y = ' + sgn(c[0], true) + fmtC(c[0]) + 'x²' + sgn(c[1]) + fmtC(c[1]) + 'x' + sgn(c[2]) + fmtC(c[2]) };
    }
    if (kind === 'linear' && n >= 2) {
      var den = n * S(function (x) { return x * x; }) - Math.pow(S(function (x) { return x; }), 2);
      if (Math.abs(den) < 1e-12) return null;
      var m = (n * S(function (x, y) { return x * y; }) - S(function (x) { return x; }) * S(function (x, y) { return y; })) / den;
      var k = (S(function (x, y) { return y; }) - m * S(function (x) { return x; })) / n;
      return { f: function (x) { return m * x + k; }, eq: 'y = ' + sgn(m, true) + fmtC(m) + 'x' + sgn(k) + fmtC(k) };
    }
    if (kind === 'power') {
      var pp = pts.filter(function (q) { return q[0] > 0 && q[1] > 0; });
      if (pp.length < 2) return null;
      var lx = pp.map(function (q) { return Math.log(q[0]); }), ly = pp.map(function (q) { return Math.log(q[1]); });
      var N = pp.length, sx = 0, sy = 0, sxx = 0, sxy = 0;
      for (var q = 0; q < N; q++) { sx += lx[q]; sy += ly[q]; sxx += lx[q] * lx[q]; sxy += lx[q] * ly[q]; }
      var dd = N * sxx - sx * sx;
      if (Math.abs(dd) < 1e-12) return null;
      var kk = (N * sxy - sx * sy) / dd, AA = Math.exp((sy - kk * sx) / N);
      return { f: function (x) { return x > 0 ? AA * Math.pow(x, kk) : null; },
               eq: 'y = ' + fmtC(AA) + 'x^' + (kk < 0 ? '-' : '') + fmtC(kk) };
    }
    return null;
  }

  /* «384/10+73.5» — pump type / stages + motor kW; the one electropump format */
  function epumpPart(v) {
    if (Array.isArray(v)) v = v[0];
    if (v === null || v === undefined || v === '') return '';
    var t = String(v).replace(/[۰-۹]/g, function (d) { return '۰۱۲۳۴۵۶۷۸۹'.indexOf(d); }).replace('٫', '.').trim();
    var n = Number(t);
    return (t !== '' && !isNaN(n)) ? String(n) : t;
  }
  /* «384/10+73.5» (or «73.5+384/10», «384/10») → [type, stages, motor kW] */
  function epumpParse(text) {
    if (Array.isArray(text)) text = text[0];
    if (text === null || text === undefined || text === '') return [null, null, null];
    var s = String(text).replace(/[۰-۹]/g, function (d) { return '۰۱۲۳۴۵۶۷۸۹'.indexOf(d); })
      .replace(/٫/g, '.').replace(/[\s\u200c]/g, '');
    var m = s.match(/^(\d{2,4}[a-z]*)\/(\d+[a-z]?(?:\([^)]*\))?)\+(\d+(?:\.\d+)?)/i);
    if (m) return [m[1].toUpperCase(), m[2].toLowerCase(), Number(m[3])];
    m = s.match(/^(\d+(?:\.\d+)?)\+(\d{2,4}[a-z]*)\/(\d+[a-z]?)$/i);
    if (m) return [m[2].toUpperCase(), m[3].toLowerCase(), Number(m[1])];
    m = s.match(/^(\d{2,4}[a-z]*)\/(\d+[a-z]?)$/i);
    if (m) return [m[1].toUpperCase(), m[2].toLowerCase(), null];
    return [null, null, null];
  }
  function epumpLabel(type, stages, motor) {
    var t = epumpPart(type), s = epumpPart(stages), m = epumpPart(motor);
    if (!t) return null;
    return t + (s ? '/' + s : '') + (m ? '+' + m : '');
  }

  function toNumber(v) {
    if (v === null || v === undefined || v === '') return null;
    if (typeof v === 'number') return v;
    var t = String(v).replace(/[۰-۹]/g, function (d) { return '۰۱۲۳۴۵۶۷۸۹'.indexOf(d); })
      .replace('٫', '.').replace(/,/g, '');
    var n = Number(t);
    return isNaN(n) ? null : n;
  }
  /* «اقلام انبار»: the warehouse items and condition classes, read once. */
  var Warehouse = {
    data: null, _p: null,
    load: function () {
      if (Warehouse.data) return Promise.resolve(Warehouse.data);
      if (!Warehouse._p) {
        Warehouse._p = window.App.api.get('/api/warehouse/catalogue').then(function (res) {
          Warehouse.data = res.data; return res.data;
        }).catch(function () { Warehouse._p = null; return null; });
      }
      return Warehouse._p;
    }
  };

  /* One chart from its config and a reader of the form's values. Used by the
     live form and by the read-only summaries (the approver sees the same
     chart the sender drew). Series kinds:
       {label, x:[fields], y:[fields], axis, trend}   points typed in the form
       {label, catalogue:{type, stages}, x:'head'|'q', hide_same_as}
                                                     a model's curve from the
                                                     pump catalogue, picked by
                                                     the form's own answers */
  /* A formula evaluator for charts drawn outside a form (the summaries):
     the same language, from an engine with no fields of its own. */
  var staticEvaluator = null;
  function chartEvaluator(evaluate) {
    if (evaluate) return evaluate;
    if (!staticEvaluator) {
      staticEvaluator = new FormEngine({ root: document.createElement('div'),
                                         schema: { sections: [], lookups: {}, conditional: [] } }).evalFormula;
    }
    return staticEvaluator;
  }
  /* «منحنی از فرمول»: the formula with every [field] written as its number,
     [x] left as x — the equation of the curve that was drawn. */
  function curveEquation(formula, getValue) {
    return String(formula || '').replace(/\[([^\]]+)\]/g, function (m, ref) {
      ref = ref.trim();
      if (ref === 'x') return 'x';
      var n = toNumber(getValue(ref));
      return n === null ? m : (n < 0 ? '(' + '-' + fmtC(n) + ')' : fmtC(n));
    }).replace(/\s*\*\s*/g, '·').replace(/\s+/g, ' ');
  }

  function paintChart(ec, box, eqBox, cfg, getValue, evaluate) {
    var palette = ['#2563eb', '#dc2626', '#16a34a', '#d97706', '#7c3aed'];
    var series = [], eqs = [], notes = [], useRight = false, xmax = 0, keys = {}, curves = [];
    (cfg.series || []).forEach(function (sr, si) {
      var color = sr.color || palette[si % palette.length];
      var right = sr.axis === 'right';
      if (sr.catalogue) {
        var t = getValue(sr.catalogue.type), st = getValue(sr.catalogue.stages);
        var key = (t === null || t === undefined || t === '' || st === null || st === undefined || st === '')
          ? null : Catalogue.normType(Array.isArray(t) ? t[0] : t) + '|' + Catalogue.normStages(Array.isArray(st) ? st[0] : st);
        keys[si] = key;
        if (!key) return;
        if (sr.hide_same_as !== undefined && sr.hide_same_as !== null && keys[sr.hide_same_as] === key) {
          notes.push('<div class="hint">«' + A.esc(sr.label || '') + '» همان مدل «'
                     + A.esc(((cfg.series || [])[sr.hide_same_as] || {}).label || '') + '» است؛ یک منحنی رسم شد.</div>');
          return;
        }
        var m = Catalogue.model(t, st);
        if (!m) {
          notes.push('<div class="hint">مدل ' + A.esc(key.replace('|', '/')) + ' در کاتالوگ پمپ نیست.</div>');
          return;
        }
        var byHead = (sr.x || 'head') === 'head';
        var line = m.pts.map(function (pt) { return byHead ? [pt[1], pt[0]] : [pt[0], pt[1]]; })
          .sort(function (p1, p2) { return p1[0] - p2[0]; });
        line.forEach(function (pt) { if (pt[0] > xmax) xmax = pt[0]; });
        if (right) useRight = true;
        series.push({ name: (sr.label ? sr.label + ' — ' : '') + m.full_title, type: 'line', data: line,
                      yAxisIndex: right ? 1 : 0, symbolSize: 6, smooth: true,
                      lineStyle: { color: color, width: 2 }, itemStyle: { color: color } });
        return;
      }
      var pts = [], scale = Number(sr.scale) || 1;
      (sr.x || []).forEach(function (xn, k) {
        var x = toNumber(getValue(xn)), y = toNumber(getValue((sr.y || [])[k]));
        if (x === null || y === null || (x === 0 && y === 0)) return;
        pts.push([x, y]);
        if (x > xmax) xmax = x;
      });
      pts.sort(function (p1, p2) { return p1[0] - p2[0]; });
      /* «start»: a fixed first point — efficiency is 100% at zero flow, as the
         workbook draws it; «connect» joins the points instead of a trend */
      var shown = pts.slice();
      if (pts.length && Array.isArray(sr.start)) shown.unshift([Number(sr.start[0]), Number(sr.start[1])]);
      shown = shown.map(function (q) { return [q[0], Math.round(q[1] * scale * 10000) / 10000]; });
      if (right) useRight = true;
      series.push(sr.connect
        ? { name: sr.label || ('سری ' + (si + 1)), type: 'line', data: shown, smooth: true,
            yAxisIndex: right ? 1 : 0, symbolSize: 8, lineStyle: { color: color, width: 2 },
            itemStyle: { color: color } }
        : { name: sr.label || ('سری ' + (si + 1)), type: 'scatter', data: shown,
            yAxisIndex: right ? 1 : 0, symbolSize: 9, itemStyle: { color: color } });
      /* the curve a formula of x draws (efficiency = 100·b / (b + a·Q)) —
         drawn once every series is in, so it spans the whole x axis */
      if (sr.curve && sr.curve.y) curves.push({ sr: sr, color: color, right: right, pts: pts });
      if (sr.trend && !sr.connect && pts.length >= 2) {
        var fit = fitTrend(sr.trend, pts);
        if (fit) {
          var lo = fit.from0 ? 0 : pts[0][0], hi = pts[pts.length - 1][0];
          var span = (hi - lo) || hi || 1, tl = [];
          for (var q = 0; q <= 40; q++) {
            var x = lo + (span * 1.1) * q / 40, y = fit.f(x);
            if (y !== null && isFinite(y)) tl.push([Math.round(x * 10000) / 10000, Math.round(y * 10000) / 10000]);
          }
          series.push({ name: (sr.label || '') + ' — روند', type: 'line', data: tl, showSymbol: false,
                        yAxisIndex: right ? 1 : 0, lineStyle: { type: 'dashed', color: color, width: 1.5 },
                        itemStyle: { color: color } });
          eqs.push('<div style="color:' + color + '"><span>' + A.esc(sr.label || '') + ' — خط روند: </span>'
                   + '<span dir="ltr" class="mono">' + A.esc(fit.eq) + '</span></div>');
        }
      }
    });
    curves.forEach(function (c) {
      var ev = chartEvaluator(evaluate), cv = c.sr.curve;
      var lookup = function (xv) { return function (name) { return name === 'x' ? xv : getValue(name); }; };
      if (cv.require) {
        var ok = false;
        try { ok = truthy0(ev(cv.require, lookup(null))); } catch (e) { ok = false; }
        if (!ok) {
          if (c.pts.length || cv.note) {
            notes.push('<div class="hint chart-note" style="color:' + c.color + '">⚠ '
                       + A.esc(cv.note || ('«' + (c.sr.label || '') + '» با داده‌های فعلی رسم‌شدنی نیست.')) + '</div>');
          }
          return;
        }
      }
      var hi = Math.max(xmax, c.pts.length ? c.pts[c.pts.length - 1][0] : 0);
      if (!hi) return;
      /* the curve's formula carries its own units (100·… for a percentage) */
      var line = [];
      for (var q = 0; q <= 50; q++) {
        var xv = hi * 1.1 * q / 50, yv = null;
        try { yv = toNumber(ev(cv.y, lookup(xv))); } catch (e) { yv = null; }
        if (yv !== null && isFinite(yv)) line.push([Math.round(xv * 10000) / 10000, Math.round(yv * 10000) / 10000]);
      }
      if (line.length < 2) return;
      if (c.right) useRight = true;
      series.push({ name: (c.sr.label || '') + ' — منحنی', type: 'line', data: line, showSymbol: false, smooth: true,
                    yAxisIndex: c.right ? 1 : 0, lineStyle: { color: c.color, width: 2 }, itemStyle: { color: c.color } });
      eqs.push('<div style="color:' + c.color + '"><span>' + A.esc(c.sr.label || '') + ' — '
               + A.esc(cv.eq_label || 'معادله') + ': </span><span dir="ltr" class="mono">y = '
               + A.esc(curveEquation(cv.y, getValue)) + '</span></div>');
    });
    var yAxis = [{ type: 'value', name: cfg.y_label || '', max: cfg.y_max ? Number(cfg.y_max) : null,
                   position: 'left', nameTextStyle: { fontFamily: 'Vazirmatn' } }];
    if (useRight) {
      yAxis.push({ type: 'value', name: cfg.y2_label || '', max: cfg.y2_max ? Number(cfg.y2_max) : null,
                   position: 'right', splitLine: { show: false }, nameTextStyle: { fontFamily: 'Vazirmatn' } });
    }
    var chart = box._chart;
    if (chart && chart.getDom() !== box) { chart.dispose(); chart = null; }
    if (!chart) {
      chart = ec.init(box);
      box._chart = chart;
      window.addEventListener('resize', function () { chart.resize(); });
    }
    chart.setOption({
      textStyle: { fontFamily: 'Vazirmatn, Tahoma, sans-serif' },
      tooltip: { trigger: 'item', formatter: function (pr) {
        return A.esc(pr.seriesName) + '<br>' + (cfg.x_label || 'x') + ': ' + pr.value[0]
          + '<br>' + (cfg.y_label || 'y') + ': ' + pr.value[1];
      } },
      legend: { top: 0, textStyle: { fontFamily: 'Vazirmatn' } },
      grid: { left: 56, right: useRight ? 56 : 24, top: series.length > 3 ? 84 : 56, bottom: 48 },
      xAxis: { type: 'value', name: cfg.x_label || '', nameLocation: 'middle', nameGap: 28, min: 0,
               max: xmax ? niceMax(xmax * 1.1) : null },
      yAxis: yAxis,
      series: series,
    }, true);
    chart.resize();
    if (eqBox) {
      eqBox.innerHTML = (eqs.join('') + notes.join(''))
        || (series.some(function (sr) { return sr.data.length; }) ? '' : 'پس از ورود داده‌ها نمودار رسم می‌شود.');
    }
  }
  function truthy0(v) { return !(v === null || v === undefined || v === '' || v === 0 || v === false); }
  function niceMax(v) {
    /* a round end for the axis: 265.65 → 300, 1.32 → 1.5 */
    var step = Math.pow(10, Math.floor(Math.log10(v))) / 2;
    return Math.ceil(v / step) * step;
  }
  function chartUsesCatalogue(cfg) {
    return ((cfg || {}).series || []).some(function (sr) { return !!sr.catalogue; });
  }
  /* A read-only chart for summaries: values is {field_name: answer}. */
  function drawStaticChart(box, eqBox, cfg, values) {
    var get = function (name) { return values ? values[name] : null; };
    var go = function () {
      return loadEcharts().then(function (ec) { paintChart(ec, box, eqBox, cfg || {}, get); });
    };
    return chartUsesCatalogue(cfg) ? Catalogue.load().then(go) : go();
  }

  function FormEngine(options) {
    var root = options.root;
    var schema = options.schema;           // { sections, lookups, conditional }
    var flat = !!options.flat;             // workflow mode: one key per field
    var self = this;

    function qs(sel) { return A.qs(sel, root); }
    function qsa(sel) { return A.qsa(sel, root); }

    /* ── rendering ────────────────────────────────────────────────────── */
    function optionsFor(field) {
      if (field.own_options && field.own_options.length) return field.own_options;
      if (field.lookup_category) return (schema.lookups || {})[field.lookup_category] || [];
      return [];
    }
    self.optionsFor = optionsFor;

    function labelHtml(field) {
      return '<label for="fld-' + A.esc(field.field_name) + '">' + A.esc(field.label)
        + (field.is_required ? ' <span class="req">*</span>' : '') + '</label>';
    }

    function renderChoice(field, multiple) {
      var opts = optionsFor(field);
      var type = multiple ? 'checkbox' : 'radio';
      /* Say what to do with the row of buttons. Without it a long list of
         unselected options reads as a box that has not loaded — which is
         exactly how «علت خرابی» was misread. */
      var tick = multiple && opts.length === 1;      /* «انجام شد»: one tick, not a list */
      var html = '<div class="choice-help">'
        + (tick ? 'برای تیک زدن روی گزینه بزنید.'
           : multiple ? 'روی هر مورد بزنید تا انتخاب شود — <b>چند مورد</b> '
                      + 'قابل انتخاب است.'
                    : 'یکی از گزینه‌ها را انتخاب کنید.')
        + ' برای برداشتن، دوباره روی همان بزنید.'
        + '<span class="choice-count" data-count="' + A.esc(field.field_name)
        + '"></span></div>';
      /* No blank "—" button: an empty choice is not a choice. Clearing is done
         by clicking the selected option again. */
      html += '<div class="btn-group' + (opts.length > 14 ? ' compact' : '')
        + '" data-field="' + A.esc(field.field_name) + '">';
      opts.forEach(function (opt) {
        html += '<label><input type="' + type + '" name="' + A.esc(field.field_name)
          + '" value="' + A.esc(opt.value) + '"'
          + (opt.is_default ? ' checked' : '') + '>'
          + '<span class="btn-opt">' + (opt.icon ? A.esc(opt.icon) + ' ' : '')
          + A.esc(opt.label) + '</span></label>';
      });
      html += '</div>';
      if (field.allow_other) {
        html += '<input type="text" class="other-input" data-other="'
          + A.esc(field.field_name) + '" placeholder="سایر موارد (در فهرست نیست)...">';
      }
      return html;
    }

    function renderSelect(field) {
      var html = '<select id="fld-' + A.esc(field.field_name) + '" name="'
        + A.esc(field.field_name) + '"><option value="">—</option>';
      optionsFor(field).forEach(function (opt) {
        html += '<option value="' + A.esc(opt.value) + '">' + A.esc(opt.label) + '</option>';
      });
      return html + '</select>';
    }

    function renderInput(field) {
      var id = 'fld-' + A.esc(field.field_name);
      var attrs = ' id="' + id + '" name="' + A.esc(field.field_name) + '"';
      /* «مقدار پیش‌فرض» written as a formula: filled with its result while the
         user has not typed a value of their own */
      if (String(field.default_value || '').charAt(0) === '=') {
        attrs += ' data-autofill="' + A.esc(field.field_name) + '"';
        if (!field.placeholder) attrs += ' placeholder="خودکار از محاسبه — قابل ویرایش"';
      }
      if (field.placeholder) attrs += ' placeholder="' + A.esc(field.placeholder) + '"';
      if (field.max_length) attrs += ' maxlength="' + field.max_length + '"';
      /* «طبقات از کاتالوگ»: the type's models as one list — «384/10» */
      if (field.stages_of) {
        return '<select class="stages-pick" id="' + id + '" name="' + A.esc(field.field_name) + '"'
          + ' data-stages-of="' + A.esc(field.stages_of) + '"><option value="">— ابتدا تیپ پمپ یا مدل را انتخاب کنید —</option></select>';
      }
      switch (field.field_type) {
        case 'number':
          if (field.min_value !== null) attrs += ' min="' + field.min_value + '"';
          if (field.max_value !== null) attrs += ' max="' + field.max_value + '"';
          attrs += ' step="' + A.esc(field.step || 'any') + '"';
          return '<input type="number"' + attrs + '>';
        case 'textarea':
          return '<textarea' + attrs + '></textarea>';
        case 'date':
          return '<input type="date"' + attrs + '>';
        case 'jalali_date':
          return '<input type="text" class="jdate"' + attrs + '>';
        case 'autocomplete':
          return '<div class="autocomplete-wrapper">'
            + '<input type="text" autocomplete="off" data-autocomplete="'
            + A.esc(field.lookup_category || 'wells') + '"' + attrs + '>'
            + '<div class="autocomplete-list"></div></div>';
        default:
          return '<input type="text"' + attrs + '>';
      }
    }

    /* A checklist: one item per line with a box to tick, and — when it is
       being shown rather than filled — the same lines with what was ticked
       already marked. Reading «۷ مورد از ۱۲» off a row of buttons is the
       thing this type exists to avoid. */
    function renderChecklist(field, locked) {
      var items = optionsFor(field);
      if (!items.length) {
        return '<div class="hint">برای این چک‌لیست موردی تعریف نشده است.</div>';
      }
      var done = [];
      if (locked) {
        var raw = field.read_only_value;
        done = Array.isArray(raw) ? raw.map(String)
          : String(raw == null ? '' : raw).split(/[،,]/)
              .map(function (x) { return x.trim(); }).filter(Boolean);
      }
      return '<ul class="checklist' + (locked ? ' locked' : '') + '" data-field="'
        + A.esc(field.field_name) + '">'
        + items.map(function (opt, i) {
            var value = opt.value === undefined ? opt : opt.value;
            var label = opt.label || value;
            var ticked = locked && done.indexOf(String(value)) >= 0;
            return '<li class="checklist-item' + (ticked ? ' done' : '') + '">'
              + '<label>'
              + '<input type="checkbox" name="' + A.esc(field.field_name) + '"'
              + ' id="fld-' + A.esc(field.field_name) + '-' + i + '"'
              + ' value="' + A.esc(value) + '"'
              + (ticked ? ' checked' : '') + (locked ? ' disabled' : '') + '>'
              + '<span class="checklist-mark"></span>'
              + '<span class="checklist-text">' + A.esc(label) + '</span>'
              + '</label></li>';
          }).join('')
        + '</ul>'
        + (locked
            ? '<div class="hint checklist-count">'
              + done.length + ' مورد از ' + items.length + ' انجام شده</div>'
            : '');
    }


    /* ── «محاسباتی»: a small, safe evaluator for the form's formulas ──────
       Same language the server uses: [field] references (by name or label),
       numbers, + − × ÷ ^, parentheses, comparisons, and ROUND, ABS, MIN, MAX,
       SQRT, IF. Nothing is ever passed to eval. The server recomputes on save;
       this only shows the result as the inputs are typed. */
    var labelToName = null;
    function refName(ref) {
      if (!labelToName) {
        labelToName = {};
        (schema.sections || []).forEach(function (sec) {
          (sec.fields || []).forEach(function (f) { labelToName[f.label] = f.field_name; });
        });
      }
      return labelToName[ref] || ref;
    }
    function toNum(v) {
      if (v === null || v === undefined || v === '') return null;
      if (typeof v === 'number') return v;
      var t = String(v).replace(/[۰-۹]/g, function (d) { return '۰۱۲۳۴۵۶۷۸۹'.indexOf(d); })
        .replace('٫', '.').replace(/,/g, '');
      var n = Number(t);
      return isNaN(n) ? null : n;
    }
    function roundTo(v, d, mode) {
      var f = Math.pow(10, d || 0), a = Math.abs(v) * f;
      var r = mode === 'up' ? Math.ceil(a - 1e-9) : mode === 'down' ? Math.floor(a + 1e-9)
        : Math.round(a);
      r = r / f;
      return v < 0 ? -r : r;
    }
    function truthy(v) { return !(v === null || v === undefined || v === '' || v === 0 || v === false); }
    function evalFormula(text, lookup) {
      var toks = [], i = 0, src = String(text || '');
      while (i < src.length) {
        var c = src[i];
        if (/\s/.test(c)) { i++; continue; }
        if (c === '[' || c === '{') {
          var close = c === '[' ? ']' : '}', j = src.indexOf(close, i);
          if (j < 0) throw 'bad';
          toks.push({ t: 'ref', v: src.slice(i + 1, j).trim() }); i = j + 1; continue;
        }
        if (c === '"' || c === "'" || c === '«') {
          var endq = src.indexOf(c === '«' ? '»' : c, i + 1);
          if (endq < 0) throw 'bad';
          toks.push({ t: 'str', v: src.slice(i + 1, endq) }); i = endq + 1; continue;
        }
        var m = /^[0-9۰-۹]+([.٫][0-9۰-۹]+)?/.exec(src.slice(i));
        if (m) { toks.push({ t: 'num', v: toNum(m[0]) }); i += m[0].length; continue; }
        m = /^[A-Za-z_][A-Za-z_0-9]*/.exec(src.slice(i));
        if (m) { toks.push({ t: 'fn', v: m[0].toUpperCase() }); i += m[0].length; continue; }
        m = /^(>=|<=|!=|<>|==|[-+*\/^%&()<>=,×÷])/.exec(src.slice(i));
        if (m) { toks.push({ t: 'op', v: m[0] === '×' ? '*' : m[0] === '÷' ? '/' : m[0] }); i += m[0].length; continue; }
        throw 'bad';
      }
      var p = 0;
      function peek(v) { return toks[p] && toks[p].t === 'op' && toks[p].v === v; }
      function cmpVals(op, a, b) {
        if (a === null || b === null) {
          if (op === '=' || op === '==') return a === b ? 1 : 0;
          if (op === '!=' || op === '<>') return a === b ? 0 : 1;
          return null;
        }
        var na = toNum(a), nb = toNum(b);
        if (na !== null && nb !== null) { a = na; b = nb; } else { a = String(a); b = String(b); }
        return { '>': a > b, '<': a < b, '>=': a >= b, '<=': a <= b, '=': a === b, '==': a === b,
                 '!=': a !== b, '<>': a !== b }[op] ? 1 : 0;
      }
      function cmp() {
        var a = cat();
        while (toks[p] && toks[p].t === 'op' && ['>', '<', '>=', '<=', '=', '==', '!=', '<>'].indexOf(toks[p].v) >= 0) {
          var op = toks[p++].v, b = cat();
          a = cmpVals(op, a, b);
        }
        return a;
      }
      function cat() {
        var a = add();
        while (peek('&')) { p++; var b = add(); a = (a === null ? '' : String(a)) + (b === null ? '' : String(b)); }
        return a;
      }
      function add() {
        var a = mul();
        while (peek('+') || peek('-')) {
          var op = toks[p++].v, b = toNum(mul()); a = toNum(a);
          a = (a === null || b === null) ? null : (op === '+' ? a + b : a - b);
        }
        return a;
      }
      function mul() {
        var a = pow();
        while (peek('*') || peek('/') || peek('%')) {
          var op = toks[p++].v, b = toNum(pow()); a = toNum(a);
          if (a === null || b === null) a = null;
          else if (op === '/') a = b === 0 ? null : a / b;
          else if (op === '%') a = b === 0 ? null : a % b;
          else a = a * b;
        }
        return a;
      }
      function pow() {
        var a = unary();
        if (peek('^')) {
          p++; var b = toNum(pow()); a = toNum(a);
          a = (a === null || b === null) ? null : Math.pow(a, b);
          if (a !== null && !isFinite(a)) a = null;
        }
        return a;
      }
      function unary() {
        if (peek('-')) { p++; var v = toNum(unary()); return v === null ? null : -v; }
        if (peek('+')) { p++; return unary(); }
        return atom();
      }
      function atom() {
        var tk = toks[p++];
        if (!tk) throw 'bad';
        if (tk.t === 'num' || tk.t === 'str') return tk.v;
        if (tk.t === 'ref') {
          var raw = lookup(refName(tk.v));
          if (raw === undefined || raw === '') return null;
          var asNum = toNum(raw);
          return asNum === null ? raw : asNum;
        }
        if (tk.t === 'op' && tk.v === '(') { var v = cmp(); if (!peek(')')) throw 'bad'; p++; return v; }
        if (tk.t === 'fn') {
          if (tk.v === 'TRUE') return 1;
          if (tk.v === 'FALSE') return 0;
          if (!peek('(')) throw 'bad';
          p++;
          var args = [];
          if (!peek(')')) { args.push(cmp()); while (peek(',')) { p++; args.push(cmp()); } }
          if (!peek(')')) throw 'bad';
          p++;
          var ns = args.map(toNum);
          var nums = ns.filter(function (x) { return x !== null; });
          var a0 = ns[0], d1 = ns[1] || 0;
          switch (tk.v) {
            case 'ROUND': return a0 === null ? null : roundTo(a0, d1);
            case 'ROUNDUP': return a0 === null ? null : roundTo(a0, d1, 'up');
            case 'ROUNDDOWN': return a0 === null ? null : roundTo(a0, d1, 'down');
            case 'ABS': return a0 === null ? null : Math.abs(a0);
            case 'SQRT': return a0 === null || a0 < 0 ? null : Math.sqrt(a0);
            case 'POWER': return a0 === null || ns[1] === null ? null : Math.pow(a0, ns[1]);
            case 'MEAN': return nums.length ? nums.reduce(function (t, x) { return t + x; }, 0) / nums.length : null;
            case 'MIN': return nums.length ? Math.min.apply(null, nums) : null;
            case 'MAX': return nums.length ? Math.max.apply(null, nums) : null;
            case 'IF': return truthy(args[0]) ? (args[1] === undefined ? null : args[1])
              : (args[2] === undefined ? null : args[2]);
            case 'AND': return args.every(truthy) ? 1 : 0;
            case 'OR': return args.some(truthy) ? 1 : 0;
            case 'NOT': return truthy(args[0]) ? 0 : 1;
            case 'IFERROR': return (args[0] === null || args[0] === '' || (typeof args[0] === 'number' && !isFinite(args[0])))
              ? (args[1] === undefined ? null : args[1]) : args[0];
            case 'COALESCE':
              for (var q = 0; q < args.length; q++) if (args[q] !== null && args[q] !== '') return args[q];
              return null;
            case 'CONCAT': return args.map(function (x) { return x === null ? '' : String(x); }).join('');
            case 'NUMBER': return a0;
            case 'LEADNUM': {
              /* «12 متری» → 12: the number an option's label starts with */
              var lt = Array.isArray(args[0]) ? args[0][0] : args[0];
              var lm = String(lt == null ? '' : lt).replace(/[۰-۹]/g, function (d) { return '۰۱۲۳۴۵۶۷۸۹'.indexOf(d); })
                .replace('٫', '.').match(/^\s*(-?\d+(?:\.\d+)?)/);
              return lm ? Number(lm[1]) : null;
            }
            case 'EPUMP': return epumpLabel(args[0], args[1], args[2]);
            case 'EPPART': {
              var ep = epumpParse(args[0]), part = String(args[1] == null ? '' : args[1]).trim().toLowerCase();
              if (part === 'pump') return epumpLabel(ep[0], ep[1]);
              if (part === 'motor') return ep[2];
              return part === 'type' ? ep[0] : part === 'stages' ? ep[1] : null;
            }
            case 'TEXT': return args[0] === null ? null : String(args[0]);
            case 'LEN': return args[0] === null ? null : String(args[0]).length;
            case 'QFIT_A': return qfit(ns, true);
            case 'QFIT_B': return qfit(ns, false);
            case 'CAT_Q': case 'CAT_H': case 'CAT_EFF': case 'CAT_KW': case 'CAT_A': case 'CAT_TITLE': case 'CAT_MEFF':
              return Catalogue.call(tk.v, args, toNum);
            default: throw 'bad';
          }
        }
        throw 'bad';
      }
      var out = cmp();
      if (p < toks.length) throw 'bad';
      return out;
    }
    self.evalFormula = evalFormula;

    function contextValue(name) {
      var wrap = qs('[data-wrap="' + name + '"]');
      if (wrap) {
        var fd = fieldByName(name);
        if (fd && fd.read_only) return fd.read_only_value;
        if (fd && fd.field_type === 'chart') return null;
        if (fd && fd.field_type === 'formula') {
          var out = qs('#fld-' + name);
          return out ? out.value : null;
        }
        return currentValueOf(name);
      }
      return (options.context || {})[name];
    }
    var byName = null;
    var suggested = {};   // field_name → value offered by setValues({onlyEmpty})
    function fieldByName(name) {
      if (!byName) {
        byName = {};
        (schema.sections || []).forEach(function (sec) {
          (sec.fields || []).forEach(function (f) { byName[f.field_name] = f; });
        });
      }
      return byName[name];
    }

    function recomputeFormulas() {
      var outs = qsa('[data-formula]');
      for (var pass = 0; pass < Math.max(3, outs.length + 1); pass++) {
        var changed = false;
        outs.forEach(function (out) {
          var fd = fieldByName(out.dataset.formula);
          if (!fd) return;
          var v = null;
          try { v = evalFormula(fd.formula, contextValue); } catch (e) { v = null; }
          var dec = /^\d+$/.test(String(fd.step || '')) ? Number(fd.step) : 4;
          var text;
          if (v === null || v === undefined || (typeof v === 'number' && !isFinite(v))) text = '';
          else if (typeof v === 'number') text = String(Math.round(v * Math.pow(10, dec)) / Math.pow(10, dec));
          else text = String(v);
          if (out.value !== text) { out.value = text; changed = true; }
        });
        if (!changed) break;
      }
      qsa('[data-autofill]').forEach(function (inp) {
        var fd = fieldByName(inp.dataset.autofill);
        if (!fd) return;
        var v = null;
        try { v = evalFormula(String(fd.default_value).slice(1), contextValue); } catch (e) { v = null; }
        var text = (v === null || v === undefined || (typeof v === 'number' && !isFinite(v))) ? ''
          : typeof v === 'number' ? String(Math.round(v * 10000) / 10000) : String(v);
        var mine = inp.value !== '' && inp.value !== inp.dataset.auto;
        if (inp.dataset.auto === undefined && inp.value !== '' && inp.value === text) mine = false;
        if (mine) return;                         // the user's own value stays
        if (inp.value !== text) inp.value = text;
        inp.dataset.auto = text;
      });
      whPresetRefresh();
      drawCharts();
    }
    self.recomputeFormulas = recomputeFormulas;

    function renderFormula(field) {
      return '<input type="text" class="calc-output" id="fld-' + A.esc(field.field_name) + '"'
        + ' name="' + A.esc(field.field_name) + '" data-formula="' + A.esc(field.field_name) + '"'
        + ' readonly tabindex="-1" placeholder="خودکار محاسبه می‌شود">'
        + '<details class="calc-formula"><summary>ƒ فرمول</summary>'
        + '<span class="hint" dir="ltr">= ' + A.esc(field.formula || '') + '</span></details>';
    }

    /* ── «مستند»: upload into a named slot ─────────────────────────────── */
    function fileRow(a, removable) {
      return '<div class="file-row" data-att="' + a.id + '">'
        + '<a href="' + A.esc(a.url) + '" target="_blank">📄 ' + A.esc(a.filename) + '</a>'
        + '<span class="hint">' + A.esc(a.size_label || '') + (a.uploaded_by_name ? ' · ' + A.esc(a.uploaded_by_name) : '')
        + (a.uploaded_at_j ? ' · ' + A.esc(a.uploaded_at_j) : '') + '</span>'
        + (removable ? '<button type="button" class="btn-sm btn-del file-del" data-att="' + a.id + '" title="حذف">🗑</button>' : '')
        + '</div>';
    }
    function renderFile(field, locked) {
      var files = field.files || [];
      var list = '<div class="file-list" data-files="' + A.esc(field.field_name) + '">'
        + (files.length ? files.map(function (a) { return fileRow(a, !locked); }).join('')
          : '<div class="hint">' + (locked ? 'مستندی بارگذاری نشده است.' : 'هنوز فایلی بارگذاری نشده.') + '</div>')
        + '</div>';
      if (locked) return list;
      if (!options.upload) {
        return list + '<div class="hint">بارگذاری این مستند در کارتابل فرایند انجام می‌شود.</div>';
      }
      return list + '<label class="file-pick btn-ghost btn-sm">📎 انتخاب فایل'
        + '<input type="file" class="file-input" data-file-for="' + A.esc(field.field_name) + '"'
        + (field.file_accept ? ' accept="' + A.esc(field.file_accept) + '"' : '')
        + (field.file_multiple !== false ? ' multiple' : '') + ' hidden></label>'
        + '<span class="file-status hint" data-status="' + A.esc(field.field_name) + '"></span>'
        + (field.file_accept ? '<span class="hint"> — نوع مجاز: ' + A.esc(field.file_accept) + '</span>' : '');
    }
    function redrawFiles(field) {
      var box = qs('[data-files="' + field.field_name + '"]');
      if (!box) return;
      var files = field.files || [];
      box.innerHTML = files.length ? files.map(function (a) { return fileRow(a, true); }).join('')
        : '<div class="hint">هنوز فایلی بارگذاری نشده.</div>';
    }
    root.addEventListener('change', async function (ev) {
      var input = ev.target.closest && ev.target.closest('.file-input');
      if (!input || !options.upload) return;
      var field = fieldByName(input.dataset.fileFor);
      if (!field || !input.files.length) return;
      var status = qs('[data-status="' + field.field_name + '"]');
      if (status) status.textContent = 'در حال بارگذاری…';
      try {
        var added = await options.upload(field, Array.prototype.slice.call(input.files));
        field.files = field.file_multiple === false ? added.slice(-1) : (field.files || []).concat(added);
        redrawFiles(field);
        if (status) status.textContent = '✓ بارگذاری شد';
      } catch (err) {
        if (status) status.textContent = '✕ ' + (err.message || 'خطا');
      }
      input.value = '';
    });
    root.addEventListener('click', async function (ev) {
      var del = ev.target.closest && ev.target.closest('.file-del');
      if (!del || !options.removeFile) return;
      var wrap = del.closest('[data-wrap]');
      var field = wrap && fieldByName(wrap.dataset.wrap);
      if (!field) return;
      if (!(await A.confirmDialog({ message: 'این فایل حذف شود؟' }))) return;
      try {
        await options.removeFile(Number(del.dataset.att));
        field.files = (field.files || []).filter(function (a) { return String(a.id) !== del.dataset.att; });
        redrawFiles(field);
      } catch (err) { A.toast(err.message, 'error'); }
    });

    /* ── «چند مقدار عددی»: one value per part (فاز ۱، فاز ۲، فاز ۳) ─────── */
    function partLabels(field) {
      return (field.part_labels && field.part_labels.length) ? field.part_labels
        : ['فاز ۱', 'فاز ۲', 'فاز ۳'];
    }
    function renderNumbers(field) {
      var name = A.esc(field.field_name);
      return '<div class="numbers-group" data-numbers="' + name + '">'
        + partLabels(field).map(function (lbl, i) {
          return '<label class="num-part"><span>' + A.esc(lbl) + '</span>'
            + '<input type="text" inputmode="decimal" dir="ltr" class="num-part-input"'
            + ' id="fld-' + name + '__' + i + '" data-part-of="' + name + '" data-part="' + i + '"'
            + (field.placeholder ? ' placeholder="' + A.esc(field.placeholder) + '"' : '') + '></label>';
        }).join('') + '</div>';
    }
    function numbersOf(name) {
      return qsa('[data-part-of="' + name + '"]').map(function (i) { return i.value.trim(); });
    }
    function splitNumbers(value) {
      if (Array.isArray(value)) return value.map(function (v) { return v == null ? '' : String(v); });
      if (value === null || value === undefined || value === '') return [];
      return String(value).replace(/\(.*\)$/, '').split(/\s*[\/،,]\s*/).map(function (v) { return v.trim(); });
    }

    /* ── «نمودار»: drawn from the form's own numbers as they are typed ──── */
    function renderChart(field) {
      return '<div class="form-chart" data-chart="' + A.esc(field.field_name) + '"></div>'
        + '<div class="form-chart-eq hint" data-chart-eq="' + A.esc(field.field_name) + '"></div>';
    }
    function drawCharts() {
      var boxes = qsa('[data-chart]');
      if (!boxes.length) return;
      loadEcharts().then(function (ec) {
        boxes.forEach(function (box) { drawChart(ec, box); });
      }).catch(function () {
        boxes.forEach(function (box) { box.innerHTML = '<div class="hint">کتابخانه‌ی نمودار بارگذاری نشد.</div>'; });
      });
    }
    function drawChart(ec, box) {
      var fd = fieldByName(box.dataset.chart);
      if (!fd || !box.offsetParent) return;           // hidden: drawn when it opens
      paintChart(ec, box, qs('[data-chart-eq="' + fd.field_name + '"]'), fd.chart_config || {},
                  contextValue, evalFormula);
    }
    self.drawCharts = drawCharts;

    /* ── «اقلام انبار»: item / specification / plaque / condition / quantity ── */
    var whValues = {};
    function whCfg(field) { return field.wh_config || {}; }
    /* «فرم قطعات»: every part of one equipment kind, counted — the workshop's paper form */
    var WHP_COLS = [['installed_new', 'نصب — نو'], ['installed_repair', 'نصب — کهنه (قابل استفاده مجدد)'],
                    ['collected_new', 'جمع‌آوری — نو'], ['collected_old', 'جمع‌آوری — کهنه'],
                    ['reusable', 'قابل استفاده مجدد'], ['scrap', 'اسقاط']];
    function whpCols(cfg) {
      var pick = (cfg.columns || []).length ? cfg.columns : WHP_COLS.map(function (c) { return c[0]; });
      return WHP_COLS.filter(function (c) { return pick.indexOf(c[0]) !== -1; });
    }
    /* «فرم قطعات»: search a part, add it, type its counts — only the parts
       actually touched are on the form, with their totals underneath,
       instead of a table of every part of the motor or pump. */
    function renderWhParts(field) {
      var name = A.esc(field.field_name), cfg = whCfg(field);
      return '<div class="wh-lines wh-parts" data-whp="' + name + '">'
        + '<div class="wh-head hint">🧩 فرم قطعات ' + A.esc(cfg.equipment_type || '') + ' — '
        + (cfg.direction === 'out' ? 'خروج از ' : 'ورود به ') + (cfg.warehouse === 'parts' ? 'انبار قطعات' : 'انبار تجهیزات')
        + '</div>'
        + (field.read_only ? '' : '<div class="whp-pick"><input type="search" class="whp-search" autocomplete="off"'
          + ' placeholder="🔎 جستجوی قطعه (نام یا کد انباری) و انتخاب — مثلاً «پیچ دو سر رزوه»">'
          + '<div class="whp-suggest hidden"></div></div>')
        + '<div class="wh-table-wrap"><table class="wh-table whp-table"><thead><tr><th>#</th><th>کد انباری</th><th>شرح قطعه</th>'
        + whpCols(cfg).map(function (c) { return '<th>' + A.esc(c[1]) + '</th>'; }).join('')
        + '<th>توضیحات</th>' + (field.read_only ? '' : '<th></th>') + '</tr></thead><tbody></tbody><tfoot></tfoot></table></div></div>';
    }
    function whpItems(cfg) {
      var d = Warehouse.data || { items: [] };
      return d.items.filter(function (it) {
        return it.kind === 'part' && (!cfg.equipment_type || it.category === cfg.equipment_type);
      });
    }
    function whpCode(it) { return (it.note || '').replace('کد انباری', '').trim() || it.code || ''; }
    function whpRowHtml(field, it, r, k) {
      var cols = whpCols(whCfg(field)), ro = field.read_only ? ' disabled' : '';
      r = r || {};
      var code = it ? whpCode(it) : (r.code || '');
      var label = it ? it.name : (r.item_name || '');
      return '<tr data-item="' + (it ? it.id : (r.item_id || '')) + '" data-name="' + A.esc(label) + '" data-code="' + A.esc(code) + '">'
        + '<td class="whp-k">' + (k + 1) + '</td><td dir="ltr" class="mono">' + A.esc(code) + '</td><td class="whp-name">' + A.esc(label) + '</td>'
        + cols.map(function (c) {
          var v = r[c[0]]; v = v === undefined || v === null || v === 0 ? '' : v;
          return '<td><input type="text" inputmode="numeric" dir="ltr" class="whp-n" data-col="' + c[0] + '" value="' + A.esc(v) + '"' + ro + '></td>';
        }).join('')
        + '<td><input type="text" class="whp-note" value="' + A.esc(r.note || '') + '"' + ro + '></td>'
        + (field.read_only ? '' : '<td><button type="button" class="btn-sm btn-del whp-del" title="حذف این قطعه">✕</button></td>')
        + '</tr>';
    }
    function whpDraw(name) {
      var field = fieldByName(name), wrap = qs('[data-whp="' + name + '"]'), body = wrap && wrap.querySelector('tbody');
      if (!field || !body) return;
      var byId = {}, byName = {};
      whpItems(whCfg(field)).forEach(function (it) { byId[String(it.id)] = it; byName[it.name] = it; });
      var rows = (whValues[name] || []).filter(function (r) { return r && (r.item_id || r.item_name); });
      body.innerHTML = rows.map(function (r, k) {
        return whpRowHtml(field, byId[String(r.item_id)] || byName[r.item_name] || null, r, k);
      }).join('');
      wrap.dataset.drawn = '1';
      whpEmptyNote(name);
      whpTotals(name);
    }
    function whpEmptyNote(name) {
      var wrap = qs('[data-whp="' + name + '"]'), field = fieldByName(name);
      if (!wrap || !field) return;
      var body = wrap.querySelector('tbody'), has = body.querySelector('tr[data-item]');
      var note = body.querySelector('tr.whp-empty');
      if (has && note) note.remove();
      if (!has && !note) {
        var cols = whpCols(whCfg(field)).length + (field.read_only ? 4 : 5);
        body.insertAdjacentHTML('beforeend', '<tr class="whp-empty"><td colspan="' + cols + '" class="hint">'
          + (field.read_only ? 'قطعه‌ای ثبت نشده است.' : 'هنوز قطعه‌ای اضافه نشده؛ از کادر جستجو قطعه را پیدا و انتخاب کنید.')
          + '</td></tr>');
      }
    }
    function whpRenumber(name) {
      qsa('[data-whp="' + name + '"] tbody tr[data-item]').forEach(function (tr, k) {
        tr.querySelector('.whp-k').textContent = k + 1;
      });
    }
    function whpSuggest(input) {
      var wrap = input.closest('[data-whp]'), name = wrap.dataset.whp, field = fieldByName(name);
      var list = wrap.querySelector('.whp-suggest');
      var q = String(input.value || '').trim().replace(/ي/g, 'ی').replace(/ك/g, 'ک');
      var taken = {};
      wrap.querySelectorAll('tbody tr[data-item]').forEach(function (tr) { taken[tr.dataset.item] = 1; });
      var items = whpItems(whCfg(field)).filter(function (it) {
        if (taken[String(it.id)]) return false;
        if (!q) return true;
        return (it.name + ' ' + whpCode(it)).replace(/ي/g, 'ی').replace(/ك/g, 'ک').indexOf(q) !== -1;
      }).slice(0, 30);
      list.innerHTML = items.length ? items.map(function (it, k) {
        return '<div class="whp-opt' + (k === 0 ? ' active' : '') + '" data-id="' + it.id + '"><span>' + A.esc(it.name)
          + '</span><span class="hint mono" dir="ltr">' + A.esc(whpCode(it)) + '</span></div>';
      }).join('') : '<div class="hint whp-none">قطعه‌ای با این نام پیدا نشد (فهرست قطعات در فرم‌ساز ویرایش می‌شود).</div>';
      list.classList.remove('hidden');
    }
    function whpAdd(name, itemId) {
      var wrap = qs('[data-whp="' + name + '"]'), field = fieldByName(name);
      var it = whpItems(whCfg(field)).filter(function (x) { return String(x.id) === String(itemId); })[0];
      if (!wrap || !it) return;
      var body = wrap.querySelector('tbody');
      var k = body.querySelectorAll('tr[data-item]').length;
      body.insertAdjacentHTML('beforeend', whpRowHtml(field, it, {}, k));
      whpEmptyNote(name);
      var search = wrap.querySelector('.whp-search');
      search.value = '';
      wrap.querySelector('.whp-suggest').classList.add('hidden');
      var first = body.querySelector('tr[data-item]:last-child .whp-n');
      if (first) first.focus();
      whpTotals(name);
    }
    root.addEventListener('input', function (e) {
      if (e.target.classList && e.target.classList.contains('whp-search')) whpSuggest(e.target);
    });
    root.addEventListener('focusin', function (e) {
      if (e.target.classList && e.target.classList.contains('whp-search')) whpSuggest(e.target);
    });
    root.addEventListener('keydown', function (e) {
      if (!e.target.classList || !e.target.classList.contains('whp-search')) return;
      var list = e.target.closest('[data-whp]').querySelector('.whp-suggest');
      var opts = Array.prototype.slice.call(list.querySelectorAll('.whp-opt'));
      var at = opts.findIndex(function (o) { return o.classList.contains('active'); });
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        if (!opts.length) return;
        if (at >= 0) opts[at].classList.remove('active');
        at = e.key === 'ArrowDown' ? Math.min(opts.length - 1, at + 1) : Math.max(0, at - 1);
        opts[at].classList.add('active');
        opts[at].scrollIntoView({ block: 'nearest' });
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (opts.length) whpAdd(e.target.closest('[data-whp]').dataset.whp, opts[Math.max(at, 0)].dataset.id);
      } else if (e.key === 'Escape') {
        list.classList.add('hidden');
      }
    });
    root.addEventListener('mousedown', function (e) {
      var opt = e.target.closest('.whp-opt');
      if (opt) { e.preventDefault(); whpAdd(opt.closest('[data-whp]').dataset.whp, opt.dataset.id); return; }
      if (!e.target.closest('.whp-pick')) qsa('.whp-suggest').forEach(function (l) { l.classList.add('hidden'); });
    });
    root.addEventListener('click', function (e) {
      var del = e.target.closest('.whp-del');
      if (!del) return;
      var wrap = del.closest('[data-whp]');
      del.closest('tr').remove();
      whpRenumber(wrap.dataset.whp);
      whpEmptyNote(wrap.dataset.whp);
      whpTotals(wrap.dataset.whp);
    });
    function whpNum(v) {
      var n = Number(String(v || '').replace(/[۰-۹]/g, function (d) { return '۰۱۲۳۴۵۶۷۸۹'.indexOf(d); }).replace('٫', '.'));
      return isNaN(n) ? 0 : n;
    }
    function whpTotals(name) {
      var box = qs('[data-whp="' + name + '"]');
      if (!box) return;
      var field = fieldByName(name), cols = whpCols(whCfg(field)), sums = {};
      qsa('[data-whp="' + name + '"] tbody tr[data-item]').forEach(function (tr) {
        var vals = {};
        tr.querySelectorAll('.whp-n').forEach(function (inp) {
          vals[inp.dataset.col] = whpNum(inp.value);
          sums[inp.dataset.col] = (sums[inp.dataset.col] || 0) + vals[inp.dataset.col];
        });
        var collected = (vals.collected_new || 0) + (vals.collected_old || 0);
        var judged = (vals.reusable || 0) + (vals.scrap || 0);
        var over = ('collected_new' in vals || 'collected_old' in vals) && judged > collected;
        tr.classList.toggle('whp-over', over);
        tr.title = over ? '«قابل استفاده + اسقاط» از تعداد جمع‌آوری‌شده بیشتر است' : '';
      });
      var n = qsa('[data-whp="' + name + '"] tbody tr[data-item]').length;
      box.querySelector('tfoot').innerHTML = '<tr><td colspan="3"><b>جمع (' + n + ' قطعه)</b></td>' + cols.map(function (c) {
        return '<td><b>' + (sums[c[0]] || 0) + '</b></td>';
      }).join('') + '<td></td>' + (field.read_only ? '' : '<td></td>') + '</tr>';
    }
    function whpRead(name) {
      var cols = whpCols(whCfg(fieldByName(name)));
      return qsa('[data-whp="' + name + '"] tbody tr[data-item]').map(function (tr) {
        var row = { item_id: Number(tr.dataset.item), item_name: tr.dataset.name, code: tr.dataset.code,
                    note: tr.querySelector('.whp-note').value.trim() };
        var any = !!row.note;
        cols.forEach(function (c) {
          var inp = tr.querySelector('[data-col="' + c[0] + '"]'), n = whpNum(inp && inp.value);
          if (n) { row[c[0]] = n; any = true; }
        });
        return any ? row : null;
      }).filter(Boolean);
    }
    root.addEventListener('input', function (e) {
      var t = e.target.closest('[data-whp] .whp-n');
      if (t) whpTotals(t.closest('[data-whp]').dataset.whp);
    });

    function renderWhLines(field) {
      if (whCfg(field).mode === 'parts') return renderWhParts(field);
      var name = A.esc(field.field_name), cfg = whCfg(field);
      var dir = cfg.direction === 'out' ? 'خروج از ' : 'ورود به ';
      var wh = cfg.warehouse === 'parts' ? 'انبار قطعات' : 'انبار تجهیزات';
      return '<div class="wh-lines" data-wh="' + name + '">'
        + '<div class="wh-head hint">' + (cfg.direction === 'out' ? '📤 ' : '📥 ') + dir + wh + '</div>'
        + '<div class="wh-table-wrap"><table class="wh-table"><thead><tr><th>کالا</th>'
        + (cfg.spec === false ? '' : '<th>تیپ / مشخصات</th>')
        + (cfg.serial === false ? '' : '<th>پلاک / سریال</th>')
        + '<th>وضعیت</th><th>تعداد</th><th></th></tr></thead><tbody></tbody></table></div>'
        + (field.read_only || cfg.preset_lock ? '' : '<button type="button" class="btn-ghost btn-sm" data-wh-add="' + name + '">➕ افزودن ردیف</button>')
        + ((cfg.preset || []).length && cfg.preset_lock && !field.read_only
            ? '<div class="hint">کالا و مشخصات همان تجهیزی است که از چاه کشیده شد؛ وضعیت و پلاک را مشخص کنید.</div>' : '')
        + '</div>';
    }
    /* «ردیف‌های ثابت»: rows the form starts with — the motor and the pump
       just pulled, their type worked out of the process (a formula) */
    function whItemByCode(code) {
      var d = Warehouse.data || { items: [] };
      return d.items.filter(function (it) { return it.code === code; })[0] || null;
    }
    function whPresetSpec(p) {
      if (!p.spec) return '';
      var v = null;
      try { v = evalFormula(String(p.spec).replace(/^=/, ''), contextValue); } catch (e) { v = null; }
      if (v === null || v === undefined) return '';
      return typeof v === 'number' ? String(Math.round(v * 10000) / 10000) : String(v);
    }
    function whPresetRows(field, saved) {
      var cfg = whCfg(field), used = [];
      var rows = (cfg.preset || []).map(function (p, i) {
        var item = whItemByCode(p.item_code);
        var mine = saved.filter(function (r, k) {
          var hit = used.indexOf(k) === -1 && item && (String(r.item_id || '') === String(item.id) || r.item_name === item.name);
          if (hit) used.push(k);
          return hit;
        })[0] || {};
        return { item_id: item ? item.id : null, item_name: item ? item.name : (p.item_code || ''),
                 spec: whPresetSpec(p) || mine.spec || '', serial: mine.serial || '',
                 condition: mine.condition || p.condition || '', qty: cfg.preset_lock ? (p.qty || 1) : (mine.qty || p.qty || 1),
                 _preset: i };
      });
      if (!cfg.preset_lock) rows = rows.concat(saved.filter(function (r, k) { return used.indexOf(k) === -1; }));
      return rows;
    }
    function whPresetRefresh() {
      self.eachField(function (field) {
        var cfg = whCfg(field);
        if (field.field_type !== 'wh_lines' || field.read_only || !(cfg.preset || []).length) return;
        qsa('[data-wh="' + field.field_name + '"] tr.wh-row[data-preset]').forEach(function (tr) {
          var p = cfg.preset[+tr.dataset.preset], inp = tr.querySelector('.wh-spec');
          if (!p || !inp || !p.spec) return;
          var v = whPresetSpec(p);
          if (cfg.preset_lock ? inp.value !== v : (!inp.value && v)) inp.value = v;
        });
      });
    }
    function whItems(cfg) {
      var d = Warehouse.data || { items: [] };
      return d.items.filter(function (it) {
        return (!(cfg.kinds || []).length || cfg.kinds.indexOf(it.kind) !== -1)
          && (!(cfg.categories || []).length || cfg.categories.indexOf(it.category) !== -1);
      });
    }
    function whConds(cfg) {
      var d = Warehouse.data || { conditions: [] };
      return d.conditions.filter(function (c) {
        return !(cfg.conditions || []).length || cfg.conditions.indexOf(c.code) !== -1;
      });
    }
    function whRowHtml(field, row) {
      var cfg = whCfg(field), ro = !!field.read_only ? ' disabled' : '';
      row = row || {};
      var fixed = row._preset !== undefined && cfg.preset_lock && !field.read_only;
      var lockItem = fixed ? ' disabled' : ro, lockText = fixed ? ' readonly' : ro;
      var items = whItems(cfg), known = false;
      var opts = '<option value="">— انتخاب کالا —</option>' + items.map(function (it) {
        var sel = String(row.item_id || '') === String(it.id)
          || (!row.item_id && row.item_name && row.item_name === it.name);
        if (sel) known = true;
        return '<option value="' + it.id + '"' + (sel ? ' selected' : '') + '>' + A.esc(it.name)
          + (it.unit ? ' (' + A.esc(it.unit) + ')' : '') + '</option>';
      }).join('');
      if (!known && row.item_name) {
        opts += '<option value="" data-name="' + A.esc(row.item_name) + '" selected>' + A.esc(row.item_name) + '</option>';
      }
      var conds = '<option value="">—</option>' + whConds(cfg).map(function (c) {
        return '<option value="' + A.esc(c.code) + '"' + ((row.condition || cfg.default_condition) === c.code ? ' selected' : '')
          + '>' + A.esc(c.label) + '</option>';
      }).join('');
      return '<tr class="wh-row' + (fixed ? ' wh-fixed' : '') + '"' + (row._preset !== undefined ? ' data-preset="' + row._preset + '"' : '')
        + '><td><select class="wh-item"' + lockItem + '>' + opts + '</select></td>'
        + (cfg.spec === false ? '' : '<td><input type="text" class="wh-spec" dir="ltr" placeholder="384/10+73.5" value="' + A.esc(row.spec || '') + '"' + lockText + '></td>')
        + (cfg.serial === false ? '' : '<td><input type="text" class="wh-serial" dir="ltr" value="' + A.esc(row.serial || '') + '"' + ro + '></td>')
        + '<td><select class="wh-cond"' + ro + '>' + conds + '</select></td>'
        + '<td><input type="text" inputmode="decimal" dir="ltr" class="wh-qty" value="' + A.esc(row.qty == null ? 1 : row.qty) + '"' + lockText + '></td>'
        + '<td>' + (ro || fixed ? '' : '<button type="button" class="btn-sm btn-del wh-del" title="حذف ردیف">✕</button>') + '</td></tr>';
    }
    function whDraw(name) {
      var field = fieldByName(name), box = qs('[data-wh="' + name + '"] tbody');
      if (!field || !box) return;
      var rows = whValues[name] || [];
      if ((whCfg(field).preset || []).length && !field.read_only) rows = whPresetRows(field, rows);
      if (!rows.length && !field.read_only) rows = [{}];
      box.innerHTML = rows.map(function (r) { return whRowHtml(field, r); }).join('');
    }
    function whRead(name) {
      return qsa('[data-wh="' + name + '"] tr.wh-row').map(function (tr) {
        var sel = tr.querySelector('.wh-item'), opt = sel.options[sel.selectedIndex];
        var get = function (c) { var el = tr.querySelector(c); return el ? el.value.trim() : ''; };
        return { item_id: sel.value ? Number(sel.value) : null,
                 item_name: sel.value ? opt.text.replace(/\s*\([^)]*\)$/, '') : (opt && opt.dataset.name) || '',
                 spec: get('.wh-spec'), serial: get('.wh-serial'), condition: get('.wh-cond'),
                 qty: get('.wh-qty') || '1' };
      }).filter(function (r) { return r.item_id || r.item_name; });
    }
    root.addEventListener('click', function (e) {
      var add = e.target.closest('[data-wh-add]');
      if (add) {
        var n = add.dataset.whAdd;
        whValues[n] = whRead(n).concat([{}]);
        whDraw(n);
        return;
      }
      var del = e.target.closest('.wh-del');
      if (del) {
        var wrap = del.closest('[data-wh]');
        del.closest('tr').remove();
        whValues[wrap.dataset.wh] = whRead(wrap.dataset.wh);
      }
    });

    var renderCols = 3;                  // columns of the section being drawn
    function renderField(field) {
      var body;
      if (field.field_type === 'radio') body = renderChoice(field, false);
      else if (field.field_type === 'checkbox' && optionsFor(field).length) {
        body = renderChoice(field, true);
      } else if (field.field_type === 'checkbox') {
        body = '<div class="btn-group"><label><input type="checkbox" id="fld-'
          + A.esc(field.field_name) + '" name="' + A.esc(field.field_name)
          + '" value="1"><span class="btn-opt">بله</span></label></div>';
      } else if (field.field_type === 'multiselect') body = renderChoice(field, true);
      else if (field.field_type === 'checklist') body = renderChecklist(field);
      else if (field.field_type === 'select') body = renderSelect(field);
      else if (field.field_type === 'file') body = renderFile(field, !!field.read_only);
      else if (field.field_type === 'formula') body = renderFormula(field);
      else if (field.field_type === 'numbers') body = renderNumbers(field);
      else if (field.field_type === 'chart') body = renderChart(field);
      else if (field.field_type === 'wh_lines') body = renderWhLines(field);
      else body = renderInput(field);

      /* Settled upstream: shown and filled so the stage can see it, but not
         editable here — the well is chosen once, at step zero, and a checklist
         somebody already ticked is carried forward as a record of what they
         ticked rather than as a form to fill again. */
      if (field.read_only && field.field_type !== 'file' && field.field_type !== 'chart'
          && field.field_type !== 'wh_lines') {
        body = field.field_type === 'checklist'
          ? renderChecklist(field, true)
          : '<input type="text" id="fld-' + A.esc(field.field_name) + '"'
            + ' value="' + A.esc(field.read_only_value == null ? ''
                                 : String(field.read_only_value)) + '"'
            + ' readonly disabled>';
      }
      var span = field.col_span > 1 ? ' span-' + Math.min(field.col_span, 2) : '';
      /* Long option lists and free text need the whole row; squeezing 20
         buttons into a 180px column is what made the form look ragged. */
      var count = optionsFor(field).length;
      var wide = '';
      if (['textarea', 'file', 'chart', 'wh_lines'].includes(field.field_type)) wide = ' span-full';
      else if (['checkbox', 'multiselect'].includes(field.field_type) && count > 4) {
        wide = ' span-full';
      } else if (field.field_type === 'radio' && count > 7) {
        wide = ' wide-choice';
      }
      /* a typed value sits beside its label, not under it — where there is
         room: in a row of four or five fields the label goes on top, or the
         box itself is left too narrow to type a number into */
      var inline = renderCols <= 3 && (['text', 'number', 'date', 'jalali_date', 'autocomplete', 'formula', 'select']
        .indexOf(field.field_type) !== -1
        || (field.read_only && ['file', 'chart', 'checklist', 'wh_lines', 'textarea'].indexOf(field.field_type) === -1));
      return '<div class="field' + span + wide + (inline ? ' inline' : '')
        + (field.field_type === 'formula' ? ' calc-field' : '')
        + (field.read_only ? ' read-only' : '') + '" data-wrap="'
        + A.esc(field.field_name) + '">'
        + labelHtml(field) + body
        + (field.help_text ? '<span class="hint">' + A.esc(field.help_text) + '</span>' : '')
        + ((field.block_options || []).length && !field.read_only
            ? '<span class="block-note hidden" data-block-note="' + A.esc(field.field_name) + '">⛔ با پاسخ «'
              + A.esc(field.block_options.join('، ')) + '» مرحله ارسال نمی‌شود؛ پس از رفع مشکل پاسخ را اصلاح کنید.</span>'
            : '')
        + '<span class="err hidden"></span></div>';
    }

    function usesCatalogue() {
      return (schema.sections || []).some(function (sec) {
        return (sec.fields || []).some(function (f) {
          return /CAT_/i.test(String(f.formula || '') + String(f.default_value || ''))
            || (f.field_type === 'chart' && chartUsesCatalogue(f.chart_config));
        });
      });
    }

    self.render = function () {
      root.innerHTML = (schema.sections || []).map(function (section) {
        if (!section.fields || !section.fields.length) return '';
        var calcs = section.collapse_formulas ? section.fields.filter(function (f) {
          return f.field_type === 'formula';
        }).length : 0;
        renderCols = section.columns || 3;
        var group = section.repeat_group ? A.esc(section.repeat_group) : '';
        return '<div class="form-section' + (section.full_width ? ' full-width' : '') + (calcs ? ' calc-collapsed' : '')
          + '" data-section="' + A.esc(section.code || '') + '"' + (group ? ' data-repeat="' + group + '"' : '') + '>'
          + '<div class="section-title">'
          + (section.icon ? '<span>' + A.esc(section.icon) + '</span>' : '')
          + '<span class="sec-title-text">' + A.esc(section.title) + '</span>'
          + (section.is_optional ? '<span class="badge muted">اختیاری</span>' : '')
          + (calcs ? '<button type="button" class="btn-sm btn-ghost calc-toggle">ƒ نمایش محاسبات ('
            + calcs + ')</button>' : '')
          + (group ? '<button type="button" class="btn-sm btn-del repeat-del hidden" title="حذف این بخش و مقادیر آن">✕ حذف</button>' : '')
          + '</div>'
          + '<div class="field-group cols-' + renderCols + '">'
          + section.fields.map(renderField).join('')
          + '</div></div>';
      }).join('');
      renderCols = 3;
      setupRepeats();
      wireStages();

      qsa('.jdate').forEach(function (input) { J.attach(input); });
      qsa('.calc-toggle').forEach(function (btn) {
        btn.addEventListener('click', function () {
          var sec = btn.closest('.form-section');
          var open = sec.classList.toggle('calc-open');
          btn.textContent = btn.textContent.replace(open ? 'نمایش' : 'پنهان', open ? 'پنهان' : 'نمایش');
          if (open) drawCharts();
        });
      });
      qsa('[data-autocomplete]').forEach(setupAutocomplete);
      enableRadioClearing();
      root.addEventListener('change', onFieldChanged);
      root.addEventListener('change', updateChoiceCounts);
      applyDefaults();
      self.applyConditional();
      updateChoiceCounts();
      root.addEventListener('input', recomputeFormulas);
      root.addEventListener('change', recomputeFormulas);
      recomputeFormulas();
      if (usesCatalogue()) Catalogue.load().then(function () { recomputeFormulas(); });
      var whNames = [];
      self.eachField(function (f) { if (f.field_type === 'wh_lines') whNames.push(f.field_name); });
      if (whNames.length) {
        Warehouse.load().then(function () {
          whNames.forEach(function (n) {
            var f = fieldByName(n);
            if (f && f.read_only && !whValues[n] && Array.isArray(f.read_only_rows)) whValues[n] = f.read_only_rows;
            if (f && whCfg(f).mode === 'parts') whpDraw(n); else whDraw(n);
          });
        });
      }
      /* a pane that is drawn first and shown a moment later still gets its chart */
      setTimeout(drawCharts, 250);
      return self;
    };

    /* ── «طبقات از کاتالوگ»: the stage count picked as a catalogue model ──
       The list holds the models of the type chosen in the linked field
       («384/2 … 384/22»); with no type yet, every model, by type. Picking
       one writes the stage count here and the type into its own field, so
       the two never disagree with the catalogue. A number field is offered
       whole stage counts only; a choice field, the counts it lists. */
    function stagesFill(pick) {
      var fd = fieldByName(pick.name);
      if (!fd || !Catalogue.data) return;
      var typeRaw = currentValueOf(fd.stages_of);
      var type = typeRaw ? Catalogue.normType(typeRaw) : '';
      var allowed = null;
      if (['radio', 'select'].indexOf(fd.field_type) !== -1 && optionsFor(fd).length) {
        allowed = optionsFor(fd).map(function (o) { return Catalogue.normStages(o.value === undefined ? o : o.value); });
      }
      var models = Object.keys(Catalogue.data).map(function (k) {
        var p = k.split('|');
        return { key: k, type: p[0], stages: p[1], m: Catalogue.data[k] };
      }).filter(function (x) {
        if (type && x.type !== type) return false;
        if (fd.field_type === 'number' && !/^\d+$/.test(x.stages)) return false;
        if (allowed && allowed.indexOf(x.stages) === -1) return false;
        return true;
      });
      var num = function (v) { var n = parseFloat(v); return isNaN(n) ? 999 : n; };
      models.sort(function (a, b) {
        return a.type === b.type ? (num(a.stages) - num(b.stages) || (a.stages < b.stages ? -1 : 1))
          : (a.type < b.type ? -1 : 1);
      });
      var want = pick.dataset.want !== undefined ? pick.dataset.want : stagesOfValue(pick.value);
      var label = function (x) {
        return (x.m.title || (x.type + '/' + x.stages)) + (x.m.kw ? ' — ' + x.m.kw + ' kW' : '');
      };
      /* each option names its type too («384|10»): with no type chosen
         yet, «10» alone would be ten different models */
      var opt = function (x) {
        return '<option value="' + A.esc(x.type + '|' + x.stages) + '" data-type="' + A.esc(x.type) + '">' + A.esc(label(x)) + '</option>';
      };
      var html = '<option value="">' + (models.length ? '— انتخاب مدل (تیپ/طبقه) —' : '— مدلی برای این تیپ در کاتالوگ نیست —') + '</option>';
      if (type) html += models.map(opt).join('');
      else {
        var groups = {};
        models.forEach(function (x) { (groups[x.type] = groups[x.type] || []).push(x); });
        html += Object.keys(groups).map(function (t) {
          return '<optgroup label="تیپ ' + A.esc(t) + '">' + groups[t].map(opt).join('') + '</optgroup>';
        }).join('');
      }
      var known = models.some(function (x) { return x.stages === Catalogue.normStages(want); });
      if (want && !known) {
        html += '<option value="' + A.esc((type || '') + '|' + want) + '">' + A.esc((type ? type + '/' : '') + want) + ' — خارج از کاتالوگ</option>';
      }
      pick.innerHTML = html;
      if (want) {
        /* the model of the chosen type, or — no type yet — the first with that count */
        var match = Array.prototype.find.call(pick.options, function (o) {
          return o.value && Catalogue.normStages(stagesOfValue(o.value)) === Catalogue.normStages(want)
            && (!type || (o.dataset.type || type) === type);
        });
        if (match) pick.value = match.value;
      }
    }
    /* «384|10» → «10»: what the field stores is the stage count */
    function stagesOfValue(v) {
      v = String(v == null ? '' : v);
      var i = v.indexOf('|');
      return i === -1 ? v : v.slice(i + 1);
    }
    function stagesPicks() { return qsa('select.stages-pick'); }
    function wireStages() {
      var picks = stagesPicks();
      if (!picks.length) return;
      Catalogue.load().then(function () { stagesPicks().forEach(stagesFill); });
      picks.forEach(function (pick) {
        pick.addEventListener('change', function () {
          pick.dataset.want = stagesOfValue(pick.value);
          var chosen = pick.options[pick.selectedIndex];
          var fd = fieldByName(pick.name);
          var t = chosen && chosen.dataset.type;
          if (!fd || !t) return;
          var now = currentValueOf(fd.stages_of);
          if (Catalogue.normType(now) === t) return;
          var typeField = fieldByName(fd.stages_of);
          if (typeField && !typeField.read_only) {
            self.setFieldValue(typeField, t);
            var el = qs('#fld-' + fd.stages_of) || qs('input[name="' + fd.stages_of + '"]:checked');
            if (el) el.dispatchEvent(new Event('change', { bubbles: true }));
          }
        });
      });
    }
    /* the type changed: its stage lists follow */
    function stagesFollow(name) {
      stagesPicks().forEach(function (pick) {
        if (pick.dataset.stagesOf === name && Catalogue.data) stagesFill(pick);
      });
    }

    /* ── «بخش تکرارشونده»: points 1 to 5 of a test, one shown to start with ──
       Sections sharing a «گروه تکرارشونده» show the first one, every one
       that already holds an answer, and as many more as «➕» asks for; «✕»
       takes the last one away again with its answers. A pump test that is
       done in three points does not carry five sections of empty boxes. */
    var repeatShown = {};                // group → how many are open
    function repeatGroups() {
      var groups = {};
      qsa('.form-section[data-repeat]').forEach(function (sec) {
        (groups[sec.dataset.repeat] = groups[sec.dataset.repeat] || []).push(sec);
      });
      return groups;
    }
    function sectionHasValue(sec) {
      return Array.prototype.some.call(sec.querySelectorAll('input, select, textarea'), function (el) {
        if (el.readOnly && el.classList.contains('calc-output')) return false;
        if (el.type === 'radio' || el.type === 'checkbox') return el.checked;
        return el.type !== 'button' && String(el.value || '').trim() !== '';
      });
    }
    function setupRepeats() {
      var groups = repeatGroups();
      Object.keys(groups).forEach(function (g) {
        var list = groups[g], last = list[list.length - 1];
        var bar = document.createElement('div');
        bar.className = 'repeat-bar';
        bar.dataset.repeatBar = g;
        bar.innerHTML = '<button type="button" class="btn-sm btn-secondary repeat-add"></button>';
        last.parentNode.insertBefore(bar, last.nextSibling);
        bar.querySelector('.repeat-add').addEventListener('click', function () {
          repeatShown[g] = Math.min(list.length, (repeatShown[g] || 1) + 1);
          applyRepeats();
          var opened = list[repeatShown[g] - 1];
          var first = opened && opened.querySelector('input:not([readonly]), select, textarea');
          if (first) first.focus();
        });
        list.forEach(function (sec) {
          sec.querySelector('.repeat-del').addEventListener('click', function () {
            clearSection(sec);
            repeatShown[g] = Math.max(1, list.indexOf(sec));
            applyRepeats();
            recomputeFormulas();
          });
        });
      });
      applyRepeats();
    }
    function clearSection(sec) {
      sec.querySelectorAll('input, select, textarea').forEach(function (el) {
        if (el.classList.contains('calc-output')) return;
        if (el.type === 'radio' || el.type === 'checkbox') el.checked = false;
        else if (el.type !== 'button' && el.type !== 'file') el.value = '';
      });
      sec.querySelectorAll('[data-part-of]').forEach(function (el) { el.value = ''; });
    }
    function applyRepeats() {
      var groups = repeatGroups();
      Object.keys(groups).forEach(function (g) {
        var list = groups[g], filled = 0;
        list.forEach(function (sec, i) { if (sectionHasValue(sec)) filled = i + 1; });
        var n = Math.max(1, filled, repeatShown[g] || 1);
        repeatShown[g] = n;
        list.forEach(function (sec, i) {
          sec.classList.toggle('repeat-hidden', i >= n);
          sec.querySelector('.repeat-del').classList.toggle('hidden', !(i === n - 1 && i > 0));
        });
        var bar = qs('[data-repeat-bar="' + g + '"]');
        if (bar) {
          var next = list[n];
          bar.classList.toggle('hidden', !next);
          if (next) {
            var title = (next.querySelector('.sec-title-text') || {}).textContent || '';
            bar.querySelector('.repeat-add').textContent = '➕ افزودن «' + title + '»';
          }
          /* the bar follows the last open section */
          var lastOpen = list[n - 1];
          if (lastOpen && lastOpen.nextSibling !== bar) lastOpen.parentNode.insertBefore(bar, lastOpen.nextSibling);
        }
      });
    }
    self.applyRepeats = applyRepeats;

    /* «۳ مورد انتخاب شده» beside the help line, so a long list still shows at
       a glance whether anything was picked. */
    /* «مانع ارسال»: say at once that this answer stops the stage */
    function updateBlockNotes() {
      qsa('[data-block-note]').forEach(function (note) {
        var fd = fieldByName(note.dataset.blockNote);
        var have = valuesOf(note.dataset.blockNote);
        note.classList.toggle('hidden', !fd || !have.some(function (v) {
          return (fd.block_options || []).indexOf(v) !== -1;
        }));
      });
    }
    function updateChoiceCounts() {
      updateBlockNotes();
      qsa('[data-count]').forEach(function (badge) {
        var name = badge.dataset.count;
        var n = qsa('input[name="' + name + '"]:checked').length;
        badge.textContent = n ? ' ' + J.toFaDigits(n) + ' مورد انتخاب شده' : '';
        badge.classList.toggle('has', !!n);
      });
    }
    self.updateChoiceCounts = updateChoiceCounts;

    function applyDefaults() {
      if (options.skipDefaults) return;
      (schema.sections || []).forEach(function (section) {
        (section.fields || []).forEach(function (field) {
          if (field.default_value && String(field.default_value).charAt(0) !== '=') {
            self.setFieldValue(field, field.default_value);
          }
        });
      });
    }

    /* Clicking the already-selected radio clears it — the only way back to
       "not answered" now that the blank option is gone. */
    function enableRadioClearing() {
      root.addEventListener('mousedown', function (ev) {
        var label = ev.target.closest('.btn-group label');
        if (!label || !root.contains(label)) return;
        var input = label.querySelector('input[type="radio"]');
        if (input && input.checked) {
          setTimeout(function () {
            input.checked = false;
            input.dispatchEvent(new Event('change', { bubbles: true }));
          }, 0);
        }
      });
    }

    /* ── conditional fields ───────────────────────────────────────────── */
    function currentValueOf(name) {
      if (qs('[data-numbers="' + name + '"]')) {
        var parts = numbersOf(name);
        return parts.some(function (x) { return x !== ''; }) ? parts.join(' / ') : '';
      }
      var picked = qs('input[name="' + name + '"]:checked');
      if (picked) return picked.value;
      var input = qs('#fld-' + name);
      if (input && input.classList.contains('stages-pick')) return stagesOfValue(input.value);
      return input ? input.value.trim() : '';
    }
    self.currentValueOf = currentValueOf;

    /* Every value the source field is holding right now.

       «علت خرابی» is a multi-select: the operator can tick سوختن الکتروپمپ and
       هوادهی together, and both of their forms have to open. So a rule is met
       when the source *contains* the value, not only when it equals it — with
       a single-choice field the two readings are the same thing. */
    function valuesOf(name) {
      var ticked = checkedValues(name);
      if (ticked.length) return ticked;
      var one = currentValueOf(name);
      return one ? [one] : [];
    }

    /* Several questions may open one form («any»): shown when any of them
       holds. Only the questions actually on this page are asked. */
    function sourcesHere(rule) {
      return (rule.any || [rule]).filter(function (r) {
        return !!qs('[data-wrap="' + r.on + '"]');
      });
    }

    function ruleIsMet(rule) {
      if (rule.any) {
        return sourcesHere(rule).some(function (r) { return oneRuleIsMet(r); });
      }
      return oneRuleIsMet(rule);
    }

    function oneRuleIsMet(rule) {
      /* «a|b|c»: any one of several values opens it — two causes can share
         one form. An empty list is a form linked to nothing yet. */
      var wanted = String(rule.value || '').split('|').filter(Boolean);
      var have = valuesOf(rule.on);
      if (wanted.indexOf('*') !== -1) return have.some(function (h) { return String(h).trim() !== ''; });
      return wanted.some(function (w) { return have.indexOf(w) !== -1; });
    }

    self.applyConditional = function () {
      (schema.conditional || []).forEach(function (rule) {
        if (rule.section) { applySectionRule(rule); return; }
        var wrap = qs('[data-wrap="' + rule.field + '"]');
        if (!wrap) return;
        /* A rule can only be judged where its source field is. On a workflow
           stage «علت خرابی» is drawn without «نوع عملیات» beside it, because
           the server already decided the branch and either sent the field or
           did not. Re-deciding it here from a second copy of the answer is how
           the one field a stage exists to collect ended up hidden behind its
           own heading. */
        if (!sourcesHere(rule).length) return;
        var show = ruleIsMet(rule);
        var was = !wrap.classList.contains('hidden');
        wrap.classList.toggle('hidden', !show);
        if (!show) clearField(rule.field);
        else if (!was) restoreDefault(rule.field);
      });
      if (options.onConditional) options.onConditional(self);
    };

    /* A whole section appears or goes away together — the parameters of one
       علت خرابی are one block, and clearing them one field at a time would
       leave half-answered readings behind when the cause is unticked. */
    function applySectionRule(rule) {
      var block = qs('[data-section="' + rule.section + '"]');
      if (!block) return;
      if (!sourcesHere(rule).length) return;
      var show = ruleIsMet(rule);
      var was = !block.classList.contains('hidden');
      block.classList.toggle('hidden', !show);
      if (show) {
        if (!was) (rule.fields || []).forEach(restoreDefault);   // reopened: defaults back
        return;
      }
      (rule.fields || []).forEach(clearField);
    }

    /* A hidden answer is dropped; a reopened field starts from its default again. */
    function clearField(name) {
      qsa('input[name="' + name + '"]').forEach(function (i) { i.checked = false; });
      var free = qs('#fld-' + name);
      if (free) free.value = '';
      qsa('[data-part-of="' + name + '"]').forEach(function (i) { i.value = ''; });
      var other = qs('[data-other="' + name + '"]');
      if (other) other.value = '';
    }
    function restoreDefault(name) {
      var fd = fieldByName(name);
      if (!fd) return;
      var now = readField(fd);
      if (!(now === '' || now === false || now === null || now === undefined
            || (Array.isArray(now) && !now.length))) return;
      /* A value the well's history or a reference bank suggested while this
         block was still closed (the flow-test points of «انتخاب پمپ», say)
         comes back with the block, rather than having been dropped with it. */
      var hint = suggested[name];
      if (hint !== undefined && hint !== null && hint !== '') {
        self.setFieldValue(fd, hint);
        return;
      }
      if (options.skipDefaults || !fd.default_value
          || String(fd.default_value).charAt(0) === '=') return;
      self.setFieldValue(fd, fd.default_value);
    }

    function onFieldChanged(ev) {
      var name = ev.target.name || (ev.target.id || '').replace(/^fld-/, '');
      if (!name) return;
      stagesFollow(name);
      if ((schema.conditional || []).some(function (r) {
            return (r.any || [r]).some(function (x) { return x.on === name; });
          })) {
        self.applyConditional();
      }
      if (name === 'well') {
        fillCentreFromWell(ev.target.value);
        if (options.onWellPicked) options.onWellPicked(ev.target.value);
      }
      if (options.onChange) options.onChange(name, self);
    }

    /* Picking a well fills in its centre, and then closes it.

       The register already knows which centre a well belongs to, so asking is
       both extra work and a chance to get it wrong. Clearing the well opens it
       again — a well nobody has chosen has no centre to impose. */
    async function fillCentreFromWell(name) {
      name = (name || '').trim();
      if (!name) { lockCentre(null); return; }
      try {
        var res = await A.api.get('/api/wells?all=1&limit=1&q='
                                  + encodeURIComponent(name));
        var well = (res.data || []).find(function (w) { return w.name === name; });
        if (!well || !well.center_value) { lockCentre(null); return; }
        var radio = qs('input[name="center"][value="'
                       + CSS.escape(well.center_value) + '"]');
        if (!radio) { lockCentre(null); return; }
        if (!radio.checked) {
          radio.checked = true;
          radio.dispatchEvent(new Event('change', { bubbles: true }));
          flash(qs('[data-wrap="center"]'));
        }
        lockCentre(well.name);
      } catch (err) { /* leave the centre for the operator to pick */ }
    }

    function lockCentre(wellName) {
      var wrap = qs('[data-wrap="center"]');
      if (!wrap) return;
      var locked = !!wellName;
      wrap.classList.toggle('from-well', locked);
      qsa('input[name="center"]').forEach(function (input) {
        // A disabled radio is not submitted, so keep the chosen one live and
        // close only the others; the group then cannot be changed either way.
        input.disabled = locked && !input.checked;
        input.readOnly = locked;
      });
      var note = wrap.querySelector('.centre-note');
      if (locked && !note) {
        note = document.createElement('span');
        note.className = 'hint centre-note';
        wrap.appendChild(note);
      }
      if (note) {
        note.textContent = locked
          ? 'مرکز چاه «' + wellName + '» است و از فهرست چاه‌ها خوانده می‌شود؛ '
            + 'برای تغییرش چاه دیگری انتخاب کنید.'
          : '';
        note.hidden = !locked;
      }
    }

    function flash(wrap) {
      if (!wrap) return;
      wrap.classList.add('auto-filled');
      setTimeout(function () { wrap.classList.remove('auto-filled'); }, 1600);
    }
    self.flash = flash;

    /* ── autocomplete ─────────────────────────────────────────────────── */
    function setupAutocomplete(input) {
      var list = input.parentNode.querySelector('.autocomplete-list');
      var source = input.dataset.autocomplete;

      var search = A.debounce(async function () {
        var value = input.value.trim();
        if (value.length < 1) { list.classList.remove('show'); return; }
        var items = [];
        if (source === 'wells' || source === 'well') {
          try {
            var res = await A.api.get('/api/wells?limit=15&q='
                                      + encodeURIComponent(value));
            items = res.data.map(function (w) {
              var tags = [];
              if (w.pm_code) tags.push('کد PM: ' + w.pm_code);
              if (w.well_class) tags.push('کلاسه: ' + w.well_class);
              if (w.center) tags.push(w.center);
              if (!w.is_verified) tags.push('تأییدنشده');
              return { value: w.name, label: w.name, id: w.id,
                       meta: tags.join(' · ') };
            });
          } catch (err) { items = []; }
        } else {
          items = ((schema.lookups || {})[source] || []).filter(function (opt) {
            return opt.value.indexOf(value) >= 0 || opt.label.indexOf(value) >= 0;
          }).slice(0, 15).map(function (opt) {
            return { value: opt.value, label: opt.label, id: opt.id, meta: '' };
          });
        }
        if (!items.length) {
          list.innerHTML = '<div class="autocomplete-item create">'
            + '«' + A.esc(value) + '» در فهرست نیست — با ثبت رکورد افزوده می‌شود</div>';
          list.classList.add('show');
          return;
        }
        list.innerHTML = items.map(function (item) {
          return '<div class="autocomplete-item" data-value="' + A.esc(item.value) + '">'
            + A.esc(item.label)
            + (item.meta ? ' <span class="meta">— ' + A.esc(item.meta) + '</span>' : '')
            + '</div>';
        }).join('');
        list.classList.add('show');
      }, 180);

      input.addEventListener('input', search);
      input.addEventListener('focus', search);
      list.addEventListener('click', function (ev) {
        var item = ev.target.closest('.autocomplete-item[data-value]');
        if (!item) return;
        input.value = item.dataset.value;
        list.classList.remove('show');
        input.dispatchEvent(new Event('change', { bubbles: true }));
        if (source === 'wells' || source === 'well') showWellBadge(input);
      });
      if (source === 'wells' || source === 'well') {
        input.addEventListener('change', function () { showWellBadge(input); });
      }
      document.addEventListener('click', function (ev) {
        if (!input.parentNode.contains(ev.target)) list.classList.remove('show');
      });
    }

    async function showWellBadge(input) {
      var wrap = input.closest('.field');
      if (!wrap) return;
      var badge = wrap.querySelector('.well-badge');
      if (!badge) {
        badge = A.el('div', { class: 'well-badge hint' });
        wrap.appendChild(badge);
      }
      var name = input.value.trim();
      if (!name) { badge.textContent = ''; return; }
      try {
        var res = await A.api.get('/api/wells?all=1&limit=1&q='
                                  + encodeURIComponent(name));
        var w = (res.data || []).find(function (x) { return x.name === name; });
        if (!w) {
          badge.innerHTML = '<span class="badge warn">چاه جدید — با ثبت رکورد افزوده می‌شود</span>';
          return;
        }
        var parts = [];
        if (w.pm_code) parts.push('<span class="badge">کد PM: ' + A.esc(w.pm_code) + '</span>');
        if (w.well_class) parts.push('<span class="badge">کلاسه: ' + A.esc(w.well_class) + '</span>');
        if (w.center) parts.push('<span class="badge muted">' + A.esc(w.center) + '</span>');
        if (!w.pm_code && !w.well_class) {
          parts.push('<span class="badge muted">کد PM ثبت نشده</span>');
        }
        badge.innerHTML = parts.join(' ');
      } catch (err) { badge.textContent = ''; }
    }
    self.showWellBadge = showWellBadge;

    /* ── reading / writing ────────────────────────────────────────────── */
    function checkedValues(name) {
      return qsa('input[name="' + name + '"]:checked')
        .map(function (i) { return i.value; }).filter(Boolean);
    }

    function otherValue(name) {
      var input = qs('[data-other="' + name + '"]');
      return input ? input.value.trim() : '';
    }
    self.otherValue = otherValue;

    function hiddenFields() {
      var hidden = {};
      (schema.conditional || []).forEach(function (rule) {
        if (rule.section) {
          var block = qs('[data-section="' + rule.section + '"]');
          if (block && block.classList.contains('hidden')) {
            (rule.fields || []).forEach(function (n) { hidden[n] = true; });
          }
          return;
        }
        var wrap = qs('[data-wrap="' + rule.field + '"]');
        if (wrap && wrap.classList.contains('hidden')) hidden[rule.field] = true;
      });
      return hidden;
    }

    function readField(field) {
      var name = field.field_name;
      if (field.stages_of && !field.read_only) {
        var pick = qs('#fld-' + name);
        return pick ? stagesOfValue(pick.value) : '';
      }
      if (field.field_type === 'file') {
        return (field.files || []).map(function (a) { return a.id; });
      }
      if (field.field_type === 'numbers') {
        var parts = numbersOf(name);
        return parts.some(function (x) { return x !== ''; }) ? parts : [];
      }
      if (field.field_type === 'wh_lines') {
        if (whCfg(field).mode === 'parts') {
          var pw = qs('[data-whp="' + name + '"]');
          return pw && pw.dataset.drawn ? whpRead(name) : (whValues[name] || []);
        }
        return qs('[data-wh="' + name + '"] tbody tr') ? whRead(name) : (whValues[name] || []);
      }
      if (field.field_type === 'radio') {
        var value = checkedValues(name)[0] || '';
        var other = otherValue(name);
        return other || value;
      }
      if (['checkbox', 'multiselect', 'checklist'].includes(field.field_type)) {
        if (optionsFor(field).length) {
          var values = checkedValues(name);
          var extra = otherValue(name);
          if (extra) {
            values = values.concat(extra.split(',').map(function (v) {
              return v.trim();
            }).filter(Boolean));
          }
          return values;
        }
        var box = qs('#fld-' + name);
        return box ? box.checked : false;
      }
      var input = qs('#fld-' + name);
      return input ? input.value.trim() : '';
    }

    self.eachField = function (fn) {
      (schema.sections || []).forEach(function (section) {
        (section.fields || []).forEach(function (field) { fn(field, section); });
      });
    };

    /* Flat mode (workflow): one key per field name, exactly as the stage was
       drawn. Shaped mode (entry page): the record API's own shape. */
    self.collect = function () {
      var hidden = hiddenFields();
      if (flat) {
        var out = {};
        self.eachField(function (field) {
          if (hidden[field.field_name] || field.read_only || field.field_type === 'chart') return;
          out[field.field_name] = readField(field);
        });
        var fOther = otherValue('failure');
        if (fOther) out.failure_other = fOther;
        return out;
      }
      var payload = { dynamic: {} };
      self.eachField(function (field) {
        var name = field.field_name;
        if (hidden[name] || field.read_only || field.field_type === 'chart') return;
        var value = readField(field);
        if (field.model_attr) {
          if (name === 'op_jdate') { payload.op_jdate = value; return; }
          if (name === 'well') { payload.well = value; return; }
          /* Choice columns are sent by *value*, under the short key. */
          var key = field.model_attr.endsWith('_id')
            ? field.model_attr.slice(0, -3) : field.model_attr;
          payload[key] = value;
        } else if (TAG_FIELDS.includes(name)) {
          payload[name] = value;
        } else {
          payload.dynamic[name] = value;
        }
      });
      var failureOther = otherValue('failure');
      if (failureOther) payload.failure_other = failureOther;
      return payload;
    };

    self.setFieldValue = function (field, value) {
      var name = field.field_name;
      if (field.stages_of && !field.read_only) {
        var pick = qs('#fld-' + name);
        if (pick) {
          var want = value === null || value === undefined ? '' : String(value);
          pick.dataset.want = want;
          if (Catalogue.data) stagesFill(pick);
          else if (want) {
            var opt = document.createElement('option');
            opt.value = '|' + want; opt.textContent = want;
            pick.appendChild(opt);
            pick.value = opt.value;
          }
        }
        return;
      }
      if (field.field_type === 'file') return;          // the upload list is the value
      if (field.field_type === 'formula' || field.field_type === 'chart') { recomputeFormulas(); return; }
      if (field.field_type === 'wh_lines') {
        var rows = value;
        if (typeof rows === 'string') { try { rows = JSON.parse(rows); } catch (e) { rows = []; } }
        whValues[name] = Array.isArray(rows) ? rows : [];
        if (Warehouse.data) { if (whCfg(field).mode === 'parts') whpDraw(name); else whDraw(name); }
        return;
      }
      if (field.field_type === 'numbers') {
        var vals = splitNumbers(value);
        qsa('[data-part-of="' + name + '"]').forEach(function (inp, k) { inp.value = vals[k] || ''; });
        return;
      }
      if (field.field_type === 'radio') {
        var radio = qs('input[name="' + name + '"][value="'
                       + CSS.escape(String(value == null ? '' : value)) + '"]');
        if (radio) { radio.checked = true; return; }
        var other = qs('[data-other="' + name + '"]');
        if (other && value) other.value = value;
        return;
      }
      if (['checkbox', 'multiselect', 'checklist'].includes(field.field_type)) {
        if (optionsFor(field).length) {
          var wanted = Array.isArray(value) ? value
            : String(value || '').split(',').map(function (v) { return v.trim(); });
          var unmatched = [];
          qsa('input[name="' + name + '"]').forEach(function (box) {
            box.checked = wanted.includes(box.value);
          });
          wanted.filter(Boolean).forEach(function (v) {
            if (!qs('input[name="' + name + '"][value="' + CSS.escape(v) + '"]')) {
              unmatched.push(v);
            }
          });
          var extra = qs('[data-other="' + name + '"]');
          if (extra && unmatched.length) extra.value = unmatched.join('، ');
        } else {
          var box2 = qs('#fld-' + name);
          if (box2) box2.checked = !!value && value !== '0' && value !== 'false';
        }
        return;
      }
      var input = qs('#fld-' + name);
      if (input) input.value = value === null || value === undefined ? '' : value;
    };

    /* Fill from a flat {field_name: value} map, skipping names this form does
       not show. Used for the workflow payload and for the «…قبلی» suggestions. */
    self.setValues = function (values, opts) {
      opts = opts || {};
      self.eachField(function (field) {
        var name = field.field_name;
        if (!Object.prototype.hasOwnProperty.call(values, name)) return;
        /* suggestions are kept for fields whose block opens later */
        if (opts.onlyEmpty) suggested[name] = values[name];
        if (opts.onlyEmpty && String(readField(field) || '').length) return;
        /* nothing saved yet: the field keeps its «مقدار پیش‌فرض» */
        if ((values[name] === null || values[name] === undefined || values[name] === '')
            && field.default_value && String(field.default_value).charAt(0) !== '=') return;
        self.setFieldValue(field, values[name]);
        if (opts.flash) flash(qs('[data-wrap="' + name + '"]'));
      });
      self.applyConditional();
      applyRepeats();
      updateChoiceCounts();
      recomputeFormulas();
    };

    self.clearErrors = function () {
      qsa('.field.has-error').forEach(function (f) { f.classList.remove('has-error'); });
      qsa('.field .err').forEach(function (e) {
        e.classList.add('hidden'); e.textContent = '';
      });
    };

    self.showErrors = function (fields) {
      self.clearErrors();
      var first = null;
      Object.keys(fields || {}).forEach(function (name) {
        var wrap = qs('[data-wrap="' + name + '"]');
        if (!wrap) return;
        wrap.classList.add('has-error');
        var err = wrap.querySelector('.err');
        if (err) { err.textContent = fields[name]; err.classList.remove('hidden'); }
        if (!first) first = wrap;
      });
      if (first) first.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return first;
    };

    self.clear = function () {
      suggested = {};
      qsa('input, textarea, select').forEach(function (el) {
        if (el.type === 'radio' || el.type === 'checkbox') el.checked = false;
        else el.value = '';
      });
      self.clearErrors();
      applyDefaults();
      self.applyConditional();
      repeatShown = {};
      applyRepeats();
      updateChoiceCounts();
    };

    self.lock = function () {
      qsa('input, textarea, select').forEach(function (el) { el.disabled = true; });
    };

    self.attachAutocompleteTo = setupAutocomplete;
    self.qs = qs;
    self.qsa = qsa;
  }

  window.FormEngine = function (options) { return new FormEngine(options); };
  window.FormEngine.Catalogue = Catalogue;
  window.FormEngine.Warehouse = Warehouse;
  window.FormEngine.drawStaticChart = drawStaticChart;
  window.FormEngine.loadEcharts = loadEcharts;

  /* A single input outside any form that still wants the well picker — the
     «شروع فرایند» dialog, for one. */
  window.FormEngine.attachAutocomplete = function (input, lookups) {
    var engine = new FormEngine({
      root: input.closest('.autocomplete-wrapper') || input.parentNode,
      schema: { sections: [], lookups: lookups || {} },
    });
    engine.attachAutocompleteTo(input);
    return engine;
  };
})();
