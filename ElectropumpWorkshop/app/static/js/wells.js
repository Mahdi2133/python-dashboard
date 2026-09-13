(function () {
  'use strict';
  var A = window.App, J = window.Jalali;
  var page = 1, editingId = null, mergeSource = null, mergeTargetId = null;

  async function load() {
    var body = A.qs('#wells-body');
    body.innerHTML = '<tr><td colspan="8" class="table-empty">در حال بارگذاری…</td></tr>';
    try {
      var res = await A.api.get('/api/wells/page?' + A.serializeQuery({
        page: page, page_size: 50, q: A.qs('#w-q').value.trim(),
        unverified: A.qs('#w-unverified').checked ? '1' : ''
      }));
      if (!res.data.length) {
        body.innerHTML = '<tr><td colspan="8" class="table-empty">چاهی یافت نشد</td></tr>';
      } else {
        var offset = (res.page - 1) * res.page_size;
        body.innerHTML = res.data.map(function (w, i) {
          return '<tr class="' + (w.is_active ? '' : 'inactive') + '">'
            + '<td>' + J.toFaDigits(offset + i + 1) + '</td>'
            + '<td>' + A.esc(w.name) + '</td>'
            + '<td>' + A.esc(w.code || '') + '</td>'
            + '<td>' + A.esc(w.center || '') + '</td>'
            + '<td>' + A.esc(w.depth === null ? '' : w.depth) + '</td>'
            + '<td>' + J.toFaDigits(w.record_count) + '</td>'
            + '<td>' + (w.is_active
                ? '<span class="badge ok">فعال</span>'
                : '<span class="badge muted">غیرفعال</span>')
              + (w.is_verified ? '' : ' <span class="badge warn">تأییدنشده</span>') + '</td>'
            + '<td><div class="action-cell">'
            + '<button class="btn-sm btn-edit" data-edit=\'' + A.esc(JSON.stringify(w)) + '\'>✏</button>'
            + '<button class="btn-sm btn-view" data-merge=\'' + A.esc(JSON.stringify(w)) + '\'>🔗</button>'
            + (w.is_active
                ? '<button class="btn-sm btn-del" data-off="' + w.id + '">🗑</button>' : '')
            + '</div></td></tr>';
        }).join('');
      }
      renderPagination(res);
    } catch (err) {
      body.innerHTML = '<tr><td colspan="8" class="table-empty">' + A.esc(err.message) + '</td></tr>';
    }
  }

  function renderPagination(res) {
    var box = A.qs('#w-pagination');
    if (res.pages <= 1) {
      box.innerHTML = '<span class="info">' + J.toFaDigits(res.total) + ' چاه</span>';
      return;
    }
    var html = '';
    var start = Math.max(1, res.page - 4), end = Math.min(res.pages, res.page + 4);
    if (start > 1) html += '<button data-page="1">۱ …</button>';
    for (var p = start; p <= end; p++) {
      html += '<button data-page="' + p + '" class="' + (p === res.page ? 'active' : '')
        + '">' + J.toFaDigits(p) + '</button>';
    }
    if (end < res.pages) html += '<button data-page="' + res.pages + '">… '
      + J.toFaDigits(res.pages) + '</button>';
    html += '<span class="info">' + J.toFaDigits(res.total) + ' چاه</span>';
    box.innerHTML = html;
  }

  function openEditor(well) {
    editingId = well ? well.id : null;
    A.qs('#well-modal-title').textContent = well ? 'ویرایش چاه' : 'افزودن چاه';
    A.qs('#w-name').value = well ? well.name : '';
    A.qs('#w-code').value = well && well.code ? well.code : '';
    A.qs('#w-center').value = well && well.center_id ? well.center_id : '';
    A.qs('#w-depth').value = well && well.depth !== null ? well.depth : '';
    A.qs('#w-notes').value = well && well.notes ? well.notes : '';
    A.qs('#w-active').value = well && !well.is_active ? '0' : '1';
    A.openModal('well-modal');
  }

  async function saveWell() {
    var payload = {
      name: A.qs('#w-name').value.trim(),
      code: A.qs('#w-code').value.trim(),
      center_id: A.qs('#w-center').value || null,
      depth: A.qs('#w-depth').value || null,
      notes: A.qs('#w-notes').value.trim(),
      is_active: A.qs('#w-active').value === '1',
      is_verified: true
    };
    if (!payload.name) { A.toast('نام چاه الزامی است.', 'error'); return; }
    try {
      var res = editingId
        ? await A.api.put('/api/wells/' + editingId, payload)
        : await A.api.post('/api/wells', payload);
      A.toast(res.message);
      A.closeModal('well-modal');
      load();
    } catch (err) { A.toast(err.message, 'error'); }
  }

  function setupMergeSearch() {
    var input = A.qs('#m-target'), list = A.qs('#m-target-list');
    var search = A.debounce(async function () {
      var q = input.value.trim();
      if (!q) { list.classList.remove('show'); return; }
      try {
        var res = await A.api.get('/api/wells?all=1&limit=12&q=' + encodeURIComponent(q));
        list.innerHTML = res.data.map(function (w) {
          return '<div class="autocomplete-item" data-id="' + w.id + '" data-name="'
            + A.esc(w.name) + '">' + A.esc(w.name) + '</div>';
        }).join('') || '<div class="autocomplete-item">یافت نشد</div>';
        list.classList.add('show');
      } catch (err) { list.classList.remove('show'); }
    }, 200);
    input.addEventListener('input', search);
    list.addEventListener('click', function (ev) {
      var item = ev.target.closest('[data-id]');
      if (!item) return;
      mergeTargetId = +item.dataset.id;
      input.value = item.dataset.name;
      list.classList.remove('show');
    });
  }

  document.addEventListener('DOMContentLoaded', async function () {
    try {
      var res = await A.api.get('/api/lookups/center');
      res.data.items.forEach(function (item) {
        A.qs('#w-center').appendChild(
          A.el('option', { value: item.id, text: item.label }));
      });
    } catch (err) { /* the center select simply stays empty */ }

    setupMergeSearch();
    A.qs('#btn-new-well').addEventListener('click', function () { openEditor(null); });
    A.qs('#w-save').addEventListener('click', saveWell);
    A.qs('#w-q').addEventListener('input', A.debounce(function () { page = 1; load(); }, 320));
    A.qs('#w-unverified').addEventListener('change', function () { page = 1; load(); });
    A.qs('#w-pagination').addEventListener('click', function (ev) {
      var button = ev.target.closest('[data-page]');
      if (button) { page = +button.dataset.page; load(); }
    });
    A.qs('#wells-body').addEventListener('click', async function (ev) {
      var edit = ev.target.closest('[data-edit]');
      if (edit) { openEditor(JSON.parse(edit.dataset.edit)); return; }
      var merge = ev.target.closest('[data-merge]');
      if (merge) {
        var well = JSON.parse(merge.dataset.merge);
        mergeSource = well.id;
        mergeTargetId = null;
        A.qs('#m-source').value = well.name;
        A.qs('#m-target').value = '';
        A.openModal('merge-modal');
        return;
      }
      var off = ev.target.closest('[data-off]');
      if (off) {
        var confirmed = await A.confirmDialog({
          title: 'غیرفعال‌سازی چاه',
          message: 'چاه غیرفعال می‌شود ولی رکوردهای قبلی آن حفظ می‌گردند.'
        });
        if (!confirmed) return;
        try {
          var res = await A.api.del('/api/wells/' + off.dataset.off);
          A.toast(res.message);
          load();
        } catch (err) { A.toast(err.message, 'error'); }
      }
    });
    A.qs('#m-confirm').addEventListener('click', async function () {
      if (!mergeTargetId) { A.toast('چاه مقصد را انتخاب کنید.', 'error'); return; }
      try {
        var res = await A.api.post('/api/wells/' + mergeTargetId + '/merge',
          { source_id: mergeSource });
        A.toast(res.message);
        A.closeModal('merge-modal');
        load();
      } catch (err) { A.toast(err.message, 'error'); }
    });
    load();
  });
})();
