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
      computed: A.qsa('#b-calcs .calc-row').map(function (row) {
        return {
          label: row.querySelector('.calc-label').value.trim(),
          fn: row.querySelector('.calc-fn').value,
          fields: (row.picked || []).slice(),
          decimals: +row.querySelector('.calc-dec').value,
          suffix: row.querySelector('.calc-suffix').value.trim()
        };
      }).filter(function (c) { return c.fields.length; }),
      sort_by: A.qs('#b-sort').value,
      sort_dir: A.qs('#b-dir').value
    };
  }

  /* A calculated column: a name, an operation, and the numeric fields it runs
     over. The field list is every numeric field the form currently has — the
     parameters of each علت خرابی included — so a reading added this morning
     can be put in a calculation this afternoon. The order matters for the
     operations that say so («اولی منهای بقیه»), so the picks are listed in the
     order they were ticked. */
  function numericFields() {
    return fields.filter(function (f) {
      return f.numeric || ['number', 'int'].indexOf(f.kind) !== -1;
    });
  }

  function addCalc() {
    var row = A.el('div', { class: 'calc-row card-soft mb-1' });
    var nums = numericFields();
    row.innerHTML = '<div class="field-group cols-3">'
      + '<div class="field"><label>نام ستون</label>'
      + '<input type="text" class="calc-label" placeholder="مثلاً: درصد تغییرات جریان"></div>'
      + '<div class="field"><label>محاسبه</label>'
      + '<select class="calc-fn">' + (meta.calculations || []).map(function (cc) {
          return '<option value="' + A.esc(cc.key) + '" data-min="' + cc.min_fields
            + '">' + A.esc(cc.label) + '</option>';
        }).join('') + '</select></div>'
      + '<div class="field"><label>رقم اعشار / پسوند</label>'
      + '<div class="calc-inline">'
      + '<input type="number" class="calc-dec" value="2" min="0" max="6">'
      + '<input type="text" class="calc-suffix" placeholder="٪" maxlength="6">'
      + '</div></div>'
      + '</div>'
      + '<div class="field"><label>روی کدام فیلدهای عددی '
      + '<span class="calc-need"></span></label>'
      + '<input type="search" class="calc-search" placeholder="جستجوی فیلد…">'
      + '<div class="calc-picks">' + (nums.length
          ? nums.map(function (f) {
              return '<label class="calc-pick-row" data-name="'
                + A.esc((f.label + ' ' + (f.section || '')).toLowerCase()) + '">'
                + '<input type="checkbox" class="calc-pick" value="'
                + A.esc(f.key) + '"><span>' + A.esc(f.label) + '</span>'
                + (f.section ? '<i>· ' + A.esc(f.section) + '</i>' : '')
                + '</label>';
            }).join('')
          : '<span class="hint">فیلد عددی‌ای تعریف نشده است.</span>')
      + '</div></div>'
      + '<div class="calc-foot"><span class="calc-order"></span>'
      + '<button class="btn-ghost calc-del" type="button">حذف ستون</button></div>';

    /* The order fields were ticked in, not the order they happen to sit in.

       «تفاضل (اولی منهای بقیه)» and «درصد تغییر (از اولی به دومی)» both turn
       on which field is first, so reading the boxes top-to-bottom would give
       the right number with the wrong sign. */
    row.picked = [];
    function labelOf(key) {
      var box = row.querySelector('.calc-pick[value="' + CSS.escape(key) + '"]');
      return box ? box.parentNode.querySelector('span').textContent : key;
    }
    function refresh() {
      var fn = row.querySelector('.calc-fn');
      var need = +fn.options[fn.selectedIndex].dataset.min;
      row.querySelector('.calc-need').textContent =
        '(دست‌کم ' + J.toFaDigits(need) + ' فیلد)';
      row.querySelector('.calc-order').textContent = row.picked.length
        ? 'ترتیب: ' + row.picked.map(labelOf).join(' ← ')
        : 'هنوز فیلدی انتخاب نشده است.';
      row.classList.toggle('short', row.picked.length < need);
    }
    row.addEventListener('change', function (ev) {
      if (ev.target.classList.contains('calc-pick')) {
        var at = row.picked.indexOf(ev.target.value);
        if (ev.target.checked && at === -1) row.picked.push(ev.target.value);
        if (!ev.target.checked && at !== -1) row.picked.splice(at, 1);
      }
      refresh();
    });
    row.querySelector('.calc-search').addEventListener('input', function () {
      var q = this.value.trim().toLowerCase();
      A.qsa('.calc-pick-row', row).forEach(function (el) {
        el.hidden = !!q && el.dataset.name.indexOf(q) === -1;
      });
    });
    row.querySelector('.calc-del').addEventListener('click', function () {
      row.remove();
    });
    A.qs('#b-calcs').appendChild(row);
    refresh();
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
    A.qs('#b-add-calc').addEventListener('click', addCalc);
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

/* ==========================================================================
   گزارش مرحله‌ای — an Excel of what one stage of one process records.

   Kept apart from the dataset builder above because the columns are not a
   fixed list: they are whatever the admin dropped on that stage, so they have
   to be fetched once a stage is chosen.
   ========================================================================== */
(function () {
  'use strict';
  var A = window.App;
  var panel = A.qs('#stage-report');
  if (!panel) return;
  var processes = [];

  function checkboxes(host, items, checked) {
    A.qs(host).innerHTML = items.map(function (c) {
      return '<label><input type="checkbox" value="' + A.esc(c.key) + '"'
        + (checked ? ' checked' : '') + '> ' + A.esc(c.label) + '</label>';
    }).join('') || '<div class="hint">موردی نیست.</div>';
  }

  function chosen() {
    return A.qsa('#sr-base input:checked, #sr-fields input:checked')
      .map(function (b) { return b.value; });
  }

  function requestBody() {
    return {
      stage_id: Number(A.qs('#sr-stage').value || 0),
      columns: chosen(),
      only_submitted: A.qs('#sr-done').checked,
      instance_status: A.qs('#sr-status').value || null,
    };
  }

  async function loadProcesses() {
    try {
      processes = (await A.api.get('/api/workflow/definitions')).data || [];
    } catch (err) {
      /* A user who may build reports but not manage processes still gets the
         active one, which is the only one they could report on anyway. */
      try {
        var def = (await A.api.get('/api/workflow/definition')).data;
        processes = [{ id: def.workflow.id, name: def.workflow.name }];
      } catch (e) { processes = []; }
    }
    A.qs('#sr-process').innerHTML = processes.map(function (p) {
      return '<option value="' + p.id + '">' + A.esc(p.name) + '</option>';
    }).join('') || '<option value="">— فرایندی نیست —</option>';
    await loadStages();
  }

  async function loadStages() {
    var id = A.qs('#sr-process').value;
    if (!id) return;
    try {
      var def = (await A.api.get('/api/workflow/definition?workflow_id=' + id)).data;
      var stages = (def.workflow.stages || []).filter(function (s) {
        return s.stage_number > 0 && s.is_active;
      });
      A.qs('#sr-stage').innerHTML = stages.map(function (s) {
        return '<option value="' + s.id + '">مرحله ' + s.stage_number + ' — '
          + A.esc(s.title) + '</option>';
      }).join('') || '<option value="">— مرحله‌ای نیست —</option>';
      await loadColumns();
    } catch (err) { A.toast(err.message, 'error'); }
  }

  async function loadColumns() {
    var id = A.qs('#sr-stage').value;
    if (!id) return;
    try {
      var data = (await A.api.get('/api/workflow/stage-report/columns?stage_id='
                                  + id)).data;
      checkboxes('#sr-base', data.base, true);
      checkboxes('#sr-fields', data.fields, true);
    } catch (err) { A.toast(err.message, 'error'); }
  }

  async function run() {
    if (!chosen().length) {
      A.toast('حداقل یک ستون را انتخاب کنید.', 'error');
      return;
    }
    var box = A.qs('#sr-result');
    box.innerHTML = '<div class="loading">در حال تهیه گزارش</div>';
    try {
      var res = await A.api.post('/api/workflow/stage-report', requestBody());
      var data = res.data;
      if (!data.rows.length) {
        box.innerHTML = '<div class="table-empty">هنوز چیزی در این مرحله '
          + 'ثبت نشده است.</div>';
        return;
      }
      box.innerHTML = '<div class="section-title">' + A.esc(data.title)
        + ' <span class="count">' + data.rows.length + ' سطر</span></div>'
        + '<div class="table-scroll"><table><thead><tr>'
        + data.columns.map(function (c) {
            return '<th>' + A.esc(c.label) + '</th>'; }).join('')
        + '</tr></thead><tbody>'
        + data.rows.slice(0, 200).map(function (r) {
            return '<tr>' + data.columns.map(function (c) {
              return '<td>' + A.esc(r[c.key]) + '</td>'; }).join('') + '</tr>';
          }).join('')
        + '</tbody></table></div>'
        + (data.rows.length > 200
            ? '<div class="hint">۲۰۰ سطر اول نمایش داده شد؛ خروجی اکسل کامل است.</div>'
            : '');
    } catch (err) {
      box.innerHTML = '<div class="alert error">' + A.esc(err.message) + '</div>';
    }
  }

  function download(fmt) {
    if (!chosen().length) {
      A.toast('حداقل یک ستون را انتخاب کنید.', 'error');
      return;
    }
    A.downloadPost('/api/workflow/stage-report/export.' + fmt, requestBody());
  }

  panel.addEventListener('toggle', function () {
    if (panel.open && !processes.length) loadProcesses();
  });
  A.qs('#sr-process').addEventListener('change', loadStages);
  A.qs('#sr-stage').addEventListener('change', loadColumns);
  A.qs('#sr-run').addEventListener('click', run);
  A.qs('#sr-xlsx').addEventListener('click', function () { download('xlsx'); });
  A.qs('#sr-csv').addEventListener('click', function () { download('csv'); });
  A.qs('#sr-all').addEventListener('click', function () {
    A.qsa('#sr-base input, #sr-fields input').forEach(function (b) {
      b.checked = true; });
  });
  A.qs('#sr-none').addEventListener('click', function () {
    A.qsa('#sr-base input, #sr-fields input').forEach(function (b) {
      b.checked = false; });
  });
})();
