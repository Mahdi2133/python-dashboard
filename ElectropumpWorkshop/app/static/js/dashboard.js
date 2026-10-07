(function () {
  'use strict';
  var A = window.App;

  function filters() {
    return {
      date_from: A.qs('#f-date-from').value.trim(),
      date_to: A.qs('#f-date-to').value.trim(),
      year: A.qs('#f-year').value,
      center: A.qs('#f-center').value,
      operation: A.qs('#f-operation').value
    };
  }

  async function load() {
    var grid = A.qs('#stats-grid');
    grid.innerHTML = '<div class="loading">در حال بارگذاری</div>';
    try {
      var res = await A.api.get('/api/dashboard?' + A.serializeQuery(filters()));
      var data = res.data;
      grid.innerHTML = data.stats.map(function (s) {
        return '<div class="stat-card" style="border-inline-start-color:' + A.esc(s.color) + '">'
          + '<div class="stat-icon">' + A.esc(s.icon) + '</div>'
          + '<div class="stat-info"><h3>' + A.fmtNumber(s.value) + '</h3>'
          + '<p>' + A.esc(s.label) + '</p></div></div>';
      }).join('');
      Object.entries(data.charts).forEach(function (entry) {
        A.renderBarChart('chart-' + entry[0], entry[1]);
      });
      /* charts of the process forms (اقدام کارشناس، علت ایراد برقی، …) */
      var extra = A.qs('#process-charts');
      if (extra) {
        extra.innerHTML = (data.process_charts || []).map(function (c) {
          return '<div class="chart-card"><h3>📌 ' + A.esc(c.title) + '</h3>'
            + '<div class="bar-chart" id="chart-p-' + A.esc(c.key) + '"></div></div>';
        }).join('');
        (data.process_charts || []).forEach(function (c) {
          A.renderBarChart('chart-p-' + c.key, c.data);
        });
      }
    } catch (err) {
      grid.innerHTML = '<div class="alert error">' + A.esc(err.message) + '</div>';
      A.toast(err.message, 'error');
    }
  }

  async function loadFilterOptions() {
    try {
      var res = await A.api.get('/api/lookups');
      ['center', 'operation'].forEach(function (code) {
        var select = A.qs('#f-' + code);
        (res.data[code] || []).forEach(function (item) {
          select.appendChild(A.el('option', { value: item.value, text: item.label }));
        });
      });
      var today = window.Jalali.today()[0];
      var yearSelect = A.qs('#f-year');
      for (var y = today; y >= today - 12; y--) {
        yearSelect.appendChild(A.el('option', { value: y, text: y }));
      }
    } catch (err) { /* filters stay empty; the dashboard still loads */ }
  }

  document.addEventListener('DOMContentLoaded', function () {
    A.qsa('.jdate').forEach(function (input) { window.Jalali.attach(input); });
    A.qs('#btn-apply').addEventListener('click', load);
    A.qsa('#f-year,#f-center,#f-operation').forEach(function (select) {
      select.addEventListener('change', load);
    });
    loadFilterOptions().then(load);
  });
})();
