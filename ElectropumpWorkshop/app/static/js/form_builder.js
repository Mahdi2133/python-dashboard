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
    file: 'مستند (بارگذاری فایل)', formula: 'محاسباتی (فرمول)', mirror: 'فیلد مشترک',
    numbers: 'چند مقدار عددی (مثلاً فاز ۱/۲/۳)', chart: 'نمودار',
    wh_lines: 'اقلام انبار (تجهیز / قطعه)'
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
      + ((field.approval_rules || []).length
          ? '<span class="badge warn" title="' + A.esc(field.approval_rules.map(function (r) {
              return r.options.join('، ') + ' ← ' + userNames(r.approvers);
            }).join(' | ')) + '">✅ ارجاع تأیید' + (field.approval_rules.length > 1
              ? ' (' + J.toFaDigits(field.approval_rules.length) + ')' : '') + '</span>' : '')
      + ((field.block_options || []).length
          ? '<span class="badge danger" title="' + A.esc(field.block_options.join('، ')) + '">⛔ مانع ارسال</span>' : '')
      + (field.field_type === 'numbers' && field.part_labels
          ? '<span class="badge">' + A.esc(field.part_labels.join(' / ')) + '</span>' : '')
      + (field.field_type === 'formula' && field.result_type === 'text' ? '<span class="badge">نتیجه‌ی متنی</span>' : '')
      + ((field.fill_stage_ids || []).length ? '<span class="badge">🖊 ' + stageNames(field.fill_stage_ids) + '</span>' : '')
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

  function userNames(ids) {
    return (ids || []).map(function (id) {
      var u = (schema.users || []).find(function (x) { return x.id === id; });
      return u ? u.name : '#' + id;
    }).join('، ');
  }

  function stageNames(ids) {
    return (schema.stages || []).filter(function (s) { return ids.indexOf(s.id) !== -1; })
      .map(function (s) { return 'مرحله ' + J.toFaDigits(s.stage_number); }).join('، ') || 'مرحله';
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
    drawOptions();
    renderApprovalOptions();
  }
  function syncApprovalBox() {
    var t = A.qs('#fb-type').value;
    A.qs('#fb-approval-box').classList.toggle('hidden', t === 'numbers');
  }

  function drawOptions() {
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
                       'autocomplete', 'checklist', 'numbers'];
    syncApprovalBox();
    if (!field) {
      /* New field: options are typed in before the field exists. */
      var t = A.qs('#fb-type').value;
      wrap.classList.toggle('hidden', !choiceTypes.includes(t));
      optionState.source = 'own';
      if (t === 'numbers') {
        /* «چند مقدار عددی»: the options name the parts */
        optionState.rows = ['فاز ۱', 'فاز ۲', 'فاز ۳'].map(function (v) {
          return { value: v, label: v, icon: '', is_active: true };
        });
      }
      note.innerHTML = '<div class="alert info small">' + (t === 'numbers'
        ? 'هر گزینه نام یک خانه‌ی عددی است (مثلاً فاز ۱، فاز ۲، فاز ۳)؛ کاربر برای هر کدام یک عدد وارد می‌کند.'
        : 'این گزینه‌ها مخصوص همین فیلد خواهند بود.') + '</div>';
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
      } else if (field.field_type === 'numbers') {
        note.innerHTML = '<div class="alert info small">هر گزینه نام یک خانه‌ی عددی است (مثلاً فاز ۱، فاز ۲، فاز ۳). '
          + 'بدون گزینه، سه خانه‌ی فاز ۱ تا ۳ نشان داده می‌شود.</div>';
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
  /* «طبقات از کاتالوگ»: which field names the pump type */
  function fillStagesOf(field) {
    var box = A.qs('#fb-stages-of');
    if (!box) return;
    var current = field && field.stages_of ? field.stages_of : '';
    var all = [];
    (schema.sections || []).forEach(function (sec) {
      (sec.fields || []).forEach(function (f) {
        if (!field || f.field_name !== field.field_name) all.push(f);
      });
    });
    /* the pump-type fields first: those drawing on the «تیپ پمپ» list */
    all.sort(function (a, b) {
      var pa = a.lookup_category === 'pump_type' ? 0 : 1, pb = b.lookup_category === 'pump_type' ? 0 : 1;
      return pa - pb;
    });
    box.innerHTML = '<option value="">— خیر —</option>' + all.map(function (f) {
      return '<option value="' + A.esc(f.field_name) + '"' + (f.field_name === current ? ' selected' : '') + '>'
        + A.esc(f.label) + ' (' + A.esc(f.field_name) + ')</option>';
    }).join('');
  }
  function fillPrefill(field) {
    fillStagesOf(field);
    var box = A.qs('#fb-prefill');
    if (!box) return;
    var chain = (field && field.prefill_from ? field.prefill_from : '').split('|');
    fillPrefillBox(box, field, chain[0] || '');
    var box2 = A.qs('#fb-prefill2');
    if (box2) fillPrefillBox(box2, field, chain[1] || '');
  }
  function refOptions(current) {
    var groups = {};
    (schema.prefill_ref || []).forEach(function (o) {
      (groups[o.group] = groups[o.group] || []).push(o);
    });
    return Object.keys(groups).map(function (g) {
      return '<optgroup label="بانک اطلاعاتی — ' + A.esc(g) + '">' + groups[g].map(function (o) {
        return '<option value="' + A.esc(o.value) + '"' + (o.value === current ? ' selected' : '') + '>'
          + A.esc(o.label) + '</option>';
      }).join('') + '</optgroup>';
    }).join('');
  }
  function fillPrefillBox(box, field, current) {
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
    box.innerHTML = html + '</optgroup>' + refOptions(current);
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
    A.qs('#fb-result-type').value = field && field.result_type === 'text' ? 'text' : 'number';
    fillChart(field);
    fillWh(field);
    fillWhen(field && field.visible_when, 'fb', field && field.field_name);
    fillApproval(field);
    fillStages(field);
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
      prefill_from: [(A.qs('#fb-prefill') || {}).value || '', (A.qs('#fb-prefill2') || {}).value || '']
        .filter(Boolean).join('|'),
      placeholder: A.qs('#fb-placeholder').value.trim(),
      stages_of: (A.qs('#fb-stages-of') || {}).value || '',
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
      visible_when: readWhen('fb'),
      approval_rules: collectRules(),
      block_options: blockPicked.slice(),
      result_type: A.qs('#fb-result-type').value,
      chart_config: A.qs('#fb-type').value === 'chart' ? collectChart() : undefined,
      wh_config: A.qs('#fb-type').value === 'wh_lines' ? collectWh() : undefined,
      fill_stage_ids: A.qsa('#fb-fill-stages select').map(function (s) { return s.value; })
        .filter(Boolean).map(Number),
      options: collectOptions()
    };
  }

  /* «تأیید گزینه»: several rules, each its own answers → its own approvers
     (and, optionally, the question the approver answers). The same rules are
     shown and edited in «فرایندساز» under «ارجاعات برای تأیید». */
  var rulesState = [], blockPicked = [], editingAnswerOpts = '';
  function fillApproval(field) {
    rulesState = ((field && field.approval_rules) || []).map(function (r) {
      return { options: (r.options || []).map(String), approvers: (r.approvers || []).slice(),
               answer_field: r.answer_field || '', required: !!r.required };
    });
    blockPicked = ((field && field.block_options) || []).map(String);
    editingAnswerOpts = '';
    (schema.sections || []).forEach(function (sec) {
      (sec.fields || []).forEach(function (f) {
        if (!f.is_choice || (field && f.field_name === field.field_name)) return;
        editingAnswerOpts += '<option value="' + A.esc(f.field_name) + '">' + A.esc(f.label)
          + ' — ' + A.esc(sec.title) + '</option>';
      });
    });
    renderApprovalOptions();
  }
  function optionRows() { return optionState.rows.filter(function (o) { return o.value; }); }
  function renderApprovalOptions() {
    var box = A.qs('#fb-approval-rules');
    if (!box) return;
    var rows = optionRows();
    if (!rows.length) {
      box.innerHTML = '<span class="muted small">اول گزینه‌های فیلد را تعریف کنید.</span>';
      A.qs('#fb-block-options').innerHTML = '';
      return;
    }
    box.innerHTML = rulesState.length ? rulesState.map(function (r, i) {
      return '<div class="fb-rule" data-rule="' + i + '">'
        + '<div class="fb-rule-head"><b>قانون ' + J.toFaDigits(i + 1) + '</b>'
        + '<button type="button" class="btn-sm btn-del fb-rule-del" title="حذف قانون">✕</button></div>'
        + '<div class="fb-approval-options">' + rows.map(function (o) {
            var on = r.options.indexOf(String(o.value)) !== -1;
            return '<label class="mini-check' + (on ? ' on' : '') + '"><input type="checkbox" class="fb-rule-opt" value="'
              + A.esc(o.value) + '"' + (on ? ' checked' : '') + '> ' + A.esc(o.label || o.value) + '</label>';
          }).join('') + '</div>'
        + '<div class="fb-inline"><label>تأییدکننده‌ها</label><select class="fb-rule-users" multiple size="4">'
        + (schema.users || []).map(function (u) {
            return '<option value="' + u.id + '"' + (r.approvers.indexOf(u.id) !== -1 ? ' selected' : '') + '>'
              + A.esc(u.name) + '</option>';
          }).join('') + '</select></div>'
        + '<label class="mini-check' + (r.required ? ' on' : '') + '"><input type="checkbox" class="fb-rule-req"'
        + (r.required ? ' checked' : '') + '> الزامی — تا پاسخ نیاید مرحله ثبت نشود (بدون تیک: فقط برای اطلاع)</label>'
        + '<div class="fb-inline"><label>پاسخ تأییدکننده</label><select class="fb-rule-answer">'
        + '<option value="">— فقط تأیید / عدم تأیید —</option>'
        + editingAnswerOpts.replace('value="' + A.esc(r.answer_field) + '"',
                                    'value="' + A.esc(r.answer_field) + '" selected')
        + '</select></div></div>';
    }).join('') : '<span class="muted small">قانون تأییدی تعریف نشده؛ پاسخ‌های این فیلد تأیید نمی‌خواهند.</span>';
    A.qs('#fb-block-options').innerHTML = rows.map(function (o) {
      var on = blockPicked.indexOf(String(o.value)) !== -1;
      return '<label class="mini-check' + (on ? ' on' : '') + '"><input type="checkbox" class="fb-block-opt" value="'
        + A.esc(o.value) + '"' + (on ? ' checked' : '') + '> ' + A.esc(o.label || o.value) + '</label>';
    }).join('');
  }
  function collectRules() {
    return rulesState.filter(function (r) { return r.options.length || r.approvers.length; });
  }
  function bindApproval() {
    var box = A.qs('#fb-approval-rules');
    box.addEventListener('change', function (ev) {
      var row = ev.target.closest('[data-rule]');
      if (!row) return;
      var r = rulesState[+row.dataset.rule];
      if (ev.target.classList.contains('fb-rule-opt')) {
        var v = String(ev.target.value);
        r.options = r.options.filter(function (x) { return x !== v; });
        if (ev.target.checked) r.options.push(v);
        ev.target.closest('label').classList.toggle('on', ev.target.checked);
      } else if (ev.target.classList.contains('fb-rule-users')) {
        r.approvers = Array.prototype.slice.call(ev.target.selectedOptions).map(function (o) { return Number(o.value); });
      } else if (ev.target.classList.contains('fb-rule-answer')) {
        r.answer_field = ev.target.value;
      } else if (ev.target.classList.contains('fb-rule-req')) {
        r.required = ev.target.checked;
        ev.target.closest('label').classList.toggle('on', ev.target.checked);
      }
    });
    box.addEventListener('click', function (ev) {
      var del = ev.target.closest('.fb-rule-del');
      if (!del) return;
      rulesState.splice(+del.closest('[data-rule]').dataset.rule, 1);
      renderApprovalOptions();
    });
    A.qs('#fb-rule-add').addEventListener('click', function () {
      rulesState.push({ options: [], approvers: [], answer_field: '', required: false });
      renderApprovalOptions();
    });
    A.qs('#fb-block-options').addEventListener('change', function (ev) {
      if (!ev.target.classList.contains('fb-block-opt')) return;
      var v = String(ev.target.value);
      blockPicked = blockPicked.filter(function (x) { return x !== v; });
      if (ev.target.checked) blockPicked.push(v);
      ev.target.closest('label').classList.toggle('on', ev.target.checked);
    });
  }

  /* «نمودار»: series of X/Y fields of the form, each with its axis and trend. */
  var chartState = [];
  var TRENDS = { '': 'بدون خط روند', poly2_0: 'درجه ۲ از مبدأ (aQ² + bQ)', poly2: 'درجه ۲',
                 power: 'توانی', linear: 'خطی' };
  function numericFieldOptions() {
    var html = '';
    (schema.sections || []).forEach(function (sec) {
      var g = '';
      (sec.fields || []).forEach(function (f) {
        if (['number', 'formula', 'mirror'].indexOf(f.field_type) === -1) return;
        g += '<option value="' + A.esc(f.field_name) + '">' + A.esc(f.label) + ' (' + A.esc(f.field_name) + ')</option>';
      });
      if (g) html += '<optgroup label="' + A.esc(sec.title) + '">' + g + '</optgroup>';
    });
    return html;
  }
  /* «اقلام انبار»: which warehouse, in or out, why; free rows or a parts form */
  var WH_REASONS = { pull: 'کشیدن الکتروپمپ از چاه', disassembly: 'دمونتاژ و تفکیک', purchase: 'خرید نو',
                     repair: 'تعمیر', assembly: 'مصرف در مونتاژ (ساخت)', assembled: 'الکتروپمپ مونتاژشده',
                     install: 'خروج برای نصب', scrap: 'اسقاط', manual: 'اصلاح موجودی' };
  var WH_CONDS = { reusable: 'قابل استفاده مجدد', repair: 'تعمیری', 'new': 'نو', scrap: 'اسقاط',
                   assembled: 'مونتاژشده — آماده نصب' };
  var WH_COLS = { installed_new: 'نصب — نو', installed_repair: 'نصب — کهنه (قابل استفاده مجدد)', collected_new: 'جمع‌آوری — نو',
                  collected_old: 'جمع‌آوری — کهنه', reusable: 'قابل استفاده مجدد', scrap: 'اسقاط' };
  function checks(box, map, picked) {
    A.qs(box).innerHTML = Object.keys(map).map(function (k) {
      return '<label class="small"><input type="checkbox" value="' + k + '" style="width:auto"'
        + (picked.indexOf(k) !== -1 ? ' checked' : '') + '> ' + A.esc(map[k]) + '</label>';
    }).join(' ');
  }
  function whModeSync() {
    var parts = A.qs('#fb-wh-mode').value === 'parts';
    A.qsa('.fb-wh-parts').forEach(function (el) { el.classList.toggle('hidden', !parts); });
    A.qsa('.fb-wh-rows').forEach(function (el) { el.classList.toggle('hidden', parts); });
    if (parts) loadPartsList();
  }

  /* «ردیف‌های ثابت»: the rows a warehouse form starts with */
  var whPreset = [];
  function drawWhPreset() {
    var box = A.qs('#fb-wh-preset');
    if (!box) return;
    var items = ((schema && schema.warehouse) || {}).items || [];
    box.innerHTML = whPreset.length ? '<table class="fb-mini-table"><thead><tr><th>کالا</th><th>مشخصات (فرمول یا متن)</th>'
      + '<th>تعداد</th><th></th></tr></thead><tbody>' + whPreset.map(function (r, i) {
        var known = items.some(function (it) { return it.code === r.item_code; });
        return '<tr data-preset="' + i + '"><td><select class="fb-wp-item"><option value="">—</option>'
          + items.map(function (it) {
              return '<option value="' + A.esc(it.code) + '"' + (it.code === r.item_code ? ' selected' : '') + '>'
                + A.esc(it.name) + ' (' + A.esc(it.code) + ')</option>';
            }).join('')
          + (r.item_code && !known ? '<option value="' + A.esc(r.item_code) + '" selected>' + A.esc(r.item_code) + '</option>' : '')
          + '</select></td><td><input type="text" dir="ltr" class="fb-wp-spec" value="' + A.esc(r.spec || '') + '"></td>'
          + '<td><input type="number" step="any" class="fb-wp-qty" value="' + A.esc(r.qty || 1) + '" style="width:70px"></td>'
          + '<td><button type="button" class="btn-sm btn-del fb-wp-del">✕</button></td></tr>';
      }).join('') + '</tbody></table>' : '<span class="hint">ردیف ثابتی تعریف نشده است.</span>';
  }
  function bindWhPreset() {
    var box = A.qs('#fb-wh-preset');
    if (!box) return;
    var sync = function (ev) {
      var tr = ev.target.closest('tr[data-preset]');
      if (!tr) return;
      var r = whPreset[+tr.dataset.preset];
      if (ev.target.classList.contains('fb-wp-item')) r.item_code = ev.target.value;
      if (ev.target.classList.contains('fb-wp-spec')) r.spec = ev.target.value;
      if (ev.target.classList.contains('fb-wp-qty')) r.qty = Number(ev.target.value) || 1;
    };
    box.addEventListener('change', sync);
    box.addEventListener('input', sync);
    box.addEventListener('click', function (ev) {
      var del = ev.target.closest('.fb-wp-del');
      if (!del) return;
      whPreset.splice(+del.closest('tr').dataset.preset, 1);
      drawWhPreset();
    });
    A.qs('#fb-wh-preset-add').addEventListener('click', function () {
      whPreset.push({ item_code: '', spec: '', qty: 1 });
      drawWhPreset();
    });
  }

  /* «فهرست قطعات»: the parts of one equipment kind, named and coded here —
     the same list the parts forms search and the warehouse counts */
  var partsList = [];
  async function loadPartsList() {
    var box = A.qs('#fb-wh-parts-list');
    if (!box) return;
    var kind = A.qs('#fb-wh-eq').value;
    box.innerHTML = '<div class="loading">بارگذاری</div>';
    try {
      var res = await A.api.get('/api/warehouse/items');
      partsList = (res.data.items || []).filter(function (it) { return it.kind === 'part' && it.category === kind; })
        .map(function (it) { return Object.assign({}, it, { _dirty: false }); });
    } catch (err) {
      box.innerHTML = '<div class="hint">' + A.esc(err.message) + '</div>';
      return;
    }
    drawPartsList();
  }
  function drawPartsList() {
    var box = A.qs('#fb-wh-parts-list');
    var active = partsList.filter(function (p) { return p.is_active; }).length;
    A.qs('#fb-wh-parts-state').textContent = active + ' قطعه‌ی فعال';
    box.innerHTML = '<input type="search" class="fb-parts-q" placeholder="جستجوی قطعه…">'
      + '<div class="table-scroll" style="max-height:280px"><table class="fb-mini-table"><thead><tr><th>کد انباری</th><th>شرح قطعه</th>'
      + '<th>فعال</th></tr></thead><tbody>' + partsList.map(function (p, i) {
        return '<tr data-part="' + i + '"' + (p.is_active ? '' : ' class="inactive"') + '>'
          + '<td><input type="text" dir="ltr" class="fb-pl-code" value="' + A.esc(p.code || '') + '" style="width:120px"></td>'
          + '<td><input type="text" class="fb-pl-name" value="' + A.esc(p.name || '') + '"></td>'
          + '<td><input type="checkbox" class="fb-pl-active" style="width:auto"' + (p.is_active ? ' checked' : '') + '></td></tr>';
      }).join('') + '</tbody></table></div>';
  }
  function bindPartsList() {
    var box = A.qs('#fb-wh-parts-list');
    if (!box) return;
    var sync = function (ev) {
      if (ev.target.classList.contains('fb-parts-q')) {
        var q = ev.target.value.trim();
        box.querySelectorAll('tr[data-part]').forEach(function (tr) {
          var p = partsList[+tr.dataset.part];
          tr.classList.toggle('hidden', !!q && (String(p.name) + ' ' + String(p.code || '')).indexOf(q) === -1);
        });
        return;
      }
      var tr = ev.target.closest('tr[data-part]');
      if (!tr) return;
      var p = partsList[+tr.dataset.part];
      if (ev.target.classList.contains('fb-pl-code')) p.code = ev.target.value;
      if (ev.target.classList.contains('fb-pl-name')) p.name = ev.target.value;
      if (ev.target.classList.contains('fb-pl-active')) { p.is_active = ev.target.checked; tr.classList.toggle('inactive', !p.is_active); }
      p._dirty = true;
    };
    box.addEventListener('input', sync);
    box.addEventListener('change', sync);
    A.qs('#fb-wh-eq').addEventListener('change', loadPartsList);
    A.qs('#fb-wh-part-new').addEventListener('click', function () {
      partsList.push({ id: null, code: '', name: '', kind: 'part', category: A.qs('#fb-wh-eq').value,
                       unit: 'عدد', is_active: true, _dirty: true });
      drawPartsList();
      var last = box.querySelector('tr[data-part]:last-child .fb-pl-name');
      if (last) last.focus();
    });
    A.qs('#fb-wh-parts-save').addEventListener('click', async function () {
      var rows = partsList.filter(function (p) { return p._dirty && (p.id || String(p.name || '').trim()); })
        .map(function (p) {
          return { id: p.id, code: p.code, name: p.name, kind: 'part', category: p.category || A.qs('#fb-wh-eq').value,
                   is_active: p.is_active };
        });
      if (!rows.length) { A.toast('تغییری در فهرست قطعات نیست.', 'info'); return; }
      try {
        var res = await A.api.post('/api/warehouse/items/bulk', { items: rows });
        A.toast(res.message, 'success');
        loadPartsList();
      } catch (err) { A.toast(err.message, 'error'); }
    });
  }
  /* The lists come from the warehouse's own tables when the schema has them
     (conditions are edited on the warehouse page, equipment kinds follow the
     item catalogue); the constants above are only the fallback. */
  function whLists() {
    var w = (schema && schema.warehouse) || {};
    var map = function (list) {
      var out = {};
      (list || []).forEach(function (x) { out[x.code] = x.label; });
      return out;
    };
    return {
      reasons: w.reasons && Object.keys(w.reasons).length ? w.reasons : WH_REASONS,
      conds: (w.conditions || []).length ? map(w.conditions) : WH_CONDS,
      cols: (w.columns || []).length ? map(w.columns) : WH_COLS,
      kinds: (w.equipment_types || []).length ? w.equipment_types : ['الکتروموتور شناور', 'پمپ شناور']
    };
  }
  function fillWh(field) {
    if (!A.qs('#fb-wh-mode')) return;
    var cfg = (field && field.wh_config) || {};
    var L = whLists();
    var kinds = L.kinds.slice();
    if (cfg.equipment_type && kinds.indexOf(cfg.equipment_type) === -1) kinds.push(cfg.equipment_type);
    A.qs('#fb-wh-eq').innerHTML = kinds.map(function (k) {
      return '<option value="' + A.esc(k) + '">' + A.esc(k) + '</option>';
    }).join('');
    A.qs('#fb-wh-reason').innerHTML = Object.keys(L.reasons).map(function (k) {
      return '<option value="' + k + '">' + A.esc(L.reasons[k]) + '</option>';
    }).join('');
    A.qs('#fb-wh-mode').value = cfg.mode === 'parts' ? 'parts' : 'rows';
    A.qs('#fb-wh-wh').value = cfg.warehouse || 'equipment';
    A.qs('#fb-wh-dir').value = cfg.direction || 'in';
    A.qs('#fb-wh-reason').value = cfg.reason || 'manual';
    A.qs('#fb-wh-kind').value = (cfg.kinds || [])[0] || '';
    A.qs('#fb-wh-eq').value = cfg.equipment_type || kinds[0] || '';
    A.qs('#fb-wh-eqf').value = cfg.equipment_field || '';
    A.qs('#fb-wh-fail').value = cfg.failure_field || '';
    A.qs('#fb-wh-cause').value = cfg.cause_field || '';
    A.qs('#fb-wh-act').value = cfg.action_field || '';
    checks('#fb-wh-conds', L.conds, cfg.conditions || []);
    checks('#fb-wh-cols', L.cols, cfg.columns || []);
    whPreset = (cfg.preset || []).map(function (r) { return Object.assign({}, r); });
    A.qs('#fb-wh-preset-lock').checked = !!cfg.preset_lock;
    drawWhPreset();
    whModeSync();
  }
  function collectWh() {
    var picked = function (box) {
      return A.qsa(box + ' input:checked').map(function (i) { return i.value; });
    };
    var mode = A.qs('#fb-wh-mode').value;
    return { mode: mode, warehouse: A.qs('#fb-wh-wh').value, direction: A.qs('#fb-wh-dir').value,
             reason: A.qs('#fb-wh-reason').value,
             kinds: A.qs('#fb-wh-kind').value ? [A.qs('#fb-wh-kind').value] : [],
             conditions: picked('#fb-wh-conds'), columns: picked('#fb-wh-cols'),
             equipment_type: A.qs('#fb-wh-eq').value, equipment_field: A.qs('#fb-wh-eqf').value.trim(),
             failure_field: A.qs('#fb-wh-fail').value.trim(), cause_field: A.qs('#fb-wh-cause').value.trim(),
             action_field: A.qs('#fb-wh-act').value.trim(),
             preset: whPreset.filter(function (r) { return r.item_code; }),
             preset_lock: A.qs('#fb-wh-preset-lock').checked };
  }

  function fillChart(field) {
    var cfg = (field && field.chart_config) || {};
    /* every setting of a series is kept — the curve, the scale, the colour,
       a catalogue curve's fields — not only what the rows below show */
    chartState = (cfg.series || []).map(function (sr) {
      var copy = JSON.parse(JSON.stringify(sr));
      copy.label = sr.label || '';
      if (!sr.catalogue) {
        copy.x = Array.isArray(sr.x) ? sr.x.slice() : [];
        copy.y = Array.isArray(sr.y) ? sr.y.slice() : [];
        copy.axis = sr.axis || 'left';
        copy.trend = sr.trend || '';
      }
      return copy;
    });
    if (!chartState.length) chartState.push({ label: '', x: [], y: [], axis: 'left', trend: '' });
    A.qs('#fb-chart-xl').value = cfg.x_label || '';
    A.qs('#fb-chart-yl').value = cfg.y_label || '';
    A.qs('#fb-chart-y2l').value = cfg.y2_label || '';
    A.qs('#fb-chart-ymax').value = cfg.y_max == null ? '' : cfg.y_max;
    A.qs('#fb-chart-y2max').value = cfg.y2_max == null ? '' : cfg.y2_max;
    drawChartSeries();
  }
  function multiSelect(cls, chosen, opts) {
    var html = opts;
    /* keep the chosen order: the i-th X goes with the i-th Y */
    chosen.forEach(function (n) {
      html = html.replace('value="' + A.esc(n) + '"', 'value="' + A.esc(n) + '" selected');
    });
    return '<select class="' + cls + '" multiple size="6">' + html + '</select>';
  }
  function drawChartSeries() {
    var opts = numericFieldOptions();
    A.qs('#fb-chart-series').innerHTML = chartState.map(function (sr, i) {
      if (sr.catalogue) {
        /* a catalogue curve: the model named by two fields of the form */
        var all = [];
        (schema.sections || []).forEach(function (sec) { (sec.fields || []).forEach(function (f) { all.push(f); }); });
        var pick = function (cls, current) {
          return '<select class="' + cls + '">' + all.map(function (f) {
            return '<option value="' + A.esc(f.field_name) + '"' + (f.field_name === current ? ' selected' : '') + '>'
              + A.esc(f.label) + ' (' + A.esc(f.field_name) + ')</option>';
          }).join('') + '</select>';
        };
        return '<div class="fb-rule" data-series="' + i + '">'
          + '<div class="fb-rule-head"><input type="text" class="fb-cs-label" placeholder="نام سری" value="' + A.esc(sr.label) + '">'
          + '<span class="badge">📘 منحنی کاتالوگ</span>'
          + '<button type="button" class="btn-sm btn-del fb-cs-del" title="حذف سری">✕</button></div>'
          + '<div class="field-group cols-2"><div class="field"><label>تیپ پمپ از فیلد</label>' + pick('fb-cs-cat-type', sr.catalogue.type) + '</div>'
          + '<div class="field"><label>تعداد طبقات از فیلد</label>' + pick('fb-cs-cat-stages', sr.catalogue.stages) + '</div></div>'
          + '</div>';
      }
      return '<div class="fb-rule" data-series="' + i + '">'
        + '<div class="fb-rule-head"><input type="text" class="fb-cs-label" placeholder="نام سری (مثلاً افت)" value="'
        + A.esc(sr.label) + '">'
        + '<select class="fb-cs-axis"><option value="left">محور چپ</option><option value="right"'
        + (sr.axis === 'right' ? ' selected' : '') + '>محور راست</option></select>'
        + '<select class="fb-cs-trend">' + Object.keys(TRENDS).map(function (k) {
            return '<option value="' + k + '"' + (sr.trend === k ? ' selected' : '') + '>' + TRENDS[k] + '</option>';
          }).join('') + '</select>'
        + '<button type="button" class="btn-sm btn-del fb-cs-del" title="حذف سری">✕</button></div>'
        + '<div class="field-group cols-2"><div class="field"><label>X (محور افقی) — به ترتیب ردیف‌ها</label>'
        + multiSelect('fb-cs-x', sr.x, opts) + '<span class="hint fb-cs-xl">' + A.esc(sr.x.join('، ')) + '</span></div>'
        + '<div class="field"><label>Y (محور عمودی) — به همان ترتیب</label>'
        + multiSelect('fb-cs-y', sr.y, opts) + '<span class="hint fb-cs-yl">' + A.esc(sr.y.join('، ')) + '</span></div></div>'
        /* a curve from a formula of x, drawn across the whole axis with its equation */
        + '<details class="fb-cs-curve"' + (sr.curve && sr.curve.y ? ' open' : '') + '><summary>📈 منحنی از فرمول (اختیاری)</summary>'
        + '<div class="field-group cols-3">'
        + '<div class="field span-2"><label>فرمول منحنی — [x] مقدار محور افقی</label><input type="text" dir="ltr" class="fb-cs-cy"'
        + ' placeholder="مثلاً: 100 * [fc_b] / ([fc_b] + [fc_a] * [x])" value="' + A.esc((sr.curve || {}).y || '') + '"></div>'
        + '<div class="field"><label>ضریب نمایش</label><input type="number" step="any" class="fb-cs-scale" placeholder="1"'
        + ' value="' + A.esc(sr.scale == null ? '' : sr.scale) + '"></div>'
        + '<div class="field"><label>شرط رسم (اختیاری)</label><input type="text" dir="ltr" class="fb-cs-creq"'
        + ' placeholder="AND([fc_b] > 0, [fc_a] >= 0)" value="' + A.esc((sr.curve || {}).require || '') + '"></div>'
        + '<div class="field span-2"><label>پیام وقتی شرط برقرار نیست</label><input type="text" class="fb-cs-cnote"'
        + ' value="' + A.esc((sr.curve || {}).note || '') + '"></div>'
        + '</div><span class="hint">نقطه‌ها همان X و Y بالا هستند و «ضریب نمایش» آن‌ها را مثلاً درصد می‌کند (۱۰۰)؛ منحنی و معادله‌ی آن از همین فرمول رسم می‌شود (واحدش در خود فرمول).</span></details>'
        + '</div>';
    }).join('');
  }
  function collectChart() {
    function num(id) { var v = A.qs(id).value; return v === '' ? null : Number(v); }
    return {
      series: chartState, x_label: A.qs('#fb-chart-xl').value.trim(), y_label: A.qs('#fb-chart-yl').value.trim(),
      y2_label: A.qs('#fb-chart-y2l').value.trim(), y_max: num('#fb-chart-ymax'), y2_max: num('#fb-chart-y2max')
    };
  }
  function bindChart() {
    var box = A.qs('#fb-chart-series');
    box.addEventListener('change', function (ev) {
      var row = ev.target.closest('[data-series]');
      if (!row) return;
      var sr = chartState[+row.dataset.series];
      if (ev.target.classList.contains('fb-cs-cat-type')) sr.catalogue.type = ev.target.value;
      if (ev.target.classList.contains('fb-cs-cat-stages')) sr.catalogue.stages = ev.target.value;
      if (ev.target.classList.contains('fb-cs-axis')) sr.axis = ev.target.value;
      if (ev.target.classList.contains('fb-cs-trend')) sr.trend = ev.target.value;
      ['x', 'y'].forEach(function (k) {
        if (!ev.target.classList.contains('fb-cs-' + k)) return;
        var now = Array.prototype.slice.call(ev.target.selectedOptions).map(function (o) { return o.value; });
        /* kept in the order they were picked */
        sr[k] = sr[k].filter(function (n) { return now.indexOf(n) !== -1; })
          .concat(now.filter(function (n) { return sr[k].indexOf(n) === -1; }));
        row.querySelector('.fb-cs-' + k + 'l').textContent = sr[k].join('، ');
      });
    });
    box.addEventListener('input', function (ev) {
      var row = ev.target.closest('[data-series]');
      if (!row) return;
      var sr = chartState[+row.dataset.series];
      if (ev.target.classList.contains('fb-cs-label')) sr.label = ev.target.value;
      if (ev.target.classList.contains('fb-cs-scale')) {
        if (ev.target.value === '') delete sr.scale; else sr.scale = Number(ev.target.value);
      }
      var keys = { 'fb-cs-cy': 'y', 'fb-cs-creq': 'require', 'fb-cs-cnote': 'note' };
      Object.keys(keys).forEach(function (cls) {
        if (!ev.target.classList.contains(cls)) return;
        sr.curve = sr.curve || {};
        sr.curve[keys[cls]] = ev.target.value;
      });
    });
    box.addEventListener('click', function (ev) {
      var del = ev.target.closest('.fb-cs-del');
      if (!del) return;
      chartState.splice(+del.closest('[data-series]').dataset.series, 1);
      drawChartSeries();
    });
    A.qs('#fb-chart-add').addEventListener('click', function () {
      chartState.push({ label: '', x: [], y: [], axis: 'left', trend: '' });
      drawChartSeries();
    });
  }

  /* «مرحله‌ی پرکردن»: one choice per process. */
  function fillStages(field) {
    var chosen = (field && field.fill_stage_ids) || [];
    var flows = {};
    (schema.stages || []).forEach(function (s) {
      (flows[s.workflow_id] = flows[s.workflow_id] || { name: s.workflow, stages: [] }).stages.push(s);
    });
    var ids = Object.keys(flows);
    A.qs('#fb-fill-wrap').classList.toggle('hidden', !ids.length);
    A.qs('#fb-fill-stages').innerHTML = ids.map(function (id) {
      var flow = flows[id];
      return '<label class="fb-inline"><span>' + A.esc(flow.name) + '</span><select data-workflow="' + id + '">'
        + '<option value="">— با فرم خودش (هر مرحله‌ای که فرمش را دارد) —</option>'
        + flow.stages.map(function (s) {
            return '<option value="' + s.id + '"' + (chosen.indexOf(s.id) !== -1 ? ' selected' : '') + '>مرحله '
              + J.toFaDigits(s.stage_number) + ' — ' + A.esc(s.title) + '</option>';
          }).join('') + '</select></label>';
    }).join('');
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
  function optionsOf(field) {
    if (field.own_options && field.own_options.length) return field.own_options;
    if (field.lookup_category) {
      return (schema.lookups || {})[field.lookup_category] || [];
    }
    return [];
  }

  /* A section — or a single field — may be opened by several questions
     («a=x;b=y»). This editor shows the first; the others are kept as they are
     and listed, and are edited in «اتصال‌ها» at the top of the page. The same
     editor serves the section dialog (prefix «sb») and the field dialog («fb»). */
  var whenRest = { sb: [], fb: [] };
  var ANY = '*';
  function whenSources(except) {
    var out = [];
    (schema.sections || []).forEach(function (sec) {
      (sec.fields || []).forEach(function (f) {
        if (except && f.field_name === except) return;
        if (['file', 'chart', 'checklist'].indexOf(f.field_type) !== -1) return;
        out.push(f);
      });
    });
    return out;
  }
  function fillWhen(rule, prefix, except) {
    prefix = prefix || 'sb';
    var rules = String(rule || '').split(';').filter(function (r) {
      return r.indexOf('=') !== -1;
    });
    whenRest[prefix] = rules.slice(1);
    var parts = String(rules[0] || '').split('=');
    var onName = parts[0] || '', value = parts.slice(1).join('=') || '';
    var note = A.qs('#' + prefix + '-when-more');
    if (note) {
      note.textContent = whenRest[prefix].length
        ? 'با ' + J.toFaDigits(whenRest[prefix].length) + ' پرسش دیگر هم باز می‌شود ('
          + whenRest[prefix].map(function (r) {
              var f = whenSources().find(function (x) { return x.field_name === r.split('=')[0]; });
              return f ? f.label : r.split('=')[0];
            }).join('، ') + ')؛ آن‌ها سر جایشان می‌مانند.'
        : '';
    }
    var fieldBox = A.qs('#' + prefix + '-when-field');
    var valueBox = A.qs('#' + prefix + '-when-value');
    if (!fieldBox || !valueBox) return;
    fieldBox.innerHTML = '<option value="">— همیشه نشان داده شود —</option>'
      + whenSources(except).map(function (f) {
          return '<option value="' + A.esc(f.field_name) + '"'
            + (f.field_name === onName ? ' selected' : '') + '>'
            + A.esc(f.label) + '</option>';
        }).join('');
    fillWhenValues(onName, value, prefix);
  }

  /* Several values may open the same thing («a|b|c»), so the value list is a
     multi-select; «✳ هر مقدار» opens it as soon as the question is answered —
     «نحوه‌ی کشیدن» once «متراژ کشیده شده» holds a number. */
  function fillWhenValues(onName, selected, prefix) {
    prefix = prefix || 'sb';
    var valueBox = A.qs('#' + prefix + '-when-value');
    if (!valueBox) return;
    var picked = String(selected || '').split('|');
    var field = whenSources().find(function (f) { return f.field_name === onName; });
    var opts = field ? [{ value: ANY, label: '✳ هر مقدار (به‌محض پر شدن)' }].concat(optionsOf(field)) : [];
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

  function readWhen(prefix) {
    prefix = prefix || 'sb';
    var onName = (A.qs('#' + prefix + '-when-field') || {}).value || '';
    var box = A.qs('#' + prefix + '-when-value');
    var values = box ? Array.prototype.slice.call(box.selectedOptions)
      .map(function (o) { return o.value; }).filter(Boolean) : [];
    if (values.indexOf(ANY) !== -1) values = [ANY];
    var rest = whenRest[prefix].filter(function (r) { return r.split('=')[0] !== onName; });
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
    A.qs('#sb-collapse').value = section && section.collapse_formulas ? '1' : '0';
    A.qs('#sb-repeat').value = section && section.repeat_group ? section.repeat_group : '';
    fillWhen(section && section.visible_when, 'sb');
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
      collapse_formulas: A.qs('#sb-collapse').value === '1',
      repeat_group: A.qs('#sb-repeat').value.trim(),
      visible_when: readWhen('sb')
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
      fillWhenValues(this.value, '', 'sb');
    });
    A.qs('#fb-when-field').addEventListener('change', function () {
      fillWhenValues(this.value, '', 'fb');
    });
    A.qs('#fb-save').addEventListener('click', saveField);
    A.qs('#sb-save').addEventListener('click', saveSection);

    /* Changing the type of a NEW field toggles the option editor. */
    A.qs('#fb-type').addEventListener('change', function () {
      if (!editingField) loadOptions(null);
      toggleSpecial();
    });
    bindApproval();
    bindChart();
    if (A.qs('#fb-wh-mode')) A.qs('#fb-wh-mode').addEventListener('change', whModeSync);
    bindWhPreset();
    bindPartsList();
    /* an option typed or renamed in the list shows up among the approvable ones */
    A.qs('#fb-options-list').addEventListener('change', renderApprovalOptions);
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
