<?php
/**
 * توابع کمکی قالب.
 *
 * این فایل را دست نزنید مگر بخواهید رفتار قالب را عوض کنید.
 * برای ویرایش متن‌ها به inc/content-home.php بروید.
 *
 * @package saadatmehr
 */

defined( 'ABSPATH' ) || exit;


/**
 * محتوای صفحه‌ی اصلی را می‌خواند و در حافظه نگه می‌دارد.
 *
 * @return array
 */
function sm_home_content() {

	static $content = null;

	if ( null === $content ) {
		$file    = get_stylesheet_directory() . '/inc/content-home.php';
		$content = file_exists( $file ) ? require $file : array();
	}

	return $content;
}


/**
 * نشانی یک فایل تصویری داخل پوشه‌ی assets/images را برمی‌گرداند.
 *
 * @param string $file نام فایل، مثلاً 'logo-seal.png'.
 * @return string
 */
function sm_img( $file ) {
	return get_stylesheet_directory_uri() . '/assets/images/' . ltrim( $file, '/' );
}


/**
 * نام واقعی فایل تصویر را پیدا می‌کند — با هر پسوندی که باشد.
 *
 * دو کار می‌کند:
 *
 *   ۱. اگر فایل اصلاً نباشد، رشته‌ی خالی برمی‌گرداند تا به‌جای
 *      «تصویر شکسته»، جایگزین برنددار نمایش داده شود.
 *
 *   ۲. پسوند برایش مهم نیست. اگر در فایل محتوا نوشته شده
 *      'hossein.webp' ولی شما 'hossein.jpg' آپلود کرده‌اید،
 *      خودش پیدایش می‌کند. این عمدی است: کاربر نباید مجبور باشد
 *      فرمت عکسش را عوض کند یا کد را دست بزند.
 *
 * @param string $file نام فایل نسبت به assets/images/.
 * @return string نام فایل موجود، یا رشته‌ی خالی.
 */
function sm_img_find( $file ) {

	$file = ltrim( (string) $file, '/' );

	if ( '' === $file ) {
		return '';
	}

	$dir = get_stylesheet_directory() . '/assets/images/';

	if ( file_exists( $dir . $file ) ) {
		return $file;
	}

	$base = preg_replace( '/\.[A-Za-z0-9]+$/', '', $file );

	foreach ( array( 'webp', 'jpg', 'jpeg', 'png', 'avif', 'JPG', 'PNG', 'WEBP' ) as $ext ) {
		if ( file_exists( $dir . $base . '.' . $ext ) ) {
			return $base . '.' . $ext;
		}
	}

	return '';
}


/**
 * آیا این تصویر (با هر پسوندی) روی سرور هست؟
 *
 * @param string $file نام فایل نسبت به assets/images/.
 * @return bool
 */
function sm_has_img( $file ) {
	return '' !== sm_img_find( $file );
}


/**
 * نشانی کامل تصویر، یا رشته‌ی خالی اگر فایل نباشد.
 *
 * @param string $file نام فایل نسبت به assets/images/.
 * @return string
 */
function sm_img_src( $file ) {

	$found = sm_img_find( $file );

	return $found ? sm_img( $found ) : '';
}


/**
 * آیکون‌های خطی سکشن دوم.
 *
 * آیکون‌ها به‌صورت SVG درون‌خطی چاپ می‌شوند تا درخواست HTTP اضافه
 * نداشته باشیم و رنگشان از CSS کنترل شود.
 *
 * @param string $name نام آیکون.
 */
