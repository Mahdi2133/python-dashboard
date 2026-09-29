/**
 * home.js — دو رفتار عمومی سایت
 *
 *   ۱. ظاهر شدن تدریجی سکشن‌ها هنگام اسکرول
 *
 * از IntersectionObserver استفاده می‌کند، نه از رویداد scroll،
 * چون کم‌هزینه‌تر است و باعث کندی صفحه نمی‌شود.
 *
 *   ۲. باز و بسته شدن نرم آکاردئون سؤالات متداول
 *
 * هر دو «افزودنی» هستند: اگر این فایل اصلاً اجرا نشود، محتوا کامل
 * دیده می‌شود و آکاردئون هم با تگ <details> مرورگر کار می‌کند —
 * فقط بدون حرکت نرم.
 *
 * اگر کاربر در سیستم‌عاملش «کاهش حرکت» را فعال کرده باشد،
 * هیچ انیمیشنی اجرا نمی‌شود.
 */
( function () {
	'use strict';

	document.documentElement.classList.remove( 'no-js' );

	var items = document.querySelectorAll( '.sm-reveal' );
	if ( ! items.length ) {
		return;
	}

	var reduced = window.matchMedia && window.matchMedia( '(prefers-reduced-motion: reduce)' ).matches;

	// اگر مرورگر قدیمی بود یا کاربر حرکت کم خواسته، اصلاً وارد حالت
	// انیمیشن نمی‌شویم؛ محتوا همان‌طور که هست دیده می‌شود.
	if ( reduced || ! ( 'IntersectionObserver' in window ) ) {
		return;
	}

	// کلاس sm-js را اسکریپت کوچکِ داخل <head> گذاشته است (در
	// functions.php، تابع sm_reveal_bootstrap). اگر به هر دلیلی آنجا
	// گذاشته نشده باشد، اینجا هم کاری نمی‌کنیم و محتوا دیده می‌ماند.
	if ( ! document.documentElement.classList.contains( 'sm-js' ) ) {
		return;
	}

	var observer = new IntersectionObserver(
		function ( entries ) {
			entries.forEach( function ( entry, i ) {
				if ( ! entry.isIntersecting ) {
					return;
				}
				// تأخیر پلکانی کوچک تا کارت‌ها پشت سر هم بیایند، نه همه با هم
				var delay = Math.min( i, 4 ) * 70;
				setTimeout( function () {
					entry.target.classList.add( 'is-visible' );
				}, delay );
				observer.unobserve( entry.target );
			} );
		},
		{ rootMargin: '0px 0px -8% 0px', threshold: 0.12 }
	);

	items.forEach( function ( el ) {
		observer.observe( el );
	} );

	/*
	 * تور ایمنی.
	 *
	 * IntersectionObserver در چند حالت ممکن است برای بعضی عنصرها
	 * هیچ‌وقت شلیک نکند: صفحه‌ای که بدون اسکرول باز می‌شود، پرش
	 * مستقیم به یک لنگر، یا مرورگری که رویداد را از دست می‌دهد.
	 * در آن حالت‌ها بخشی از محتوا برای همیشه نامرئی می‌ماند.
	 *
	 * این تایمر می‌گوید: هر چیزی که تا سه ثانیه بعد از بارگذاری
	 * هنوز ظاهر نشده، به‌هر‌حال نشان داده شود. افکت اسکرول سر جایش
	 * می‌ماند و فقط حالتِ «نامرئیِ همیشگی» ممکن نیست.
	 */
	window.setTimeout( function () {
		items.forEach( function ( el ) {
			el.classList.add( 'is-visible' );
		} );
	}, 3000 );
}() );


/* ======================================================================
   آکاردئون سؤالات متداول
   ----------------------------------------------------------------------
   عمداً یک بلوک جداست، نه ادامه‌ی بلوک بالا. بلوک بالا چند جا زودتر
   return می‌کند (مثلاً وقتی کاربر «کاهش حرکت» را روشن کرده)، و اگر
   آکاردئون داخل آن بود، در همان حالت‌ها اصلاً اجرا نمی‌شد.
   ====================================================================== */
