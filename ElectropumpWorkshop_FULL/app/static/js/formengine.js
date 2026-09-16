/* ==========================================================================
   The form engine shared by the data-entry page and the process کارتابل.

   Both draw the same fields from the same form-builder schema; only the shape
   of what they submit differs. Keeping one renderer means a field type added
   in the form builder appears in both places, and a fix to radio clearing or
   the well autocomplete is a fix in both.

   Every selector is scoped to the engine's own root element, so two engines
   can live on one page without fighting over field ids.
   ========================================================================== */
(function () {
  'use strict';
  var A = window.App, J = window.Jalali;

  /* Keys the record API takes at the top level rather than as dynamic values.
     The flat mode used by the workflow sends everything by field name and lets
     the server sort it out, so this only matters for the entry page. */
  var TAG_FIELDS = ['failure', 'workshop_opinion', 'desc_tags', 'install_relates_to'];

  function FormEngine(options) {
    var root = options.root;
    var schema = options.schema;           // { sections, lookups, conditional }
    var flat = !!options.flat;             // workflow mode: one key per field
    var self = this;

    function qs(sel) { return A.qs(sel, root); }
    function qsa(sel) { return A.qsa(sel, root); }

    /* ── rendering ────────────────────────────────────────────────────── */
    function optionsFor(field) {
      if (field.own_options && field.own_options.length) return field.own_options;
      if (field.lookup_category) return (schema.lookups || {})[field.lookup_category] || [];
      return [];
    }
    self.optionsFor = optionsFor;

    function labelHtml(field) {
      return '<label for="fld-' + A.esc(field.field_name) + '">' + A.esc(field.label)
        + (field.is_required ? ' <span class="req">*</span>' : '') + '</label>';
    }

    function renderChoice(field, multiple) {
      var opts = optionsFor(field);
      var type = multiple ? 'checkbox' : 'radio';
      /* Say what to do with the row of buttons. Without it a long list of
         unselected options reads as a box that has not loaded — which is
         exactly how «علت خرابی» was misread. */
      var html = '<div class="choice-help">'
        + (multiple ? 'روی هر مورد بزنید تا انتخاب شود — <b>چند مورد</b> '
                      + 'قابل انتخاب است.'
                    : 'یکی از گزینه‌ها را انتخاب کنید.')
        + ' برای برداشتن، دوباره روی همان بزنید.'
        + '<span class="choice-count" data-count="' + A.esc(field.field_name)
        + '"></span></div>';
      /* No blank "—" button: an empty choice is not a choice. Clearing is done
         by clicking the selected option again. */
      html += '<div class="btn-group' + (opts.length > 14 ? ' compact' : '')
        + '" data-field="' + A.esc(field.field_name) + '">';
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
      var html = '<select id="fld-' + A.esc(field.field_name) + '" name="'
        + A.esc(field.field_name) + '"><option value="">—</option>';
      optionsFor(field).forEach(function (opt) {
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

      /* Settled upstream: shown and filled so the stage can see it, but not
         editable here — the well is chosen once, at step zero. */
      if (field.read_only) {
        body = '<input type="text" id="fld-' + A.esc(field.field_name) + '"'
          + ' value="' + A.esc(field.read_only_value == null ? ''
                               : String(field.read_only_value)) + '"'
          + ' readonly disabled>';
      }
      var span = field.col_span > 1 ? ' span-' + Math.min(field.col_span, 2) : '';
      /* Long option lists and free text need the whole row; squeezing 20
         buttons into a 180px column is what made the form look ragged. */
      var count = optionsFor(field).length;
      var wide = '';
      if (field.field_type === 'textarea') wide = ' span-full';
      else if (['checkbox', 'multiselect'].includes(field.field_type) && count > 4) {
        wide = ' span-full';
      } else if (field.field_type === 'radio' && count > 7) {
        wide = ' wide-choice';
      }
      return '<div class="field' + span + wide
        + (field.read_only ? ' read-only' : '') + '" data-wrap="'
        + A.esc(field.field_name) + '">'
        + labelHtml(field) + body
        + (field.help_text ? '<span class="hint">' + A.esc(field.help_text) + '</span>' : '')
        + '<span class="err hidden"></span></div>';
    }

    self.render = function () {
      root.innerHTML = (schema.sections || []).map(function (section) {
        if (!section.fields || !section.fields.length) return '';
        return '<div class="form-section' + (section.full_width ? ' full-width' : '')
          + '" data-section="' + A.esc(section.code || '') + '">'
          + '<div class="section-title">'
          + (section.icon ? '<span>' + A.esc(section.icon) + '</span>' : '')
          + '<span>' + A.esc(section.title) + '</span>'
          + (section.is_optional ? '<span class="badge muted">اختیاری</span>' : '')
          + '</div>'
          + '<div class="field-group cols-' + (section.columns || 3) + '">'
          + section.fields.map(renderField).join('')
          + '</div></div>';
      }).join('');

      qsa('.jdate').forEach(function (input) { J.attach(input); });
      qsa('[data-autocomplete]').forEach(setupAutocomplete);
      enableRadioClearing();
      root.addEventListener('change', onFieldChanged);
      root.addEventListener('change', updateChoiceCounts);
      applyDefaults();
      self.applyConditional();
      updateChoiceCounts();
      return self;
    };

    /* «۳ مورد انتخاب شده» beside the help line, so a long list still shows at
       a glance whether anything was picked. */
    function updateChoiceCounts() {
      qsa('[data-count]').forEach(function (badge) {
        var name = badge.dataset.count;
        var n = qsa('input[name="' + name + '"]:checked').length;
        badge.textContent = n ? ' ' + J.toFaDigits(n) + ' مورد انتخاب شده' : '';
        badge.classList.toggle('has', !!n);
      });
    }
    self.updateChoiceCounts = updateChoiceCounts;

    function applyDefaults() {
      if (options.skipDefaults) return;
      (schema.sections || []).forEach(function (section) {
        (section.fields || []).forEach(function (field) {
          if (field.default_value) self.setFieldValue(field, field.default_value);
        });
      });
    }

    /* Clicking the already-selected radio clears it — the only way back to
       "not answered" now that the blank option is gone. */
    function enableRadioClearing() {
      root.addEventListener('mousedown', function (ev) {
        var label = ev.target.closest('.btn-group label');
        if (!label || !root.contains(label)) return;
        var input = label.querySelector('input[type="radio"]');
        if (input && input.checked) {
          setTimeout(function () {
            input.checked = false;
            input.dispatchEvent(new Event('change', { bubbles: true }));
          }, 0);
        }
      });
    }

    /* ── conditional fields ───────────────────────────────────────────── */
    function currentValueOf(name) {
      var picked = qs('input[name="' + name + '"]:checked');
      if (picked) return picked.value;
      var input = qs('#fld-' + name);
      return input ? input.value.trim() : '';
    }
    self.currentValueOf = currentValueOf;

    self.applyConditional = function () {
      (schema.conditional || []).forEach(function (rule) {
        var wrap = qs('[data-wrap="' + rule.field + '"]');
        if (!wrap) return;
        /* A rule can only be judged where its source field is. On a workflow
           stage «علت خرابی» is drawn without «نوع عملیات» beside it, because
           the server already decided the branch and either sent the field or
           did not. Re-deciding it here from a second copy of the answer is how
           the one field a stage exists to collect ended up hidden behind its
           own heading. */
        var source = qs('[data-wrap="' + rule.on + '"]');
        if (!source) return;
        var show = String(currentValueOf(rule.on) || '') === rule.value;
        wrap.classList.toggle('hidden', !show);
        if (!show) {
          qsa('input[name="' + rule.field + '"]').forEach(function (i) {
            i.checked = false;
          });
          var free = qs('#fld-' + rule.field);
          if (free) free.value = '';
          var other = qs('[data-other="' + rule.field + '"]');
          if (other) other.value = '';
        }
      });
      if (options.onConditional) options.onConditional(self);
    };

    function onFieldChanged(ev) {
      var name = ev.target.name || (ev.target.id || '').replace(/^fld-/, '');
      if (!name) return;
      if ((schema.conditional || []).some(function (r) { return r.on === name; })) {
        self.applyConditional();
      }
      if (name === 'well') {
        fillCentreFromWell(ev.target.value);
        if (options.onWellPicked) options.onWellPicked(ev.target.value);
      }
      if (options.onChange) options.onChange(name, self);
    }

    /* Picking a well fills in its centre — the register knows which centre
       each well belongs to, so the operator should not have to remember. */
    async function fillCentreFromWell(name) {
      name = (name || '').trim();
      if (!name) return;
      try {
        var res = await A.api.get('/api/wells?all=1&limit=1&q='
                                  + encodeURIComponent(name));
        var well = (res.data || []).find(function (w) { return w.name === name; });
        if (!well || !well.center_value) return;
        var radio = qs('input[name="center"][value="'
                       + CSS.escape(well.center_value) + '"]');
        if (!radio || radio.checked) return;
        radio.checked = true;
        radio.dispatchEvent(new Event('change', { bubbles: true }));
        flash(qs('[data-wrap="center"]'));
      } catch (err) { /* leave the centre for the operator to pick */ }
    }

    function flash(wrap) {
      if (!wrap) return;
      wrap.classList.add('auto-filled');
      setTimeout(function () { wrap.classList.remove('auto-filled'); }, 1600);
    }
    self.flash = flash;

    /* ── autocomplete ─────────────────────────────────────────────────── */
    function setupAutocomplete(input) {
      var list = input.parentNode.querySelector('.autocomplete-list');
      var source = input.dataset.autocomplete;

      var search = A.debounce(async function () {
        var value = input.value.trim();
        if (value.length < 1) { list.classList.remove('show'); return; }
        var items = [];
        if (source === 'wells' || source === 'well') {
          try {
            var res = await A.api.get('/api/wells?limit=15&q='
                                      + encodeURIComponent(value));
            items = res.data.map(function (w) {
              var tags = [];
              if (w.pm_code) tags.push('کد PM: ' + w.pm_code);
              if (w.well_class) tags.push('کلاسه: ' + w.well_class);
              if (w.center) tags.push(w.center);
              if (!w.is_verified) tags.push('تأییدنشده');
              return { value: w.name, label: w.name, id: w.id,
                       meta: tags.join(' · ') };
            });
          } catch (err) { items = []; }
        } else {
          items = ((schema.lookups || {})[source] || []).filter(function (opt) {
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
        if (source === 'wells' || source === 'well') showWellBadge(input);
      });
      if (source === 'wells' || source === 'well') {
        input.addEventListener('change', function () { showWellBadge(input); });
      }
      document.addEventListener('click', function (ev) {
        if (!input.parentNode.contains(ev.target)) list.classList.remove('show');
      });
    }

    async function showWellBadge(input) {
      var wrap = input.closest('.field');
      if (!wrap) return;
      var badge = wrap.querySelector('.well-badge');
      if (!badge) {
        badge = A.el('div', { class: 'well-badge hint' });
        wrap.appendChild(badge);
      }
      var name = input.value.trim();
      if (!name) { badge.textContent = ''; return; }
      try {
        var res = await A.api.get('/api/wells?all=1&limit=1&q='
                                  + encodeURIComponent(name));
        var w = (res.data || []).find(function (x) { return x.name === name; });
        if (!w) {
          badge.innerHTML = '<span class="badge warn">چاه جدید — با ثبت رکورد افزوده می‌شود</span>';
          return;
        }
        var parts = [];
        if (w.pm_code) parts.push('<span class="badge">کد PM: ' + A.esc(w.pm_code) + '</span>');
        if (w.well_class) parts.push('<span class="badge">کلاسه: ' + A.esc(w.well_class) + '</span>');
        if (w.center) parts.push('<span class="badge muted">' + A.esc(w.center) + '</span>');
        if (!w.pm_code && !w.well_class) {
          parts.push('<span class="badge muted">کد PM ثبت نشده</span>');
        }
        badge.innerHTML = parts.join(' ');
      } catch (err) { badge.textContent = ''; }
    }
    self.showWellBadge = showWellBadge;

    /* ── reading / writing ────────────────────────────────────────────── */
    function checkedValues(name) {
      return qsa('input[name="' + name + '"]:checked')
        .map(function (i) { return i.value; }).filter(Boolean);
    }

    function otherValue(name) {
      var input = qs('[data-other="' + name + '"]');
      return input ? input.value.trim() : '';
    }
    self.otherValue = otherValue;

    function hiddenFields() {
      var hidden = {};
      (schema.conditional || []).forEach(function (rule) {
        var wrap = qs('[data-wrap="' + rule.field + '"]');
        if (wrap && wrap.classList.contains('hidden')) hidden[rule.field] = true;
      });
      return hidden;
    }

    function readField(field) {
      var name = field.field_name;
      if (field.field_type === 'radio') {
        var value = checkedValues(name)[0] || '';
        var other = otherValue(name);
        return other || value;
      }
      if (field.field_type === 'checkbox' || field.field_type === 'multiselect') {
        if (optionsFor(field).length) {
          var values = checkedValues(name);
          var extra = otherValue(name);
          if (extra) {
            values = values.concat(extra.split(',').map(function (v) {
              return v.trim();
            }).filter(Boolean));
          }
          return values;
        }
        var box = qs('#fld-' + name);
        return box ? box.checked : false;
      }
      var input = qs('#fld-' + name);
      return input ? input.value.trim() : '';
    }

    self.eachField = function (fn) {
      (schema.sections || []).forEach(function (section) {
        (section.fields || []).forEach(function (field) { fn(field, section); });
      });
    };

    /* Flat mode (workflow): one key per field name, exactly as the stage was
       drawn. Shaped mode (entry page): the record API's own shape. */
    self.collect = function () {
      var hidden = hiddenFields();
      if (flat) {
        var out = {};
        self.eachField(function (field) {
          if (hidden[field.field_name] || field.read_only) return;
          out[field.field_name] = readField(field);
        });
        var fOther = otherValue('failure');
        if (fOther) out.failure_other = fOther;
        return out;
      }
      var payload = { dynamic: {} };
      self.eachField(function (field) {
        var name = field.field_name;
        if (hidden[name] || field.read_only) return;
        var value = readField(field);
        if (field.model_attr) {
          if (name === 'op_jdate') { payload.op_jdate = value; return; }
          if (name === 'well') { payload.well = value; return; }
          /* Choice columns are sent by *value*, under the short key. */
          var key = field.model_attr.endsWith('_id')
            ? field.model_attr.slice(0, -3) : field.model_attr;
          payload[key] = value;
        } else if (TAG_FIELDS.includes(name)) {
          payload[name] = value;
        } else {
          payload.dynamic[name] = value;
        }
      });
      var failureOther = otherValue('failure');
      if (failureOther) payload.failure_other = failureOther;
      return payload;
    };

    self.setFieldValue = function (field, value) {
      var name = field.field_name;
      if (field.field_type === 'radio') {
        var radio = qs('input[name="' + name + '"][value="'
                       + CSS.escape(String(value == null ? '' : value)) + '"]');
        if (radio) { radio.checked = true; return; }
        var other = qs('[data-other="' + name + '"]');
        if (other && value) other.value = value;
        return;
      }
      if (field.field_type === 'checkbox' || field.field_type === 'multiselect') {
        if (optionsFor(field).length) {
          var wanted = Array.isArray(value) ? value
            : String(value || '').split(',').map(function (v) { return v.trim(); });
          var unmatched = [];
          qsa('input[name="' + name + '"]').forEach(function (box) {
            box.checked = wanted.includes(box.value);
          });
          wanted.filter(Boolean).forEach(function (v) {
            if (!qs('input[name="' + name + '"][value="' + CSS.escape(v) + '"]')) {
              unmatched.push(v);
            }
          });
          var extra = qs('[data-other="' + name + '"]');
          if (extra && unmatched.length) extra.value = unmatched.join('، ');
        } else {
          var box2 = qs('#fld-' + name);
          if (box2) box2.checked = !!value && value !== '0' && value !== 'false';
        }
        return;
      }
      var input = qs('#fld-' + name);
      if (input) input.value = value === null || value === undefined ? '' : value;
    };

    /* Fill from a flat {field_name: value} map, skipping names this form does
       not show. Used for the workflow payload and for the «…قبلی» suggestions. */
    self.setValues = function (values, opts) {
      opts = opts || {};
      self.eachField(function (field) {
        var name = field.field_name;
        if (!Object.prototype.hasOwnProperty.call(values, name)) return;
        if (opts.onlyEmpty && String(readField(field) || '').length) return;
        self.setFieldValue(field, values[name]);
        if (opts.flash) flash(qs('[data-wrap="' + name + '"]'));
      });
      self.applyConditional();
      updateChoiceCounts();
    };

    self.clearErrors = function () {
      qsa('.field.has-error').forEach(function (f) { f.classList.remove('has-error'); });
      qsa('.field .err').forEach(function (e) {
        e.classList.add('hidden'); e.textContent = '';
      });
    };

    self.showErrors = function (fields) {
      self.clearErrors();
      var first = null;
      Object.keys(fields || {}).forEach(function (name) {
        var wrap = qs('[data-wrap="' + name + '"]');
        if (!wrap) return;
        wrap.classList.add('has-error');
        var err = wrap.querySelector('.err');
        if (err) { err.textContent = fields[name]; err.classList.remove('hidden'); }
        if (!first) first = wrap;
      });
      if (first) first.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return first;
    };

    self.clear = function () {
      qsa('input, textarea, select').forEach(function (el) {
        if (el.type === 'radio' || el.type === 'checkbox') el.checked = false;
        else el.value = '';
      });
      self.clearErrors();
      applyDefaults();
      self.applyConditional();
      updateChoiceCounts();
    };

    self.lock = function () {
      qsa('input, textarea, select').forEach(function (el) { el.disabled = true; });
    };

    self.attachAutocompleteTo = setupAutocomplete;
    self.qs = qs;
    self.qsa = qsa;
  }

  window.FormEngine = function (options) { return new FormEngine(options); };

  /* A single input outside any form that still wants the well picker — the
     «شروع فرایند» dialog, for one. */
  window.FormEngine.attachAutocomplete = function (input, lookups) {
    var engine = new FormEngine({
      root: input.closest('.autocomplete-wrapper') || input.parentNode,
      schema: { sections: [], lookups: lookups || {} },
    });
    engine.attachAutocompleteTo(input);
    return engine;
  };
})();