function sm_icon( $name ) {

	$paths = array(
		// نمودار — ارزیابی بیومتریک
		'chart'  => '<path d="M4 20V10M10 20V4M16 20v-7M22 20V8"/>',
		// نشان — سال‌های تجربه
		'award'  => '<circle cx="13" cy="9" r="6"/><path d="m9.5 14.2-1.3 7.3 4.8-2.6 4.8 2.6-1.3-7.3"/>',
		// افراد — تعداد همراهان
		'users'  => '<circle cx="10" cy="8" r="3.6"/><path d="M3.5 20.5a6.7 6.7 0 0 1 13 0"/><path d="M17.5 5.2a3.4 3.4 0 0 1 0 6.6M19 20.5a6.6 6.6 0 0 0-2.2-4.6"/>',
		// نمایشگر — اجرای آنلاین
		'screen' => '<rect x="2.5" y="4" width="20" height="13" rx="2"/><path d="M9 21h8M12.5 17v4"/>',
		// مغز — مهندسی رفتار
		'brain'  => '<path d="M13 4a3 3 0 0 1 5 2.2A3 3 0 0 1 20 12a3 3 0 0 1-2 5.6A3 3 0 0 1 13 20Z"/><path d="M13 4a3 3 0 0 0-5 2.2A3 3 0 0 0 6 12a3 3 0 0 0 2 5.6A3 3 0 0 0 13 20"/><path d="M13 4v16"/>',
		// سلول — تغذیه سلولی
		'cell'   => '<circle cx="13" cy="12" r="9"/><circle cx="13" cy="12" r="3.2"/><path d="M8 6.5 9.8 8.6M18 6.5l-1.8 2.1M8 17.5l1.8-2.1M18 17.5l-1.8-2.1"/>',
		// سپر — شاخص‌های NCD
		'shield' => '<path d="M13 3 5 6v6c0 4.6 3.3 8.2 8 9 4.7-.8 8-4.4 8-9V6Z"/><path d="m9.6 12.2 2.3 2.3 4.5-4.6"/>',
	);

	if ( ! isset( $paths[ $name ] ) ) {
		return;
	}

	// width و height روی خود تگ — دلیلش در inc/footer.php توضیح داده شده
	printf(
		'<svg viewBox="0 0 26 24" width="20" height="18" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">%s</svg>',
		$paths[ $name ] // phpcs:ignore WordPress.Security.EscapeOutput -- مقادیر ثابت و داخلی هستند.
	);
}


/**
 * پنل بیومتریک سکشن سوم.
 *
 * جایگزین موقت تصویر است. وقتی فایل عکس واقعی رسید و در
 * content-home.php ثبت شد، این تابع دیگر فراخوانی نمی‌شود.
 *
 * شاخص‌ها نمونه‌ی نمایشی‌اند و عمداً «نمونه» برچسب خورده‌اند تا
 * با داده‌ی واقعی بیمار اشتباه گرفته نشوند.
 */
function sm_biometric_panel() {

	$rows = array(
		array( 'label' => 'حساسیت به انسولین', 'value' => 78 ),
		array( 'label' => 'انعطاف‌پذیری متابولیک', 'value' => 64 ),
		array( 'label' => 'کیفیت ریتم سیرکادین', 'value' => 71 ),
		array( 'label' => 'ترکیب بدنی', 'value' => 58 ),
	);
	?>
	<div class="sm-biopanel" role="img" aria-label="نمونه‌ی نمایشی از داشبورد پایش شاخص‌های بیومتریک">
		<div class="sm-biopanel__head">
			<span class="sm-biopanel__dot" aria-hidden="true"></span>
			<span class="sm-biopanel__label">پایش شاخص‌های متابولیک</span>
			<span class="sm-biopanel__tag">نمونه</span>
		</div>

		<div class="sm-biopanel__rows">
			<?php foreach ( $rows as $r ) : ?>
				<div class="sm-biopanel__row">
					<span class="sm-biopanel__name"><?php echo esc_html( $r['label'] ); ?></span>
					<span class="sm-biopanel__track">
						<span class="sm-biopanel__fill" style="width:<?php echo esc_attr( $r['value'] ); ?>%"></span>
					</span>
				</div>
			<?php endforeach; ?>
		</div>

		<div class="sm-biopanel__foot">
			<svg class="sm-biopanel__spark" viewBox="0 0 240 56" width="240" height="48" fill="none" aria-hidden="true" preserveAspectRatio="none">
				<path d="M2 46C22 44 34 38 52 30S86 12 106 14s30 16 48 18 42-8 60-20 24-8 24-8"
				      stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
			</svg>
			<span class="sm-biopanel__caption">روند ۱۰۰ روزه پروتکل SMP</span>
		</div>
	</div>
	<?php
}