( function () {
	'use strict';

	/*
	 * آکاردئون عمداً به کلاس sm-js (مال انیمیشن اسکرول) وابسته نیست.
	 * آن کلاس وقتی کاربر «کاهش حرکت» را روشن کرده باشد گذاشته نمی‌شود،
	 * و آن‌وقت آکاردئون هم از کار می‌افتاد — در حالی که «یکی باز،
	 * بقیه بسته» ربطی به انیمیشن ندارد و باید همیشه کار کند.
	 *
	 * کلاس sm-acc فقط انتقالِ نرم را روشن می‌کند. چون هیچ چیدمانی را
	 * عوض نمی‌کند، دیر گذاشته‌شدنش هیچ پرشی ایجاد نمی‌کند.
	 */
	var animate = ! ( window.matchMedia && window.matchMedia( '(prefers-reduced-motion: reduce)' ).matches );

	if ( animate ) {
		document.documentElement.classList.add( 'sm-acc' );
	}

	var groups = [
		{ items: '.sm-faq__item',  panel: '.sm-faq__a', solo: true  },
		{ items: '.sm-afaq__item', panel: '.sm-afaq__a', solo: false }
	];

	groups.forEach( function ( g ) {

		var list = Array.prototype.slice.call( document.querySelectorAll( g.items ) );

		if ( ! list.length ) {
			return;
		}

		list.forEach( function ( det ) {

			var head  = det.querySelector( 'summary' );
			var panel = det.querySelector( g.panel );

			if ( ! head || ! panel ) {
				return;
			}

			head.addEventListener( 'click', function ( e ) {

				e.preventDefault();

				if ( det.open ) {
					collapse( det, panel );
					return;
				}

				// آکاردئون: باز کردن یکی، بقیه را می‌بندد
				if ( g.solo ) {
					list.forEach( function ( other ) {
						if ( other !== det && other.open ) {
							collapse( other, other.querySelector( g.panel ) );
						}
					} );
				}

				expand( det, panel );
			} );
		} );
	} );

	function expand( det, panel ) {

		det.open = true;
		det.classList.remove( 'is-closing' );

		if ( ! animate ) {
			return;
		}

		var target = panel.scrollHeight;

		panel.style.height = '0px';
		// خواندن offsetHeight مرورگر را وادار می‌کند مقدار صفر را
		// واقعاً اعمال کند؛ بدون آن، انتقال اصلاً اجرا نمی‌شود.
		void panel.offsetHeight;
		panel.style.height = target + 'px';

		once( panel, function () { panel.style.height = ''; } );
	}

	function collapse( det, panel ) {

		if ( ! animate ) {
			det.open = false;
			return;
		}

		panel.style.height = panel.scrollHeight + 'px';
		void panel.offsetHeight;
		det.classList.add( 'is-closing' );
		panel.style.height = '0px';

		once( panel, function () {
			det.open = false;
			det.classList.remove( 'is-closing' );
			panel.style.height = '';
		} );
	}

	/**
	 * یک‌بار پس از پایان انتقال اجرا می‌شود.
	 * تایمر پشتیبان لازم است: اگر عنصر پنهان باشد یا انتقال لغو شود،
	 * رویداد transitionend هیچ‌وقت نمی‌آید و آکاردئون قفل می‌ماند.
	 */
	function once( el, fn ) {

		var done = false;

		function run() {
			if ( done ) { return; }
			done = true;
			el.removeEventListener( 'transitionend', handler );
			fn();
		}

		function handler( e ) {
			if ( e.target === el && 'height' === e.propertyName ) { run(); }
		}

		el.addEventListener( 'transitionend', handler );
		window.setTimeout( run, 420 );
	}

}() );


