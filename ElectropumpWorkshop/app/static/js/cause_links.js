/* «علت خرابی ← فرم»: which choice opens which form, as a table.

   One row per option of the chosen field (علت خرابی by default). Each row
   holds the forms that option opens — any number of them, and any form may be
   opened by several options. Saving writes the links back onto the forms
   themselves, which is what the stage forms, the entry page and the server's
   required-field check already read; nothing else has to learn about this. */
(function () {
  'use strict';
  var A = window.App, J = window.Jalali;
  var data = null, links = {};          // cause value → [form code]

  function formTitle(code) {
    var f = (data.forms || []).concat(data.others || [], data.field_links || [],
                                      data.field_others || [])
      .find(function (x) { return x.code === code; });
    return f ? (code.indexOf('field:') === 0 ? '◽ ' : '') + f.title : code;
  }

  function render() {
    var box = A.qs('#cl-rows');
    var gap = (data.causes || []).filter(function (c) {
      return !(links[c.value] || []).length;
    }).length;
    A.qs('#cl-gap').innerHTML = gap
      ? '⚠ ' + J.toFaDigits(gap) + ' علت به هیچ فرمی وصل نیست'
      : '✓ همه‌ی علت‌ها فرم دارند';
    A.qs('#cl-gap').className = 'cl-gap ' + (gap ? 'warn' : 'ok');

    var choices = (data.forms || []).map(function (f) {
      return '<option value="' + A.esc(f.code) + '">' + A.esc(f.title)
        + ' (' + J.toFaDigits(f.field_count) + ' فیلد)</option>';
    }).join('');
    var otherChoices = (data.others || []).map(function (f) {
      return '<option value="' + A.esc(f.code) + '" data-plain="'
        + (f.has_rule ? '0' : '1') + '">' + A.esc(f.title)
        + (f.has_rule ? ' · به پرسش دیگری هم وصل است' : '') + '</option>';
    }).join('');
    var fieldChoices = (data.field_links || []).concat(data.field_others || [])
      .map(function (f) {
        return '<option value="' + A.esc(f.code) + '" data-plain="'
          + (f.causes || f.has_rule ? '0' : '1') + '" data-field="1">◽ '
          + A.esc(f.title) + (f.section_title ? ' — ' + A.esc(f.section_title) : '')
          + (f.has_rule && !f.causes ? ' · به پرسش دیگری هم وصل است' : '')
          + '</option>';
      }).join('');

    box.innerHTML = (data.causes || []).map(function (c) {
      var mine = links[c.value] || [];
      return '<div class="cl-row' + (mine.length ? '' : ' empty') + '" data-cause="'
        + A.esc(c.value) + '">'
        + '<div class="cl-cause">' + A.esc(c.label) + '</div>'
        + '<div class="cl-forms">'
        + (mine.length
            ? mine.map(function (code) {
                return '<span class="owner-chip" data-form="' + A.esc(code) + '">'
                  + A.esc(formTitle(code))
                  + '<button type="button" class="cl-off" title="برداشتن">×</button>'
                  + '</span>';
              }).join('')
            : '<span class="owner-none">هیچ فرمی باز نمی‌کند</span>')
        + '</div>'
        + '<select class="cl-add"><option value="">افزودن فرم…</option>'
        + (choices ? '<optgroup label="فرم‌های علت">' + choices + '</optgroup>' : '')
        + (otherChoices ? '<optgroup label="بخش‌های دیگر فرم">' + otherChoices
            + '</optgroup>' : '')
        + (fieldChoices ? '<optgroup label="یک فیلد تکی">' + fieldChoices
            + '</optgroup>' : '')
        + '</select>'
        + '<button type="button" class="btn-ghost btn-sm cl-new" '
        + 'title="یک فرم خالی تازه برای همین علت بسازید">➕ فرم تازه</button>'
        + '</div>';
    }).join('') || '<div class="hint">این فیلد گزینه‌ای ندارد.</div>';
  }

  async function load(fieldName) {
    var res = await A.api.get('/api/form-builder/cause-links?field='
                              + encodeURIComponent(fieldName || 'failure'));
    data = res.data;
    links = {};
    (data.causes || []).forEach(function (c) { links[c.value] = c.forms.slice(); });
    var sel = A.qs('#cl-field');
    sel.innerHTML = (data.sources || []).map(function (s) {
      return '<option value="' + A.esc(s.name) + '"'
        + (s.name === data.field.name ? ' selected' : '') + '>'
        + A.esc(s.label) + (s.section_title ? ' — ' + A.esc(s.section_title) : '')
        + '</option>';
    }).join('');
    render();
  }

  /* Anything created or renamed in the form builder shows up here at once,
     rather than after the whole page is reloaded. */
  window.CauseLinksReload = function () {
    if (!A.qs('#cause-links') || !data) return Promise.resolve();
    if (A.qs('#cl-state').textContent === 'تغییرات ذخیره نشده است') {
      return Promise.resolve();     // do not throw away unsaved links
    }
    return load(data.field.name).catch(function () {});
  };

  /* Links are kept per cause while editing, and turned around into per-form
     lists on save — every form that was or now is involved gets its full list,
     so unlinking the last cause closes the form instead of opening it for all. */
  async function save() {
    var perForm = {};
    (data.forms || []).concat(data.field_links || [])
      .forEach(function (f) { perForm[f.code] = []; });
    Object.keys(links).forEach(function (cause) {
      links[cause].forEach(function (code) {
        (perForm[code] = perForm[code] || []).push(cause);
      });
    });
    var state = A.qs('#cl-state');
    state.textContent = 'در حال ذخیره…';
    try {
      var res = await A.api.put('/api/form-builder/cause-links',
                                { field: data.field.name, links: perForm });
      state.textContent = '✓ ' + (res.message || 'ذخیره شد');
      await load(data.field.name);
    } catch (err) {
      state.textContent = '';
      A.toast(err.message, 'error');
    }
  }

  async function newForm(cause) {
    var label = (data.causes.find(function (c) { return c.value === cause; }) || {})
      .label || cause;
    var code = 'fail_x' + Date.now().toString(36);
    try {
      await A.api.post('/api/form-builder/sections', {
        code: code, title: label + ' — پارامترها', icon: '🧾', columns: 3,
        full_width: true, visible_when: data.field.name + '=' + cause,
      });
      A.toast('فرم «' + label + ' — پارامترها» ساخته شد؛ حالا فیلدهایش را '
              + 'با «فیلد جدید» اضافه کنید.', 'success');
      await load(data.field.name);
      if (window.FormBuilderReload) await window.FormBuilderReload();
    } catch (err) { A.toast(err.message, 'error'); }
  }

  document.addEventListener('DOMContentLoaded', function () {
    if (!A.qs('#cause-links')) return;
    load('failure').catch(function (err) {
      A.qs('#cl-rows').innerHTML = '<div class="alert error">'
        + A.esc(err.message) + '</div>';
    });
    A.qs('#cl-field').addEventListener('change', function () { load(this.value); });
    A.qs('#cl-save').addEventListener('click', save);
    A.qs('#cl-rows').addEventListener('change', async function (ev) {
      if (!ev.target.classList.contains('cl-add') || !ev.target.value) return;
      var row = ev.target.closest('.cl-row');
      var code = ev.target.value;
      var opt = ev.target.selectedOptions[0];
      if (opt && opt.dataset.plain === '1') {
        var go = await A.confirmDialog({
          title: 'وصل کردن یک بخش یا فیلد معمولی',
          message: '«' + formTitle(code) + '» الان برای همه نمایش داده '
            + 'می‌شود. اگر آن را به این علت وصل کنید، از این به بعد فقط با '
            + 'انتخاب این علت (یا علت‌های دیگری که به آن وصل کنید) باز می‌شود. '
            + 'ادامه می‌دهید؟', confirmText: 'وصل کن' });
        if (!go) { ev.target.value = ''; return; }
      }
      if (opt && opt.dataset.field === '1') {
        // a single field linked from now on
        var fmoved = (data.field_others || []).find(function (x) { return x.code === code; });
        if (fmoved) {
          data.field_others = data.field_others.filter(function (x) { return x.code !== code; });
          data.field_links.push(Object.assign({ causes: [] }, fmoved));
        }
      } else if (opt && opt.dataset.plain === '1') {
        // it becomes a cause form from now on
        var moved = data.others.find(function (x) { return x.code === code; });
        data.others = data.others.filter(function (x) { return x.code !== code; });
        data.forms.push(Object.assign({ causes: [] }, moved));
      }
      var list = links[row.dataset.cause] = links[row.dataset.cause] || [];
      if (list.indexOf(code) === -1) list.push(code);
      render();
      A.qs('#cl-state').textContent = 'تغییرات ذخیره نشده است';
    });
    A.qs('#cl-rows').addEventListener('click', function (ev) {
      var off = ev.target.closest('.cl-off');
      if (off) {
        var row = off.closest('.cl-row');
        var code = off.closest('.owner-chip').dataset.form;
        links[row.dataset.cause] = (links[row.dataset.cause] || [])
          .filter(function (c) { return c !== code; });
        render();
        A.qs('#cl-state').textContent = 'تغییرات ذخیره نشده است';
        return;
      }
      var add = ev.target.closest('.cl-new');
      if (add) newForm(add.closest('.cl-row').dataset.cause);
    });
  });
})();
