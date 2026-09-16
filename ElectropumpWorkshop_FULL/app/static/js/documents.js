/* ==========================================================================
   مستندات فرایندها — every file attached to any process, in one place.

   A photo taken at stage 3 is what stage 5 signs off against, so the admin
   and the stage owners both reach it from here rather than opening each
   process in turn.
   ========================================================================== */
(function () {
  'use strict';
  var A = window.App, J = window.Jalali;
  var page = 1;

  async function load() {
    var params = ['page=' + page, 'page_size=50'];
    var q = A.qs('#doc-q').value.trim();
    if (q) params.push('q=' + encodeURIComponent(q));
    if (A.qs('#doc-instance').value) {
      params.push('instance_id=' + A.qs('#doc-instance').value);
    }
    if (A.qs('#doc-stage').value) params.push('stage=' + A.qs('#doc-stage').value);
    try {
      var res = await A.api.get('/api/workflow/attachments?' + params.join('&'));
      render(res);
    } catch (err) {
      A.qs('#doc-alert').innerHTML = '<div class="alert error">'
        + A.esc(err.message) + '</div>';
      A.qs('#doc-rows').innerHTML = '<tr><td colspan="9" class="table-empty">'
        + A.esc(err.message) + '</td></tr>';
    }
  }

  function render(res) {
    var rows = res.data || [];
    A.qs('#doc-count').textContent = J.toFaDigits(res.total || 0);
    if (!rows.length) {
      A.qs('#doc-rows').innerHTML = '<tr><td colspan="9" class="table-empty">'
        + 'مستندی یافت نشد.</td></tr>';
      A.qs('#doc-pages').innerHTML = '';
      return;
    }
    var offset = ((res.page || 1) - 1) * (res.page_size || 50);
    A.qs('#doc-rows').innerHTML = rows.map(function (d, i) {
      return '<tr>'
        + '<td>' + J.toFaDigits(offset + i + 1) + '</td>'
        + '<td>📄 ' + A.esc(d.filename) + '</td>'
        + '<td>#' + J.toFaDigits(d.instance_id)
        + (d.operation_label ? ' <span class="badge muted">'
            + A.esc(d.operation_label) + '</span>' : '') + '</td>'
        + '<td>' + A.esc(d.well || '—') + '</td>'
        + '<td>' + J.toFaDigits(d.stage_number) + ' — '
        + A.esc(d.stage_title || '') + '</td>'
        + '<td>' + A.esc(d.uploaded_by_name || '—') + '</td>'
        + '<td class="mono">' + A.esc(d.uploaded_at_j || '') + ' '
        + A.esc(d.uploaded_at_time || '') + '</td>'
        + '<td>' + A.esc(d.size_label) + '</td>'
        + '<td><a class="btn-sm btn-view" href="' + A.esc(d.url)
        + '">⬇ دانلود</a></td>'
        + '</tr>';
    }).join('');
    renderPages(res);
  }

  function renderPages(res) {
    var pages = res.pages || 1;
    if (pages < 2) { A.qs('#doc-pages').innerHTML = ''; return; }
    var html = '';
    for (var i = 1; i <= pages; i++) {
      html += '<button class="page-btn' + (i === res.page ? ' active' : '')
        + '" data-page="' + i + '" type="button">' + J.toFaDigits(i) + '</button>';
    }
    A.qs('#doc-pages').innerHTML = html;
  }

  document.addEventListener('DOMContentLoaded', async function () {
    try {
      var def = await A.api.get('/api/workflow/definition');
      A.qs('#doc-stage').innerHTML = '<option value="">همه مرحله‌ها</option>'
        + (def.data.workflow.stages || []).map(function (s) {
            return '<option value="' + s.stage_number + '">'
              + J.toFaDigits(s.stage_number) + ' — ' + A.esc(s.title) + '</option>';
          }).join('');
    } catch (err) { /* the filter is a convenience; the list still works */ }
    await load();
    A.qs('#doc-refresh').addEventListener('click', function () { page = 1; load(); });
    A.qs('#doc-q').addEventListener('input', A.debounce(function () {
      page = 1; load();
    }, 300));
    A.qs('#doc-instance').addEventListener('change', function () { page = 1; load(); });
    A.qs('#doc-stage').addEventListener('change', function () { page = 1; load(); });
    A.qs('#doc-pages').addEventListener('click', function (ev) {
      var button = ev.target.closest('[data-page]');
      if (button) { page = Number(button.dataset.page); load(); }
    });
  });
})();
