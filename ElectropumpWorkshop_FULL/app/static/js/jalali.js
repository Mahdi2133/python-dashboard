/* ==========================================================================
   Jalali calendar + a real Persian date picker, with no external library.
   Mirrors app/services/jalali.py exactly (Borkowski 33-year cycle), so a date
   picked in the browser and the date stored on the server always agree.
   ========================================================================== */
(function (global) {
  'use strict';

  var BREAKS = [-61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181, 1210,
                1635, 2060, 2097, 2192, 2262, 2324, 2394, 2456, 3178];

  var MONTHS = ['', 'فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور',
                'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند'];
  /* Jalali weeks start on Saturday. */
  var WEEK_LONG  = ['شنبه', 'یکشنبه', 'دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنجشنبه', 'جمعه'];
  var WEEK_SHORT = ['ش', 'ی', 'د', 'س', 'چ', 'پ', 'ج'];

  function jalCal(jy) {
    if (jy < BREAKS[0] || jy >= BREAKS[BREAKS.length - 1]) {
      throw new Error('سال شمسی خارج از محدوده: ' + jy);
    }
    var gy = jy + 621, leapJ = -14, jp = BREAKS[0], jump = 0, i, jm;
    for (i = 1; i < BREAKS.length; i++) {
      jm = BREAKS[i];
      jump = jm - jp;
      if (jy < jm) break;
      leapJ += Math.floor(jump / 33) * 8 + Math.floor((jump % 33) / 4);
      jp = jm;
    }
    var n = jy - jp;
    leapJ += Math.floor(n / 33) * 8 + Math.floor(((n % 33) + 3) / 4);
    if ((jump % 33) === 4 && (jump - n) === 4) leapJ += 1;
    var leapG = Math.floor(gy / 4) - Math.floor((Math.floor(gy / 100) + 1) * 3 / 4) - 150;
    var march = 20 + leapJ - leapG;
    if (jump - n < 6) n = n - jump + Math.floor((jump + 4) / 33) * 33;
    var leap = (((n + 1) % 33) - 1) % 4;
    if (leap === -1) leap = 4;
    return { leap: leap, gy: gy, march: march };
  }

  function isLeap(jy) { return jalCal(jy).leap === 0; }

  function monthDays(jy, jm) {
    jm = +jm;
    if (jm <= 6) return 31;
    if (jm <= 11) return 30;
    return isLeap(jy) ? 30 : 29;
  }

  function g2d(gy, gm, gd) {
    var a = Math.floor((14 - gm) / 12), y = gy + 4800 - a, m = gm + 12 * a - 3;
    return gd + Math.floor((153 * m + 2) / 5) + 365 * y + Math.floor(y / 4)
           - Math.floor(y / 100) + Math.floor(y / 400) - 32045;
  }

  function d2g(jdn) {
    var a = jdn + 32044, b = Math.floor((4 * a + 3) / 146097),
        c = a - Math.floor(146097 * b / 4), d = Math.floor((4 * c + 3) / 1461),
        e = c - Math.floor(1461 * d / 4), m = Math.floor((5 * e + 2) / 153);
    return {
      gy: 100 * b + d - 4800 + Math.floor(m / 10),
      gm: m + 3 - 12 * Math.floor(m / 10),
      gd: e - Math.floor((153 * m + 2) / 5) + 1
    };
  }

  function j2d(jy, jm, jd) {
    var r = jalCal(jy);
    return g2d(r.gy, 3, r.march) + (jm - 1) * 31 - Math.floor(jm / 7) * (jm - 7) + jd - 1;
  }

  function d2j(jdn) {
    var gy = d2g(jdn).gy, jy = gy - 621, r = jalCal(jy),
        k = jdn - g2d(gy, 3, r.march);
    if (k >= 0) {
      if (k <= 185) return { jy: jy, jm: 1 + Math.floor(k / 31), jd: 1 + (k % 31) };
      k -= 186;
    } else {
      jy -= 1;
      k += 179;
      if (r.leap === 1) k += 1;      // leap flag of the *original* jy
    }
    return { jy: jy, jm: 7 + Math.floor(k / 30), jd: 1 + (k % 30) };
  }

  function toJalali(date) {
    var j = d2j(g2d(date.getFullYear(), date.getMonth() + 1, date.getDate()));
    return [j.jy, j.jm, j.jd];
  }

  function toGregorian(jy, jm, jd) {
    var g = d2g(j2d(+jy, +jm, +jd));
    return new Date(g.gy, g.gm - 1, g.gd);
  }

  /* Day of week with Saturday = 0, matching the picker's column order. */
  function weekday(jy, jm, jd) { return (j2d(jy, jm, jd) + 1) % 7; }

  var FA_DIGITS = '۰۱۲۳۴۵۶۷۸۹', AR_DIGITS = '٠١٢٣٤٥٦٧٨٩';
  function toEnDigits(text) {
    if (text === null || text === undefined) return '';
    return String(text).replace(/[۰-۹٠-٩]/g, function (ch) {
      var i = FA_DIGITS.indexOf(ch);
      if (i < 0) i = AR_DIGITS.indexOf(ch);
      return String(i);
    });
  }
  function toFaDigits(text) {
    return String(text === null || text === undefined ? '' : text)
      .replace(/[0-9]/g, function (d) { return FA_DIGITS[+d]; });
  }

  function parse(text) {
    if (!text) return null;
    var m = /^\s*(\d{2,4})\s*[\/\-.]\s*(\d{1,2})\s*[\/\-.]\s*(\d{1,2})\s*$/
            .exec(toEnDigits(text));
    if (!m) return null;
    var y = +m[1], mo = +m[2], d = +m[3];
    if (y < 100) y += (y < 50 ? 1400 : 1300);
    else if (y < 1000) y += 1000;
    if (mo < 1 || mo > 12 || d < 1 || d > monthDays(y, mo)) return null;
    return [y, mo, d];
  }

  function format(jy, jm, jd) {
    return jy + '/' + String(jm).padStart(2, '0') + '/' + String(jd).padStart(2, '0');
  }

  function todayJalali() { return toJalali(new Date()); }

  /* ── the picker ─────────────────────────────────────────────────────── */
  function attach(input, options) {
    options = options || {};
    if (input.__jdp) return input.__jdp;

    var wrap = document.createElement('div');
    wrap.className = 'jdp-wrap';
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);
    input.setAttribute('autocomplete', 'off');
    input.setAttribute('inputmode', 'numeric');
    if (!input.placeholder) input.placeholder = 'مثال: ' + format.apply(null, todayJalali());

    var panel = document.createElement('div');
    panel.className = 'jdp-panel';
    wrap.appendChild(panel);

    var today = todayJalali();
    var view = { y: today[0], m: today[1] };
    var selected = parse(input.value);
    if (selected) { view.y = selected[0]; view.m = selected[1]; }

    function render() {
      var years = [];
      for (var y = today[0] - 30; y <= today[0] + 5; y++) years.push(y);

      var html = '<div class="jdp-head">'
        + '<button type="button" class="jdp-nav" data-step="-1" title="ماه قبل">›</button>'
        + '<div class="jdp-title">'
        + '<select class="jdp-month" aria-label="ماه">'
        + MONTHS.slice(1).map(function (name, i) {
            return '<option value="' + (i + 1) + '"'
              + (view.m === i + 1 ? ' selected' : '') + '>' + name + '</option>';
          }).join('')
        + '</select>'
        + '<select class="jdp-year" aria-label="سال">'
        + years.map(function (y) {
            return '<option value="' + y + '"' + (view.y === y ? ' selected' : '')
              + '>' + y + '</option>';
          }).join('')
        + '</select></div>'
        + '<button type="button" class="jdp-nav" data-step="1" title="ماه بعد">‹</button>'
        + '</div>'
        + '<div class="jdp-week">'
        + WEEK_SHORT.map(function (d, i) {
            return '<span title="' + WEEK_LONG[i] + '">' + d + '</span>';
          }).join('')
        + '</div><div class="jdp-days">';

      var lead = weekday(view.y, view.m, 1);
      for (var i = 0; i < lead; i++) html += '<div class="jdp-day other"></div>';
      var total = monthDays(view.y, view.m);
      for (var d = 1; d <= total; d++) {
        var cls = 'jdp-day';
        if (view.y === today[0] && view.m === today[1] && d === today[2]) cls += ' today';
        if (selected && selected[0] === view.y && selected[1] === view.m
            && selected[2] === d) cls += ' selected';
        if (weekday(view.y, view.m, d) === 6) cls += ' holiday';   // Friday
        html += '<div class="' + cls + '" data-day="' + d + '">' + d + '</div>';
      }
      html += '</div><div class="jdp-foot">'
        + '<button type="button" class="jdp-today">امروز</button>'
        + '<button type="button" class="jdp-clear">پاک کردن</button>'
        + '<button type="button" class="jdp-close">بستن</button></div>';
      panel.innerHTML = html;
    }

    function clampToViewport() {
      /* Keep the panel on screen when the field sits near either edge — the
         form has date inputs in the first and last grid column. */
      panel.style.marginInlineStart = '0px';
      var rect = panel.getBoundingClientRect();
      var pad = 8, shift = 0;
      if (rect.right > window.innerWidth - pad) shift = window.innerWidth - pad - rect.right;
      else if (rect.left < pad) shift = pad - rect.left;
      if (shift) {
        var rtl = getComputedStyle(panel).direction === 'rtl'
          || document.documentElement.dir === 'rtl';
        panel.style.marginInlineStart = (rtl ? -shift : shift) + 'px';
      }
    }

    function open() {
      selected = parse(input.value) || selected;
      if (selected) { view.y = selected[0]; view.m = selected[1]; }
      render();
      panel.classList.add('show');
      clampToViewport();
    }
    function close() { panel.classList.remove('show'); }

    function commit(jy, jm, jd) {
      selected = [jy, jm, jd];
      input.value = format(jy, jm, jd);
      input.dispatchEvent(new Event('change', { bubbles: true }));
      if (options.onSelect) options.onSelect(input.value, selected);
      close();
    }

    panel.addEventListener('click', function (ev) {
      var nav = ev.target.closest('.jdp-nav');
      if (nav) {
        view.m += +nav.dataset.step;
        if (view.m > 12) { view.m = 1; view.y++; }
        if (view.m < 1) { view.m = 12; view.y--; }
        render();
        return;
      }
      var day = ev.target.closest('.jdp-day[data-day]');
      if (day) { commit(view.y, view.m, +day.dataset.day); return; }
      if (ev.target.closest('.jdp-today')) { commit(today[0], today[1], today[2]); return; }
      if (ev.target.closest('.jdp-clear')) {
        input.value = '';
        selected = null;
        input.dispatchEvent(new Event('change', { bubbles: true }));
        close();
        return;
      }
      if (ev.target.closest('.jdp-close')) close();
    });

    panel.addEventListener('change', function (ev) {
      if (ev.target.classList.contains('jdp-month')) { view.m = +ev.target.value; render(); }
      if (ev.target.classList.contains('jdp-year')) { view.y = +ev.target.value; render(); }
    });

    input.addEventListener('focus', open);
    input.addEventListener('click', open);
    input.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape') close();
      if (ev.key === 'Enter') { close(); }
    });
    input.addEventListener('blur', function () {
      /* Typing is allowed too; normalise what was typed on the way out. */
      var parsed = parse(input.value);
      if (parsed) {
        selected = parsed;
        input.value = format.apply(null, parsed);
        input.classList.remove('jdp-invalid');
      } else if (input.value.trim()) {
        input.classList.add('jdp-invalid');
      } else {
        input.classList.remove('jdp-invalid');
      }
    });
    /* Close on an outside click, evaluated in the CAPTURE phase.
       The month arrows and the month/year selects rebuild panel.innerHTML in
       their own bubble-phase handler; by the time a bubble-phase document
       listener ran, ev.target would already be detached and wrap.contains()
       would report false, closing the picker on every navigation click. */
    document.addEventListener('click', function (ev) {
      if (!wrap.contains(ev.target)) close();
    }, true);

    input.__jdp = { open: open, close: close, get: function () { return selected; } };
    return input.__jdp;
  }

  global.Jalali = {
    MONTHS: MONTHS, WEEK_LONG: WEEK_LONG, WEEK_SHORT: WEEK_SHORT,
    isLeap: isLeap, monthDays: monthDays, toJalali: toJalali, toGregorian: toGregorian,
    weekday: weekday, parse: parse, format: format, today: todayJalali,
    toEnDigits: toEnDigits, toFaDigits: toFaDigits, attach: attach
  };
})(window);
