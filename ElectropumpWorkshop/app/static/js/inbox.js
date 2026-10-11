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
  var approvalsToMe = [], approvalResults = [];   // «ارجاع برای تأیید»
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
    setText('#inbox-count', J.toFaDigits(items.length + approvalsToMe.length + approvalResults.length));
    if (!box) return;
    var extra = approvalHtml();
    if (!items.length && !canStart && !extra) {
      box.innerHTML = emptyHtml();
      return;
    }
    var html = canStart
      ? '<div class="wf-group">🚦 شروع فرایند</div>'
        + '<button class="wf-item wf-item-start" data-start="1" type="button">'
        + '<div class="wf-item-top">'
        + '<span class="wf-stage-no">＋</span>'
        + '<span class="wf-item-title">شروع فرایند جدید</span>'
        + '<span class="badge">🚦</span></div>'
        + '<div class="wf-item-sub">نوع عملیات و چاه را تعیین کنید تا فرایند '
        + 'آغاز شود.</div></button>'
      : '';
    html = extra + html;
    /* Several offices run their wells at the same time, so the work is
       grouped by the well's مرکز (folded and unfolded by hand, remembered),
       and inside it by process — one well, one heading. */
    var offices = [], byOffice = {};
    items.forEach(function (it, i) {
      var name = officeOf(it);
      if (!byOffice[name]) { byOffice[name] = []; offices.push(name); }
      byOffice[name].push(i);
    });
    box.innerHTML = html + offices.map(function (name) {
      var idx = byOffice[name], lastRef = null;
      var wells = {};
      idx.forEach(function (i) { wells[items[i].id] = 1; });
      return '<details class="wf-office"' + (officeFolded(name) ? '' : ' open') + ' data-office="' + A.esc(name) + '">'
        + '<summary><span>🏢 ' + A.esc(name) + '</span><span class="wf-office-n">'
        + J.toFaDigits(Object.keys(wells).length) + ' چاه · ' + J.toFaDigits(idx.length) + ' کار</span></summary>'
        + idx.map(function (i) {
          var it = items[i], header = '';
          if (it.id !== lastRef) {
            lastRef = it.id;
            header = '<div class="wf-group">' + (it.well ? A.esc(it.well) : 'فرایند')
              + ' <span class="hint">#' + J.toFaDigits(it.id) + '</span></div>';
          }
          return header + itemHtml(it, i);
        }).join('') + '</details>';
    }).join('');
  }

  function officeOf(it) { return it.well_center || 'بدون مرکز'; }
  function officeFolded(name) {
    try { return window.localStorage.getItem('wf-office-fold:' + name) === '1'; } catch (e) { return false; }
  }
  document.addEventListener('toggle', function (ev) {
    var d = ev.target;
    if (!d || !d.classList || !d.classList.contains('wf-office')) return;
    try { window.localStorage.setItem('wf-office-fold:' + d.dataset.office, d.open ? '0' : '1'); } catch (e) { /* private window */ }
  }, true);

  /* ── «وضعیت چاه‌ها»: by office, which wells reached my stage, which wait
     for me and which have gone on ─────────────────────────────────────── */
  var board = null;
  async function loadBoard() {
    var wrap = A.qs('#wf-board');
    if (!wrap) return;
    var q = '?days=' + encodeURIComponent((A.qs('#wb-days') || {}).value || 60)
      + ((A.qs('#wb-stage') || {}).value ? '&stage_id=' + A.qs('#wb-stage').value : '');
    try {
      board = (await A.api.get('/api/workflow/board' + q)).data;
    } catch (err) {
      fill('#wb-body', '<div class="hint">' + A.esc(err.message) + '</div>');
      return;
    }
    var sel = A.qs('#wb-stage');
    if (sel && sel.options.length <= 1 && board.stages.length > 1) {
      sel.innerHTML = '<option value="">همه‌ی مرحله‌های من</option>' + board.stages.map(function (st) {
        return '<option value="' + st.id + '">' + J.toFaDigits(st.stage_number) + ' — ' + A.esc(st.title) + '</option>';
      }).join('');
    }
    if (sel) sel.classList.toggle('hidden', board.stages.length < 2 && !sel.value);
    renderBoard();
  }

  /* One dropdown, not a wall of cards: the wells still to do (yours first,
     then returned, waiting on approval or on earlier stages) and the wells
     done, each with its office; picking one opens it here. */
  function renderBoard() {
    if (!board) return;
    var t = board.totals, remaining = t.todo + t.returned + t.approval + t.waiting;
    setText('#wb-totals', board.offices.length
      ? J.toFaDigits(board.offices.length) + ' اداره · باقی‌مانده ' + J.toFaDigits(remaining)
        + ' · انجام‌شده ' + J.toFaDigits(t.done) : '');
    var needle = ((A.qs('#wb-q') || {}).value || '').trim();
    var pick = A.qs('#wb-pick');
    if (!pick) return;
    var left = [], gone = [];
    var RANK = { todo: 0, returned: 1, approval: 2, waiting: 3 };
    board.offices.forEach(function (o) {
      o.wells.forEach(function (w) {
        if (needle && (w.well || '').indexOf(needle) === -1 && (o.office || '').indexOf(needle) === -1) return;
        (w.state === 'done' ? gone : left).push({ w: w, office: o.office });
      });
    });
    left.sort(function (a, b) { return (RANK[a.w.state] || 9) - (RANK[b.w.state] || 9)
      || String(a.office).localeCompare(String(b.office), 'fa') || String(a.w.well).localeCompare(String(b.w.well), 'fa'); });
    gone.sort(function (a, b) { return String(a.office).localeCompare(String(b.office), 'fa')
      || String(a.w.well).localeCompare(String(b.w.well), 'fa'); });
    var MARK = { todo: '🟠', returned: '🔴', approval: '🟣', waiting: '⚪', done: '✅' };
    var opt = function (x) {
      var w = x.w;
      return '<option value="' + w.instance_id + '|' + w.stage_number + '">'
        + MARK[w.state] + ' ' + A.esc(x.office || '—') + ' — ' + A.esc(w.well || ('#' + w.instance_id))
        + (board.stages.length > 1 ? ' — مرحله ' + J.toFaDigits(w.stage_number) : '')
        + ' (' + A.esc(w.state_label) + (w.done_at_j ? ' ' + A.esc(w.done_at_j) : '') + ')</option>';
    };
    pick.innerHTML = (board.offices.length
        ? '<option value="">— انتخاب چاه (' + J.toFaDigits(left.length) + ' باقی‌مانده، ' + J.toFaDigits(gone.length) + ' انجام‌شده) —</option>'
        : '<option value="">در این بازه چاهی به مرحله‌های شما نرسیده است</option>')
      + (left.length ? '<optgroup label="⏳ باقی‌مانده (' + J.toFaDigits(left.length) + ')">' + left.map(opt).join('') + '</optgroup>' : '')
      + (gone.length ? '<optgroup label="✅ انجام‌شده (' + J.toFaDigits(gone.length) + ')">' + gone.map(opt).join('') + '</optgroup>' : '');
  }

  /* «ارجاع برای تأیید» in the list: requests waiting on me, and the answers
     to the requests I sent. */
  function approvalHtml() {
    var html = '';
    if (approvalsToMe.length) {
      html += '<div class="wf-group">📝 ارجاع‌ها برای شما (اطلاع / تأیید)</div>'
        + approvalsToMe.map(function (r) {
          return '<button class="wf-item to-approve" data-areq="' + r.id + '" type="button">'
            + '<div class="wf-item-top"><span class="wf-stage-no">✓</span>'
            + '<span class="wf-item-title">' + A.esc(r.stage_title || '') + '</span>'
            + (r.required ? '<span class="badge warn">اجباری</span>' : '') + '</div>'
            + '<div class="wf-item-sub">از ' + A.esc(r.requester_name || '') + ' · '
            + A.esc(r.well || '') + ' · فرایند #' + J.toFaDigits(r.instance_id) + '</div></button>';
        }).join('');
    }
    if (approvalResults.length) {
      html += '<div class="wf-group">📬 پاسخ درخواست‌های تأیید شما</div>'
        + approvalResults.map(function (r) {
          var okd = r.status === 'approved';
          return '<button class="wf-item" data-ares="' + r.id + '" data-inst="' + r.instance_id
            + '" data-stage="' + r.stage_number + '" type="button">'
            + '<div class="wf-item-top"><span class="wf-stage-no">' + (okd ? '✅' : '✕') + '</span>'
            + '<span class="wf-item-title">' + A.esc(r.stage_title || '') + '</span>'
            + '<span class="badge ' + (okd ? 'ok' : 'danger') + '">' + A.esc(r.status_label) + '</span></div>'
            + '<div class="wf-item-sub">' + A.esc(r.approver_name || '')
            + (r.answer && r.answer.value ? ' — ' + A.esc(r.answer.value) : '')
            + (r.decision_note ? ': ' + A.esc(r.decision_note) : '')
            + ' · ' + A.esc(r.well || '') + '</div></button>';
        }).join('');
    }
    return html;
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
      items = (res.data || []).map(function (it, n) { it._n = n; return it; });
      // by office, then by well; inside one process the server's order stays
      items.sort(function (a, b) {
        var oa = officeOf(a), ob = officeOf(b);
        if (oa !== ob) return oa === 'بدون مرکز' ? 1 : ob === 'بدون مرکز' ? -1 : oa.localeCompare(ob, 'fa');
        if ((a.well || '') !== (b.well || '')) return (a.well || '').localeCompare(b.well || '', 'fa');
        return a._n - b._n;
      });
      /* Step zero is a stage like any other, so it is a card in the work list
         rather than a button hanging over every page. Only its owner gets it,
         and only there does the «شروع فرایند» form exist. */
      canStart = !!res.may_start;
      startable = res.startable || [];
      myStages = res.my_stages || [];
      running = res.running || 0;
      approvalsToMe = res.approval_requests || [];
      approvalResults = res.approval_results || [];
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

  /* «باکس اطلاعات ثبت‌شده»: each stage's box folds away, and stays folded
     the next time (remembered on this computer). */
  function foldKey(n) { return 'wf-sum-fold:' + n; }
  function isFolded(n) {
    try { return localStorage.getItem(foldKey(n)) === '1'; } catch (e) { return false; }
  }
  function setFolded(n, on) {
    try { if (on) localStorage.setItem(foldKey(n), '1'); else localStorage.removeItem(foldKey(n)); } catch (e) { /* ok */ }
  }
  function sumBlockHtml(b, tag) {
    var key = (tag || '') + b.stage_number;
    return '<details class="sum-block ' + A.esc(b.status) + '" data-fold="' + A.esc(key) + '"'
      + (isFolded(key) ? '' : ' open') + '>'
      + '<summary class="sum-head">'
      + '<span class="wf-step-no">' + J.toFaDigits(b.stage_number) + '</span>'
      + '<b>' + A.esc(b.title) + '</b>'
      + '<span class="badge muted">' + A.esc(b.status_label) + '</span>'
      + '<span class="sum-who">' + A.esc(b.user_name || '')
      + (b.submitted_at_j ? ' · ' + A.esc(b.submitted_at_j) : '') + '</span>'
      + '<span class="sum-fold-hint">نمایش / پنهان</span>'
      + '</summary>'
      + (b.note ? '<div class="sum-note">' + A.esc(b.note) + '</div>' : '')
      + (b.groups && b.groups.length ? sumGroupsHtml(b.groups)
         : '<dl class="sum-values">' + b.values.map(sumValueHtml).join('') + '</dl>')
      + (b.charts || []).map(function (c) {
          var id = 'sc' + (++sumChartSeq);
          sumCharts[id] = c;
          return '<div class="sum-chart"><div class="sum-chart-title">📈 ' + A.esc(c.label) + '</div>'
            + '<div class="form-chart" data-sum-chart="' + id + '"></div>'
            + '<div class="form-chart-eq hint" data-sum-chart-eq="' + id + '"></div></div>';
        }).join('')
      + '</details>';
  }
  /* One recorded answer; a document is shown as the file itself, to open. */
  function sumCell(v) {
    return v.files && v.files.length
      ? v.files.map(function (a) {
          return '<a href="' + A.esc(a.url) + '" target="_blank">📄 ' + A.esc(a.filename) + '</a>';
        }).join(' ')
      : A.esc(v.value);
  }
  function sumValueHtml(v) {
    return '<dt>' + A.esc(v.label) + '</dt><dd>' + sumCell(v) + '</dd>';
  }
  /* «سکشن‌بندی»: a stage's answers form by form. Forms of the same shape side
     by side — the five «کارکرد» of a pumping test — become one table, one
     column per form, so کارکرد ۱ is never mistaken for کارکرد ۲. */
  function sumAlike(g1, g2) {
    var a = g1.values.map(function (v) { return v.label; });
    var b = g2.values.map(function (v) { return v.label; });
    if (a.length < 3 || b.length < 3) return false;
    if (g1.values.concat(g2.values).some(function (v) { return v.files && v.files.length; })) return false;
    var both = a.filter(function (x) { return b.indexOf(x) !== -1; }).length;
    var all = a.length + b.length - both;
    return both / all >= 0.6;
  }
  function sumCommonPrefix(titles) {
    var p = titles[0] || '';
    titles.forEach(function (t) { while (p && t.indexOf(p) !== 0) p = p.slice(0, -1); });
    var cut = Math.max(p.lastIndexOf('—'), p.lastIndexOf('-'), p.lastIndexOf(':'));
    return cut > 0 ? p.slice(0, cut + 1) : '';
  }
  function sumTableHtml(run) {
    var prefix = sumCommonPrefix(run.map(function (g) { return g.title; }));
    var labels = [];
    run.forEach(function (g) {
      g.values.forEach(function (v) { if (labels.indexOf(v.label) === -1) labels.push(v.label); });
    });
    var head = prefix.replace(/[—\-:]\s*$/, '').trim();
    return '<div class="sum-group"><div class="sum-group-title">' + A.esc(head || run[0].title) + '</div>'
      + '<div class="sum-table-wrap"><table class="sum-table"><thead><tr><th></th>'
      + run.map(function (g) {
          return '<th>' + A.esc(g.title.slice(prefix.length).trim() || g.title) + '</th>';
        }).join('') + '</tr></thead><tbody>'
      + labels.map(function (lbl) {
          return '<tr><th>' + A.esc(lbl) + '</th>' + run.map(function (g) {
            var v = g.values.filter(function (x) { return x.label === lbl; })[0];
            return '<td>' + (v ? sumCell(v) : '—') + '</td>';
          }).join('') + '</tr>';
        }).join('') + '</tbody></table></div></div>';
  }
  function sumGroupsHtml(groups) {
    var out = [], i = 0;
    while (i < groups.length) {
      var j = i + 1;
      while (j < groups.length && sumAlike(groups[i], groups[j])) j++;
      if (j - i >= 2) out.push(sumTableHtml(groups.slice(i, j)));
      else out.push('<div class="sum-group"><div class="sum-group-title">' + A.esc(groups[i].title)
                    + '</div><dl class="sum-values">' + groups[i].values.map(sumValueHtml).join('')
                    + '</dl></div>');
      i = j;
    }
    return out.join('');
  }

  /* «نمودار» in a summary: drawn once its box is open and has a size. */
  var sumCharts = {}, sumChartSeq = 0;
  function drawSumCharts(scope) {
    if (!window.FormEngine || !window.FormEngine.drawStaticChart) return;
    A.qsa('[data-sum-chart]', scope || document).forEach(function (box) {
      var c = sumCharts[box.dataset.sumChart];
      if (!c || !box.offsetParent) return;
      var eq = A.qs('[data-sum-chart-eq="' + box.dataset.sumChart + '"]', scope || document);
      window.FormEngine.drawStaticChart(box, eq, c.chart, c.values).catch(function () {
        box.innerHTML = '<div class="hint">کتابخانه‌ی نمودار بارگذاری نشد.</div>';
      });
    });
  }
  document.addEventListener('toggle', function (ev) {
    var d = ev.target;
    if (d && d.matches && d.matches('details.sum-block[data-fold]')) {
      setFolded(d.dataset.fold, !d.open);
      if (d.open) drawSumCharts(d);
    }
    if (d && d.id === 'wf-summary-wrap') { setFolded('all', !d.open); if (d.open) drawSumCharts(d); }
  }, true);

  function renderSummary(detail) {
    var wrap = A.qs('#wf-summary-wrap');
    if (wrap) wrap.open = !isFolded('all');
    var parentHtml = '';
    if (detail.parent) {
      parentHtml = '<div class="sum-parent"><div class="pal-group-title">🔗 از فرایند #'
        + J.toFaDigits(detail.parent.id) + ' — ' + A.esc(detail.parent.workflow_name || '')
        + ' (' + A.esc(detail.parent.status_label || '') + ')</div>'
        + (detail.parent_summary || []).map(function (b) { return sumBlockHtml(b, 'p'); }).join('')
        + '</div>';
    }
    if ((detail.children || []).length) {
      parentHtml += '<div class="hint">🔗 فرایندهایی که از این فرایند شروع شد: '
        + detail.children.map(function (c) {
          return '#' + J.toFaDigits(c.id) + ' ' + A.esc(c.workflow_name || '') + ' (' + A.esc(c.status_label) + ')';
        }).join('، ') + '</div>';
    }
    var blocks = detail.summary || summaryFromEntries(detail);
    /* An approver sees what the sender opened to them and nothing else, so
       say so — an approver who does not know the view is narrowed may read a
       missing stage as a stage nobody filled. */
    var scoped = detail.summary_scoped
      ? '<div class="hint">ثبت‌کنندهٔ این مرحله تعیین کرده است که شما کدام '
        + 'مرحله‌ها را ببینید؛ بقیه‌ی مرحله‌ها اینجا نشان داده نمی‌شوند.</div>'
      : '';
    var tools = blocks.length > 1 || detail.parent
      ? '<div class="sum-tools"><button type="button" class="btn-sm btn-ghost" data-sum-all="close">➖ پنهان کردن همه</button>'
        + '<button type="button" class="btn-sm btn-ghost" data-sum-all="open">➕ نمایش همه</button></div>'
      : '';
    if (!blocks.length) {
      fill('#wf-summary', parentHtml + (scoped
           || '<div class="hint">هنوز مرحله‌ای پیش از این ثبت نشده است.</div>'));
      setTimeout(function () { drawSumCharts(A.qs('#wf-summary')); }, 60);
      return;
    }
    fill('#wf-summary', tools + parentHtml + scoped + blocks.map(function (b) {
      return sumBlockHtml(b, '');
    }).join(''));
    setTimeout(function () { drawSumCharts(A.qs('#wf-summary')); }, 60);
  }
  document.addEventListener('click', function (ev) {
    var b = ev.target.closest && ev.target.closest('[data-sum-all]');
    if (!b) return;
    A.qsa('#wf-summary details.sum-block').forEach(function (d) { d.open = b.dataset.sumAll === 'open'; });
    setTimeout(function () { drawSumCharts(A.qs('#wf-summary')); }, 60);
  });

  /* The label of the «مستند» field a document was uploaded into. */
  function slotLabel(name) {
    var found = null;
    ((current && current.detail && current.detail.form && current.detail.form.sections) || [])
      .forEach(function (sec) {
        (sec.fields || []).forEach(function (f) { if (f.field_name === name) found = f.label; });
      });
    return found || 'مستند فرم';
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
        + (a.field_name ? '<span class="badge muted">' + A.esc(slotLabel(a.field_name)) + '</span>' : '')
        + (a.approval_request_id ? '<span class="badge warn">پیوست ارجاع تأیید</span>' : '')
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
                detail.operation_label,
                Object.assign({}, detail.payload || {}, detail.draft || {}));
      if (detail.well) fillPrevious(detail.well);
      resetRefPanel(detail.well, detail.form && detail.form.stage);
      renderApprovalPanel(detail);
      /* A blocking approval in front of this stage stops it being filled —
         the server refuses it either way, so the button says so first. */
      var hold = detail.blocked_by;
      var before = detail.opens_after || [];
      var submit = A.qs('#wf-submit');
      if (submit) {
        submit.disabled = !detail.may_act || !!hold || before.length > 0;
        submit.title = hold
          ? 'در انتظار تأیید مرحله ' + hold.stage_number
          : before.length ? 'این مرحله هنوز باز نشده است'
          : (detail.may_act ? '' : 'این مرحله در اختیار شما نیست.');
      }
      fill('#wf-progress', progressHtml(detail.referral_progress));
      renderDocsOwed(detail);
      renderDecisionChoices(detail);
      fill('#wf-blocked', (hold
        ? '<div class="wf-blocked">⛔ مرحله ' + J.toFaDigits(hold.stage_number)
          + ' — ' + A.esc(hold.title) + ' در انتظار تأیید '
          + '<b>' + A.esc(hold.approver || 'تأییدکننده') + '</b> است. '
          + 'تا تأیید نشود، این مرحله ثبت نمی‌شود.</div>'
        : '')
        + (before.length
          ? '<div class="wf-blocked">⏳ این مرحله پس از ثبت '
            + before.map(function (b) { return '«' + A.esc(b.title) + '»'; }).join(' و ')
            + ' باز می‌شود.</div>'
          : ''));
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
  /* «تصمیم شما»: forward, stop, or send back — whichever this stage offers and
     this person may use. With only «ارسال» there is nothing to choose and the
     box stays out of the way. */
  function renderDecisionChoices(detail) {
    var box = A.qs('#wf-decision');
    if (!box) return;
    var acts = detail.actions || [];
    var show = detail.may_act && !detail.awaiting_my_decision && acts.length > 1;
    box.classList.toggle('hidden', !show);
    if (!show) return;
    A.qs('#wf-decision-options').innerHTML = acts.map(function (a, i) {
      var icon = a.kind === 'stop' ? '⛔' : a.kind === 'return' ? '↩' : '✅';
      var sub = a.kind === 'return' && a.choices
        ? 'برگشت به: <select class="d-target">'
          + '<option value="">— کدام مرحله؟ —</option>'
          + a.choices.map(function (c) {
              return '<option value="' + c.stage_number + '">مرحله '
                + J.toFaDigits(c.stage_number) + ' — ' + A.esc(c.title)
                + (c.by ? ' (' + A.esc(c.by) + ')' : '') + '</option>';
            }).join('') + '</select>'
          + (a.needs_docs ? ' · بارگذاری مستند الزامی' : '')
        : a.kind === 'return'
        ? 'برگشت به مرحله ' + J.toFaDigits(a.target_stage) + ' — '
          + A.esc(a.target_title || '')
          + (a.needs_docs ? ' · بارگذاری مستند الزامی' : '')
        : a.kind === 'stop'
          ? 'فرایند همین‌جا بسته می‌شود و ادامه پیدا نمی‌کند.'
          : 'فرم را کامل کنید تا کار به مرحله‌ی بعد برود.';
      return '<label class="decision-opt ' + a.kind + '"'
        + (a.when ? ' data-when="' + A.esc(a.when) + '"' : '') + '>'
        + '<input type="radio" name="wf_action" value="' + A.esc(a.id) + '"'
        + ' data-kind="' + a.kind + '"' + (i === 0 ? ' checked' : '') + '>'
        + '<span class="d-main">' + icon + ' ' + A.esc(a.label) + '</span>'
        + '<span class="d-sub">' + sub + '</span></label>';
    }).join('');
    A.qs('#wf-decision-note').value = '';
    decisionTied = false;
    refreshDecisions();
  }

  /* A decision tied to an answer — «نمایش فقط وقتی نتیجه بررسی = نیاز به
     کشیدن ندارد» — comes up the moment that answer is picked: it is selected,
     its description box opens, and «ارسال به مرحله بعد» steps aside, because
     that answer means the work does not go on. Take the answer back and it
     all goes back. The server holds the same rule on submit. */
  var decisionTied = false;

  function ruleHolds(rule, values) {
    var at = rule.indexOf('=');
    if (at < 0) return true;
    var wanted = rule.slice(at + 1).split('|').map(function (v) { return v.trim(); })
      .filter(Boolean);
    var have = values[rule.slice(0, at).trim()];
    have = Array.isArray(have) ? have : [have];
    if (wanted.indexOf('*') !== -1) {
      return have.some(function (h) { return h !== null && h !== undefined && String(h).trim() !== ''; });
    }
    return have.some(function (h) {
      return h !== null && h !== undefined && wanted.indexOf(String(h).trim()) !== -1;
    });
  }

  function refreshDecisions() {
    var box = A.qs('#wf-decision');
    if (!box || !current || !current.detail) return;
    var detail = current.detail;
    if (!detail.may_act || detail.awaiting_my_decision
        || (detail.actions || []).length < 2) return;
    var values = Object.assign({}, detail.payload || {}, form ? form.collect() : {});
    var opts = A.qsa('#wf-decision-options .decision-opt');
    var tied = [];
    opts.forEach(function (opt) {
      opt._ok = !opt.dataset.when || ruleHolds(opt.dataset.when, values);
      if (opt.dataset.when && opt._ok) tied.push(opt);
    });
    var others = 0;
    opts.forEach(function (opt) {
      var show = opt.classList.contains('forward') ? !tied.length : opt._ok;
      opt.hidden = !show;
      if (show && !opt.classList.contains('forward')) others += 1;
    });
    box.classList.toggle('hidden', !others);
    var checked = A.qs('input[name="wf_action"]:checked');
    var lost = !checked || checked.closest('.decision-opt').hidden;
    if ((tied.length && !decisionTied) || lost) {
      var pick = tied[0] || opts.find(function (o) { return !o.hidden; });
      if (pick) pick.querySelector('input[type=radio]').checked = true;
    }
    if (tied.length && !decisionTied) {
      box.classList.remove('flash'); void box.offsetWidth; box.classList.add('flash');
      if (box.scrollIntoView) box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
    decisionTied = !!tied.length;
    decisionChanged();
  }

  function chosenAction() {
    var r = A.qs('input[name="wf_action"]:checked');
    if (!r) return { id: 'forward', kind: 'forward' };
    var pick = r.closest('.decision-opt').querySelector('.d-target');
    return { id: r.value, kind: r.dataset.kind, picks: !!pick,
             target: pick ? pick.value : null };
  }

  function decisionChanged() {
    var a = chosenAction();
    A.qs('#wf-decision-note-row').classList.toggle('hidden', a.kind === 'forward');
    /* «ارجاع» hands on the next stage; it means nothing when the work is
       being stopped or sent back, so it steps aside. */
    var refer = A.qs('#wf-refer-pick');
    if (refer && current && current.detail) {
      var r = current.detail.referral || {};
      refer.classList.toggle('hidden', a.kind !== 'forward' || r.mode !== 'choose'
        || !current.detail.may_act || current.detail.awaiting_my_decision);
    }
    var btn = A.qs('#wf-submit');
    if (btn) {
      btn.textContent = a.kind === 'stop' ? '⛔ توقف فرایند'
        : a.kind === 'return' ? '↩ برگشت برای تکمیل'
        : '✅ ثبت و ارسال مرحله';
      btn.classList.toggle('btn-danger', a.kind === 'stop');
      btn.classList.toggle('btn-primary', a.kind !== 'stop');
    }
  }

  /* Sent back «with a photo, a video, any document»: say by whom and why,
     and that nothing goes on until something is attached. */
  function renderDocsOwed(detail) {
    var d = detail.docs_owed;
    fill('#wf-docs-owed', d
      ? '<div class="wf-docs-owed' + (d.sent ? ' done' : '') + '">📎 '
        + '<b>' + A.esc(d.by || 'مرحله‌ی بعد') + '</b> درخواست مستند کرده است'
        + (d.note ? ': «' + A.esc(d.note) + '»' : '') + '.<br>'
        + (d.sent
            ? '✓ ' + J.toFaDigits(d.sent) + ' مستند بارگذاری شده؛ حالا می‌توانید '
              + 'مرحله را دوباره ثبت کنید.'
            : 'پیش از ثبت دوباره، دست‌کم یک عکس، فیلم یا فایل در بخش «مستندات '
              + 'این فرایند» پایین همین صفحه بارگذاری کنید.')
        + '</div>'
      : '');
  }

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
      where = A.esc(refer.hint || 'کار را به کارتابل چه کسی ارجاع می‌دهید؟')
        + (refer.next_stage
            ? ' <span class="hint">(ارجاع یعنی سپردن مرحله‌ی بعد — <b>مرحله '
              + J.toFaDigits(refer.next_stage.stage_number) + ' «'
              + A.esc(refer.next_stage.title) + '»</b>)</span>'
            : '');
      /* Sending the work back to somebody behind this stage is not a
         referral — it would hand them the next stage's forms. Say where the
         way back is, when this person has one. */
      if ((detail.actions || []).some(function (a) { return a.kind === 'return'; })) {
        where += '<div class="hint mt-1">↩ برای برگرداندن کار به مرحله‌های قبل، '
          + 'در «تصمیم شما در این مرحله» گزینه‌ی برگشت را انتخاب کنید.</div>';
      }
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

  /* «نمایش فقط وقتی…» as this stage draws it. A «فیلد مشترک» is drawn
     under its source's name but with its own rule — «تیپ الکتروموتور» in the
     assembly opens on «مونتاژ کدام تجهیز؟», not on the pump type it waits for
     in the entry form — so the rules come from the stage's own forms and
     fields; the global list only fills in for what the stage does not draw. */
  function ruleEntry(raw) {
    var any = String(raw || '').split(';').map(function (part) {
      var k = part.indexOf('=');
      if (k < 1) return null;
      var on = part.slice(0, k).trim();
      var vals = part.slice(k + 1).split('|').map(function (v) { return v.trim(); }).filter(Boolean);
      return on ? { on: on, value: vals.join('|') } : null;
    }).filter(Boolean);
    return any.length ? { on: any[0].on, value: any[0].value, any: any } : null;
  }
  function stageConditional(sections) {
    var mine = [], fieldsHere = {}, sectionsHere = {};
    (sections || []).forEach(function (s) {
      if (s.code) sectionsHere[s.code] = true;
      var r = ruleEntry(s.visible_when);
      if (r && s.code) {
        mine.push(Object.assign({ section: s.code,
                                  fields: (s.fields || []).map(function (f) { return f.field_name; }) }, r));
      }
      (s.fields || []).forEach(function (f) {
        fieldsHere[f.field_name] = true;
        var fr = ruleEntry(f.visible_when);
        if (fr) mine.push(Object.assign({ field: f.field_name }, fr));
      });
    });
    return mine.concat((schema.conditional || []).filter(function (r) {
      return r.section ? !sectionsHere[r.section] : !fieldsHere[r.field];
    }));
  }

  function buildForm(sections, operationLabel, values) {
    var root = A.qs('#wf-form');
    if (!root) return;
    form = window.FormEngine({
      root: root,
      schema: { sections: sections, lookups: schema.lookups,
                conditional: stageConditional(sections) },
      flat: true,
      /* The operation was settled at step zero and is not on this form, so it
         is handed to the engine as context — otherwise a rule keyed on it
         could not be judged and «علت خرابی» would hide itself. */
      context: Object.assign({}, (current && current.detail && current.detail.payload) || {},
                             { operation_kind: operationLabel }),
      /* the run this form belongs to: the electropump it assembled is the
         one its pumping test is about, unless another is picked */
      instanceId: current && current.detail ? current.detail.id : null,
      /* «مستند» fields upload straight into their slot of this process. */
      upload: async function (field, files) {
        var added = [];
        for (var i = 0; i < files.length; i++) {
          var body = new FormData();
          body.append('file', files[i]);
          body.append('stage_number', current.stage_number);
          body.append('field_name', field.field_name);
          var res = await A.request('/api/workflow/instances/' + current.id + '/attachments',
                                    { method: 'POST', body: body });
          added.push(res.data);
        }
        refreshAttachmentList();
        return added;
      },
      removeFile: async function (id) {
        await A.api.del('/api/workflow/attachments/' + id);
        refreshAttachmentList();
      },
      onWellPicked: fillPrevious,
      onChange: function (name) {
        if (name === 'required_action' || name === 'pump_type_now') {
          refreshStageForm();
        }
        var ap = current && current.detail && current.detail.approval_requests;
        if (ap && (ap.watch || []).indexOf(name) !== -1) refreshApproval();
        refreshDecisions();
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
    /* The rebuild can bring in a section that was not there before —
       «اطلاعات چاه و نصب» appears only once «اقدام مورد نیاز» is answered —
       and its «تاریخ نصب قبلی» has to be filled like everything else was. */
    if (current.detail.well) fillPrevious(current.detail.well);
    refreshDecisions();
  }, 250);

  /* What the reference databases know about this well — flow tests,
     production trend, videometry — loaded when the box is opened. */
  function resetRefPanel(well, stage) {
    var refWrap = A.qs('#wf-ref-wrap');
    if (!refWrap) return;
    refWrap.open = false;
    A.qs('#wf-ref').innerHTML = '';
    // the process builder decides, per stage, whether this box is shown
    var shown = !!well && !(stage && stage.show_refdata === false);
    refWrap.classList.toggle('hidden', !shown);
    refWrap.dataset.well = well || '';
    refWrap.dataset.loaded = '';
  }

  /* The «…قبلی» fields are read off the well's last operation. Whether that
     worked has to be visible: a well with no history looks exactly like a
     broken prefill, and the operator is left wondering which it was. */
  async function fillPrevious(wellName) {
    if (!wellName || !form) return;
    /* Which fields start from the well's history is the admin's setting in
       فرم‌ساز («پر شدن خودکار از سوابق همان چاه»), not a guess from how a
       field happens to be named. */
    var wanted = [];
    form.eachField(function (f) {
      if (f.prefill_from && !f.read_only) wanted.push(f.field_name);
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
        fill('#wf-prev-note', '<div class="alert warn">ℹ ' + (data.has_history
          ? 'در سوابق چاه «' + A.esc(wellName) + '» برای فیلدهای «قبلی» این فرم '
            + 'مقداری ثبت نشده است؛ آن‌ها را دستی وارد کنید.'
          : 'برای چاه «' + A.esc(wellName) + '» عملیات قبلی‌ای در سامانه ثبت نشده '
            + 'است، بنابراین فیلدهای «قبلی» خالی‌اند و باید دستی وارد شوند.')
          + '</div>');
        return;
      }
      /* Filled in, never locked: the operator can overwrite any of it. */
      form.setValues(values, { onlyEmpty: true, flash: true });
      var src = data.source || {};
      var refs = (data.refs || []).map(function (r) {
        return A.esc(r.title) + (r.date ? ' ' + A.esc(r.date) : '');
      });
      fill('#wf-prev-note', '<div class="alert info">✓ <b>' + filled.length + ' فیلد</b> خودکار پر شد'
        + (src.date ? ' — از سوابق این چاه (<b>' + A.esc(src.date) + '</b>'
            + (src.operation ? ' — ' + A.esc(src.operation) : '') + ')' : '')
        + (refs.length ? ' — از بانک‌های اطلاعاتی: ' + refs.join('، ') : '')
        + '. اگر درست نیست، همان‌جا ویرایش کنید.</div>');
    } catch (err) {
      fill('#wf-prev-note', '');
    }
  }

  /* ── «گزارش مرحله‌ی من»: each متولی's report of their own stage ───────── */
  function myReportBody() {
    var get = function (id) { return window.Jalali.toEnDigits((A.qs(id).value || '').trim()); };
    return { stage_id: Number(A.qs('#mr-stage').value), all_columns: true,
             date_from: get('#mr-from'), date_to: get('#mr-to'), mine_only: A.qs('#mr-mine').checked };
  }
  async function runMyReport() {
    if (!A.qs('#mr-stage').value) return;
    var box = A.qs('#mr-table');
    box.innerHTML = '<div class="loading">بارگذاری</div>';
    try {
      var res = await A.api.post('/api/workflow/stage-report', myReportBody());
      var d = res.data;
      A.qs('#mr-count').textContent = (window.Jalali ? window.Jalali.toFaDigits(d.rows.length) : d.rows.length) + ' ردیف';
      var cols = d.columns.filter(function (c) {
        return d.rows.some(function (r) { return r[c.key] !== '' && r[c.key] !== null && r[c.key] !== undefined; });
      });
      box.innerHTML = d.rows.length ? '<table><thead><tr>' + cols.map(function (c) {
        return '<th>' + A.esc(c.label) + '</th>';
      }).join('') + '</tr></thead><tbody>' + d.rows.map(function (r) {
        return '<tr>' + cols.map(function (c) {
          var v = r[c.key]; v = v === null || v === undefined ? '' : String(v);
          return '<td title="' + A.esc(v) + '">' + A.esc(v.length > 60 ? v.slice(0, 60) + '…' : v) + '</td>';
        }).join('') + '</tr>';
      }).join('') + '</tbody></table>' : '<div class="table-empty">در این بازه موردی ثبت نشده است.</div>';
    } catch (err) { box.innerHTML = '<div class="alert error">' + A.esc(err.message) + '</div>'; }
  }
  function setupMyReport() {
    var btn = A.qs('#btn-my-report');
    if (!btn) return;
    btn.addEventListener('click', async function () {
      var panel = A.qs('#my-report');
      panel.classList.toggle('hidden');
      if (panel.classList.contains('hidden') || A.qs('#mr-stage').options.length) return;
      A.qsa('#my-report .jdate').forEach(function (inp) { window.Jalali.attach(inp); });
      try {
        var res = await A.api.get('/api/workflow/my-stages');
        var stages = res.data.stages;
        if (!stages.length) {
          A.qs('#mr-table').innerHTML = '<div class="hint">شما متولی هیچ مرحله‌ای نیستید.</div>';
          return;
        }
        A.qs('#mr-stage').innerHTML = stages.map(function (st) {
          return '<option value="' + st.id + '">' + A.esc(st.workflow) + ' — مرحله ' + st.stage_number + ': '
            + A.esc(st.title) + ' (' + st.done + ')' + (st.mine ? ' ★' : '') + '</option>';
        }).join('');
        var mine = stages.find(function (st) { return st.mine; });
        if (mine) A.qs('#mr-stage').value = mine.id;
        runMyReport();
      } catch (err) { A.toast(err.message, 'error'); }
    });
    A.qs('#mr-close').addEventListener('click', function () { A.qs('#my-report').classList.add('hidden'); });
    A.qs('#mr-run').addEventListener('click', runMyReport);
    A.qs('#mr-stage').addEventListener('change', runMyReport);
    A.qsa('[data-mr-export]').forEach(function (b) {
      b.addEventListener('click', function () {
        A.downloadPost('/api/workflow/stage-report/export.' + b.dataset.mrExport, myReportBody());
      });
    });
  }

  async function submitStage() {
    if (!current) return;
    var button = A.qs('#wf-submit');
    /* «موجودی کافی نیست»: the stock alarm is a warning, not a block — the
       count may not be up to date — so the owner confirms knowingly */
    /* what the warehouse will not let go: an electropump without its
       pumping test does not leave for install — said here, before sending */
    var blocked = form && form.blockers ? form.blockers() : [];
    if (blocked.length && chosenAction().kind === 'forward') {
      fill('#inbox-alert', '<div class="alert error">⛔ ' + blocked.map(A.esc).join('<br>⛔ ') + '</div>');
      A.toast(blocked[0], 'error');
      return;
    }
    var alerts = form && form.stockAlerts ? form.stockAlerts() : [];
    if (alerts.length && !window.confirm('⚠ ' + alerts.join('\n⚠ ') + '\n\nبا وجود این هشدارها مرحله ثبت شود؟')) return;
    button.disabled = true;
    form.clearErrors();
    try {
      var refer = (current.detail && current.detail.referral) || {};
      var decision = chosenAction();
      if (decision.kind !== 'forward') {
        var why = A.qs('#wf-decision-note').value.trim();
        var err = A.qs('#wf-decision-err');
        if (decision.picks && !decision.target) {
          err.textContent = 'به کدام مرحله برگردد؟ مرحله را انتخاب کنید.';
          err.classList.remove('hidden');
          button.disabled = false;
          return;
        }
        if (!why) {
          err.textContent = 'توضیح این تصمیم را بنویسید.'; err.classList.remove('hidden');
          A.qs('#wf-decision-note').focus();
          button.disabled = false;
          return;
        }
        err.classList.add('hidden');
        var go = await A.confirmDialog({
          title: decision.kind === 'stop' ? 'توقف فرایند' : 'برگشت برای تکمیل',
          message: decision.kind === 'stop'
            ? 'فرایند همین‌جا بسته می‌شود و به مرحله‌های بعد نمی‌رود. مطمئن هستید؟'
            : 'کار به مرحله‌ی انتخاب‌شده برمی‌گردد و این مرحله منتظر پاسخ می‌ماند.',
          confirmText: decision.kind === 'stop' ? 'توقف' : 'برگشت',
          danger: decision.kind === 'stop' });
        if (!go) { button.disabled = false; return; }
        var r2 = await A.api.post('/api/workflow/instances/' + current.id + '/submit',
          { stage_number: current.stage_number, action: decision.id, note: why,
            target_stage: decision.target, data: form.collect() });
        A.toast(r2.message || 'انجام شد.', 'success');
        A.qs('#wf-detail').classList.add('hidden');
        current = null;
        await loadInbox();
        return;
      }
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


  /* ── «ارجاع برای تأیید» ─────────────────────────────────────────────── */
  var STATE = {
    not_sent: ['muted', 'ارسال نشده'], pending: ['warn', 'در انتظار تأیید'],
    approved: ['ok', 'تأیید شد'], rejected: ['danger', 'تأیید نشد'],
    changed: ['warn', 'پس از تأیید تغییر کرده']
  };
  var areqRule = null;
  function renderApprovalPanel(detail) {
    var box = A.qs('#wf-approval-box');
    if (!box) return;
    var ap = detail.approval_requests;
    if (!ap || !detail.may_act || (!(ap.required || []).length && !ap.enabled
        && !(ap.history || []).length)) { box.classList.add('hidden'); box.innerHTML = ''; return; }
    var html = '<div class="section-title"><span>📝</span><span>ارجاع‌ها</span></div>';
    var must = (ap.required || []).filter(function (r) { return r.required; });
    var info = (ap.required || []).filter(function (r) { return !r.required; });
    function ruleLi(r, verb) {
      var st = STATE[r.state] || STATE.not_sent;
      var action = (r.state === 'approved' || r.state === 'pending') ? ''
        : '<button class="btn-sm btn-ghost" type="button" data-areq-rule="' + A.esc(String(r.item_id)) + '"'
          + ' data-areq-approver="' + A.esc(r.approver_name || '') + '">📤 ' + verb + '</button>';
      return '<li><b>' + A.esc(r.title) + '</b> ← ' + A.esc(r.approver_name || '—')
        + ' <span class="badge ' + st[0] + '">' + st[1] + '</span> ' + action + '</li>';
    }
    if (info.length) {
      html += '<div class="hint">با ثبت این مرحله، این موارد خودکار <b>برای اطلاع</b> افراد زیر فرستاده می‌شود؛ '
        + 'منتظر پاسخ آن‌ها نمی‌مانید و کار به مرحله‌ی بعد می‌رود (اگر بخواهید، همین حالا هم با توضیح و مستند بفرستید):</div>'
        + '<ul class="areq-required">' + info.map(function (r) { return ruleLi(r, 'ارسال همین حالا'); }).join('') + '</ul>';
    }
    if (must.length) {
      html += '<div class="hint">این موارد <b>الزامی</b> است و پیش از ثبت نهایی مرحله باید به تأیید برسد:</div>'
        + '<ul class="areq-required">' + must.map(function (r) { return ruleLi(r, 'ارسال برای تأیید'); }).join('') + '</ul>';
    }
    if (ap.enabled) {
      html += '<button class="btn-ghost btn-sm" type="button" id="areq-open">📝 ارجاع برای تأیید (با ضمیمه‌ی فرم‌ها، توضیحات و مستندات)</button>';
    }
    if ((ap.history || []).length) {
      html += '<div class="areq-history"><div class="pal-group-title">سابقه‌ی درخواست‌های تأیید این مرحله</div>'
        + ap.history.map(function (r) {
          var cls = { approved: 'ok', rejected: 'danger', pending: 'warn' }[r.status] || 'muted';
          return '<div class="areq-row"><span class="badge ' + cls + '">' + A.esc(r.status_label) + '</span> '
            + '<b>' + A.esc(r.approver_name || '') + '</b> · ' + A.esc(r.created_at_j || '')
            + (r.note ? '<div class="hint">توضیح شما: ' + A.esc(r.note) + '</div>' : '')
            + (r.answer && r.answer.value ? '<div class="areq-answer">' + A.esc(r.answer.label) + ': <b>' + A.esc(r.answer.value) + '</b></div>' : '')
            + (r.decision_note ? '<div class="areq-answer">پاسخ: ' + A.esc(r.decision_note) + '</div>' : '')
            + ' <button class="btn-sm btn-ghost" type="button" data-areq-view="' + r.id + '">جزئیات</button>'
            + (r.status === 'pending' ? ' <button class="btn-sm btn-ghost" type="button" data-areq-cancel="' + r.id + '">لغو</button>' : '')
            + '</div>';
        }).join('') + '</div>';
    }
    var pending = must.some(function (r) { return r.state === 'pending'; });
    if (pending) html += '<div class="alert warn">تا پاسخ تأییدِ الزامی نیاید، ثبت نهایی این مرحله ممکن نیست.</div>';
    box.innerHTML = html;
    box.classList.remove('hidden');
  }

  /* An answer that needs «تأیید گزینه» was picked or changed: the server
     recomputes the panel with the answers on the page (nothing is saved). */
  var refreshApproval = A.debounce(async function () {
    if (!current || !form) return;
    try {
      var res = await A.api.post('/api/workflow/instances/' + current.id + '/approval-status',
        { stage_number: current.stage_number, draft: form.collect() });
      current.detail.approval_requests = res.data;
      renderApprovalPanel(current.detail);
    } catch (err) { /* the submit check still says what is missing */ }
  }, 400);

  async function openRequestModal(ruleId, ruleApprover) {
    if (!current) return;
    areqRule = ruleId || null;
    var ap = current.detail.approval_requests || {};
    var sel = A.qs('#areq-approver');
    sel.innerHTML = '';
    if (areqRule) {
      sel.appendChild(A.el('option', { value: '', text: ruleApprover || 'تأییدکننده‌ی تعیین‌شده' }));
      sel.disabled = true;
    } else {
      sel.disabled = false;
      sel.appendChild(A.el('option', { value: '', text: '— انتخاب کنید —' }));
      (ap.approvers || []).forEach(function (u) { sel.appendChild(A.el('option', { value: u.id, text: u.name })); });
    }
    A.qs('#areq-note').value = '';
    A.qs('#areq-files').value = '';
    var box = A.qs('#areq-blocks');
    box.innerHTML = '<div class="loading">در حال بارگذاری</div>';
    A.openModal('areq-modal');
    try {
      var res = await A.api.post('/api/workflow/instances/' + current.id + '/approval-blocks',
        { stage_number: current.stage_number, draft: form ? form.collect() : {} });
      var rule = areqRule ? (ap.required || []).filter(function (r) { return String(r.item_id) === String(areqRule); })[0] : null;
      var lastStage = null;
      box.innerHTML = res.data.map(function (b) {
        var head = '';
        if (b.stage_number !== lastStage) {
          lastStage = b.stage_number;
          head = '<div class="pal-group-title">مرحله ' + J.toFaDigits(b.stage_number) + ' — ' + A.esc(b.stage_title)
            + (b.current ? ' (مرحله‌ی شما)' : '') + '</div>';
        }
        var forced = rule && rule.key === b.key;
        var on = forced || (b.current && b.filled > 0 && !areqRule);
        return head + '<label class="mini-check areq-block"><input type="checkbox" value="' + A.esc(b.key) + '"'
          + (on ? ' checked' : '') + (forced ? ' disabled' : '') + '> ' + A.esc(b.title)
          + ' <span class="hint">(' + J.toFaDigits(b.filled) + ' از ' + J.toFaDigits(b.total) + ' فیلد پر شده)</span></label>';
      }).join('') || '<div class="hint">فرم پرشده‌ای برای ضمیمه نیست.</div>';
    } catch (err) { box.innerHTML = '<div class="alert error">' + A.esc(err.message) + '</div>'; }
  }

  async function sendRequest() {
    var keys = A.qsa('#areq-blocks input:checked').map(function (c) { return c.value; });
    var btn = A.qs('#areq-send');
    btn.disabled = true;
    try {
      var res = await A.api.post('/api/workflow/instances/' + current.id + '/approval-requests', {
        stage_number: current.stage_number, approver_id: A.qs('#areq-approver').value || null,
        keys: keys, note: A.qs('#areq-note').value, draft: form ? form.collect() : {},
        rule_item_id: areqRule });
      var files = A.qs('#areq-files').files;
      for (var i = 0; i < files.length; i++) {
        var body = new FormData();
        body.append('file', files[i]);
        body.append('stage_number', current.stage_number);
        body.append('approval_request_id', res.data.id);
        await A.request('/api/workflow/instances/' + current.id + '/attachments', { method: 'POST', body: body });
      }
      A.closeModal('areq-modal');
      A.toast(res.message || 'ارسال شد.', 'success');
      await openStage({ id: current.id, stage_number: current.stage_number });
    } catch (err) { A.toast(err.message, 'error'); }
    btn.disabled = false;
  }

  var viewing = null;
  async function openRequestView(id, asApprover) {
    try {
      var res = await A.api.get('/api/workflow/approval-requests/' + id);
      var r = viewing = res.data;
      A.qs('#areq-view-title').textContent = 'درخواست تأیید — مرحله ' + J.toFaDigits(r.stage_number) + ' «' + (r.stage_title || '') + '»';
      var html = '<dl class="kv"><dt>فرایند</dt><dd>#' + J.toFaDigits(r.instance_id) + ' — ' + A.esc(r.process || '') + '</dd>'
        + '<dt>چاه</dt><dd>' + A.esc(r.well || '—') + '</dd>'
        + '<dt>فرستنده</dt><dd>' + A.esc(r.requester_name || '') + ' · ' + A.esc(r.created_at_j || '') + '</dd>'
        + '<dt>تأییدکننده</dt><dd>' + A.esc(r.approver_name || '') + '</dd>'
        + '<dt>وضعیت</dt><dd>' + A.esc(r.status_label) + (r.decision_note ? ' — ' + A.esc(r.decision_note) : '') + '</dd></dl>';
      if (r.note) html += '<div class="alert info"><b>توضیحات فرستنده:</b> ' + A.esc(r.note) + '</div>';
      var snapGroups = (r.snapshot || []).map(function (sec) {
        return { code: sec.code, title: sec.title, values: sec.values || [] };
      });
      if (snapGroups.length > 1 && snapGroups.some(function (g, k) { return k && sumAlike(snapGroups[k - 1], g); })) {
        html += sumGroupsHtml(snapGroups.filter(function (g) { return g.values.length; }));
      } else (r.snapshot || []).forEach(function (sec) {
        html += '<div class="areq-sec"><div class="section-title">📋 ' + A.esc(sec.title)
          + ' <span class="hint">— مرحله ' + J.toFaDigits(sec.stage_number) + ' «' + A.esc(sec.stage_title) + '»</span></div>'
          + (sec.values.length ? '<dl class="sum-values">' + sec.values.map(function (v) {
              var val = v.files && v.files.length
                ? v.files.map(function (a) { return '<a href="' + A.esc(a.url) + '" target="_blank">📄 ' + A.esc(a.filename) + '</a>'; }).join(' ')
                : A.esc(v.value);
              return '<dt>' + A.esc(v.label) + '</dt><dd>' + val + '</dd>';
            }).join('') + '</dl>' : '<div class="hint">این فرم هنوز خالی بود.</div>') + '</div>';
      });
      if ((r.attachments || []).length) {
        html += '<div class="section-title">📎 مستندات پیوست</div><div class="doc-list">' + r.attachments.map(function (a) {
          return '<div class="doc-row"><a href="' + A.esc(a.url) + '" target="_blank" class="doc-name">📄 ' + A.esc(a.filename)
            + '</a><span class="doc-meta">' + A.esc(a.size_label || '') + ' · ' + A.esc(a.uploaded_by_name || '') + '</span></div>';
        }).join('') + '</div>';
      }
      var mayDecide = r.status === 'pending' && asApprover;
      /* «پاسخ تأییدکننده»: approving also says which way the work goes on. */
      if (r.answer && r.answer.value) {
        html += '<div class="alert ok"><b>' + A.esc(r.answer.label) + ':</b> ' + A.esc(r.answer.value) + '</div>';
      }
      if (mayDecide && r.answer) {
        html += '<div class="field mt-2 areq-answer-box"><label>' + A.esc(r.answer.label)
          + ' <span class="hint">(برای «تأیید» یکی را انتخاب کنید)</span></label><div class="btn-group">'
          + (r.answer.choices || []).map(function (c) {
              return '<label><input type="radio" name="areq-answer" value="' + A.esc(c) + '"><span class="btn-opt">'
                + A.esc(c) + '</span></label>';
            }).join('') + '</div></div>';
      }
      if (mayDecide) {
        html += '<div class="field mt-2"><label>نظر شما <span class="hint">(برای «تأیید نمی‌شود» الزامی است)</span></label>'
          + '<textarea id="areq-decision-note" rows="2"></textarea></div>'
          + '<div class="field"><label>مستند پاسخ <span class="hint">(اختیاری)</span></label><input type="file" id="areq-decision-files" multiple></div>';
      }
      A.qs('#areq-view-body').innerHTML = html;
      A.qs('#areq-approve').classList.toggle('hidden', !mayDecide);
      A.qs('#areq-reject').classList.toggle('hidden', !mayDecide);
      A.openModal('areq-view-modal');
    } catch (err) { A.toast(err.message, 'error'); }
  }

  async function decideRequest(approved) {
    if (!viewing) return;
    var picked = A.qs('input[name="areq-answer"]:checked');
    if (approved && viewing.answer && !picked) {
      A.toast('برای تأیید، «' + viewing.answer.label + '» را انتخاب کنید.', 'error');
      return;
    }
    try {
      var files = (A.qs('#areq-decision-files') || {}).files || [];
      for (var i = 0; i < files.length; i++) {
        var body = new FormData();
        body.append('file', files[i]);
        body.append('stage_number', viewing.stage_number);
        body.append('approval_request_id', viewing.id);
        await A.request('/api/workflow/instances/' + viewing.instance_id + '/attachments', { method: 'POST', body: body });
      }
      var res = await A.api.post('/api/workflow/approval-requests/' + viewing.id + '/decide',
        { approved: approved, note: (A.qs('#areq-decision-note') || {}).value || '',
          answer: picked ? picked.value : null });
      A.closeModal('areq-view-modal');
      A.toast(res.message || 'ثبت شد.', 'success');
      await loadInbox();
    } catch (err) { A.toast(err.message, 'error'); }
  }

  async function refreshAttachmentList() {
    if (!current) return;
    try {
      var res = await A.api.get('/api/workflow/instances/' + current.id
                                + '?stage=' + current.stage_number);
      renderAttachments(res.data);
      renderDocsOwed(res.data);
    } catch (err) { /* the list refreshes on the next open */ }
  }

  async function uploadFiles(files) {
    if (!current || !files.length) return;
    for (var i = 0; i < files.length; i++) {
      var body = new FormData();
      body.append('file', files[i]);
      body.append('stage_number', current.stage_number);
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
    renderDocsOwed(res.data);
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

    A.qs('#inbox-items').addEventListener('click', async function (ev) {
      var areq = ev.target.closest('[data-areq]');
      if (areq) { openRequestView(Number(areq.dataset.areq), true); return; }
      var ares = ev.target.closest('[data-ares]');
      if (ares) {
        try { await A.api.post('/api/workflow/approval-requests/' + ares.dataset.ares + '/seen', {}); } catch (e) { /* ok */ }
        await openStage({ id: Number(ares.dataset.inst), stage_number: Number(ares.dataset.stage) });
        loadInbox();
        return;
      }
      if (ev.target.closest('[data-start]')) {
        renderKinds(); A.openModal('new-process-modal'); return;
      }
      var button = ev.target.closest('[data-i]');
      if (button) openStage(items[Number(button.dataset.i)]);
    });
    A.qs('#btn-refresh').addEventListener('click', function () { loadInbox(); loadBoard(); });
    loadBoard();
    ['#wb-days', '#wb-stage'].forEach(function (sel) {
      var el = A.qs(sel); if (el) el.addEventListener('change', loadBoard);
    });
    var wq = A.qs('#wb-q'); if (wq) wq.addEventListener('input', renderBoard);
    var wp = A.qs('#wb-pick');
    if (wp) wp.addEventListener('change', function () {
      if (!wp.value) return;
      var parts = wp.value.split('|');
      openStage({ id: Number(parts[0]), stage_number: Number(parts[1]) });
      var d = A.qs('#wf-detail'); if (d) d.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
    document.addEventListener('click', function (ev) {
      var chip = ev.target.closest('[data-wb-inst]');
      if (!chip) return;
      openStage({ id: Number(chip.dataset.wbInst), stage_number: Number(chip.dataset.wbStage) });
      var d = A.qs('#wf-detail'); if (d) d.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
    var decisionBox = A.qs('#wf-decision-options');
    if (decisionBox) decisionBox.addEventListener('change', function (ev) {
      // Picking a stage to go back to is choosing that decision.
      if (ev.target.classList.contains('d-target')) {
        ev.target.closest('.decision-opt').querySelector('input[type=radio]').checked = true;
      }
      decisionChanged();
    });
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
    A.qs('#wf-approval-box').addEventListener('click', async function (ev) {
      if (ev.target.closest('#areq-open')) { openRequestModal(null); return; }
      var rule = ev.target.closest('[data-areq-rule]');
      if (rule) { openRequestModal(rule.dataset.areqRule, rule.dataset.areqApprover); return; }
      var view = ev.target.closest('[data-areq-view]');
      if (view) { openRequestView(Number(view.dataset.areqView), false); return; }
      var cancel = ev.target.closest('[data-areq-cancel]');
      if (cancel) {
        if (!(await A.confirmDialog({ message: 'درخواست تأیید لغو شود؟' }))) return;
        try {
          await A.api.post('/api/workflow/approval-requests/' + cancel.dataset.areqCancel + '/cancel', {});
          await openStage({ id: current.id, stage_number: current.stage_number });
        } catch (err) { A.toast(err.message, 'error'); }
      }
    });
    A.qs('#areq-send').addEventListener('click', sendRequest);
    A.qs('#areq-approve').addEventListener('click', function () { decideRequest(true); });
    A.qs('#areq-reject').addEventListener('click', function () { decideRequest(false); });
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
        renderDocsOwed(res.data);
      } catch (err) { A.toast(err.message, 'error'); }
    });
    A.qs('#np-start').addEventListener('click', startProcess);
    setupMyReport();
    var refWrap = A.qs('#wf-ref-wrap');
    if (refWrap && window.RefPanel) {
      refWrap.addEventListener('toggle', function () {
        if (!refWrap.open || refWrap.dataset.loaded || !refWrap.dataset.well) return;
        refWrap.dataset.loaded = '1';
        window.RefPanel.load(A.qs('#wf-ref'), refWrap.dataset.well, { compact: true });
      });
    }
    /* The well picker in the dialog is the same autocomplete the forms use,
       so the process starts against a canonical well from the register. */
    window.FormEngine.attachAutocomplete(A.qs('#np-well'), schema.lookups);
  });
})();
