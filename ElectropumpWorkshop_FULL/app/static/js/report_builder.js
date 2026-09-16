(function () {
  'use strict';
  var A = window.App, J = window.Jalali;
  var meta = null, fields = [], last = null;

  function spec() {
    return {
      dataset: A.qs('#b-dataset').value,
      limit: +A.qs('#b-limit').value,
      base_filters: {
        date_from: A.qs('#b-date-from').value.trim(),
        date_to: A.qs('#b-date-to').value.trim(),
        year: A.qs('#b-year').value,
        center: A.qs('#b-center').value
      },
      group_by: A.qsa('#b-groups input:checked').map(function (i) { return i.value; }),
      fields: A.qsa('#b-fields input:checked').map(function (i) { return i.value; }),
      aggregations: A.qsa('#b-aggs .agg-row').map(function (row) {
        return { fn: row.querySelector('.agg-fn').value,
                 field: row.querySelector('.agg-field').value || null };
      }),
      filters: A.qsa('#b-filters .filter-row-item').map(function (row) {
        return { field: row.querySelector('.flt-field').value,
                 op: row.querySelector('.flt-op').value,
                 value: row.querySelector('.flt-value').value.trim() };
      }).filter(function (f) { return f.field; }),
      sort_by: A.qs('#b-sort').value,
      sort_dir: A.qs('#b-dir').value
    };
  }

  function fieldOptions(includeBlank) {
    return (includeBlank ? '<option value="">—</option>' : '')
      + fields.map(function (f) {
          return '<option value="' + A.esc(f.key) + '">' + A.esc(f.label) + '</option>';
        }).join('');
  }

  function addAgg() {
    var row = A.el('div', { class: 'agg-row field-group cols-3 mb-1' });
    row.innerHTML = '<div class="field"><label>تابع</label>'
      + '<select class="agg-fn">' + meta.aggregations.map(function (a) {
          return '<option value="' + A.esc(a.key) + '">' + A.esc(a.label) + '</option>';
        }).join('') + '</select></div>'
      + '<div class="field"><label>روی فیلد</label>'
      + '<select class="agg-field">' + fieldOptions(true) + '</select></div>'
      + '<div class="field" style="justify-content:flex-end">'
      + '<button class="btn-ghost agg-del" type="button">حذف</button></div>';
    row.querySelector('.agg-del').addEventListener('click', function () { row.remove(); });
    A.qs('#b-aggs').appendChild(row);
  }

  function addFilter() {
    var row = A.el('div', { class: 'filter-row-item field-group cols-3 mb-1' });
    row.innerHTML = '<div class="field"><label>فیلد</label>'
      + '<select class="flt-field">' + fieldOptions(true) + '</select></div>'
      + '<div class="field"><label>عملگر</label>'
      + '<select class="flt-op">' + meta.operators.map(function (o) {
          return '<option value="' + A.esc(o.key) + '">' + A.esc(o.label) + '</option>';
        }).join('') + '</select></div>'
      + '<div class="field"><label>مقدار</label>'
      + '<div style="display:flex;gap:6px"><input type="text" class="flt-value">'
      + '<button class="btn-ghost flt-del" type="button">حذف</button></div></div>';
    row.querySelector('.flt-del').addEventListener('click', function () { row.remove(); });
    A.qs('#b-filters').appendChild(row);
  }

  function render(result) {
    last = result;
    A.qs('#b-result').classList.remove('hidden');
    A.qs('#b-count').textContent = J.toFaDigits(result.rows.length) + ' سطر';
    A.qs('#b-head').innerHTML = result.columns
      .map(function (c) { return '<th>' + A.esc(c.label) + '</th>'; }).join('');
    A.qs('#b-body').innerHTML = result.rows.length
      ? result.rows.map(function (row) {
          return '<tr>' + result.columns.map(function (c) {
            var v = row[c.key];
            return '<td>' + A.esc(v === null || v === undefined ? '—' : v) + '</td>';
          }).join('') + '</tr>';
        }).join('')
      : '<tr><td colspan="' + result.columns.length
        + '" class="table-empty">نتیجه‌ای یافت نشد</td></tr>';

    var chartCard = A.qs('#b-chart-card');
    if (result.chart && result.chart.labels && result.chart.labels.length) {
      chartCard.classList.remove('hidden');
      A.renderBarChart('b-chart', result.chart.labels.map(function (label, i) {
        return { label: label, value: result.chart.values[i] };
      }));
    } else { chartCard.classList.add('hidden'); }

    /* Sorting can only target a column the result actually has. */
    var sort = A.qs('#b-sort');
    var chosen = sort.value;
    sort.innerHTML = '<option value="">پیش‌فرض</option>'
      + result.columns.map(function (c) {
          return '<option value="' + A.esc(c.key) + '">' + A.esc(c.label) + '</option>';
        }).join('');
    sort.value = chosen;
  }

  async function run() {
    var button = A.qs('#b-run');
    button.disabled = true;
    try {
      var res = await A.api.post('/api/reports/builder', spec());
      render(res.data);
    } catch (err) {
      A.toast(err.message, 'error');
    } finally { button.disabled = false; }
  }

  document.addEventListener('DOMContentLoaded', async function () {
    A.qsa('.jdate').forEach(function (input) { J.attach(input); });
    try {
      var res = await A.api.get('/api/reports');
      meta = res.data;
      var datasetSelect = A.qs('#b-dataset');
      Object.entries(meta.datasets).forEach(function (entry) {
        datasetSelect.appendChild(A.el('option',
          { value: entry[0], text: entry[1].label }));
      });
      fields = meta.datasets[datasetSelect.value].fields;

      A.qs('#b-groups').innerHTML = fields.map(function (f) {
        return '<label><input type="checkbox" value="' + A.esc(f.key) + '">'
          + '<span class="btn-opt">' + A.esc(f.label) + '</span></label>';
      }).join('');
      A.qs('#b-fields').innerHTML = fields.map(function (f) {
        return '<label><input type="checkbox" value="' + A.esc(f.key) + '">'
          + '<span class="btn-opt">' + A.esc(f.label) + '</span></label>';
      }).join('');
      A.qs('#b-sort').innerHTML = '<option value="">پیش‌فرض</option>' + fieldOptions(false);
      addAgg();

      var lookups = await A.api.get('/api/lookups');
      (lookups.data.center || []).forEach(function (item) {
        A.qs('#b-center').appendChild(
          A.el('option', { value: item.value, text: item.label }));
      });
      var y = J.today()[0];
      for (var i = y; i >= y - 12; i--) {
        A.qs('#b-year').appendChild(A.el('option', { value: i, text: i }));
      }
    } catch (err) { A.toast(err.message, 'error'); return; }

    A.qs('#b-add-agg').addEventListener('click', addAgg);
    A.qs('#b-add-filter').addEventListener('click', addFilter);
    A.qs('#b-run').addEventListener('click', run);
    A.qs('#b-reset').addEventListener('click', function () {
      A.qsa('#b-groups input, #b-fields input').forEach(function (i) { i.checked = false; });
      A.qs('#b-aggs').innerHTML = '';
      A.qs('#b-filters').innerHTML = '';
      addAgg();
      A.qs('#b-result').classList.add('hidden');
    });
    A.qsa('[data-fmt]').forEach(function (button) {
      button.addEventListener('click', function () {
        A.downloadPost('/api/reports/builder/export.' + button.dataset.fmt, spec());
      });
    });
  });
})();
