<?php
/**
 * Template Name: صفحه نقشه راه SMP
 *
 * برای نشانی /smp/map/ که کد QR انتهای فصل سوم کتاب به آن اشاره می‌کند.
 * متن‌ها در inc/content-pages.php کلید 'map' هستند.
 *
 * @package saadatmehr
 */

defined( 'ABSPATH' ) || exit;

$c = sm_page_content( 'map' );

get_header();
?>

<main id="main" class="sm-page sm-page--map" role="main">

	<section class="sm-phead sm-phead--compact" aria-labelledby="sm-map-title">
		<div class="sm-wrap sm-phead__inner">
			<p class="sm-phead__eyebrow"><?php echo esc_html( $c['eyebrow'] ); ?></p>
			<h1 id="sm-map-title" class="sm-phead__title"><?php echo esc_html( $c['title'] ); ?></h1>
			<p class="sm-phead__lead"><?php echo esc_html( $c['lead'] ); ?></p>
		</div>
	</section>

	<?php /* اینفوگرافیک — روی موبایل داخل قاب افقی اسکرول می‌شود */ ?>
	<?php $map_img = ! empty( $c['image'] ) ? sm_img_src( $c['image'] ) : ''; ?>
	<?php if ( $map_img ) : ?>
		<section class="sm-section sm-mapfig">
			<div class="sm-wrap">
				<figure class="sm-mapfig__frame">
					<img src="<?php echo esc_url( $map_img ); ?>"
					     alt="<?php echo esc_attr( $c['image_alt'] ); ?>"
					     loading="lazy" decoding="async">
				</figure>
				<p class="sm-mapfig__hint">برای دیدن جزئیات، تصویر را بزرگ کنید یا افقی بکشید.</p>
			</div>
		</section>
	<?php endif; ?>

	<section class="sm-section sm-mapphases">
		<div class="sm-wrap">
			<ol class="sm-mapphases__list">
				<?php foreach ( $c['phases'] as $ph ) : ?>
					<li class="sm-mapphase sm-reveal">
						<header class="sm-mapphase__head">
							<span class="sm-mapphase__num" aria-hidden="true"><?php echo esc_html( $ph['num'] ); ?></span>
							<div>
								<h2 class="sm-mapphase__title">
									<span class="sm-mapphase__en"><?php echo esc_html( $ph['en'] ); ?></span>
									<span class="sm-mapphase__fa"><?php echo esc_html( $ph['fa'] ); ?></span>
								</h2>
								<p class="sm-mapphase__goal"><?php echo esc_html( $ph['goal'] ); ?></p>
							</div>
						</header>
						<ul class="sm-mapphase__items">
							<?php foreach ( $ph['items'] as $it ) : ?>
								<li><?php echo esc_html( $it ); ?></li>
							<?php endforeach; ?>
						</ul>
						<p class="sm-mapphase__signal">
							<span class="sm-mapphase__signal-label">نشانه‌ی عبور</span>
							<?php echo esc_html( $ph['signal'] ); ?>
						</p>
					</li>
				<?php endforeach; ?>
			</ol>

			<?php if ( ! empty( $c['note'] ) ) : ?>
				<p class="sm-note sm-note--gold"><?php echo esc_html( $c['note'] ); ?></p>
			<?php endif; ?>
		</div>
	</section>

	<section class="sm-closing">
		<div class="sm-wrap sm-closing__inner">
			<a class="sm-btn sm-btn--gold" href="<?php echo esc_url( home_url( $c['cta_link'] ) ); ?>"><?php echo esc_html( $c['cta_text'] ); ?></a>
		</div>
	</section>

</main>

<?php
get_footer();
