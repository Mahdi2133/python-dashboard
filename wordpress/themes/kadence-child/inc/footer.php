<?php
/**
 * فوتر اختصاصی سایت — چهار ستون.
 *
 * فوتر قالب دمو (Kadence) با CSS پنهان می‌شود و این فوتر جایش می‌نشیند.
 *
 * روی قلاب wp_footer سوار می‌شود، نه با بازنویسی footer.php قالب مادر —
 * بازنویسی آن ریسک بسته‌نشدن تگ‌های بازشده در header.php را دارد.
 *
 * برای ویرایش محتوا به inc/content-footer.php بروید.
 *
 * @package saadatmehr
 */

defined( 'ABSPATH' ) || exit;


/**
 * محتوای فوتر را می‌خواند و در حافظه نگه می‌دارد.
 *
 * @return array
 */
function sm_footer_content() {

	static $content = null;

	if ( null === $content ) {
		$file    = get_stylesheet_directory() . '/inc/content-footer.php';
		$content = file_exists( $file ) ? require $file : array();
	}

	return $content;
}


/**
 * تاریخ میلادی را به هجری شمسی تبدیل می‌کند.
 *
 * وردپرس به‌صورت پیش‌فرض تاریخ را شمسی نمی‌کند. روی یک سایت فارسی،
 * «© ۲۰۲۶» یا «تاریخ امضا: 2026/09/18» غلط به نظر می‌رسد.
 *
 * الگوریتم همان الگوریتمِ شناخته‌شده‌ی شمارشِ روز است و با چند
 * تاریخِ معلوم (نوروز، اول مهر، شب یلدا) راستی‌آزمایی شده.
 *
 * @param int $gy سال میلادی.
 * @param int $gm ماه میلادی (۱ تا ۱۲).
 * @param int $gd روز میلادی.
 * @return array آرایه‌ی سه‌تایی: سال، ماه، روزِ شمسی.
 */
function sm_jalali_parts( $gy, $gm, $gd ) {

	$g_days = array( 0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334 );

	$gy2 = ( $gm > 2 ) ? $gy + 1 : $gy;

	$days = 355666
		+ ( 365 * $gy )
		+ ( (int) ( ( $gy2 + 3 ) / 4 ) )
		- ( (int) ( ( $gy2 + 99 ) / 100 ) )
		+ ( (int) ( ( $gy2 + 399 ) / 400 ) )
		+ $gd
		+ $g_days[ $gm - 1 ];

	$jy   = -1595 + ( 33 * ( (int) ( $days / 12053 ) ) );
	$days %= 12053;

	$jy   += 4 * ( (int) ( $days / 1461 ) );
	$days %= 1461;

	if ( $days > 365 ) {
		$jy   += (int) ( ( $days - 1 ) / 365 );
		$days  = ( $days - 1 ) % 365;
	}

	if ( $days < 186 ) {
		$jm = 1 + (int) ( $days / 31 );
		$jd = 1 + ( $days % 31 );
	} else {
		$jm = 7 + (int) ( ( $days - 186 ) / 30 );
		$jd = 1 + ( ( $days - 186 ) % 30 );
	}

	return array( $jy, $jm, $jd );
}


/**
 * سال جاری هجری شمسی.
 *
 * @return int
 */
function sm_jalali_year() {

	$parts = sm_jalali_parts(
		(int) current_time( 'Y' ),
		(int) current_time( 'n' ),
		(int) current_time( 'j' )
	);

	return $parts[0];
}


/**
 * نامِ ماه‌های شمسی.
 *
 * @return array
 */
function sm_jalali_months() {
	return array(
		1 => 'فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور',
		'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند',
	);
}


/**
 * یک زمانِ یونیکس را به تاریخ و ساعتِ شمسیِ خوانا تبدیل می‌کند.
 *
 * نمونه:  ۲۷ شهریور ۱۴۰۵ — ساعت ۱۱:۱۳
 *
 * @param int  $ts       زمان یونیکس.
 * @param bool $withtime ساعت هم بیاید یا نه.
 * @return string
 */
