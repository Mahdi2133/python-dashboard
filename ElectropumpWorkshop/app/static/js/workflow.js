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
        + ' (' + A.esc(p.operation_label || 'هر دو عملیات') + ')'
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
    var kindSel = A.qs('#wf-proc-kind');
    if (kindSel) kindSel.value = wf.operation_kind || '';
    var note = [];
    if (row.instance_count) {
      note.push('این فرایند ' + J.toFaDigits(row.instance_count)
        + ' بار اجرا شده است، بنابراین حذف نمی‌شود — فقط می‌توان غیرفعالش کرد.');
    }
    if (!wf.is_active) {
      note.push('غیرفعال است: فرایند تازه‌ای روی آن شروع نمی‌شود.');
    }
    fillNote(note.join(' '));
    renderReadiness();
  }

  /* «شروع فرایند در کارتابل نیست»: say which of the things a start needs is
     missing, and fix the ones a click can fix. */
  function renderReadiness() {
    var box = A.qs('#wf-ready');
    var r = definition && definition.readiness;
    if (!box || !r) return;
    var head = r.ready
      ? '<div class="wf-ready-head ok">✅ آماده است: ' + r.starters.map(function (s) {
          return '<b>' + A.esc(s.people.join('، ')) + '</b> در کارتابل خود گزینه‌ی '
            + '«شروع فرایند جدید — ' + A.esc(s.label) + '» را می‌بیند';
        }).join('؛ ') + '.</div>'
      : '<div class="wf-ready-head warn">⚠️ این فرایند هنوز در کارتابل کسی «شروع فرایند» '
        + 'نشان نمی‌دهد. موارد زیر را درست کنید:</div>';
    box.innerHTML = head + '<ul class="wf-ready-list">' + r.checks.map(function (c) {
      var fix = '';
      if (!c.ok && c.key === 'active' && !r.clash) {
        fix = ' <button type="button" class="btn-ghost btn-sm" data-ready="activate">فعال کن</button>';
      } else if (!c.ok && c.key === 'clash' && c.clash.other_is_both
                 && definition.workflow.operation_kind) {
        fix = ' <button type="button" class="btn-ghost btn-sm" data-ready="resolve">«'
          + A.esc(c.clash.name) + '» فقط برای ' + A.esc(otherKindLabel()) + ' باشد و این فعال شود</button>';
      }
      return '<li class="' + (c.ok ? 'ok' : 'bad') + '">' + (c.ok ? '✓ ' : '✗ ')
        + A.esc(c.text) + fix + '</li>';
    }).join('') + '</ul>';
  }

  function otherKindLabel() {
    var k = definition.workflow.operation_kind;
    return k === 'install' ? 'کشیدن' : k === 'pull' ? 'نصب' : '';
  }

  async function activateProcess(resolve) {
    try {
      await A.api.put('/api/workflow/definitions/' + definition.workflow.id,
                      { is_active: true, resolve_clash: !!resolve });
      A.toast('فرایند فعال شد.', 'success');
    } catch (err) {
      if (err.payload && err.payload.clash && definition.workflow.operation_kind) {
        var go = await A.confirmDialog({
          title: 'تداخل با فرایند دیگر',
          message: err.message + ' آیا فرایند دیگر از این به بعد فقط برای «'
            + otherKindLabel() + '» باشد و این فرایند فعال شود؟',
          confirmText: 'بله، همین کار را بکن', danger: false });
        if (go) return activateProcess(true);
      } else {
        A.toast(err.message, 'error');
      }
    }
    await switchProcess(definition.workflow.id);
    await loadProcesses(definition.workflow.id);
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
      if (A.qs('#wf-conn').open) loadConnections();
    } catch (err) { A.toast(err.message, 'error'); }
  }

  async function saveProcess() {
    if (!definition) return;
    try {
      var wantActive = A.qs('#wf-proc-active').checked;
      await A.api.put('/api/workflow/definitions/' + definition.workflow.id, {
        name: A.qs('#wf-proc-name').value.trim(),
        description: A.qs('#wf-proc-desc').value.trim(),
        is_active: wantActive && definition.workflow.is_active,
        operation_kind: (A.qs('#wf-proc-kind') || {}).value || null,
      });
      A.toast('فرایند ذخیره شد.', 'success');
      if (wantActive && !definition.workflow.is_active) {
        definition.workflow.operation_kind = (A.qs('#wf-proc-kind') || {}).value || null;
        return activateProcess(false);
      }
      await switchProcess(definition.workflow.id);
      await loadProcesses(definition.workflow.id);
    } catch (err) { A.toast(err.message, 'error'); }
  }

  /* «فرایند جدید»: empty, or — what the workshop needs — «فرایند نصب» built
     from the current process, which then keeps only کشیدن. */
  var KIND_LABEL = { pull: 'کشیدن', install: 'نصب' };

  function newProcess() {
    var src = A.qs('#np2-source');
    src.innerHTML = processes.map(function (p) {
      return '<option value="' + p.id + '"'
        + (definition && p.id === definition.workflow.id ? ' selected' : '') + '>'
        + A.esc(p.name) + '</option>';
    }).join('');
    procModalSync();
    A.openModal('proc-modal');
  }

  function procModalSync() {
    var kind = A.qs('#np2-kind').value;
    var copy = A.qs('input[name="np2-from"]:checked').value === 'copy';
    A.qs('#np2-copy-opts').classList.toggle('hidden', !copy);
    var other = kind === 'install' ? 'pull' : kind === 'pull' ? 'install' : '';
    A.qs('#np2-narrow').closest('label').classList.toggle('hidden', !other);
    A.qs('#np2-other').textContent = KIND_LABEL[other] || '';
    A.qs('#np2-this').textContent = KIND_LABEL[kind] || '';
  }

  async function createProcess() {
    var name = A.qs('#np2-name').value.trim();
    if (!name) { A.toast('نام فرایند را بنویسید.', 'error'); return; }
    var kind = A.qs('#np2-kind').value || null;
    var copy = A.qs('input[name="np2-from"]:checked').value === 'copy';
    try {
      var res;
      if (copy) {
        var other = kind === 'install' ? 'pull' : kind === 'pull' ? 'install' : null;
        res = await A.api.post('/api/workflow/definitions/'
                               + A.qs('#np2-source').value + '/clone', {
          name: name, operation_kind: kind,
          source_kind: other && A.qs('#np2-narrow').checked ? other : null,
          activate: A.qs('#np2-activate').checked });
      } else {
        res = await A.api.post('/api/workflow/definitions',
                               { name: name, operation_kind: kind });
      }
      A.toast(res.message || 'ساخته شد.', 'success');
      A.closeModal('proc-modal');
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

  async function addStage(asIntake) {
    var title = window.prompt(asIntake ? 'عنوان مرحله شروع:'
                                       : 'عنوان مرحله جدید:',
                              asIntake ? 'شروع فرایند' : '');
    if (!title || !title.trim()) return;
    try {
      await A.api.post('/api/workflow/stages', {
        workflow_id: definition.workflow.id, title: title.trim(),
        as_intake: !!asIntake,
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

  /* Bring a retired stage back into the path. Everything it held — متولی,
     فرم, ارجاع — was left intact when it was retired, so this is one flag. */
  async function restoreStage(card) {
    try {
      var res = await A.api.put('/api/workflow/stages/' + card.dataset.stage,
                                { is_active: true });
      A.toast(res.message || 'مرحله بازگشت.', 'success');
      await switchProcess(definition.workflow.id);
    } catch (err) { A.toast(err.message, 'error'); }
  }

  /* ── who is connected to what ───────────────────────────────────────── */
  async function loadConnections() {
    var box = A.qs('#wf-conn-body');
    if (!box || !definition) return;
    box.innerHTML = '<div class="loading">در حال بارگذاری</div>';
    try {
      var d = (await A.api.get('/api/workflow/connections?workflow_id='
                               + definition.workflow.id)).data;
      box.innerHTML = connectionsHtml(d);
    } catch (err) {
      box.innerHTML = '<div class="alert error">' + A.esc(err.message) + '</div>';
    }
  }

  function connectionsHtml(d) {
    var warn = [];
    var doors = d.doors || [];
    var shut = doors.filter(function (x) { return x.stage_number === null; });
    if (shut.length && !d.has_intake) {
      warn.push('هیچ مرحله‌ای برای شروع عملیات '
        + shut.map(function (x) { return '«' + x.kind_label + '»'; }).join(' و ')
        + ' تعیین نشده است، پس فقط مدیر سیستم می‌تواند آن را شروع کند. روی '
        + 'مرحله‌ی مورد نظر گزینهٔ «فرایند از همین مرحله شروع می‌شود» را '
        + 'بزنید.');
    }
    if (d.unassigned.length) {
      warn.push('بدون متولی: ' + d.unassigned.map(function (u) {
        return 'مرحله ' + J.toFaDigits(u.stage_number) + ' — ' + A.esc(u.title);
      }).join('، '));
    }
    (d.locked_first || []).forEach(function (x) {
      warn.push('«' + x.part + '» در مرحله ' + J.toFaDigits(x.stage_number)
        + ' — ' + x.title + ' روی «فقط نمایش» است، ولی همین اولین مرحله‌ای '
        + 'است که آن را دارد؛ پس هیچ‌کس نمی‌تواند پرش کند و همیشه «—» '
        + 'نشان داده می‌شود. تیک «فقط نمایش» را بردارید.');
    });
    if (d.empty_forms.length) {
      warn.push('بدون فرم (احتمالاً بخشی که حذف شده): '
        + d.empty_forms.map(function (u) {
            return 'مرحله ' + J.toFaDigits(u.stage_number) + ' — '
              + A.esc(u.title); }).join('، '));
    }
    function cards(list, icon) {
      return list.map(function (c) {
        return '<li><span class="conn-stage">' + icon + ' مرحله '
          + J.toFaDigits(c.stage_number) + ' — ' + A.esc(c.title) + '</span>'
          + '<span class="badge muted">' + A.esc(c.applies_to_label) + '</span>'
          + (c.can_start ? '<span class="badge start">🚦 شروع فرایند</span>' : '')
          + (c.shared_with
              ? '<span class="badge muted">مشترک با ' + J.toFaDigits(c.shared_with)
                + ' نفر دیگر</span>' : '')
          + (c.route_by_center
              ? '<span class="badge muted">بر اساس مرکز چاه</span>' : '')
          + (c.powers || []).map(function (p) {
              return '<span class="badge power">⚖ ' + A.esc(p) + '</span>';
            }).join('')
          + '<div class="conn-parts">'
          + (c.parts.length
              ? c.parts.map(function (x) {
                  return '<span class="conn-part' + (x.locked ? ' locked' : '')
                    + '">' + (x.locked ? '🔒 ' : '') + A.esc(x.title)
                    + ' <i>' + J.toFaDigits(x.count) + '</i></span>';
                }).join('')
              : '<span class="conn-part empty">— هیچ فرمی روی این مرحله نیست —</span>')
          + '</div></li>';
      }).join('');
    }
    return (warn.length
        ? '<div class="alert warn">' + warn.map(A.esc).join('<br>') + '</div>'
        : '')
      + '<div class="conn-doors">' + doors.map(function (x) {
          return '<div class="conn-door' + (x.stage_number === null ? ' shut' : '')
            + '"><span class="door-kind">🚦 ' + A.esc(x.kind_label) + '</span>'
            + (x.stage_number === null
                ? '<span class="door-none">مرحله‌ی شروع تعیین نشده</span>'
                : '<span class="door-at">از مرحله ' + J.toFaDigits(x.stage_number)
                  + ' — ' + A.esc(x.title) + '</span>'
                  + '<span class="door-who">' + (x.owners.length
                      ? A.esc(x.owners.join('، '))
                      : 'بدون متولی') + '</span>')
            + '</div>';
        }).join('') + '</div>'
      + '<div class="hint">در این لحظه <b>' + J.toFaDigits(d.running)
      + '</b> فرایند در جریان است. کارتابل هر کاربر تا وقتی فرایندی در جریان '
      + 'نباشد خالی است — این به معنی وصل‌نبودن فرم‌ها نیست.</div>'
      + '<div class="conn-grid">' + d.users.map(function (u) {
          return '<div class="conn-user' + (u.is_active ? '' : ' off') + '">'
            + '<div class="conn-head"><b>' + A.esc(u.full_name) + '</b>'
            + '<span class="hint">' + A.esc(u.username) + ' · '
            + A.esc(u.role_label) + '</span>'
            + '<span class="badge' + (u.open_work ? '' : ' muted') + '">'
            + J.toFaDigits(u.open_work) + ' کار باز</span></div>'
            + '<ul class="conn-list">'
            + cards(u.owns, '📝') + cards(u.approves, '✅')
            + cards(u.referred, '🔀')
            + '</ul></div>';
        }).join('') + '</div>';
  }

  /* ── stages ─────────────────────────────────────────────────────────── */
  function userOptions(selected, placeholder) {
    return '<option value="">' + A.esc(placeholder || '— متولی انتخاب نشده —')
      + '</option>'
      + definition.users.map(function (u) {
          return '<option value="' + u.id + '"'
            + (u.id === selected ? ' selected' : '') + '>'
            + A.esc(u.full_name) + ' (' + A.esc(u.username) + ')</option>';
        }).join('');
  }

  /* A stage's متولی is a list, not a person.

     The city has eight مراکز آبرسانی and each needs its own user, so «اعلام
     علت خرابی» belongs to all eight at once. Each name is a chip that can be
     taken off; the select underneath adds one more. The first name is the
     stage's primary متولی — the one every single-name screen shows. */
  function ownersRow(s) {
    var ids = s.owner_ids && s.owner_ids.length
      ? s.owner_ids
      : (s.assignee_id ? [s.assignee_id] : []);
    var chips = ids.map(function (id, i) {
      var u = userById(id);
      return '<span class="owner-chip" data-owner="' + id + '">'
        + (i === 0 ? '<b title="متولی اصلی">★</b> ' : '')
        + A.esc(u ? u.full_name : '#' + id)
        + '<button type="button" class="owner-off" title="برداشتن">×</button>'
        + '</span>';
    }).join('');
    return '<div class="wf-stage-row wf-owners" data-owners="' + ids.join(',') + '">'
      + '<label>متولی‌ها</label>'
      + '<div class="owner-box">'
      + '<div class="owner-chips">'
      + (chips || '<span class="owner-none">هیچ متولی‌ای تعیین نشده</span>')
      + '</div>'
      + '<select class="owner-add">' + userOptions(null, 'افزودن متولی…')
      + '</select>'
      + '<label class="owner-route"><input type="checkbox" class="wf-by-center"'
      + (s.route_by_center ? ' checked' : '') + '> فقط متولی مرکزِ همان چاه'
      + '</label>'
      + '<span class="hint">با چند متولی، کار در کارتابل همه‌ی آن‌ها می‌آید. '
      + 'گزینهٔ بالا آن را به متولی‌ای می‌دهد که مرکزش با مرکز چاه یکی است '
      + '(مرکز هر کاربر در تب «کاربران» تعیین می‌شود).</span>'
      + '</div></div>';
  }

  /* Where each operation opens. This is «کشیدن از مرکز آبرسانی، نصب از کارگاه
     نصب» said as data: mark the stage, and «شامل» decides which operation it
     opens. Nothing about the start point lives in the code any more. */
  function startRow(s) {
    /* «شامل» says which runs pass through this stage; this says which run
       *starts* here. کارگاه مکانیک is passed through by both, but only a نصب
       opens there — two different questions, so two different settings. */
    var kind = s.start_kind || s.applies_to || 'both';
    return '<div class="wf-stage-start' + (s.can_start ? ' on' : '') + '">'
      + '<label><input type="checkbox" class="wf-can-start"'
      + (s.can_start ? ' checked' : '') + '>'
      + '🚦 فرایند از همین مرحله شروع می‌شود</label>'
      + '<div class="start-kind-row"' + (s.can_start ? '' : ' hidden') + '>'
      + '<span>برای شروع عملیات</span>'
      + '<select class="wf-start-kind">' + appliesOptions(kind) + '</select>'
      + '</div>'
      + '<span class="hint">متولی‌های این مرحله می‌توانند همین عملیات را '
      + 'آغاز کنند و فرایند از همین مرحله شروع می‌شود. اگر چند مرحله در '
      + 'شروع یک عملیات باشند، هر کس از مرحلهٔ خودش شروع می‌کند.</span></div>';
  }

  function userById(id) {
    return (definition.users || []).find(function (u) { return u.id === id; });
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
      + (item.kind === 'section'
          ? '<button class="btn-sm lock-toggle" type="button" title="کدام فیلدهای این فرم '
            + 'در این مرحله قابل ویرایش‌اند و کدام قفل">' + lockLabel(item.locked_fields)
            + '</button>' : '')
      + '<button class="btn-sm btn-del remove" type="button" title="حذف">×</button>'
      + (item.kind === 'section' ? lockPanel(item) : '')
      + '</li>';
  }

  /* Per field, per stage: which of a form's fields this stage fills and which
     it only sees. A locked field shows what an earlier stage recorded — or,
     with «برداشت از سوابق», the well's history — and cannot be changed here;
     the server holds to the same list whatever the browser sends. */
  function sectionFields(code) {
    return ((definition.palette || {}).fields || []).filter(function (f) {
      return f.section === code;
    });
  }

  function lockLabel(locked) {
    var n = (locked || []).length;
    return n ? '🔐 ' + J.toFaDigits(n) + ' فیلد قفل' : '🔐 فیلدها';
  }

  function lockPanel(item) {
    var locked = item.locked_fields || [];
    var fields = sectionFields(item.code);
    return '<div class="wf-lock-panel" hidden data-locked="' + A.esc(locked.join(',')) + '">'
      + '<div class="hint">تیک «قفل» یعنی کاربر این مرحله آن فیلد را می‌بیند ولی نمی‌تواند '
      + 'تغییرش دهد. بقیه‌ی فیلدها را خودش پر می‌کند.</div>'
      + (fields.length ? fields.map(function (f) {
          var on = locked.indexOf(f.code) !== -1;
          return '<label class="lock-row' + (on ? ' on' : '') + '">'
            + '<span>' + A.esc(f.title) + ' <i class="mono">' + A.esc(f.code) + '</i></span>'
            + '<span class="lock-choice"><input type="checkbox" class="lock-field" value="'
            + A.esc(f.code) + '"' + (on ? ' checked' : '') + '> 🔒 قفل</span></label>';
        }).join('') : '<div class="hint">این فرم فیلدی ندارد.</div>')
      + '<div class="lock-actions"><button type="button" class="btn-ghost btn-sm lock-all">'
      + 'قفل همه</button><button type="button" class="btn-ghost btn-sm lock-none">'
      + 'همه قابل ویرایش</button></div></div>';
  }

  function syncLocks(li) {
    var panel = li.querySelector('.wf-lock-panel');
    var names = A.qsa('.lock-field:checked', panel).map(function (b) { return b.value; });
    panel.dataset.locked = names.join(',');
    A.qsa('.lock-row', panel).forEach(function (row) {
      row.classList.toggle('on', row.querySelector('.lock-field').checked);
    });
    li.querySelector('.lock-toggle').textContent = lockLabel(names);
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
      /* One recipient or several — «ارجاع به دفتر فنی و بهره‌بردار» names
         two at once. The same chip list the owners use. */
      + '<div class="wf-stage-row wf-refer-user"'
      + (s.referral_mode === 'next' ? ' hidden' : '') + '>'
      + '<label>کاربر</label>'
      + referPicker(s)
      + '</div>'
      + '<label class="mini-check wf-refer-all-row"'
      + (s.referral_mode === 'next' ? ' hidden' : '') + '>'
      + '<input type="checkbox" class="wf-refer-all"'
      + (s.refer_all ? ' checked' : '') + '>'
      + ' اگر به چند نفر ارجاع شد، <b>همه</b> باید ثبت کنند '
      + '(وگرنه یکی کافی است)</label>'
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
      + '</select></div>'
      /* Two decisions the admin owns, and the whole point of the section:
         whether this approval stops the process, and how much of the record
         the approver is handed to judge it by. */
      + '<label class="mini-check wf-blocks-row' + (s.approval_blocks ? ' on' : '')
      + '"><input type="checkbox" class="wf-approval-blocks"'
      + (s.approval_blocks ? ' checked' : '') + '>'
      + '⛔ تا تأیید نشود، مرحله‌های بعدی ثبت نمی‌شوند</label>'
      + '<div class="wf-stage-row"><label>تأییدکننده چه می‌بیند</label>'
      + '<select class="wf-approval-sees">'
      + (definition.approval_sees || []).map(function (x) {
          return '<option value="' + x.value + '"'
            + (x.value === s.approval_sees ? ' selected' : '') + '>'
            + A.esc(x.label) + '</option>';
        }).join('')
      + '</select></div>'
      + '<span class="hint">اگر «ثبت‌کننده انتخاب می‌کند» باشد، هنگام ارسال '
      + 'برای تأیید، فهرست مرحله‌های ثبت‌شده به ثبت‌کننده نشان داده می‌شود تا '
      + 'تعیین کند تأییدکننده کدام‌ها را ببیند.</span>'
      + '</div>'
      + '</details>';
  }

  /* «اقدام‌های تصمیم‌گیری»: what the person at this stage may decide besides
     sending the work on. امین checking مرکز آبرسانی's report may stop the
     process («نیاز به کشیدن ندارد، قابل اصلاح است») or send it back for a
     photo or a video — and the admin says, per action, who may. */
  /* «اقدام‌ها»: the buttons the person at this stage has besides «ارسال».

     Two are what a reviewer actually needs — stop the whole process (the well
     does not need pulling), or send it back to be corrected — so each is a
     card with one switch, rather than a list to build. More of either kind
     can still be added underneath. For each button the admin says plainly who
     sees it: everyone who holds the stage, or only the people named. */
  var ACTION_DEFAULTS = {
    stop: { label: 'نیاز به ادامه ندارد — توقف فرایند',
            title: '⛔ توقف کل فرایند',
            help: 'فرایند همین‌جا بسته می‌شود و به مرحله‌های بعد نمی‌رود؛ '
              + 'دلیل آن ثبت می‌شود و در رصد فرایندها دیده می‌شود.' },
    'return': { label: 'برگشت به مرحله‌ی قبل برای اصلاح',
                title: '↩ برگشت برای اصلاح یا مستندسازی',
                help: 'کار به کسی که مرحله‌ی قبل را پر کرده برمی‌گردد تا '
                  + 'اصلاح کند (یا عکس و فیلم بارگذاری کند) و دوباره بفرستد.' },
  };

  function actionsEditor(s) {
    var acts = s.actions || [];
    var stop = acts.find(function (a) { return a.kind === 'stop'; });
    var back = acts.find(function (a) { return a.kind === 'return'; });
    var extras = acts.filter(function (a) { return a !== stop && a !== back; });
    var on = (stop ? 1 : 0) + (back ? 1 : 0) + extras.length;
    return '<details class="wf-refer wf-actions" open data-stage-number="'
      + s.stage_number + '">'
      + '<summary>⚖ تصمیم‌های این مرحله'
      + '<span class="wf-refer-tag">' + (on ? J.toFaDigits(on) + ' دکمه‌ی فعال'
                                             : 'فقط «ارسال به مرحله بعد»')
      + '</span></summary>'
      + '<div class="wf-actions-head"><span class="hint">کسی که این مرحله را بررسی '
      + 'می‌کند، همیشه دکمه‌ی <b>«ارسال به مرحله بعد»</b> را دارد. هر کدام از '
      + 'تصمیم‌های زیر را که روشن کنید، به‌عنوان یک دکمه‌ی دیگر در کارتابل او '
      + 'نمایش داده می‌شود.</span></div>'
      + actionRow(stop || { kind: 'stop' }, s, { fixed: true, on: !!stop })
      + actionRow(back || { kind: 'return' }, s, { fixed: true, on: !!back })
      + '<div class="wf-action-list">' + extras.map(function (a) {
          return actionRow(a, s, { on: true });
        }).join('') + '</div>'
      + '<button type="button" class="btn-ghost btn-sm wf-action-add">'
      + '➕ یک دکمه‌ی دیگر (مثلاً برگشت به مرحله‌ای مشخص)</button></details>';
  }

  var actionSeq = 0;

  function actionRow(a, s, opts) {
    opts = opts || {};
    var stages = definition.workflow.stages.filter(function (x) {
      return x.is_active !== false && x.stage_number !== s.stage_number;
    });
    var d = ACTION_DEFAULTS[a.kind] || ACTION_DEFAULTS.stop;
    var isReturn = a.kind === 'return';
    var who = a.user_ids || [];
    var group = 'act-who-' + (++actionSeq);
    var owners = (s.owner_names || []).join('، ') || 'متولی تعیین نشده';
    var head = opts.fixed
      ? '<label class="wf-action-switch"><input type="checkbox" class="act-on"'
        + (opts.on ? ' checked' : '') + '><b>' + d.title + '</b></label>'
        + '<div class="hint">' + d.help + '</div>'
      : '<div class="wf-action-top"><select class="act-kind">'
        + (definition.action_kinds || []).map(function (k) {
            return '<option value="' + k.value + '"'
              + (k.value === a.kind ? ' selected' : '') + '>' + A.esc(k.label)
              + '</option>';
          }).join('') + '</select>'
        + '<button type="button" class="act-del" title="حذف این دکمه">🗑</button></div>';
    return '<div class="wf-action' + (opts.fixed ? ' fixed' : '') + '"'
      + ' data-id="' + A.esc(a.id || (opts.fixed ? (isReturn ? 'back' : 'stop') : ''))
      + '" data-kind="' + a.kind + '" data-users="' + who.join(',') + '">'
      + head
      + '<div class="wf-action-body"' + (opts.on ? '' : ' hidden') + '>'
      + '<div class="act-field"><label>متن دکمه در کارتابل</label>'
      + '<input class="act-label" value="' + A.esc(a.label || d.label) + '"></div>'
      + '<div class="wf-action-return act-field"' + (isReturn ? '' : ' hidden') + '>'
      + '<label>برگشت به</label><select class="act-target">'
      + '<option value="">هر مرحله‌ی قبلی (بررسی‌کننده انتخاب می‌کند)</option>'
      + stages.map(function (x) {
          return '<option value="' + x.stage_number + '"'
            + (x.stage_number === a.target_stage ? ' selected' : '') + '>'
            + 'همیشه مرحله ' + J.toFaDigits(x.stage_number) + ' — ' + A.esc(x.title)
            + '</option>';
        }).join('') + '</select>'
      + '<label class="mini-check"><input type="checkbox" class="act-docs"'
      + (a.needs_docs ? ' checked' : '') + '> تا عکس، فیلم یا فایلی بارگذاری نشود، '
      + 'ثبت دوباره ممکن نیست</label></div>'
      + whenControl(a, s)
      + '<div class="wf-action-who act-field">'
      + '<label>این دکمه برای چه کسانی نمایش داده شود؟</label>'
      + '<label class="who-opt"><input type="radio" class="act-who-mode" name="' + group
      + '" value="all"' + (who.length ? '' : ' checked') + '> همه‌ی متولی‌های این مرحله '
      + '<span class="hint">(' + A.esc(owners) + ')</span></label>'
      + '<label class="who-opt"><input type="radio" class="act-who-mode" name="' + group
      + '" value="some"' + (who.length ? ' checked' : '') + '> فقط این افراد:</label>'
      + '<div class="who-some"' + (who.length ? '' : ' hidden') + '>'
      + '<div class="owner-chips">' + actionWho(who) + '</div>'
      + '<select class="act-who-add">' + userOptions(null, 'افزودن فرد…')
      + '</select></div></div>'
      + '</div></div>';
  }

  /* «این دکمه کِی نمایش داده شود؟» — always, or only while a question on the
     form has a given answer: «نتیجه بررسی = نیاز به کشیدن ندارد». Then the
     decision comes up by itself the moment that answer is picked, and
     «ارسال به مرحله بعد» steps aside. The questions on this stage come first. */
  function whenFields(s) {
    var codes = (s.items || []).map(function (i) { return i.code; });
    var all = definition.choice_fields || [];
    var here = all.filter(function (f) {
      return codes.indexOf(f.section) !== -1 || codes.indexOf(f.name) !== -1;
    });
    return here.concat(all.filter(function (f) { return here.indexOf(f) === -1; }));
  }

  function whenValues(field, picked) {
    if (!field) return '';
    return field.options.map(function (v) {
      return '<label class="mini-check"><input type="checkbox" class="act-when-val" value="'
        + A.esc(v) + '"' + (picked.indexOf(v) !== -1 ? ' checked' : '') + '> '
        + A.esc(v) + '</label>';
    }).join('') || '<span class="hint">این پرسش گزینه‌ای ندارد.</span>';
  }

  function whenControl(a, s) {
    var rule = a.when || '';
    var on = rule.split('=')[0] || '';
    var picked = rule.indexOf('=') !== -1 ? rule.split('=').slice(1).join('=').split('|') : [];
    var fields = whenFields(s);
    var field = fields.find(function (f) { return f.name === on; });
    return '<div class="act-field act-when">'
      + '<label>این دکمه کِی نمایش داده شود؟</label>'
      + '<select class="act-when-on"><option value="">همیشه</option>'
      + fields.map(function (f) {
          return '<option value="' + A.esc(f.name) + '"' + (f.name === on ? ' selected' : '')
            + ' title="' + A.esc(f.section_title || '') + '">فقط وقتی «' + A.esc(f.label)
            + '» این باشد:</option>';
        }).join('') + '</select>'
      + '<div class="act-when-values">' + whenValues(field, picked) + '</div>'
      + '<span class="hint act-when-hint"' + (on ? '' : ' hidden') + '>با انتخاب این پاسخ، '
      + 'این تصمیم خودبه‌خود انتخاب می‌شود و «ارسال به مرحله بعد» کنار می‌رود.</span>'
      + '</div>';
  }

  function actionWho(ids) {
    return ids.length
      ? ids.map(function (id) {
          var u = userById(id);
          return '<span class="owner-chip" data-who="' + id + '">'
            + A.esc(u ? u.full_name : '#' + id)
            + '<button type="button" class="act-who-off">×</button></span>';
        }).join('')
      : '<span class="owner-none">هنوز کسی انتخاب نشده</span>';
  }

  function readActions(card) {
    var out = [];
    A.qsa('.wf-action', card).forEach(function (row) {
      var sw = row.querySelector('.act-on');
      if (sw && !sw.checked) return;               // this decision is switched off
      var kindSel = row.querySelector('.act-kind');
      var mode = row.querySelector('.act-who-mode:checked');
      var ids = (row.dataset.users || '').split(',').filter(Boolean).map(Number);
      if (mode && mode.value === 'some' && !ids.length) {
        throw new Error('برای «' + row.querySelector('.act-label').value.trim()
          + '» گزینه‌ی «فقط این افراد» انتخاب شده ولی کسی اضافه نشده است.');
      }
      var whenOn = row.querySelector('.act-when-on');
      var when = '';
      if (whenOn && whenOn.value) {
        var vals = A.qsa('.act-when-val:checked', row).map(function (b) { return b.value; });
        if (!vals.length) {
          throw new Error('برای «' + row.querySelector('.act-label').value.trim()
            + '» پرسش انتخاب شده ولی هیچ پاسخی تیک نخورده است.');
        }
        when = whenOn.value + '=' + vals.join('|');
      }
      out.push({
        when: when,
        id: row.dataset.id || '',
        kind: kindSel ? kindSel.value : row.dataset.kind,
        label: row.querySelector('.act-label').value.trim(),
        target_stage: row.querySelector('.act-target').value || null,
        needs_docs: row.querySelector('.act-docs').checked,
        user_ids: mode && mode.value === 'all' ? [] : ids,
      });
    });
    return out;
  }

  function referPicker(s) {
    var ids = (s.referral_user_ids && s.referral_user_ids.length)
      ? s.referral_user_ids
      : (s.referral_user_id ? [s.referral_user_id] : []);
    return '<div class="owner-box wf-refer-users" data-ids="' + ids.join(',') + '">'
      + '<div class="owner-chips">' + referChips(ids) + '</div>'
      + '<select class="refer-add">' + userOptions(null, 'افزودن گیرنده…')
      + '</select></div>';
  }

  function referChips(ids) {
    return ids.length
      ? ids.map(function (id) {
          var u = userById(id);
          return '<span class="owner-chip" data-refer="' + id + '">'
            + A.esc(u ? u.full_name : '#' + id)
            + '<button type="button" class="refer-off" title="برداشتن">×</button>'
            + '</span>';
        }).join('')
      : '<span class="owner-none">گیرنده‌ای انتخاب نشده</span>';
  }

  function referIds(card) {
    var box = card.querySelector('.wf-refer-users');
    return box ? (box.dataset.ids || '').split(',').filter(Boolean).map(Number)
               : [];
  }

  function setReferIds(card, ids) {
    var box = card.querySelector('.wf-refer-users');
    if (!box) return;
    box.dataset.ids = ids.join(',');
    box.querySelector('.owner-chips').innerHTML = referChips(ids);
  }

  function referralModeOptions(current) {
    return (definition.referral_modes || []).map(function (m) {
      return '<option value="' + m.value + '"'
        + (m.value === current ? ' selected' : '') + '>' + A.esc(m.label)
        + '</option>';
    }).join('');
  }

  function renderStages() {
    // A retired stage zero is not a stage zero: the server will not start a
    // process through it, so the builder must offer to make a new one.
    var hasIntake = definition.workflow.stages.some(function (s) {
      return s.stage_number === 0 && s.is_active !== false;
    });
    A.qs('#wf-name').textContent = definition.workflow.name
      + (definition.workflow.description
          ? ' — ' + definition.workflow.description : '');
    A.qs('#wf-stages').innerHTML = definition.workflow.stages.map(function (s) {
      var zero = s.stage_number === 0;
      // A stage that already carries recorded entries cannot be deleted
      // outright — the server retires it instead. Say so on the card, or the
      // admin clicks «حذف» and sees nothing change.
      var retired = s.is_active === false;
      return '<div class="wf-stage card' + (s.assignee_id ? '' : ' unassigned')
        + (retired ? ' retired' : '')
        + '" data-stage="' + s.id + '">'
        + (retired ? '<div class="wf-retired-flag">این مرحله بازنشسته شده '
            + 'است: در فرایندهای گذشته رکورد دارد، پس پاک نشد و فقط از '
            + 'مسیر کنار رفت. فرایندهای تازه از آن عبور نمی‌کنند.</div>' : '')
        + '<div class="wf-stage-head">'
        + '<span class="wf-stage-move" title="برای جابه‌جایی بکشید">⠿</span>'
        + '<span class="wf-stage-badge">مرحله ' + J.toFaDigits(s.stage_number) + '</span>'
        + '<input class="wf-stage-title" value="' + A.esc(s.title) + '">'
        + '</div>'
        + ownersRow(s)
        + '<div class="wf-stage-row">'
        + '<label>شامل</label>'
        + '<select class="wf-applies">' + appliesOptions(s.applies_to) + '</select>'
        + '</div>'
        + startRow(s)
        + (s.description ? '<div class="hint wf-stage-desc">'
            + A.esc(s.description) + '</div>' : '')
        + (zero ? '<div class="hint">این مرحله فقط نوع عملیات را می‌پرسد.</div>'
                : referralPanel(s) + actionsEditor(s))
        + '<ul class="wf-drop" data-stage="' + s.id + '">'
        + (s.items.map(itemHtml).join('')
           || '<li class="wf-drop-empty">موردی اینجا نیست — از پالت بکشید</li>')
        + '</ul>'
        + '<div class="wf-stage-foot">'
        + '<button class="btn-primary btn-sm save-stage" type="button">💾 ذخیره مرحله</button>'
        + (retired
            ? '<button class="btn-sm restore-stage" type="button" '
              + 'title="بازگرداندن مرحله">↩ بازگرداندن</button>'
            : '<button class="btn-sm btn-del del-stage" type="button" '
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
      + 'افزودن مرحله</button>'
      + (hasIntake ? ''
          : '<div class="hint warn-text">این فرایند مرحله ۰ ندارد؛ بدون آن '
            + 'فقط مدیر سیستم می‌تواند فرایند را شروع کند.</div>'
            + '<button class="btn-ghost btn-sm" id="wf-add-intake" '
            + 'type="button">افزودن مرحله شروع</button>')
      + '</div>';
    wireDragTargets();
    wireStageDrag();
  }

  /* ── dragging a whole stage, to change the order of the chain ───────── */
  /* The handle is the draggable thing, not the card. Making the card
     draggable would collide with the section-and-field drags that happen
     inside it — the browser would start whichever it liked from the same
     mousedown. Grabbing ⠿ is unambiguous. */
  var movingStage = null;

  function clearDropMarks() {
    A.qsa('.wf-stage').forEach(function (c) {
      c.classList.remove('drop-before', 'drop-after');
    });
  }

  function wireStageDrag() {
    A.qsa('.wf-stage[data-stage]').forEach(function (card) {
      var handle = card.querySelector('.wf-stage-move');
      if (handle) {
        handle.draggable = true;
        handle.addEventListener('dragstart', function (ev) {
          ev.stopPropagation();
          dragging = null;                    // not an item drag
          movingStage = card;
          card.classList.add('moving');
          ev.dataTransfer.effectAllowed = 'move';
          ev.dataTransfer.setData('text/plain', 'stage:' + card.dataset.stage);
        });
        handle.addEventListener('dragend', function () {
          card.classList.remove('moving');
          clearDropMarks();
          if (movingStage) { movingStage = null; saveOrder(); }
        });
      }
      card.addEventListener('dragover', function (ev) {
        if (!movingStage || movingStage === card) return;
        ev.preventDefault();
        ev.stopPropagation();
        var box = card.getBoundingClientRect();
        /* The row reads right to left, so the right half of a card is the
           side a stage lands *before*. */
        var before = ev.clientX > box.left + box.width / 2;
        card.classList.toggle('drop-before', before);
        card.classList.toggle('drop-after', !before);
      });
      card.addEventListener('dragleave', function () {
        card.classList.remove('drop-before', 'drop-after');
      });
      card.addEventListener('drop', function (ev) {
        if (!movingStage || movingStage === card) return;
        ev.preventDefault();
        ev.stopPropagation();
        var before = card.classList.contains('drop-before');
        card.parentNode.insertBefore(movingStage,
                                     before ? card : card.nextSibling);
        clearDropMarks();
      });
    });
  }

  async function saveOrder() {
    var ids = A.qsa('#wf-stages .wf-stage[data-stage]')
      .map(function (c) { return Number(c.dataset.stage); });
    var was = definition.workflow.stages
      .slice().sort(function (a, b) { return a.stage_number - b.stage_number; })
      .map(function (s) { return s.id; });
    if (ids.join() === was.join()) return;        // dropped back where it was
    try {
      var res = await A.api.put('/api/workflow/stages/order',
        { workflow_id: definition.workflow.id, stage_ids: ids });
      A.toast(res.message || 'ترتیب ذخیره شد.', 'success');
      await switchProcess(definition.workflow.id);
    } catch (err) {
      A.toast(err.message, 'error');
      await switchProcess(definition.workflow.id);   // put the cards back
    }
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

  /* The decision switches save themselves. A switch that looks on but is not
     saved until a button far below is pressed reads as «it does not save». */
  function autosaveActions(card) {
    if (!card) return;
    clearTimeout(card._actSave);
    card._actSave = setTimeout(function () { saveStage(card); }, 500);
  }

  function markDirty(stage) {
    if (!stage) return;
    var state = stage.querySelector('.save-state');
    if (state) { state.textContent = '● تغییر ذخیره‌نشده'; state.className = 'save-state dirty'; }
  }

  /* ── saving ─────────────────────────────────────────────────────────── */
  function ownerIds(card) {
    var row = card.querySelector('.wf-owners');
    if (!row) {
      // An older page: one متولی in a plain select.
      var one = card.querySelector('.wf-assignee');
      return one && one.value ? [Number(one.value)] : [];
    }
    return (row.dataset.owners || '').split(',')
      .filter(Boolean).map(Number);
  }

  /* Redraw one stage's chips from its data-owners list, without touching the
     rest of the card — the admin may have half-filled the form below it. */
  function drawOwners(card) {
    var row = card.querySelector('.wf-owners');
    if (!row) return;
    var ids = ownerIds(card);
    row.querySelector('.owner-chips').innerHTML = ids.length
      ? ids.map(function (id, i) {
          var u = userById(id);
          return '<span class="owner-chip" data-owner="' + id + '">'
            + (i === 0 ? '<b title="متولی اصلی">★</b> ' : '')
            + A.esc(u ? u.full_name : '#' + id)
            + '<button type="button" class="owner-off" title="برداشتن">×</button>'
            + '</span>';
        }).join('')
      : '<span class="owner-none">هیچ متولی‌ای تعیین نشده</span>';
    card.classList.toggle('unassigned', !ids.length);
  }

  function addOwner(card, id) {
    var row = card.querySelector('.wf-owners');
    var ids = ownerIds(card);
    if (!id || ids.indexOf(id) !== -1) return;
    ids.push(id);
    row.dataset.owners = ids.join(',');
    drawOwners(card);
  }

  function dropOwner(card, id) {
    var row = card.querySelector('.wf-owners');
    var ids = ownerIds(card).filter(function (x) { return x !== id; });
    row.dataset.owners = ids.join(',');
    drawOwners(card);
  }

  async function saveStage(card) {
    var id = card.dataset.stage;
    var state = card.querySelector('.save-state');
    state.textContent = 'در حال ذخیره…';
    state.className = 'save-state';
    try {
      var body = {
        title: card.querySelector('.wf-stage-title').value.trim(),
        owner_ids: ownerIds(card),
        applies_to: card.querySelector('.wf-applies').value,
      };
      var starts = card.querySelector('.wf-can-start');
      if (starts) body.can_start = starts.checked;
      var startKind = card.querySelector('.wf-start-kind');
      if (startKind) body.start_kind = startKind.value;
      var byCenter = card.querySelector('.wf-by-center');
      if (byCenter) body.route_by_center = byCenter.checked;
      var mode = card.querySelector('.wf-refer-mode');
      if (mode) {
        body.referral_mode = mode.value;
        var recipients = referIds(card);
        body.referral_user_ids = recipients;
        body.referral_user_id = recipients.length ? recipients[0] : null;
        var all = card.querySelector('.wf-refer-all');
        if (all) body.refer_all = all.checked;
        body.referral_hint = card.querySelector('.wf-refer-hint').value.trim();
        body.needs_approval = card.querySelector('.wf-needs-approval').checked;
        body.approver_id = card.querySelector('.wf-approver').value || null;
        body.reject_to_stage = card.querySelector('.wf-reject-to').value || null;
        var blocks = card.querySelector('.wf-approval-blocks');
        if (blocks) body.approval_blocks = blocks.checked;
        var sees = card.querySelector('.wf-approval-sees');
        if (sees) body.approval_sees = sees.value;
      }
      if (card.querySelector('.wf-actions')) body.actions = readActions(card);
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
          locked_fields: ((li.querySelector('.wf-lock-panel') || { dataset: {} })
            .dataset.locked || '').split(',').filter(Boolean),
        };
      });
      await A.api.put('/api/workflow/stages/' + id + '/items', { items: items });
      state.textContent = '✓ ذخیره شد';
      state.className = 'save-state ok';
      if (A.qs('#wf-conn').open) loadConnections();
      card.classList.toggle('unassigned', !ownerIds(card).length);
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
          + (r.workflow_name ? '<span class="badge muted">🔀 ' + A.esc(r.workflow_name)
             + '</span>' : '')
          + (r.well_pm_code ? '<span class="badge muted">کد PM: '
              + A.esc(r.well_pm_code) + '</span>' : '')
          + '<span class="badge muted">آغاز: ' + A.esc(r.created_at_j || '') + '</span>'
          /* Stopped on purpose: the reason is the whole point of the entry. */
          + (r.status === 'stopped' && r.outcome_note
              ? '<span class="badge warn">⛔ ' + A.esc(r.outcome_note) + '</span>'
              : '')
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
    A.qs('#wf-conn').addEventListener('toggle', function () {
      if (this.open) loadConnections();
    });
    A.qs('#wf-proc-save').addEventListener('click', saveProcess);
    A.qs('#wf-proc-new').addEventListener('click', newProcess);
    A.qs('#np2-go').addEventListener('click', createProcess);
    A.qs('#wf-ready').addEventListener('click', function (ev) {
      var b = ev.target.closest('[data-ready]');
      if (b) activateProcess(b.dataset.ready === 'resolve');
    });
    A.qs('#np2-kind').addEventListener('change', procModalSync);
    A.qsa('input[name="np2-from"]').forEach(function (r) {
      r.addEventListener('change', procModalSync);
    });
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
      var back = ev.target.closest('.restore-stage');
      if (back) { restoreStage(back.closest('.wf-stage')); return; }
      var lockBtn = ev.target.closest('.lock-toggle');
      if (lockBtn) {
        var lp = lockBtn.closest('.wf-drop-item').querySelector('.wf-lock-panel');
        lp.hidden = !lp.hidden;
        return;
      }
      var lockAll = ev.target.closest('.lock-all, .lock-none');
      if (lockAll) {
        var li = lockAll.closest('.wf-drop-item');
        A.qsa('.lock-field', li).forEach(function (b) {
          b.checked = lockAll.classList.contains('lock-all');
        });
        syncLocks(li);
        markDirty(li.closest('.wf-stage'));
        return;
      }
      var addAct = ev.target.closest('.wf-action-add');
      if (addAct) {
        var acard = addAct.closest('.wf-stage');
        var stageData = definition.workflow.stages.find(function (x) {
          return String(x.id) === acard.dataset.stage; });
        var holder = document.createElement('div');
        holder.innerHTML = actionRow({ kind: 'return', user_ids: [] }, stageData,
                                     { on: true });
        acard.querySelector('.wf-action-list').appendChild(holder.firstChild);
        markDirty(acard);
        return;
      }
      var delAct = ev.target.closest('.act-del');
      if (delAct) {
        var dcard = delAct.closest('.wf-stage');
        delAct.closest('.wf-action').remove();
        markDirty(dcard);
        autosaveActions(dcard);
        return;
      }
      var whoOff = ev.target.closest('.act-who-off');
      if (whoOff) {
        var arow = whoOff.closest('.wf-action');
        var gone = Number(whoOff.closest('.owner-chip').dataset.who);
        var left = (arow.dataset.users || '').split(',').filter(Boolean)
          .map(Number).filter(function (x) { return x !== gone; });
        arow.dataset.users = left.join(',');
        arow.querySelector('.owner-chips').innerHTML = actionWho(left);
        markDirty(arow.closest('.wf-stage'));
        if (left.length) autosaveActions(arow.closest('.wf-stage'));
        return;
      }
      var roff = ev.target.closest('.refer-off');
      if (roff) {
        var rchip = roff.closest('.owner-chip');
        var rcard = rchip.closest('.wf-stage');
        setReferIds(rcard, referIds(rcard).filter(function (x) {
          return x !== Number(rchip.dataset.refer);
        }));
        markDirty(rcard);
        return;
      }
      var off = ev.target.closest('.owner-off');
      if (off) {
        var chip = off.closest('.owner-chip');
        var host = chip.closest('.wf-stage');
        dropOwner(host, Number(chip.dataset.owner));
        markDirty(host);
        return;
      }
      if (ev.target.closest('#wf-add-stage')) { addStage(); return; }
      if (ev.target.closest('#wf-add-intake')) addStage(true);
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
        var allRow = card.querySelector('.wf-refer-all-row');
        if (allRow) allRow.hidden = mode === 'next';
        card.querySelector('.wf-refer-hint-row').hidden = mode !== 'choose';
        card.querySelector('.wf-refer-user').querySelector('label').textContent =
          mode === 'choose' ? 'پیش‌فرض' : 'کاربر';
      }
      if (ev.target.classList.contains('wf-needs-approval')) {
        card.querySelector('.wf-approve-box').hidden = !ev.target.checked;
      }
      if (ev.target.classList.contains('wf-approval-blocks')) {
        var row = ev.target.closest('.wf-blocks-row');
        if (row) row.classList.toggle('on', ev.target.checked);
      }
      if (ev.target.classList.contains('act-kind')) {
        var krow = ev.target.closest('.wf-action');
        krow.dataset.kind = ev.target.value;
        krow.querySelector('.wf-action-return').hidden = ev.target.value !== 'return';
      }
      if (ev.target.classList.contains('lock-field')) {
        syncLocks(ev.target.closest('.wf-drop-item'));
        return;
      }
      if (ev.target.classList.contains('act-when-on')) {
        var wrow = ev.target.closest('.wf-action');
        var st = definition.workflow.stages.find(function (x) {
          return String(x.id) === card.dataset.stage; });
        var f = whenFields(st || {}).find(function (x) { return x.name === ev.target.value; });
        wrow.querySelector('.act-when-values').innerHTML = whenValues(f, []);
        wrow.querySelector('.act-when-hint').hidden = !ev.target.value;
        return;                        // saved once an answer is ticked
      }
      if (ev.target.closest('.wf-actions')) autosaveActions(card);
      if (ev.target.classList.contains('act-on')) {
        ev.target.closest('.wf-action').querySelector('.wf-action-body').hidden =
          !ev.target.checked;
      }
      if (ev.target.classList.contains('act-who-mode')) {
        ev.target.closest('.wf-action').querySelector('.who-some').hidden =
          ev.target.value !== 'some';
      }
      if (ev.target.classList.contains('act-who-add') && ev.target.value) {
        var wrow = ev.target.closest('.wf-action');
        var cur = (wrow.dataset.users || '').split(',').filter(Boolean).map(Number);
        var add = Number(ev.target.value);
        if (cur.indexOf(add) === -1) cur.push(add);
        wrow.dataset.users = cur.join(',');
        wrow.querySelector('.owner-chips').innerHTML = actionWho(cur);
        ev.target.value = '';
      }
      if (ev.target.classList.contains('refer-add') && ev.target.value) {
        var ids = referIds(card);
        var pick = Number(ev.target.value);
        if (ids.indexOf(pick) === -1) ids.push(pick);
        setReferIds(card, ids);
        ev.target.value = '';
      }
      if (ev.target.classList.contains('owner-add') && ev.target.value) {
        addOwner(card, Number(ev.target.value));
        ev.target.value = '';
      }
      if (ev.target.classList.contains('wf-can-start')) {
        var box = ev.target.closest('.wf-stage-start');
        if (box) {
          box.classList.toggle('on', ev.target.checked);
          var kindRow = box.querySelector('.start-kind-row');
          if (kindRow) kindRow.hidden = !ev.target.checked;
        }
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
