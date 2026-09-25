<?php
/**
 * Template Name: صفحه کتاب معماری متابولیک
 *
 * نشانی: /book/
 * متن‌ها در inc/content-book.php کلید 'book' هستند.
 *
 * @package saadatmehr
 */

defined( 'ABSPATH' ) || exit;

$c = sm_page_content( 'book' );

$on_sale = ! empty( $c['sale_enabled'] ) && ! empty( $c['buy_link'] );

get_header();
?>

<main id="main" class="sm-page sm-page--book" role="main">

	<?php /* ============ ۱ — سربرگ فروش ============ */ ?>
	<section class="sm-bhero" aria-labelledby="sm-book-title">
		<div class="sm-wrap sm-bhero__grid">

			<div class="sm-bhero__text">
				<p class="sm-phead__eyebrow"><?php echo esc_html( $c['eyebrow'] ); ?></p>
				<h1 id="sm-book-title" class="sm-phead__title"><?php echo esc_html( $c['title'] ); ?></h1>
				<p class="sm-bhero__sub"><?php echo esc_html( $c['subtitle'] ); ?></p>

				<?php foreach ( $c['lead'] as $t ) : ?>
					<p class="sm-phead__lead"><?php echo esc_html( $t ); ?></p>
				<?php endforeach; ?>

				<?php if ( ! $on_sale ) : ?>
					<p class="sm-bhero__soon"><?php echo esc_html( $c['soon_text'] ); ?></p>
				<?php endif; ?>

				<div class="sm-hero__actions">
					<?php if ( $on_sale ) : ?>
						<a class="sm-btn sm-btn--gold" href="<?php echo esc_url( $c['buy_link'] ); ?>">
							<?php echo esc_html( $c['buy_text'] ); ?>
						</a>
						<?php if ( ! empty( $c['price'] ) ) : ?>
							<span class="sm-bhero__price"><?php echo esc_html( $c['price'] ); ?></span>
						<?php endif; ?>
					<?php else : ?>
						<a class="sm-btn sm-btn--gold" href="<?php echo esc_url( home_url( $c['notify_link'] ) ); ?>">
							<?php echo esc_html( $c['notify_text'] ); ?>
						</a>
					<?php endif; ?>

					<a class="sm-btn sm-btn--ghost" href="<?php echo esc_attr( $c['toc_anchor'] ); ?>">
						<?php echo esc_html( $c['toc_text'] ); ?>
					</a>
				</div>
			</div>

			<div class="sm-bhero__media">
				<?php $cover = ! empty( $c['cover'] ) ? sm_img_src( $c['cover'] ) : ''; ?>
				<?php if ( $cover ) : ?>
					<img class="sm-bhero__cover" src="<?php echo esc_url( $cover ); ?>"
					     alt="<?php echo esc_attr( $c['cover_alt'] ); ?>" loading="eager" decoding="async">
				<?php else : ?>
					<?php sm_book_mockup( 'معماری متابولیک', $c['subtitle'] ); ?>
				<?php endif; ?>

				<?php
				// ردیف‌های بدون مقدار اصلاً چاپ نمی‌شوند — هیچ‌وقت
				// روی سایت یک متخصص سلامت عدد حدسی نمی‌گذاریم.
				$facts = array_filter(
					$c['facts'],
					static function ( $f ) {
						return '' !== trim( $f['value'] );
					}
				);
				?>
				<?php if ( $facts ) : ?>
					<dl class="sm-facts">
						<?php foreach ( $facts as $f ) : ?>
							<div class="sm-facts__row">
								<dt><?php echo esc_html( $f['label'] ); ?></dt>
								<dd><?php echo esc_html( $f['value'] ); ?></dd>
							</div>
						<?php endforeach; ?>
					</dl>
				<?php endif; ?>
			</div>

		</div>
	</section>


	<?php /* ============ ۲ — این کتاب برای چه کسی است ============ */ ?>
	<section class="sm-section sm-fit" aria-labelledby="sm-fit-title">
		<div class="sm-wrap sm-fit__grid">
			<div class="sm-fit__col sm-fit__col--yes sm-reveal">
				<h2 id="sm-fit-title" class="sm-block__title"><?php echo esc_html( $c['fit']['title'] ); ?></h2>
				<ul class="sm-ticklist">
					<?php foreach ( $c['fit']['yes'] as $t ) : ?>
						<li><?php echo esc_html( $t ); ?></li>
					<?php endforeach; ?>
				</ul>
			</div>
			<div class="sm-fit__col sm-fit__col--no sm-reveal">
				<h2 class="sm-block__title"><?php echo esc_html( $c['fit']['no_title'] ); ?></h2>
				<ul class="sm-crosslist">
					<?php foreach ( $c['fit']['no'] as $t ) : ?>
						<li><?php echo esc_html( $t ); ?></li>
					<?php endforeach; ?>
				</ul>
			</div>
		</div>
	</section>


	<?php /* ============ ۳ — ارزش کتاب ============ */ ?>
	<section class="sm-section sm-prose-section" aria-labelledby="sm-value-title">
		<div class="sm-wrap">
			<header class="sm-section__head sm-section__head--center">
				<p class="sm-eyebrow"><?php echo esc_html( $c['value']['eyebrow'] ); ?></p>
				<h2 id="sm-value-title" class="sm-section__title"><?php echo esc_html( $c['value']['title'] ); ?></h2>
			</header>
			<ul class="sm-ticklist sm-ticklist--two">
				<?php foreach ( $c['value']['items'] as $t ) : ?>
					<li class="sm-reveal"><?php echo esc_html( $t ); ?></li>
				<?php endforeach; ?>
			</ul>
		</div>
	</section>


	<?php /* ============ ۴ — هفت فصل ============ */ ?>
	<section id="chapters" class="sm-section sm-chapters" aria-labelledby="sm-ch-title">
		<div class="sm-wrap">
			<header class="sm-section__head sm-section__head--center">
				<p class="sm-eyebrow"><?php echo esc_html( $c['chapters']['eyebrow'] ); ?></p>
				<h2 id="sm-ch-title" class="sm-section__title"><?php echo esc_html( $c['chapters']['title'] ); ?></h2>
			</header>
			<ol class="sm-chapters__list">
				<?php foreach ( $c['chapters']['items'] as $ch ) : ?>
					<li class="sm-chapter sm-reveal">
						<span class="sm-chapter__num" aria-hidden="true"><?php echo esc_html( $ch['num'] ); ?></span>
						<div class="sm-chapter__body">
							<h3 class="sm-chapter__name"><?php echo esc_html( $ch['name'] ); ?></h3>
							<p class="sm-chapter__text"><?php echo esc_html( $ch['text'] ); ?></p>
						</div>
					</li>
				<?php endforeach; ?>
			</ol>
		</div>
	</section>


	<?php /* ============ ۵ — بعد از خواندن کتاب ============ */ ?>
	<section class="sm-section sm-after" aria-labelledby="sm-after-title">
		<div class="sm-wrap">
			<header class="sm-section__head sm-section__head--center">
				<p class="sm-eyebrow"><?php echo esc_html( $c['after']['eyebrow'] ); ?></p>
				<h2 id="sm-after-title" class="sm-section__title"><?php echo esc_html( $c['after']['title'] ); ?></h2>
			</header>
			<ul class="sm-ticklist sm-ticklist--two">
				<?php foreach ( $c['after']['items'] as $t ) : ?>
					<li class="sm-reveal"><?php echo esc_html( $t ); ?></li>
				<?php endforeach; ?>
			</ul>
		</div>
	</section>


	<?php /* ============ ۶ — نویسنده ============ */ ?>
	<section class="sm-section sm-prose-section" aria-labelledby="sm-author-title">
		<div class="sm-wrap sm-split">
			<div class="sm-split__media sm-reveal sm-split__media--author">
				<?php sm_person_avatar( $c['author'] ); ?>
			</div>
			<div class="sm-split__text sm-reveal">
				<p class="sm-eyebrow"><?php echo esc_html( $c['author']['eyebrow'] ); ?></p>
				<h2 id="sm-author-title" class="sm-block__title"><?php echo esc_html( $c['author']['name'] ); ?></h2>
				<p class="sm-person__role"><?php echo esc_html( $c['author']['role'] ); ?></p>
				<?php foreach ( $c['author']['text'] as $t ) : ?>
					<p class="sm-block__text"><?php echo esc_html( $t ); ?></p>
				<?php endforeach; ?>
			</div>
		</div>
	</section>


	<?php /* ============ ۶٫۵ — کتاب پیشین ============ */ ?>
	<?php
	$prev = isset( $c['previous'] ) ? $c['previous'] : array();

	// اگر جلدِ رو موجود باشد کتابِ سه‌بعدیِ چرخان را می‌سازیم؛
	// وگرنه به همان تصویرِ تختِ قبلی برمی‌گردیم.
	$prev_3d  = ! empty( $prev['enabled'] ) && ! empty( $prev['front'] ) && sm_has_img( $prev['front'] );
	$prev_src = ! empty( $prev['enabled'] ) && ! empty( $prev['image'] ) ? sm_img_src( $prev['image'] ) : '';
	?>
	<?php if ( $prev_3d || $prev_src ) : ?>
		<section class="sm-section sm-prevbook" aria-labelledby="sm-prev-title">
			<div class="sm-wrap sm-split">
				<div class="sm-split__text sm-reveal">
					<p class="sm-eyebrow"><?php echo esc_html( $prev['eyebrow'] ); ?></p>
					<h2 id="sm-prev-title" class="sm-block__title"><?php echo esc_html( $prev['title'] ); ?></h2>
					<p class="sm-prevbook__name"><?php echo esc_html( $prev['name'] ); ?></p>
					<?php foreach ( $prev['text'] as $t ) : ?>
						<p class="sm-block__text"><?php echo esc_html( $t ); ?></p>
					<?php endforeach; ?>
				</div>
				<figure class="sm-split__media sm-reveal sm-prevbook__fig">
					<?php if ( $prev_3d ) : ?>
						<?php sm_cover3d( $prev ); ?>
					<?php else : ?>
						<img class="sm-prevbook__img" src="<?php echo esc_url( $prev_src ); ?>"
						     alt="<?php echo esc_attr( $prev['image_alt'] ); ?>" loading="lazy" decoding="async">
						<?php /* در حالت سه‌بعدی این زیرنویس نمی‌آید؛ دو دکمه‌ی
						         «جلد رو / جلد پشت» همان کار را بهتر می‌کنند. */ ?>
						<figcaption class="sm-prevbook__cap"><?php echo esc_html( $prev['caption'] ); ?></figcaption>
					<?php endif; ?>
				</figure>
			</div>
		</section>
	<?php endif; ?>


	<?php /* ============ ۷ — نوار شورای علمی ============ */ ?>
	<section class="sm-section sm-councilbar" aria-labelledby="sm-cb-title">
		<div class="sm-wrap sm-councilbar__inner">
			<h2 id="sm-cb-title" class="sm-councilbar__title"><?php echo esc_html( $c['council_teaser']['title'] ); ?></h2>
			<p class="sm-councilbar__text"><?php echo esc_html( $c['council_teaser']['text'] ); ?></p>
			<a class="sm-btn sm-btn--ghost" href="<?php echo esc_url( home_url( $c['council_teaser']['link'] ) ); ?>">
				<?php echo esc_html( $c['council_teaser']['cta'] ); ?>
			</a>
		</div>
	</section>


	<?php /* ============ ۸ — فراخوان پایانی ============ */ ?>
	<section class="sm-closing" aria-labelledby="sm-book-closing">
		<div class="sm-wrap sm-closing__inner">
			<h2 id="sm-book-closing" class="sm-closing__title"><?php echo esc_html( $c['closing_title'] ); ?></h2>
			<p class="sm-closing__text"><?php echo esc_html( $c['closing_text'] ); ?></p>
			<a class="sm-btn sm-btn--gold" href="<?php echo esc_url( home_url( $c['closing_link'] ) ); ?>">
				<?php echo esc_html( $c['closing_cta'] ); ?>
			</a>
		</div>
	</section>

</main>

<?php
get_footer();