function sm_jalali_datetime( $ts, $withtime = true ) {

	$ts = (int) $ts;

	if ( ! $ts ) {
		return '';
	}

	// به وقتِ محلیِ سایت، نه وقتِ سرور.
	$offset = (float) get_option( 'gmt_offset' );
	$local  = $ts + (int) round( $offset * HOUR_IN_SECONDS );

	$parts  = sm_jalali_parts(
		(int) gmdate( 'Y', $local ),
		(int) gmdate( 'n', $local ),
		(int) gmdate( 'j', $local )
	);

	$months = sm_jalali_months();

	$out = sprintf(
		'%s %s %s',
		sm_fa_digits( $parts[2] ),
		isset( $months[ $parts[1] ] ) ? $months[ $parts[1] ] : '',
		sm_fa_digits( $parts[0] )
	);

	if ( $withtime ) {
		$out .= ' — ساعت ' . sm_fa_digits( gmdate( 'H:i', $local ) );
	}

	return $out;
}


/**
 * عدد لاتین را به رقم فارسی تبدیل می‌کند.
 *
 * @param string|int $number ورودی.
 * @return string
 */
function sm_fa_digits( $number ) {
	return str_replace(
		array( '0', '1', '2', '3', '4', '5', '6', '7', '8', '9' ),
		array( '۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹' ),
		(string) $number
	);
}


/**
 * آیکون‌های فوتر و صفحات.
 *
 * @param string $name نام آیکون.
 */
function sm_footer_icon( $name ) {

	$paths = array(
		'phone'     => '<path d="M21 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 1.1 4.1 2 2 0 0 1 3.1 1.9h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.5 2.1L7.2 9.7a16 16 0 0 0 6 6l1.2-1.2a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2Z"/>',
		'mail'      => '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="m2 7 10 6 10-6"/>',
		'pin'       => '<path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/>',
		'clock'     => '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.2 1.9"/>',
		'book'      => '<path d="M4 4.5A2.5 2.5 0 0 1 6.5 2H20v18H6.5A2.5 2.5 0 0 0 4 22Z"/><path d="M4 17.5A2.5 2.5 0 0 1 6.5 15H20"/>',
		'star'      => '<path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1-5.4-2.9-5.4 2.9 1-6.1L3.2 9.5l6.1-.9Z"/>',
		'instagram' => '<rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17.5" cy="6.5" r="1.2" fill="currentColor" stroke="none"/>',
		'telegram'  => '<path d="M21.5 4.3 2.9 11.4c-.9.3-.9 1.1 0 1.4l4.7 1.5 1.8 5.4c.2.6.6.7 1.1.3l2.6-2.1 4.6 3.4c.7.4 1.2.2 1.4-.7l3-13.9c.2-.9-.4-1.3-1-1.1Z"/><path d="m7.6 14.3 9.9-6.5-7.6 7.6"/>',
		'whatsapp'  => '<path d="M20.5 11.6a8.4 8.4 0 0 1-12.5 7.3L3.5 20.5l1.6-4.4A8.4 8.4 0 1 1 20.5 11.6Z"/><path d="M8.6 8.2c.4-.1.8 0 1 .4l.7 1.2c.2.3.1.6-.1.9l-.4.5c.6 1.1 1.5 2 2.6 2.6l.5-.5c.2-.2.6-.3.9-.1l1.2.7c.4.2.5.6.4 1-.2.8-1 1.4-1.9 1.3-2.9-.4-5.2-2.7-5.6-5.6-.1-.9.4-1.7 1.2-1.9Z" fill="currentColor" stroke="none"/>',
		'youtube'   => '<rect x="2" y="5" width="20" height="14" rx="4"/><path d="m10 9 5 3-5 3Z" fill="currentColor"/>',
		'linkedin'  => '<rect x="3" y="3" width="18" height="18" rx="3"/><path d="M8 10.5V17M8 7.4v.1M12 17v-3.6a2 2 0 0 1 4 0V17"/>',
		'aparat'    => '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3.4"/><path d="M12 3v2.6M12 18.4V21M3 12h2.6M18.4 12H21"/>',
	);

	if ( ! isset( $paths[ $name ] ) ) {
		return;
	}

	/*
	 * width و height عمداً روی خود تگ نوشته می‌شوند، نه فقط در CSS.
	 *
	 * یک SVG بدون این دو، اگر قاعده‌ی CSS مربوطه به هر دلیلی بارگذاری
	 * نشود، تا اندازه‌ی کل والدش بزرگ می‌شود و صفحه را به هم می‌ریزد.
	 * با این دو عدد، بدترین حالت یک آیکون کمی بزرگ‌تر است، نه یک
	 * آیکون تمام‌صفحه. CSS همچنان می‌تواند اندازه را دقیق‌تر کند.
	 */
	printf(
		'<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">%s</svg>',
		$paths[ $name ] // phpcs:ignore WordPress.Security.EscapeOutput -- مقادیر ثابت و داخلی.
	);
}


