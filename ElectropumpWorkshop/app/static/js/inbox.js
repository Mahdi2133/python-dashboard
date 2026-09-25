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
  var canStart = false;        // does this user own a stage that opens one?
  var startable = [];          // and which operations that stage admits
  var myStages = [], running = 0;  // what the کارتابل holds when it is empty

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
      box.innerHTML = emptyHtml();
      return;
    }
    var html = canStart
      ? '<div class="wf-group">مرحله ۰ — شروع فرایند</div>'
        + '<button class="wf-item wf-item-start" data-start="1" type="button">'
        + '<div class="wf-item-top">'
        + '<span class="wf-stage-no">۰</span>'
        + '<span class="wf-item-title">شروع فرایند جدید</span>'
        + '<span class="badge">🚦</span></div>'
        + '<div class="wf-item-sub">نوع عملیات و چاه را تعیین کنید تا فرایند '
        + 'آغاز شود.</div></button>'
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

  /* An empty کارتابل that explains itself.

     "The forms I assigned to this user are not connected" is what an empty
     list looks like; the truth is usually that nothing is running yet. So
     list the stages this person owns — that is the connection, visible. */
  function emptyHtml() {
    var head = '<div class="table-empty">در حال حاضر کاری در کارتابل شما نیست.';
    if (!myStages.length) {
      return head + '<div class="hint">هیچ مرحله‌ای در فرایندساز به نام شما '
        + 'ثبت نشده است. مدیر سیستم می‌تواند در تب «فرایندساز» شما را متولی '
        + 'یک مرحله کند.</div></div>';
    }
    var rows = myStages.map(function (s) {
      return '<li><span class="wf-stage-no">'
        + J.toFaDigits(s.stage_number) + '</span> ' + A.esc(s.title)
        + '<span class="mine-role">'
        + (s.role === 'approve' ? 'تأییدکننده' : 'متولی') + '</span>'
        + '<span class="mine-count">' + J.toFaDigits(s.field_count)
        + ' مورد</span></li>';
    }).join('');
    return head
      + '<div class="hint">' + J.toFaDigits(myStages.length)
      + ' مرحله به نام شما ثبت شده است؛ '
      + (running
          ? 'هیچ‌کدام از ' + J.toFaDigits(running)
            + ' فرایند باز هنوز به آن‌ها نرسیده است.'
          : 'در این لحظه هیچ فرایندی در جریان نیست، پس کارتابل خالی است.')
      + '</div><ul class="mine-stages">' + rows + '</ul></div>';
  }

  function itemHtml(it, i) {
    var waiting = (it.waiting_on || []).length;
    var active = current && current.id === it.id
      && current.stage_number === it.stage_number;
    var approving = it.task_kind === 'approve';
    var referred = !!it.referred_to_name;
    return '<button class="wf-item' + (active ? ' active' : '')
      + (approving ? ' to-approve' : referred ? ' referred' : '')
      + '" data-i="' + i + '" type="button">'
      + '<div class="wf-item-top">'
      + '<span class="wf-stage-no">'
      + (approving ? '✅' : J.toFaDigits(it.stage_number)) + '</span>'
      + '<span class="wf-item-title">' + A.esc(it.stage_title) + '</span>'
      + '<span class="badge ' + (approving ? 'warn'
          : it.operation_kind === 'pull' ? 'warn' : '') + '">'
      + (approving ? 'تأیید' : A.esc(it.operation_label)) + '</span>'
      + '</div>'
      + (it.referred_by_name
          ? '<div class="wf-item-refer">🔀 ارجاع از ' + A.esc(it.referred_by_name)
            + (it.referral_note ? ' — ' + A.esc(it.referral_note) : '')
            + '</div>'
          : '')
      + '<div class="wf-item-sub">'
      + A.esc(it.created_at_j || '')
      + (it.entry_status === 'rejected'
          ? ' · <span class="badge warn">برگشت خورده</span>' : '')
      + (it.unassigned ? ' · <span class="badge warn">بدون متولی</span>' : '')
      + (waiting ? ' · <span class="badge warn">' + J.toFaDigits(waiting)
          + ' مرحله عقب‌تر ثبت نشده</span>' : '')
      + '</div></button>';
  }

  async function loadInbox() {
    try {
      var res = await A.api.get('/api/workflow/inbox');
      items = res.data || [];
      /* Step zero is a stage like any other, so it is a card in the work list
         rather than a button hanging over every page. Only its owner gets it,
         and only there does the «شروع فرایند» form exist. */
      canStart = !!res.may_start;
      startable = res.startable || [];
      myStages = res.my_stages || [];
      running = res.running || 0;
      renderList();
    } catch (err) {
      fill('#inbox-items', '<div class="alert error">'
           + A.esc(err.message) + '</div>');
    }
  }

  /* ── one stage ──────────────────────────────────────────────────────── */
  function renderPath(detail) {
    var done = {};
    (detail.entries || []).forEach(function (e) { done[e.stage_number] = e; });
    fill('#wf-path', (detail.path || []).map(function (s) {
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
    }).join(''));
  }

  /* What this stage is for and what to do with it, in the stage's own words —
     the description the admin wrote in the process builder. */
  function renderGuide(detail) {
    var stage = detail.form && detail.form.stage;
    if (!stage) { fill('#wf-guide', ''); return; }
    var required = [], conditional = 0;
    (detail.form.sections || []).forEach(function (s) {
      /* A cause form is owed only once its cause is ticked; listing all ten
         forms' readings up front buries the three fields that really are. */
      if (s.conditional) { conditional += 1; return; }
      (s.fields || []).forEach(function (f) {
        if (f.is_required && !f.read_only) required.push(f.label);
      });
    });
    fill('#wf-guide', '<div class="alert info wf-guide">'
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
      + (conditional
          ? ' با انتخاب هر علت خرابی، فرم پارامترهای همان علت باز می‌شود و '
            + 'پر کردن آن هم الزامی است.'
          : '')
      + '</div></div>');
  }

  function renderWarning(detail) {
    var waiting = detail.waiting_on || [];
    if (!waiting.length) { fill('#wf-warning', ''); return; }
    /* A warning, never a block — the stage owner may well have the numbers in
       hand before the paperwork upstream catches up. */
    fill('#wf-warning',
      '<div class="alert warn">⚠ این مرحله‌ها هنوز ثبت نشده‌اند: '
      + waiting.map(function (w) {
          return '<b>مرحله ' + J.toFaDigits(w.stage_number) + ' — '
            + A.esc(w.title) + '</b>'
            + (w.assignee ? ' (' + A.esc(w.assignee) + ')' : '');
        }).join('، ')
      + '.<br>می‌توانید مرحله‌ی خود را همین حالا تکمیل کنید؛ فرایند منتظر '
      + 'ترتیب مرحله‌ها نمی‌ماند.</div>');
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
    var keep = { submitted: 1, archived: 1, deferred: 1 };
    return (detail.entries || []).filter(function (e) {
      return e.stage_number > 0 && e.stage_number !== current.stage_number
        && keep[e.status];
    }).sort(function (a, b) { return a.stage_number - b.stage_number; })
      .map(function (e) {
        var values = [];
        Object.keys(e.payload || {}).forEach(function (name) {
          var v = e.payload[name];
          if (Array.isArray(v)) v = v.filter(Boolean).join('، ');
          if (v === null || v === undefined || v === '' || v === false) return;
          values.push({ label: labels[name] || name, value: String(v) });
        });
        return {
          stage_number: e.stage_number, title: e.title || '',
          status: e.status, status_label: e.status_label,
          user_name: e.user_name, submitted_at_j: e.submitted_at_j,
          note: e.note, values: values,
        };
      }).filter(function (b) { return b.values.length || b.note; });
  }

  function renderSummary(detail) {
    var blocks = detail.summary || summaryFromEntries(detail);
    /* An approver sees what the sender opened to them and nothing else, so
       say so — an approver who does not know the view is narrowed may read a
       missing stage as a stage nobody filled. */
    var scoped = detail.summary_scoped
      ? '<div class="hint">ثبت‌کنندهٔ این مرحله تعیین کرده است که شما کدام '
        + 'مرحله‌ها را ببینید؛ بقیه‌ی مرحله‌ها اینجا نشان داده نمی‌شوند.</div>'
      : '';
    if (!blocks.length) {
      fill('#wf-summary', scoped
           || '<div class="hint">هنوز مرحله‌ای پیش از این ثبت نشده است.</div>');
      return;
    }
    fill('#wf-summary', scoped + blocks.map(function (b) {
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
        + ' مرحله ' + J.toFaDigits(a.stage_number) + '</span>'
        + '<button class="btn-sm btn-del" data-del-doc="' + a.id + '" type="button">🗑</button>'
        + '</div>';
    }).join('') + '</div>');
  }

  async function openStage(entry) {
    try {
      var res = await A.api.get('/api/workflow/instances/' + entry.id
                                + '?stage=' + entry.stage_number);
      var detail = res.data;
      current = { id: detail.id, stage_number: entry.stage_number, detail: detail };
      A.qs('#wf-detail').classList.remove('hidden');
      setText('#wf-title', 'مرحله ' + J.toFaDigits(entry.stage_number)
        + ' — ' + (detail.form ? detail.form.stage.title : '')
        + (detail.well ? ' · ' + detail.well : ''));
      setText('#wf-kind', detail.operation_label);
      /* The form first. It is the point of this page, and everything after it
         is context around it — so nothing that decorates the page can end up
         standing between the stage owner and the fields they came to fill.
         Everything the process already knows is filled in, so a stage can see
         and correct what came before rather than typing it again. */
      buildForm(detail.form ? detail.form.sections : [],
                detail.operation_label, detail.payload || {});
      if (detail.well) fillPrevious(detail.well);
      /* A blocking approval in front of this stage stops it being filled —
         the server refuses it either way, so the button says so first. */
      var hold = detail.blocked_by;
      var submit = A.qs('#wf-submit');
      if (submit) {
        submit.disabled = !detail.may_act || !!hold;
        submit.title = hold
          ? 'در انتظار تأیید مرحله ' + hold.stage_number
          : (detail.may_act ? '' : 'این مرحله در اختیار شما نیست.');
      }
      fill('#wf-progress', progressHtml(detail.referral_progress));
      fill('#wf-blocked', hold
        ? '<div class="wf-blocked">⛔ مرحله ' + J.toFaDigits(hold.stage_number)
          + ' — ' + A.esc(hold.title) + ' در انتظار تأیید '
          + '<b>' + A.esc(hold.approver || 'تأییدکننده') + '</b> است. '
          + 'تا تأیید نشود، این مرحله ثبت نمی‌شود.</div>'
        : '');
      renderReferral(detail);
      renderDecision(detail);

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

  /* Where this stage's work goes when it is sent on. The admin decided the
     shape of this in the process builder: a fixed person, the next stage's own
     متولی, or — the case this box exists for — whoever the person finishing
     the stage names. */
  /* A stage referred to several people who must all record: say who has and
     who has not, so nobody wonders why pressing ثبت did not move it on. */
  function progressHtml(progress) {
    if (!progress || !progress.all_must || progress.people.length < 2) return '';
    var done = progress.people.filter(function (p) { return p.done; }).length;
    return '<div class="refer-progress">👥 این مرحله به '
      + J.toFaDigits(progress.people.length) + ' نفر ارجاع شده و همه باید ثبت '
      + 'کنند — ' + J.toFaDigits(done) + ' نفر ثبت کرده‌اند: '
      + progress.people.map(function (p) {
          return '<span class="rp ' + (p.done ? 'done' : 'left') + '">'
            + (p.done ? '✓ ' : '… ') + A.esc(p.full_name) + '</span>';
        }).join(' ') + '</div>';
  }

  function renderReferral(detail) {
    var box = A.qs('#wf-refer-box');
    var refer = detail.referral || {};
    if (!box) return;
    var choosing = refer.mode === 'choose' && detail.may_act
      && !detail.awaiting_my_decision;
    box.classList.toggle('hidden', !detail.may_act || detail.awaiting_my_decision
                         || (refer.mode === 'next' && !refer.needs_approval));
    A.qs('#wf-refer-pick').classList.toggle('hidden', !choosing);

    var where;
    if (refer.needs_approval) {
      where = 'این مرحله پس از ثبت، برای تأیید به <b>'
        + A.esc(refer.approver_name || 'تأییدکننده تعیین‌نشده')
        + '</b> ارسال می‌شود.';
    } else if (refer.mode === 'user') {
      var names = (refer.default_user_names || []);
      where = 'پس از ثبت، کار به <b>'
        + A.esc(names.length ? names.join('، ')
                             : (refer.default_user_name || 'کاربر تعیین‌نشده'))
        + '</b> ارجاع می‌شود'
        + (names.length > 1
            ? (refer.refer_all ? ' و همه باید ثبت کنند.' : ' و ثبت یکی کافی است.')
            : '.');
    } else if (choosing) {
      where = A.esc(refer.hint || 'کار را به کارتابل چه کسی ارجاع می‌دهید؟');
    } else {
      where = 'پس از ثبت، کار به متولی مرحله بعد می‌رود'
        + (refer.next_stage && refer.next_stage.assignee_name
            ? ' (<b>' + A.esc(refer.next_stage.assignee_name) + '</b>)' : '')
        + '.';
    }
    fill('#wf-refer-info', where);

    /* One recipient or several: «ارجاع به دفتر فنی و بهره‌بردار» sends the
       same work to two کارتابل at once. Whether one of them is enough or all
       of them must record is the admin's setting, said here in words. */
    var list = A.qs('#wf-refer-list');
    if (list && choosing) {
      var defaults = refer.default_user_ids || [];
      list.innerHTML = (refer.users || []).map(function (u) {
        return '<label class="refer-pick-row" data-name="'
          + A.esc((u.full_name + ' ' + u.username).toLowerCase()) + '">'
          + '<input type="checkbox" class="refer-pick" value="' + u.id + '"'
          + (defaults.indexOf(u.id) !== -1 ? ' checked' : '') + '>'
          + '<span>' + A.esc(u.full_name) + '</span>'
          + '<i>' + A.esc(u.role_label) + '</i></label>';
      }).join('');
      fill('#wf-refer-all-note', refer.refer_all
        ? 'اگر چند نفر را انتخاب کنید، <b>همه</b> باید ثبت کنند تا کار جلو برود.'
        : 'اگر چند نفر را انتخاب کنید، ثبت <b>یکی</b> از آن‌ها کافی است.');
    }
    renderShare(detail);
  }

  /* What the approver will be allowed to read.

     An approval is a judgement on something, so whoever asks for it says what
     that something is. The admin decides per stage whether this is fixed
     («همه‌ی اطلاعات» or «فقط همین مرحله») or handed to the sender — and only
     then does this list appear, with the stage being approved always in it
     because that is the thing being judged. */
  function renderShare(detail) {
    var box = A.qs('#wf-share-box');
    if (!box) return;
    var ap = detail.approval;
    var picking = ap && ap.sees === 'pick' && detail.may_act
      && !detail.awaiting_my_decision;
    box.classList.toggle('hidden', !ap || detail.awaiting_my_decision
                         || !detail.may_act);
    if (!ap || !detail.may_act || detail.awaiting_my_decision) return;

    var head = '<div class="share-head">🔒 تأییدکننده (<b>'
      + A.esc(ap.approver || 'تعیین‌نشده') + '</b>) چه می‌بیند: '
      + A.esc(ap.sees_label) + '</div>'
      + (ap.blocks
          ? '<div class="share-block">⛔ تا زمانی که این مرحله تأیید نشود، '
            + 'مرحله‌های بعدی ثبت نمی‌شوند.</div>'
          : '');
    if (!picking) { box.innerHTML = head; return; }
    var rows = (ap.choices || []);
    box.innerHTML = head
      + (rows.length
          ? '<div class="hint">مرحله‌هایی را که می‌خواهید تأییدکننده ببیند '
            + 'تیک بزنید. اطلاعات همین مرحله همیشه دیده می‌شود.</div>'
            + '<ul class="share-list">'
            + rows.map(function (r) {
                return '<li><label><input type="checkbox" class="share-pick"'
                  + ' value="' + r.stage_number + '" checked>'
                  + '<span class="wf-stage-no">'
                  + J.toFaDigits(r.stage_number) + '</span> '
                  + A.esc(r.title)
                  + '<span class="share-meta">' + J.toFaDigits(r.field_count)
                  + ' مورد' + (r.owner ? ' · ' + A.esc(r.owner) : '')
                  + '</span></label></li>';
              }).join('')
            + '</ul>'
          : '<div class="hint">هنوز مرحله‌ی ثبت‌شده‌ی دیگری نیست؛ '
            + 'تأییدکننده اطلاعات همین مرحله را می‌بیند.</div>');
  }

  /* The approver's view: the work is filled in and read-only, and the only
     thing left is a verdict. */
  function renderDecision(detail) {
    var box = A.qs('#wf-decide-box');
    var actions = A.qs('#wf-submit-actions');
    if (!box) return;
    var deciding = !!detail.awaiting_my_decision;
    box.classList.toggle('hidden', !deciding);
    if (actions) actions.classList.toggle('hidden', deciding);
    if (!deciding) return;
    /* The approver is here to judge what was written, not to rewrite it. The
       form stays on screen — they need to read it — but the pen is taken away
       so nothing can be changed behind the submitter's back. */
    if (form && form.lock) form.lock();
    var entry = (detail.entries || []).filter(function (e) {
      return e.stage_number === current.stage_number;
    })[0] || {};
    fill('#wf-decide-info',
      'این مرحله را <b>' + A.esc(entry.user_name || '—') + '</b> ثبت کرده و '
      + 'برای تأیید شما فرستاده است'
      + (entry.submitted_at_j ? ' (' + A.esc(entry.submitted_at_j) + ')' : '')
      + '. با «تأیید» کار به مرحله بعد می‌رود؛ با «برگشت» همراه دلیل، به '
      + 'ثبت‌کننده بازمی‌گردد.');
  }

  async function decide(approved) {
    if (!current) return;
    var note = (A.qs('#wf-decide-note') || {}).value || '';
    if (!approved && !note.trim()) {
      A.toast('برای برگشت دادن، ذکر دلیل الزامی است.', 'error');
      A.qs('#wf-decide-note').focus();
      return;
    }
    try {
      var res = await A.api.post('/api/workflow/instances/' + current.id
                                 + '/decide',
        { stage_number: current.stage_number, approved: approved,
          comment: note });
      A.toast(res.message || 'ثبت شد.', 'success');
      A.qs('#wf-decide-note').value = '';
      A.qs('#wf-detail').classList.add('hidden');
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
      var refer = (current.detail && current.detail.referral) || {};
      var recipients = A.qsa('.refer-pick:checked')
        .map(function (b) { return Number(b.value); });
      if (refer.mode === 'choose' && !recipients.length) {
        A.toast('ارجاع به کدام کاربر؟ دست‌کم یک نفر را انتخاب کنید.', 'error');
        button.disabled = false;
        return;
      }
      var res = await A.api.post('/api/workflow/instances/' + current.id + '/submit',
        { stage_number: current.stage_number, data: form.collect(),
          refer_to: recipients.length ? recipients : null,
          referral_note: (A.qs('#wf-refer-note') || {}).value || null,
          share_stages: A.qsa('.share-pick:checked')
            .map(function (b) { return Number(b.value); }) });
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

  /* Draw the نوع عملیات choices from what this person may actually open.

     کشیدن and نصب start at different stages and so belong to different
     people: مرکز آبرسانی opens a کشیدن, کارگاه نصب opens a نصب. Offering a
     radio the server will refuse is worse than not offering it. */
  function renderKinds() {
    var box = A.qs('#np-kind');
    if (!box || !startable.length) return;
    box.innerHTML = startable.map(function (k, i) {
      return '<label><input type="radio" name="np_kind" value="' + A.esc(k.label)
        + '"' + (startable.length === 1 || i === 0 ? ' checked' : '')
        + '><span class="btn-opt">' + A.esc(k.label) + '</span></label>';
    }).join('');
    var hint = box.parentNode && box.parentNode.querySelector('.hint');
    if (hint) {
      hint.textContent = startable.length === 1
        ? 'شما فقط می‌توانید عملیات «' + startable[0].label + '» را آغاز کنید؛ '
          + 'عملیات دیگر از مرحله‌ی کاربر دیگری شروع می‌شود.'
        : 'هر عملیات از مرحله‌ای آغاز می‌شود که در فرایندساز برایش تعیین شده '
          + 'است.';
    }
  }

  /* ── new process ────────────────────────────────────────────────────── */
  async function startProcess() {
    var kind = A.qs('input[name="np_kind"]:checked');
    if (!kind) { A.toast('نوع عملیات را انتخاب کنید.', 'error'); return; }
    if (!A.qs('#np-well').value.trim()) {
      A.toast('نام چاه را انتخاب کنید — چاه فقط همین‌جا تعیین می‌شود.', 'error');
      A.qs('#np-well').focus();
      return;
    }
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
      if (ev.target.closest('[data-start]')) {
        renderKinds(); A.openModal('new-process-modal'); return;
      }
      var button = ev.target.closest('[data-i]');
      if (button) openStage(items[Number(button.dataset.i)]);
    });
    A.qs('#btn-refresh').addEventListener('click', loadInbox);
    var referSearch = A.qs('#wf-refer-search');
    if (referSearch) referSearch.addEventListener('input', function () {
      var q = this.value.trim().toLowerCase();
      A.qsa('.refer-pick-row').forEach(function (row) {
        row.hidden = !!q && row.dataset.name.indexOf(q) === -1;
      });
    });
    A.qs('#wf-close').addEventListener('click', function () {
      A.qs('#wf-detail').classList.add('hidden');
      current = null;
      renderList();
    });
    A.qs('#wf-submit').addEventListener('click', submitStage);
    A.qs('#wf-approve').addEventListener('click', function () { decide(true); });
    A.qs('#wf-reject').addEventListener('click', function () { decide(false); });
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
    A.qs('#np-start').addEventListener('click', startProcess);
    /* The well picker in the dialog is the same autocomplete the forms use,
       so the process starts against a canonical well from the register. */
    window.FormEngine.attachAutocomplete(A.qs('#np-well'), schema.lookups);
  });
})();
