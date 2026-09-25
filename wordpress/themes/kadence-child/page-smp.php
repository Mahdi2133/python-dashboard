<?php
/**
 * Template Name: صفحه پروتکل SMP
 *
 * متن‌ها در inc/content-pages.php کلید 'smp' هستند.
 *
 * @package saadatmehr
 */

defined( 'ABSPATH' ) || exit;

$c = sm_page_content( 'smp' );

get_header();
?>

<main id="main" class="sm-page sm-page--smp" role="main">

	<section class="sm-phead" aria-labelledby="sm-phead-title">
		<div class="sm-phead__bg" aria-hidden="true">
			<img src="<?php echo esc_url( sm_img( 'logo-seal.png' ) ); ?>" alt="" class="sm-phead__seal" loading="eager" decoding="async">
		</div>
		<div class="sm-wrap sm-phead__inner">
			<p class="sm-phead__eyebrow"><?php echo esc_html( $c['eyebrow'] ); ?></p>
			<h1 id="sm-phead-title" class="sm-phead__title"><?php echo esc_html( $c['title'] ); ?></h1>
			<?php foreach ( $c['lead'] as $p ) : ?>
				<p class="sm-phead__lead"><?php echo esc_html( $p ); ?></p>
			<?php endforeach; ?>
			<div class="sm-hero__actions">
				<a class="sm-btn sm-btn--gold" href="<?php echo esc_url( home_url( $c['cta_link'] ) ); ?>"><?php echo esc_html( $c['cta_text'] ); ?></a>
				<a class="sm-btn sm-btn--ghost" href="<?php echo esc_url( home_url( $c['cta2_link'] ) ); ?>"><?php echo esc_html( $c['cta2_text'] ); ?></a>
			</div>
			<?php if ( ! empty( $c['trustline'] ) ) : ?>
				<p class="sm-phead__trust"><?php echo esc_html( $c['trustline'] ); ?></p>
			<?php endif; ?>
		</div>
	</section>

	<section class="sm-section sm-protocol" aria-label="سه مرحله پروتکل">
		<div class="sm-wrap">
			<ol class="sm-phases">
				<?php foreach ( $c['phases'] as $ph ) : ?>
					<li class="sm-phase sm-reveal">
						<span class="sm-phase__num" aria-hidden="true"><?php echo esc_html( $ph['num'] ); ?></span>
						<span class="sm-phase__en"><?php echo esc_html( $ph['en'] ); ?></span>
						<h2 class="sm-phase__fa"><?php echo esc_html( $ph['fa'] ); ?></h2>
						<p class="sm-phase__text"><?php echo esc_html( $ph['text'] ); ?></p>
					</li>
				<?php endforeach; ?>
			</ol>
		</div>
	</section>

	<?php if ( ! empty( $c['monitor'] ) ) : $m = $c['monitor']; ?>
	<section class="sm-section sm-monitor" aria-labelledby="sm-monitor-title">
		<div class="sm-wrap sm-split">
			<div class="sm-split__text sm-reveal">
				<p class="sm-eyebrow"><?php echo esc_html( $m['eyebrow'] ); ?></p>
				<h2 id="sm-monitor-title" class="sm-block__title"><?php echo esc_html( $m['title'] ); ?></h2>
				<?php foreach ( $m['text'] as $t ) : ?>
					<p class="sm-block__text"><?php echo esc_html( $t ); ?></p>
				<?php endforeach; ?>
				<ul class="sm-ticklist">
					<?php foreach ( $m['items'] as $item ) : ?>
						<li><?php echo esc_html( $item ); ?></li>
					<?php endforeach; ?>
				</ul>
			</div>
			<div class="sm-split__media sm-reveal">
				<?php sm_biometric_panel(); ?>
				<p class="sm-split__note"><?php echo esc_html( $m['note'] ); ?></p>
			</div>
		</div>
	</section>
	<?php endif; ?>

	<section class="sm-section sm-prose-section">
		<div class="sm-wrap sm-measure">
			<?php foreach ( $c['sections'] as $sec ) : ?>
				<div class="sm-block sm-reveal">
					<h2 class="sm-block__title"><?php echo esc_html( $sec['title'] ); ?></h2>
					<?php foreach ( $sec['text'] as $t ) : ?>
						<p class="sm-block__text"><?php echo esc_html( $t ); ?></p>
					<?php endforeach; ?>
				</div>
			<?php endforeach; ?>
		</div>
	</section>

	<section class="sm-closing" aria-labelledby="sm-smp-closing">
		<div class="sm-wrap sm-closing__inner">
			<h2 id="sm-smp-closing" class="sm-closing__title"><?php echo esc_html( $c['closing_title'] ); ?></h2>
			<p class="sm-closing__text"><?php echo esc_html( $c['closing_text'] ); ?></p>
			<a class="sm-btn sm-btn--gold" href="<?php echo esc_url( home_url( $c['cta_link'] ) ); ?>"><?php echo esc_html( $c['cta_text'] ); ?></a>
		</div>
	</section>

</main>

<?php
get_footer();