/**
 * یک ردیف اطلاعات تماس چاپ می‌کند — فقط اگر مقدار داشته باشد.
 *
 * @param string $icon  نام آیکون.
 * @param string $value متن نمایشی.
 * @param string $href  نشانی پیوند (اختیاری).
 * @param string $note  توضیح کوچک زیر مقدار (اختیاری).
 */
function sm_contact_row( $icon, $value, $href = '', $note = '' ) {

	$value = trim( (string) $value );

	if ( '' === $value ) {
		return;
	}
	?>
	<li class="sm-foot__contact-row">
		<span class="sm-foot__contact-icon" aria-hidden="true"><?php sm_footer_icon( $icon ); ?></span>
		<span class="sm-foot__contact-body">
			<?php if ( $href ) : ?>
				<a href="<?php echo esc_url( $href ); ?>"><span class="sm-foot__contact-value"><?php echo esc_html( $value ); ?></span></a>
			<?php else : ?>
				<span class="sm-foot__contact-value"><?php echo esc_html( $value ); ?></span>
			<?php endif; ?>
			<?php if ( $note ) : ?>
				<span class="sm-foot__contact-note"><?php echo esc_html( $note ); ?></span>
			<?php endif; ?>
		</span>
	</li>
	<?php
}


/**
 * فوتر را چاپ می‌کند.
 */
