/* ==========================================================================
   Data-entry page. The form is not hardcoded: it is rendered from the
   form-builder schema by the shared FormEngine, so anything an admin adds or
   hides there shows up here — and in the process کارتابل — without a code
   change.
   ========================================================================== */
(function () {
  'use strict';
  var A = window.App, J = window.Jalali;
  var form = null;
  var schema = null;
  var editingId = window.RECORD_ID || null;

  /* ── «…قبلی» prefill ────────────────────────────────────────────────── */
  /* What the last operation installed is what this one finds. The values are
     filled in and left editable: the register is not always right, and the
     person standing at the well is. */
  async function fillPreviousFrom(wellName) {
    if (editingId || !wellName) return;
    try {
      var res = await A.api.get('/api/workflow/previous?well='
                                + encodeURIComponent(wellName));
      var data = res.data || {};
      if (!data.values || !Object.keys(data.values).length) return;
      form.setValues(data.values, { onlyEmpty: true, flash: true });
      if (data.source) {
        A.toast('مقادیر «قبلی» از عملیات ' + (data.source.date || '')
                + ' خوانده شد — در صورت نیاز ویرایش کنید.', 'info');
      }
    } catch (err) { /* prefill is a convenience, never a blocker */ }
  }

  /* ── save ───────────────────────────────────────────────────────────── */
  async function save() {
    var payload = form.collect();
    form.clearErrors();
    A.qs('#form-alert').innerHTML = '';
    var button = A.qs('#btn-save');
    button.disabled = true;
    try {
      var res = editingId
        ? await A.api.put('/api/records/' + editingId, payload)
        : await A.api.post('/api/records', payload);
      A.toast(res.message || 'ذخیره شد.', 'success');
      if (editingId) {
        setTimeout(function () { window.location.href = '/records'; }, 700);
      } else {
        form.clear();
        applyEntryDefaults();
      }
    } catch (err) {
      if (err.fields) {
        form.showErrors(err.fields);
        A.qs('#form-alert').innerHTML =
          '<div class="alert error">اطلاعات فرم کامل یا معتبر نیست؛ '
          + 'فیلدهای مشخص‌شده را بررسی کنید.</div>';
      } else {
        A.qs('#form-alert').innerHTML =
          '<div class="alert error">' + A.esc(err.message) + '</div>';
      }
    } finally {
      button.disabled = false;
    }
  }

  function applyEntryDefaults() {
    var dateInput = A.qs('#fld-op_jdate');
    if (dateInput && !dateInput.value && !editingId) {
      dateInput.value = J.format.apply(null, J.today());
    }
  }

  function populate(record) {
    form.eachField(function (field) {
      var name = field.field_name;
      var value;
      if (name === 'op_jdate') value = record.date_display;
      else if (name === 'well') value = record.well;
      else if (['failure', 'workshop_opinion', 'desc_tags',
                'install_relates_to'].includes(name)) {
        value = record[name];
      } else if (field.model_attr) {
        var key = field.model_attr.endsWith('_id')
          ? field.model_attr.slice(0, -3) : field.model_attr;
        value = record[key];
        /* Dates are serialised twice: ISO for machines and `_j` in Jalali for
           people. A date input must be handed the Jalali one, or reopening a
           record shows 2024-10-05 where 1403/07/14 was typed. */
        if (field.field_type === 'jalali_date') {
          value = record[key + '_j'] || record[key + '_raw'] || '';
        }
      } else {
        value = (record.dynamic || {})[name];
      }
      form.setFieldValue(field, value);
    });
    if (record.failure_other) {
      var other = A.qs('[data-other="failure"]');
      if (other) other.value = record.failure_other;
    }
    var wellInput = A.qs('#fld-well');
    if (wellInput && wellInput.value) form.showWellBadge(wellInput);
    form.applyConditional();
  }

  /* مهلت ویرایش گذشته: فرم فقط‌خواندنی می‌شود. سرور هم درخواست را رد می‌کند —
     این کار فقط زودتر و روشن‌تر به کاربر می‌گوید چرا نمی‌تواند ذخیره کند. */
  function lockForm(record) {
    var until = record.edit_deadline_j
      ? 'مهلت ویرایش این رکورد تا <b>' + A.esc(record.edit_deadline_j) + '</b>'
        + (record.edit_deadline_time
            ? ' ساعت <b>' + A.esc(record.edit_deadline_time) + '</b>' : '')
        + ' بود و به پایان رسیده است.'
      : 'مهلت ویرایش این رکورد به پایان رسیده است.';
    A.qs('#form-alert').innerHTML = '<div class="alert error">🔒 ' + until
      + '<br>برای تغییر این رکورد با <b>مدیر سیستم</b> هماهنگ کنید.</div>';
    form.lock();
    var save = A.qs('#btn-save');
    save.disabled = true;
    save.title = 'مهلت ویرایش به پایان رسیده است.';
    A.qs('#btn-clear').classList.add('hidden');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  document.addEventListener('DOMContentLoaded', async function () {
    try {
      var res = await A.api.get('/api/form-builder?for=entry');
      schema = res.data;
      form = window.FormEngine({
        root: A.qs('#form-grid'),
        schema: schema,
        onWellPicked: fillPreviousFrom,
      });
      form.render();
      applyEntryDefaults();
      if (editingId) {
        A.qs('#page-mode').textContent = 'ویرایش رکورد #' + editingId;
        A.qs('#btn-save').textContent = '💾 ذخیره تغییرات';
        A.qs('#btn-cancel').classList.remove('hidden');
        var rec = await A.api.get('/api/records/' + editingId);
        populate(rec.data);
        if (rec.data.can_edit === false) lockForm(rec.data);
      }
    } catch (err) {
      A.qs('#form-grid').innerHTML = '<div class="alert error">'
        + A.esc(err.message) + '</div>';
      return;
    }
    A.qs('#btn-save').addEventListener('click', save);
    A.qs('#btn-clear').addEventListener('click', async function () {
      if (await A.confirmDialog({ title: 'پاک کردن فرم',
        message: 'تمام مقادیر واردشده پاک می‌شوند. ادامه می‌دهید؟' })) {
        form.clear();
        applyEntryDefaults();
      }
    });
    document.addEventListener('keydown', function (ev) {
      if (ev.ctrlKey && ev.key === 's') { ev.preventDefault(); save(); }
    });
  });
})();
