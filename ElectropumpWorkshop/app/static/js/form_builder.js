(function () {
  'use strict';
  var A = window.App, J = window.Jalali;
  var schema = null, editingField = null, editingSection = null, dragged = null;
  var optionState = { source: null, readonly: false, rows: [] };

  var TYPE_LABELS = {
    text: 'متن', number: 'عدد', textarea: 'متن بلند', date: 'تاریخ میلادی',
    jalali_date: 'تاریخ شمسی', select: 'لیست کشویی', radio: 'تک‌انتخابی',
    checkbox: 'چندانتخابی', multiselect: 'چندانتخابی (لیست)',
    autocomplete: 'جستجوی خودکار', checklist: 'چک‌لیست',
    file: 'مستند (بارگذاری فایل)', formula: 'محاسباتی (فرمول)', mirror: 'فیلد مشترک'
  };

  /* Show the settings panel of the chosen special type only. */
  function toggleSpecial() {
    var t = A.qs('#fb-type').value;
    A.qsa('.fb-special').forEach(function (p) { p.classList.toggle('hidden', p.dataset.for !== t); });
  }
  function fillFieldPickers(field) {
    var opts = '';
    (schema.sections || []).forEach(function (sec) {
      var group = '';
      (sec.fields || []).forEach(function (f) {
        if (field && f.field_name === field.field_name) return;
        if (f.field_type === 'mirror') return;
        group += '<option value="' + A.esc(f.field_name) + '">' + A.esc(f.label) + ' (' + A.esc(f.field_name) + ')</option>';
      });
      if (group) opts += '<optgroup label="' + A.esc(sec.title) + '">' + group + '</optgroup>';
    });
    A.qs('#fb-mirror').innerHTML = '<option value="">— انتخاب فیلد —</option>' + opts;
    A.qs('#fb-formula-field').innerHTML = '<option value="">＋ درج فیلد…</option>' + opts;
  }

  async function load() {
    var res = await A.api.get('/api/form-builder?all=1');
    schema = res.data;
    render();
    if (window.CauseLinksReload) window.CauseLinksReload();
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
      + (field.field_type === 'mirror' ? '<span class="badge">🔗 ' + A.esc(field.mirror_of || '?') + '</span>' : '')
      + (field.field_type === 'formula' ? '<span class="badge mono" dir="ltr">= ' + A.esc((field.formula || '').slice(0, 40)) + '</span>' : '')
      + '<span class="badge muted mono">' + A.esc(field.field_name) + '</span>'
      + (field.is_builtin ? '<span class="badge">پایه</span>'
          : '<span class="badge ok">سفارشی</span>')
      + (field.is_required ? '<span class="badge danger">الزامی</span>' : '')
      + (field.show_in_table ? '<span class="badge">در جدول</span>' : '')
      + (field.lookup_category
          ? '<span class="badge">' + A.esc(field.lookup_category) + '</span>' : '')
      + (field.is_active ? '' : '<span class="badge muted">پنهان</span>')
      + '<span class="spacer"></span>'
      + '<button class="btn-sm btn-edit" data-move-field="' + field.id
      + '" title="انتقال یا کپی به بخش دیگر">📦 انتقال / کپی</button>'
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

  /* ── option editor ──────────────────────────────────────────────────── */
  function renderOptions() {
    var list = A.qs('#fb-options-list');
    var count = A.qs('#fb-options-count');
    count.textContent = optionState.rows.length
      ? optionState.rows.length + ' گزینه' : 'بدون گزینه';
    if (optionState.readonly) {
      list.innerHTML = optionState.rows.length
        ? optionState.rows.map(function (o) {
            return '<div class="badge muted">' + A.esc(o.label || o.value) + '</div>';
          }).join(' ')
        : '<span class="muted small">—</span>';
      return;
    }
    if (!optionState.rows.length) {
      list.innerHTML = '<span class="muted small">گزینه‌ای تعریف نشده. '
        + 'با دکمه‌ی «گزینه جدید» اضافه کنید.</span>';
      return;
    }
    list.innerHTML = '<div class="options-head"><span></span><span>مقدار ذخیره‌شده</span>'
      + '<span>برچسب نمایشی</span><span>آیکون</span><span>فعال</span><span></span></div>'
      + optionState.rows.map(function (o, i) {
          return '<div class="option-row' + (o.is_active ? '' : ' off')
            + '" draggable="true" data-i="' + i + '">'
            + '<span class="handle">⠿</span>'
            + '<input type="text" data-k="value" value="' + A.esc(o.value) + '">'
            + '<input type="text" data-k="label" value="' + A.esc(o.label || '') + '">'
            + '<input type="text" data-k="icon" maxlength="4" value="'
              + A.esc(o.icon || '') + '">'
            + '<button type="button" class="opt-toggle" title="فعال / غیرفعال">'
              + (o.is_active ? '✅' : '⛔') + '</button>'
            + '<button type="button" class="opt-del" title="حذف از فهرست">✕</button>'
            + '</div>';
        }).join('');
  }

  async function loadOptions(field) {
    var wrap = A.qs('#fb-options-wrap');
    var note = A.qs('#fb-options-note');
    optionState = { source: null, readonly: false, rows: [] };
    A.qs('#fb-options-bulk').classList.add('hidden');
    A.qs('#fb-options-bulk').value = '';

    var choiceTypes = ['select', 'radio', 'checkbox', 'multiselect',
                       'autocomplete', 'checklist'];
    if (!field) {
      /* New field: options are typed in before the field exists. */
      wrap.classList.toggle('hidden', !choiceTypes.includes(A.qs('#fb-type').value));
      optionState.source = 'own';
      note.innerHTML = '<div class="alert info small">این گزینه‌ها مخصوص همین فیلد '
        + 'خواهند بود.</div>';
      renderOptions();
      return;
    }
    if (!choiceTypes.includes(field.field_type)) {
      wrap.classList.add('hidden');
      return;
    }
    wrap.classList.remove('hidden');
    note.innerHTML = '<div class="loading small">در حال بارگذاری گزینه‌ها</div>';
    try {
      var res = await A.api.get('/api/form-builder/fields/' + field.id + '/options');
      var d = res.data;
      optionState.source = d.source;
      optionState.readonly = !!d.readonly;
      optionState.rows = (d.options || []).map(function (o) {
        return { value: o.value, label: o.label || o.value, icon: o.icon || '',
                 is_active: o.is_active !== false };
      });
      if (d.readonly) {
        note.innerHTML = '<div class="alert warn small">' + A.esc(d.note || '') + '</div>';
      } else if (d.source === 'lookup') {
        var shared = (d.shared_with || []);
        note.innerHTML = '<div class="alert warn small">این گزینه‌ها در فهرست مشترک '
          + '«<b>' + A.esc(d.category_name || d.category) + '</b>» نگهداری می‌شوند'
          + (shared.length
              ? ' و فیلدهای دیگری هم از آن استفاده می‌کنند: <b>'
                + shared.map(A.esc).join('، ') + '</b>. تغییر اینجا روی آن‌ها هم اثر می‌گذارد.'
              : '.')
          + ' گزینه‌ای که از فهرست بردارید <b>حذف نمی‌شود</b>، فقط غیرفعال می‌گردد تا '
          + 'رکوردهای قبلی سالم بمانند.</div>';
      } else {
        note.innerHTML = '<div class="alert info small">این گزینه‌ها مخصوص همین فیلد است.'
          + ' گزینه‌ی برداشته‌شده غیرفعال می‌شود، نه حذف.</div>';
      }
      renderOptions();
    } catch (err) {
      note.innerHTML = '<div class="alert error small">' + A.esc(err.message) + '</div>';
    }
  }

  function collectOptions() {
    return optionState.rows.filter(function (o) { return o.value; })
      .map(function (o) {
        return { value: o.value, label: o.label || o.value,
                 icon: o.icon || null, is_active: o.is_active };
      });
  }

  /* What a section or a field takes with it.

     A field lives in the form builder, but it is *used* by the process: a
     stage carries it, and a person owns that stage. Deleting it here takes it
     off their کارتابل, so say whose work changes before anything is removed. */
  async function usageNote(kind, code) {
    if (!code) return '';
    var text = '';
    try { text = await usageText(kind, code); } catch (err) { text = ''; }
    return text + await reportNote(kind === 'section' ? 'form' : 'field', code);
  }

  /* Which reports read this field or form — so removing it is not a surprise. */
  async function reportNote(kind, code) {
    try {
      var res = await A.api.get('/api/analytics/dependencies?kind=' + kind + '&ref=' + encodeURIComponent(code));
      var list = res.data || [];
      if (!list.length) return '';
      return '\n\n⚠ ' + J.toFaDigits(list.length) + ' گزارش از این مورد استفاده می‌کند: '
        + list.map(function (r) { return '«' + r.name + '»'; }).join('، ')
        + '. پس از حذف یا تغییر نوع، آن بخش‌های گزارش خطا می‌دهند تا در گزارش‌ساز اصلاح شوند.';
    } catch (err) { return ''; }
  }

  async function usageText(kind, code) {
    var data = await A.api.get('/api/workflow/uses?kind=' + encodeURIComponent(kind)
                               + '&code=' + encodeURIComponent(code));
    var stages = (data && data.data && data.data.stages) || [];
    if (!stages.length) {
      return '\n\nاین مورد در هیچ مرحله‌ای از فرایندها به کار نرفته است.';
    }
    var who = [];
    var lines = stages.map(function (s) {
      var owner = s.assignee || 'بدون متولی';
      if (s.assignee && who.indexOf(s.assignee) === -1) who.push(s.assignee);
      return '• مرحله ' + J.toFaDigits(s.stage_number) + ' — ' + s.title
             + ' (' + owner + ')' + (s.locked ? ' — فقط نمایشی' : '');
    });
    var head = '\n\nاین مورد هم‌اکنون در ' + J.toFaDigits(stages.length)
               + ' مرحله از فرایند به کار رفته است:\n' + lines.join('\n');
    if (who.length) {
      head += '\n\nبا حذف آن، این مورد از کارتابل ' + who.join('، ')
              + ' برداشته می‌شود.';
    }
    return head;
  }

  /* «پر شدن خودکار از سوابق همان چاه»: which answer on the well's last
     operation this field starts from. The list is when it happened, then
     every field the form has — so a reading added today can be carried
     forward tomorrow without anyone touching the code. */
  function fillPrefill(field) {
    var box = A.qs('#fb-prefill');
    if (!box) return;
    var current = field && field.prefill_from ? field.prefill_from : '';
    var html = '<option value="">— خیر —</option>'
      + '<optgroup label="زمان آخرین عملیات">'
      + (schema.prefill_when || []).map(function (w) {
          return '<option value="' + A.esc(w.value) + '"'
            + (w.value === current ? ' selected' : '') + '>'
            + A.esc(w.label) + '</option>';
        }).join('') + '</optgroup><optgroup label="مشخصات ثبت‌شده‌ی خود چاه">'
      + (schema.prefill_well || []).map(function (w) {
          return '<option value="' + A.esc(w.value) + '"'
            + (w.value === current ? ' selected' : '') + '>'
            + A.esc(w.label) + '</option>';
        }).join('')
      + '</optgroup><optgroup label="مقدار یک فیلد در سوابق چاه (آخرین عملیاتی که آن را دارد)">'
      + '<option value="@self"' + (current === '@self' ? ' selected' : '') + '>'
      + '★ همین فیلد — مقداری که آخرین بار برای این چاه ثبت شده</option>';
    (schema.sections || []).forEach(function (sec) {
      (sec.fields || []).forEach(function (f) {
        if (field && f.field_name === field.field_name) return;
        html += '<option value="' + A.esc(f.field_name) + '"'
          + (f.field_name === current ? ' selected' : '') + '>'
          + A.esc(f.label) + ' — ' + A.esc(sec.title) + '</option>';
      });
    });
    box.innerHTML = html + '</optgroup>';
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
    fillPrefill(field);
    A.qs('#fb-placeholder').value = field && field.placeholder ? field.placeholder : '';
    A.qs('#fb-lookup').value = field && field.lookup_category ? field.lookup_category : '';
    fillFieldPickers(field);
    A.qs('#fb-accept').value = field && field.file_accept ? field.file_accept : '';
    A.qs('#fb-multiple').value = field && field.file_multiple === false ? '0' : '1';
    A.qs('#fb-formula').value = field && field.formula ? field.formula : '';
    A.qs('#fb-formula-status').textContent = '';
    A.qs('#fb-mirror').value = field && field.mirror_of ? field.mirror_of : '';
    toggleSpecial();
    A.qs('#fb-lookup').disabled = !!(field && field.is_builtin);
    A.qs('#fb-min').value = field && field.min_value !== null ? field.min_value : '';
    A.qs('#fb-max').value = field && field.max_value !== null ? field.max_value : '';
    A.qs('#fb-step').value = field && field.step ? field.step : '';
    A.qs('#fb-help').value = field && field.help_text ? field.help_text : '';
    A.qs('#fb-other').value = field && field.allow_other ? '1' : '0';
    A.qs('#fb-export').value = field && field.export_header ? field.export_header : '';
    A.qs('#fb-delete').classList.toggle('hidden', !field);
    A.openModal('field-modal');
    loadOptions(field);
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
      prefill_from: (A.qs('#fb-prefill') || {}).value || '',
      placeholder: A.qs('#fb-placeholder').value.trim(),
      lookup_category: A.qs('#fb-lookup').value,
      min_value: A.qs('#fb-min').value, max_value: A.qs('#fb-max').value,
      step: A.qs('#fb-step').value.trim(),
      help_text: A.qs('#fb-help').value.trim(),
      allow_other: A.qs('#fb-other').value === '1',
      export_header: A.qs('#fb-export').value.trim(),
      file_accept: A.qs('#fb-accept').value.trim(),
      file_multiple: A.qs('#fb-multiple').value === '1',
      formula: A.qs('#fb-formula').value.trim(),
      mirror_of: A.qs('#fb-mirror').value,
      options: collectOptions()
    };
  }

  async function saveField() {
    var payload = collectField();
    if (!payload.field_name || !payload.label) {
      A.toast('نام فنی و برچسب الزامی است.', 'error'); return;
    }
    var options = payload.options;
    /* A lookup-backed field keeps its options in the shared category, so they
       are saved through the options endpoint rather than with the field. */
    if (editingField && payload.field_type !== editingField.field_type) {
      var note = await reportNote('field', editingField.field_name);
      if (note && !(await A.confirmDialog({ title: 'تغییر نوع فیلد',
        message: 'نوع فیلد عوض می‌شود.' + note, confirmText: 'تغییر بده', danger: false }))) return;
    }
    var optionsAreShared = editingField && optionState.source === 'lookup';
    if (optionsAreShared || optionState.readonly) delete payload.options;

    try {
      var res = editingField
        ? await A.api.put('/api/form-builder/fields/' + editingField.id, payload)
        : await A.api.post('/api/form-builder/fields', payload);
      if (optionsAreShared && !optionState.readonly) {
        await A.api.put('/api/form-builder/fields/' + editingField.id + '/options',
                        { options: options });
      }
      A.toast(res.message);
      A.closeModal('field-modal');
      await load();
    } catch (err) { A.toast(err.message, 'error'); }
  }

  /* «نمایش فقط وقتی…» — two dropdowns rather than a typed rule.

     The rule is stored as «field=value», but nobody should have to know that
     to say «this block belongs to سوختن الکتروپمپ». The first list offers the
     choice fields that have options; the second offers that field's options. */
  function whenSources() {
    var out = [];
    (schema.sections || []).forEach(function (sec) {
      (sec.fields || []).forEach(function (f) {
        if (optionsOf(f).length) out.push(f);
      });
    });
    return out;
  }

  function optionsOf(field) {
    if (field.own_options && field.own_options.length) return field.own_options;
    if (field.lookup_category) {
      return (schema.lookups || {})[field.lookup_category] || [];
    }
    return [];
  }

  /* A section may be opened by several questions («a=x;b=y»). This editor
     shows the first; the others are kept as they are and listed, and are
     edited in «اتصال‌ها» at the top of the page. */
  var whenRest = [];
  function fillWhen(rule) {
    var rules = String(rule || '').split(';').filter(function (r) {
      return r.indexOf('=') !== -1;
    });
    whenRest = rules.slice(1);
    var parts = String(rules[0] || '').split('=');
    var onName = parts[0] || '', value = parts.slice(1).join('=') || '';
    var note = A.qs('#sb-when-more');
    if (note) {
      note.textContent = whenRest.length
        ? 'این بخش با ' + J.toFaDigits(whenRest.length) + ' پرسش دیگر هم باز می‌شود ('
          + whenRest.map(function (r) {
              var f = whenSources().find(function (x) { return x.field_name === r.split('=')[0]; });
              return f ? f.label : r.split('=')[0];
            }).join('، ') + ')؛ آن‌ها سر جایشان می‌مانند.'
        : '';
    }
    var fieldBox = A.qs('#sb-when-field');
    var valueBox = A.qs('#sb-when-value');
    if (!fieldBox || !valueBox) return;
    fieldBox.innerHTML = '<option value="">— همیشه نشان داده شود —</option>'
      + whenSources().map(function (f) {
          return '<option value="' + A.esc(f.field_name) + '"'
            + (f.field_name === onName ? ' selected' : '') + '>'
            + A.esc(f.label) + '</option>';
        }).join('');
    fillWhenValues(onName, value);
  }

  /* Several values may open the same section («a|b|c»), so the value list is
     a multi-select; the same links are edited more comfortably in «اتصال
     علت‌های خرابی به فرم‌ها» at the top of the page. */
  function fillWhenValues(onName, selected) {
    var valueBox = A.qs('#sb-when-value');
    if (!valueBox) return;
    var picked = String(selected || '').split('|');
    var field = whenSources().find(function (f) { return f.field_name === onName; });
    var opts = field ? optionsOf(field) : [];
    valueBox.multiple = true;
    valueBox.size = Math.min(6, Math.max(3, opts.length));
    valueBox.innerHTML = opts.map(function (o) {
      var v = o.value === undefined ? o : o.value;
      return '<option value="' + A.esc(v) + '"'
        + (picked.indexOf(String(v)) !== -1 ? ' selected' : '') + '>'
        + A.esc(o.label || v) + '</option>';
    }).join('');
    valueBox.disabled = !opts.length;
  }

  function readWhen() {
    var onName = (A.qs('#sb-when-field') || {}).value || '';
    var box = A.qs('#sb-when-value');
    var values = box ? Array.prototype.slice.call(box.selectedOptions)
      .map(function (o) { return o.value; }).filter(Boolean) : [];
    var rest = whenRest.filter(function (r) { return r.split('=')[0] !== onName; });
    return (onName ? [onName + '=' + values.join('|')] : []).concat(rest).join(';');
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
    A.qs('#sb-entry').value = section && section.show_on_entry === false ? '0' : '1';
    fillWhen(section && section.visible_when);
    fillBring(section);
    A.qs('#sb-delete').classList.toggle('hidden', !section);
    A.openModal('section-modal');
  }

  async function saveSection() {
    var payload = {
      code: A.qs('#sb-code').value.trim(), title: A.qs('#sb-title').value.trim(),
      icon: A.qs('#sb-icon').value.trim(), columns: A.qs('#sb-columns').value,
      full_width: A.qs('#sb-full').value === '1',
      is_active: A.qs('#sb-active').value === '1',
      show_on_entry: A.qs('#sb-entry').value === '1',
      visible_when: readWhen()
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

  /* ── moving and copying fields between sections ─────────────────────── */
  /* The fields of every other section, to bring into this one. */
  function fillBring(section) {
    var box = A.qs('#sb-bring-box');
    if (!box) return;
    box.classList.toggle('hidden', !section);
    if (!section) return;
    A.qs('#sb-bring-field').innerHTML = '<option value="">— فیلدی را انتخاب کنید —</option>'
      + schema.sections.filter(function (s) { return s.id !== section.id; })
          .map(function (s) {
            return '<optgroup label="' + A.esc(s.title) + '">'
              + s.fields.map(function (f) {
                  return '<option value="' + f.id + '">' + A.esc(f.label)
                    + ' (' + A.esc(f.field_name) + ')</option>';
                }).join('') + '</optgroup>';
          }).join('');
  }

  async function moveField(fieldId, sectionId) {
    var field = findField(fieldId);
    var res = await A.api.put('/api/form-builder/fields/' + fieldId,
                              { section_id: sectionId, sort_order: 9999 });
    A.toast('«' + (field ? field.label : '') + '» به بخش جدید منتقل شد.');
    return res;
  }

  async function copyField(fieldId, sectionId, label) {
    var res = await A.api.post('/api/form-builder/fields/' + fieldId + '/copy',
                               { section_id: sectionId, label: label || null });
    A.toast(res.message);
    return res;
  }

  async function bring(mode) {
    var id = A.qs('#sb-bring-field').value;
    if (!id || !editingSection) { A.toast('ابتدا فیلد را انتخاب کنید.', 'error'); return; }
    try {
      if (mode === 'move') await moveField(id, editingSection.id);
      else await copyField(id, editingSection.id);
      await load();
      editingSection = schema.sections.find(function (s) { return s.id === editingSection.id; });
      fillBring(editingSection);
    } catch (err) { A.toast(err.message, 'error'); }
  }

  var moving = null;
  function openMove(field) {
    moving = field;
    A.qs('#copy-modal-title').textContent = 'انتقال یا کپی «' + field.label + '»';
    A.qs('#cp-section').innerHTML = schema.sections.map(function (s) {
      return '<option value="' + s.id + '"' + (s.id === field.section_id ? ' disabled' : '')
        + '>' + A.esc(s.title) + (s.id === field.section_id ? ' (بخش فعلی)' : '') + '</option>';
    }).join('');
    var first = schema.sections.find(function (s) { return s.id !== field.section_id; });
    if (first) A.qs('#cp-section').value = first.id;
    A.qs('input[name="cp-mode"][value="move"]').checked = true;
    A.qs('#cp-label').value = field.label;
    A.qs('#cp-label-row').classList.add('hidden');
    A.openModal('copy-modal');
  }

  window.FormBuilderReload = function () { return load(); };

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
    A.qs('#sb-when-field').addEventListener('change', function () {
      fillWhenValues(this.value, '');
    });
    A.qs('#fb-save').addEventListener('click', saveField);
    A.qs('#sb-save').addEventListener('click', saveSection);

    /* Changing the type of a NEW field toggles the option editor. */
    A.qs('#fb-type').addEventListener('change', function () {
      if (!editingField) loadOptions(null);
      toggleSpecial();
    });
    A.qs('#fb-formula-field').addEventListener('change', function () {
      if (!this.value) return;
      var t = A.qs('#fb-formula'), s0 = t.selectionStart || t.value.length;
      t.value = t.value.slice(0, s0) + '[' + this.value + ']' + t.value.slice(t.selectionEnd || s0);
      this.value = '';
      t.focus();
    });
    A.qs('#fb-formula-check').addEventListener('click', async function () {
      var st = A.qs('#fb-formula-status');
      try {
        var res = await A.api.post('/api/form-builder/formula/check', {
          formula: A.qs('#fb-formula').value, field_name: A.qs('#fb-name').value.trim() });
        st.textContent = res.data.valid ? '✓ معتبر — ورودی‌ها: ' + res.data.refs.join('، ') : '✕ ' + res.data.error;
        st.style.color = res.data.valid ? 'var(--success)' : 'var(--danger)';
      } catch (err) { st.textContent = err.message; }
    });

    var optList = A.qs('#fb-options-list');
    optList.addEventListener('input', function (ev) {
      var input = ev.target.closest('input[data-k]');
      if (!input) return;
      var row = +input.closest('[data-i]').dataset.i;
      optionState.rows[row][input.dataset.k] = input.value;
    });
    optList.addEventListener('click', function (ev) {
      var row = ev.target.closest('[data-i]');
      if (!row) return;
      var i = +row.dataset.i;
      if (ev.target.closest('.opt-toggle')) {
        optionState.rows[i].is_active = !optionState.rows[i].is_active;
        renderOptions();
      } else if (ev.target.closest('.opt-del')) {
        optionState.rows.splice(i, 1);
        renderOptions();
      }
    });
    var optDrag = null;
    optList.addEventListener('dragstart', function (ev) {
      optDrag = ev.target.closest('.option-row');
      if (optDrag) optDrag.classList.add('dragging');
    });
    optList.addEventListener('dragend', function () {
      if (!optDrag) return;
      optDrag.classList.remove('dragging');
      var order = A.qsa('.option-row', optList).map(function (r) { return +r.dataset.i; });
      optionState.rows = order.map(function (i) { return optionState.rows[i]; });
      optDrag = null;
      renderOptions();
    });
    optList.addEventListener('dragover', function (ev) {
      ev.preventDefault();
      var over = ev.target.closest('.option-row');
      if (!over || !optDrag || over === optDrag) return;
      var rect = over.getBoundingClientRect();
      over.parentNode.insertBefore(optDrag,
        (ev.clientY - rect.top) > rect.height / 2 ? over.nextSibling : over);
    });

    A.qs('#fb-opt-add').addEventListener('click', function () {
      if (optionState.readonly) return;
      optionState.rows.push({ value: '', label: '', icon: '', is_active: true });
      renderOptions();
      var inputs = A.qsa('.option-row input[data-k="value"]', optList);
      if (inputs.length) inputs[inputs.length - 1].focus();
    });

    A.qs('#fb-opt-bulk').addEventListener('click', function () {
      var box = A.qs('#fb-options-bulk');
      if (box.classList.contains('hidden')) {
        box.value = optionState.rows.map(function (o) {
          return [o.value, o.label, o.icon].filter(Boolean).join('|');
        }).join('\n');
        box.classList.remove('hidden');
        box.focus();
        A.toast('پس از ویرایش، دوباره روی «ورود گروهی» بزنید تا اعمال شود.');
      } else {
        var seen = {};
        optionState.rows.forEach(function (o) { seen[o.value] = o; });
        optionState.rows = box.value.split('\n').map(function (line) {
          var parts = line.split('|');
          var value = (parts[0] || '').trim();
          if (!value) return null;
          return { value: value, label: (parts[1] || value).trim(),
                   icon: (parts[2] || '').trim(),
                   is_active: seen[value] ? seen[value].is_active : true };
        }).filter(Boolean);
        box.classList.add('hidden');
        renderOptions();
      }
    });

    A.qs('#fb-delete').addEventListener('click', async function () {
      if (!editingField) return;
      var base = editingField.is_builtin
        ? 'این فیلد پایه است و حذف نمی‌شود؛ فقط از فرم پنهان می‌گردد.'
        : 'اگر رکوردی مقدار این فیلد را داشته باشد، فیلد فقط غیرفعال می‌شود.';
      var confirmed = await A.confirmDialog({
        title: 'حذف فیلد',
        message: base + await usageNote('field', editingField.field_name)
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
      var note = await usageNote('section', editingSection.code);
      if (!await A.confirmDialog({ title: 'حذف بخش',
        message: 'بخش‌های دارای فیلد پایه فقط غیرفعال می‌شوند.' + note })) return;
      try {
        var res = await A.api.del('/api/form-builder/sections/' + editingSection.id);
        A.toast(res.message);
        A.closeModal('section-modal');
        await load();
      } catch (err) { A.toast(err.message, 'error'); }
    });

    A.qs('#sb-bring-move').addEventListener('click', function () { bring('move'); });
    A.qs('#sb-bring-copy').addEventListener('click', function () { bring('copy'); });
    A.qsa('input[name="cp-mode"]').forEach(function (r) {
      r.addEventListener('change', function () {
        A.qs('#cp-label-row').classList.toggle('hidden',
          A.qs('input[name="cp-mode"]:checked').value !== 'copy');
      });
    });
    A.qs('#cp-go').addEventListener('click', async function () {
      if (!moving) return;
      var target = Number(A.qs('#cp-section').value);
      var mode = A.qs('input[name="cp-mode"]:checked').value;
      try {
        if (mode === 'move') await moveField(moving.id, target);
        else await copyField(moving.id, target, A.qs('#cp-label').value.trim());
        A.closeModal('copy-modal');
        await load();
      } catch (err) { A.toast(err.message, 'error'); }
    });

    var container = A.qs('#sections-container');
    container.addEventListener('click', function (ev) {
      var mv = ev.target.closest('[data-move-field]');
      if (mv) { openMove(findField(mv.dataset.moveField)); return; }
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
      /* Where each field now sits — its section as well as its place. */
      var placement = A.qsa('[data-field-id]', container).map(function (row) {
        return { id: Number(row.dataset.fieldId),
                 section_id: Number(row.closest('[data-fields]').dataset.fields) };
      });
      try {
        await A.api.post('/api/form-builder/reorder', { placement: placement });
        A.toast('جای فیلدها ذخیره شد.');
        await load();
      } catch (err) { A.toast(err.message, 'error'); await load(); }
    });
    container.addEventListener('dragover', function (ev) {
      if (!dragged) return;
      ev.preventDefault();
      var over = ev.target.closest('[data-field-id]');
      if (over && over !== dragged) {
        var rect = over.getBoundingClientRect();
        over.parentNode.insertBefore(dragged,
          (ev.clientY - rect.top) > rect.height / 2 ? over.nextSibling : over);
        return;
      }
      /* An empty section, or the space under a section's last field. */
      if (over) return;
      var section = ev.target.closest('[data-section]');
      var list = section && section.querySelector('[data-fields]');
      if (list && dragged.parentNode !== list) {
        var empty = list.querySelector('.muted.small');
        if (empty) empty.remove();
        list.appendChild(dragged);
      }
    });
  });
})();