/**
 * کتابِ سه‌بعدیِ چرخان
 * -----------------------------------------------------------------
 * چرخاندنِ کتاب با موس، با انگشت و با صفحه‌کلید.
 *
 * این فایل «افزودنی» است: دو دکمه‌ی «جلد رو / جلد پشت» رادیوباتنِ
 * واقعی‌اند و با CSS خالص کار می‌کنند. اگر این اسکریپت اصلاً اجرا
 * نشود، باز هم می‌شود هر دو جلد را دید — فقط کشیدن با موس نیست.
 *
 * چند نکته‌ی ریز که عمدی‌اند:
 *
 *  • کشیدنِ عمودی روی کتاب، صفحه را اسکرول می‌کند و کتاب را
 *    نمی‌چرخاند (touch-action: pan-y). اگر جز این بود، کاربرِ
 *    موبایل روی کتاب گیر می‌کرد.
 *
 *  • بعد از رها کردن، کتاب با اصطکاک می‌چرخد و بعد روی نزدیک‌ترین
 *    جلد می‌نشیند؛ چون روی هر دو جلد متن هست و زاویه‌ی کج،
 *    متن را ناخوانا می‌کند.
 *
 *  • زاویه‌ی ry بی‌کران نگه داشته می‌شود (می‌تواند ‎-۷۴۰‎ هم بشود).
 *    اگر هر بار به بازه‌ی ‎۰..۳۶۰‎ برش می‌دادیم، کتاب موقعِ عبور از
 *    صفر یک‌بار سریع برمی‌گشت.
 */
