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
    // reports that read this stage (its timing or its data) would break
    var used = [];
    try {
      used = (await A.api.get('/api/analytics/dependencies?kind=stage&ref=' + card.dataset.stage)).data || [];
    } catch (err) { used = []; }
    var okToGo = await A.confirmDialog({
      title: 'حذف مرحله',
      message: 'مرحله «' + title + '» حذف شود؟'
        + (used.length ? ' — توجه: ' + used.length + ' گزارش از این مرحله استفاده می‌کند ('
          + used.map(function (r) { return '«' + r.name + '»'; }).join('، ')
          + ') و پس از حذف، آن بخش‌ها خطا خواهند داد.' : ''),
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
      + '<label class="owner-route"><input type="checkbox" class="wf-show-ref"'
      + (s.show_refdata !== false ? ' checked' : '') + '> نمایش «اطلاعات چاه از بانک‌های اطلاعاتی» '
      + '(دبی‌سنجی، روند تولید، ویدئومتری) در کارتابل این مرحله'
      + '</label>'
      + '<span class="hint">با چند متولی، فرایندی که یکی از آن‌ها شروع کند فقط در کارتابل '
      + '<b>همان شروع‌کننده</b> می‌آید و بقیه آن را نمی‌بینند؛ فرایندی که کس دیگری (مثلاً مدیر) '
      + 'شروع کند، به همه‌ی آن‌ها می‌رسد. گزینهٔ بالا کار را به متولی‌ای می‌دهد که مرکزش با '
      + 'مرکز چاه یکی است (مرکز هر کاربر در تب «کاربران» تعیین می‌شود).</span>'
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
          ? '<select class="mini item-approver" title="ارجاع این فرم: با ثبت مرحله برای اطلاع این شخص فرستاده می‌شود">'
            + '<option value="">📝 ارجاع: —</option>'
            + definition.users.map(function (u) {
                return '<option value="' + u.id + '"' + (u.id === item.approval_user_id ? ' selected' : '') + '>📝 '
                  + A.esc(u.full_name) + '</option>';
              }).join('') + '</select>'
            + '<label class="mini-check" title="تیک‌خورده: مرحله تا تأیید این شخص ثبت نمی‌شود">'
            + '<input type="checkbox" class="item-approval-req"' + (item.approval_required ? ' checked' : '')
            + '> الزامی</label>' : '')
      + (item.kind === 'section'
          ? '<button class="btn-sm lock-toggle" type="button" title="کدام فیلدهای این فرم '
            + 'در این مرحله قابل ویرایش‌اند و کدام قفل">' + lockLabel(item.locked_fields, item.hidden_fields)
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

  function lockLabel(locked, hidden) {
    var n = (locked || []).length, h = (hidden || []).length;
    if (!n && !h) return '🔐 فیلدها';
    return (n ? '🔐 ' + J.toFaDigits(n) + ' قفل' : '') + (n && h ? ' · ' : '')
      + (h ? '🙈 ' + J.toFaDigits(h) + ' پنهان' : '');
  }

  function lockPanel(item) {
    var locked = item.locked_fields || [];
    var hidden = item.hidden_fields || [];
    var fields = sectionFields(item.code);
    return '<div class="wf-lock-panel" hidden data-locked="' + A.esc(locked.join(',')) + '"'
      + ' data-hidden="' + A.esc(hidden.join(',')) + '">'
      + '<div class="hint">تیک «قفل» یعنی کاربر این مرحله آن فیلد را می‌بیند ولی نمی‌تواند '
      + 'تغییرش دهد؛ «پنهان» یعنی آن فیلد در این مرحله اصلاً نشان داده نمی‌شود (در فرم و '
      + 'مرحله‌های دیگر می‌ماند). بقیه‌ی فیلدها را خودش پر می‌کند.</div>'
      + (fields.length ? fields.map(function (f) {
          var on = locked.indexOf(f.code) !== -1, off = hidden.indexOf(f.code) !== -1;
          return '<label class="lock-row' + (on ? ' on' : '') + (off ? ' off' : '') + '">'
            + '<span>' + A.esc(f.title) + ' <i class="mono">' + A.esc(f.code) + '</i></span>'
            + '<span class="lock-choice"><input type="checkbox" class="lock-field" value="'
            + A.esc(f.code) + '"' + (on ? ' checked' : '') + '> 🔒 قفل</span>'
            + '<span class="lock-choice"><input type="checkbox" class="hide-field" value="'
            + A.esc(f.code) + '"' + (off ? ' checked' : '') + '> 🙈 پنهان</span></label>';
        }).join('') : '<div class="hint">این فرم فیلدی ندارد.</div>')
      + '<div class="lock-actions"><button type="button" class="btn-ghost btn-sm lock-all">'
      + 'قفل همه</button><button type="button" class="btn-ghost btn-sm lock-none">'
      + 'همه قابل ویرایش</button></div></div>';
  }

  function syncLocks(li) {
    var panel = li.querySelector('.wf-lock-panel');
    var names = A.qsa('.lock-field:checked', panel).map(function (b) { return b.value; });
    var hides = A.qsa('.hide-field:checked', panel).map(function (b) { return b.value; });
    names = names.filter(function (n) { return hides.indexOf(n) === -1; });
    panel.dataset.locked = names.join(',');
    panel.dataset.hidden = hides.join(',');
    A.qsa('.lock-row', panel).forEach(function (row) {
      var off = row.querySelector('.hide-field').checked;
      if (off) row.querySelector('.lock-field').checked = false;
      row.classList.toggle('on', row.querySelector('.lock-field').checked);
      row.classList.toggle('off', off);
    });
    li.querySelector('.lock-toggle').textContent = lockLabel(names, hides);
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
      + '<div class="hint wf-refer-user-hint"' + (s.referral_mode === 'next' ? ' hidden' : '') + '>'
      + 'کاربرِ «ارجاع به» <b>مرحله‌ی بعد را پر می‌کند</b>. برای کسی که فقط باید تأیید کند، '
      + '«این مرحله باید تأیید شود» یا «ارجاع برای تأیید» را به کار ببرید؛ تأییدکننده‌ها '
      + 'هیچ‌وقت فرم مرحله‌ی بعد را دریافت نمی‌کنند و آن مرحله به متولی خودش می‌رود.</div>'
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
      /* «ارجاع برای تأیید»: the person here sends chosen forms, a note and
         documents to someone; the answer comes back to them and they go on. */
      + '<label class="mini-check wf-areq-toggle">'
      + '<input type="checkbox" class="wf-areq-enabled"' + (s.approval_request_enabled ? ' checked' : '')
      + '> 📝 امکان «ارجاع برای تأیید» (ضمیمه‌ی فرم‌های پرشده، توضیحات و مستندات؛ پاسخ به همین مرحله برمی‌گردد)</label>'
      + '<div class="wf-areq-box"' + (s.approval_request_enabled ? '' : ' hidden') + '>'
      + '<div class="wf-stage-row"><label>تأییدکننده‌های مجاز</label>'
      + '<select class="wf-areq-users" multiple size="4">'
      + definition.users.map(function (u) {
          return '<option value="' + u.id + '"'
            + ((s.approval_request_user_ids || []).indexOf(u.id) >= 0 ? ' selected' : '') + '>'
            + A.esc(u.full_name) + '</option>';
        }).join('')
      + '</select></div>'
      + '<span class="hint">هیچ‌کدام انتخاب نشود یعنی همه‌ی کاربران فعال. برای «تأیید اجباری» یک فرم مشخص، '
      + 'روی همان فرم در این مرحله «✅ تأیید» را تنظیم کنید.</span>'
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

  /* «ارجاعات برای تأیید»: every answer asked on this stage that needs
     somebody's approval before the stage can be sent on — which answers,
     whose approval, and what the approver picks. The rules live on the fields
     (the form builder edits the same thing); here the admin sees a stage's
     referrals in one place and changes them where the process is drawn. */
  function approvalRulesPanel(s) {
    return '<details class="wf-refer wf-rules" data-stage-id="' + s.id + '">'
      + '<summary>📝 ارجاعات (اطلاع‌رسانی / تأیید پاسخ‌ها)'
      + '<span class="wf-refer-tag wf-rules-tag">برای دیدن باز کنید</span></summary>'
      + '<div class="wf-rules-body"><div class="loading">در حال بارگذاری</div></div></details>';
  }

  function ruleRowHtml(field, rule, answerFields) {
    rule = rule || { options: [], approvers: [], answer_field: null };
    return '<div class="wf-rule">'
      + '<div class="wf-rule-opts">' + field.options.map(function (o) {
          var on = rule.options.indexOf(o) !== -1;
          return '<label class="mini-check' + (on ? ' on' : '') + '"><input type="checkbox" class="r-opt" value="'
            + A.esc(o) + '"' + (on ? ' checked' : '') + '> ' + A.esc(o) + '</label>';
        }).join('') + '</div>'
      + '<div class="wf-rule-row"><label>تأییدکننده‌ها</label><select class="r-who" multiple size="3">'
      + definition.users.map(function (u) {
          return '<option value="' + u.id + '"' + (rule.approvers.indexOf(u.id) !== -1 ? ' selected' : '') + '>'
            + A.esc(u.full_name) + '</option>';
        }).join('') + '</select></div>'
      + '<div class="wf-rule-who hint">' + whoText(rule.approvers) + '</div>'
      + '<label class="mini-check' + (rule.required ? ' on' : '') + '" title="بدون تیک: فقط برای اطلاع فرستاده می‌شود و مرحله منتظر نمی‌ماند">'
      + '<input type="checkbox" class="r-req"' + (rule.required ? ' checked' : '') + '> الزامی — تا پاسخ نیاید مرحله ثبت نشود</label>'
      + '<div class="wf-rule-row"><label>پاسخ تأییدکننده</label><select class="r-answer">'
      + '<option value="">— فقط تأیید / عدم تأیید —</option>'
      + answerFields.filter(function (a) { return a.field_name !== field.field_name; }).map(function (a) {
          return '<option value="' + A.esc(a.field_name) + '"' + (a.field_name === rule.answer_field ? ' selected' : '') + '>'
            + A.esc(a.label) + (a.section_title ? ' — ' + A.esc(a.section_title) : '') + '</option>';
        }).join('') + '</select>'
      + '<button type="button" class="btn-sm btn-del r-del" title="حذف این قاعده">✕</button></div></div>';
  }

  function whoText(ids) {
    var names = (ids || []).map(function (id) {
      var u = definition.users.find(function (x) { return x.id === id; });
      return u ? u.full_name : null;
    }).filter(Boolean);
    return names.length ? '✅ ' + names.map(A.esc).join('، ') : '<span class="text-danger">تأییدکننده انتخاب نشده</span>';
  }

  function ruleFieldHtml(field, answerFields) {
    return '<div class="wf-rule-field" data-field-id="' + field.id + '">'
      + '<div class="wf-rule-head"><b>' + A.esc(field.label) + '</b>'
      + (field.section_title ? ' <span class="hint">— ' + A.esc(field.section_title) + '</span>' : '')
      + '<span class="save-state r-state"></span></div>'
      + '<div class="wf-rule-list">' + (field.rules.length ? field.rules.map(function (r) {
          return ruleRowHtml(field, r, answerFields);
        }).join('') : '') + '</div>'
      + '<div class="wf-rule-block"><span class="hint">⛔ مانع ارسال مرحله:</span> ' + field.options.map(function (o) {
          var on = (field.block_options || []).indexOf(o) !== -1;
          return '<label class="mini-check' + (on ? ' on' : '') + '"><input type="checkbox" class="r-block" value="'
            + A.esc(o) + '"' + (on ? ' checked' : '') + '> ' + A.esc(o) + '</label>';
        }).join('') + '</div>'
      + '<div class="wf-rule-actions"><button type="button" class="btn-ghost btn-sm r-add">➕ قاعده‌ی دیگر</button>'
      + '<button type="button" class="btn-primary btn-sm r-save">💾 ذخیره</button></div></div>';
  }

  async function loadRules(box) {
    var body = box.querySelector('.wf-rules-body');
    try {
      var res = await A.api.get('/api/workflow/stages/' + box.dataset.stageId + '/approval-rules');
      var d = box._rules = res.data;
      var count = d.fields.reduce(function (n, f) { return n + f.rules.length; }, 0);
      box.querySelector('.wf-rules-tag').textContent = count
        ? J.toFaDigits(count) + ' قاعده‌ی تأیید' : 'بدون ارجاع';
      body.innerHTML = '<div class="hint">هر قاعده: اگر یکی از گزینه‌های تیک‌خورده انتخاب شود، با ثبت مرحله، همان فرم‌ها '
        + '(و فرم‌هایی که آن پاسخ باز کرده) <b>برای اطلاع</b> این افراد فرستاده می‌شود؛ مرحله منتظر آن‌ها نمی‌ماند و '
        + 'کاربر مرحله کارش را ادامه می‌دهد. فقط قاعده‌ای که «الزامی» تیک خورده باشد مرحله را تا پاسخ نگه می‌دارد. '
        + '«مانع ارسال» یعنی با آن پاسخ اصلاً نمی‌شود ارسال کرد.</div>'
        + (d.items.length ? '<div class="hint">تأیید اجباری فرم‌ها: ' + d.items.map(function (i) {
            return '«' + A.esc(i.section_title) + '» ← ' + A.esc(i.approver_name || '—');
          }).join('، ') + '</div>' : '')
        + '<div class="wf-rule-fields">' + d.fields.map(function (f) { return ruleFieldHtml(f, d.answer_fields); }).join('')
        + '</div>'
        + (d.others.length ? '<select class="r-addfield"><option value="">➕ قاعده برای پرسشی دیگر از این مرحله…</option>'
            + d.others.map(function (f) {
                return '<option value="' + f.id + '">' + A.esc(f.label)
                  + (f.section_title ? ' — ' + A.esc(f.section_title) : '') + '</option>';
              }).join('') + '</select>' : '');
    } catch (err) { body.innerHTML = '<div class="alert error">' + A.esc(err.message) + '</div>'; }
  }

  function bindRules(box) {
    if (box._bound) return;
    box._bound = true;
    function fieldOf(el) {
      var holder = el.closest('.wf-rule-field');
      var id = holder && Number(holder.dataset.fieldId);
      var d = box._rules || { fields: [], others: [] };
      return { holder: holder, data: d.fields.concat(d.others).find(function (f) { return f.id === id; }) };
    }
    box.addEventListener('change', function (ev) {
      ev.stopPropagation();                  // a referral is saved on its own, not with the stage
      if (ev.target.classList.contains('r-opt') || ev.target.classList.contains('r-block')
          || ev.target.classList.contains('r-req')) {
        ev.target.closest('label').classList.toggle('on', ev.target.checked);
      }
      if (ev.target.classList.contains('r-who')) {
        var line = ev.target.closest('.wf-rule').querySelector('.wf-rule-who');
        if (line) line.innerHTML = whoText(Array.prototype.slice.call(ev.target.selectedOptions)
          .map(function (o) { return Number(o.value); }));
      }
      if (ev.target.classList.contains('r-addfield') && ev.target.value) {
        var d = box._rules;
        var f = d.others.find(function (x) { return String(x.id) === ev.target.value; });
        if (f) {
          d.others = d.others.filter(function (x) { return x !== f; });
          d.fields.push(f);
          var wrap = document.createElement('div');
          wrap.innerHTML = ruleFieldHtml(f, d.answer_fields);
          var node = wrap.firstChild;
          node.querySelector('.wf-rule-list').innerHTML = ruleRowHtml(f, null, d.answer_fields);
          box.querySelector('.wf-rule-fields').appendChild(node);
          ev.target.querySelector('option[value="' + f.id + '"]').remove();
          ev.target.value = '';
        }
      }
      var st = ev.target.closest('.wf-rule-field');
      if (st) st.querySelector('.r-state').textContent = 'ذخیره نشده';
    });
    box.addEventListener('click', async function (ev) {
      var add = ev.target.closest('.r-add');
      if (add) {
        var fo = fieldOf(add);
        var wrap = document.createElement('div');
        wrap.innerHTML = ruleRowHtml(fo.data, null, box._rules.answer_fields);
        fo.holder.querySelector('.wf-rule-list').appendChild(wrap.firstChild);
        return;
      }
      var del = ev.target.closest('.r-del');
      if (del) {
        var holder = del.closest('.wf-rule-field');
        del.closest('.wf-rule').remove();
        holder.querySelector('.r-state').textContent = 'ذخیره نشده';
        return;
      }
      var save = ev.target.closest('.r-save');
      if (save) {
        var fs = fieldOf(save);
        var rules = A.qsa('.wf-rule', fs.holder).map(function (row) {
          return {
            options: A.qsa('.r-opt:checked', row).map(function (c) { return c.value; }),
            approvers: Array.prototype.slice.call(row.querySelector('.r-who').selectedOptions)
              .map(function (o) { return Number(o.value); }),
            answer_field: row.querySelector('.r-answer').value || null,
            required: !!(row.querySelector('.r-req') || {}).checked,
          };
        }).filter(function (r) { return r.options.length || r.approvers.length; });
        var blocked = A.qsa('.r-block:checked', fs.holder).map(function (c) { return c.value; });
        var state = fs.holder.querySelector('.r-state');
        state.textContent = 'در حال ذخیره…';
        try {
          await A.api.put('/api/form-builder/fields/' + fs.data.id,
                          { approval_rules: rules, block_options: blocked });
          state.textContent = '✓ ذخیره شد';
          await loadRules(box);
        } catch (err) { state.textContent = ''; A.toast(err.message, 'error'); }
      }
    });
  }

  document.addEventListener('toggle', function (ev) {
    var box = ev.target;
    if (!box.classList || !box.classList.contains('wf-rules') || !box.open) return;
    bindRules(box);
    loadRules(box);
  }, true);

  /* «ترتیب و مسیر»: when this stage opens, when the run visits it at all, and
     which process starts once it is done. Nothing here is fixed in code — the
     کارگاه مکانیک and کارگاه کشیدن stages that open together after «بررسی
     کارشناس» are two stages waiting for the same one. */
  function orderPanel(s) {
    var others = definition.workflow.stages.filter(function (x) {
      return x.stage_number > 0 && x.stage_number !== s.stage_number && x.is_active !== false;
    });
    var waits = s.waits_for || [];
    var rule = s.visit_when || '';
    var on = rule.split('=')[0] || '';
    var picked = rule.indexOf('=') !== -1 ? rule.split('=').slice(1).join('=').split('|') : [];
    var fields = whenFields(s);
    var field = fields.find(function (f) { return f.name === on; });
    var flows = (definition.workflows || []).filter(function (w) { return w.id !== definition.workflow.id; });
    var count = (waits.length ? 1 : 0) + (on ? 1 : 0) + (s.spawn_workflow_id ? 1 : 0) + (s.spawn_when ? 1 : 0);
    var spawnRules = String(s.spawn_when || '').split(';').filter(function (x) { return x.indexOf('=') !== -1; });
    return '<details class="wf-refer wf-order"' + (count ? ' open' : '') + '>'
      + '<summary>🔀 ترتیب و مسیر<span class="wf-refer-tag">' + (count ? J.toFaDigits(count) + ' تنظیم'
          : 'از شروع فرایند باز است') + '</span></summary>'
      + '<div class="act-field"><label>این مرحله پس از ثبتِ این مرحله‌ها باز شود:</label>'
      + '<div class="wf-order-waits">' + (others.map(function (x) {
          var hit = waits.indexOf(x.stage_number) !== -1;
          return '<label class="mini-check' + (hit ? ' on' : '') + '"><input type="checkbox" class="wf-wait" value="'
            + x.stage_number + '"' + (hit ? ' checked' : '') + '> مرحله ' + J.toFaDigits(x.stage_number) + ' — '
            + A.esc(x.title) + '</label>';
        }).join('') || '<span class="hint">مرحله‌ی دیگری نیست.</span>') + '</div>'
      + '<span class="hint">چند مرحله که منتظر یک مرحله باشند، با ثبت آن هم‌زمان در کارتابل متولی‌هایشان باز '
      + 'می‌شوند (مثلاً کارگاه مکانیک و کارگاه کشیدن پس از بررسی کارشناس). بدون تیک: مثل قبل، از شروع فرایند باز است.</span></div>'
      + '<div class="act-field"><label>این مرحله فقط وقتی طی می‌شود که:</label>'
      + '<select class="wf-visit-on"><option value="">همیشه</option>'
      + fields.map(function (f) {
          return '<option value="' + A.esc(f.name) + '"' + (f.name === on ? ' selected' : '') + '>«'
            + A.esc(f.label) + '» یکی از این‌ها باشد:</option>';
        }).join('') + '</select>'
      + '<div class="wf-visit-values">' + visitValues(field, picked) + '</div>'
      + '<span class="hint">تا آن پرسش جواب نگرفته، مرحله در مسیر می‌ماند؛ با پاسخی که در فهرست نیست، از مسیر کنار می‌رود.</span></div>'
      + '<div class="act-field"><label>پس از ثبت (و تأیید) این مرحله، این فرایند هم برای همین چاه شروع شود:</label>'
      + '<select class="wf-spawn"><option value="">— هیچ —</option>'
      + flows.map(function (w) {
          return '<option value="' + w.id + '"' + (w.id === s.spawn_workflow_id ? ' selected' : '') + '>'
            + A.esc(w.name) + (w.is_active ? '' : ' (غیرفعال)') + '</option>';
        }).join('') + '</select>'
      + '<span class="hint">فرایند تازه با اطلاعات همین پرونده در کارتابل متولی مرحله‌ی شروعِ آن باز می‌شود '
      + '(مثلاً «فرایند نصب» پس از تأیید ساخت الکتروپمپ).</span>'
      + '<label class="mt-1">… فقط وقتی شروع شود که (همه‌ی شرط‌ها برقرار باشد):</label>'
      + '<div class="wf-spawn-rules">' + (spawnRules.length ? spawnRules : ['']).map(function (r) {
          return spawnRuleRow(s, r);
        }).join('') + '</div>'
      + '<button type="button" class="btn-sm btn-ghost wf-sw-add">➕ شرط دیگر</button>'
      + '<span class="hint">بدون شرط: همیشه. مثلاً «اقدام کارشناس» یکی از گزینه‌های ۲ و ۳ و «وضعیت کشیدن» = '
      + 'کشیدن انجام شد.</span></div>'
      + '</details>';
  }
  function spawnRuleRow(s, rule) {
    var on = (rule || '').split('=')[0] || '';
    var picked = (rule || '').indexOf('=') !== -1 ? rule.split('=').slice(1).join('=').split('|') : [];
    var fields = whenFields(s);
    var field = fields.find(function (f) { return f.name === on; });
    return '<div class="wf-sw-row">'
      + '<select class="wf-sw-on"><option value="">— پرسش —</option>'
      + fields.map(function (f) {
          return '<option value="' + A.esc(f.name) + '"' + (f.name === on ? ' selected' : '') + '>«'
            + A.esc(f.label) + '» یکی از این‌ها باشد:</option>';
        }).join('') + '</select>'
      + '<button type="button" class="btn-sm btn-del wf-sw-del" title="حذف شرط">×</button>'
      + '<div class="wf-sw-values">' + spawnValues(field, picked) + '</div></div>';
  }
  function spawnValues(field, picked) {
    if (!field) return '';
    return field.options.map(function (v) {
      return '<label class="mini-check' + (picked.indexOf(v) !== -1 ? ' on' : '') + '"><input type="checkbox" class="wf-sw-val" value="'
        + A.esc(v) + '"' + (picked.indexOf(v) !== -1 ? ' checked' : '') + '> ' + A.esc(v) + '</label>';
    }).join('');
  }
  function visitValues(field, picked) {
    if (!field) return '';
    return field.options.map(function (v) {
      return '<label class="mini-check"><input type="checkbox" class="wf-visit-val" value="'
        + A.esc(v) + '"' + (picked.indexOf(v) !== -1 ? ' checked' : '') + '> ' + A.esc(v) + '</label>';
    }).join('');
  }
  function readOrder(card, body) {
    if (!card.querySelector('.wf-order')) return;
    body.waits_for = A.qsa('.wf-wait:checked', card).map(function (b) { return Number(b.value); });
    var on = card.querySelector('.wf-visit-on').value;
    var vals = A.qsa('.wf-visit-val:checked', card).map(function (b) { return b.value; });
    body.visit_when = on && vals.length ? on + '=' + vals.join('|') : '';
    body.spawn_workflow_id = card.querySelector('.wf-spawn').value || null;
    body.spawn_when = A.qsa('.wf-sw-row', card).map(function (row) {
      var on = row.querySelector('.wf-sw-on').value;
      var vals = A.qsa('.wf-sw-val:checked', row).map(function (b) { return b.value; });
      return on && vals.length ? on + '=' + vals.join('|') : '';
    }).filter(Boolean).join(';');
  }

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
        + '<div class="wf-stage-row" title="برای گزارش تأخیر: اگر این مرحله بیش از این مدت طول بکشد تأخیردار شمرده می‌شود. خالی یعنی مهلت ندارد.">'
        + '<label>مهلت (ساعت)</label>'
        + '<input type="number" min="0" step="0.5" class="wf-sla" placeholder="اختیاری" value="'
        + (s.sla_hours === null || s.sla_hours === undefined ? '' : A.esc(s.sla_hours)) + '">'
        + '</div>'
        + startRow(s)
        + (s.description ? '<div class="hint wf-stage-desc">'
            + A.esc(s.description) + '</div>' : '')
        + (zero ? '<div class="hint">این مرحله فقط نوع عملیات را می‌پرسد.</div>'
                : orderPanel(s) + referralPanel(s) + actionsEditor(s) + approvalRulesPanel(s))
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
      var sla = card.querySelector('.wf-sla');
      if (sla) body.sla_hours = sla.value === '' ? null : Number(sla.value);
      var starts = card.querySelector('.wf-can-start');
      if (starts) body.can_start = starts.checked;
      var startKind = card.querySelector('.wf-start-kind');
      if (startKind) body.start_kind = startKind.value;
      var byCenter = card.querySelector('.wf-by-center');
      if (byCenter) body.route_by_center = byCenter.checked;
      var showRef = card.querySelector('.wf-show-ref');
      if (showRef) body.show_refdata = showRef.checked;
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
        var areq = card.querySelector('.wf-areq-enabled');
        if (areq) {
          body.approval_request_enabled = areq.checked;
          body.approval_request_user_ids = Array.prototype.slice.call(
            card.querySelector('.wf-areq-users').selectedOptions).map(function (o) { return Number(o.value); });
        }
      }
      if (card.querySelector('.wf-actions')) body.actions = readActions(card);
      readOrder(card, body);
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
          hidden_fields: ((li.querySelector('.wf-lock-panel') || { dataset: {} })
            .dataset.hidden || '').split(',').filter(Boolean),
          approval_user_id: (li.querySelector('.item-approver') || {}).value || null,
          approval_required: !!(li.querySelector('.item-approval-req') || {}).checked,
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
  /* «رصد فرایندها»: every process as a map, right to left — start, the stages
     in order (stages that ran together share a column), each stage's sign-off
     below it, the people a stage referred to above it, then the end, the stop,
     or the process it started. Filtered on the server. */
  var monFilled = false;
  async function fillMonitorFilters() {
    if (monFilled) return;
    monFilled = true;
    A.qsa('#pane-monitor .jdate').forEach(function (i) { if (J.attach) J.attach(i); });
    A.qs('#mon-flow').innerHTML = '<option value="">همه</option>' + (definition.workflows || []).map(function (w) {
      return '<option value="' + w.id + '">' + A.esc(w.name) + '</option>';
    }).join('');
    try {
      var res = await A.api.get('/api/lookups/center');
      var items = (res.data && (res.data.items || res.data)) || [];
      A.qs('#mon-center').innerHTML = '<option value="">همه</option>' + items.filter(function (i) {
        return i.is_active !== false;
      }).map(function (i) {
        return '<option value="' + i.id + '">' + A.esc(i.label || i.value) + '</option>';
      }).join('');
    } catch (err) { /* the other filters still work */ }
  }

  async function loadMonitor(extra) {
    await fillMonitorFilters();
    var params = [];
    [['status', '#mon-status'], ['kind', '#mon-kind'], ['workflow_id', '#mon-flow'],
     ['date_from', '#mon-from'], ['date_to', '#mon-to'], ['well', '#mon-well'],
     ['center_id', '#mon-center']].forEach(function (p) {
      var v = (A.qs(p[1]) || {}).value;
      if (v) params.push(p[0] + '=' + encodeURIComponent(v.trim()));
    });
    if (extra && extra.instance) params = ['instance=' + extra.instance];
    var list = A.qs('#mon-list');
    list.innerHTML = '<div class="loading">در حال بارگذاری</div>';
    try {
      var res = await A.api.get('/api/workflow/monitor?' + params.join('&'));
      var rows = res.data || [];
      A.qs('#mon-count').textContent = rows.length
        ? J.toFaDigits(rows.length) + ' فرایند' + (res.total > rows.length ? ' از ' + J.toFaDigits(res.total) : '')
        : '';
      if (!rows.length) {
        list.innerHTML = '<div class="table-empty">فرایندی با این فیلترها یافت نشد.</div>';
        return;
      }
      var graph = A.qs('#mon-view').value !== 'list';
      list.innerHTML = rows.map(function (r) { return monCard(r, graph); }).join('');
    } catch (err) {
      list.innerHTML = '<div class="alert error">' + A.esc(err.message) + '</div>';
    }
  }

  function monCard(r, graph) {
    var body = graph ? '<div class="mon-graph">' + flowSvg(r) + '</div>' : monSteps(r);
    /* «نمایش / مخفی»: each map folds away; the choice is remembered here */
    body = '<details class="mon-body" data-mon-fold="' + r.id + '"' + (monHidden(r.id) ? '' : ' open') + '>'
      + '<summary class="mon-body-head">' + (graph ? '🗺 نقشه‌ی فرایند' : '📋 مرحله‌ها')
      + ' <span class="hint">— نمایش / مخفی</span></summary>' + body + '</details>';
    return '<div class="card mon-card" id="mon-' + r.id + '">'
      + '<div class="card-head">'
      + '<span>🔀 فرایند #' + J.toFaDigits(r.id) + ' — ' + A.esc(r.well || 'چاه نامشخص')
      + (r.center ? ' <span class="hint">(' + A.esc(r.center) + ')</span>' : '') + '</span>'
      + '<span class="badge ' + (r.status === 'completed' ? 'ok' : r.status === 'open' ? 'warn' : 'danger') + '">'
      + A.esc(r.status_label) + '</span></div>'
      + '<div class="mon-meta">'
      + '<span class="badge">' + A.esc(r.operation_label) + '</span>'
      + (r.workflow_name ? '<span class="badge muted">🔀 ' + A.esc(r.workflow_name) + '</span>' : '')
      + (r.well_pm_code ? '<span class="badge muted">کد PM: ' + A.esc(r.well_pm_code) + '</span>' : '')
      + '<span class="badge muted">آغاز: ' + A.esc(r.created_at_j || '') + (r.created_by_name ? ' · ' + A.esc(r.created_by_name) : '') + '</span>'
      + (r.completed_at_j ? '<span class="badge muted">پایان: ' + A.esc(r.completed_at_j) + '</span>' : '')
      + (r.status === 'stopped' && r.outcome_note ? '<span class="badge warn">⛔ ' + A.esc(r.outcome_note) + '</span>' : '')
      + (r.record_id ? '<a class="badge ok" href="/records">رکورد #' + J.toFaDigits(r.record_id) + '</a>' : '')
      + (r.parent_id ? '<a class="badge" href="#" data-mon-instance="' + r.parent_id + '">↖ از فرایند #' + J.toFaDigits(r.parent_id) + '</a>' : '')
      + (r.children || []).map(function (c) {
          return '<a class="badge" href="#" data-mon-instance="' + c + '">↘ فرایند #' + J.toFaDigits(c) + '</a>';
        }).join('')
      + (r.attachment_count ? '<span class="badge muted">📎 ' + J.toFaDigits(r.attachment_count) + '</span>' : '')
      + '</div>' + body
      + (r.status === 'open' ? '<div class="mon-foot"><button class="btn-sm btn-del cancel-wf" data-id="' + r.id
          + '" type="button">لغو فرایند</button></div>' : '')
      + '</div>';
  }

  function monHidden(id) {
    try {
      var one = localStorage.getItem('wf-mon-map:' + id);
      if (one !== null) return one === '0';
      return localStorage.getItem('wf-mon-map:all') === '0';
    } catch (e) { return false; }
  }
  function monRemember(id, open) {
    try { localStorage.setItem('wf-mon-map:' + id, open ? '1' : '0'); } catch (e) { /* ok */ }
  }
  function monAll(open) {
    try {
      Object.keys(localStorage).forEach(function (k) {
        if (k.indexOf('wf-mon-map:') === 0) localStorage.removeItem(k);
      });
      localStorage.setItem('wf-mon-map:all', open ? '1' : '0');
    } catch (e) { /* ok */ }
    A.qsa('#mon-list details.mon-body').forEach(function (d) { d.open = open; });
  }
  document.addEventListener('toggle', function (ev) {
    var d = ev.target;
    if (d && d.matches && d.matches('details.mon-body[data-mon-fold]')) monRemember(d.dataset.monFold, d.open);
  }, true);

  function monSteps(r) {
    return '<div class="wf-path">' + (r.nodes || []).filter(function (n) { return n.kind === 'stage'; }).map(function (n) {
      return '<div class="wf-step ' + n.status + '">'
        + '<span class="wf-step-no">' + J.toFaDigits(n.stage_number) + '</span>'
        + '<span class="wf-step-title">' + A.esc(n.title) + '</span>'
        + '<span class="wf-step-who">' + A.esc(n.who || '') + '</span>'
        + '<span class="wf-step-state">' + A.esc(n.status_label || '') + '</span>'
        + (n.when ? '<span class="wf-step-when">' + A.esc(n.when) + '</span>' : '') + '</div>';
    }).join('') + '</div>';
  }

  var ST_COLORS = {
    submitted: ['#dcfce7', '#16a34a'], completed: ['#dcfce7', '#16a34a'], archived: ['#e0f2fe', '#0284c7'],
    deferred: ['#e0f2fe', '#0284c7'], pending: ['#f1f5f9', '#64748b'], waiting: ['#ffffff', '#94a3b8'],
    awaiting: ['#fef3c7', '#d97706'], rejected: ['#fee2e2', '#dc2626'], stopped: ['#fee2e2', '#dc2626'],
    cancelled: ['#fee2e2', '#dc2626'], skipped: ['#f8fafc', '#cbd5e1'], open: ['#e0f2fe', '#0284c7']
  };
  var EDGE = { flow: ['#475569', ''], info: ['#7c3aed', '4 3'], approval: ['#d97706', ''],
               return: ['#dc2626', '5 3'], spawn: ['#0891b2', '6 3'] };

  function clip(t, n) { t = String(t || ''); return t.length > n ? t.slice(0, n - 1) + '…' : t; }
  /* up to two lines of about n characters, broken between words */
  function wrap2(t, n) {
    t = String(t || '').trim();
    if (t.length <= n) return [t];
    var words = t.split(/\s+/), a = '', i = 0;
    while (i < words.length && (a + (a ? ' ' : '') + words[i]).length <= n) { a += (a ? ' ' : '') + words[i]; i++; }
    if (!a) { a = t.slice(0, n); return [a, clip(t.slice(n), n)]; }
    return [a, clip(words.slice(i).join(' '), n)];
  }
  function svgEsc(t) { return A.esc(String(t == null ? '' : t)); }

  function flowSvg(r) {
    var nodes = r.nodes || [], edges = r.edges || [];
    /* sized so a full title, its متولی and its state fit inside the shape */
    var COL = 280, W_ST = 236, H_ST = 92, PILL_W = 208, PILL_H = 28, BELOW_H = 64;
    var main = nodes.filter(function (n) { return !n.attach; });
    var byKey = {};
    nodes.forEach(function (n) { byKey[n.key] = n; });
    var cols = {};
    main.forEach(function (n) { (cols[n.level] = cols[n.level] || []).push(n); });
    var above = {}, below = {};
    nodes.filter(function (n) { return n.attach; }).forEach(function (n) {
      var bag = n.place === 'above' ? above : below;
      (bag[n.attach] = bag[n.attach] || []).push(n);
    });
    var maxAbove = 0, maxBelow = 0;
    main.forEach(function (n) {
      maxAbove = Math.max(maxAbove, Math.min((above[n.key] || []).length, 4));
      var b = (below[n.key] || []).slice();
      b.forEach(function (x) { b = b.concat(below[x.key] || []); });
      maxBelow = Math.max(maxBelow, b.length);
    });
    var rowH = H_ST + 34 + maxAbove * (PILL_H + 6) + maxBelow * (BELOW_H + 12);
    var top = 16 + maxAbove * (PILL_H + 6);
    var levels = Object.keys(cols).map(Number);
    var maxLevel = Math.max.apply(null, levels.concat([0]));
    var maxRows = Math.max.apply(null, Object.keys(cols).map(function (k) { return cols[k].length; }).concat([1]));
    var W = (maxLevel + 1) * COL + 40, H = top + maxRows * rowH + 10;
    var pos = {};
    levels.forEach(function (lv) {
      cols[lv].forEach(function (n, i) {
        pos[n.key] = { x: W - 20 - lv * COL - COL / 2, y: top + i * rowH + H_ST / 2,
                       w: n.kind === 'stage' ? W_ST : (n.kind === 'link' ? 150 : 76), h: n.kind === 'stage' ? H_ST : 64 };
      });
    });
    function place(anchorKey) {
      var a = pos[anchorKey];
      if (!a) return;
      (above[anchorKey] || []).slice(0, 4).forEach(function (n, i) {
        pos[n.key] = { x: a.x, y: a.y - a.h / 2 - 14 - i * (PILL_H + 6), w: PILL_W, h: PILL_H };
      });
      var extra = (above[anchorKey] || []).length - 4;
      if (extra > 0) pos[anchorKey].more = extra;
      var yb = a.y + a.h / 2 + 18;
      (below[anchorKey] || []).forEach(function (n) {
        pos[n.key] = { x: a.x, y: yb + BELOW_H / 2, w: n.kind === 'approval' ? 180 : 208, h: BELOW_H };
        yb += BELOW_H + 12;
        place(n.key);
        if (below[n.key]) yb += (below[n.key].length) * (BELOW_H + 12);
      });
    }
    main.forEach(function (n) { place(n.key); });

    var out = [];
    out.push('<svg class="flow-svg" xmlns="http://www.w3.org/2000/svg" width="' + W + '" height="' + H
      + '" viewBox="0 0 ' + W + ' ' + H + '" direction="rtl">');
    out.push('<defs>' + Object.keys(EDGE).map(function (k) {
      return '<marker id="ar-' + k + '-' + r.id + '" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        + '<path d="M0,0 L10,5 L0,10 z" fill="' + EDGE[k][0] + '"/></marker>';
    }).join('') + '</defs>');
    // edges first, nodes on top
    edges.forEach(function (e) {
      var a = pos[e.from], b = pos[e.to];
      if (!a || !b) return;
      var c = EDGE[e.kind] || EDGE.flow, d;
      if (e.kind === 'flow') {
        var x1 = a.x - a.w / 2, y1 = a.y, x2 = b.x + b.w / 2, y2 = b.y, mx = (x1 + x2) / 2;
        d = 'M' + x1 + ',' + y1 + ' C' + mx + ',' + y1 + ' ' + mx + ',' + y2 + ' ' + x2 + ',' + y2;
      } else if (e.kind === 'return') {
        var xr = a.x + a.w / 2, xs = b.x + b.w / 2 + 4;
        d = 'M' + xr + ',' + a.y + ' C' + (xr + 40) + ',' + a.y + ' ' + (xs + 40) + ',' + b.y + ' ' + xs + ',' + b.y;
      } else {
        var up = b.y < a.y;
        d = 'M' + a.x + ',' + (a.y + (up ? -a.h / 2 : a.h / 2)) + ' L' + b.x + ',' + (b.y + (up ? b.h / 2 : -b.h / 2));
      }
      out.push('<path d="' + d + '" fill="none" stroke="' + c[0] + '" stroke-width="' + (e.kind === 'flow' ? 1.8 : 1.4) + '"'
        + (c[1] ? ' stroke-dasharray="' + c[1] + '"' : '') + ' marker-end="url(#ar-' + e.kind + '-' + r.id + ')"/>');
    });
    nodes.forEach(function (n) {
      var p = pos[n.key];
      if (!p) return;
      var col = ST_COLORS[n.status] || ST_COLORS.pending;
      var tip = [n.title, n.who, n.status_label, n.when, n.sub, n.note].filter(Boolean).join(' — ');
      var g = '<g class="fnode k-' + n.kind + '"' + (n.instance_id ? ' data-mon-instance="' + n.instance_id + '" style="cursor:pointer"' : '')
        + '><title>' + svgEsc(tip) + '</title>';
      var dash = n.status === 'waiting' || n.status === 'skipped' ? ' stroke-dasharray="5 3"' : '';
      if (n.kind === 'stage') {
        g += '<rect x="' + (p.x - p.w / 2) + '" y="' + (p.y - p.h / 2) + '" width="' + p.w + '" height="' + p.h
          + '" rx="12" fill="' + col[0] + '" stroke="' + col[1] + '" stroke-width="1.6"' + dash + '/>'
          + '<circle cx="' + (p.x + p.w / 2 - 14) + '" cy="' + (p.y - p.h / 2 + 14) + '" r="10" fill="' + col[1] + '"/>'
          + '<text x="' + (p.x + p.w / 2 - 14) + '" y="' + (p.y - p.h / 2 + 18) + '" text-anchor="middle" class="f-no">'
          + svgEsc(J.toFaDigits(n.stage_number)) + '</text>'
          + wrap2(n.title, 24).map(function (line, li, all) {
            return '<text x="' + (p.x - 10) + '" y="' + (p.y - (all.length > 1 ? 24 : 14) + li * 16) + '" text-anchor="middle" class="f-title">'
              + svgEsc(line) + '</text>';
          }).join('')
          + '<text x="' + p.x + '" y="' + (p.y + 14) + '" text-anchor="middle" class="f-who">' + svgEsc(clip(n.who, 34)) + '</text>'
          + '<text x="' + p.x + '" y="' + (p.y + 32) + '" text-anchor="middle" class="f-state" fill="' + col[1] + '">'
          + svgEsc(clip((n.status_label || '') + (n.when ? ' · ' + n.when : ''), 36)) + '</text>';
        if (p.more) g += '<text x="' + p.x + '" y="' + (p.y - p.h / 2 - 14 - 4 * (PILL_H + 6) + 10) + '" text-anchor="middle" class="f-sub">+'
          + svgEsc(J.toFaDigits(p.more)) + ' ارجاع دیگر</text>';
      } else if (n.kind === 'start' || n.kind === 'end') {
        g += '<circle cx="' + p.x + '" cy="' + p.y + '" r="30" fill="' + col[0] + '" stroke="' + col[1] + '" stroke-width="' + (n.kind === 'end' ? 4 : 2) + '"/>'
          + '<text x="' + p.x + '" y="' + (p.y + 4) + '" text-anchor="middle" class="f-title">' + svgEsc(clip(n.title, 8)) + '</text>'
          + (n.sub ? '<text x="' + p.x + '" y="' + (p.y + 48) + '" text-anchor="middle" class="f-sub">' + svgEsc(clip(n.sub, 32)) + '</text>' : '');
      } else if (n.kind === 'stop') {
        var r8 = 30, pts = [];
        for (var k = 0; k < 8; k++) {
          var ang = Math.PI / 8 + k * Math.PI / 4;
          pts.push((p.x + r8 * Math.cos(ang)).toFixed(1) + ',' + (p.y + r8 * Math.sin(ang)).toFixed(1));
        }
        g += '<polygon points="' + pts.join(' ') + '" fill="#fee2e2" stroke="#dc2626" stroke-width="2"/>'
          + '<text x="' + p.x + '" y="' + (p.y + 4) + '" text-anchor="middle" class="f-title" fill="#b91c1c">' + svgEsc(n.title) + '</text>'
          + (n.sub ? '<text x="' + p.x + '" y="' + (p.y + 48) + '" text-anchor="middle" class="f-sub">' + svgEsc(clip(n.sub, 36)) + '</text>' : '');
      } else if (n.kind === 'approval') {
        var hw = p.w / 2, hh = p.h / 2;
        g += '<polygon points="' + p.x + ',' + (p.y - hh) + ' ' + (p.x + hw) + ',' + p.y + ' ' + p.x + ',' + (p.y + hh) + ' ' + (p.x - hw) + ',' + p.y
          + '" fill="' + col[0] + '" stroke="' + col[1] + '" stroke-width="1.6"/>'
          + '<text x="' + p.x + '" y="' + (p.y - 3) + '" text-anchor="middle" class="f-who">' + svgEsc(clip(n.title, 22)) + '</text>'
          + '<text x="' + p.x + '" y="' + (p.y + 14) + '" text-anchor="middle" class="f-state" fill="' + col[1] + '">' + svgEsc(clip(n.status_label || '', 20)) + '</text>';
      } else if (n.kind === 'referral') {
        g += '<rect x="' + (p.x - p.w / 2) + '" y="' + (p.y - p.h / 2) + '" width="' + p.w + '" height="' + p.h
          + '" rx="12" fill="' + col[0] + '" stroke="#7c3aed" stroke-width="1.2"/>'
          + '<text x="' + p.x + '" y="' + (p.y + 5) + '" text-anchor="middle" class="f-sub">📝 ' + svgEsc(clip(n.title, 20))
          + ' · ' + svgEsc(clip(n.status_label || '', 14)) + '</text>';
      } else if (n.kind === 'link') {
        var lw = p.w / 2, lh = p.h / 2, cut = 14;
        g += '<polygon points="' + (p.x - lw + cut) + ',' + (p.y - lh) + ' ' + (p.x + lw - cut) + ',' + (p.y - lh) + ' ' + (p.x + lw) + ',' + p.y
          + ' ' + (p.x + lw - cut) + ',' + (p.y + lh) + ' ' + (p.x - lw + cut) + ',' + (p.y + lh) + ' ' + (p.x - lw) + ',' + p.y
          + '" fill="' + col[0] + '" stroke="#0891b2" stroke-width="1.6"/>'
          + '<text x="' + p.x + '" y="' + (p.y - 4) + '" text-anchor="middle" class="f-title">' + svgEsc(clip(n.title, 16)) + '</text>'
          + '<text x="' + p.x + '" y="' + (p.y + 14) + '" text-anchor="middle" class="f-sub">' + svgEsc(clip(n.sub, 24)) + '</text>';
      }
      out.push(g + '</g>');
    });
    out.push('</svg>');
    return out.join('');
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
      var swAdd = ev.target.closest('.wf-sw-add'), swDel = ev.target.closest('.wf-sw-del');
      if (swAdd || swDel) {
        var scard = (swAdd || swDel).closest('.wf-stage');
        if (swAdd) {
          var sst = definition.workflow.stages.find(function (x) { return String(x.id) === scard.dataset.stage; });
          scard.querySelector('.wf-spawn-rules').insertAdjacentHTML('beforeend', spawnRuleRow(sst || {}, ''));
        } else {
          swDel.closest('.wf-sw-row').remove();
        }
        markDirty(scard);
        return;
      }
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
        var userHint = card.querySelector('.wf-refer-user-hint');
        if (userHint) userHint.hidden = mode === 'next';
        card.querySelector('.wf-refer-hint-row').hidden = mode !== 'choose';
        card.querySelector('.wf-refer-user').querySelector('label').textContent =
          mode === 'choose' ? 'پیش‌فرض' : 'کاربر';
      }
      if (ev.target.classList.contains('wf-areq-enabled')) {
        var abox = ev.target.closest('.wf-stage').querySelector('.wf-areq-box');
        if (abox) abox.hidden = !ev.target.checked;
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
      if (ev.target.classList.contains('lock-field') || ev.target.classList.contains('hide-field')) {
        syncLocks(ev.target.closest('.wf-drop-item'));
        return;
      }
      if (ev.target.classList.contains('wf-visit-on')) {
        var vst = definition.workflow.stages.find(function (x) {
          return String(x.id) === card.dataset.stage; });
        var vf = whenFields(vst || {}).find(function (x) { return x.name === ev.target.value; });
        card.querySelector('.wf-visit-values').innerHTML = visitValues(vf, []);
      }
      if (ev.target.classList.contains('wf-sw-on')) {
        var sst = definition.workflow.stages.find(function (x) {
          return String(x.id) === card.dataset.stage; });
        var sf = whenFields(sst || {}).find(function (x) { return x.name === ev.target.value; });
        ev.target.closest('.wf-sw-row').querySelector('.wf-sw-values').innerHTML = spawnValues(sf, []);
      }
      if (ev.target.classList.contains('wf-sw-val')) {
        ev.target.closest('label').classList.toggle('on', ev.target.checked);
      }
      if (ev.target.classList.contains('wf-wait') || ev.target.classList.contains('wf-visit-val')) {
        ev.target.closest('label').classList.toggle('on', ev.target.checked);
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
    A.qs('#mon-refresh').addEventListener('click', function () { loadMonitor(); });
    if (A.qs('#mon-maps-show')) {
      A.qs('#mon-maps-show').addEventListener('click', function () { monAll(true); });
      A.qs('#mon-maps-hide').addEventListener('click', function () { monAll(false); });
    }
    ['#mon-status', '#mon-kind', '#mon-center', '#mon-flow', '#mon-view'].forEach(function (sel) {
      A.qs(sel).addEventListener('change', function () { loadMonitor(); });
    });
    A.qs('#mon-well').addEventListener('keydown', function (ev) { if (ev.key === 'Enter') loadMonitor(); });
    /* a linked process: jump to its card, or show it alone */
    A.qs('#mon-list').addEventListener('click', function (ev) {
      var link = ev.target.closest('[data-mon-instance]');
      if (!link) return;
      ev.preventDefault();
      var id = link.getAttribute('data-mon-instance');
      var card = A.qs('#mon-' + id);
      if (card) { card.scrollIntoView({ behavior: 'smooth', block: 'center' }); card.classList.add('flash');
                  setTimeout(function () { card.classList.remove('flash'); }, 1500); }
      else loadMonitor({ instance: id });
    });
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
