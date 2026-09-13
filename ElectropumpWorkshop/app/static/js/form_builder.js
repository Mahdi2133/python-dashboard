(function () {
  'use strict';
  var A = window.App;
  var schema = null, editingField = null, editingSection = null, dragged = null;

  var TYPE_LABELS = {
    text: 'متن', number: 'عدد', textarea: 'متن بلند', date: 'تاریخ میلادی',
    jalali_date: 'تاریخ شمسی', select: 'لیست کشویی', radio: 'تک‌انتخابی',
    checkbox: 'چندانتخابی', multiselect: 'چندانتخابی (لیست)', autocomplete: 'جستجوی خودکار'
  };

  async function load() {
    var res = await A.api.get('/api/form-builder?all=1');
    schema = res.data;
    render();
  }

  function render() {
    A.qs('#sections-container').innerHTML = schema.sections.map(function (section) {
      return '<div class="card' + (section.is_active ? '' : ' inactive')
        + '" data-section="' + section.id + '">'
        + '<div class="section-title">'
        + (section.icon ? '<span>' + A.esc(section.icon) + '</span>' : '')
        + '<span>' + A.esc(section.title) + '</span>'
        + (section.is_active ? '' : '<span class="badge muted">غیرفعال</span>')
        + '<span class="count">' + section.fields.length + ' فیلد · '
        + section.columns + ' ستون · <code>' + A.esc(section.code) + '</code></span>'
        + '<button class="btn-sm btn-edit" data-edit-section="' + section.id
        + '" style="margin-inline-start:8px">✏ بخش</button></div>'
        + '<div class="sortable-list" data-fields="' + section.id + '">'
        + (section.fields.length ? section.fields.map(fieldRow).join('')
            : '<div class="muted small">فیلدی در این بخش نیست.</div>')
        + '</div></div>';
    }).join('');
  }

  function fieldRow(field) {
    return '<div class="sortable-item' + (field.is_active ? '' : ' inactive')
      + '" draggable="true" data-field-id="' + field.id + '">'
      + '<span class="handle">⠿</span>'
      + '<span>' + A.esc(field.label) + '</span>'
      + '<span class="badge muted">' + A.esc(TYPE_LABELS[field.field_type]
          || field.field_type) + '</span>'
      + '<span class="badge muted mono">' + A.esc(field.field_name) + '</span>'
      + (field.is_builtin ? '<span class="badge">پایه</span>'
          : '<span class="badge ok">سفارشی</span>')
      + (field.is_required ? '<span class="badge danger">الزامی</span>' : '')
      + (field.show_in_table ? '<span class="badge">در جدول</span>' : '')
      + (field.lookup_category
          ? '<span class="badge">' + A.esc(field.lookup_category) + '</span>' : '')
      + (field.is_active ? '' : '<span class="badge muted">پنهان</span>')
      + '<span class="spacer"></span>'
      + '<button class="btn-sm btn-edit" data-edit-field="' + field.id + '">ویرایش</button>'
      + '</div>';
  }

  function findField(id) {
    var found = null;
    schema.sections.forEach(function (s) {
      s.fields.forEach(function (f) { if (f.id === +id) found = f; });
    });
    return found;
  }

  function openFieldEditor(field) {
    editingField = field;
    A.qs('#field-modal-title').textContent = field
      ? 'ویرایش فیلد: ' + field.label : 'فیلد جدید';
    A.qs('#fb-name').value = field ? field.field_name : '';
    A.qs('#fb-name').disabled = !!(field && field.is_builtin);
    A.qs('#fb-label').value = field ? field.label : '';
    A.qs('#fb-type').value = field ? field.field_type : 'text';
    A.qs('#fb-type').disabled = !!(field && field.is_builtin);
    A.qs('#fb-section').value = field ? field.section_id : (schema.sections[0] || {}).id;
    A.qs('#fb-order').value = field ? field.sort_order : 99;
    A.qs('#fb-span').value = field ? field.col_span : 1;
    A.qs('#fb-required').value = field && field.is_required ? '1' : '0';
    A.qs('#fb-active').value = field && !field.is_active ? '0' : '1';
    A.qs('#fb-table').value = field && field.show_in_table ? '1' : '0';
    A.qs('#fb-default').value = field && field.default_value ? field.default_value : '';
    A.qs('#fb-placeholder').value = field && field.placeholder ? field.placeholder : '';
    A.qs('#fb-lookup').value = field && field.lookup_category ? field.lookup_category : '';
    A.qs('#fb-lookup').disabled = !!(field && field.is_builtin);
    A.qs('#fb-min').value = field && field.min_value !== null ? field.min_value : '';
    A.qs('#fb-max').value = field && field.max_value !== null ? field.max_value : '';
    A.qs('#fb-step').value = field && field.step ? field.step : '';
    A.qs('#fb-help').value = field && field.help_text ? field.help_text : '';
    A.qs('#fb-other').value = field && field.allow_other ? '1' : '0';
    A.qs('#fb-export').value = field && field.export_header ? field.export_header : '';
    A.qs('#fb-options').value = field
      ? (field.own_options || []).map(function (o) {
          return o.value + (o.label !== o.value ? '|' + o.label : '');
        }).join('\n')
      : '';
    A.qs('#fb-options-wrap').classList.toggle('hidden', !!(field && field.is_builtin));
    A.qs('#fb-delete').classList.toggle('hidden', !field);
    A.openModal('field-modal');
  }

  function collectField() {
    return {
      field_name: A.qs('#fb-name').value.trim(),
      label: A.qs('#fb-label').value.trim(),
      field_type: A.qs('#fb-type').value,
      section_id: A.qs('#fb-section').value,
      sort_order: A.qs('#fb-order').value || 0,
      col_span: A.qs('#fb-span').value,
      is_required: A.qs('#fb-required').value === '1',
      is_active: A.qs('#fb-active').value === '1',
      show_in_table: A.qs('#fb-table').value === '1',
      default_value: A.qs('#fb-default').value.trim(),
      placeholder: A.qs('#fb-placeholder').value.trim(),
      lookup_category: A.qs('#fb-lookup').value,
      min_value: A.qs('#fb-min').value, max_value: A.qs('#fb-max').value,
      step: A.qs('#fb-step').value.trim(),
      help_text: A.qs('#fb-help').value.trim(),
      allow_other: A.qs('#fb-other').value === '1',
      export_header: A.qs('#fb-export').value.trim(),
      options: A.qs('#fb-options').value.split('\n').map(function (line) {
        var parts = line.split('|');
        var value = (parts[0] || '').trim();
        if (!value) return null;
        return { value: value, label: (parts[1] || value).trim() };
      }).filter(Boolean)
    };
  }

  async function saveField() {
    var payload = collectField();
    if (!payload.field_name || !payload.label) {
      A.toast('نام فنی و برچسب الزامی است.', 'error'); return;
    }
    try {
      var res = editingField
        ? await A.api.put('/api/form-builder/fields/' + editingField.id, payload)
        : await A.api.post('/api/form-builder/fields', payload);
      A.toast(res.message);
      A.closeModal('field-modal');
      await load();
    } catch (err) { A.toast(err.message, 'error'); }
  }

  function openSectionEditor(section) {
    editingSection = section;
    A.qs('#section-modal-title').textContent = section ? 'ویرایش بخش' : 'بخش جدید';
    A.qs('#sb-code').value = section ? section.code : '';
    A.qs('#sb-code').disabled = !!section;
    A.qs('#sb-title').value = section ? section.title : '';
    A.qs('#sb-icon').value = section && section.icon ? section.icon : '';
    A.qs('#sb-columns').value = section ? section.columns : 3;
    A.qs('#sb-full').value = section && section.full_width ? '1' : '0';
    A.qs('#sb-active').value = section && !section.is_active ? '0' : '1';
    A.qs('#sb-delete').classList.toggle('hidden', !section);
    A.openModal('section-modal');
  }

  async function saveSection() {
    var payload = {
      code: A.qs('#sb-code').value.trim(), title: A.qs('#sb-title').value.trim(),
      icon: A.qs('#sb-icon').value.trim(), columns: A.qs('#sb-columns').value,
      full_width: A.qs('#sb-full').value === '1',
      is_active: A.qs('#sb-active').value === '1'
    };
    if (!payload.code || !payload.title) {
      A.toast('کد و عنوان بخش الزامی است.', 'error'); return;
    }
    try {
      var res = editingSection
        ? await A.api.put('/api/form-builder/sections/' + editingSection.id, payload)
        : await A.api.post('/api/form-builder/sections', payload);
      A.toast(res.message);
      A.closeModal('section-modal');
      await load();
    } catch (err) { A.toast(err.message, 'error'); }
  }

  document.addEventListener('DOMContentLoaded', async function () {
    try { await load(); }
    catch (err) {
      A.qs('#sections-container').innerHTML = '<div class="alert error">'
        + A.esc(err.message) + '</div>';
      return;
    }

    A.qs('#fb-type').innerHTML = schema.field_types.map(function (t) {
      return '<option value="' + t + '">' + A.esc(TYPE_LABELS[t] || t) + '</option>';
    }).join('');
    A.qs('#fb-section').innerHTML = schema.sections.map(function (s) {
      return '<option value="' + s.id + '">' + A.esc(s.title) + '</option>';
    }).join('');
    A.qs('#fb-lookup').innerHTML = '<option value="">— گزینه‌های اختصاصی —</option>'
      + Object.keys(schema.lookups).filter(function (c) { return c !== '__months__'; })
        .map(function (c) { return '<option value="' + A.esc(c) + '">' + A.esc(c) + '</option>'; })
        .join('');

    A.qs('#btn-new-field').addEventListener('click', function () { openFieldEditor(null); });
    A.qs('#btn-new-section').addEventListener('click', function () { openSectionEditor(null); });
    A.qs('#fb-save').addEventListener('click', saveField);
    A.qs('#sb-save').addEventListener('click', saveSection);

    A.qs('#fb-delete').addEventListener('click', async function () {
      if (!editingField) return;
      var confirmed = await A.confirmDialog({
        title: 'حذف فیلد',
        message: editingField.is_builtin
          ? 'این فیلد پایه است و حذف نمی‌شود؛ فقط از فرم پنهان می‌گردد. ادامه؟'
          : 'اگر رکوردی مقدار این فیلد را داشته باشد، فیلد فقط غیرفعال می‌شود.'
      });
      if (!confirmed) return;
      try {
        var res = await A.api.del('/api/form-builder/fields/' + editingField.id);
        A.toast(res.message);
        A.closeModal('field-modal');
        await load();
      } catch (err) { A.toast(err.message, 'error'); }
    });

    A.qs('#sb-delete').addEventListener('click', async function () {
      if (!editingSection) return;
      if (!await A.confirmDialog({ title: 'حذف بخش',
        message: 'بخش‌های دارای فیلد پایه فقط غیرفعال می‌شوند.' })) return;
      try {
        var res = await A.api.del('/api/form-builder/sections/' + editingSection.id);
        A.toast(res.message);
        A.closeModal('section-modal');
        await load();
      } catch (err) { A.toast(err.message, 'error'); }
    });

    var container = A.qs('#sections-container');
    container.addEventListener('click', function (ev) {
      var field = ev.target.closest('[data-edit-field]');
      if (field) { openFieldEditor(findField(field.dataset.editField)); return; }
      var section = ev.target.closest('[data-edit-section]');
      if (section) {
        openSectionEditor(schema.sections.find(function (s) {
          return s.id === +section.dataset.editSection;
        }));
      }
    });

    container.addEventListener('dragstart', function (ev) {
      dragged = ev.target.closest('[data-field-id]');
      if (dragged) dragged.classList.add('dragging');
    });
    container.addEventListener('dragend', async function () {
      if (!dragged) return;
      dragged.classList.remove('dragging');
      dragged = null;
      var order = A.qsa('[data-field-id]', container)
        .map(function (row) { return row.dataset.fieldId; });
      try {
        await A.api.post('/api/form-builder/reorder', { fields: order });
        A.toast('ترتیب فیلدها ذخیره شد.');
      } catch (err) { A.toast(err.message, 'error'); }
    });
    container.addEventListener('dragover', function (ev) {
      ev.preventDefault();
      var over = ev.target.closest('[data-field-id]');
      if (!over || !dragged || over === dragged) return;
      var rect = over.getBoundingClientRect();
      over.parentNode.insertBefore(dragged,
        (ev.clientY - rect.top) > rect.height / 2 ? over.nextSibling : over);
    });
  });
})();
