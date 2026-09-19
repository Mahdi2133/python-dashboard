/* ==========================================================================
   فرایندساز — who fills which part of the form, and the map of every process
   in flight.

   The designer is a drag surface: sections and single fields are dragged from
   the palette onto a stage. A stage's contents are saved whole rather than as
   add/remove calls, because the order the admin sees has to be the order that
   is stored.
   ========================================================================== */
(function () {
  'use strict';
  var A = window.App, J = window.Jalali;
  var definition = null;      // { workflow, palette, users, applies_to }
  var processes = [];         // every defined process, for the selector
  var dragging = null;        // { kind, id, title, from }

  /* ── palette ────────────────────────────────────────────────────────── */
  function renderPalette() {
    var term = (A.qs('#pal-search').value || '').trim();
    function match(x) { return !term || x.title.indexOf(term) >= 0
      || (x.code || '').indexOf(term) >= 0; }

    A.qs('#pal-sections').innerHTML = definition.palette.sections
      .filter(match).map(function (s) {
        return '<div class="pal-item" draggable="true" data-kind="section" '
          + 'data-id="' + s.id + '" data-title="' + A.esc(s.title) + '">'
          + (s.icon ? A.esc(s.icon) + ' ' : '📦 ') + A.esc(s.title)
          + '<span class="pal-meta">' + J.toFaDigits(s.field_count) + ' فیلد</span>'
          + '</div>';
      }).join('') || '<div class="hint">موردی یافت نشد.</div>';

    A.qs('#pal-fields').innerHTML = definition.palette.fields
      .filter(match).map(function (f) {
        return '<div class="pal-item small" draggable="true" data-kind="field" '
          + 'data-id="' + f.id + '" data-title="' + A.esc(f.title) + '">'
          + '◽ ' + A.esc(f.title)
          + '<span class="pal-meta">' + A.esc(f.section_title || '') + '</span>'
          + '</div>';
      }).join('') || '<div class="hint">موردی یافت نشد.</div>';
  }

  /* ── the process itself ─────────────────────────────────────────────── */
  async function loadProcesses(selectId) {
    try {
      processes = (await A.api.get('/api/workflow/definitions')).data || [];
    } catch (err) { processes = []; }
    var select = A.qs('#wf-process');
    if (!select) return;
    var current = selectId || (definition && definition.workflow.id);
    select.innerHTML = processes.map(function (p) {
      return '<option value="' + p.id + '"'
        + (p.id === current ? ' selected' : '') + '>' + A.esc(p.name)
        + (p.is_active ? ' — فعال' : '') + '</option>';
    }).join('') || '<option value="">— فرایندی تعریف نشده —</option>';
    renderProcessBox();
  }

  function renderProcessBox() {
    var wf = definition && definition.workflow;
    if (!wf) return;
    var row = processes.filter(function (p) { return p.id === wf.id; })[0] || {};
    A.qs('#wf-proc-name').value = wf.name || '';
    A.qs('#wf-proc-desc').value = wf.description || '';
    A.qs('#wf-proc-active').checked = !!wf.is_active;
    var note = [];
    if (row.instance_count) {
      note.push('این فرایند ' + J.toFaDigits(row.instance_count)
        + ' بار اجرا شده است، بنابراین حذف نمی‌شود — فقط می‌توان غیرفعالش کرد.');
    }
    if (!wf.is_active) {
      note.push('غیرفعال است: فرایند تازه‌ای روی آن شروع نمی‌شود.');
    }
    fillNote(note.join(' '));
  }

  function fillNote(text) {
    var box = A.qs('#wf-proc-note');
    if (box) box.textContent = text || '';
  }

  async function switchProcess(id) {
    try {
      definition = (await A.api.get('/api/workflow/definition?workflow_id='
                                    + id)).data;
      renderPalette();
      renderStages();
      renderProcessBox();
    } catch (err) { A.toast(err.message, 'error'); }
  }

  async function saveProcess() {
    if (!definition) return;
    try {
      await A.api.put('/api/workflow/definitions/' + definition.workflow.id, {
        name: A.qs('#wf-proc-name').value.trim(),
        description: A.qs('#wf-proc-desc').value.trim(),
        is_active: A.qs('#wf-proc-active').checked,
      });
      A.toast('فرایند ذخیره شد.', 'success');
      await switchProcess(definition.workflow.id);
      await loadProcesses(definition.workflow.id);
    } catch (err) { A.toast(err.message, 'error'); }
  }

  async function newProcess() {
    var name = window.prompt('نام فرایند جدید:');
    if (!name || !name.trim()) return;
    try {
      var res = await A.api.post('/api/workflow/definitions',
                                 { name: name.trim() });
      A.toast(res.message || 'ساخته شد.', 'success');
      await switchProcess(res.data.id);
      await loadProcesses(res.data.id);
    } catch (err) { A.toast(err.message, 'error'); }
  }

  async function deleteProcess() {
    if (!definition) return;
    var okToGo = await A.confirmDialog({
      title: 'حذف فرایند',
      message: 'فرایند «' + definition.workflow.name + '» با همه‌ی مرحله‌هایش '
        + 'حذف شود؟ اگر اجرایی داشته باشد، حذف نمی‌شود.',
    });
    if (!okToGo) return;
    try {
      var res = await A.api.del('/api/workflow/definitions/'
                                + definition.workflow.id);
      A.toast(res.message || 'حذف شد.', 'success');
      definition = (await A.api.get('/api/workflow/definition')).data;
      renderPalette(); renderStages();
      await loadProcesses();
    } catch (err) { A.toast(err.message, 'error'); }
  }

  async function addStage() {
    var title = window.prompt('عنوان مرحله جدید:');
    if (!title || !title.trim()) return;
    try {
      await A.api.post('/api/workflow/stages', {
        workflow_id: definition.workflow.id, title: title.trim(),
      });
      A.toast('مرحله اضافه شد. حالا متولی و فرمش را مشخص کنید.', 'success');
      await switchProcess(definition.workflow.id);
      await loadProcesses(definition.workflow.id);
    } catch (err) { A.toast(err.message, 'error'); }
  }

  async function removeStage(card) {
    var title = card.querySelector('.wf-stage-title').value;
    var okToGo = await A.confirmDialog({
      title: 'حذف مرحله',
      message: 'مرحله «' + title + '» حذف شود؟',
    });
    if (!okToGo) return;
    try {
      var res = await A.api.del('/api/workflow/stages/' + card.dataset.stage);
      A.toast(res.message || 'حذف شد.', 'success');
      await switchProcess(definition.workflow.id);
    } catch (err) { A.toast(err.message, 'error'); }
  }

  /* ── stages ─────────────────────────────────────────────────────────── */
  function userOptions(selected) {
    return '<option value="">— متولی انتخاب نشده —</option>'
      + definition.users.map(function (u) {
          return '<option value="' + u.id + '"'
            + (u.id === selected ? ' selected' : '') + '>'
            + A.esc(u.full_name) + ' (' + A.esc(u.username) + ')</option>';
        }).join('');
  }

  function appliesOptions(selected) {
    return definition.applies_to.map(function (a) {
      return '<option value="' + a.value + '"'
        + (a.value === selected ? ' selected' : '') + '>'
        + A.esc(a.label) + '</option>';
    }).join('');
  }

  function itemHtml(item) {
    return '<li class="wf-drop-item" draggable="true" data-item-kind="'
      + A.esc(item.kind) + '" data-item-id="' + (item.section_id || item.field_id)
      + '" data-applies="' + A.esc(item.applies_to) + '"'
      + ' data-optional="' + (item.is_optional ? '1' : '') + '"'
      + ' data-readonly="' + (item.is_read_only ? '1' : '') + '">'
      + '<span class="grip">⠿</span>'
      + '<span class="wf-item-name">'
      + (item.kind === 'section' ? '📦 ' : '◽ ') + A.esc(item.title || item.code)
      + '</span>'
      + '<select class="mini applies">' + appliesOptions(item.applies_to) + '</select>'
      + '<label class="mini-check" title="اختیاری — نبودنش مانع ثبت مرحله نمی‌شود">'
      + '<input type="checkbox" class="optional"' + (item.is_optional ? ' checked' : '')
      + '> اختیاری</label>'
      + '<label class="mini-check" title="قفل — آنچه مرحله‌ی قبل پر کرده نشان '
      + 'داده می‌شود ولی اینجا قابل تغییر نیست">'
      + '<input type="checkbox" class="readonly"' + (item.is_read_only ? ' checked' : '')
      + '> 🔒 فقط نمایش</label>'
      + '<button class="btn-sm btn-del remove" type="button" title="حذف">×</button>'
      + '</li>';
  }

  /* Where a stage's work goes when it is finished, and who signs it off.
     The workshop's process is a chain of handovers — «ارجاع به کارگاه مکانیک»,
     «برگشت به کارتابل بهره‌بردار» — so this is the part the admin spends most
     of their time in, and it is spelled out rather than hidden in a dialog. */
  function referralPanel(s) {
    var stages = definition.workflow.stages.filter(function (x) {
      return x.stage_number > 0;
    });
    return '<details class="wf-refer"' + (s.needs_approval
        || s.referral_mode !== 'next' ? ' open' : '') + '>'
      + '<summary>🔀 ارجاع و تأیید'
      + '<span class="wf-refer-tag">' + A.esc(s.referral_mode_label || '')
      + (s.needs_approval ? ' · تأیید لازم' : '') + '</span></summary>'
      + '<div class="wf-stage-row">'
      + '<label>ارجاع به</label>'
      + '<select class="wf-refer-mode">' + referralModeOptions(s.referral_mode)
      + '</select></div>'
      + '<div class="wf-stage-row wf-refer-user"'
      + (s.referral_mode === 'next' ? ' hidden' : '') + '>'
      + '<label>کاربر</label>'
      + '<select class="wf-refer-user-id">' + userOptions(s.referral_user_id)
      + '</select></div>'
      + '<div class="wf-stage-row wf-refer-hint-row"'
      + (s.referral_mode === 'choose' ? '' : ' hidden') + '>'
      + '<label>راهنما</label>'
      + '<input class="wf-refer-hint" value="' + A.esc(s.referral_hint || '')
      + '" placeholder="مثلاً: به کارتابل چه کسی ارجاع می‌دهید؟"></div>'
      + '<label class="mini-check wf-approve-toggle">'
      + '<input type="checkbox" class="wf-needs-approval"'
      + (s.needs_approval ? ' checked' : '')
      + '> این مرحله باید تأیید شود</label>'
      + '<div class="wf-approve-box"' + (s.needs_approval ? '' : ' hidden') + '>'
      + '<div class="wf-stage-row"><label>تأییدکننده</label>'
      + '<select class="wf-approver">' + userOptions(s.approver_id)
      + '</select></div>'
      + '<div class="wf-stage-row"><label>در صورت رد</label>'
      + '<select class="wf-reject-to">'
      + '<option value="">برگشت به همین مرحله</option>'
      + stages.map(function (x) {
          return '<option value="' + x.stage_number + '"'
            + (s.reject_to_stage === x.stage_number ? ' selected' : '') + '>'
            + 'مرحله ' + J.toFaDigits(x.stage_number) + ' — ' + A.esc(x.title)
            + '</option>';
        }).join('')
      + '</select></div></div>'
      + '</details>';
  }

  function referralModeOptions(current) {
    return (definition.referral_modes || []).map(function (m) {
      return '<option value="' + m.value + '"'
        + (m.value === current ? ' selected' : '') + '>' + A.esc(m.label)
        + '</option>';
    }).join('');
  }

  function renderStages() {
    A.qs('#wf-name').textContent = definition.workflow.name
      + (definition.workflow.description
          ? ' — ' + definition.workflow.description : '');
    A.qs('#wf-stages').innerHTML = definition.workflow.stages.map(function (s) {
      var zero = s.stage_number === 0;
      return '<div class="wf-stage card' + (s.assignee_id ? '' : ' unassigned')
        + '" data-stage="' + s.id + '">'
        + '<div class="wf-stage-head">'
        + '<span class="wf-stage-badge">مرحله ' + J.toFaDigits(s.stage_number) + '</span>'
        + '<input class="wf-stage-title" value="' + A.esc(s.title) + '">'
        + '</div>'
        + '<div class="wf-stage-row">'
        + '<label>متولی</label>'
        + '<select class="wf-assignee">' + userOptions(s.assignee_id) + '</select>'
        + '</div>'
        + '<div class="wf-stage-row">'
        + '<label>شامل</label>'
        + '<select class="wf-applies">' + appliesOptions(s.applies_to) + '</select>'
        + '</div>'
        + (s.description ? '<div class="hint wf-stage-desc">'
            + A.esc(s.description) + '</div>' : '')
        + (zero ? '<div class="hint">این مرحله فقط نوع عملیات را می‌پرسد.</div>'
                : referralPanel(s))
        + '<ul class="wf-drop" data-stage="' + s.id + '">'
        + (s.items.map(itemHtml).join('')
           || '<li class="wf-drop-empty">موردی اینجا نیست — از پالت بکشید</li>')
        + '</ul>'
        + '<div class="wf-stage-foot">'
        + '<button class="btn-primary btn-sm save-stage" type="button">💾 ذخیره مرحله</button>'
        + (zero ? '' : '<button class="btn-sm btn-del del-stage" type="button" '
            + 'title="حذف مرحله">🗑</button>')
        + '<span class="save-state"></span>'
        + '</div>'
        + '</div>';
    }).join('')
      + '<div class="wf-stage card wf-add-stage">'
      + '<h4>➕ مرحله تازه</h4>'
      + '<div class="hint">یک مرحله به این فرایند اضافه کنید، سپس متولی، '
      + 'فرم و ارجاعش را مشخص کنید.</div>'
      + '<button class="btn-ghost btn-sm" id="wf-add-stage" type="button">'
      + 'افزودن مرحله</button></div>';
    wireDragTargets();
  }

  /* ── drag and drop ──────────────────────────────────────────────────── */
  function wireDragTargets() {
    A.qsa('.wf-drop').forEach(function (list) {
      list.addEventListener('dragover', function (ev) {
        ev.preventDefault();
        list.classList.add('over');
      });
      list.addEventListener('dragleave', function () { list.classList.remove('over'); });
      list.addEventListener('drop', function (ev) {
        ev.preventDefault();
        list.classList.remove('over');
        if (!dragging) return;
        if (dragging.from === list) {
          /* Reordering inside one stage: drop it where it was let go. */
          var after = itemAfter(list, ev.clientY);
          if (after) list.insertBefore(dragging.node, after);
          else list.appendChild(dragging.node);
        } else {
          var empty = list.querySelector('.wf-drop-empty');
          if (empty) empty.remove();
          if (dragging.node && dragging.from) dragging.node.remove();
          list.insertAdjacentHTML('beforeend', itemHtml({
            kind: dragging.kind,
            section_id: dragging.kind === 'section' ? dragging.id : null,
            field_id: dragging.kind === 'field' ? dragging.id : null,
            title: dragging.title, applies_to: dragging.applies || 'both',
            is_optional: !!dragging.optional,
            is_read_only: !!dragging.readonly,
          }));
        }
        markDirty(list.closest('.wf-stage'));
      });
    });
  }

  function itemAfter(list, y) {
    return A.qsa('.wf-drop-item', list).find(function (el) {
      var box = el.getBoundingClientRect();
      return y < box.top + box.height / 2;
    });
  }

  function markDirty(stage) {
    if (!stage) return;
    var state = stage.querySelector('.save-state');
    if (state) { state.textContent = '● تغییر ذخیره‌نشده'; state.className = 'save-state dirty'; }
  }

  /* ── saving ─────────────────────────────────────────────────────────── */
  async function saveStage(card) {
    var id = card.dataset.stage;
    var state = card.querySelector('.save-state');
    state.textContent = 'در حال ذخیره…';
    state.className = 'save-state';
    try {
      var body = {
        title: card.querySelector('.wf-stage-title').value.trim(),
        assignee_id: card.querySelector('.wf-assignee').value || null,
        applies_to: card.querySelector('.wf-applies').value,
      };
      var mode = card.querySelector('.wf-refer-mode');
      if (mode) {
        body.referral_mode = mode.value;
        body.referral_user_id = card.querySelector('.wf-refer-user-id').value || null;
        body.referral_hint = card.querySelector('.wf-refer-hint').value.trim();
        body.needs_approval = card.querySelector('.wf-needs-approval').checked;
        body.approver_id = card.querySelector('.wf-approver').value || null;
        body.reject_to_stage = card.querySelector('.wf-reject-to').value || null;
      }
      await A.api.put('/api/workflow/stages/' + id, body);
      /* Read each control if it is there, fall back to what the row was
         drawn with if it is not. A desktop install is updated by copying
         files, so the script and the page it is running against can end up a
         version apart — and when they do, saving a stage must not die on a
         checkbox that template does not have yet. */
      function flag(li, css, attr) {
        var box = li.querySelector(css);
        return box ? box.checked : li.dataset[attr] === '1';
      }
      var items = A.qsa('.wf-drop-item', card).map(function (li) {
        var applies = li.querySelector('.applies');
        return {
          kind: li.dataset.itemKind,
          id: Number(li.dataset.itemId),
          applies_to: applies ? applies.value : (li.dataset.applies || 'both'),
          is_optional: flag(li, '.optional', 'optional'),
          is_read_only: flag(li, '.readonly', 'readonly'),
        };
      });
      await A.api.put('/api/workflow/stages/' + id + '/items', { items: items });
      state.textContent = '✓ ذخیره شد';
      state.className = 'save-state ok';
      card.classList.toggle('unassigned',
                            !card.querySelector('.wf-assignee').value);
    } catch (err) {
      state.textContent = '✗ ' + err.message;
      state.className = 'save-state err';
      A.toast(err.message, 'error');
    }
  }

  /* ── monitor ────────────────────────────────────────────────────────── */
  async function loadMonitor() {
    var params = [];
    if (A.qs('#mon-status').value) params.push('status=' + A.qs('#mon-status').value);
    if (A.qs('#mon-kind').value) params.push('kind=' + A.qs('#mon-kind').value);
    try {
      var res = await A.api.get('/api/workflow/instances?' + params.join('&'));
      var rows = res.data || [];
      if (!rows.length) {
        A.qs('#mon-list').innerHTML = '<div class="table-empty">فرایندی یافت نشد.</div>';
        return;
      }
      A.qs('#mon-list').innerHTML = rows.map(function (r) {
        var steps = (r.entries || []).filter(function (e) {
          return e.stage_number > 0;
        }).map(function (e) {
          return '<div class="wf-step ' + e.status + '">'
            + '<span class="wf-step-no">' + J.toFaDigits(e.stage_number) + '</span>'
            + '<span class="wf-step-title">' + A.esc(e.title || '') + '</span>'
            + '<span class="wf-step-who">'
            + A.esc(e.user_name || e.assignee_name || 'بدون متولی') + '</span>'
            + '<span class="wf-step-state">' + A.esc(e.status_label) + '</span>'
            + (e.submitted_at_j ? '<span class="wf-step-when">'
                + A.esc(e.submitted_at_j) + '</span>' : '')
            + '</div>';
        }).join('');
        return '<div class="card mon-card">'
          + '<div class="card-head">'
          + '<span>🔀 فرایند #' + J.toFaDigits(r.id) + ' — '
          + A.esc(r.well || 'چاه نامشخص') + '</span>'
          + '<span class="badge ' + (r.status === 'completed' ? 'ok' : 'warn') + '">'
          + A.esc(r.status_label) + '</span></div>'
          + '<div class="mon-meta">'
          + '<span class="badge">' + A.esc(r.operation_label) + '</span>'
          + (r.well_pm_code ? '<span class="badge muted">کد PM: '
              + A.esc(r.well_pm_code) + '</span>' : '')
          + '<span class="badge muted">آغاز: ' + A.esc(r.created_at_j || '') + '</span>'
          + (r.record_id ? '<a class="badge ok" href="/records">رکورد #'
              + J.toFaDigits(r.record_id) + ' ثبت شد</a>'
              : '<span class="badge warn">هنوز رکورد نشده</span>')
          + (r.attachment_count ? '<span class="badge muted">📎 '
              + J.toFaDigits(r.attachment_count) + '</span>' : '')
          + '</div>'
          + '<div class="wf-path">' + steps + '</div>'
          + (r.status === 'open'
              ? '<div class="mon-foot"><button class="btn-sm btn-del cancel-wf" '
                + 'data-id="' + r.id + '" type="button">لغو فرایند</button></div>'
              : '')
          + '</div>';
      }).join('');
    } catch (err) {
      A.qs('#mon-list').innerHTML = '<div class="alert error">'
        + A.esc(err.message) + '</div>';
    }
  }

  function showPane(which) {
    A.qs('#pane-design').classList.toggle('hidden', which !== 'design');
    A.qs('#pane-monitor').classList.toggle('hidden', which !== 'monitor');
    A.qs('#tab-design').classList.toggle('active', which === 'design');
    A.qs('#tab-monitor').classList.toggle('active', which === 'monitor');
    if (which === 'monitor') loadMonitor();
  }

  document.addEventListener('DOMContentLoaded', async function () {
    try {
      definition = (await A.api.get('/api/workflow/definition')).data;
    } catch (err) {
      A.qs('#wf-alert').innerHTML = '<div class="alert error">'
        + A.esc(err.message) + '</div>';
      return;
    }
    renderPalette();
    renderStages();
    loadProcesses();

    A.qs('#pal-search').addEventListener('input', renderPalette);
    A.qs('#wf-process').addEventListener('change', function () {
      if (this.value) switchProcess(Number(this.value));
    });
    A.qs('#wf-proc-save').addEventListener('click', saveProcess);
    A.qs('#wf-proc-new').addEventListener('click', newProcess);
    A.qs('#wf-proc-del').addEventListener('click', deleteProcess);

    /* One delegated listener each, so redrawing the stages never leaves a
       stale handler behind. */
    document.addEventListener('dragstart', function (ev) {
      var pal = ev.target.closest('.pal-item');
      if (pal) {
        dragging = { kind: pal.dataset.kind, id: Number(pal.dataset.id),
                     title: pal.dataset.title, from: null, node: null };
        return;
      }
      var item = ev.target.closest('.wf-drop-item');
      if (item) {
        dragging = { kind: item.dataset.itemKind, id: Number(item.dataset.itemId),
                     title: item.querySelector('.wf-item-name').textContent.trim(),
                     applies: item.querySelector('.applies').value,
                     optional: item.querySelector('.optional').checked,
                     readonly: item.querySelector('.readonly').checked,
                     from: item.parentNode, node: item };
        item.classList.add('dragging');
      }
    });
    document.addEventListener('dragend', function () {
      A.qsa('.wf-drop-item.dragging').forEach(function (el) {
        el.classList.remove('dragging');
      });
      dragging = null;
    });

    A.qs('#wf-stages').addEventListener('click', function (ev) {
      var remove = ev.target.closest('.remove');
      if (remove) {
        var li = remove.closest('.wf-drop-item');
        var list = li.parentNode;
        li.remove();
        if (!list.querySelector('.wf-drop-item')) {
          list.innerHTML = '<li class="wf-drop-empty">موردی اینجا نیست — '
            + 'از پالت بکشید</li>';
        }
        markDirty(list.closest('.wf-stage'));
        return;
      }
      var save = ev.target.closest('.save-stage');
      if (save) { saveStage(save.closest('.wf-stage')); return; }
      var drop = ev.target.closest('.del-stage');
      if (drop) { removeStage(drop.closest('.wf-stage')); return; }
      if (ev.target.closest('#wf-add-stage')) addStage();
    });
    A.qs('#wf-stages').addEventListener('change', function (ev) {
      var card = ev.target.closest('.wf-stage');
      markDirty(card);
      if (!card) return;
      /* Only show what the chosen kind of referral actually needs: a fixed
         user needs a name, a submitter's choice needs a prompt, and the
         default needs neither. */
      if (ev.target.classList.contains('wf-refer-mode')) {
        var mode = ev.target.value;
        card.querySelector('.wf-refer-user').hidden = mode === 'next';
        card.querySelector('.wf-refer-hint-row').hidden = mode !== 'choose';
        card.querySelector('.wf-refer-user').querySelector('label').textContent =
          mode === 'choose' ? 'پیش‌فرض' : 'کاربر';
      }
      if (ev.target.classList.contains('wf-needs-approval')) {
        card.querySelector('.wf-approve-box').hidden = !ev.target.checked;
      }
    });

    A.qs('#tab-design').addEventListener('click', function () { showPane('design'); });
    A.qs('#tab-monitor').addEventListener('click', function () { showPane('monitor'); });
    A.qs('#mon-refresh').addEventListener('click', loadMonitor);
    A.qs('#mon-status').addEventListener('change', loadMonitor);
    A.qs('#mon-kind').addEventListener('change', loadMonitor);
    A.qs('#mon-list').addEventListener('click', async function (ev) {
      var button = ev.target.closest('.cancel-wf');
      if (!button) return;
      var reason = await A.confirmDialog({ title: 'لغو فرایند',
        message: 'این فرایند لغو شود؟ رکوردی ثبت نخواهد شد.' });
      if (!reason) return;
      try {
        await A.api.post('/api/workflow/instances/' + button.dataset.id + '/cancel',
                         { reason: 'لغو توسط مدیر' });
        loadMonitor();
      } catch (err) { A.toast(err.message, 'error'); }
    });
    showPane('design');
  });
})();