/**
 * ماکت سه‌بعدی کتاب.
 *
 * عطف در سمت راست قرار می‌گیرد، چون کتاب فارسی از راست باز می‌شود.
 * وقتی طرح جلد واقعی آماده شد و در content-home.php ثبت شد،
 * این تابع دیگر فراخوانی نمی‌شود.
 *
 * @param string $title    عنوان روی جلد.
 * @param string $subtitle زیرعنوان روی جلد.
 */
function sm_book_mockup( $title, $subtitle ) {
	?>
	<div class="sm-book3d" role="img" aria-label="ماکت جلد کتاب <?php echo esc_attr( $title ); ?>">
		<div class="sm-book3d__body">
			<div class="sm-book3d__pages" aria-hidden="true"></div>
			<div class="sm-book3d__spine" aria-hidden="true"></div>
			<div class="sm-book3d__front">
				<img class="sm-book3d__seal" src="<?php echo esc_url( sm_img( 'logo-seal.png' ) ); ?>" alt="" loading="lazy" decoding="async">
				<span class="sm-book3d__title"><?php echo esc_html( $title ); ?></span>
				<span class="sm-book3d__rule" aria-hidden="true"></span>
				<span class="sm-book3d__sub"><?php echo esc_html( $subtitle ); ?></span>
			</div>
		</div>
		<p class="sm-book3d__note">طرح جلد نهایی به‌زودی جایگزین می‌شود</p>
	</div>
	<?php
}


/**
 * محتوای صفحات داخلی را می‌خواند و در حافظه نگه می‌دارد.
 *
 * محتوا در دو فایل تقسیم شده تا هیچ‌کدام بیش از حد بلند نشود:
 *   content-pages.php  →  smp، map، about، faq، contact، media
 *   content-book.php   →  book، council
 *   content-legal.php  →  terms
 *
 * @param string $key کلید صفحه.
 * @return array
 */
function sm_page_content( $key ) {

	static $all = null;

	if ( null === $all ) {
		$all = array();

		foreach ( array( 'content-pages.php', 'content-book.php', 'content-legal.php', 'content-cases.php', 'content-namazi.php' ) as $name ) {
			$file = get_stylesheet_directory() . '/inc/' . $name;
			if ( file_exists( $file ) ) {
				$all = array_merge( $all, (array) require $file );
			}
		}
	}

	return isset( $all[ $key ] ) ? $all[ $key ] : array();
}


/**
 * تصویر یا نشان جایگزینِ یک فرد را چاپ می‌کند.
 *
 * اگر عکس نرسیده باشد، به‌جای جای خالی یا عکس عمومی، یک نشان
 * برنددار با حرف اول نام ساخته می‌شود. عمداً از عکس آرشیوی
 * استفاده نمی‌کنیم؛ چهره‌ی جعلی روی سایت یک متخصص سلامت،
 * اعتماد را از بین می‌برد.
 *
 * @param array $person شامل name و initial و photo.
 */
function sm_person_avatar( $person ) {

	$src = ! empty( $person['photo'] ) ? sm_img_src( $person['photo'] ) : '';

	if ( $src ) {
		printf(
			'<img class="sm-avatar sm-avatar--photo" src="%s" alt="%s" loading="lazy" decoding="async" width="150" height="150">',
			esc_url( $src ),
			esc_attr( $person['name'] )
		);
		return;
	}

	printf(
		'<span class="sm-avatar sm-avatar--mono" aria-hidden="true"><span>%s</span></span>',
		esc_html( $person['initial'] ?? '؟' )
	);
}


