(function () {
  'use strict';
  var A = window.App, J = window.Jalali;
  var current = null;

  function filters() {
    return {
      date_from: A.qs('#f-date-from').value.trim(),
      date_to: A.qs('#f-date-to').value.trim(),
      year: A.qs('#f-year').value, month: A.qs('#f-month').value,
      center: A.qs('#f-center').value, contractor: A.qs('#f-contractor').value,
      operation: A.qs('#f-operation').value, well: A.qs('#f-well').value.trim()
    };
  }

  async function run(key) {
    current = key;
    var panel = A.qs('#report-panel');
    panel.classList.remove('hidden');
    A.qs('#report-body').innerHTML =
      '<tr><td class="table-empty">در حال محاسبه…</td></tr>';
    panel.scrollIntoView({ behavior: 'smooth' });
    try {
      var res = await A.api.get('/api/reports/' + key + '?' + A.serializeQuery(filters()));
      render(res.data);
    } catch (err) {
      A.qs('#report-body').innerHTML = '<tr><td class="table-empty">'
        + A.esc(err.message) + '</td></tr>';
      A.toast(err.message, 'error');
    }
  }

  function render(report) {
    A.qs('#report-title').textContent = report.title;
    A.qs('#report-desc').textContent = report.description || '';

    var summary = Object.entries(report.summary || {});
    A.qs('#report-summary').innerHTML = summary.length
      ? '<div class="summary-strip">' + summary.map(function (e) {
          return '<span>' + A.esc(labelFor(e[0])) + ': <b>'
            + A.esc(e[1] === null ? '—' : e[1]) + '</b></span>';
        }).join('') + '</div>'
      : '';

    A.qs('#report-head').innerHTML = report.columns
      .map(function (c) { return '<th>' + A.esc(c.label) + '</th>'; }).join('');
    A.qs('#report-body').innerHTML = report.rows.length
      ? report.rows.map(function (row) {
          return '<tr>' + report.columns.map(function (c) {
            var v = row[c.key];
            if (Array.isArray(v)) v = v.join('، ');
            if (v === null || v === undefined || v === '') v = '—';
            return '<td title="' + A.esc(v) + '">' + A.esc(v) + '</td>';
          }).join('') + '</tr>';
        }).join('')
      : '<tr><td colspan="' + report.columns.length
        + '" class="table-empty">داده‌ای برای این فیلترها یافت نشد</td></tr>';

    var chartCard = A.qs('#report-chart-card');
    if (report.chart && report.chart.labels && report.chart.labels.length) {
      chartCard.classList.remove('hidden');
      A.renderBarChart('report-chart', report.chart.labels.map(function (label, i) {
        return { label: label, value: report.chart.values[i] };
      }));
    } else { chartCard.classList.add('hidden'); }
  }

  var LABELS = {
    total: 'مجموع', count: 'تعداد', groups: 'تعداد گروه', wells: 'تعداد چاه',
    years: 'تعداد سال', tests: 'تعداد آزمایش', compared: 'تعداد مقایسه',
    below_design: 'کمتر از طراحی', avg_difference: 'میانگین اختلاف',
    avg_test_flow: 'میانگین دبی آزمایش', combinations: 'ترکیب‌ها',
    from: 'از تاریخ', to: 'تا تاریخ'
  };
  function labelFor(key) { return LABELS[key] || key; }

  async function loadFilters() {
    var res = await A.api.get('/api/lookups');
    [['center', 'center'], ['contractor', 'contractor'], ['operation', 'operation']]
      .forEach(function (pair) {
        var select = A.qs('#f-' + pair[0]);
        (res.data[pair[1]] || []).forEach(function (item) {
          select.appendChild(A.el('option', { value: item.value, text: item.label }));
        });
      });
    var y = J.today()[0], yearSelect = A.qs('#f-year');
    for (var i = y; i >= y - 12; i--) {
      yearSelect.appendChild(A.el('option', { value: i, text: i }));
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    A.qsa('.jdate').forEach(function (input) { J.attach(input); });
    loadFilters();
    A.qsa('[data-report]').forEach(function (card) {
      card.addEventListener('click', function () { run(card.dataset.report); });
    });
    A.qsa('[data-fmt]').forEach(function (button) {
      button.addEventListener('click', function () {
        if (!current) return;
        A.download('/api/reports/' + current + '/export.' + button.dataset.fmt
          + '?' + A.serializeQuery(filters()));
      });
    });
    A.qs('#btn-print').addEventListener('click', function () {
      if (!current) return;
      window.open('/print/report/' + current + '?' + A.serializeQuery(filters()), '_blank');
    });
    A.qsa('#f-year,#f-month,#f-center,#f-contractor,#f-operation').forEach(function (s) {
      s.addEventListener('change', function () { if (current) run(current); });
    });
  });
})();
