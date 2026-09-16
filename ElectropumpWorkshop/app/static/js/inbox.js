/* ==========================================================================
   کارتابل فرایند — the work this person owes, and the form or decision for each.

   Two kinds of item land here: a phase to fill and an approval to give. Both
   come off the same map, so neither the names nor the order of anything are
   written in this file — the server says what to draw and this page draws it.

   Phases are independent: the workshop can record the motor before the expert
   has ruled on the fault. What the page must not do is let that pass
   unnoticed, so every phase says which earlier ones have not reported yet.
   ========================================================================== */
(function () {
  'use strict';
  var A = window.App, J = window.Jalali;
  var items = [];
  var current = null;          // { id, node_key, task_kind, detail }
  var form = null;
  var startForm = null;        // the FormEngine of the «شروع فرایند» dialog
  var startOptions = [];       // processes this person may open
  var schema = null;           // lookups + conditional rules, loaded once
  var canStart = false;        // may this user open a process at all?
  var routingFields = [];      // answers that change what the form asks next

  /* Where each panel belongs, if the page is missing it. A desktop app is
     updated by copying files, so the template and this script can end up a
     version apart; rather than fail on the difference, the page builds what it
     needs. These panels are context around the stage form — the form itself is
     the point — so a missing one must never stand between the stage owner and
     the fields they came to fill. */
  var PANELS = {
    'wf-path': { cls: 'wf-path' },
    'wf-guide': { cls: '' },
    'wf-prev-note': { cls: '' },
    'wf-warning': { cls: '' },
    'wf-summary': {
      wrap: '<details class="wf-summary-wrap" open>'
            + '<summary>📋 اطلاعات ثبت‌شده در مرحله‌های قبل (فقط مشاهده)</summary>'
            + '<div id="wf-summary"></div></details>',
    },
  };

  function ensurePanel(id) {
    var box = A.qs('#' + id);
    if (box) return box;
    var spec = PANELS[id];
    var anchor = A.qs('#wf-form');
    if (!spec || !anchor || !anchor.parentNode) return null;
    var holder = document.createElement('div');
    holder.innerHTML = spec.wrap
      || '<div id="' + id + '"' + (spec.cls ? ' class="' + spec.cls + '"' : '')
         + '></div>';
    anchor.parentNode.insertBefore(holder.firstChild, anchor);
    return A.qs('#' + id);
  }

  /* Fill a panel, making it first if the template predates it. */
  function fill(selector, html) {
    var box = A.qs(selector);
    if (!box && selector.charAt(0) === '#') box = ensurePanel(selector.slice(1));
    if (box) box.innerHTML = html;
    return box;
  }

  function setText(selector, text) {
    var box = A.qs(selector);
    if (box) box.textContent = text;
    return box;
  }

  /* ── list ───────────────────────────────────────────────────────────── */
  function renderList() {
    var box = A.qs('#inbox-items');
    setText('#inbox-count', J.toFaDigits(items.length));
    if (!box) return;
    if (!items.length && !canStart) {
      box.innerHTML = '<div class="table-empty">در حال حاضر کاری در کارتابل '
        + 'شما نیست.</div>';
      return;
    }
    /* Opening a process is a card in the work list, not a button hanging over
       every page — and only the people the start node names ever see it. */
    var html = canStart
      ? '<div class="wf-group">شروع فرایند</div>'
        + '<button class="wf-item wf-item-start" data-start="1" type="button">'
        + '<div class="wf-item-top">'
        + '<span class="wf-stage-no">🚦</span>'
        + '<span class="wf-item-title">شروع فرایند جدید</span>'
        + '<span class="badge">' + J.toFaDigits(startOptions.length || 1)
        + ' فرایند</span></div>'
        + '<div class="wf-item-sub">فرم شروع را پر کنید تا فرایند آغاز شود.'
        + '</div></button>'
      : '';
    var lastRef = null;
    box.innerHTML = html + items.map(function (it, i) {
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
      && current.node_key === it.node_key;
    var approving = it.task_kind === 'approve';
    return '<button class="wf-item' + (active ? ' active' : '')
      + (approving ? ' wf-item-approve' : '')
      + '" data-i="' + i + '" type="button">'
      + '<div class="wf-item-top">'
      + '<span class="wf-stage-no">' + (approving ? '✅'
          : J.toFaDigits(it.stage_number)) + '</span>'
      + '<span class="wf-item-title">' + A.esc(it.stage_title) + '</span>'
      + '<span class="badge' + (approving ? ' warn' : '') + '">'
      + (approving ? 'تأیید' : A.esc(it.operation_label || 'تکمیل')) + '</span>'
      + '</div>'
      + '<div class="wf-item-sub">'
      + A.esc(it.workflow_name || '') + ' · ' + A.esc(it.created_at_j || '')
      + (it.unassigned ? ' · <span class="badge warn">بدون متولی</span>' : '')
      + (waiting ? ' · <span class="badge warn">' + J.toFaDigits(waiting)
          + ' فاز عقب‌تر ثبت نشده</span>' : '')
      + '</div></button>';
  }

  async function loadInbox() {
    try {
      var res = await A.api.get('/api/workflow/inbox');
      items = res.data || [];
      canStart = !!res.may_start;
      startOptions = res.start_options || [];
      renderList();
    } catch (err) {
      fill('#inbox-items', '<div class="alert error">'
           + A.esc(err.message) + '</div>');
    }
  }

  /* ── one stage ──────────────────────────────────────────────────────── */
  function renderPath(detail) {
    fill('#wf-path', (detail.path || []).map(function (node) {
      var isHere = node.key === current.node_key;
      return '<div class="wf-step ' + A.esc(node.status || 'pending')
        + (isHere ? ' here' : '') + '">'
        + '<span class="wf-step-no">'
        + (node.node_type === 'approval' ? '✅'
           : J.toFaDigits(node.stage_number)) + '</span>'
        + '<span class="wf-step-title">' + A.esc(node.title) + '</span>'
        + '<span class="wf-step-who">'
        + A.esc(node.assignee_name
                || (node.approver_names || []).join('، ')
                || 'بدون متولی') + '</span>'
        + '<span class="wf-step-state">'
        + A.esc(node.status_label || 'در انتظار') + '</span>'
        + '</div>';
    }).join(''));
  }

  /* What this stage is for and what to do with it, in the stage's own words —
     the description the admin wrote in the process builder. */
  function renderGuide(detail) {
    var node = detail.node || (detail.form && detail.form.stage);
    if (!node) { fill('#wf-guide', ''); return; }
    var required = [], routing = [];
    ((detail.form && detail.form.sections) || []).forEach(function (s) {
      (s.fields || []).forEach(function (f) {
        if (f.is_required && !f.read_only) required.push(f.label);
        if (f.affects_routing) routing.push(f.label);
      });
    });
    var approving = node.node_type === 'approval';
    fill('#wf-guide', '<div class="alert info wf-guide">'
      + '<b>' + A.esc(node.icon || '') + ' ' + A.esc(node.title) + '</b>'
      + (node.description
          ? '<div class="wf-guide-desc">' + A.esc(node.description) + '</div>'
          : '')
      + '<div class="wf-guide-todo">'
      + (approving
          ? 'اطلاعات ثبت‌شده را ببینید و سپس <b>تأیید</b> یا <b>رد</b> کنید. '
            + 'برای رد کردن، ذکر دلیل الزامی است.'
          : 'فرم زیر را پر کنید و دکمه‌ی <b>«ثبت و ارسال فاز»</b> را بزنید.'
            + (required.length
                ? ' فیلدهای الزامی: <b>' + required.map(A.esc).join('، ')
                  + '</b>.' : ''))
      + (routing.length
          ? '<br>🔀 پاسخ به <b>' + routing.map(A.esc).join('، ')
            + '</b> مسیر ادامه‌ی فرایند را تعیین می‌کند.' : '')
      + '</div></div>');
  }

  function renderWarning(detail) {
    var waiting = detail.waiting_on || [];
    if (!waiting.length) { fill('#wf-warning', ''); return; }
    /* A warning, never a block — the stage owner may well have the numbers in
       hand before the paperwork upstream catches up. */
    fill('#wf-warning',
      '<div class="alert warn">⚠ این فازها هنوز ثبت نشده‌اند: '
      + waiting.map(function (w) {
          return '<b>' + A.esc(w.title) + '</b>'
            + (w.assignee ? ' (' + A.esc(w.assignee) + ')' : '');
        }).join('، ')
      + '.<br>می‌توانید فاز خود را همین حالا تکمیل کنید؛ فرایند منتظر ترتیب '
      + 'فازها نمی‌ماند.</div>');
  }

  /* Everything earlier stages recorded, shown locked. The stage owner reads
     it, then adds their own part; none of it is theirs to change here. */
  /* Field labels, so a summary built here reads like the form does. */
  function fieldLabels() {
    var labels = {};
    (schema.sections || []).forEach(function (s) {
      (s.fields || []).forEach(function (f) { labels[f.field_name] = f.label; });
    });
    return labels;
  }

  /* The same summary the server sends, rebuilt from the stage entries the
     page already has. The کارتابل must not go blank just because the server
     is a release behind this script — which is exactly what happens when a
     desktop install is updated by copying some files and not others. */
  function summaryFromEntries(detail) {
    var labels = fieldLabels();
    var keep = { submitted: 1, approved: 1 };
    return (detail.entries || []).filter(function (e) {
      return e.task_kind !== 'approve' && e.node_key !== current.node_key
        && keep[e.status];
    }).sort(function (a, b) { return (a.stage_number || 0) - (b.stage_number || 0); })
      .map(function (e) {
        var values = [];
        Object.keys(e.payload || {}).forEach(function (name) {
          var v = e.payload[name];
          if (Array.isArray(v)) v = v.filter(Boolean).join('، ');
          if (v === null || v === undefined || v === '' || v === false) return;
          values.push({ label: labels[name] || name, value: String(v) });
        });
        return {
          stage_number: e.stage_number, node_key: e.node_key,
          title: e.title || '',
          status: e.status, status_label: e.status_label,
          user_name: e.user_name, submitted_at_j: e.submitted_at_j,
          note: e.note, values: values,
        };
      }).filter(function (b) { return b.values.length || b.note; });
  }

  function renderSummary(detail) {
    var blocks = detail.summary || summaryFromEntries(detail);
    if (!blocks.length) {
      fill('#wf-summary',
           '<div class="hint">هنوز فازی پیش از این ثبت نشده است.</div>');
      return;
    }
    fill('#wf-summary', blocks.map(function (b) {
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
    }).join(''));
  }

  function renderAttachments(detail) {
    var list = detail.attachments || [];
    if (!list.length) {
      fill('#wf-attachments',
           '<div class="hint">هنوز مستندی بارگذاری نشده است.</div>');
      return;
    }
    fill('#wf-attachments', '<div class="doc-list">' + list.map(function (a) {
      return '<div class="doc-row">'
        + '<a href="' + A.esc(a.url) + '" class="doc-name">📄 ' + A.esc(a.filename) + '</a>'
        + '<span class="doc-meta">' + A.esc(a.size_label) + ' · '
        + A.esc(a.uploaded_by_name || '') + ' · ' + A.esc(a.uploaded_at_j || '')
        + (a.stage_title ? ' · ' + A.esc(a.stage_title) : '') + '</span>'
        + '<button class="btn-sm btn-del" data-del-doc="' + a.id + '" type="button">🗑</button>'
        + '</div>';
    }).join('') + '</div>');
  }

  async function openStage(entry) {
    try {
      var res = await A.api.get('/api/workflow/instances/' + entry.id
                                + '?node=' + encodeURIComponent(entry.node_key));
      var detail = res.data;
      var node = detail.node || {};
      current = { id: detail.id, node_key: entry.node_key,
                  stage_number: entry.stage_number,
                  task_kind: entry.task_kind || 'fill', detail: detail };
      routingFields = (detail.form && detail.form.routing_fields) || [];
      A.qs('#wf-detail').classList.remove('hidden');
      setText('#wf-title', (node.icon ? node.icon + ' ' : '')
        + (node.title || '') + (detail.well ? ' · ' + detail.well : ''));
      setText('#wf-kind', detail.workflow_name || detail.operation_label || '');

      /* The form first. It is the point of this page, and everything after it
         is context around it — so nothing that decorates the page can end up
         standing between the owner and the fields they came to fill.
         Everything the process already knows is filled in, so a phase can see
         and correct what came before rather than typing it again. */
      buildForm(detail.form ? detail.form.sections : [],
                detail.operation_label, detail.payload || {});
      if (detail.well) fillPrevious(detail.well);
      showApproval(detail, node);

      renderPath(detail);
      renderGuide(detail);
      renderWarning(detail);
      renderSummary(detail);
      renderAttachments(detail);
      renderList();
      A.qs('#wf-detail').scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (err) {
      A.toast(err.message, 'error');
      fill('#inbox-alert', '<div class="alert error">' + A.esc(err.message)
           + '</div>');
    }
  }

  /* An approval node asks for a verdict rather than a form, so the page swaps
     the submit bar for approve/reject — and says how many approvals this node
     needs, because «تأیید یکی کافی است» and «همه باید تأیید کنند» are very
     different things to be told after the fact. */
  function showApproval(detail, node) {
    var approving = node.node_type === 'approval';
    var pane = A.qs('#wf-approval');
    var fillBar = A.qs('#wf-fill-actions');
    if (pane) pane.classList.toggle('hidden', !approving);
    if (fillBar) fillBar.classList.toggle('hidden', approving);
    var submit = A.qs('#wf-submit');
    if (submit) {
      submit.disabled = !detail.may_act;
      submit.title = detail.may_act ? '' : 'این فاز در اختیار شما نیست.';
    }
    if (!approving || !pane) return;
    var given = (node.approvals || []).filter(function (t) {
      return t.status === 'approved';
    }).length;
    var mode = (node.config || {}).approval_mode || 'any';
    var need = mode === 'all' ? (node.approvals || []).length
      : mode === 'quorum' ? ((node.config || {}).approval_quorum || 2) : 1;
    fill('#wf-approval-info',
      'تأییدکنندگان: <b>' + A.esc((node.approver_names || []).join('، ')
        || 'تعیین‌نشده') + '</b> — تاکنون <b>' + J.toFaDigits(given)
      + '</b> از <b>' + J.toFaDigits(need) + '</b> تأیید لازم ثبت شده است.'
      + ((node.approvals || []).filter(function (t) { return t.comment; })
          .map(function (t) {
            return '<br>💬 ' + A.esc(t.user_name || t.assignee_name || '')
              + ': ' + A.esc(t.comment);
          }).join('')));
    ['#wf-approve', '#wf-reject'].forEach(function (sel) {
      var button = A.qs(sel);
      if (button) button.disabled = !detail.may_approve;
    });
  }

  async function decide(approved) {
    if (!current) return;
    var comment = (A.qs('#wf-comment') || {}).value || '';
    if (!approved && !comment.trim()) {
      A.toast('برای رد کردن، ذکر دلیل الزامی است.', 'error');
      A.qs('#wf-comment').focus();
      return;
    }
    try {
      var res = await A.api.post('/api/workflow/instances/' + current.id
                                 + '/decide',
        { node_key: current.node_key, approved: approved, comment: comment });
      A.toast(res.message || 'ثبت شد.', 'success');
      A.qs('#wf-detail').classList.add('hidden');
      A.qs('#wf-comment').value = '';
      current = null;
      await loadInbox();
    } catch (err) {
      A.toast(err.message, 'error');
      fill('#inbox-alert', '<div class="alert error">' + A.esc(err.message)
           + '</div>');
    }
  }

  function buildForm(sections, operationLabel, values) {
    var root = A.qs('#wf-form');
    if (!root) return;
    form = window.FormEngine({
      root: root,
      schema: { sections: sections, lookups: schema.lookups,
                conditional: schema.conditional },
      flat: true,
      /* The operation was settled at step zero and is not on this form, so it
         is handed to the engine as context — otherwise a rule keyed on it
         could not be judged and «علت خرابی» would hide itself. */
      context: { operation_kind: operationLabel },
      onWellPicked: fillPrevious,
      /* Some answers decide where the process goes next, and therefore what
         this very form should still be asking. The server says which ones —
         they are the fields the arrows leaving this node read — so no field
         name is written into this page. */
      onChange: function (name) {
        if (routingFields.indexOf(name) >= 0) refreshStageForm();
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

  /* An answer that decides the route can also decide what else this node
     asks, so the form is re-read the moment such an answer changes. Nothing is
     saved — the server just recomputes the node with the answers in hand. */
  var refreshStageForm = A.debounce(async function () {
    if (!current) return;
    var answers = form.collect();
    var res;
    try {
      res = await A.api.post('/api/workflow/instances/' + current.id + '/form',
                             { node_key: current.node_key, data: answers });
    } catch (err) { return; }
    routingFields = (res.data.form && res.data.form.routing_fields)
      || routingFields;
    buildForm(res.data.form ? res.data.form.sections : [],
              res.data.operation_label,
              Object.assign({}, current.detail.payload || {}, answers));
  }, 250);

  /* The «…قبلی» fields are read off the well's last operation. Whether that
     worked has to be visible: a well with no history looks exactly like a
     broken prefill, and the operator is left wondering which it was. */
  async function fillPrevious(wellName) {
    if (!wellName || !form) return;
    var wanted = [];
    form.eachField(function (f) {
      if (/_prev|prev_|old_install/.test(f.field_name)) wanted.push(f.field_name);
    });
    if (!wanted.length) { fill('#wf-prev-note', ''); return; }
    try {
      var res = await A.api.get('/api/workflow/previous?well='
                                + encodeURIComponent(wellName));
      var data = res.data || {};
      var values = data.values || {};
      var filled = wanted.filter(function (n) {
        return Object.prototype.hasOwnProperty.call(values, n);
      });
      if (!filled.length) {
        fill('#wf-prev-note', '<div class="alert warn">ℹ برای چاه «'
          + A.esc(wellName) + '» عملیات قبلی‌ای در سامانه ثبت نشده است، '
          + 'بنابراین فیلدهای «قبلی» خالی‌اند و باید دستی وارد شوند.</div>');
        return;
      }
      /* Filled in, never locked: the operator can overwrite any of it. */
      form.setValues(values, { onlyEmpty: true, flash: true });
      var src = data.source || {};
      fill('#wf-prev-note', '<div class="alert info">✓ مقادیر «قبلی» از آخرین '
        + 'عملیات این چاه'
        + (src.date ? ' (<b>' + A.esc(src.date) + '</b>'
            + (src.operation ? ' — ' + A.esc(src.operation) : '') + ')' : '')
        + ' پر شد: <b>' + filled.length + ' فیلد</b>. '
        + 'اگر درست نیست، همان‌جا ویرایش کنید.</div>');
    } catch (err) {
      fill('#wf-prev-note', '');
    }
  }

  async function submitStage() {
    if (!current) return;
    var button = A.qs('#wf-submit');
    button.disabled = true;
    form.clearErrors();
    try {
      var res = await A.api.post('/api/workflow/instances/' + current.id + '/submit',
        { node_key: current.node_key, data: form.collect() });
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
        body.append('node_key', current.node_key);
        await A.request('/api/workflow/instances/' + current.id + '/attachments',
                        { method: 'POST', body: body });
      } catch (err) {
        A.toast(files[i].name + ': ' + err.message, 'error');
      }
    }
    var res = await A.api.get('/api/workflow/instances/' + current.id
                              + '?node=' + encodeURIComponent(current.node_key));
    renderAttachments(res.data);
    A.toast('مستندات بارگذاری شد.', 'success');
  }

  /* ── new process ────────────────────────────────────────────────────── */
  /* The dialog is drawn from the start node of the chosen process. This page
     does not know that one process asks for a well and an operation and
     another asks for a number of days — it renders whatever the map says. */
  async function openStartDialog() {
    A.openModal('new-process-modal');
    fill('#np-form', '<div class="loading">در حال بارگذاری</div>');
    var select = A.qs('#np-process');
    await loadStartForm(select && select.value);
  }

  async function loadStartForm(code) {
    try {
      var res = await A.api.get('/api/workflow/start-form'
        + (code ? '?code=' + encodeURIComponent(code) : ''));
      var data = res.data;
      var select = A.qs('#np-process');
      var options = data.options || [];
      A.qs('#np-process-field').classList.toggle('hidden', options.length < 2);
      if (select && select.options.length !== options.length) {
        select.innerHTML = options.map(function (o) {
          return '<option value="' + A.esc(o.code) + '"'
            + (o.code === data.workflow.code ? ' selected' : '') + '>'
            + A.esc(o.name) + '</option>';
        }).join('');
      }
      fill('#np-guide', (data.node && data.node.description
        ? A.esc(data.node.description) : ''));
      startForm = window.FormEngine({
        root: A.qs('#np-form'),
        schema: { sections: data.sections, lookups: schema.lookups,
                  conditional: schema.conditional },
        flat: true,
      });
      startForm.render();
      var date = A.qs('#np-form [id^="fld-"][id$="jdate"]');
      if (date && !date.value) date.value = J.format.apply(null, J.today());
    } catch (err) {
      fill('#np-form', '<div class="alert error">' + A.esc(err.message)
           + '</div>');
      startForm = null;
    }
  }

  async function startProcess() {
    if (!startForm) return;
    startForm.clearErrors();
    var select = A.qs('#np-process');
    try {
      var res = await A.api.post('/api/workflow/instances', {
        workflow_code: select && select.value ? select.value : null,
        data: startForm.collect(),
      });
      A.closeModal('new-process-modal');
      A.toast(res.message || 'فرایند آغاز شد.', 'success');
      await loadInbox();
    } catch (err) {
      if (err.fields) startForm.showErrors(err.fields);
      A.toast(err.message, 'error');
    }
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
      if (ev.target.closest('[data-start]')) { openStartDialog(); return; }
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
                                  + '?node=' + encodeURIComponent(current.node_key));
        renderAttachments(res.data);
      } catch (err) { A.toast(err.message, 'error'); }
    });
    A.qs('#np-start').addEventListener('click', startProcess);
    A.qs('#np-process').addEventListener('change', function () {
      loadStartForm(this.value);
    });
    A.qs('#wf-approve').addEventListener('click', function () { decide(true); });
    A.qs('#wf-reject').addEventListener('click', function () { decide(false); });
  });
})();