( function () {
	'use strict';

	var books = document.querySelectorAll( '[data-sm-cover3d]' );
	if ( ! books.length ) { return; }

	var FRONT = -24;          // زاویه‌ی استراحت — جلد رو، با کمی عطف پیدا
	var TILT  = 4;            // کجیِ عمودیِ استراحت
	var SENS  = 0.42;         // درجه به ازای هر پیکسل کشیدن
	var FRIC  = 0.94;         // اصطکاکِ چرخشِ آزاد

	var calm = window.matchMedia && window.matchMedia( '(prefers-reduced-motion: reduce)' ).matches;

	Array.prototype.forEach.call( books, function ( root ) {
		setup( root );
	} );

	function setup( root ) {

		var grab = root.querySelector( '[data-sm-cover3d-grab]' );
		var body = root.querySelector( '[data-sm-cover3d-body]' );
		var rFront = root.querySelector( '.sm-cover3d__radio--front' );
		var rBack  = root.querySelector( '.sm-cover3d__radio--back' );
		var hint   = root.querySelector( '.sm-cover3d__hint' );

		if ( ! grab || ! body ) { return; }

		var ry = FRONT;
		var rx = TILT;
		var vel = 0;
		var raf = 0;
		var dragging = false;
		var touched = false;      // کاربر یک‌بار دست زده؟ (برای توقفِ حرکتِ دعوت)
		var lastX = 0, lastY = 0;
		var moved = 0;

		grab.setAttribute( 'tabindex', '0' );
		grab.setAttribute( 'role', 'group' );
		grab.setAttribute( 'aria-label', 'کتاب سه‌بعدی — با کشیدن یا کلیدهای جهت‌دار بچرخانید' );
		if ( hint && hint.id ) { grab.setAttribute( 'aria-describedby', hint.id ); }

		/* ---------- نوشتنِ زاویه ---------- */

		function apply() {
			body.style.setProperty( '--sm-ry', ry.toFixed( 2 ) + 'deg' );
			body.style.setProperty( '--sm-rx', rx.toFixed( 2 ) + 'deg' );
		}

		function live( on ) {
			body.classList.toggle( 'is-live', !! on );
			grab.classList.toggle( 'is-live', !! on );
		}

		/* گِردکردن با شکستنِ تساوی به‌سمتِ منفی.
		   Math.round در جاوااسکریپت ‎-۰٫۵‎ را ‎-۰‎ می‌کند، یعنی تساوی را
		   به‌سمتِ مثبت می‌شکند. ما عکسش را می‌خواهیم: وقتی دو مسیرِ
		   چرخش هم‌فاصله‌اند، کتاب باید از سمتِ عطف بچرخد تا طرحِ عطف
		   وسطِ حرکت دیده شود — و تا با حالتِ بدونِ جاوااسکریپت
		   (‎-۲۰۴deg‎ در CSS) یکی باشد. */
		function rnd( x ) {
			return Math.ceil( x - 0.5 );
		}

		/* نزدیک‌ترین زاویه‌ای که یکی از دو جلد رو به بیننده باشد */
		function nearest() {
			return FRONT + 180 * rnd( ( ry - FRONT ) / 180 );
		}

		/* نزدیک‌ترین زاویه برای جلدِ خواسته‌شده */
		function angleFor( face ) {
			var t = ( ry - FRONT ) / 180;
			var k = 'back' === face
				? 2 * rnd( ( t - 1 ) / 2 ) + 1
				: 2 * rnd( t / 2 );
			return FRONT + 180 * k;
		}

		/* رادیوها را با زاویه‌ی فعلی هماهنگ می‌کند (بدون شلیکِ change) */
		function syncRadio() {
			if ( ! rFront || ! rBack ) { return; }
			var k = rnd( ( ry - FRONT ) / 180 );
			var isFront = 0 === ( ( k % 2 ) + 2 ) % 2;
			rFront.checked = isFront;
			rBack.checked = ! isFront;
		}

		function glide( to ) {
			cancelAnimationFrame( raf );
			vel = 0;
			live( false );          // ترنزیشنِ CSS کار را انجام می‌دهد
			ry = to;
			rx = TILT;
			apply();
			syncRadio();
		}

		function settle() {
			glide( nearest() );
		}

		/* ---------- چرخشِ آزاد بعد از رها کردن ---------- */

		function coast() {
			vel *= FRIC;
			ry += vel;
			apply();

			if ( Math.abs( vel ) > 0.12 ) {
				raf = requestAnimationFrame( coast );
			} else {
				settle();
			}
		}

		/* ---------- کشیدن ---------- */

		function down( e ) {
			if ( e.button && 0 !== e.button ) { return; }

			touched = true;
			dragging = true;
			moved = 0;
			vel = 0;
			lastX = e.clientX;
			lastY = e.clientY;

			cancelAnimationFrame( raf );
			live( true );

			if ( grab.setPointerCapture ) {
				try { grab.setPointerCapture( e.pointerId ); } catch ( err ) {}
			}
		}

		function move( e ) {
			if ( ! dragging ) { return; }

			var dx = e.clientX - lastX;
			var dy = e.clientY - lastY;
			lastX = e.clientX;
			lastY = e.clientY;
			moved += Math.abs( dx ) + Math.abs( dy );

			var step = dx * SENS;
			ry += step;
			vel = vel * 0.6 + step * 0.4;

			// کجیِ عمودی فقط با موس. روی لمس، کشیدنِ عمودی
			// مالِ اسکرولِ صفحه است.
			if ( 'touch' !== e.pointerType ) {
				rx = Math.max( -16, Math.min( 16, rx - dy * 0.2 ) );
			}

			apply();
			if ( e.cancelable ) { e.preventDefault(); }
		}

		function up( e ) {
			if ( ! dragging ) { return; }
			dragging = false;

			if ( grab.releasePointerCapture ) {
				try { grab.releasePointerCapture( e.pointerId ); } catch ( err ) {}
			}

			// تکِ ساده بدون کشیدن = ورق زدن به جلدِ دیگر
			if ( moved < 6 ) {
				glide( angleFor( rBack && rBack.checked ? 'front' : 'back' ) );
				return;
			}

			if ( calm ) { settle(); return; }
			raf = requestAnimationFrame( coast );
		}

		function cancel() {
			if ( ! dragging ) { return; }
			dragging = false;
			settle();
		}

		grab.addEventListener( 'pointerdown', down );
		grab.addEventListener( 'pointermove', move );
		grab.addEventListener( 'pointerup', up );
		grab.addEventListener( 'pointercancel', cancel );
		grab.addEventListener( 'dragstart', function ( e ) { e.preventDefault(); } );

		/* ---------- صفحه‌کلید ---------- */

		grab.addEventListener( 'keydown', function ( e ) {
			var k = e.key;
			var hit = true;

			touched = true;
			cancelAnimationFrame( raf );
			live( false );

			if ( 'ArrowRight' === k ) { ry += 18; }
			else if ( 'ArrowLeft' === k ) { ry -= 18; }
			else if ( 'ArrowUp' === k ) { rx = Math.max( -16, rx - 6 ); }
			else if ( 'ArrowDown' === k ) { rx = Math.min( 16, rx + 6 ); }
			else if ( 'Home' === k ) { ry = angleFor( 'front' ); rx = TILT; }
			else if ( 'End' === k ) { ry = angleFor( 'back' ); rx = TILT; }
			else if ( ' ' === k || 'Enter' === k || 'Spacebar' === k ) {
				ry = angleFor( rBack && rBack.checked ? 'front' : 'back' );
				rx = TILT;
			} else { hit = false; }

			if ( ! hit ) { return; }

			e.preventDefault();
			apply();
			syncRadio();
		} );

		/* ---------- دکمه‌های «جلد رو / جلد پشت» ---------- */

		function onPick( face ) {
			return function () {
				touched = true;
				cancelAnimationFrame( raf );
				vel = 0;
				live( false );
				ry = angleFor( face );
				rx = TILT;
				apply();
			};
		}

		if ( rFront ) { rFront.addEventListener( 'change', onPick( 'front' ) ); }
		if ( rBack ) { rBack.addEventListener( 'change', onPick( 'back' ) ); }

		/* ---------- حرکتِ دعوت، یک‌بار ---------- */
		// نشان می‌دهد که این یک جعبه‌ی سه‌بعدی است، نه یک عکس.

		if ( calm || ! ( 'IntersectionObserver' in window ) ) { return; }

		var io = new IntersectionObserver( function ( entries, obs ) {
			entries.forEach( function ( en ) {
				if ( ! en.isIntersecting ) { return; }
				obs.disconnect();

				window.setTimeout( function () {
					if ( touched ) { return; }
					ry = FRONT - 40;
					apply();
				}, 500 );

				window.setTimeout( function () {
					if ( touched ) { return; }
					ry = FRONT;
					apply();
				}, 1450 );
			} );
		}, { threshold: 0.4 } );

		io.observe( root );
	}

}() );


