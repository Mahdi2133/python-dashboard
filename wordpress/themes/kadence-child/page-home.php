<?php
/**
 * Template Name: صفحه اصلی آکادمی سعادت‌مهر
 *
 * صفحه‌ی اصلی با ساختار ۹ سکشنی، طبق فایل «ترتیب صفحه اول.docx».
 *
 * هدف صفحه یکی است: رساندن بازدیدکننده‌ی مناسب به «درخواست ارزیابی
 * اولیه». به همین دلیل کتاب نقش پشتیبان دارد و قیمت نمایش داده نمی‌شود.
 *
 * متن‌ها در inc/content-home.php هستند — برای ویرایش محتوا فقط
 * آن فایل را تغییر دهید، به این فایل دست نزنید.
 *
 * @package saadatmehr
 */

defined( 'ABSPATH' ) || exit;

$c = sm_home_content();

get_header();
?>

<main id="main" class="sm-home" role="main">

	<?php
	/* ============ ۱ — هیرو ============
	 *
	 * وقتی عکس تیم هست، دو چیدمان ممکن است — با کلید 'layout' در
	 * inc/content-home.php انتخاب می‌شود:
	 *
	 *   'split'   عکس یک طرف، متن روی پانل سرمه‌ای طرف دیگر.
	 *             عکس هیچ پرده‌ای نمی‌گیرد و کامل دیده می‌شود.
	 *   'overlay' متن روی خود عکس، با پرده‌ی رنگی روی نیمه‌ی متن.
	 *
	 * 'text_side' می‌گوید متن کدام سمت فیزیکی بنشیند: چپ یا راست.
	 * روی موبایل هر دو حالت یکی می‌شوند: عکس بالا، متن پایین.
	 */
	$hero_src  = ! empty( $c['hero']['image'] ) ? sm_img_src( $c['hero']['image'] ) : '';
	$hero_side = ( 'right' === ( $c['hero']['text_side'] ?? 'left' ) ) ? 'right' : 'left';
	$hero_mode = ( 'overlay' === ( $c['hero']['layout'] ?? 'split' ) ) ? 'overlay' : 'split';

	$hero_class = 'sm-hero';

	if ( $hero_src ) {
		$hero_class .= ' sm-hero--photo sm-hero--' . $hero_mode . ' sm-hero--text-' . $hero_side;
	}
	?>
	<section class="<?php echo esc_attr( $hero_class ); ?>" aria-labelledby="sm-hero-title">
		<div class="sm-hero__bg">
			<?php if ( $hero_src ) : ?>
				<img src="<?php echo esc_url( $hero_src ); ?>"
				     alt="<?php echo esc_attr( $c['hero']['image_alt'] ?? '' ); ?>"
				     class="sm-hero__photo" loading="eager" fetchpriority="high" decoding="async">
			<?php else : ?>
				<img src="<?php echo esc_url( sm_img( 'logo-seal.png' ) ); ?>" alt="" class="sm-hero__seal" loading="eager" decoding="async" aria-hidden="true">
			<?php endif; ?>
		</div>
		<div class="sm-wrap sm-hero__inner">
			<h1 id="sm-hero-title" class="sm-hero__title"><?php echo esc_html( $c['hero']['title'] ); ?></h1>
			<p class="sm-hero__subtitle"><?php echo esc_html( $c['hero']['subtitle'] ); ?></p>
			<div class="sm-hero__actions">
				<a class="sm-btn sm-btn--gold" href="<?php echo esc_url( home_url( $c['hero']['cta_link'] ) ); ?>">
					<?php echo esc_html( $c['hero']['cta_text'] ); ?>
				</a>
				<a class="sm-btn sm-btn--ghost" href="<?php echo esc_url( home_url( $c['hero']['cta2_link'] ) ); ?>">
					<?php echo esc_html( $c['hero']['cta2_text'] ); ?>
				</a>
			</div>
			<?php if ( ! empty( $c['hero']['trustline'] ) ) : ?>
				<ul class="sm-hero__trust">
					<?php foreach ( $c['hero']['trustline'] as $t ) : ?>
						<li><?php echo esc_html( $t ); ?></li>
					<?php endforeach; ?>
				</ul>
			<?php endif; ?>
		</div>
	</section>


	<?php /* ============ ۲ — نوار اعتماد سریع ============ */ ?>
	<?php if ( ! empty( $c['trustbar']['items'] ) ) : ?>
		<section class="sm-trustbar" aria-label="اعتبار آکادمی">
			<div class="sm-wrap">
				<ul class="sm-trustbar__list">
					<?php foreach ( $c['trustbar']['items'] as $item ) : ?>
						<li class="sm-trustbar__item">
							<span class="sm-trustbar__icon" aria-hidden="true"><?php sm_icon( $item['icon'] ); ?></span>
							<span class="sm-trustbar__text"><?php echo esc_html( $item['text'] ); ?></span>
						</li>
					<?php endforeach; ?>
				</ul>
			</div>
		</section>
	<?php endif; ?>


	<?php /* ============ ۳ — مسئله‌ی مخاطب ============ */ ?>
	<section class="sm-section sm-problem" aria-labelledby="sm-problem-title">
		<div class="sm-wrap sm-problem__grid">
			<div class="sm-problem__text">
				<p class="sm-eyebrow"><?php echo esc_html( $c['problem']['eyebrow'] ); ?></p>
				<h2 id="sm-problem-title" class="sm-section__title"><?php echo esc_html( $c['problem']['title'] ); ?></h2>
				<?php foreach ( $c['problem']['paragraphs'] as $p ) : ?>
					<p class="sm-lead"><?php echo esc_html( $p ); ?></p>
				<?php endforeach; ?>
			</div>
			<ul class="sm-problem__list sm-reveal">
				<?php foreach ( $c['problem']['items'] as $item ) : ?>
					<li><?php echo esc_html( $item ); ?></li>
				<?php endforeach; ?>
			</ul>
		</div>
	</section>


	<?php /* ============ ۴ — معرفی پروتکل SMP ============ */ ?>
	<section class="sm-section sm-protocol" aria-labelledby="sm-protocol-title">
		<div class="sm-wrap">
			<header class="sm-section__head sm-section__head--center">
				<p class="sm-eyebrow"><?php echo esc_html( $c['protocol']['eyebrow'] ); ?></p>
				<h2 id="sm-protocol-title" class="sm-section__title"><?php echo esc_html( $c['protocol']['title'] ); ?></h2>
				<p class="sm-lead sm-lead--center"><?php echo esc_html( $c['protocol']['lead'] ); ?></p>
			</header>

			<ol class="sm-phases">
				<?php foreach ( $c['protocol']['phases'] as $i => $ph ) : ?>
					<li class="sm-phase sm-reveal">
						<span class="sm-phase__num" aria-hidden="true"><?php echo esc_html( sm_fa_digits( $i + 1 ) ); ?></span>
						<span class="sm-phase__en"><?php echo esc_html( $ph['en'] ); ?></span>
						<h3 class="sm-phase__fa"><?php echo esc_html( $ph['fa'] ); ?></h3>
						<p class="sm-phase__text"><?php echo esc_html( $ph['text'] ); ?></p>
					</li>
				<?php endforeach; ?>
			</ol>

			<p class="sm-center">
				<a class="sm-btn sm-btn--navy" href="<?php echo esc_url( home_url( $c['protocol']['cta_link'] ) ); ?>">
					<?php echo esc_html( $c['protocol']['cta_text'] ); ?>
				</a>
			</p>
		</div>
	</section>


	<?php /* ============ ۵ — برنامه ۱۰۰ روزه ============ */ ?>
	<section class="sm-section sm-weeks" aria-labelledby="sm-weeks-title">
		<div class="sm-wrap">
			<header class="sm-section__head sm-section__head--center">
				<p class="sm-eyebrow"><?php echo esc_html( $c['weeks']['eyebrow'] ); ?></p>
				<h2 id="sm-weeks-title" class="sm-section__title"><?php echo esc_html( $c['weeks']['title'] ); ?></h2>
			</header>

			<ol class="sm-weeks__track">
				<?php foreach ( $c['weeks']['items'] as $w ) : ?>
					<li class="sm-week sm-reveal">
						<span class="sm-week__range"><?php echo esc_html( $w['range'] ); ?></span>
						<h3 class="sm-week__title"><?php echo esc_html( $w['title'] ); ?></h3>
						<p class="sm-week__text"><?php echo esc_html( $w['text'] ); ?></p>
					</li>
				<?php endforeach; ?>
			</ol>

			<?php if ( ! empty( $c['weeks']['note'] ) ) : ?>
				<p class="sm-note"><?php echo esc_html( $c['weeks']['note'] ); ?></p>
			<?php endif; ?>
		</div>
	</section>


	<?php /* ============ ۶ — نتایج و بازتاب رسانه‌ای ============ */ ?>
	<section class="sm-section sm-proof" aria-labelledby="sm-proof-title">
		<div class="sm-wrap">
			<header class="sm-section__head sm-section__head--center">
				<p class="sm-eyebrow"><?php echo esc_html( $c['proof']['eyebrow'] ); ?></p>
				<h2 id="sm-proof-title" class="sm-section__title"><?php echo esc_html( $c['proof']['title'] ); ?></h2>
				<p class="sm-lead sm-lead--center"><?php echo esc_html( $c['proof']['lead'] ); ?></p>
			</header>

			<?php if ( ! empty( $c['proof']['testimonials_enabled'] ) && ! empty( $c['proof']['testimonials'] ) ) : ?>
				<ul class="sm-quotes">
					<?php foreach ( $c['proof']['testimonials'] as $t ) : ?>
						<li class="sm-quote sm-reveal">
							<blockquote><p><?php echo esc_html( $t['quote'] ); ?></p></blockquote>
							<p class="sm-quote__meta">
								<span class="sm-quote__name"><?php echo esc_html( $t['name'] ); ?></span>
								<?php if ( ! empty( $t['meta'] ) ) : ?>
									<span class="sm-quote__extra"><?php echo esc_html( $t['meta'] ); ?></span>
								<?php endif; ?>
							</p>
						</li>
					<?php endforeach; ?>
				</ul>
			<?php endif; ?>

			<?php
			/*
			 * فقط چند کارت اول در صفحه‌ی اصلی می‌آید؛ بقیه در /media/.
			 * تعدادش در inc/content-home.php کلید media_limit است.
			 */
			$media_all   = ! empty( $c['proof']['media'] ) ? $c['proof']['media'] : array();
			$media_limit = isset( $c['proof']['media_limit'] ) ? (int) $c['proof']['media_limit'] : 0;
			$media_shown = $media_limit > 0 ? array_slice( $media_all, 0, $media_limit ) : $media_all;
			?>
			<?php if ( $media_shown ) : ?>
				<ul class="sm-media__grid">
					<?php foreach ( $media_shown as $m ) : ?>
						<li class="sm-media__item sm-reveal">
							<a class="sm-media__card" href="<?php echo esc_url( $m['url'] ); ?>" target="_blank" rel="noopener noreferrer">
								<span class="sm-media__logo"><?php sm_media_logo( $m ); ?></span>
								<span class="sm-media__title"><?php echo esc_html( $m['title'] ); ?></span>
								<span class="sm-media__outlet"><?php echo esc_html( $m['outlet'] ); ?></span>
								<span class="sm-media__cta">
									مشاهده مصاحبه
									<span class="screen-reader-text">در <?php echo esc_html( $m['outlet'] ); ?> — در پنجره جدید باز می‌شود</span>
								</span>
							</a>
						</li>
					<?php endforeach; ?>
				</ul>

				<?php if ( count( $media_all ) > count( $media_shown ) && ! empty( $c['proof']['media_link'] ) ) : ?>
					<p class="sm-media__more">
						<a class="sm-link-more" href="<?php echo esc_url( home_url( $c['proof']['media_link'] ) ); ?>">
							<?php echo esc_html( $c['proof']['media_cta'] ); ?> <span aria-hidden="true">←</span>
						</a>
					</p>
				<?php endif; ?>
			<?php endif; ?>
		</div>
	</section>


	<?php /* ============ ۶٫۵ — پشتوانه‌ی علمی ============ */ ?>
	<?php sm_home_council( $c ); ?>


	<?php /* ============ ۷ — تیم ============ */ ?>
	<section class="sm-section sm-team" aria-labelledby="sm-team-title">
		<div class="sm-wrap">
			<header class="sm-section__head sm-section__head--center">
				<p class="sm-eyebrow"><?php echo esc_html( $c['team']['eyebrow'] ); ?></p>
				<h2 id="sm-team-title" class="sm-section__title"><?php echo esc_html( $c['team']['title'] ); ?></h2>
			</header>

			<ul class="sm-team__grid">
				<?php foreach ( $c['team']['members'] as $m ) : ?>
					<li class="sm-team__card sm-reveal">
						<?php sm_person_avatar( $m ); ?>
						<h3 class="sm-team__name"><?php echo esc_html( $m['name'] ); ?></h3>
						<p class="sm-team__role"><?php echo esc_html( $m['role'] ); ?></p>
						<p class="sm-team__text"><?php echo esc_html( $m['text'] ); ?></p>
					</li>
				<?php endforeach; ?>
			</ul>

			<p class="sm-center">
				<a class="sm-btn sm-btn--outline" href="<?php echo esc_url( home_url( $c['team']['cta_link'] ) ); ?>">
					<?php echo esc_html( $c['team']['cta_text'] ); ?>
				</a>
			</p>
		</div>
	</section>


	<?php /* ============ ۸ — کتاب (نقش پشتیبان) ============ */ ?>
	<section class="sm-section sm-book" aria-labelledby="sm-book-title">
		<div class="sm-wrap sm-book__grid">
			<div class="sm-book__visual sm-reveal">
				<?php if ( ! empty( $c['book']['cover'] ) ) : ?>
					<img class="sm-book__cover-img" src="<?php echo esc_url( sm_img( $c['book']['cover'] ) ); ?>"
					     alt="جلد کتاب معماری متابولیک" loading="lazy" decoding="async">
				<?php else : ?>
					<?php sm_book_mockup( 'معماری متابولیک', 'پروتکل SMP' ); ?>
				<?php endif; ?>
			</div>
			<div class="sm-book__text">
				<p class="sm-eyebrow"><?php echo esc_html( $c['book']['eyebrow'] ); ?></p>
				<h2 id="sm-book-title" class="sm-section__title"><?php echo esc_html( $c['book']['title'] ); ?></h2>
				<?php foreach ( $c['book']['paragraphs'] as $p ) : ?>
					<p class="sm-book__p"><?php echo esc_html( $p ); ?></p>
				<?php endforeach; ?>
				<a class="sm-btn sm-btn--outline" href="<?php echo esc_url( home_url( $c['book']['cta_link'] ) ); ?>">
					<?php echo esc_html( $c['book']['cta_text'] ); ?>
				</a>
			</div>
		</div>
	</section>


	<?php /* ============ ۸٫۵ — مقالات ============ */ ?>
	<?php if ( ! empty( $c['articles']['enabled'] ) ) : ?>
		<?php
		$posts = get_posts(
			array(
				'numberposts'      => (int) $c['articles']['count'],
				'post_status'      => 'publish',
				'suppress_filters' => false,
			)
		);
		?>
		<section class="sm-section sm-articles" aria-labelledby="sm-articles-title">
			<div class="sm-wrap">
				<header class="sm-section__head sm-section__head--row">
					<div>
						<p class="sm-eyebrow"><?php echo esc_html( $c['articles']['eyebrow'] ); ?></p>
						<h2 id="sm-articles-title" class="sm-section__title"><?php echo esc_html( $c['articles']['title'] ); ?></h2>
					</div>
					<?php if ( $posts ) : ?>
						<a class="sm-link-more" href="<?php echo esc_url( home_url( $c['articles']['cta_link'] ) ); ?>">
							<?php echo esc_html( $c['articles']['cta_text'] ); ?> <span aria-hidden="true">←</span>
						</a>
					<?php endif; ?>
				</header>

				<?php if ( $posts ) : ?>
					<ul class="sm-articles__grid">
						<?php foreach ( $posts as $post ) : setup_postdata( $post ); ?>
							<?php sm_article_card( $post ); ?>
						<?php endforeach; wp_reset_postdata(); ?>
					</ul>
				<?php else : ?>
					<p class="sm-empty"><?php echo esc_html( $c['articles']['empty_text'] ); ?></p>
				<?php endif; ?>
			</div>
		</section>
	<?php endif; ?>


	<?php /* ============ ۹ — فراخوان نهایی ============ */ ?>
	<section class="sm-closing" aria-labelledby="sm-closing-title">
		<div class="sm-wrap sm-closing__inner">
			<h2 id="sm-closing-title" class="sm-closing__title"><?php echo esc_html( $c['closing']['title'] ); ?></h2>
			<p class="sm-closing__text"><?php echo esc_html( $c['closing']['text'] ); ?></p>
			<a class="sm-btn sm-btn--gold" href="<?php echo esc_url( home_url( $c['closing']['cta_link'] ) ); ?>">
				<?php echo esc_html( $c['closing']['cta_text'] ); ?>
			</a>
			<?php if ( ! empty( $c['closing']['notes'] ) ) : ?>
				<ul class="sm-closing__notes">
					<?php foreach ( $c['closing']['notes'] as $n ) : ?>
						<li><?php echo esc_html( $n ); ?></li>
					<?php endforeach; ?>
				</ul>
			<?php endif; ?>
		</div>
	</section>

</main>

<?php
get_footer();