function sm_render_footer() {

	if ( is_admin() || is_embed() ) {
		return;
	}

	$c    = sm_footer_content();
	$logo = get_stylesheet_directory_uri() . '/assets/images/logo-header.png';

	$socials = array(
		'instagram' => 'اینستاگرام',
		'telegram'  => 'تلگرام',
		'whatsapp'  => 'واتساپ',
		'aparat'    => 'آپارات',
		'youtube'   => 'یوتیوب',
		'linkedin'  => 'لینکدین',
	);

	$has_social = false;
	foreach ( array_keys( $socials ) as $key ) {
		if ( ! empty( $c['social'][ $key ] ) ) {
			$has_social = true;
			break;
		}
	}

	$copyright = str_replace(
		'{year}',
		sm_fa_digits( sm_jalali_year() ),
		$c['bottom']['copyright'] ?? ''
	);

	// شماره‌ی لاتین برای لینک tel: — اگر نبود، از خود مقدار نمایشی می‌سازیم.
	$mobile_raw = $c['contact']['mobile_raw'] ?? '';
	if ( ! $mobile_raw && ! empty( $c['contact']['mobile'] ) ) {
		$mobile_raw = $c['contact']['mobile'];
	}
	$mobile_raw = preg_replace( '/[^0-9+]/', '', sm_fa_to_en_digits( $mobile_raw ) );

	$phone_raw = preg_replace( '/[^0-9+]/', '', sm_fa_to_en_digits( $c['contact']['phone'] ?? '' ) );
	?>

	<footer class="sm-foot" role="contentinfo">
		<div class="sm-foot__inner">

			<div class="sm-foot__grid">

				<?php /* ---------- ستون ۱: معرفی ---------- */ ?>
				<div class="sm-foot__col sm-foot__col--brand">
					<img class="sm-foot__logo" src="<?php echo esc_url( $logo ); ?>"
					     alt="<?php echo esc_attr( get_bloginfo( 'name' ) ); ?>"
					     width="240" height="88" loading="lazy" decoding="async">
					<?php if ( ! empty( $c['about']['text'] ) ) : ?>
						<p class="sm-foot__about"><?php echo esc_html( $c['about']['text'] ); ?></p>
					<?php endif; ?>
					<?php if ( ! empty( $c['about']['note'] ) ) : ?>
						<p class="sm-foot__about sm-foot__about--note"><?php echo esc_html( $c['about']['note'] ); ?></p>
					<?php endif; ?>

					<?php if ( $has_social ) : ?>
						<ul class="sm-foot__social" aria-label="<?php echo esc_attr( $c['social']['title'] ?? 'شبکه‌های اجتماعی' ); ?>">
							<?php foreach ( $socials as $key => $label ) : ?>
								<?php if ( empty( $c['social'][ $key ] ) ) { continue; } ?>
								<li>
									<a href="<?php echo esc_url( $c['social'][ $key ] ); ?>" target="_blank" rel="noopener noreferrer me">
										<?php sm_footer_icon( $key ); ?>
										<span class="screen-reader-text"><?php echo esc_html( $label ); ?></span>
									</a>
								</li>
							<?php endforeach; ?>
						</ul>
					<?php endif; ?>
				</div>

				<?php /* ---------- ستون ۲: دسترسی سریع ---------- */ ?>
				<?php if ( ! empty( $c['links']['items'] ) ) : ?>
					<nav class="sm-foot__col" aria-label="<?php echo esc_attr( $c['links']['title'] ?? 'دسترسی سریع' ); ?>">
						<h2 class="sm-foot__title"><?php echo esc_html( $c['links']['title'] ); ?></h2>
						<ul class="sm-foot__links">
							<?php foreach ( $c['links']['items'] as $item ) : ?>
								<li><a href="<?php echo esc_url( home_url( $item['url'] ) ); ?>"><?php echo esc_html( $item['label'] ); ?></a></li>
							<?php endforeach; ?>
						</ul>
					</nav>
				<?php endif; ?>

				<?php /* ---------- ستون ۳: راه‌های ارتباطی ---------- */ ?>
				<div class="sm-foot__col">
					<h2 class="sm-foot__title"><?php echo esc_html( $c['contact']['title'] ?? 'راه‌های ارتباطی' ); ?></h2>
					<?php if ( ! empty( $c['contact']['text'] ) ) : ?>
						<p class="sm-foot__about"><?php echo esc_html( $c['contact']['text'] ); ?></p>
					<?php endif; ?>
					<ul class="sm-foot__contact">
						<?php
						sm_contact_row( 'phone', $c['contact']['phone'] ?? '', $phone_raw ? 'tel:' . $phone_raw : '' );
						sm_contact_row( 'phone', $c['contact']['mobile'] ?? '', $mobile_raw ? 'tel:' . $mobile_raw : '' );
						sm_contact_row(
							'mail',
							$c['contact']['email'] ?? '',
							! empty( $c['contact']['email'] ) ? 'mailto:' . $c['contact']['email'] : ''
						);
						sm_contact_row( 'pin', $c['contact']['address'] ?? '', '', $c['contact']['address_note'] ?? '' );
						sm_contact_row( 'pin', ! empty( $c['contact']['postal'] ) ? 'کد پستی: ' . $c['contact']['postal'] : '', '' );
						sm_contact_row( 'clock', $c['contact']['hours'] ?? '', '', $c['contact']['hours_note'] ?? '' );
						?>
					</ul>
				</div>

				<?php /* ---------- ستون ۴: محصولات + نماد اعتماد ---------- */ ?>
				<?php
				$enamad     = isset( $c['enamad'] ) ? $c['enamad'] : array();
				$has_enamad = ! empty( $enamad['enabled'] ) && ! empty( $enamad['id'] ) && ! empty( $enamad['code'] );
				?>
				<?php if ( ! empty( $c['products']['items'] ) || $has_enamad ) : ?>
					<div class="sm-foot__col">
						<?php if ( ! empty( $c['products']['items'] ) ) : ?>
						<h2 class="sm-foot__title"><?php echo esc_html( $c['products']['title'] ); ?></h2>
						<ul class="sm-foot__products">
							<?php foreach ( $c['products']['items'] as $i => $item ) : ?>
								<li>
									<a href="<?php echo esc_url( home_url( $item['url'] ) ); ?>">
										<span class="sm-foot__product-icon" aria-hidden="true"><?php sm_footer_icon( 0 === $i ? 'book' : 'star' ); ?></span>
										<span class="sm-foot__product-body">
											<span class="sm-foot__product-name"><?php echo esc_html( $item['label'] ); ?></span>
											<?php if ( ! empty( $item['meta'] ) ) : ?>
												<span class="sm-foot__product-meta"><?php echo esc_html( $item['meta'] ); ?></span>
											<?php endif; ?>
										</span>
									</a>
								</li>
							<?php endforeach; ?>
						</ul>
						<?php endif; ?>

						<?php
						/*
						 * نماد اعتماد الکترونیکی.
						 *
						 * ⚠️ این تکه عمداً عیناً همان چیزی است که اینماد
						 *    می‌دهد و نباید ساده‌اش کرد:
						 *
						 *    • تصویر باید از trustseal.enamad.ir بیاید،
						 *      نه از پوشه‌ی خودمان. اینماد هر بار همان
						 *      درخواست را می‌بیند و سایت را «فعال»
						 *      می‌شناسد. با عکسِ محلی، نماد باطل است.
						 *    • referrerpolicy='origin' لازم است، چون
						 *      اینماد دامنه‌ی درخواست را چک می‌کند.
						 *    • صفتِ code روی خودِ img را هم نگه داشته‌ایم.
						 *
						 *    تنها چیزی که اضافه شده alt خالی و aria-label
						 *    روی لینک است، تا صفحه‌خوان «لینک بدون نام»
						 *    نگوید. این‌ها در اعتبارسنجی اثری ندارند.
						 */
						?>
						<?php if ( $has_enamad ) : ?>
							<?php
							$enamad_url = sprintf(
								'https://trustseal.enamad.ir/?id=%s&Code=%s',
								rawurlencode( $enamad['id'] ),
								rawurlencode( $enamad['code'] )
							);
							$enamad_img = sprintf(
								'https://trustseal.enamad.ir/logo.aspx?id=%s&Code=%s',
								rawurlencode( $enamad['id'] ),
								rawurlencode( $enamad['code'] )
							);
							$enamad_ttl = ! empty( $enamad['title'] ) ? $enamad['title'] : 'نماد اعتماد الکترونیکی';
							?>
							<div class="sm-foot__enamad">
								<a class="sm-foot__enamad-link"
								   href="<?php echo esc_url( $enamad_url ); ?>"
								   target="_blank" rel="noopener"
								   referrerpolicy="origin"
								   aria-label="<?php echo esc_attr( $enamad_ttl ); ?>">
									<?php
									/*
									 * عمداً loading="lazy" ندارد.
									 *
									 * فوتر پایینِ صفحه است و با lazy، مرورگرِ
									 * خیلی از بازدیدکننده‌ها هیچ‌وقت تصویر را
									 * از سرورِ اینماد نمی‌خواهد. اینماد همان
									 * درخواست‌ها را نشانه‌ی «سایت فعال است»
									 * می‌گیرد. یک تصویرِ کوچکِ اضافه ارزشش را
									 * دارد که نماد معتبر بماند.
									 */
									?>
									<img src="<?php echo esc_url( $enamad_img ); ?>" alt=""
									     referrerpolicy="origin" decoding="async"
									     code="<?php echo esc_attr( $enamad['code'] ); ?>">
								</a>
								<span class="sm-foot__enamad-cap"><?php echo esc_html( $enamad_ttl ); ?></span>
							</div>
						<?php endif; ?>
					</div>
				<?php endif; ?>

			</div>

			<?php /* ---------- نوار دعوت به اقدام ---------- */ ?>
			<?php if ( ! empty( $c['cta']['label'] ) ) : ?>
				<div class="sm-foot__cta">
					<div class="sm-foot__cta-text">
						<?php if ( ! empty( $c['cta']['title'] ) ) : ?>
							<p class="sm-foot__cta-title"><?php echo esc_html( $c['cta']['title'] ); ?></p>
						<?php endif; ?>
						<?php if ( ! empty( $c['cta']['text'] ) ) : ?>
							<p class="sm-foot__cta-sub"><?php echo esc_html( $c['cta']['text'] ); ?></p>
						<?php endif; ?>
					</div>
					<a class="sm-foot__cta-btn" href="<?php echo esc_url( home_url( $c['cta']['url'] ) ); ?>">
						<?php echo esc_html( $c['cta']['label'] ); ?>
					</a>
				</div>
			<?php endif; ?>

			<?php /* ---------- نوارِ دسته‌بندیِ مقالات ---------- */ ?>
			<?php $topics = isset( $c['topics'] ) ? $c['topics'] : array(); ?>
			<?php if ( ! empty( $topics['enabled'] ) ) : ?>
				<?php
				/*
				 * دسته‌ها از خودِ وردپرس خوانده می‌شوند. hide_empty یعنی
				 * دسته‌ای که هنوز مقاله‌ای ندارد نمایش داده نشود — لینکِ
				 * به صفحه‌ی خالی، هم برای کاربر بد است هم برای گوگل.
				 */
				$cats = get_categories(
					array(
						'hide_empty' => true,
						'number'     => max( 1, (int) ( $topics['limit'] ?? 8 ) ),
						'orderby'    => 'count',
						'order'      => 'DESC',
					)
				);
				?>
				<nav class="sm-foot__topics" aria-label="<?php echo esc_attr( $topics['title'] ); ?>">
					<h2 class="sm-foot__topics-title"><?php echo esc_html( $topics['title'] ); ?></h2>

					<ul class="sm-foot__topics-list">
						<li>
							<a class="sm-foot__topic sm-foot__topic--all" href="<?php echo esc_url( home_url( $topics['url'] ) ); ?>">
								<?php echo esc_html( $topics['all'] ); ?>
							</a>
						</li>

						<?php if ( empty( $cats ) ) : ?>
							<li><span class="sm-foot__topic is-empty"><?php echo esc_html( $topics['empty'] ); ?></span></li>
						<?php else : ?>
							<?php foreach ( $cats as $cat ) : ?>
								<li>
									<a class="sm-foot__topic" href="<?php echo esc_url( get_category_link( $cat->term_id ) ); ?>">
										<?php echo esc_html( $cat->name ); ?>
										<span class="sm-foot__topic-n"><?php echo esc_html( sm_fa_digits( (int) $cat->count ) ); ?></span>
									</a>
								</li>
							<?php endforeach; ?>
						<?php endif; ?>
					</ul>
				</nav>
			<?php endif; ?>

			<?php /* ---------- سلب مسئولیت و کپی‌رایت ---------- */ ?>
			<div class="sm-foot__bottom">
				<?php if ( ! empty( $c['bottom']['disclaimer'] ) ) : ?>
					<p class="sm-foot__disclaimer"><?php echo esc_html( $c['bottom']['disclaimer'] ); ?></p>
				<?php endif; ?>
				<?php if ( $copyright ) : ?>
					<p class="sm-foot__copy"><?php echo esc_html( $copyright ); ?></p>
				<?php endif; ?>
			</div>

		</div>
	</footer>
	<?php
}
add_action( 'wp_footer', 'sm_render_footer', 5 );


/**
 * ارقام فارسی و عربی را به لاتین برمی‌گرداند.
 *
 * لازم است چون شماره‌ی تلفن با رقم فارسی نمایش داده می‌شود ولی
 * لینک tel: فقط با رقم لاتین کار می‌کند.
 *
 * @param string $text ورودی.
 * @return string
 */
function sm_fa_to_en_digits( $text ) {
	return str_replace(
		array( '۰','۱','۲','۳','۴','۵','۶','۷','۸','۹','٠','١','٢','٣','٤','٥','٦','٧','٨','٩' ),
		array( '0','1','2','3','4','5','6','7','8','9','0','1','2','3','4','5','6','7','8','9' ),
		(string) $text
	);
}