/**
 * لایت‌باکسِ تصویرها
 * -----------------------------------------------------------------
 * هر لینکی که data-sm-lightbox داشته باشد، به‌جای باز شدن در تبِ
 * تازه، تصویرش را در همین صفحه بزرگ نشان می‌دهد.
 *
 * چرا این شکلی:
 *
 *  • خودِ لینک یک لینکِ واقعی به فایلِ تصویر است. اگر جاوااسکریپت
 *    اجرا نشود یا هنوز نرسیده باشد، کلیک همان کارِ همیشگی را
 *    می‌کند و تصویر باز می‌شود. هیچ‌وقت «هیچ اتفاقی نمی‌افتد».
 *
 *  • از <dialog> استفاده می‌کنیم نه از div. مرورگر خودش Escape،
 *    قفلِ فوکوس و پس‌زمینه را مدیریت می‌کند و لازم نیست دوباره
 *    بنویسیمشان.
 *
 *  • تصویرِ بزرگ فقط لحظه‌ی باز شدن بارگذاری می‌شود. هجده روزنامه
 *    اگر همه از اول بیایند، صفحه سنگین می‌شود.
 */
( function () {
	'use strict';

	var links = document.querySelectorAll( '[data-sm-lightbox]' );
	if ( ! links.length ) { return; }

	// اگر مرورگر <dialog> را نمی‌شناسد، لینک‌ها دست‌نخورده می‌مانند
	// و در تبِ تازه باز می‌شوند. همان رفتارِ درست است.
	if ( 'function' !== typeof HTMLDialogElement || ! HTMLDialogElement.prototype.showModal ) { return; }

	var items = Array.prototype.slice.call( links );
	var at = 0;

	var box = document.createElement( 'dialog' );
	box.className = 'sm-lightbox';
	box.innerHTML =
		'<button type="button" class="sm-lightbox__close" aria-label="بستن">&times;</button>' +
		'<button type="button" class="sm-lightbox__nav sm-lightbox__nav--prev" aria-label="قبلی">&rsaquo;</button>' +
		'<button type="button" class="sm-lightbox__nav sm-lightbox__nav--next" aria-label="بعدی">&lsaquo;</button>' +
		'<div class="sm-lightbox__zoombar">' +
			'<button type="button" class="sm-lightbox__zb" data-zoom="out" aria-label="کوچک‌نمایی">&minus;</button>' +
			'<span class="sm-lightbox__pct" aria-live="polite">۱۰۰٪</span>' +
			'<button type="button" class="sm-lightbox__zb" data-zoom="in" aria-label="بزرگ‌نمایی">+</button>' +
			'<button type="button" class="sm-lightbox__zb sm-lightbox__zb--reset" data-zoom="reset" aria-label="اندازه‌ی اصلی">&#8634;</button>' +
		'</div>' +
		'<figure class="sm-lightbox__fig">' +
			'<img class="sm-lightbox__img" alt="">' +
			'<figcaption class="sm-lightbox__cap"></figcaption>' +
		'</figure>';
	document.body.appendChild( box );

	var img = box.querySelector( '.sm-lightbox__img' );
	var cap = box.querySelector( '.sm-lightbox__cap' );
	var prev = box.querySelector( '.sm-lightbox__nav--prev' );
	var next = box.querySelector( '.sm-lightbox__nav--next' );
	var pct  = box.querySelector( '.sm-lightbox__pct' );

	/* ------------------------------------------------------------- *
	 * زوم و جابه‌جاییِ تصویر
	 * -------------------------------------------------------------
	 * روی موبایل، مرورگر خودش با دو انگشت زوم می‌کند. روی دسکتاپ
	 * چنین چیزی وجود ندارد و تصویرِ روزنامه در اندازه‌ی «جا شدن در
	 * صفحه» خوانده نمی‌شود. پس زوم را خودمان می‌سازیم:
	 *
	 *   • چرخِ موس        →  زوم حولِ همان نقطه‌ای که نشانگر است
	 *   • دوبار کلیک      →  رفت‌وبرگشت بین ۱۰۰٪ و ۲۵۰٪
	 *   • درگ             →  جابه‌جایی وقتی بزرگ شده
	 *   • + و − و ۰       →  با صفحه‌کلید
	 *   • دو انگشت        →  روی تاچ‌پد و صفحه‌ی لمسی
	 *
	 * جابه‌جایی محدود می‌شود تا تصویر از کادر بیرون نرود و کاربر
	 * صفحه‌ی خالی نبیند.
	 * ------------------------------------------------------------- */

	var MIN = 1;
	var MAX = 6;
	var sc = 1;
	var tx = 0;
	var ty = 0;

	function fa( n ) {
		return String( n ).replace( /\d/g, function ( d ) {
			return String.fromCharCode( 0x06F0 + Number( d ) );
		} );
	}

	function apply() {
		img.style.transform = 'translate(' + tx + 'px,' + ty + 'px) scale(' + sc + ')';
		box.classList.toggle( 'is-zoomed', sc > 1 );
		pct.textContent = fa( Math.round( sc * 100 ) ) + '٪';
	}

	function reset() {
		sc = 1;
		tx = 0;
		ty = 0;
		img.style.transition = '';
		apply();
	}

	/* تصویر نباید آن‌قدر برود که کادرش از وسطِ صفحه خارج شود. */
	function clamp() {
		var r = img.getBoundingClientRect();
		var over = function ( size, view ) {
			return Math.max( 0, ( size - view ) / 2 );
		};
		var bx = over( r.width, box.clientWidth );
		var by = over( r.height, box.clientHeight );
		tx = Math.max( -bx, Math.min( bx, tx ) );
		ty = Math.max( -by, Math.min( by, ty ) );
	}

	/*
	 * زوم حولِ یک نقطه. (cx,cy) مختصاتِ صفحه است. فاصله‌ی آن نقطه
	 * تا مرکزِ تصویر به همان نسبتِ بزرگ‌نمایی کشیده می‌شود، پس همان
	 * نقطه زیرِ نشانگر می‌ماند.
	 */
	function zoomAt( next, cx, cy ) {
		next = Math.max( MIN, Math.min( MAX, next ) );
		if ( next === sc ) { return; }

		var r  = img.getBoundingClientRect();
		var mx = r.left + r.width / 2;
		var my = r.top + r.height / 2;
		var k  = next / sc;

		tx = ( tx - ( cx - mx ) ) * k + ( cx - mx );
		ty = ( ty - ( cy - my ) ) * k + ( cy - my );
		sc = next;

		if ( 1 === sc ) { tx = 0; ty = 0; }
		apply();
		clamp();
		apply();
	}

	function center() {
		var r = box.getBoundingClientRect();
		return [ r.left + r.width / 2, r.top + r.height / 2 ];
	}

	/* ---- چرخِ موس و ژستِ دو انگشتِ تاچ‌پد ---- */
	box.addEventListener( 'wheel', function ( e ) {
		e.preventDefault();
		// ctrlKey روی تاچ‌پد یعنی ژستِ pinch — قدمِ ریزتری می‌خواهد.
		var step = e.ctrlKey ? 0.01 : 0.0022;
		zoomAt( sc * Math.exp( -e.deltaY * step ), e.clientX, e.clientY );
	}, { passive: false } );

	/* ---- دوبار کلیک ---- */
	img.addEventListener( 'dblclick', function ( e ) {
		e.preventDefault();
		img.style.transition = 'transform .25s ease';
		zoomAt( sc > 1 ? 1 : 2.5, e.clientX, e.clientY );
		setTimeout( function () { img.style.transition = ''; }, 280 );
	} );

	/* ---- درگ برای جابه‌جایی ---- */
	var drag = null;

	img.addEventListener( 'pointerdown', function ( e ) {
		if ( sc <= 1 ) { return; }
		e.preventDefault();
		drag = { x: e.clientX, y: e.clientY, tx: tx, ty: ty };
		img.setPointerCapture( e.pointerId );
	} );

	img.addEventListener( 'pointermove', function ( e ) {
		if ( ! drag ) { return; }
		tx = drag.tx + ( e.clientX - drag.x );
		ty = drag.ty + ( e.clientY - drag.y );
		clamp();
		apply();
	} );

	[ 'pointerup', 'pointercancel' ].forEach( function ( evt ) {
		img.addEventListener( evt, function () { drag = null; } );
	} );

	/* ---- دکمه‌های نوارِ زوم ---- */
	box.querySelector( '.sm-lightbox__zoombar' ).addEventListener( 'click', function ( e ) {
		var btn = e.target.closest( '[data-zoom]' );
		if ( ! btn ) { return; }
		var c = center();
		img.style.transition = 'transform .2s ease';
		if ( 'reset' === btn.getAttribute( 'data-zoom' ) ) {
			reset();
		} else {
			zoomAt( 'in' === btn.getAttribute( 'data-zoom' ) ? sc * 1.5 : sc / 1.5, c[0], c[1] );
		}
		setTimeout( function () { img.style.transition = ''; }, 230 );
	} );

	function show( i ) {
		at = ( i + items.length ) % items.length;
		var el = items[ at ];
		reset();
		box.classList.add( 'is-loading' );
		img.src = el.getAttribute( 'href' );
		img.alt = el.getAttribute( 'data-sm-caption' ) || '';
		cap.textContent = el.getAttribute( 'data-sm-caption' ) || '';
		var many = items.length > 1;
		prev.hidden = ! many;
		next.hidden = ! many;
	}

	img.addEventListener( 'load', function () { box.classList.remove( 'is-loading' ); } );
	img.addEventListener( 'error', function () { box.classList.remove( 'is-loading' ); } );

	items.forEach( function ( el, i ) {
		el.addEventListener( 'click', function ( e ) {
			// کلیکِ وسط یا با Ctrl را دست نمی‌زنیم؛ کاربر عمداً
			// می‌خواهد در تبِ تازه باز شود.
			if ( e.metaKey || e.ctrlKey || e.shiftKey || 1 === e.button ) { return; }
			e.preventDefault();
			show( i );
			box.showModal();
		} );
	} );

	box.querySelector( '.sm-lightbox__close' ).addEventListener( 'click', function () { box.close(); } );
	prev.addEventListener( 'click', function () { show( at - 1 ); } );
	next.addEventListener( 'click', function () { show( at + 1 ); } );

	// کلیک روی پس‌زمینه = بستن. کلیک روی خودِ تصویر نه.
	box.addEventListener( 'click', function ( e ) {
		if ( e.target === box ) { box.close(); }
	} );

	box.addEventListener( 'keydown', function ( e ) {
		var c;

		if ( 'ArrowLeft' === e.key ) { e.preventDefault(); show( at + 1 ); return; }
		if ( 'ArrowRight' === e.key ) { e.preventDefault(); show( at - 1 ); return; }

		if ( '+' === e.key || '=' === e.key ) {
			e.preventDefault();
			c = center();
			zoomAt( sc * 1.5, c[0], c[1] );
			return;
		}

		if ( '-' === e.key || '_' === e.key ) {
			e.preventDefault();
			c = center();
			zoomAt( sc / 1.5, c[0], c[1] );
			return;
		}

		if ( '0' === e.key ) { e.preventDefault(); reset(); }

		/*
		 * وقتی تصویر بزرگ شده، جهت‌های بالا و پایین باید تصویر را
		 * جابه‌جا کنند نه صفحه را.
		 */
		if ( sc > 1 && ( 'ArrowUp' === e.key || 'ArrowDown' === e.key ) ) {
			e.preventDefault();
			ty += ( 'ArrowUp' === e.key ? 60 : -60 );
			clamp();
			apply();
		}
	} );

	box.addEventListener( 'close', function () {
		img.removeAttribute( 'src' );
		reset();
	} );

}() );