/**
 * اسکیمای FAQPage گوگل را برای صفحه‌ی سؤالات متداول چاپ می‌کند.
 *
 * این کد به گوگل می‌گوید کدام بخش صفحه پرسش و پاسخ است، تا بتواند
 * آن‌ها را مستقیم زیر لینک سایت در نتایج جست‌وجو نشان دهد.
 *
 * @param array $items آرایه‌ای از array( 'q' => …, 'a' => array( … ) ).
 */
function sm_faq_schema( $items ) {

	if ( empty( $items ) ) {
		return;
	}

	$entities = array();

	foreach ( $items as $item ) {
		if ( empty( $item['q'] ) || empty( $item['a'] ) ) {
			continue;
		}

		$entities[] = array(
			'@type'          => 'Question',
			'name'           => wp_strip_all_tags( $item['q'] ),
			'acceptedAnswer' => array(
				'@type' => 'Answer',
				'text'  => wp_strip_all_tags( implode( ' ', (array) $item['a'] ) ),
			),
		);
	}

	if ( empty( $entities ) ) {
		return;
	}

	$schema = array(
		'@context'   => 'https://schema.org',
		'@type'      => 'FAQPage',
		'mainEntity' => $entities,
	);

	printf(
		'<script type="application/ld+json">%s</script>',
		wp_json_encode( $schema, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES )
	);
}


/**
 * نشان یک رسانه را چاپ می‌کند.
 *
 * اگر فایل لوگو هنوز در assets/images/media/ گذاشته نشده باشد،
 * به‌جای تصویر شکسته، نام کوتاه رسانه به‌صورت متنی نمایش داده
 * می‌شود. فایل نام‌ها از قبل در content-home.php نوشته شده‌اند،
 * پس به‌محض آپلود تصویر، خودبه‌خود جای متن را می‌گیرد.
 *
 * @param array $item یک آیتم از فهرست media.
 */
function sm_media_logo( $item ) {

	$src = ! empty( $item['logo'] ) ? sm_img_src( 'media/' . $item['logo'] ) : '';

	if ( $src ) {
		printf(
			'<img src="%s" alt="%s" loading="lazy" decoding="async">',
			esc_url( $src ),
			esc_attr( $item['outlet'] )
		);
		return;
	}

	printf(
		'<span class="sm-media__wordmark">%s</span>',
		esc_html( $item['short'] ?? $item['outlet'] )
	);
}


/**
 * سکشن خلاصه‌ی «پشتوانه‌ی علمی» در صفحه‌ی اصلی.
 *
 * فقط چند نفر از هر گروه را نشان می‌دهد و بقیه را به صفحه‌ی
 * /book/council/ می‌سپارد. نام‌ها و عنوان‌ها از inc/content-book.php
 * خوانده می‌شوند تا در دو جا تکرار نشوند.
 *
 * @param array $c محتوای صفحه‌ی اصلی.
 */
