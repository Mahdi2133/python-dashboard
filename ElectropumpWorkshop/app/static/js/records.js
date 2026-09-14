/* Records table: server-side paging, filtering and sorting. */
(function () {
  'use strict';
  var A = window.App, J = window.Jalali;
  var state = { page: 1, page_size: 50, sort: 'op_date', dir: 'desc' };
  var columns = [];
  var schema = null;

  function filters() {
    return {
      q: A.qs('#f-q').value.trim(),
      center: A.qs('#f-center').value,
      operation: A.qs('#f-operation').value,
      contractor: A.qs('#f-contractor').value,
      failure: A.qs('#f-failure').value,
      month: A.qs('#f-month').value,
      year: A.qs('#f-year').value,
      date_from: A.qs('#f-date-from').value.trim(),
      date_to: A.qs('#f-date-to').value.trim(),
      include_inactive: A.qs('#f-inactive').checked ? '1' : ''
    };
  }

  function queryString(extra) {
    return A.serializeQuery(Object.assign(filters(), {
      page: state.page, page_size: state.page_size,
      sort: state.sort, dir: state.dir
    }, extra || {}));
  }

  /* Columns come from the form definition (show_in_table), so an admin who
     adds a field to the table gets it here without touching this file. */
  function buildColumns() {
    var fields = [];
    schema.sections.forEach(function (section) {
      section.fields.forEach(function (field) {
        if (field.show_in_table) fields.push(field);
      });
    });
    fields.sort(function (a, b) { return (a.table_order || 99) - (b.table_order || 99); });
    columns = [];
    fields.forEach(function (field) {
      var key = field.field_name;
      if (key === 'op_jdate') key = 'date_display';
      else if (key === 'well') key = 'well';
      else if (!['failure', 'workshop_opinion', 'desc_tags'].includes(key)
               && field.model_attr) {
        key = field.model_attr.endsWith('_id')
          ? field.model_attr.slice(0, -3) : field.model_attr;
      }
      columns.push({ key: key, label: field.label,
                     sort: field.model_attr && !field.model_attr.endsWith('_id')
                           ? field.model_attr : null });
      /* The PM code and class identify the well, so they sit right beside the
         name — which is what makes two wells sharing a name tellable apart. */
      if (field.field_name === 'well') {
        columns.push({ key: 'well_pm_code', label: 'کد PM', sort: null });
        columns.push({ key: 'well_class', label: 'کلاسه چاه', sort: null });
      }
    });
    A.qs('#table-head').innerHTML = '<th>#</th>'
      + columns.map(function (col) {
          if (!col.sort) return '<th>' + A.esc(col.label) + '</th>';
          var arrow = state.sort === col.sort
            ? (state.dir === 'desc' ? ' <span class="arrow">▼</span>'
                                    : ' <span class="arrow">▲</span>') : '';
          return '<th class="sortable" data-sort="' + A.esc(col.sort) + '">'
            + A.esc(col.label) + arrow + '</th>';
        }).join('')
      + '<th>عملیات</th>';
  }

  function cell(value) {
    if (Array.isArray(value)) return A.esc(value.join('، '));
    if (value === null || value === undefined) return '';
    return A.esc(String(value));
  }

  async function load() {
    var body = A.qs('#records-body');
    body.innerHTML = '<tr><td colspan="' + (columns.length + 2)
      + '" class="table-empty">در حال بارگذاری…</td></tr>';
    try {
      var res = await A.api.get('/api/records?' + queryString());
      A.qs('#record-count').textContent = J.toFaDigits(res.total) + ' رکورد';
      if (!res.data.length) {
        body.innerHTML = '<tr><td colspan="' + (columns.length + 2)
          + '" class="table-empty">رکوردی یافت نشد</td></tr>';
        renderPagination(res);
        return;
      }
      var offset = (res.page - 1) * res.page_size;
      body.innerHTML = res.data.map(function (row, i) {
        var full = columns.map(function (col) {
          var v = row[col.key];
          return '<td title="' + cell(v) + '">' + cell(v) + '</td>';
        }).join('');
        return '<tr class="' + (row.is_active ? '' : 'inactive') + '">'
          + '<td>' + J.toFaDigits(offset + i + 1) + '</td>' + full
          + '<td><div class="action-cell">'
          + '<button class="btn-sm btn-view" data-view="' + row.id + '">👁</button>'
          + (A.can('record.edit')
              ? '<a class="btn-sm btn-edit" href="/entry/' + row.id + '">✏</a>' : '')
          + (A.can('record.delete')
              ? (row.is_active
                  ? '<button class="btn-sm btn-del" data-del="' + row.id + '">🗑</button>'
                  : '<button class="btn-sm btn-view" data-restore="' + row.id + '">↩</button>')
              : '')
          + '</div></td></tr>';
      }).join('');
      renderPagination(res);
    } catch (err) {
      body.innerHTML = '<tr><td colspan="' + (columns.length + 2)
        + '" class="table-empty">' + A.esc(err.message) + '</td></tr>';
    }
  }

  function renderPagination(res) {
    var box = A.qs('#pagination');
    if (res.pages <= 1) {
      box.innerHTML = '<span class="info">'
        + J.toFaDigits(res.total) + ' رکورد</span>';
      return;
    }
    var html = '<button data-page="1" ' + (res.page === 1 ? 'disabled' : '') + '>«</button>'
      + '<button data-page="' + (res.page - 1) + '" '
      + (res.page === 1 ? 'disabled' : '') + '>‹</button>';
    var start = Math.max(1, res.page - 3), end = Math.min(res.pages, res.page + 3);
    for (var p = start; p <= end; p++) {
      html += '<button data-page="' + p + '" class="'
        + (p === res.page ? 'active' : '') + '">' + J.toFaDigits(p) + '</button>';
    }
    html += '<button data-page="' + (res.page + 1) + '" '
      + (res.page === res.pages ? 'disabled' : '') + '>›</button>'
      + '<button data-page="' + res.pages + '" '
      + (res.page === res.pages ? 'disabled' : '') + '>»</button>'
      + '<span class="info">صفحه ' + J.toFaDigits(res.page) + ' از '
      + J.toFaDigits(res.pages) + ' — ' + J.toFaDigits(res.total) + ' رکورد</span>';
    box.innerHTML = html;
  }

  async function showDetail(id) {
    try {
      var res = await A.api.get('/api/records/' + id);
      var rec = res.data;
      var rows = [];
      schema.sections.forEach(function (section) {
        var items = [];
        section.fields.forEach(function (field) {
          var key = field.field_name;
          var value;
          if (key === 'op_jdate') value = rec.date_display;
          else if (key === 'well') value = rec.well;
          else if (['failure', 'workshop_opinion', 'desc_tags'].includes(key)) {
            value = (rec[key] || []).join('، ');
          } else if (field.model_attr) {
            var attr = field.model_attr.endsWith('_id')
              ? field.model_attr.slice(0, -3) : field.model_attr;
            value = rec[attr];
          } else { value = (rec.dynamic || {})[key]; }
          if (value === null || value === undefined || value === '' || value === false) return;
          items.push('<dt>' + A.esc(field.label) + '</dt><dd>' + A.esc(value) + '</dd>');
        });
        if (items.length) {
          rows.push('<h4 style="color:var(--primary);margin:12px 0 6px">'
            + A.esc(section.icon || '') + ' ' + A.esc(section.title) + '</h4>'
            + '<dl class="kv">' + items.join('') + '</dl>');
        }
      });
      A.qs('#detail-body').innerHTML = rows.join('') || '<p>مقداری ثبت نشده است.</p>';
      A.qs('#detail-edit').href = '/entry/' + id;
      A.qs('#detail-edit').classList.toggle('hidden', !A.can('record.edit'));
      A.openModal('detail-modal');
    } catch (err) { A.toast(err.message, 'error'); }
  }

  async function loadFilterOptions() {
    var res = await A.api.get('/api/lookups');
    [['center', 'center'], ['operation', 'operation'],
     ['contractor', 'contractor'], ['failure', 'failure_reason']]
      .forEach(function (pair) {
        var select = A.qs('#f-' + pair[0]);
        (res.data[pair[1]] || []).forEach(function (item) {
          select.appendChild(A.el('option', { value: item.value, text: item.label }));
        });
      });
    var current = J.today()[0], yearSelect = A.qs('#f-year');
    for (var y = current; y >= current - 12; y--) {
      yearSelect.appendChild(A.el('option', { value: y, text: y }));
    }
  }

  document.addEventListener('DOMContentLoaded', async function () {
    A.qsa('.jdate').forEach(function (input) { J.attach(input); });
    try {
      var res = await A.api.get('/api/form-builder');
      schema = res.data;
      buildColumns();
      await loadFilterOptions();
    } catch (err) { A.toast(err.message, 'error'); return; }

    var reload = function () { state.page = 1; load(); };
    A.qs('#f-q').addEventListener('input', A.debounce(reload, 350));
    ['#f-center', '#f-operation', '#f-contractor', '#f-failure', '#f-month',
     '#f-year', '#f-date-from', '#f-date-to', '#f-inactive'].forEach(function (sel) {
      A.qs(sel).addEventListener('change', reload);
    });
    A.qs('#f-page-size').addEventListener('change', function (ev) {
      state.page_size = +ev.target.value; reload();
    });
    A.qs('#btn-reset').addEventListener('click', function () {
      A.qsa('.filter-row input, .filter-row select').forEach(function (el) {
        if (el.type === 'checkbox') el.checked = false;
        else if (el.id !== 'f-page-size') el.value = '';
      });
      reload();
    });

    A.qs('#table-head').addEventListener('click', function (ev) {
      var th = ev.target.closest('[data-sort]');
      if (!th) return;
      if (state.sort === th.dataset.sort) {
        state.dir = state.dir === 'desc' ? 'asc' : 'desc';
      } else { state.sort = th.dataset.sort; state.dir = 'desc'; }
      buildColumns();
      load();
    });

    A.qs('#pagination').addEventListener('click', function (ev) {
      var button = ev.target.closest('[data-page]');
      if (!button || button.disabled) return;
      state.page = +button.dataset.page;
      load();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });

    A.qs('#records-body').addEventListener('click', async function (ev) {
      var view = ev.target.closest('[data-view]');
      if (view) { showDetail(view.dataset.view); return; }
      var del = ev.target.closest('[data-del]');
      if (del) {
        var confirmed = await A.confirmDialog({
          title: 'حذف رکورد',
          message: 'رکورد غیرفعال می‌شود و از فهرست خارج می‌گردد. '
                   + 'داده‌ها حذف نمی‌شوند و قابل بازیابی هستند.'
        });
        if (!confirmed) return;
        try {
          var res = await A.api.del('/api/records/' + del.dataset.del);
          A.toast(res.message);
          load();
        } catch (err) { A.toast(err.message, 'error'); }
        return;
      }
      var restore = ev.target.closest('[data-restore]');
      if (restore) {
        try {
          await A.api.post('/api/records/' + restore.dataset.restore + '/restore', {});
          A.toast('رکورد بازیابی شد.');
          load();
        } catch (err) { A.toast(err.message, 'error'); }
      }
    });

    if (!A.can('record.export')) {
      A.qsa('[data-export]').forEach(function (b) { b.classList.add('hidden'); });
    }
    A.qsa('[data-export]').forEach(function (button) {
      button.addEventListener('click', function () {
        A.download('/api/export.' + button.dataset.export + '?' + A.serializeQuery(filters()));
      });
    });
    A.qs('#btn-print').addEventListener('click', function () { window.print(); });

    load();
  });
})();