/**
 * شمارنده‌های صفحه‌ی سعید نمازی
 * -----------------------------------------------------------------
 * هر عنصری که data-sm-count داشته باشد، وقتی وارد صفحه شد از صفر
 * تا عددِ خودش بالا می‌رود.
 *
 * چرا این شکلی:
 *
 *  • عددِ نهایی از همان اول داخلِ HTML هست. جاوااسکریپت فقط آن را
 *    موقتاً صفر می‌کند و بالا می‌برد. اگر این فایل اصلاً اجرا نشود،
 *    کاربر عددِ درست را می‌بیند — نه صفر، نه جای خالی.
 *
 *  • پسوند (+ یا ٪) و جداکننده‌ی هزارگان از خودِ متنِ اولیه خوانده
 *    می‌شوند، نه از تنظیمات. پس اگر روزی متن عوض شد، شمارنده هم
 *    خودبه‌خود همان شکل را می‌گیرد.
 *
 *  • اگر کاربر «کاهش حرکت» را روشن کرده باشد، هیچ شمارشی انجام
 *    نمی‌شود و عدد ثابت می‌ماند.
 */
( function () {
	'use strict';

	var nodes = document.querySelectorAll( '[data-sm-count]' );
	if ( ! nodes.length ) { return; }

	var still = window.matchMedia && window.matchMedia( '(prefers-reduced-motion: reduce)' ).matches;
	if ( still || ! window.IntersectionObserver ) { return; }

	var DUR = 1400;

	function run( el ) {
		var end = parseInt( el.getAttribute( 'data-sm-count' ), 10 );
		if ( isNaN( end ) || end <= 0 ) { return; }

		// متنِ اولیه را می‌شکافیم: عددِ قالب‌بندی‌شده + هر چیزی که بعدش آمده.
		var raw  = el.textContent.trim();
		var tail = raw.replace( /^[\d.,٫٬۰-۹٠-٩\s]+/, '' );

		// آیا عدد جداکننده‌ی هزارگان دارد؟ اگر بله، در شمارش هم بگذاریم.
		var grouped = /[,٬]/.test( raw );
		var sep     = /٬/.test( raw ) ? '٬' : ',';

		// رقم‌ها فارسی‌اند یا لاتین؟ از خودِ متن می‌فهمیم.
		var farsi = /[۰-۹]/.test( raw );

		function fmt( n ) {
			var s = String( n );
			if ( grouped ) { s = s.replace( /\B(?=(\d{3})+(?!\d))/g, sep ); }
			if ( farsi ) {
				s = s.replace( /\d/g, function ( d ) {
					return String.fromCharCode( 0x06F0 + Number( d ) );
				} );
			}
			return s + tail;
		}

		var t0 = 0;

		function step( now ) {
			if ( ! t0 ) { t0 = now; }
			var p = Math.min( 1, ( now - t0 ) / DUR );
			// easeOutCubic — تند شروع می‌شود و نرم می‌ایستد.
			var e = 1 - Math.pow( 1 - p, 3 );
			el.textContent = fmt( Math.round( end * e ) );
			if ( p < 1 ) { requestAnimationFrame( step ); }
		}

		requestAnimationFrame( step );
	}

	var io = new IntersectionObserver( function ( entries ) {
		entries.forEach( function ( entry ) {
			if ( ! entry.isIntersecting ) { return; }
			io.unobserve( entry.target );
			run( entry.target );
		} );
	}, { threshold: 0.4 } );

	Array.prototype.forEach.call( nodes, function ( el ) { io.observe( el ); } );

}() );