function sm_home_council( $c ) {

	$cfg = isset( $c['council'] ) ? $c['council'] : array();

	if ( empty( $cfg['enabled'] ) ) {
		return;
	}

	$council = sm_page_content( 'council' );

	if ( empty( $council['experts']['people'] ) && empty( $council['athletes']['people'] ) ) {
		return;
	}

	$photos = ! empty( $council['photos_enabled'] );

	$groups = array(
		array(
			'title'  => $cfg['experts_title'],
			'people' => array_slice( $council['experts']['people'], 0, (int) $cfg['experts_count'] ),
		),
		array(
			'title'  => $cfg['athletes_title'],
			'people' => array_slice( $council['athletes']['people'], 0, (int) $cfg['athletes_count'] ),
		),
	);
	?>
	<section class="sm-section sm-hcouncil" aria-labelledby="sm-hcouncil-title">
		<div class="sm-wrap">

			<header class="sm-section__head sm-section__head--center">
				<p class="sm-eyebrow"><?php echo esc_html( $cfg['eyebrow'] ); ?></p>
				<h2 id="sm-hcouncil-title" class="sm-section__title"><?php echo esc_html( $cfg['title'] ); ?></h2>
				<p class="sm-hcouncil__lead"><?php echo esc_html( $cfg['lead'] ); ?></p>
			</header>

			<?php foreach ( $groups as $g ) : ?>
				<?php if ( empty( $g['people'] ) ) { continue; } ?>
				<div class="sm-hcouncil__group">
					<h3 class="sm-hcouncil__gtitle"><?php echo esc_html( $g['title'] ); ?></h3>
					<ul class="sm-hcouncil__list">
						<?php foreach ( $g['people'] as $p ) : ?>
							<?php $src = $photos && ! empty( $p['photo'] ) ? sm_img_src( 'people/' . $p['photo'] ) : ''; ?>
							<li class="sm-hcard sm-reveal">
								<?php if ( $src ) : ?>
									<img class="sm-hcard__photo" src="<?php echo esc_url( $src ); ?>"
									     alt="<?php echo esc_attr( $p['name'] ); ?>"
									     width="480" height="480" loading="lazy" decoding="async">
								<?php endif; ?>
								<span class="sm-hcard__name"><?php echo esc_html( $p['name'] ); ?></span>
								<span class="sm-hcard__role"><?php echo esc_html( $p['role'] ); ?></span>
								<?php if ( ! empty( $p['org'] ) ) : ?>
									<span class="sm-hcard__org"><?php echo esc_html( $p['org'] ); ?></span>
								<?php endif; ?>
							</li>
						<?php endforeach; ?>
					</ul>
				</div>
			<?php endforeach; ?>

			<p class="sm-hcouncil__more">
				<a class="sm-btn sm-btn--ghost" href="<?php echo esc_url( home_url( $cfg['cta_link'] ) ); ?>">
					<?php echo esc_html( $cfg['cta_text'] ); ?>
				</a>
			</p>

		</div>
	</section>
	<?php
}


/**
 * کتابِ سه‌بعدیِ چرخان.
 *
 * یک جعبه‌ی واقعیِ شش‌وجهی با CSS 3D می‌سازد: جلد رو، جلد پشت، عطف،
 * لبه‌ی برگه‌ها و دو لبه‌ی بالا و پایین. کاربر می‌تواند با موس یا انگشت
 * بچرخاندش و با صفحه‌کلید هم کار می‌کند.
 *
 * چند تصمیمِ عمدی:
 *
 * ۱) عطف سمتِ راست است، چون کتابِ فارسی از راست باز می‌شود. در ریاضیِ
 *    CSS این یعنی وجهِ ‎+X‎، و برای دیدنِ آن باید rotateY منفی باشد —
 *    به همین دلیل زاویه‌ی پیش‌فرض ‎-۲۴ درجه است، نه ‎+۲۴‎.
 *
 * ۲) دو دکمه‌ی «جلد رو / جلد پشت» رادیوباتنِ واقعی‌اند، نه دکمه‌ی
 *    جاوااسکریپتی. پس اگر جاوااسکریپت اجرا نشود یا هنوز بارگذاری
 *    نشده باشد، چرخشِ رو ↔ پشت همچنان کار می‌کند. جاوااسکریپت فقط
 *    «کشیدن با موس» را اضافه می‌کند.
 *
 * ۳) روی خودِ کتاب role="img" نگذاشته‌ایم؛ چون در آن حالت مرورگر
 *    alt‌ِ تصویرهای داخل را نادیده می‌گیرد. این‌طوری کسی که با
 *    صفحه‌خوان کار می‌کند، توضیحِ هر دو جلد را می‌شنود.
 *
 * @param array $cfg آرایه‌ی previous از inc/content-book.php
 */
