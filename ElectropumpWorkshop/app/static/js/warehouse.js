/* انبار تجهیزات و قطعات: the manager's report, stock, the ledger, manual
   entries and the item catalogue. */
(function () {
  'use strict';
  var A = window.App;
  var cat = null;
  var MANAGE = false;
  function fa(v) { return window.Jalali ? window.Jalali.toFaDigits(v) : String(v); }
  function q(v) { return v === null || v === undefined ? '—' : fa(Math.round(Number(v) * 1000) / 1000); }

  function filters() {
    var get = function (id) { return (A.qs(id).value || '').trim(); };
    var p = { date_from: get('#wh-from'), date_to: get('#wh-to'), warehouse: get('#wh-wh'),
              condition: get('#wh-cond'), well: get('#wh-well') };
    return Object.keys(p).filter(function (k) { return p[k]; })
      .map(function (k) { return k + '=' + encodeURIComponent(window.Jalali.toEnDigits(p[k])); }).join('&');
  }
  function current() { var t = A.qs('#wh-tabs .tab.active'); return t ? t.dataset.tab : 'report'; }

  function switchTab(name) {
    A.qsa('#wh-tabs .tab').forEach(function (t) { t.classList.toggle('active', t.dataset.tab === name); });
    A.qsa('.tab-panel').forEach(function (p) { p.classList.toggle('hidden', p.dataset.panel !== name); });
    A.qs('.wh-filters').classList.toggle('hidden', name === 'new' || name === 'items');
    refresh();
  }

  function refresh() {
    var f = filters();
    ['summary', 'stock', 'moves'].forEach(function (w) {
      var a = A.qs('#wh-x-' + w);
      if (a) a.href = '/api/warehouse/export/' + (w === 'moves' ? 'movements' : w) + '.xlsx' + (f ? '?' + f : '');
    });
    var tab = current();
    if (tab === 'report') loadReport(f);
    else if (tab === 'stock') loadStock(f);
    else if (tab === 'moves') loadMoves(f);
    else if (tab === 'items') loadItems();
  }

  function simpleTable(rows, cols) {
    if (!rows.length) return '<div class="chart-empty">در این بازه گردشی ثبت نشده است.</div>';
    return '<div class="table-scroll" style="max-height:420px"><table><thead><tr>' + cols.map(function (c) {
      return '<th>' + c[1] + '</th>';
    }).join('') + '</tr></thead><tbody>' + rows.map(function (r) {
      return '<tr>' + cols.map(function (c) {
        return '<td>' + (c[0] === 'qty' ? q(r.qty) : A.esc(r[c[0]] == null ? '—' : String(r[c[0]]))) + '</td>';
      }).join('') + '</tr>';
    }).join('') + '</tbody></table></div>';
  }

  async function loadReport(f) {
    var s = (await A.api.get('/api/warehouse/summary' + (f ? '?' + f : ''))).data;
    var h = s.headline;
    var cards = [['🔧', h.electropumps_pulled, 'الکتروپمپ کشیده‌شده و تحویل انبار'],
                 ['🛠', h.electropumps_assembled, 'الکتروپمپ مونتاژشده (ساخت)'],
                 ['🚚', h.electropumps_installed, 'الکتروپمپ خارج‌شده برای نصب'],
                 ['♻', h.parts_reused, 'مصرف اقلام قابل استفاده مجدد'],
                 ['🆕', h.parts_new, 'مصرف اقلام نو (خریداری‌شده)'],
                 ['🗑', h.parts_scrapped, 'اقلام اسقاط']];
    A.qs('#wh-head').innerHTML = cards.map(function (c) {
      return '<div class="stat-card"><div class="stat-icon">' + c[0] + '</div><div class="stat-info"><h3>'
        + q(c[1]) + '</h3><p>' + c[2] + '</p></div></div>';
    }).join('');
    A.qs('#wh-by-reason').innerHTML = simpleTable(s.by_reason, [['warehouse', 'انبار'], ['direction', 'ورود/خروج'], ['reason', 'علت'], ['qty', 'مقدار']]);
    A.qs('#wh-by-cond').innerHTML = simpleTable(s.by_condition, [['warehouse', 'انبار'], ['direction', 'ورود/خروج'], ['condition', 'وضعیت'], ['qty', 'مقدار']]);
    A.qs('#wh-by-item').innerHTML = simpleTable(s.by_item, [['warehouse', 'انبار'], ['item', 'کالا'], ['condition', 'وضعیت'], ['direction', 'ورود/خروج'], ['qty', 'مقدار']]);
    partsReport(s.parts || {});
  }

  /* قطعات: installed new / used, collected, reusable and scrapped — per
     equipment kind, per year and per part (the 25 most used on screen; the
     Excel of this report carries every part). */
  function partsReport(p) {
    var t = p.total || {};
    var cards = [['🆕', t.installed_new, 'قطعه‌ی نو نصب‌شده'],
                 ['♻', t.installed_repair, 'قطعه‌ی کهنه (قابل استفاده مجدد) نصب‌شده'],
                 ['📦', (t.reusable || 0) + (t.scrap || 0) + (t.collected || 0), 'قطعه‌ی جمع‌آوری‌شده'],
                 ['✅', t.reusable, 'قابل استفاده مجدد'],
                 ['🗑', t.scrap, 'اسقاط'],
                 ['⚙', t.equipments, 'الکتروموتور و پمپ (کد تجهیز)']];
    A.qs('#wh-parts-head').innerHTML = cards.map(function (c) {
      return '<div class="stat-card"><div class="stat-icon">' + c[0] + '</div><div class="stat-info"><h3>'
        + q(c[1] || 0) + '</h3><p>' + c[2] + '</p></div></div>';
    }).join('');
    var table = function (rows, cols, max) {
      if (!rows || !rows.length) return '<div class="chart-empty">در این بازه قطعه‌ای ثبت نشده است.</div>';
      return '<div class="table-scroll" style="max-height:' + (max || 360) + 'px"><table class="rp-table"><thead><tr>'
        + cols.map(function (c) { return '<th>' + c[1] + '</th>'; }).join('') + '</tr></thead><tbody>'
        + rows.map(function (r) {
          return '<tr>' + cols.map(function (c) {
            var v = r[c[0]];
            return '<td' + (c[2] ? ' dir="ltr"' : '') + '>' + (typeof v === 'number' ? q(v) : A.esc(v == null || v === '' ? '—' : String(v))) + '</td>';
          }).join('') + '</tr>';
        }).join('') + '</tbody></table></div>';
    };
    A.qs('#wh-parts-kind').innerHTML = table(p.by_kind, [['equipment_kind', 'تجهیز'], ['installed', 'نصب'],
      ['collected', 'جمع‌آوری (ارزیابی‌نشده)'], ['reusable', 'قابل استفاده مجدد'], ['scrap', 'اسقاط']]);
    A.qs('#wh-parts-year').innerHTML = table((p.by_year || []).slice().reverse(), [['year', 'سال', true], ['installed', 'نصب'],
      ['new', 'نصب نو'], ['repair', 'نصب کهنه'], ['reusable', 'قابل استفاده مجدد'], ['scrap', 'اسقاط']]);
    var parts = p.by_part || [];
    A.qs('#wh-parts-count').textContent = parts.length > 25 ? '(۲۵ قطعه‌ی پرمصرف از ' + fa(parts.length) + ' — همه در اکسل)' : '';
    A.qs('#wh-parts-part').innerHTML = table(parts.slice(0, 25), [['equipment_kind', 'تجهیز'], ['part_code', 'کد انباری', true],
      ['part_name', 'شرح قطعه'], ['installed_new', 'نصب نو'], ['installed_repair', 'نصب کهنه'],
      ['installed_unknown', 'نصب بی‌وضعیت'], ['collected', 'جمع‌آوری'], ['reusable', 'قابل استفاده مجدد'], ['scrap', 'اسقاط']], 520);
  }

  async function loadStock(f) {
    var rows = (await A.api.get('/api/warehouse/stock' + (f ? '?' + f : ''))).data.rows;
    A.qs('#wh-stock').innerHTML = rows.length ? rows.map(function (r) {
      return '<tr><td>' + A.esc(r.warehouse_label) + '</td><td>' + A.esc(r.item_name) + '</td><td>' + A.esc(r.condition_label)
        + '</td><td>' + q(r.in) + '</td><td>' + q(r.out) + '</td><td><b' + (r.balance < 0 ? ' style="color:var(--danger)"' : '') + '>'
        + q(r.balance) + '</b></td><td>' + A.esc(r.unit || '') + '</td></tr>';
    }).join('') : '<tr><td colspan="7" class="table-empty">موجودی‌ای ثبت نشده است.</td></tr>';
  }

  async function loadMoves(f) {
    var rows = (await A.api.get('/api/warehouse/movements' + (f ? '?' + f : ''))).data.rows;
    var conds = {}; (cat.conditions || []).forEach(function (c) { conds[c.code] = c.label; });
    A.qs('#wh-mcount').textContent = fa(rows.length);
    A.qs('#wh-moves').innerHTML = rows.length ? rows.map(function (r) {
      return '<tr><td>' + A.esc(r.jdate) + '</td><td>' + A.esc(r.warehouse_label) + '</td><td>'
        + (r.direction === 'in' ? '📥 ' : '📤 ') + A.esc(r.direction_label) + '</td><td>' + A.esc(r.reason_label) + '</td>'
        + '<td>' + A.esc(r.item_name) + '</td><td dir="ltr">' + A.esc(r.spec || '') + '</td><td dir="ltr">' + A.esc(r.serial || '') + '</td>'
        + '<td>' + A.esc(conds[r.condition] || r.condition || '—') + '</td><td>' + q(r.qty) + '</td>'
        + '<td>' + A.esc(r.well_name || '') + '</td><td>' + A.esc(r.stage_title || 'ثبت دستی') + '</td>'
        + '<td>' + A.esc(r.user_name || '') + '</td><td>'
        + (MANAGE && !r.instance_id ? '<button type="button" class="btn-sm btn-del" data-del="' + r.id + '">✕</button>' : '') + '</td></tr>';
    }).join('') : '<tr><td colspan="13" class="table-empty">گردشی ثبت نشده است.</td></tr>';
  }

  async function loadItems() {
    var items = (await A.api.get('/api/warehouse/items')).data.items;
    A.qs('#it-body').innerHTML = items.map(function (i) {
      return '<tr' + (i.is_active ? '' : ' class="inactive"') + '><td dir="ltr">' + A.esc(i.code || '') + '</td><td>' + A.esc(i.name) + '</td>'
        + '<td>' + (i.kind === 'equipment' ? 'تجهیز' : 'قطعه') + '</td><td>' + A.esc(i.category || '') + '</td>'
        + '<td>' + A.esc(i.unit || '') + '</td><td>' + (i.is_active ? '✓' : '—') + '</td><td>' + A.esc(i.source || '') + '</td>'
        + '<td>' + (MANAGE ? '<button type="button" class="btn-sm btn-ghost" data-edit="' + i.id + '">✎</button>' : '') + '</td></tr>';
    }).join('');
    A.qs('#cond-list').innerHTML = (cat.conditions || []).map(function (c) {
      return '<span class="badge" style="background:' + (c.color || '#eef2f5') + '22;color:' + (c.color || '#555') + '">' + A.esc(c.label) + '</span>';
    }).join(' ');
    A.qs('#it-body').onclick = function (e) {
      var b = e.target.closest('[data-edit]');
      if (b) editItem(items.find(function (i) { return String(i.id) === b.dataset.edit; }));
    };
  }

  async function editItem(item) {
    item = item || { kind: 'part', unit: 'عدد', is_active: true };
    var name = window.prompt('نام کالا:', item.name || ''); if (name === null || !name.trim()) return;
    var code = window.prompt('کد کالا (اختیاری):', item.code || ''); if (code === null) return;
    var kind = window.confirm('این کالا «تجهیز» است (الکتروموتور / پمپ / الکتروپمپ)؟\nتأیید = تجهیز، انصراف = قطعه') ? 'equipment' : 'part';
    var unit = window.prompt('واحد:', item.unit || 'عدد'); if (unit === null) return;
    var category = window.prompt('گروه (اختیاری):', item.category || ''); if (category === null) return;
    try {
      var res = await A.api.post('/api/warehouse/items', { id: item.id, name: name, code: code, kind: kind,
                                                           unit: unit, category: category, is_active: true });
      A.toast(res.message, 'success');
      await loadCat(); loadItems();
    } catch (err) { A.toast(err.message, 'error'); }
  }

  async function loadCat() {
    cat = (await A.api.get('/api/warehouse/catalogue')).data;
    var condOpts = cat.conditions.map(function (c) { return '<option value="' + c.code + '">' + A.esc(c.label) + '</option>'; }).join('');
    A.qs('#wh-cond').innerHTML = '<option value="">همه</option>' + condOpts;
    A.qs('#nm-cond').innerHTML = '<option value="">—</option>' + condOpts;
    A.qs('#nm-reason').innerHTML = Object.keys(cat.reasons).map(function (k) {
      return '<option value="' + k + '"' + (k === 'purchase' ? ' selected' : '') + '>' + A.esc(cat.reasons[k]) + '</option>';
    }).join('');
    A.qs('#nm-item').innerHTML = cat.items.map(function (i) {
      return '<option value="' + i.id + '">' + A.esc(i.name) + ' — ' + (i.kind === 'equipment' ? 'تجهیز' : 'قطعه') + '</option>';
    }).join('');
  }

  document.addEventListener('DOMContentLoaded', async function () {
    MANAGE = window.IS_ADMIN || (window.CAN || []).indexOf('warehouse.manage') !== -1;
    if (!MANAGE) {
      A.qsa('.wh-manage').forEach(function (el) { el.classList.add('hidden'); });
      var t = A.qs('#wh-tabs [data-tab="new"]'); if (t) t.classList.add('hidden');
    }
    A.qsa('.jdate').forEach(function (inp) { window.Jalali.attach(inp); });
    var t = window.Jalali.today();
    A.qs('#nm-date').value = t[0] + '/' + String(t[1]).padStart(2, '0') + '/' + String(t[2]).padStart(2, '0');
    await loadCat();
    A.qsa('#wh-tabs .tab').forEach(function (t) { t.addEventListener('click', function () { switchTab(t.dataset.tab); }); });
    ['#wh-from', '#wh-to', '#wh-wh', '#wh-cond'].forEach(function (id) { A.qs(id).addEventListener('change', refresh); });
    A.qs('#wh-well').addEventListener('input', A.debounce(refresh, 400));
    A.qs('#wh-moves').addEventListener('click', async function (e) {
      var b = e.target.closest('[data-del]');
      if (!b || !window.confirm('این ردیف حذف شود؟')) return;
      try { await A.api.del('/api/warehouse/movements/' + b.dataset.del); refresh(); }
      catch (err) { A.toast(err.message, 'error'); }
    });
    A.qs('#nm-save').addEventListener('click', async function () {
      var get = function (id) { return A.qs(id).value.trim(); };
      try {
        var res = await A.api.post('/api/warehouse/movements', {
          jdate: window.Jalali.toEnDigits(get('#nm-date')), warehouse: get('#nm-wh'), direction: get('#nm-dir'),
          reason: get('#nm-reason'), item_id: get('#nm-item'), condition: get('#nm-cond'),
          qty: window.Jalali.toEnDigits(get('#nm-qty')), spec: get('#nm-spec'), serial: get('#nm-serial'),
          well: get('#nm-well'), note: get('#nm-note') });
        A.toast(res.message, 'success');
        A.qs('#nm-qty').value = '1'; A.qs('#nm-spec').value = ''; A.qs('#nm-serial').value = ''; A.qs('#nm-note').value = '';
      } catch (err) { A.toast(err.message, 'error'); }
    });
    var add = A.qs('#it-add'); if (add) add.addEventListener('click', function () { editItem(null); });
    var imp = A.qs('#it-import');
    if (imp) imp.addEventListener('change', async function () {
      if (!this.files[0]) return;
      var form = new FormData(); form.append('file', this.files[0]);
      try {
        var res = await A.api.upload('/api/warehouse/items/import', form);
        A.toast('اقلام: ' + fa(res.data.added) + ' جدید، ' + fa(res.data.updated) + ' به‌روز', 'success');
        await loadCat(); loadItems();
      } catch (err) { A.toast(err.message, 'error'); }
      this.value = '';
    });
    refresh();
  });
})();
