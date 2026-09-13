/* ==========================================================================
   Data-entry page. The form is not hardcoded: it is rendered from the
   form-builder schema returned by /api/form-builder, so anything an admin
   adds or hides there shows up here without a code change.
   ========================================================================== */
(function () {
  'use strict';
  var A = window.App, J = window.Jalali;
  var schema = null;
  var editingId = window.RECORD_ID || null;

  /* ── rendering ──────────────────────────────────────────────────────── */
  function optionsFor(field) {
    if (field.own_options && field.own_options.length) return field.own_options;
    if (field.lookup_category) return schema.lookups[field.lookup_category] || [];
    return [];
  }

  function labelHtml(field) {
    return '<label for="fld-' + A.esc(field.field_name) + '">' + A.esc(field.label)
      + (field.is_required ? ' <span class="req">*</span>' : '') + '</label>';
  }

  function renderChoice(field, multiple) {
    var opts = optionsFor(field);
    var type = multiple ? 'checkbox' : 'radio';
    var html = '<div class="btn-group' + (opts.length > 14 ? ' compact' : '')
      + '" data-field="' + A.esc(field.field_name) + '">';
    if (!multiple && !field.is_required) {
      html += '<label><input type="radio" name="' + A.esc(field.field_name)
        + '" value=""><span class="btn-opt">—</span></label>';
    }
    opts.forEach(function (opt) {
      html += '<label><input type="' + type + '" name="' + A.esc(field.field_name)
        + '" value="' + A.esc(opt.value) + '"'
        + (opt.is_default ? ' checked' : '') + '>'
        + '<span class="btn-opt">' + (opt.icon ? A.esc(opt.icon) + ' ' : '')
        + A.esc(opt.label) + '</span></label>';
    });
    html += '</div>';
    if (field.allow_other) {
      html += '<input type="text" class="other-input" data-other="'
        + A.esc(field.field_name) + '" placeholder="سایر موارد (در فهرست نیست)...">';
    }
    return html;
  }

  function renderSelect(field) {
    var opts = optionsFor(field);
    var html = '<select id="fld-' + A.esc(field.field_name) + '" name="'
      + A.esc(field.field_name) + '"><option value="">—</option>';
    opts.forEach(function (opt) {
      html += '<option value="' + A.esc(opt.value) + '">' + A.esc(opt.label) + '</option>';
    });
    return html + '</select>';
  }

  function renderInput(field) {
    var id = 'fld-' + A.esc(field.field_name);
    var attrs = ' id="' + id + '" name="' + A.esc(field.field_name) + '"';
    if (field.placeholder) attrs += ' placeholder="' + A.esc(field.placeholder) + '"';
    if (field.max_length) attrs += ' maxlength="' + field.max_length + '"';
    switch (field.field_type) {
      case 'number':
        if (field.min_value !== null) attrs += ' min="' + field.min_value + '"';
        if (field.max_value !== null) attrs += ' max="' + field.max_value + '"';
        attrs += ' step="' + A.esc(field.step || 'any') + '"';
        return '<input type="number"' + attrs + '>';
      case 'textarea':
        return '<textarea' + attrs + '></textarea>';
      case 'date':
        return '<input type="date"' + attrs + '>';
      case 'jalali_date':
        return '<input type="text" class="jdate"' + attrs + '>';
      case 'autocomplete':
        return '<div class="autocomplete-wrapper">'
          + '<input type="text" autocomplete="off" data-autocomplete="'
          + A.esc(field.lookup_category || 'wells') + '"' + attrs + '>'
          + '<div class="autocomplete-list"></div></div>';
      default:
        return '<input type="text"' + attrs + '>';
    }
  }

  function renderField(field) {
    var body;
    if (field.field_type === 'radio') body = renderChoice(field, false);
    else if (field.field_type === 'checkbox' && optionsFor(field).length) {
      body = renderChoice(field, true);
    } else if (field.field_type === 'checkbox') {
      body = '<div class="btn-group"><label><input type="checkbox" id="fld-'
        + A.esc(field.field_name) + '" name="' + A.esc(field.field_name)
        + '" value="1"><span class="btn-opt">بله</span></label></div>';
    } else if (field.field_type === 'multiselect') body = renderChoice(field, true);
    else if (field.field_type === 'select') body = renderSelect(field);
    else body = renderInput(field);

    var span = field.col_span > 1 ? ' span-' + Math.min(field.col_span, 2) : '';
    var wide = ['textarea', 'checkbox', 'multiselect'].includes(field.field_type)
      && optionsFor(field).length > 6 ? ' span-full' : '';
    return '<div class="field' + span + wide + '" data-wrap="'
      + A.esc(field.field_name) + '">'
      + labelHtml(field) + body
      + (field.help_text ? '<span class="hint">' + A.esc(field.help_text) + '</span>' : '')
      + '<span class="err hidden"></span></div>';
  }

  function renderForm() {
    var grid = A.qs('#form-grid');
    grid.innerHTML = schema.sections.map(function (section) {
      if (!section.fields.length) return '';
      return '<div class="form-section' + (section.full_width ? ' full-width' : '')
        + '"><div class="section-title">'
        + (section.icon ? '<span>' + A.esc(section.icon) + '</span>' : '')
        + '<span>' + A.esc(section.title) + '</span></div>'
        + '<div class="field-group cols-' + (section.columns || 3) + '">'
        + section.fields.map(renderField).join('')
        + '</div></div>';
    }).join('');

    A.qsa('.jdate', grid).forEach(function (input) { J.attach(input); });
    A.qsa('[data-autocomplete]', grid).forEach(setupAutocomplete);
    applyDefaults();
  }

  function applyDefaults() {
    schema.sections.forEach(function (section) {
      section.fields.forEach(function (field) {
        if (!field.default_value) return;
        setFieldValue(field, field.default_value);
      });
    });
    var dateInput = A.qs('#fld-op_jdate');
    if (dateInput && !dateInput.value && !editingId) {
      dateInput.value = J.format.apply(null, J.today());
    }
  }

  /* ── autocomplete (wells and lookup-backed text fields) ─────────────── */
  function setupAutocomplete(input) {
    var list = input.parentNode.querySelector('.autocomplete-list');
    var source = input.dataset.autocomplete;
    var hiddenId = null;

    var search = A.debounce(async function () {
      var value = input.value.trim();
      if (value.length < 1) { list.classList.remove('show'); return; }
      var items = [];
      if (source === 'wells' || source === 'well') {
        try {
          var res = await A.api.get('/api/wells?limit=15&q=' + encodeURIComponent(value));
          items = res.data.map(function (w) {
            return { value: w.name, label: w.name, id: w.id,
                     meta: w.center || (w.is_verified ? '' : 'تأییدنشده') };
          });
        } catch (err) { items = []; }
      } else {
        items = (schema.lookups[source] || []).filter(function (opt) {
          return opt.value.indexOf(value) >= 0 || opt.label.indexOf(value) >= 0;
        }).slice(0, 15).map(function (opt) {
          return { value: opt.value, label: opt.label, id: opt.id, meta: '' };
        });
      }
      if (!items.length) {
        list.innerHTML = '<div class="autocomplete-item create">'
          + '«' + A.esc(value) + '» در فهرست نیست — با ثبت رکورد افزوده می‌شود</div>';
        list.classList.add('show');
        return;
      }
      list.innerHTML = items.map(function (item) {
        return '<div class="autocomplete-item" data-value="' + A.esc(item.value) + '">'
          + A.esc(item.label)
          + (item.meta ? ' <span class="meta">— ' + A.esc(item.meta) + '</span>' : '')
          + '</div>';
      }).join('');
      list.classList.add('show');
    }, 180);

    input.addEventListener('input', search);
    input.addEventListener('focus', search);
    list.addEventListener('click', function (ev) {
      var item = ev.target.closest('.autocomplete-item[data-value]');
      if (!item) return;
      input.value = item.dataset.value;
      list.classList.remove('show');
      input.dispatchEvent(new Event('change', { bubbles: true }));
    });
    document.addEventListener('click', function (ev) {
      if (!input.parentNode.contains(ev.target)) list.classList.remove('show');
    });
  }

  /* ── reading / writing values ───────────────────────────────────────── */
  function checkedValues(name) {
    return A.qsa('input[name="' + name + '"]:checked')
      .map(function (i) { return i.value; }).filter(Boolean);
  }

  function otherValue(name) {
    var input = A.qs('[data-other="' + name + '"]');
    return input ? input.value.trim() : '';
  }

  function collect() {
    var payload = { dynamic: {} };
    schema.sections.forEach(function (section) {
      section.fields.forEach(function (field) {
        var name = field.field_name;
        var value;
        if (field.field_type === 'radio') {
          value = checkedValues(name)[0] || '';
          var other = otherValue(name);
          if (other) value = other;
        } else if (field.field_type === 'checkbox' || field.field_type === 'multiselect') {
          if (optionsFor(field).length) {
            value = checkedValues(name);
            var extra = otherValue(name);
            if (extra) value = value.concat(extra.split(',').map(function (v) {
              return v.trim();
            }).filter(Boolean));
          } else {
            var box = A.qs('#fld-' + name);
            value = box ? box.checked : false;
          }
        } else {
          var input = A.qs('#fld-' + name);
          value = input ? input.value.trim() : '';
        }

        if (field.model_attr) {
          if (name === 'op_jdate') { payload.op_jdate = value; return; }
          if (name === 'well') { payload.well = value; return; }
          /* Choice columns are sent by *value*, under the short key. */
          var key = field.model_attr.endsWith('_id')
            ? field.model_attr.slice(0, -3) : field.model_attr;
          payload[key] = value;
        } else if (['failure', 'workshop_opinion', 'desc_tags'].includes(name)) {
          payload[name] = value;
        } else {
          payload.dynamic[name] = value;
        }
      });
    });
    /* «سایر موارد خرابی» keeps its own column, as in the original form. */
    var failureOther = otherValue('failure');
    if (failureOther) payload.failure_other = failureOther;
    return payload;
  }

  function setFieldValue(field, value) {
    var name = field.field_name;
    if (field.field_type === 'radio') {
      var radio = A.qs('input[name="' + name + '"][value="' + CSS.escape(value || '') + '"]');
      if (radio) { radio.checked = true; return; }
      var other = A.qs('[data-other="' + name + '"]');
      if (other && value) other.value = value;
      return;
    }
    if (field.field_type === 'checkbox' || field.field_type === 'multiselect') {
      if (optionsFor(field).length) {
        var wanted = Array.isArray(value) ? value
          : String(value || '').split(',').map(function (v) { return v.trim(); });
        var unmatched = [];
        A.qsa('input[name="' + name + '"]').forEach(function (box) {
          box.checked = wanted.includes(box.value);
        });
        wanted.filter(Boolean).forEach(function (v) {
          if (!A.qs('input[name="' + name + '"][value="' + CSS.escape(v) + '"]')) {
            unmatched.push(v);
          }
        });
        var extra = A.qs('[data-other="' + name + '"]');
        if (extra && unmatched.length) extra.value = unmatched.join('، ');
      } else {
        var box2 = A.qs('#fld-' + name);
        if (box2) box2.checked = !!value && value !== '0' && value !== 'false';
      }
      return;
    }
    var input = A.qs('#fld-' + name);
    if (input) input.value = value === null || value === undefined ? '' : value;
  }

  function populate(record) {
    schema.sections.forEach(function (section) {
      section.fields.forEach(function (field) {
        var name = field.field_name;
        var value;
        if (name === 'op_jdate') value = record.date_display;
        else if (name === 'well') value = record.well;
        else if (['failure', 'workshop_opinion', 'desc_tags'].includes(name)) {
          value = record[name];
        } else if (field.model_attr) {
          var key = field.model_attr.endsWith('_id')
            ? field.model_attr.slice(0, -3) : field.model_attr;
          value = record[key];
        } else {
          value = (record.dynamic || {})[name];
        }
        setFieldValue(field, value);
      });
    });
    if (record.failure_other) {
      var other = A.qs('[data-other="failure"]');
      if (other) other.value = record.failure_other;
    }
  }

  function clearForm() {
    A.qsa('#form-grid input, #form-grid textarea, #form-grid select').forEach(function (el) {
      if (el.type === 'radio' || el.type === 'checkbox') el.checked = false;
      else el.value = '';
    });
    clearErrors();
    applyDefaults();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function clearErrors() {
    A.qsa('.field.has-error').forEach(function (f) { f.classList.remove('has-error'); });
    A.qsa('.field .err').forEach(function (e) { e.classList.add('hidden'); e.textContent = ''; });
    A.qs('#form-alert').innerHTML = '';
  }

  function showErrors(fields) {
    clearErrors();
    var first = null;
    Object.entries(fields || {}).forEach(function (entry) {
      var wrap = A.qs('[data-wrap="' + entry[0] + '"]');
      if (!wrap) return;
      wrap.classList.add('has-error');
      var err = wrap.querySelector('.err');
      err.textContent = entry[1];
      err.classList.remove('hidden');
      if (!first) first = wrap;
    });
    A.qs('#form-alert').innerHTML = '<div class="alert error">'
      + 'فرم ثبت نشد. موارد مشخص‌شده را اصلاح کنید:<br>'
      + Object.values(fields || {}).map(A.esc).join(' • ') + '</div>';
    if (first) first.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  /* ── save ───────────────────────────────────────────────────────────── */
  async function save() {
    var button = A.qs('#btn-save');
    button.disabled = true;
    clearErrors();
    try {
      var payload = collect();
      var res = editingId
        ? await A.api.put('/api/records/' + editingId, payload)
        : await A.api.post('/api/records', payload);
      A.toast(res.message || 'ذخیره شد.');
      if (editingId) {
        setTimeout(function () { window.location.href = '/records'; }, 700);
      } else {
        clearForm();
      }
    } catch (err) {
      if (err.fields) showErrors(err.fields);
      else A.qs('#form-alert').innerHTML = '<div class="alert error">'
        + A.esc(err.message) + '</div>';
      A.toast(err.message, 'error');
    } finally {
      button.disabled = false;
    }
  }

  document.addEventListener('DOMContentLoaded', async function () {
    try {
      var res = await A.api.get('/api/form-builder');
      schema = res.data;
      renderForm();
      if (editingId) {
        A.qs('#page-mode').textContent = 'ویرایش رکورد #' + editingId;
        A.qs('#btn-save').textContent = '💾 ذخیره تغییرات';
        A.qs('#btn-cancel').classList.remove('hidden');
        var rec = await A.api.get('/api/records/' + editingId);
        populate(rec.data);
      }
    } catch (err) {
      A.qs('#form-grid').innerHTML = '<div class="alert error">'
        + A.esc(err.message) + '</div>';
      return;
    }
    A.qs('#btn-save').addEventListener('click', save);
    A.qs('#btn-clear').addEventListener('click', async function () {
      if (await A.confirmDialog({ title: 'پاک کردن فرم',
        message: 'تمام مقادیر واردشده پاک می‌شوند. ادامه می‌دهید؟' })) clearForm();
    });
    document.addEventListener('keydown', function (ev) {
      if (ev.ctrlKey && ev.key === 's') { ev.preventDefault(); save(); }
    });
  });
})();