function sm_cover3d( $cfg ) {

	$front = sm_img_src( isset( $cfg['front'] ) ? $cfg['front'] : '' );
	$back  = sm_img_src( isset( $cfg['back'] ) ? $cfg['back'] : '' );

	// بدون جلدِ رو چیزی برای نشان دادن نیست.
	if ( ! $front ) {
		return;
	}

	$spine = sm_img_src( isset( $cfg['spine'] ) ? $cfg['spine'] : '' );

	// شناسه‌ی یکتا، تا اگر روزی دو کتاب در یک صفحه آمد رادیوها قاطی نشوند.
	static $seq = 0;
	++$seq;
	$id = 'sm-cover3d-' . $seq;

	// ضخامتِ عطف، به‌صورتِ نسبتِ بی‌واحد نسبت به عرضِ جلد.
	// بی‌واحد است چون در CSS باید در یک طول ضرب شود، و calc()
	// اجازه‌ی تقسیمِ طول بر درصد را نمی‌دهد.
	$thick = isset( $cfg['thickness'] ) ? (float) $cfg['thickness'] : 6.5;
	$thick = max( 1.5, min( 18.0, $thick ) ) / 100;

	$front_alt = isset( $cfg['front_alt'] ) ? $cfg['front_alt'] : '';
	$back_alt  = isset( $cfg['back_alt'] ) ? $cfg['back_alt'] : '';
	$hint      = isset( $cfg['hint'] ) ? $cfg['hint'] : '';
	$b_front   = isset( $cfg['btn_front'] ) ? $cfg['btn_front'] : 'جلد رو';
	$b_back    = isset( $cfg['btn_back'] ) ? $cfg['btn_back'] : 'جلد پشت';
	?>
	<div class="sm-cover3d" data-sm-cover3d
	     style="--sm-bk-thick: <?php echo esc_attr( number_format( $thick, 4, '.', '' ) ); ?>">

		<input class="sm-cover3d__radio sm-cover3d__radio--front" type="radio"
		       name="<?php echo esc_attr( $id ); ?>" id="<?php echo esc_attr( $id ); ?>-f" checked>
		<input class="sm-cover3d__radio sm-cover3d__radio--back" type="radio"
		       name="<?php echo esc_attr( $id ); ?>" id="<?php echo esc_attr( $id ); ?>-b">

		<div class="sm-cover3d__stage">
			<div class="sm-cover3d__grab" data-sm-cover3d-grab>
				<div class="sm-cover3d__body" data-sm-cover3d-body>

					<div class="sm-cover3d__face sm-cover3d__face--front">
						<img src="<?php echo esc_url( $front ); ?>"
						     alt="<?php echo esc_attr( $front_alt ); ?>"
						     width="763" height="1120" loading="lazy" decoding="async">
					</div>

					<?php if ( $back ) : ?>
						<div class="sm-cover3d__face sm-cover3d__face--back">
							<img src="<?php echo esc_url( $back ); ?>"
							     alt="<?php echo esc_attr( $back_alt ); ?>"
							     width="763" height="1120" loading="lazy" decoding="async">
						</div>
					<?php endif; ?>

					<div class="sm-cover3d__face sm-cover3d__face--spine" aria-hidden="true">
						<?php if ( $spine ) : ?>
							<img src="<?php echo esc_url( $spine ); ?>" alt=""
							     width="51" height="1120" loading="lazy" decoding="async">
						<?php endif; ?>
					</div>

					<div class="sm-cover3d__face sm-cover3d__face--fore" aria-hidden="true"></div>
					<div class="sm-cover3d__face sm-cover3d__face--head" aria-hidden="true"></div>
					<div class="sm-cover3d__face sm-cover3d__face--tail" aria-hidden="true"></div>

				</div>
			</div>
			<span class="sm-cover3d__shadow" aria-hidden="true"></span>
		</div>

		<?php if ( $hint ) : ?>
			<p class="sm-cover3d__hint" id="<?php echo esc_attr( $id ); ?>-hint">
				<?php echo esc_html( $hint ); ?>
			</p>
		<?php endif; ?>

		<div class="sm-cover3d__ctrl">
			<label class="sm-cover3d__btn sm-cover3d__btn--front"
			       for="<?php echo esc_attr( $id ); ?>-f"><?php echo esc_html( $b_front ); ?></label>
			<label class="sm-cover3d__btn sm-cover3d__btn--back"
			       for="<?php echo esc_attr( $id ); ?>-b"><?php echo esc_html( $b_back ); ?></label>
		</div>

	</div>
	<?php
}


