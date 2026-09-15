/* ==========================================================================
   کارتابل فرایند — the stages this person owes, and the form for each.

   Stages are independent: the workshop can record the motor before the
   engineer has ruled on the fault. What the page must not do is let that pass
   unnoticed, so every stage says which earlier stages have not reported yet.
   ========================================================================== */
(function () {
  'use strict';
  var A = window.App, J = window.Jalali;
  var items = [];
  var current = null;          // { instance, stage_number }
  var form = null;
  var schema = null;           // lookups + conditional rules, loaded once

  /* ── list ───────────────────────────────────────────────────────────── */
  function renderList() {
    var box = A.qs('#inbox-items');
    A.qs('#inbox-count').textContent = J.toFaDigits(items.length);
    if (!items.length) {
      box.innerHTML = '<div class="table-empty">در حال حاضر کاری در کارتابل '
        + 'شما نیست.</div>';
      return;
    }
    var lastRef = null;
    box.innerHTML = items.map(function (it, i) {
      var header = '';
      if (it.id !== lastRef) {
        lastRef = it.id;
        header = '<div class="wf-group">فرایند #' + J.toFaDigits(it.id)
          + (it.well ? ' — ' + A.esc(it.well) : '') + '</div>';
      }
      return header + itemHtml(it, i);
    }).join('');
  }

  function itemHtml(it, i) {
    var waiting = (it.waiting_on || []).length;
    var active = current && current.id === it.id
      && current.stage_number === it.stage_number;
    return '<button class="wf-item' + (active ? ' active' : '')
      + '" data-i="' + i + '" type="button">'
      + '<div class="wf-item-top">'
      + '<span class="wf-stage-no">' + J.toFaDigits(it.stage_number) + '</span>'
      + '<span class="wf-item-title">' + A.esc(it.stage_title) + '</span>'
      + '<span class="badge ' + (it.operation_kind === 'pull' ? 'warn' : '')
      + '">' + A.esc(it.operation_label) + '</span>'
      + '</div>'
      + '<div class="wf-item-sub">'
      + A.esc(it.created_at_j || '')
      + (it.unassigned ? ' · <span class="badge warn">بدون متولی</span>' : '')
      + (waiting ? ' · <span class="badge warn">' + J.toFaDigits(waiting)
          + ' مرحله عقب‌تر ثبت نشده</span>' : '')
      + '</div></button>';
  }

  async function loadInbox() {
    try {
      var res = await A.api.get('/api/workflow/inbox');
      items = res.data || [];
      renderList();
    } catch (err) {
      A.qs('#inbox-items').innerHTML = '<div class="alert error">'
        + A.esc(err.message) + '</div>';
    }
  }

  /* ── one stage ──────────────────────────────────────────────────────── */
  function renderPath(detail) {
    var done = {};
    (detail.entries || []).forEach(function (e) { done[e.stage_number] = e; });
    A.qs('#wf-path').innerHTML = (detail.path || []).map(function (s) {
      var entry = done[s.stage_number] || {};
      var state = entry.status || 'pending';
      var isHere = s.stage_number === current.stage_number;
      return '<div class="wf-step ' + state + (isHere ? ' here' : '') + '">'
        + '<span class="wf-step-no">' + J.toFaDigits(s.stage_number) + '</span>'
        + '<span class="wf-step-title">' + A.esc(s.title) + '</span>'
        + '<span class="wf-step-who">'
        + A.esc(s.assignee_name || 'بدون متولی') + '</span>'
        + '<span class="wf-step-state">'
        + A.esc(entry.status_label || 'در انتظار') + '</span>'
        + '</div>';
    }).join('');
  }

  /* What this stage is for and what to do with it, in the stage's own words —
     the description the admin wrote in the process builder. */
  function renderGuide(detail) {
    var stage = detail.form && detail.form.stage;
    var box = A.qs('#wf-guide');
    if (!stage) { box.innerHTML = ''; return; }
    var required = [];
    (detail.form.sections || []).forEach(function (s) {
      (s.fields || []).forEach(function (f) {
        if (f.is_required && !f.read_only) required.push(f.label);
      });
    });
    box.innerHTML = '<div class="alert info wf-guide">'
      + '<b>مرحله ' + J.toFaDigits(stage.stage_number) + ' — '
      + A.esc(stage.title) + '</b>'
      + (stage.description
          ? '<div class="wf-guide-desc">' + A.esc(stage.description) + '</div>'
          : '')
      + '<div class="wf-guide-todo">فرم زیر را پر کنید و دکمه‌ی '
      + '<b>«ثبت و ارسال مرحله»</b> را بزنید تا فرایند به مرحله‌ی بعد برود.'
      + (required.length
          ? ' فیلدهای الزامی: <b>' + required.map(A.esc).join('، ') + '</b>.'
          : '')
      + '</div></div>';
  }

  function renderWarning(detail) {
    var waiting = detail.waiting_on || [];
    var box = A.qs('#wf-warning');
    if (!waiting.length) { box.innerHTML = ''; return; }
    /* A warning, never a block — the stage owner may well have the numbers in
       hand before the paperwork upstream catches up. */
    box.innerHTML = '<div class="alert warn">⚠ این مرحله‌ها هنوز ثبت نشده‌اند: '
      + waiting.map(function (w) {
          return '<b>مرحله ' + J.toFaDigits(w.stage_number) + ' — '
            + A.esc(w.title) + '</b>'
            + (w.assignee ? ' (' + A.esc(w.assignee) + ')' : '');
        }).join('، ')
      + '.<br>می‌توانید مرحله‌ی خود را همین حالا تکمیل کنید؛ فرایند منتظر '
      + 'ترتیب مرحله‌ها نمی‌ماند.</div>';
  }

  /* Everything earlier stages recorded, shown locked. The stage owner reads
     it, then adds their own part; none of it is theirs to change here. */
  function renderSummary(detail) {
    var box = A.qs('#wf-summary');
    var blocks = detail.summary || [];
    if (!blocks.length) {
      box.innerHTML = '<div class="hint">هنوز مرحله‌ای پیش از این ثبت نشده است.</div>';
      return;
    }
    box.innerHTML = blocks.map(function (b) {
      return '<div class="sum-block ' + A.esc(b.status) + '">'
        + '<div class="sum-head">'
        + '<span class="wf-step-no">' + J.toFaDigits(b.stage_number) + '</span>'
        + '<b>' + A.esc(b.title) + '</b>'
        + '<span class="badge muted">' + A.esc(b.status_label) + '</span>'
        + '<span class="sum-who">' + A.esc(b.user_name || '')
        + (b.submitted_at_j ? ' · ' + A.esc(b.submitted_at_j) : '') + '</span>'
        + '</div>'
        + (b.note ? '<div class="sum-note">' + A.esc(b.note) + '</div>' : '')
        + '<dl class="sum-values">' + b.values.map(function (v) {
            return '<dt>' + A.esc(v.label) + '</dt><dd>' + A.esc(v.value) + '</dd>';
          }).join('') + '</dl>'
        + '</div>';
    }).join('');
  }

  function renderAttachments(detail) {
    var box = A.qs('#wf-attachments');
    var list = detail.attachments || [];
    if (!list.length) { box.innerHTML = '<div class="hint">هنوز مستندی بارگذاری نشده است.</div>'; return; }
    box.innerHTML = '<div class="doc-list">' + list.map(function (a) {
      return '<div class="doc-row">'
        + '<a href="' + A.esc(a.url) + '" class="doc-name">📄 ' + A.esc(a.filename) + '</a>'
        + '<span class="doc-meta">' + A.esc(a.size_label) + ' · '
        + A.esc(a.uploaded_by_name || '') + ' · ' + A.esc(a.uploaded_at_j || '')
        + ' مرحله ' + J.toFaDigits(a.stage_number) + '</span>'
        + '<button class="btn-sm btn-del" data-del-doc="' + a.id + '" type="button">🗑</button>'
        + '</div>';
    }).join('') + '</div>';
  }

  async function openStage(entry) {
    try {
      var res = await A.api.get('/api/workflow/instances/' + entry.id
                                + '?stage=' + entry.stage_number);
      var detail = res.data;
      current = { id: detail.id, stage_number: entry.stage_number, detail: detail };
      A.qs('#wf-detail').classList.remove('hidden');
      A.qs('#wf-title').textContent = 'مرحله ' + J.toFaDigits(entry.stage_number)
        + ' — ' + (detail.form ? detail.form.stage.title : '')
        + (detail.well ? ' · ' + detail.well : '');
      A.qs('#wf-kind').textContent = detail.operation_label;
      renderPath(detail);
      renderGuide(detail);
      renderWarning(detail);
      renderSummary(detail);
      renderAttachments(detail);

      /* Everything the process already knows is filled in, so a stage can see
         and correct what came before rather than typing it again. */
      buildForm(detail.form ? detail.form.sections : [],
                detail.operation_label, detail.payload || {});
      if (detail.well) fillPrevious(detail.well);
      A.qs('#wf-submit').disabled = !detail.may_act;
      A.qs('#wf-submit').title = detail.may_act ? ''
        : 'این مرحله در اختیار شما نیست.';
      renderList();
      A.qs('#wf-detail').scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (err) {
      A.toast(err.message, 'error');
    }
  }

  function buildForm(sections, operationLabel, values) {
    form = window.FormEngine({
      root: A.qs('#wf-form'),
      schema: { sections: sections, lookups: schema.lookups,
                conditional: schema.conditional },
      flat: true,
      /* The operation was settled at step zero and is not on this form, so it
         is handed to the engine as context — otherwise a rule keyed on it
         could not be judged and «علت خرابی» would hide itself. */
      context: { operation_kind: operationLabel },
      onWellPicked: fillPrevious,
      onChange: function (name) {
        if (name === 'required_action' || name === 'pump_type_now') {
          refreshStageForm();
        }
      },
    });
    form.render();
    form.setValues(values || {});
    /* Whichever stage owns «اطلاعات پایه» is the one that dates the operation,
       so it gets today's date to start from — the entry page has always done
       this, and a stage form that did not would send the process on with no
       date and fail at the very last step. */
    var date = A.qs('#fld-op_jdate');
    if (date && !date.value) date.value = J.format.apply(null, J.today());
  }

  /* Stage 4's «اقدام مورد نیاز» decides whether «اطلاعات چاه و نصب» is even
     asked, so the form is re-fetched the moment that answer changes. */
  var refreshStageForm = A.debounce(async function () {
    if (!current) return;
    var answers = form.collect();
    var res;
    try {
      /* Nothing is saved — the server just recomputes the stage with the
         answers in hand, which is how «اطلاعات چاه و نصب» appears or files
         itself away the instant «اقدام مورد نیاز» is picked. */
      res = await A.api.post('/api/workflow/instances/' + current.id + '/form',
                             { stage_number: current.stage_number, data: answers });
    } catch (err) { return; }
    buildForm(res.data.form ? res.data.form.sections : [],
              res.data.operation_label,
              Object.assign({}, current.detail.payload || {}, answers));
  }, 250);

  async function fillPrevious(wellName) {
    if (!wellName) return;
    try {
      var res = await A.api.get('/api/workflow/previous?well='
                                + encodeURIComponent(wellName));
      var data = res.data || {};
      if (!data.values || !Object.keys(data.values).length) return;
      /* Filled in, never locked: the operator can overwrite any of it. */
      form.setValues(data.values, { onlyEmpty: true, flash: true });
      if (data.source) {
        A.toast('مقادیر «قبلی» از عملیات ' + (data.source.date || '')
                + ' پر شد — قابل ویرایش است.', 'info');
      }
    } catch (err) { /* nothing to prefill */ }
  }

  async function submitStage() {
    if (!current) return;
    var button = A.qs('#wf-submit');
    button.disabled = true;
    form.clearErrors();
    try {
      var res = await A.api.post('/api/workflow/instances/' + current.id + '/submit',
        { stage_number: current.stage_number, data: form.collect() });
      A.toast(res.message || 'ثبت شد.', 'success');
      A.qs('#wf-detail').classList.add('hidden');
      current = null;
      await loadInbox();
    } catch (err) {
      if (err.fields) form.showErrors(err.fields);
      A.qs('#inbox-alert').innerHTML = '<div class="alert error">'
        + A.esc(err.message) + '</div>';
      A.toast(err.message, 'error');
    } finally {
      button.disabled = false;
    }
  }

  async function uploadFiles(files) {
    if (!current || !files.length) return;
    for (var i = 0; i < files.length; i++) {
      var body = new FormData();
      body.append('file', files[i]);
      try {
        await A.request('/api/workflow/instances/' + current.id + '/attachments',
                        { method: 'POST', body: body });
      } catch (err) {
        A.toast(files[i].name + ': ' + err.message, 'error');
      }
    }
    var res = await A.api.get('/api/workflow/instances/' + current.id
                              + '?stage=' + current.stage_number);
    renderAttachments(res.data);
    A.toast('مستندات بارگذاری شد.', 'success');
  }

  /* ── new process ────────────────────────────────────────────────────── */
  async function startProcess() {
    var kind = A.qs('input[name="np_kind"]:checked');
    if (!kind) { A.toast('نوع عملیات را انتخاب کنید.', 'error'); return; }
    try {
      var res = await A.api.post('/api/workflow/instances', {
        operation_kind: kind.value,
        well: A.qs('#np-well').value.trim(),
      });
      A.closeModal('new-process-modal');
      A.toast(res.message || 'فرایند آغاز شد.', 'success');
      await loadInbox();
    } catch (err) { A.toast(err.message, 'error'); }
  }

  document.addEventListener('DOMContentLoaded', async function () {
    try {
      schema = (await A.api.get('/api/form-builder')).data;
    } catch (err) {
      A.qs('#inbox-alert').innerHTML = '<div class="alert error">'
        + A.esc(err.message) + '</div>';
      return;
    }
    await loadInbox();

    A.qs('#inbox-items').addEventListener('click', function (ev) {
      var button = ev.target.closest('[data-i]');
      if (button) openStage(items[Number(button.dataset.i)]);
    });
    A.qs('#btn-refresh').addEventListener('click', loadInbox);
    A.qs('#wf-close').addEventListener('click', function () {
      A.qs('#wf-detail').classList.add('hidden');
      current = null;
      renderList();
    });
    A.qs('#wf-submit').addEventListener('click', submitStage);
    A.qs('#wf-file').addEventListener('change', function () {
      uploadFiles(this.files);
      this.value = '';
    });
    A.qs('#wf-attachments').addEventListener('click', async function (ev) {
      var button = ev.target.closest('[data-del-doc]');
      if (!button) return;
      if (!await A.confirmDialog({ title: 'حذف مستند',
        message: 'این مستند حذف شود؟' })) return;
      try {
        await A.api.del('/api/workflow/attachments/' + button.dataset.delDoc);
        var res = await A.api.get('/api/workflow/instances/' + current.id
                                  + '?stage=' + current.stage_number);
        renderAttachments(res.data);
      } catch (err) { A.toast(err.message, 'error'); }
    });
    A.qs('#btn-new-process').addEventListener('click', function () {
      A.openModal('new-process-modal');
    });
    A.qs('#np-start').addEventListener('click', startProcess);
    /* The well picker in the dialog is the same autocomplete the forms use,
       so the process starts against a canonical well from the register. */
    window.FormEngine.attachAutocomplete(A.qs('#np-well'), schema.lookups);
  });
})();
