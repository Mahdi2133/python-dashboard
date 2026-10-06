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

		var nav     = form.querySelector( '.sm-steps' );
		var items   = nav ? Array.prototype.slice.call( nav.querySelectorAll( '.sm-steps__item' ) ) : [];
		var btnOld  = form.querySelector( '.sm-form__next' );
		var btnPrev = form.querySelector( '.sm-form__prev' );
		var btnMain = form.querySelector( '.sm-form__submit' );
		var consent = form.querySelector( '.sm-field--consent' );
		var box     = consent ? consent.querySelector( 'input[type="checkbox"]' ) : null;
		var current = 0;

		var LAST = steps.length - 1;
		var TXT_NEXT = form.getAttribute( 'data-next-label' ) || 'مرحله بعد';
		var TXT_SEND = form.getAttribute( 'data-send-label' ) || ( btnMain ? btnMain.textContent : 'ارسال' );
		var TXT_TICK = form.getAttribute( 'data-consent-msg' ) || 'برای ارسال، لطفاً این مورد را تأیید کنید.';

		// دکمه‌ی «مرحله بعد»ِ قدیمی اگر هنوز در صفحه باشد، برداشته می‌شود.
		if ( btnOld ) { btnOld.parentNode.removeChild( btnOld ); }

		if ( nav ) {
			nav.hidden = false;
			nav.removeAttribute( 'aria-hidden' );
		}

		/* پیامِ خطای رضایت — یک بار ساخته می‌شود و کنارِ خودِ تیک می‌نشیند. */
		var tickMsg = null;

		function sayTick( on ) {
			if ( ! consent ) { return; }

			if ( ! tickMsg ) {
				tickMsg = document.createElement( 'p' );
				tickMsg.className = 'sm-form__tickmsg';
				tickMsg.setAttribute( 'role', 'alert' );
				tickMsg.textContent = TXT_TICK;
				consent.appendChild( tickMsg );
			}

			tickMsg.hidden = ! on;
			consent.classList.toggle( 'is-missing', !! on );
		}

		function show( i, quiet ) {

			current = Math.max( 0, Math.min( i, LAST ) );

			steps.forEach( function ( s, n ) {
				s.hidden = n !== current;
			} );

			items.forEach( function ( li, n ) {
				li.classList.toggle( 'is-current', n === current );
				li.classList.toggle( 'is-done', n < current );
			} );

			var last = current === LAST;

			if ( btnPrev ) { btnPrev.hidden = current === 0; }
			if ( consent ) { consent.hidden = ! last; }

			/*
			 * همان یک دکمه، با برچسبِ کارِ همان گام. در گامِ آخر هم
			 * ظاهرش فرق می‌کند تا معلوم باشد این «ارسال» است نه «بعدی».
			 */
			if ( btnMain ) {
				btnMain.textContent = last ? TXT_SEND : TXT_NEXT;
				btnMain.classList.toggle( 'sm-form__submit--send', last );
			}

			if ( ! last ) { sayTick( false ); }

			// اولین فیلد گام تازه را در دید کاربر بیاور
			var head = steps[ current ].querySelector( '.sm-fieldset__legend' );
			if ( head && form.dataset.smStarted && ! quiet ) {
				head.scrollIntoView( { behavior: 'smooth', block: 'center' } );
			}
			form.dataset.smStarted = '1';
		}

		/**
		 * فیلدهای یک گام را اعتبارسنجی می‌کند.
		 *
		 * چرا گام‌به‌گام و نه کلِ فرم: checkValidity روی کل فرم،
		 * فیلدهای پنهانِ گام‌های دیگر را هم می‌بیند و مرورگر پیام خطا
		 * را روی چیزی می‌گذارد که کاربر اصلاً نمی‌بیند — یعنی یک
		 * خطای نامرئی که هیچ‌وقت رفع نمی‌شود.
		 */
		function validStep( n, focus ) {

			var fields = steps[ n ].querySelectorAll( 'input, select, textarea' );
			var ok     = true;

			Array.prototype.forEach.call( fields, function ( el ) {
				if ( el.checkValidity() ) { return; }
				if ( ok && focus ) { el.reportValidity(); }
				ok = false;
			} );

			return ok;
		}

		/**
		 * پیش از ارسالِ واقعی: همه‌ی گام‌ها، بعد تیکِ رضایت.
		 * اگر گامی ایراد داشت، همان گام باز می‌شود — نه اینکه فرم
		 * بی‌صدا برود و سرور ردش کند و کاربر به گامِ یک پرت شود.
		 */
		function readyToSend() {

			for ( var n = 0; n <= LAST; n++ ) {
				if ( validStep( n, false ) ) { continue; }
				show( n );
				validStep( n, true );
				return false;
			}

			if ( box && ! box.checked ) {
				sayTick( true );
				box.focus();
				consent.scrollIntoView( { behavior: 'smooth', block: 'center' } );
				return false;
			}

			sayTick( false );
			return true;
		}

		/*
		 * تنها نقطه‌ی تصمیم. دکمه از نوعِ submit است، پس چه با موس
		 * زده شود چه با Enter، از همین‌جا رد می‌شود.
		 */
		form.addEventListener( 'submit', function ( e ) {

			if ( current < LAST ) {
				e.preventDefault();
				if ( validStep( current, true ) ) { show( current + 1 ); }
				return;
			}

			if ( ! readyToSend() ) { e.preventDefault(); }
		} );

		if ( btnPrev ) {
			btnPrev.addEventListener( 'click', function () { show( current - 1 ); } );
		}

		if ( box ) {
			box.addEventListener( 'change', function () {
				if ( box.checked ) { sayTick( false ); }
			} );
		}

		items.forEach( function ( li, n ) {
			li.addEventListener( 'click', function () {
				if ( n < current ) { show( n ); }
			} );
		} );

		/*
		 * اگر سرور فرم را رد کرده باشد (sm=err)، از گامِ آخر شروع
		 * می‌کنیم. کاربر همان‌جا بود؛ پرت کردنش به گامِ یک یعنی از
		 * نو شروع کند.
		 */
		show( form.hasAttribute( 'data-open-last' ) ? LAST : 0, true );
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

		/* ------------------------------------------------------------- *
		 * نمره‌گذاری
		 * -------------------------------------------------------------
		 * فقط پرسش‌های data-axis="friction" نمره دارند — پنج پرسشِ
		 * بخشِ دوم، هرکدام ۰ تا ۲، یعنی حداکثر ۱۰.
		 *
		 * دو پرسشِ بخشِ اول (context) و پرسشِ بخشِ سوم (time) عمداً
		 * نمره نمی‌گیرند: اولی‌ها جنسِ کار را مشخص می‌کنند و سومی
		 * فقط تعیین می‌کند راهکار در چه اندازه‌ای از تقویم جا شود.
		 * ------------------------------------------------------------- */

		var sum      = 0;
		var max      = 0;
		var timePick = null;
		var trail    = [];

		Array.prototype.forEach.call( quiz.querySelectorAll( '.sm-quiz__q' ), function ( q ) {

			var picked = q.querySelector( 'input[type="radio"]:checked' );
			if ( ! picked ) { return; }

			var v  = parseInt( picked.value, 10 ) || 0;
			var no = parseInt( q.dataset.no, 10 ) || 0;

			trail.push( no + ':' + v );

			if ( 'friction' === q.dataset.axis ) {
				sum += v;
				// بیشترین مقدارِ ممکنِ همین پرسش، نه یک عددِ ثابت.
				max += q.querySelectorAll( 'input[type="radio"]' ).length - 1;
			}

			if ( 'time' === q.dataset.axis ) { timePick = v; }
		} );

		var zone = sum >= TEXT.cutRed ? 'red' : ( sum >= TEXT.cutAmber ? 'amber' : 'green' );
		var pct  = max ? Math.round( ( sum / max ) * 100 ) : 0;
		var z    = TEXT.zones[ zone ];

		set( 'sm-result-badge', z.label );
		set( 'sm-result-title', z.title );
		set( 'sm-result-text', z.text );
		set( 'sm-result-num', 'شاخص اصطکاک متابولیک: ' + fa( sum ) + ' از ' + fa( max ) );

		// «گام بعدی» فقط در وضعیت قرمز متن دارد.
		var nextEl = document.getElementById( 'sm-result-next' );

		if ( nextEl ) {
			nextEl.textContent = z.next || '';
			nextEl.hidden = ! z.next;
		}

		// جمله‌ی پایانی بر اساس گلوگاه زمانی
		var timeEl = document.getElementById( 'sm-result-time' );

		if ( timeEl ) {
			var note = ( null !== timePick && TEXT.timeNotes ) ? TEXT.timeNotes[ String( timePick ) ] : '';
			timeEl.textContent = note || '';
			timeEl.hidden = ! note;
		}

		result.className = 'sm-result sm-result--' + zone;

		var fill = document.getElementById( 'sm-result-fill' );
		if ( fill ) { fill.style.width = pct + '%'; }

		/*
		 * نتیجه را به فرمِ تماس هم می‌دهیم تا وقتی کاربر فرم را فرستاد،
		 * ثبت شود که با چه وضعیتی تماس گرفته است.
		 */
		fill = document.getElementById( 'sm-audit-zone' );
		if ( fill ) { fill.value = zone; }

		fill = document.getElementById( 'sm-audit-score' );
		if ( fill ) { fill.value = String( sum ); }

		fill = document.getElementById( 'sm-audit-answers' );
		if ( fill ) { fill.value = trail.join( '|' ); }

		// دکمه‌ی فرم، متنِ همان وضعیت را می‌گیرد.
		var btn = document.getElementById( 'sm-audit-submit' );
		if ( btn && z.cta ) { btn.textContent = z.cta; }

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