/**
 * بلوکِ «دستاوردهای کلیدی» یک پرونده‌ی بالینی.
 * ---------------------------------------------------------------------------
 *
 * سه نوع المان می‌شناسد و بر اساس 'type' یکی را می‌سازد:
 *
 *     bar    میله‌ی افقی با محورِ مدرج   — برای تغییرِ عددیِ مطلق
 *     rise   میله‌ی عمودی با محورِ مدرج  — برای «بالا رفتن» (قد)
 *     state  کارتِ دووضعیتی              — برای شاخصِ کیفی، بدون عدد
 *
 * ⚠️ چرا محورها از صفر شروع می‌شوند و نه از عددِ واقعیِ فرد:
 *
 *     از این پرونده فقط «اندازه‌ی تغییر» در دست است (+۵ کیلو، +۳ سانت)
 *     نه عددِ مطلقِ ورود و خروج. اگر محور را ۰ تا ۱۰۰ می‌کشیدیم، باید
 *     یک عددِ شروعِ ساختگی می‌گذاشتیم. پس محور همان چیزی را نشان
 *     می‌دهد که واقعاً اندازه‌گیری شده: خودِ تغییر.
 *
 * همه‌چیز SVG و CSS است — نه تصویر، نه کتابخانه‌ی نمودار. صفحه‌ی
 * پرونده‌ها با این کار حتی یک کیلوبایت هم سنگین‌تر نمی‌شود.
 *
 * @param array $viz بلوکِ 'viz' یک پرونده.
 */
