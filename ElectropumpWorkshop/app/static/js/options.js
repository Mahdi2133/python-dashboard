(function () {
  'use strict';
  var A = window.App;
  var categories = [], activeCode = null, activeItem = null, dragged = null;

  async function loadCategories() {
    var res = await A.api.get('/api/lookups/categories');
    categories = res.data;
    A.qs('#cat-list').innerHTML = categories.map(function (cat) {
      return '<div class="sortable-item" data-cat="' + A.esc(cat.code) + '" '
        + 'style="cursor:pointer">'
        + '<span>' + A.esc(cat.name_fa) + '</span>'
        + '<span class="spacer"></span>'
        + (cat.allows_multiple ? '<span class="badge">چندانتخابی</span>' : '')
        + '<span class="badge muted mono">' + A.esc(cat.code) + '</span></div>';
    }).join('');
  }

  async function loadItems(code) {
    activeCode = code;
    var cat = categories.find(function (c) { return c.code === code; });
    A.qs('#opt-title').textContent = cat ? cat.name_fa : 'گزینه‌ها';
    A.qs('#opt-sub').textContent = cat ? 'کد دسته: ' + cat.code : '';
    A.qs('#btn-save-order').classList.remove('hidden');
    var showAll = A.qs('#show-inactive').checked;
    var res = await A.api.get('/api/lookups/' + code + (showAll ? '?all=1' : ''));
    var items = res.data.items || [];
    A.qs('#opt-list').innerHTML = items.length ? items.map(function (item) {
      return '<div class="sortable-item' + (item.is_active ? '' : ' inactive')
        + '" draggable="true" data-id="' + item.id + '">'
        + '<span class="handle">⠿</span>'
        + '<span>' + (item.icon ? A.esc(item.icon) + ' ' : '') + A.esc(item.label) + '</span>'
        + (item.label !== item.value
            ? '<span class="badge muted">' + A.esc(item.value) + '</span>' : '')
        + (item.aliases.length
            ? '<span class="badge">' + item.aliases.length + ' مستعار</span>' : '')
        + (item.is_adhoc ? '<span class="badge warn">خودکار</span>' : '')
        + (item.is_active ? '' : '<span class="badge muted">غیرفعال</span>')
        + '<span class="spacer"></span>'
        + '<button class="btn-sm btn-edit" data-item=\'' + A.esc(JSON.stringify(item))
        + '\'>ویرایش</button></div>';
    }).join('') : '<div class="muted small">گزینه‌ای ثبت نشده است.</div>';
  }

  function openEditor(item) {
    activeItem = item;
    A.qs('#opt-modal-title').textContent = item ? 'ویرایش گزینه' : 'گزینه جدید';
    A.qs('#o-value').value = item ? item.value : '';
    A.qs('#o-label').value = item ? item.label : '';
    A.qs('#o-icon').value = item && item.icon ? item.icon : '';
    A.qs('#o-notes').value = item && item.notes ? item.notes : '';
    A.qs('#o-active').value = item && !item.is_active ? '0' : '1';
    A.qs('#o-alias').value = '';
    renderAliases(item ? item.aliases : []);
    A.qs('#o-delete').classList.toggle('hidden', !item);
    A.openModal('opt-modal');
  }

  function renderAliases(aliases) {
    A.qs('#o-alias-list').innerHTML = (aliases || []).map(function (a) {
      return '<span class="badge">' + A.esc(a) + '</span>';
    }).join('') || '<span class="muted small">نام مستعاری ثبت نشده.</span>';
  }

  async function save() {
    var payload = {
      value: A.qs('#o-value').value.trim(),
      label: A.qs('#o-label').value.trim() || A.qs('#o-value').value.trim(),
      icon: A.qs('#o-icon').value.trim(),
      notes: A.qs('#o-notes').value.trim(),
      is_active: A.qs('#o-active').value === '1'
    };
    if (!payload.value) { A.toast('مقدار گزینه الزامی است.', 'error'); return; }
    try {
      var res = activeItem
        ? await A.api.put('/api/lookups/item/' + activeItem.id, payload)
        : await A.api.post('/api/lookups/' + activeCode, payload);
      A.toast(res.message);
      A.closeModal('opt-modal');
      loadItems(activeCode);
    } catch (err) { A.toast(err.message, 'error'); }
  }

  document.addEventListener('DOMContentLoaded', async function () {
    try { await loadCategories(); }
    catch (err) { A.toast(err.message, 'error'); return; }

    A.qs('#cat-list').addEventListener('click', function (ev) {
      var row = ev.target.closest('[data-cat]');
      if (row) loadItems(row.dataset.cat);
    });
    A.qs('#show-inactive').addEventListener('change', function () {
      if (activeCode) loadItems(activeCode);
    });
    A.qs('#btn-add-opt').addEventListener('click', function () {
      if (!activeCode) { A.toast('ابتدا یک دسته را انتخاب کنید.', 'warn'); return; }
      openEditor(null);
    });
    A.qs('#opt-list').addEventListener('click', function (ev) {
      var button = ev.target.closest('[data-item]');
      if (button) openEditor(JSON.parse(button.dataset.item));
    });
    A.qs('#o-save').addEventListener('click', save);
    A.qs('#o-delete').addEventListener('click', async function () {
      if (!activeItem) return;
      var confirmed = await A.confirmDialog({
        title: 'حذف گزینه',
        message: 'اگر رکوردی از این گزینه استفاده کند، فقط غیرفعال می‌شود و حذف نمی‌گردد.'
      });
      if (!confirmed) return;
      try {
        var res = await A.api.del('/api/lookups/item/' + activeItem.id);
        A.toast(res.message);
        A.closeModal('opt-modal');
        loadItems(activeCode);
      } catch (err) { A.toast(err.message, 'error'); }
    });
    A.qs('#o-alias-add').addEventListener('click', async function () {
      if (!activeItem) { A.toast('ابتدا گزینه را ذخیره کنید.', 'warn'); return; }
      var alias = A.qs('#o-alias').value.trim();
      if (!alias) return;
      try {
        var res = await A.api.post('/api/lookups/item/' + activeItem.id + '/aliases',
          { alias: alias });
        activeItem = res.data;
        renderAliases(activeItem.aliases);
        A.qs('#o-alias').value = '';
        A.toast(res.message);
      } catch (err) { A.toast(err.message, 'error'); }
    });

    /* drag to reorder */
    var list = A.qs('#opt-list');
    list.addEventListener('dragstart', function (ev) {
      dragged = ev.target.closest('[data-id]');
      if (dragged) dragged.classList.add('dragging');
    });
    list.addEventListener('dragend', function () {
      if (dragged) dragged.classList.remove('dragging');
      dragged = null;
    });
    list.addEventListener('dragover', function (ev) {
      ev.preventDefault();
      var over = ev.target.closest('[data-id]');
      if (!over || !dragged || over === dragged) return;
      var rect = over.getBoundingClientRect();
      var after = (ev.clientY - rect.top) > rect.height / 2;
      list.insertBefore(dragged, after ? over.nextSibling : over);
    });
    A.qs('#btn-save-order').addEventListener('click', async function () {
      var order = A.qsa('#opt-list [data-id]').map(function (row) { return row.dataset.id; });
      try {
        var res = await A.api.post('/api/lookups/' + activeCode + '/reorder', { order: order });
        A.toast(res.message);
      } catch (err) { A.toast(err.message, 'error'); }
    });

    if (categories.length) loadItems(categories[0].code);
  });
})();
