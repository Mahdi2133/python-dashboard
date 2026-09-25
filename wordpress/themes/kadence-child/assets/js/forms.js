/**
 * forms.js — سه رفتار
 *
 *   ۱. فرم /smp/start/ را به سه گام تقسیم می‌کند
 *   ۲. پاپ‌آپ هماهنگی پرداخت در /order/ را باز و بسته می‌کند
 *   ۳. نتیجه‌ی خودارزیابی /smp/check/ را محاسبه و نمایش می‌دهد
 *
 * هر دو «افزودنی» هستند: اگر این فایل اصلاً اجرا نشود، فرم درخواست
 * به‌صورت یک صفحه‌ی بلند و کاملاً قابل ارسال باقی می‌ماند و صفحه‌ی
 * خودارزیابی هم پرسش‌هایش را نشان می‌دهد. هیچ محتوایی پنهان نمی‌شود.
 */
( function () {
	'use strict';

	/* ==================================================================
	   ۱ — فرم چندمرحله‌ای
	   ================================================================== */

	var form = document.querySelector( '.sm-form' );

	if ( form ) {
		multiStep( form );
	}

	function multiStep( form ) {

		var steps = Array.prototype.slice.call( form.querySelectorAll( '.sm-fieldset' ) );

		if ( steps.length < 2 ) {
			return;
		}

		var nav      = form.querySelector( '.sm-steps' );
		var items    = nav ? Array.prototype.slice.call( nav.querySelectorAll( '.sm-steps__item' ) ) : [];
		var btnNext  = form.querySelector( '.sm-form__next' );
		var btnPrev  = form.querySelector( '.sm-form__prev' );
		var btnSend  = form.querySelector( '.sm-form__submit' );
		var consent  = form.querySelector( '.sm-field--consent' );
		var current  = 0;

		if ( nav ) {
			nav.hidden = false;
			nav.removeAttribute( 'aria-hidden' );
		}

		function show( i ) {

			current = Math.max( 0, Math.min( i, steps.length - 1 ) );

			steps.forEach( function ( s, n ) {
				s.hidden = n !== current;
			} );

			items.forEach( function ( li, n ) {
				li.classList.toggle( 'is-current', n === current );
				li.classList.toggle( 'is-done', n < current );
			} );

			var last = current === steps.length - 1;

			if ( btnPrev ) { btnPrev.hidden = current === 0; }
			if ( btnNext ) { btnNext.hidden = last; }
			if ( btnSend ) { btnSend.hidden = ! last; }
			if ( consent ) { consent.hidden = ! last; }

			// اولین فیلد گام تازه را در دید کاربر بیاور
			var head = steps[ current ].querySelector( '.sm-fieldset__legend' );
			if ( head && form.dataset.smStarted ) {
				head.scrollIntoView( { behavior: 'smooth', block: 'center' } );
			}
			form.dataset.smStarted = '1';
		}

		/**
		 * فقط فیلدهای گام جاری را اعتبارسنجی می‌کند.
		 * checkValidity روی کل فرم، فیلدهای پنهانِ گام‌های بعدی را هم
		 * می‌بیند و پیام خطا روی چیزی می‌گذارد که کاربر اصلاً نمی‌بیند.
		 */
		function stepValid() {

			var fields = steps[ current ].querySelectorAll( 'input, select, textarea' );
			var ok     = true;

			Array.prototype.forEach.call( fields, function ( el ) {
				if ( ! el.checkValidity() ) {
					if ( ok ) { el.reportValidity(); }
					ok = false;
				}
			} );

			return ok;
		}

		if ( btnNext ) {
			btnNext.addEventListener( 'click', function () {
				if ( stepValid() ) { show( current + 1 ); }
			} );
		}

		if ( btnPrev ) {
			btnPrev.addEventListener( 'click', function () { show( current - 1 ); } );
		}

		items.forEach( function ( li, n ) {
			li.addEventListener( 'click', function () {
				if ( n < current ) { show( n ); }
			} );
		} );

		show( 0 );
	}


	/* ==================================================================
	   ۲ — پاپ‌آپ هماهنگی پرداخت
	   ================================================================== */

	var sheet = document.getElementById( 'sm-paysheet' );

	if ( sheet ) {
		paysheet( sheet );
	}

	function paysheet( sheet ) {

		var openers = document.querySelectorAll( '[data-sm-paysheet="open"]' );

		function show() {
			// showModal پس‌زمینه را قفل می‌کند و Escape را خودش می‌گیرد
			if ( sheet.showModal ) {
				if ( ! sheet.open ) { sheet.showModal(); }
			} else {
				sheet.setAttribute( 'open', '' );   // مرورگر قدیمی
			}
		}

		Array.prototype.forEach.call( openers, function ( btn ) {
			btn.addEventListener( 'click', show );
		} );

		// کلیک روی فضای خالی پشت پاپ‌آپ آن را می‌بندد
		sheet.addEventListener( 'click', function ( e ) {
			if ( e.target === sheet && sheet.close ) { sheet.close(); }
		} );

		// چون کاربر تازه سفارش ثبت کرده، قدم بعدی همین است —
		// پس خودش باز می‌شود، ولی با کمی مکث تا صفحه جا بیفتد.
		window.setTimeout( show, 700 );
	}

	/* دکمه‌ی کپی — روی هر عنصری با data-sm-copy کار می‌کند */
	document.addEventListener( 'click', function ( e ) {

		var btn = e.target.closest ? e.target.closest( '[data-sm-copy]' ) : null;

		if ( ! btn ) {
			return;
		}

		var text = btn.getAttribute( 'data-sm-copy' );
		var done = btn.getAttribute( 'data-sm-done' ) || 'کپی شد';
		var was  = btn.textContent;

		function ok() {
			btn.textContent = done;
			btn.classList.add( 'is-copied' );
			window.setTimeout( function () {
				btn.textContent = was;
				btn.classList.remove( 'is-copied' );
			}, 1800 );
		}

		if ( navigator.clipboard && navigator.clipboard.writeText ) {
			navigator.clipboard.writeText( text ).then( ok, fallback );
		} else {
			fallback();
		}

		function fallback() {
			// روی http یا مرورگر قدیمی، clipboard در دسترس نیست
			var tmp = document.createElement( 'textarea' );
			tmp.value = text;
			tmp.setAttribute( 'readonly', '' );
			tmp.style.position = 'fixed';
			tmp.style.opacity = '0';
			document.body.appendChild( tmp );
			tmp.select();
			try { document.execCommand( 'copy' ); ok(); } catch ( err ) { /* بی‌صدا */ }
			document.body.removeChild( tmp );
		}
	} );


	/* ==================================================================
	   ۳ — خودارزیابی
	   ================================================================== */

	var quiz = document.getElementById( 'sm-quiz' );

	if ( ! quiz ) {
		return;
	}

	var dataTag = document.getElementById( 'sm-quiz-data' );
	var TEXT    = {};

	try {
		TEXT = JSON.parse( dataTag.textContent );
	} catch ( e ) {
		return;
	}

	var counter = quiz.querySelector( '.sm-quiz__count' );
	var warn    = quiz.querySelector( '.sm-quiz__warn' );
	var total   = counter ? parseInt( counter.dataset.total, 10 ) : 0;
	var result  = document.getElementById( 'sm-result' );

	function answered() {
		var seen = {};
		Array.prototype.forEach.call(
			quiz.querySelectorAll( 'input[type="radio"]:checked' ),
			function ( el ) { seen[ el.name ] = true; }
		);
		return Object.keys( seen ).length;
	}

	function updateCount() {
		if ( ! counter ) { return; }
		var n = answered();
		counter.textContent = 'پاسخ داده‌شده: ' + fa( n ) + ' از ' + fa( total );
	}

	function fa( n ) {
		return String( n ).replace( /[0-9]/g, function ( d ) {
			return '۰۱۲۳۴۵۶۷۸۹'[ d ];
		} );
	}

	quiz.addEventListener( 'change', function () {
		updateCount();
		if ( warn ) { warn.hidden = true; }
	} );

	quiz.addEventListener( 'reset', function () {
		window.setTimeout( function () {
			updateCount();
			if ( result ) { result.hidden = true; }
			if ( warn ) { warn.hidden = true; }
		}, 0 );
	} );

	quiz.addEventListener( 'submit', function ( e ) {

		e.preventDefault();

		if ( answered() < total ) {
			if ( warn ) {
				warn.hidden = false;
				warn.scrollIntoView( { behavior: 'smooth', block: 'center' } );
			}
			return;
		}

		var sum     = 0;
		var max     = 0;
		var rhythm  = 0;
		var glucose = 0;

		Array.prototype.forEach.call( quiz.querySelectorAll( '.sm-quiz__q' ), function ( q ) {

			var picked = q.querySelector( 'input[type="radio"]:checked' );

			if ( ! picked ) { return; }

			var v = parseInt( picked.value, 10 ) || 0;

			sum += v;
			max += 3;

			if ( 'rhythm' === q.dataset.axis )  { rhythm  += v; }
			if ( 'glucose' === q.dataset.axis ) { glucose += v; }
		} );

		var pct  = max ? Math.round( ( sum / max ) * 100 ) : 0;
		var zone = pct < 34 ? 'green' : ( pct < 62 ? 'amber' : 'red' );

		// اگر اختلاف دو کفه کمتر از ۲۰٪ باشد، «ترکیبی» است
		var leak = 'both';
		var gap  = Math.abs( rhythm - glucose );

		if ( gap > Math.max( rhythm, glucose ) * 0.2 ) {
			leak = rhythm > glucose ? 'rhythm' : 'glucose';
		}

		var z = TEXT.zones[ zone ];
		var l = TEXT.leaks[ leak ];

		set( 'sm-result-badge', z.label );
		set( 'sm-result-title', z.title );
		set( 'sm-result-text', z.text );
		set( 'sm-result-leaktitle', l.title );
		set( 'sm-result-leaktext', l.text );
		set( 'sm-result-book', l.book );

		result.className = 'sm-result sm-result--' + zone;

		var fill = document.getElementById( 'sm-result-fill' );
		if ( fill ) { fill.style.width = pct + '%'; }

		result.hidden = false;
		result.focus();
		result.scrollIntoView( { behavior: 'smooth', block: 'start' } );
	} );

	function set( id, text ) {
		var el = document.getElementById( id );
		if ( el ) { el.textContent = text; }
	}

	updateCount();
}() );