function sm_case_viz( $viz ) {

	if ( empty( $viz['items'] ) ) {
		return;
	}
	?>
	<section class="sm-viz" aria-labelledby="sm-viz-<?php echo esc_attr( md5( $viz['title'] ) ); ?>">

		<h3 class="sm-viz__title" id="sm-viz-<?php echo esc_attr( md5( $viz['title'] ) ); ?>">
			<?php echo esc_html( $viz['title'] ); ?>
		</h3>

		<div class="sm-viz__grid">
			<?php foreach ( $viz['items'] as $item ) : ?>
				<?php
				$type = isset( $item['type'] ) ? $item['type'] : 'state';
				$val  = isset( $item['value'] ) ? (float) $item['value'] : 0;
				$max  = isset( $item['max'] ) && $item['max'] > 0 ? (float) $item['max'] : 1;
				$pct  = max( 0, min( 100, ( $val / $max ) * 100 ) );
				?>
				<figure class="sm-vizcard sm-vizcard--<?php echo esc_attr( $type ); ?>">

					<figcaption class="sm-vizcard__head">
						<span class="sm-vizcard__label"><?php echo esc_html( $item['label'] ); ?></span>
						<?php if ( ! empty( $item['en'] ) ) : ?>
							<span class="sm-vizcard__en" dir="ltr"><?php echo esc_html( $item['en'] ); ?></span>
						<?php endif; ?>
					</figcaption>

					<?php if ( 'state' === $type ) : ?>

						<?php /* ---------- کارتِ دووضعیتی ---------- */ ?>
						<div class="sm-vizstate">
							<div class="sm-vizstate__node sm-vizstate__node--a">
								<span class="sm-vizstate__dot" aria-hidden="true"></span>
								<span class="sm-vizstate__cap">نقطه‌ی ورود</span>
								<span class="sm-vizstate__txt"><?php echo esc_html( $item['before'] ); ?></span>
							</div>

							<span class="sm-vizstate__arrow" aria-hidden="true">
								<svg viewBox="0 0 40 12" width="40" height="12" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
									<path d="M38 6H4M10 1 4 6l6 5"/>
								</svg>
							</span>

							<div class="sm-vizstate__node sm-vizstate__node--b">
								<span class="sm-vizstate__dot" aria-hidden="true"></span>
								<span class="sm-vizstate__cap">پایان پروتکل</span>
								<span class="sm-vizstate__txt"><?php echo esc_html( $item['after'] ); ?></span>
							</div>
						</div>

						<?php if ( ! empty( $item['badge'] ) ) : ?>
							<p class="sm-vizcard__badge"><?php echo esc_html( $item['badge'] ); ?></p>
						<?php endif; ?>

					<?php else : ?>

						<?php
						/*
						 * عددِ درشت. خودِ عدد، نه میله، چیزی است که خوانده
						 * می‌شود؛ میله فقط کمک می‌کند اندازه‌اش حس شود.
						 */
						?>
						<p class="sm-vizcard__big">
							<span class="sm-vizcard__plus" aria-hidden="true">+</span><?php echo esc_html( sm_fa_digits( $val ) ); ?><span class="sm-vizcard__unit"><?php echo esc_html( $item['unit'] ); ?></span>
						</p>

						<?php if ( 'rise' === $type ) : ?>

							<?php /* ---------- رنج‌بارِ عمودی ---------- */ ?>
							<div class="sm-vizrise" role="img"
							     aria-label="<?php echo esc_attr( sprintf( '%s: %s %s افزایش نسبت به خط مبنا', $item['label'], sm_fa_digits( $val ), $item['unit'] ) ); ?>">
								<ul class="sm-vizrise__axis" aria-hidden="true">
									<?php foreach ( array_reverse( (array) $item['ticks'] ) as $t ) : ?>
										<li><?php echo esc_html( sm_fa_digits( $t ) ); ?></li>
									<?php endforeach; ?>
								</ul>
								<div class="sm-vizrise__track">
									<div class="sm-vizrise__fill" style="--sm-viz-pct: <?php echo esc_attr( round( $pct, 2 ) ); ?>%;">
										<span class="sm-vizrise__tip" dir="ltr">+<?php echo esc_html( sm_fa_digits( $val ) ); ?> <?php echo esc_html( $item['unit_en'] ?? '' ); ?></span>
									</div>
									<span class="sm-vizrise__base">خط مبنا</span>
								</div>
							</div>

						<?php else : ?>

							<?php /* ---------- میله‌ی افقی ---------- */ ?>
							<div class="sm-vizbar" role="img"
							     aria-label="<?php echo esc_attr( sprintf( '%s: %s %s افزایش نسبت به خط مبنا', $item['label'], sm_fa_digits( $val ), $item['unit'] ) ); ?>">
								<div class="sm-vizbar__track">
									<div class="sm-vizbar__fill" style="--sm-viz-pct: <?php echo esc_attr( round( $pct, 2 ) ); ?>%;">
										<span class="sm-vizbar__tip" dir="ltr">+<?php echo esc_html( sm_fa_digits( $val ) ); ?> <?php echo esc_html( $item['unit_en'] ?? '' ); ?></span>
									</div>
								</div>
								<ul class="sm-vizbar__axis" aria-hidden="true">
									<?php foreach ( (array) $item['ticks'] as $t ) : ?>
										<li><?php echo esc_html( sm_fa_digits( $t ) ); ?></li>
									<?php endforeach; ?>
								</ul>
							</div>

						<?php endif; ?>

						<dl class="sm-vizcard__pair">
							<div><dt>پیش از پروتکل</dt><dd><?php echo esc_html( $item['before'] ); ?></dd></div>
							<div><dt>پس از مداخله</dt><dd><?php echo esc_html( $item['after'] ); ?></dd></div>
						</dl>

					<?php endif; ?>

					<?php if ( ! empty( $item['note'] ) ) : ?>
						<p class="sm-vizcard__note"><?php echo esc_html( $item['note'] ); ?></p>
					<?php endif; ?>

				</figure>
			<?php endforeach; ?>
		</div>

		<?php if ( ! empty( $viz['note'] ) ) : ?>
			<p class="sm-viz__note"><?php echo esc_html( $viz['note'] ); ?></p>
		<?php endif; ?>

	</section>
	<?php
}
