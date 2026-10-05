/* ==========================================================================
   The form engine shared by the data-entry page and the process کارتابل.

   Both draw the same fields from the same form-builder schema; only the shape
   of what they submit differs. Keeping one renderer means a field type added
   in the form builder appears in both places, and a fix to radio clearing or
   the well autocomplete is a fix in both.

   Every selector is scoped to the engine's own root element, so two engines
   can live on one page without fighting over field ids.
   ========================================================================== */
(function () {
  'use strict';
  var A = window.App, J = window.Jalali;

  /* Keys the record API takes at the top level rather than as dynamic values.
     The flat mode used by the workflow sends everything by field name and lets
     the server sort it out, so this only matters for the entry page. */
  var TAG_FIELDS = ['failure', 'workshop_opinion', 'desc_tags', 'install_relates_to'];

  function FormEngine(options) {
    var root = options.root;
    var schema = options.schema;           // { sections, lookups, conditional }
    var flat = !!options.flat;             // workflow mode: one key per field
    var self = this;

    function qs(sel) { return A.qs(sel, root); }
    function qsa(sel) { return A.qsa(sel, root); }

    /* ── rendering ────────────────────────────────────────────────────── */
    function optionsFor(field) {
      if (field.own_options && field.own_options.length) return field.own_options;
      if (field.lookup_category) return (schema.lookups || {})[field.lookup_category] || [];
      return [];
    }
    self.optionsFor = optionsFor;

    function labelHtml(field) {
      return '<label for="fld-' + A.esc(field.field_name) + '">' + A.esc(field.label)
        + (field.is_required ? ' <span class="req">*</span>' : '') + '</label>';
    }

    function renderChoice(field, multiple) {
      var opts = optionsFor(field);
      var type = multiple ? 'checkbox' : 'radio';
      /* Say what to do with the row of buttons. Without it a long list of
         unselected options reads as a box that has not loaded — which is
         exactly how «علت خرابی» was misread. */
      var html = '<div class="choice-help">'
        + (multiple ? 'روی هر مورد بزنید تا انتخاب شود — <b>چند مورد</b> '
                      + 'قابل انتخاب است.'
                    : 'یکی از گزینه‌ها را انتخاب کنید.')
        + ' برای برداشتن، دوباره روی همان بزنید.'
        + '<span class="choice-count" data-count="' + A.esc(field.field_name)
        + '"></span></div>';
      /* No blank "—" button: an empty choice is not a choice. Clearing is done
         by clicking the selected option again. */
      html += '<div class="btn-group' + (opts.length > 14 ? ' compact' : '')
        + '" data-field="' + A.esc(field.field_name) + '">';
      opts.forEach(function (opt) {
        html += '<label><input type="' + type + '" name="' + A.esc(field.field_name)
          + '" value="' + A.esc(opt.value) + '"'
          + (opt.is_default ? ' checked' : '') + '>'
          + '<span class="btn-opt">' + (opt.icon ? A.esc(opt.icon) + ' ' : '')
          + A.esc(opt.label) + '</span></label>';
      });
      html += '</div>';
      if (field.allow_other) {
        html += '<input type="text" class="other-input" data-other="'
          + A.esc(field.field_name) + '" placeholder="سایر موارد (در فهرست نیست)...">';
      }
      return html;
    }

    function renderSelect(field) {
      var html = '<select id="fld-' + A.esc(field.field_name) + '" name="'
        + A.esc(field.field_name) + '"><option value="">—</option>';
      optionsFor(field).forEach(function (opt) {
        html += '<option value="' + A.esc(opt.value) + '">' + A.esc(opt.label) + '</option>';
      });
      return html + '</select>';
    }

    function renderInput(field) {
      var id = 'fld-' + A.esc(field.field_name);
      var attrs = ' id="' + id + '" name="' + A.esc(field.field_name) + '"';
      /* «مقدار پیش‌فرض» written as a formula: filled with its result while the
         user has not typed a value of their own */
      if (String(field.default_value || '').charAt(0) === '=') {
        attrs += ' data-autofill="' + A.esc(field.field_name) + '"';
        if (!field.placeholder) attrs += ' placeholder="خودکار از محاسبه — قابل ویرایش"';
      }
      if (field.placeholder) attrs += ' placeholder="' + A.esc(field.placeholder) + '"';
      if (field.max_length) attrs += ' maxlength="' + field.max_length + '"';
      switch (field.field_type) {
        case 'number':
          if (field.min_value !== null) attrs += ' min="' + field.min_value + '"';
          if (field.max_value !== null) attrs += ' max="' + field.max_value + '"';
          attrs += ' step="' + A.esc(field.step || 'any') + '"';
          return '<input type="number"' + attrs + '>';
        case 'textarea':
          return '<textarea' + attrs + '></textarea>';
        case 'date':
          return '<input type="date"' + attrs + '>';
        case 'jalali_date':
          return '<input type="text" class="jdate"' + attrs + '>';
        case 'autocomplete':
          return '<div class="autocomplete-wrapper">'
            + '<input type="text" autocomplete="off" data-autocomplete="'
            + A.esc(field.lookup_category || 'wells') + '"' + attrs + '>'
            + '<div class="autocomplete-list"></div></div>';
        default:
          return '<input type="text"' + attrs + '>';
      }
    }

    /* A checklist: one item per line with a box to tick, and — when it is
       being shown rather than filled — the same lines with what was ticked
       already marked. Reading «۷ مورد از ۱۲» off a row of buttons is the
       thing this type exists to avoid. */
    function renderChecklist(field, locked) {
      var items = optionsFor(field);
      if (!items.length) {
        return '<div class="hint">برای این چک‌لیست موردی تعریف نشده است.</div>';
      }
      var done = [];
      if (locked) {
        var raw = field.read_only_value;
        done = Array.isArray(raw) ? raw.map(String)
          : String(raw == null ? '' : raw).split(/[،,]/)
              .map(function (x) { return x.trim(); }).filter(Boolean);
      }
      return '<ul class="checklist' + (locked ? ' locked' : '') + '" data-field="'
        + A.esc(field.field_name) + '">'
        + items.map(function (opt, i) {
            var value = opt.value === undefined ? opt : opt.value;
            var label = opt.label || value;
            var ticked = locked && done.indexOf(String(value)) >= 0;
            return '<li class="checklist-item' + (ticked ? ' done' : '') + '">'
              + '<label>'
              + '<input type="checkbox" name="' + A.esc(field.field_name) + '"'
              + ' id="fld-' + A.esc(field.field_name) + '-' + i + '"'
              + ' value="' + A.esc(value) + '"'
              + (ticked ? ' checked' : '') + (locked ? ' disabled' : '') + '>'
              + '<span class="checklist-mark"></span>'
              + '<span class="checklist-text">' + A.esc(label) + '</span>'
              + '</label></li>';
          }).join('')
        + '</ul>'
        + (locked
            ? '<div class="hint checklist-count">'
              + done.length + ' مورد از ' + items.length + ' انجام شده</div>'
            : '');
    }


    /* ── «محاسباتی»: a small, safe evaluator for the form's formulas ──────
       Same language the server uses: [field] references (by name or label),
       numbers, + − × ÷ ^, parentheses, comparisons, and ROUND, ABS, MIN, MAX,
       SQRT, IF. Nothing is ever passed to eval. The server recomputes on save;
       this only shows the result as the inputs are typed. */
    var labelToName = null;
    function refName(ref) {
      if (!labelToName) {
        labelToName = {};
        (schema.sections || []).forEach(function (sec) {
          (sec.fields || []).forEach(function (f) { labelToName[f.label] = f.field_name; });
        });
      }
      return labelToName[ref] || ref;
    }
    function toNum(v) {
      if (v === null || v === undefined || v === '') return null;
      if (typeof v === 'number') return v;
      var t = String(v).replace(/[۰-۹]/g, function (d) { return '۰۱۲۳۴۵۶۷۸۹'.indexOf(d); })
        .replace('٫', '.').replace(/,/g, '');
      var n = Number(t);
      return isNaN(n) ? null : n;
    }
    function qfit(vals, wantA) {
      if (vals.length % 2) return null;
      var n = vals.length / 2, x2 = 0, x3 = 0, x4 = 0, yx = 0, yx2 = 0, k = 0;
      for (var q = 0; q < n; q++) {
        var x = vals[q], y = vals[n + q];
        if (x === null || x === 0 || y === null) continue;
        k++; x2 += x * x; x3 += x * x * x; x4 += x * x * x * x; yx += y * x; yx2 += y * x * x;
      }
      var det = x4 * x2 - x3 * x3;
      if (k < 2 || Math.abs(det) < 1e-12) return null;
      return wantA ? (yx2 * x2 - yx * x3) / det : (x4 * yx - x3 * yx2) / det;
    }
    function roundTo(v, d, mode) {
      var f = Math.pow(10, d || 0), a = Math.abs(v) * f;
      var r = mode === 'up' ? Math.ceil(a - 1e-9) : mode === 'down' ? Math.floor(a + 1e-9)
        : Math.round(a);
      r = r / f;
      return v < 0 ? -r : r;
    }
    function truthy(v) { return !(v === null || v === undefined || v === '' || v === 0 || v === false); }
    function evalFormula(text, lookup) {
      var toks = [], i = 0, src = String(text || '');
      while (i < src.length) {
        var c = src[i];
        if (/\s/.test(c)) { i++; continue; }
        if (c === '[' || c === '{') {
          var close = c === '[' ? ']' : '}', j = src.indexOf(close, i);
          if (j < 0) throw 'bad';
          toks.push({ t: 'ref', v: src.slice(i + 1, j).trim() }); i = j + 1; continue;
        }
        if (c === '"' || c === "'" || c === '«') {
          var endq = src.indexOf(c === '«' ? '»' : c, i + 1);
          if (endq < 0) throw 'bad';
          toks.push({ t: 'str', v: src.slice(i + 1, endq) }); i = endq + 1; continue;
        }
        var m = /^[0-9۰-۹]+([.٫][0-9۰-۹]+)?/.exec(src.slice(i));
        if (m) { toks.push({ t: 'num', v: toNum(m[0]) }); i += m[0].length; continue; }
        m = /^[A-Za-z_][A-Za-z_0-9]*/.exec(src.slice(i));
        if (m) { toks.push({ t: 'fn', v: m[0].toUpperCase() }); i += m[0].length; continue; }
        m = /^(>=|<=|!=|<>|==|[-+*\/^%&()<>=,×÷])/.exec(src.slice(i));
        if (m) { toks.push({ t: 'op', v: m[0] === '×' ? '*' : m[0] === '÷' ? '/' : m[0] }); i += m[0].length; continue; }
        throw 'bad';
      }
      var p = 0;
      function peek(v) { return toks[p] && toks[p].t === 'op' && toks[p].v === v; }
      function cmpVals(op, a, b) {
        if (a === null || b === null) {
          if (op === '=' || op === '==') return a === b ? 1 : 0;
          if (op === '!=' || op === '<>') return a === b ? 0 : 1;
          return null;
        }
        var na = toNum(a), nb = toNum(b);
        if (na !== null && nb !== null) { a = na; b = nb; } else { a = String(a); b = String(b); }
        return { '>': a > b, '<': a < b, '>=': a >= b, '<=': a <= b, '=': a === b, '==': a === b,
                 '!=': a !== b, '<>': a !== b }[op] ? 1 : 0;
      }
      function cmp() {
        var a = cat();
        while (toks[p] && toks[p].t === 'op' && ['>', '<', '>=', '<=', '=', '==', '!=', '<>'].indexOf(toks[p].v) >= 0) {
          var op = toks[p++].v, b = cat();
          a = cmpVals(op, a, b);
        }
        return a;
      }
      function cat() {
        var a = add();
        while (peek('&')) { p++; var b = add(); a = (a === null ? '' : String(a)) + (b === null ? '' : String(b)); }
        return a;
      }
      function add() {
        var a = mul();
        while (peek('+') || peek('-')) {
          var op = toks[p++].v, b = toNum(mul()); a = toNum(a);
          a = (a === null || b === null) ? null : (op === '+' ? a + b : a - b);
        }
        return a;
      }
      function mul() {
        var a = pow();
        while (peek('*') || peek('/') || peek('%')) {
          var op = toks[p++].v, b = toNum(pow()); a = toNum(a);
          if (a === null || b === null) a = null;
          else if (op === '/') a = b === 0 ? null : a / b;
          else if (op === '%') a = b === 0 ? null : a % b;
          else a = a * b;
        }
        return a;
      }
      function pow() {
        var a = unary();
        if (peek('^')) {
          p++; var b = toNum(pow()); a = toNum(a);
          a = (a === null || b === null) ? null : Math.pow(a, b);
          if (a !== null && !isFinite(a)) a = null;
        }
        return a;
      }
      function unary() {
        if (peek('-')) { p++; var v = toNum(unary()); return v === null ? null : -v; }
        if (peek('+')) { p++; return unary(); }
        return atom();
      }
      function atom() {
        var tk = toks[p++];
        if (!tk) throw 'bad';
        if (tk.t === 'num' || tk.t === 'str') return tk.v;
        if (tk.t === 'ref') {
          var raw = lookup(refName(tk.v));
          if (raw === undefined || raw === '') return null;
          var asNum = toNum(raw);
          return asNum === null ? raw : asNum;
        }
        if (tk.t === 'op' && tk.v === '(') { var v = cmp(); if (!peek(')')) throw 'bad'; p++; return v; }
        if (tk.t === 'fn') {
          if (tk.v === 'TRUE') return 1;
          if (tk.v === 'FALSE') return 0;
          if (!peek('(')) throw 'bad';
          p++;
          var args = [];
          if (!peek(')')) { args.push(cmp()); while (peek(',')) { p++; args.push(cmp()); } }
          if (!peek(')')) throw 'bad';
          p++;
          var ns = args.map(toNum);
          var nums = ns.filter(function (x) { return x !== null; });
          var a0 = ns[0], d1 = ns[1] || 0;
          switch (tk.v) {
            case 'ROUND': return a0 === null ? null : roundTo(a0, d1);
            case 'ROUNDUP': return a0 === null ? null : roundTo(a0, d1, 'up');
            case 'ROUNDDOWN': return a0 === null ? null : roundTo(a0, d1, 'down');
            case 'ABS': return a0 === null ? null : Math.abs(a0);
            case 'SQRT': return a0 === null || a0 < 0 ? null : Math.sqrt(a0);
            case 'POWER': return a0 === null || ns[1] === null ? null : Math.pow(a0, ns[1]);
            case 'MIN': return nums.length ? Math.min.apply(null, nums) : null;
            case 'MAX': return nums.length ? Math.max.apply(null, nums) : null;
            case 'IF': return truthy(args[0]) ? (args[1] === undefined ? null : args[1])
              : (args[2] === undefined ? null : args[2]);
            case 'AND': return args.every(truthy) ? 1 : 0;
            case 'OR': return args.some(truthy) ? 1 : 0;
            case 'NOT': return truthy(args[0]) ? 0 : 1;
            case 'IFERROR': return (args[0] === null || args[0] === '' || (typeof args[0] === 'number' && !isFinite(args[0])))
              ? (args[1] === undefined ? null : args[1]) : args[0];
            case 'COALESCE':
              for (var q = 0; q < args.length; q++) if (args[q] !== null && args[q] !== '') return args[q];
              return null;
            case 'CONCAT': return args.map(function (x) { return x === null ? '' : String(x); }).join('');
            case 'NUMBER': return a0;
            case 'TEXT': return args[0] === null ? null : String(args[0]);
            case 'LEN': return args[0] === null ? null : String(args[0]).length;
            case 'QFIT_A': return qfit(ns, true);
            case 'QFIT_B': return qfit(ns, false);
            default: throw 'bad';
          }
        }
        throw 'bad';
      }
      var out = cmp();
      if (p < toks.length) throw 'bad';
      return out;
    }
    self.evalFormula = evalFormula;

    function contextValue(name) {
      var wrap = qs('[data-wrap="' + name + '"]');
      if (wrap) {
        var fd = fieldByName(name);
        if (fd && fd.read_only) return fd.read_only_value;
        if (fd && fd.field_type === 'chart') return null;
        if (fd && fd.field_type === 'formula') {
          var out = qs('#fld-' + name);
          return out ? out.value : null;
        }
        return currentValueOf(name);
      }
      return (options.context || {})[name];
    }
    var byName = null;
    function fieldByName(name) {
      if (!byName) {
        byName = {};
        (schema.sections || []).forEach(function (sec) {
          (sec.fields || []).forEach(function (f) { byName[f.field_name] = f; });
        });
      }
      return byName[name];
    }

    function recomputeFormulas() {
      var outs = qsa('[data-formula]');
      for (var pass = 0; pass < Math.max(3, outs.length + 1); pass++) {
        var changed = false;
        outs.forEach(function (out) {
          var fd = fieldByName(out.dataset.formula);
          if (!fd) return;
          var v = null;
          try { v = evalFormula(fd.formula, contextValue); } catch (e) { v = null; }
          var dec = /^\d+$/.test(String(fd.step || '')) ? Number(fd.step) : 4;
          var text;
          if (v === null || v === undefined || (typeof v === 'number' && !isFinite(v))) text = '';
          else if (typeof v === 'number') text = String(Math.round(v * Math.pow(10, dec)) / Math.pow(10, dec));
          else text = String(v);
          if (out.value !== text) { out.value = text; changed = true; }
        });
        if (!changed) break;
      }
      qsa('[data-autofill]').forEach(function (inp) {
        var fd = fieldByName(inp.dataset.autofill);
        if (!fd) return;
        var v = null;
        try { v = evalFormula(String(fd.default_value).slice(1), contextValue); } catch (e) { v = null; }
        var text = (v === null || v === undefined || (typeof v === 'number' && !isFinite(v))) ? ''
          : typeof v === 'number' ? String(Math.round(v * 10000) / 10000) : String(v);
        var mine = inp.value !== '' && inp.value !== inp.dataset.auto;
        if (inp.dataset.auto === undefined && inp.value !== '' && inp.value === text) mine = false;
        if (mine) return;                         // the user's own value stays
        if (inp.value !== text) inp.value = text;
        inp.dataset.auto = text;
      });
      drawCharts();
    }
    self.recomputeFormulas = recomputeFormulas;

    function renderFormula(field) {
      return '<input type="text" class="calc-output" id="fld-' + A.esc(field.field_name) + '"'
        + ' name="' + A.esc(field.field_name) + '" data-formula="' + A.esc(field.field_name) + '"'
        + ' readonly tabindex="-1" placeholder="خودکار محاسبه می‌شود">'
        + '<details class="calc-formula"><summary>ƒ فرمول</summary>'
        + '<span class="hint" dir="ltr">= ' + A.esc(field.formula || '') + '</span></details>';
    }

    /* ── «مستند»: upload into a named slot ─────────────────────────────── */
    function fileRow(a, removable) {
      return '<div class="file-row" data-att="' + a.id + '">'
        + '<a href="' + A.esc(a.url) + '" target="_blank">📄 ' + A.esc(a.filename) + '</a>'
        + '<span class="hint">' + A.esc(a.size_label || '') + (a.uploaded_by_name ? ' · ' + A.esc(a.uploaded_by_name) : '')
        + (a.uploaded_at_j ? ' · ' + A.esc(a.uploaded_at_j) : '') + '</span>'
        + (removable ? '<button type="button" class="btn-sm btn-del file-del" data-att="' + a.id + '" title="حذف">🗑</button>' : '')
        + '</div>';
    }
    function renderFile(field, locked) {
      var files = field.files || [];
      var list = '<div class="file-list" data-files="' + A.esc(field.field_name) + '">'
        + (files.length ? files.map(function (a) { return fileRow(a, !locked); }).join('')
          : '<div class="hint">' + (locked ? 'مستندی بارگذاری نشده است.' : 'هنوز فایلی بارگذاری نشده.') + '</div>')
        + '</div>';
      if (locked) return list;
      if (!options.upload) {
        return list + '<div class="hint">بارگذاری این مستند در کارتابل فرایند انجام می‌شود.</div>';
      }
      return list + '<label class="file-pick btn-ghost btn-sm">📎 انتخاب فایل'
        + '<input type="file" class="file-input" data-file-for="' + A.esc(field.field_name) + '"'
        + (field.file_accept ? ' accept="' + A.esc(field.file_accept) + '"' : '')
        + (field.file_multiple !== false ? ' multiple' : '') + ' hidden></label>'
        + '<span class="file-status hint" data-status="' + A.esc(field.field_name) + '"></span>'
        + (field.file_accept ? '<span class="hint"> — نوع مجاز: ' + A.esc(field.file_accept) + '</span>' : '');
    }
    function redrawFiles(field) {
      var box = qs('[data-files="' + field.field_name + '"]');
      if (!box) return;
      var files = field.files || [];
      box.innerHTML = files.length ? files.map(function (a) { return fileRow(a, true); }).join('')
        : '<div class="hint">هنوز فایلی بارگذاری نشده.</div>';
    }
    root.addEventListener('change', async function (ev) {
      var input = ev.target.closest && ev.target.closest('.file-input');
      if (!input || !options.upload) return;
      var field = fieldByName(input.dataset.fileFor);
      if (!field || !input.files.length) return;
      var status = qs('[data-status="' + field.field_name + '"]');
      if (status) status.textContent = 'در حال بارگذاری…';
      try {
        var added = await options.upload(field, Array.prototype.slice.call(input.files));
        field.files = field.file_multiple === false ? added.slice(-1) : (field.files || []).concat(added);
        redrawFiles(field);
        if (status) status.textContent = '✓ بارگذاری شد';
      } catch (err) {
        if (status) status.textContent = '✕ ' + (err.message || 'خطا');
      }
      input.value = '';
    });
    root.addEventListener('click', async function (ev) {
      var del = ev.target.closest && ev.target.closest('.file-del');
      if (!del || !options.removeFile) return;
      var wrap = del.closest('[data-wrap]');
      var field = wrap && fieldByName(wrap.dataset.wrap);
      if (!field) return;
      if (!(await A.confirmDialog({ message: 'این فایل حذف شود؟' }))) return;
      try {
        await options.removeFile(Number(del.dataset.att));
        field.files = (field.files || []).filter(function (a) { return String(a.id) !== del.dataset.att; });
        redrawFiles(field);
      } catch (err) { A.toast(err.message, 'error'); }
    });

    /* ── «چند مقدار عددی»: one value per part (فاز ۱، فاز ۲، فاز ۳) ─────── */
    function partLabels(field) {
      return (field.part_labels && field.part_labels.length) ? field.part_labels
        : ['فاز ۱', 'فاز ۲', 'فاز ۳'];
    }
    function renderNumbers(field) {
      var name = A.esc(field.field_name);
      return '<div class="numbers-group" data-numbers="' + name + '">'
        + partLabels(field).map(function (lbl, i) {
          return '<label class="num-part"><span>' + A.esc(lbl) + '</span>'
            + '<input type="text" inputmode="decimal" dir="ltr" class="num-part-input"'
            + ' id="fld-' + name + '__' + i + '" data-part-of="' + name + '" data-part="' + i + '"'
            + (field.placeholder ? ' placeholder="' + A.esc(field.placeholder) + '"' : '') + '></label>';
        }).join('') + '</div>';
    }
    function numbersOf(name) {
      return qsa('[data-part-of="' + name + '"]').map(function (i) { return i.value.trim(); });
    }
    function splitNumbers(value) {
      if (Array.isArray(value)) return value.map(function (v) { return v == null ? '' : String(v); });
      if (value === null || value === undefined || value === '') return [];
      return String(value).replace(/\(.*\)$/, '').split(/\s*[\/،,]\s*/).map(function (v) { return v.trim(); });
    }

    /* ── «نمودار»: drawn from the form's own numbers as they are typed ──── */
    function renderChart(field) {
      return '<div class="form-chart" data-chart="' + A.esc(field.field_name) + '"></div>'
        + '<div class="form-chart-eq hint" data-chart-eq="' + A.esc(field.field_name) + '"></div>';
    }
    var echartsLoading = null;
    function loadEcharts() {
      if (window.echarts) return Promise.resolve(window.echarts);
      if (echartsLoading) return echartsLoading;
      var me = document.querySelector('script[src*="js/formengine.js"]');
      var src = me ? me.getAttribute('src').replace(/js\/formengine\.js.*$/, 'vendor/echarts.min.js')
        : '/static/vendor/echarts.min.js';
      echartsLoading = new Promise(function (resolve, reject) {
        var tag = document.createElement('script');
        tag.src = src;
        tag.onload = function () { resolve(window.echarts); };
        tag.onerror = reject;
        document.head.appendChild(tag);
      });
      return echartsLoading;
    }
    function solve3(m, v) {
      /* Cramer's rule for the 3×3 normal equations of a full quadratic. */
      function det(a) {
        return a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1])
          - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
          + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]);
      }
      var d = det(m);
      if (Math.abs(d) < 1e-12) return null;
      return [0, 1, 2].map(function (k) {
        var c = m.map(function (row, r) { return row.map(function (x, j) { return j === k ? v[r] : x; }); });
        return det(c) / d;
      });
    }
    function fmtC(n) {
      var a = Math.abs(n);
      return String(a >= 100 ? Math.round(a * 100) / 100 : a >= 1 ? Math.round(a * 10000) / 10000
        : Number(a.toPrecision(4)));
    }
    function sgn(n, first) { return n < 0 ? (first ? '-' : ' - ') : (first ? '' : ' + '); }
    function fitTrend(kind, pts) {
      var xs = pts.map(function (q) { return q[0]; }), ys = pts.map(function (q) { return q[1]; });
      var n = pts.length;
      function S(f) { var t = 0; for (var q = 0; q < n; q++) t += f(xs[q], ys[q]); return t; }
      if (kind === 'poly2_0') {
        var flat = xs.concat(ys), a = qfit(flat, true), b = qfit(flat, false);
        if (a === null) return null;
        return { f: function (x) { return a * x * x + b * x; }, from0: true,
                 eq: 'y = ' + sgn(a, true) + fmtC(a) + 'x²' + sgn(b) + fmtC(b) + 'x' };
      }
      if (kind === 'poly2' && n >= 3) {
        var c = solve3([[S(function (x) { return Math.pow(x, 4); }), S(function (x) { return Math.pow(x, 3); }), S(function (x) { return x * x; })],
                        [S(function (x) { return Math.pow(x, 3); }), S(function (x) { return x * x; }), S(function (x) { return x; })],
                        [S(function (x) { return x * x; }), S(function (x) { return x; }), n]],
                       [S(function (x, y) { return y * x * x; }), S(function (x, y) { return y * x; }), S(function (x, y) { return y; })]);
        if (!c) return null;
        return { f: function (x) { return c[0] * x * x + c[1] * x + c[2]; },
                 eq: 'y = ' + sgn(c[0], true) + fmtC(c[0]) + 'x²' + sgn(c[1]) + fmtC(c[1]) + 'x' + sgn(c[2]) + fmtC(c[2]) };
      }
      if (kind === 'linear' && n >= 2) {
        var den = n * S(function (x) { return x * x; }) - Math.pow(S(function (x) { return x; }), 2);
        if (Math.abs(den) < 1e-12) return null;
        var m = (n * S(function (x, y) { return x * y; }) - S(function (x) { return x; }) * S(function (x, y) { return y; })) / den;
        var k = (S(function (x, y) { return y; }) - m * S(function (x) { return x; })) / n;
        return { f: function (x) { return m * x + k; }, eq: 'y = ' + sgn(m, true) + fmtC(m) + 'x' + sgn(k) + fmtC(k) };
      }
      if (kind === 'power') {
        var pp = pts.filter(function (q) { return q[0] > 0 && q[1] > 0; });
        if (pp.length < 2) return null;
        var lx = pp.map(function (q) { return Math.log(q[0]); }), ly = pp.map(function (q) { return Math.log(q[1]); });
        var N = pp.length, sx = 0, sy = 0, sxx = 0, sxy = 0;
        for (var q = 0; q < N; q++) { sx += lx[q]; sy += ly[q]; sxx += lx[q] * lx[q]; sxy += lx[q] * ly[q]; }
        var dd = N * sxx - sx * sx;
        if (Math.abs(dd) < 1e-12) return null;
        var kk = (N * sxy - sx * sy) / dd, AA = Math.exp((sy - kk * sx) / N);
        return { f: function (x) { return x > 0 ? AA * Math.pow(x, kk) : null; },
                 eq: 'y = ' + fmtC(AA) + 'x^' + (kk < 0 ? '-' : '') + fmtC(kk) };
      }
      return null;
    }
    var chartInstances = {};
    function drawCharts() {
      var boxes = qsa('[data-chart]');
      if (!boxes.length) return;
      loadEcharts().then(function (ec) {
        boxes.forEach(function (box) { drawChart(ec, box); });
      }).catch(function () {
        boxes.forEach(function (box) { box.innerHTML = '<div class="hint">کتابخانه‌ی نمودار بارگذاری نشد.</div>'; });
      });
    }
    function drawChart(ec, box) {
      var fd = fieldByName(box.dataset.chart);
      if (!fd || !box.offsetParent) return;           // hidden: drawn when it opens
      var cfg = fd.chart_config || {};
      var palette = ['#2563eb', '#dc2626', '#16a34a', '#d97706', '#7c3aed'];
      var series = [], eqs = [], useRight = false, xmax = 0;
      (cfg.series || []).forEach(function (sr, si) {
        var pts = [];
        (sr.x || []).forEach(function (xn, k) {
          var x = toNum(contextValue(xn)), y = toNum(contextValue((sr.y || [])[k]));
          if (x === null || y === null || (x === 0 && y === 0)) return;
          pts.push([x, y]);
          if (x > xmax) xmax = x;
        });
        pts.sort(function (p1, p2) { return p1[0] - p2[0]; });
        var right = sr.axis === 'right';
        if (right) useRight = true;
        var color = palette[si % palette.length];
        series.push({ name: sr.label || ('سری ' + (si + 1)), type: 'scatter', data: pts,
                      yAxisIndex: right ? 1 : 0, symbolSize: 9, itemStyle: { color: color } });
        if (sr.trend && pts.length >= 2) {
          var fit = fitTrend(sr.trend, pts);
          if (fit) {
            var lo = fit.from0 ? 0 : pts[0][0], hi = pts[pts.length - 1][0];
            var span = (hi - lo) || hi || 1, line = [];
            for (var q = 0; q <= 40; q++) {
              var x = lo + (span * 1.1) * q / 40, y = fit.f(x);
              if (y !== null && isFinite(y)) line.push([Math.round(x * 10000) / 10000, Math.round(y * 10000) / 10000]);
            }
            series.push({ name: (sr.label || '') + ' — روند', type: 'line', data: line, showSymbol: false,
                          yAxisIndex: right ? 1 : 0, lineStyle: { type: 'dashed', color: color, width: 1.5 },
                          itemStyle: { color: color } });
            eqs.push('<div style="color:' + color + '"><span>' + A.esc(sr.label || '') + ' — خط روند: </span>'
                     + '<span dir="ltr" class="mono">' + A.esc(fit.eq) + '</span></div>');
          }
        }
      });
      var yAxis = [{ type: 'value', name: cfg.y_label || '', max: cfg.y_max ? Number(cfg.y_max) : null,
                     position: 'left', nameTextStyle: { fontFamily: 'Vazirmatn' } }];
      if (useRight) {
        yAxis.push({ type: 'value', name: cfg.y2_label || '', max: cfg.y2_max ? Number(cfg.y2_max) : null,
                     position: 'right', splitLine: { show: false }, nameTextStyle: { fontFamily: 'Vazirmatn' } });
      }
      var chart = chartInstances[fd.field_name];
      if (chart && chart.getDom() !== box) { chart.dispose(); chart = null; }
      if (!chart) {
        chart = ec.init(box);
        chartInstances[fd.field_name] = chart;
        window.addEventListener('resize', function () { chart.resize(); });
      }
      chart.setOption({
        textStyle: { fontFamily: 'Vazirmatn, Tahoma, sans-serif' },
        tooltip: { trigger: 'item', formatter: function (pr) {
          return A.esc(pr.seriesName) + '<br>' + pr.value[0] + ' ، ' + pr.value[1];
        } },
        legend: { top: 0, textStyle: { fontFamily: 'Vazirmatn' } },
        grid: { left: 56, right: useRight ? 56 : 24, top: 48, bottom: 48 },
        xAxis: { type: 'value', name: cfg.x_label || '', nameLocation: 'middle', nameGap: 28, min: 0,
                 max: xmax ? Math.ceil(xmax * 1.15 * 100) / 100 : null },
        yAxis: yAxis,
        series: series,
      }, true);
      chart.resize();
      var eqBox = qs('[data-chart-eq="' + fd.field_name + '"]');
      if (eqBox) {
        eqBox.innerHTML = eqs.length ? eqs.join('')
          : (series.some(function (sr) { return sr.data.length; }) ? '' : 'پس از ورود داده‌ها نمودار رسم می‌شود.');
      }
    }
    self.drawCharts = drawCharts;

    function renderField(field) {
      var body;
      if (field.field_type === 'radio') body = renderChoice(field, false);
      else if (field.field_type === 'checkbox' && optionsFor(field).length) {
        body = renderChoice(field, true);
      } else if (field.field_type === 'checkbox') {
        body = '<div class="btn-group"><label><input type="checkbox" id="fld-'
          + A.esc(field.field_name) + '" name="' + A.esc(field.field_name)
          + '" value="1"><span class="btn-opt">بله</span></label></div>';
      } else if (field.field_type === 'multiselect') body = renderChoice(field, true);
      else if (field.field_type === 'checklist') body = renderChecklist(field);
      else if (field.field_type === 'select') body = renderSelect(field);
      else if (field.field_type === 'file') body = renderFile(field, !!field.read_only);
      else if (field.field_type === 'formula') body = renderFormula(field);
      else if (field.field_type === 'numbers') body = renderNumbers(field);
      else if (field.field_type === 'chart') body = renderChart(field);
      else body = renderInput(field);

      /* Settled upstream: shown and filled so the stage can see it, but not
         editable here — the well is chosen once, at step zero, and a checklist
         somebody already ticked is carried forward as a record of what they
         ticked rather than as a form to fill again. */
      if (field.read_only && field.field_type !== 'file' && field.field_type !== 'chart') {
        body = field.field_type === 'checklist'
          ? renderChecklist(field, true)
          : '<input type="text" id="fld-' + A.esc(field.field_name) + '"'
            + ' value="' + A.esc(field.read_only_value == null ? ''
                                 : String(field.read_only_value)) + '"'
            + ' readonly disabled>';
      }
      var span = field.col_span > 1 ? ' span-' + Math.min(field.col_span, 2) : '';
      /* Long option lists and free text need the whole row; squeezing 20
         buttons into a 180px column is what made the form look ragged. */
      var count = optionsFor(field).length;
      var wide = '';
      if (['textarea', 'file', 'chart'].includes(field.field_type)) wide = ' span-full';
      else if (['checkbox', 'multiselect'].includes(field.field_type) && count > 4) {
        wide = ' span-full';
      } else if (field.field_type === 'radio' && count > 7) {
        wide = ' wide-choice';
      }
      return '<div class="field' + span + wide
        + (field.read_only ? ' read-only' : '') + '" data-wrap="'
        + A.esc(field.field_name) + '">'
        + labelHtml(field) + body
        + (field.help_text ? '<span class="hint">' + A.esc(field.help_text) + '</span>' : '')
        + ((field.block_options || []).length && !field.read_only
            ? '<span class="block-note hidden" data-block-note="' + A.esc(field.field_name) + '">⛔ با پاسخ «'
              + A.esc(field.block_options.join('، ')) + '» مرحله ارسال نمی‌شود؛ پس از رفع مشکل پاسخ را اصلاح کنید.</span>'
            : '')
        + '<span class="err hidden"></span></div>';
    }

    self.render = function () {
      root.innerHTML = (schema.sections || []).map(function (section) {
        if (!section.fields || !section.fields.length) return '';
        return '<div class="form-section' + (section.full_width ? ' full-width' : '')
          + '" data-section="' + A.esc(section.code || '') + '">'
          + '<div class="section-title">'
          + (section.icon ? '<span>' + A.esc(section.icon) + '</span>' : '')
          + '<span>' + A.esc(section.title) + '</span>'
          + (section.is_optional ? '<span class="badge muted">اختیاری</span>' : '')
          + '</div>'
          + '<div class="field-group cols-' + (section.columns || 3) + '">'
          + section.fields.map(renderField).join('')
          + '</div></div>';
      }).join('');

      qsa('.jdate').forEach(function (input) { J.attach(input); });
      qsa('[data-autocomplete]').forEach(setupAutocomplete);
      enableRadioClearing();
      root.addEventListener('change', onFieldChanged);
      root.addEventListener('change', updateChoiceCounts);
      applyDefaults();
      self.applyConditional();
      updateChoiceCounts();
      root.addEventListener('input', recomputeFormulas);
      root.addEventListener('change', recomputeFormulas);
      recomputeFormulas();
      /* a pane that is drawn first and shown a moment later still gets its chart */
      setTimeout(drawCharts, 250);
      return self;
    };

    /* «۳ مورد انتخاب شده» beside the help line, so a long list still shows at
       a glance whether anything was picked. */
    /* «مانع ارسال»: say at once that this answer stops the stage */
    function updateBlockNotes() {
      qsa('[data-block-note]').forEach(function (note) {
        var fd = fieldByName(note.dataset.blockNote);
        var have = valuesOf(note.dataset.blockNote);
        note.classList.toggle('hidden', !fd || !have.some(function (v) {
          return (fd.block_options || []).indexOf(v) !== -1;
        }));
      });
    }
    function updateChoiceCounts() {
      updateBlockNotes();
      qsa('[data-count]').forEach(function (badge) {
        var name = badge.dataset.count;
        var n = qsa('input[name="' + name + '"]:checked').length;
        badge.textContent = n ? ' ' + J.toFaDigits(n) + ' مورد انتخاب شده' : '';
        badge.classList.toggle('has', !!n);
      });
    }
    self.updateChoiceCounts = updateChoiceCounts;

    function applyDefaults() {
      if (options.skipDefaults) return;
      (schema.sections || []).forEach(function (section) {
        (section.fields || []).forEach(function (field) {
          if (field.default_value && String(field.default_value).charAt(0) !== '=') {
            self.setFieldValue(field, field.default_value);
          }
        });
      });
    }

    /* Clicking the already-selected radio clears it — the only way back to
       "not answered" now that the blank option is gone. */
    function enableRadioClearing() {
      root.addEventListener('mousedown', function (ev) {
        var label = ev.target.closest('.btn-group label');
        if (!label || !root.contains(label)) return;
        var input = label.querySelector('input[type="radio"]');
        if (input && input.checked) {
          setTimeout(function () {
            input.checked = false;
            input.dispatchEvent(new Event('change', { bubbles: true }));
          }, 0);
        }
      });
    }

    /* ── conditional fields ───────────────────────────────────────────── */
    function currentValueOf(name) {
      if (qs('[data-numbers="' + name + '"]')) {
        var parts = numbersOf(name);
        return parts.some(function (x) { return x !== ''; }) ? parts.join(' / ') : '';
      }
      var picked = qs('input[name="' + name + '"]:checked');
      if (picked) return picked.value;
      var input = qs('#fld-' + name);
      return input ? input.value.trim() : '';
    }
    self.currentValueOf = currentValueOf;

    /* Every value the source field is holding right now.

       «علت خرابی» is a multi-select: the operator can tick سوختن الکتروپمپ and
       هوادهی together, and both of their forms have to open. So a rule is met
       when the source *contains* the value, not only when it equals it — with
       a single-choice field the two readings are the same thing. */
    function valuesOf(name) {
      var ticked = checkedValues(name);
      if (ticked.length) return ticked;
      var one = currentValueOf(name);
      return one ? [one] : [];
    }

    /* Several questions may open one form («any»): shown when any of them
       holds. Only the questions actually on this page are asked. */
    function sourcesHere(rule) {
      return (rule.any || [rule]).filter(function (r) {
        return !!qs('[data-wrap="' + r.on + '"]');
      });
    }

    function ruleIsMet(rule) {
      if (rule.any) {
        return sourcesHere(rule).some(function (r) { return oneRuleIsMet(r); });
      }
      return oneRuleIsMet(rule);
    }

    function oneRuleIsMet(rule) {
      /* «a|b|c»: any one of several values opens it — two causes can share
         one form. An empty list is a form linked to nothing yet. */
      var wanted = String(rule.value || '').split('|').filter(Boolean);
      var have = valuesOf(rule.on);
      if (wanted.indexOf('*') !== -1) return have.some(function (h) { return String(h).trim() !== ''; });
      return wanted.some(function (w) { return have.indexOf(w) !== -1; });
    }

    self.applyConditional = function () {
      (schema.conditional || []).forEach(function (rule) {
        if (rule.section) { applySectionRule(rule); return; }
        var wrap = qs('[data-wrap="' + rule.field + '"]');
        if (!wrap) return;
        /* A rule can only be judged where its source field is. On a workflow
           stage «علت خرابی» is drawn without «نوع عملیات» beside it, because
           the server already decided the branch and either sent the field or
           did not. Re-deciding it here from a second copy of the answer is how
           the one field a stage exists to collect ended up hidden behind its
           own heading. */
        if (!sourcesHere(rule).length) return;
        var show = ruleIsMet(rule);
        var was = !wrap.classList.contains('hidden');
        wrap.classList.toggle('hidden', !show);
        if (!show) clearField(rule.field);
        else if (!was) restoreDefault(rule.field);
      });
      if (options.onConditional) options.onConditional(self);
    };

    /* A whole section appears or goes away together — the parameters of one
       علت خرابی are one block, and clearing them one field at a time would
       leave half-answered readings behind when the cause is unticked. */
    function applySectionRule(rule) {
      var block = qs('[data-section="' + rule.section + '"]');
      if (!block) return;
      if (!sourcesHere(rule).length) return;
      var show = ruleIsMet(rule);
      var was = !block.classList.contains('hidden');
      block.classList.toggle('hidden', !show);
      if (show) {
        if (!was) (rule.fields || []).forEach(restoreDefault);   // reopened: defaults back
        return;
      }
      (rule.fields || []).forEach(clearField);
    }

    /* A hidden answer is dropped; a reopened field starts from its default again. */
    function clearField(name) {
      qsa('input[name="' + name + '"]').forEach(function (i) { i.checked = false; });
      var free = qs('#fld-' + name);
      if (free) free.value = '';
      qsa('[data-part-of="' + name + '"]').forEach(function (i) { i.value = ''; });
      var other = qs('[data-other="' + name + '"]');
      if (other) other.value = '';
    }
    function restoreDefault(name) {
      var fd = fieldByName(name);
      if (!fd || options.skipDefaults || !fd.default_value
          || String(fd.default_value).charAt(0) === '=') return;
      var now = readField(fd);
      if (now === '' || now === false || (Array.isArray(now) && !now.length)) {
        self.setFieldValue(fd, fd.default_value);
      }
    }

    function onFieldChanged(ev) {
      var name = ev.target.name || (ev.target.id || '').replace(/^fld-/, '');
      if (!name) return;
      if ((schema.conditional || []).some(function (r) {
            return (r.any || [r]).some(function (x) { return x.on === name; });
          })) {
        self.applyConditional();
      }
      if (name === 'well') {
        fillCentreFromWell(ev.target.value);
        if (options.onWellPicked) options.onWellPicked(ev.target.value);
      }
      if (options.onChange) options.onChange(name, self);
    }

    /* Picking a well fills in its centre, and then closes it.

       The register already knows which centre a well belongs to, so asking is
       both extra work and a chance to get it wrong. Clearing the well opens it
       again — a well nobody has chosen has no centre to impose. */
    async function fillCentreFromWell(name) {
      name = (name || '').trim();
      if (!name) { lockCentre(null); return; }
      try {
        var res = await A.api.get('/api/wells?all=1&limit=1&q='
                                  + encodeURIComponent(name));
        var well = (res.data || []).find(function (w) { return w.name === name; });
        if (!well || !well.center_value) { lockCentre(null); return; }
        var radio = qs('input[name="center"][value="'
                       + CSS.escape(well.center_value) + '"]');
        if (!radio) { lockCentre(null); return; }
        if (!radio.checked) {
          radio.checked = true;
          radio.dispatchEvent(new Event('change', { bubbles: true }));
          flash(qs('[data-wrap="center"]'));
        }
        lockCentre(well.name);
      } catch (err) { /* leave the centre for the operator to pick */ }
    }

    function lockCentre(wellName) {
      var wrap = qs('[data-wrap="center"]');
      if (!wrap) return;
      var locked = !!wellName;
      wrap.classList.toggle('from-well', locked);
      qsa('input[name="center"]').forEach(function (input) {
        // A disabled radio is not submitted, so keep the chosen one live and
        // close only the others; the group then cannot be changed either way.
        input.disabled = locked && !input.checked;
        input.readOnly = locked;
      });
      var note = wrap.querySelector('.centre-note');
      if (locked && !note) {
        note = document.createElement('span');
        note.className = 'hint centre-note';
        wrap.appendChild(note);
      }
      if (note) {
        note.textContent = locked
          ? 'مرکز چاه «' + wellName + '» است و از فهرست چاه‌ها خوانده می‌شود؛ '
            + 'برای تغییرش چاه دیگری انتخاب کنید.'
          : '';
        note.hidden = !locked;
      }
    }

    function flash(wrap) {
      if (!wrap) return;
      wrap.classList.add('auto-filled');
      setTimeout(function () { wrap.classList.remove('auto-filled'); }, 1600);
    }
    self.flash = flash;

    /* ── autocomplete ─────────────────────────────────────────────────── */
    function setupAutocomplete(input) {
      var list = input.parentNode.querySelector('.autocomplete-list');
      var source = input.dataset.autocomplete;

      var search = A.debounce(async function () {
        var value = input.value.trim();
        if (value.length < 1) { list.classList.remove('show'); return; }
        var items = [];
        if (source === 'wells' || source === 'well') {
          try {
            var res = await A.api.get('/api/wells?limit=15&q='
                                      + encodeURIComponent(value));
            items = res.data.map(function (w) {
              var tags = [];
              if (w.pm_code) tags.push('کد PM: ' + w.pm_code);
              if (w.well_class) tags.push('کلاسه: ' + w.well_class);
              if (w.center) tags.push(w.center);
              if (!w.is_verified) tags.push('تأییدنشده');
              return { value: w.name, label: w.name, id: w.id,
                       meta: tags.join(' · ') };
            });
          } catch (err) { items = []; }
        } else {
          items = ((schema.lookups || {})[source] || []).filter(function (opt) {
            return opt.value.indexOf(value) >= 0 || opt.label.indexOf(value) >= 0;
          }).slice(0, 15).map(function (opt) {
            return { value: opt.value, label: opt.label, id: opt.id, meta: '' };
          });
        }
        if (!items.length) {
          list.innerHTML = '<div class="autocomplete-item create">'
            + '«' + A.esc(value) + '» در فهرست نیست — با ثبت رکورد افزوده می‌شود</div>';
          list.classList.add('show');
          return;
        }
        list.innerHTML = items.map(function (item) {
          return '<div class="autocomplete-item" data-value="' + A.esc(item.value) + '">'
            + A.esc(item.label)
            + (item.meta ? ' <span class="meta">— ' + A.esc(item.meta) + '</span>' : '')
            + '</div>';
        }).join('');
        list.classList.add('show');
      }, 180);

      input.addEventListener('input', search);
      input.addEventListener('focus', search);
      list.addEventListener('click', function (ev) {
        var item = ev.target.closest('.autocomplete-item[data-value]');
        if (!item) return;
        input.value = item.dataset.value;
        list.classList.remove('show');
        input.dispatchEvent(new Event('change', { bubbles: true }));
        if (source === 'wells' || source === 'well') showWellBadge(input);
      });
      if (source === 'wells' || source === 'well') {
        input.addEventListener('change', function () { showWellBadge(input); });
      }
      document.addEventListener('click', function (ev) {
        if (!input.parentNode.contains(ev.target)) list.classList.remove('show');
      });
    }

    async function showWellBadge(input) {
      var wrap = input.closest('.field');
      if (!wrap) return;
      var badge = wrap.querySelector('.well-badge');
      if (!badge) {
        badge = A.el('div', { class: 'well-badge hint' });
        wrap.appendChild(badge);
      }
      var name = input.value.trim();
      if (!name) { badge.textContent = ''; return; }
      try {
        var res = await A.api.get('/api/wells?all=1&limit=1&q='
                                  + encodeURIComponent(name));
        var w = (res.data || []).find(function (x) { return x.name === name; });
        if (!w) {
          badge.innerHTML = '<span class="badge warn">چاه جدید — با ثبت رکورد افزوده می‌شود</span>';
          return;
        }
        var parts = [];
        if (w.pm_code) parts.push('<span class="badge">کد PM: ' + A.esc(w.pm_code) + '</span>');
        if (w.well_class) parts.push('<span class="badge">کلاسه: ' + A.esc(w.well_class) + '</span>');
        if (w.center) parts.push('<span class="badge muted">' + A.esc(w.center) + '</span>');
        if (!w.pm_code && !w.well_class) {
          parts.push('<span class="badge muted">کد PM ثبت نشده</span>');
        }
        badge.innerHTML = parts.join(' ');
      } catch (err) { badge.textContent = ''; }
    }
    self.showWellBadge = showWellBadge;

    /* ── reading / writing ────────────────────────────────────────────── */
    function checkedValues(name) {
      return qsa('input[name="' + name + '"]:checked')
        .map(function (i) { return i.value; }).filter(Boolean);
    }

    function otherValue(name) {
      var input = qs('[data-other="' + name + '"]');
      return input ? input.value.trim() : '';
    }
    self.otherValue = otherValue;

    function hiddenFields() {
      var hidden = {};
      (schema.conditional || []).forEach(function (rule) {
        if (rule.section) {
          var block = qs('[data-section="' + rule.section + '"]');
          if (block && block.classList.contains('hidden')) {
            (rule.fields || []).forEach(function (n) { hidden[n] = true; });
          }
          return;
        }
        var wrap = qs('[data-wrap="' + rule.field + '"]');
        if (wrap && wrap.classList.contains('hidden')) hidden[rule.field] = true;
      });
      return hidden;
    }

    function readField(field) {
      var name = field.field_name;
      if (field.field_type === 'file') {
        return (field.files || []).map(function (a) { return a.id; });
      }
      if (field.field_type === 'numbers') {
        var parts = numbersOf(name);
        return parts.some(function (x) { return x !== ''; }) ? parts : [];
      }
      if (field.field_type === 'radio') {
        var value = checkedValues(name)[0] || '';
        var other = otherValue(name);
        return other || value;
      }
      if (['checkbox', 'multiselect', 'checklist'].includes(field.field_type)) {
        if (optionsFor(field).length) {
          var values = checkedValues(name);
          var extra = otherValue(name);
          if (extra) {
            values = values.concat(extra.split(',').map(function (v) {
              return v.trim();
            }).filter(Boolean));
          }
          return values;
        }
        var box = qs('#fld-' + name);
        return box ? box.checked : false;
      }
      var input = qs('#fld-' + name);
      return input ? input.value.trim() : '';
    }

    self.eachField = function (fn) {
      (schema.sections || []).forEach(function (section) {
        (section.fields || []).forEach(function (field) { fn(field, section); });
      });
    };

    /* Flat mode (workflow): one key per field name, exactly as the stage was
       drawn. Shaped mode (entry page): the record API's own shape. */
    self.collect = function () {
      var hidden = hiddenFields();
      if (flat) {
        var out = {};
        self.eachField(function (field) {
          if (hidden[field.field_name] || field.read_only || field.field_type === 'chart') return;
          out[field.field_name] = readField(field);
        });
        var fOther = otherValue('failure');
        if (fOther) out.failure_other = fOther;
        return out;
      }
      var payload = { dynamic: {} };
      self.eachField(function (field) {
        var name = field.field_name;
        if (hidden[name] || field.read_only || field.field_type === 'chart') return;
        var value = readField(field);
        if (field.model_attr) {
          if (name === 'op_jdate') { payload.op_jdate = value; return; }
          if (name === 'well') { payload.well = value; return; }
          /* Choice columns are sent by *value*, under the short key. */
          var key = field.model_attr.endsWith('_id')
            ? field.model_attr.slice(0, -3) : field.model_attr;
          payload[key] = value;
        } else if (TAG_FIELDS.includes(name)) {
          payload[name] = value;
        } else {
          payload.dynamic[name] = value;
        }
      });
      var failureOther = otherValue('failure');
      if (failureOther) payload.failure_other = failureOther;
      return payload;
    };

    self.setFieldValue = function (field, value) {
      var name = field.field_name;
      if (field.field_type === 'file') return;          // the upload list is the value
      if (field.field_type === 'formula' || field.field_type === 'chart') { recomputeFormulas(); return; }
      if (field.field_type === 'numbers') {
        var vals = splitNumbers(value);
        qsa('[data-part-of="' + name + '"]').forEach(function (inp, k) { inp.value = vals[k] || ''; });
        return;
      }
      if (field.field_type === 'radio') {
        var radio = qs('input[name="' + name + '"][value="'
                       + CSS.escape(String(value == null ? '' : value)) + '"]');
        if (radio) { radio.checked = true; return; }
        var other = qs('[data-other="' + name + '"]');
        if (other && value) other.value = value;
        return;
      }
      if (['checkbox', 'multiselect', 'checklist'].includes(field.field_type)) {
        if (optionsFor(field).length) {
          var wanted = Array.isArray(value) ? value
            : String(value || '').split(',').map(function (v) { return v.trim(); });
          var unmatched = [];
          qsa('input[name="' + name + '"]').forEach(function (box) {
            box.checked = wanted.includes(box.value);
          });
          wanted.filter(Boolean).forEach(function (v) {
            if (!qs('input[name="' + name + '"][value="' + CSS.escape(v) + '"]')) {
              unmatched.push(v);
            }
          });
          var extra = qs('[data-other="' + name + '"]');
          if (extra && unmatched.length) extra.value = unmatched.join('، ');
        } else {
          var box2 = qs('#fld-' + name);
          if (box2) box2.checked = !!value && value !== '0' && value !== 'false';
        }
        return;
      }
      var input = qs('#fld-' + name);
      if (input) input.value = value === null || value === undefined ? '' : value;
    };

    /* Fill from a flat {field_name: value} map, skipping names this form does
       not show. Used for the workflow payload and for the «…قبلی» suggestions. */
    self.setValues = function (values, opts) {
      opts = opts || {};
      self.eachField(function (field) {
        var name = field.field_name;
        if (!Object.prototype.hasOwnProperty.call(values, name)) return;
        if (opts.onlyEmpty && String(readField(field) || '').length) return;
        /* nothing saved yet: the field keeps its «مقدار پیش‌فرض» */
        if ((values[name] === null || values[name] === undefined || values[name] === '')
            && field.default_value && String(field.default_value).charAt(0) !== '=') return;
        self.setFieldValue(field, values[name]);
        if (opts.flash) flash(qs('[data-wrap="' + name + '"]'));
      });
      self.applyConditional();
      updateChoiceCounts();
      recomputeFormulas();
    };

    self.clearErrors = function () {
      qsa('.field.has-error').forEach(function (f) { f.classList.remove('has-error'); });
      qsa('.field .err').forEach(function (e) {
        e.classList.add('hidden'); e.textContent = '';
      });
    };

    self.showErrors = function (fields) {
      self.clearErrors();
      var first = null;
      Object.keys(fields || {}).forEach(function (name) {
        var wrap = qs('[data-wrap="' + name + '"]');
        if (!wrap) return;
        wrap.classList.add('has-error');
        var err = wrap.querySelector('.err');
        if (err) { err.textContent = fields[name]; err.classList.remove('hidden'); }
        if (!first) first = wrap;
      });
      if (first) first.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return first;
    };

    self.clear = function () {
      qsa('input, textarea, select').forEach(function (el) {
        if (el.type === 'radio' || el.type === 'checkbox') el.checked = false;
        else el.value = '';
      });
      self.clearErrors();
      applyDefaults();
      self.applyConditional();
      updateChoiceCounts();
    };

    self.lock = function () {
      qsa('input, textarea, select').forEach(function (el) { el.disabled = true; });
    };

    self.attachAutocompleteTo = setupAutocomplete;
    self.qs = qs;
    self.qsa = qsa;
  }

  window.FormEngine = function (options) { return new FormEngine(options); };

  /* A single input outside any form that still wants the well picker — the
     «شروع فرایند» dialog, for one. */
  window.FormEngine.attachAutocomplete = function (input, lookups) {
    var engine = new FormEngine({
      root: input.closest('.autocomplete-wrapper') || input.parentNode,
      schema: { sections: [], lookups: lookups || {} },
    });
    engine.attachAutocompleteTo(input);
    return engine;
  };
})();
