<?php
/**
 * Template Name: صفحه درباره ما
 *
 * متن‌ها در inc/content-pages.php کلید 'about' هستند.
 *
 * @package saadatmehr
 */

defined( 'ABSPATH' ) || exit;

$c = sm_page_content( 'about' );

get_header();
?>

<main id="main" class="sm-page sm-page--about" role="main">

	<?php
	/* سربرگ صفحه — همان منطق هیروی صفحه‌ی اصلی.
	   توضیح کامل چیدمان‌ها در page-home.php آمده است. */
	$head_src  = ! empty( $c['image'] ) ? sm_img_src( $c['image'] ) : '';
	$head_side = ( 'left' === ( $c['text_side'] ?? 'right' ) ) ? 'left' : 'right';
	$head_mode = ( 'overlay' === ( $c['layout'] ?? 'split' ) ) ? 'overlay' : 'split';

	$head_class = 'sm-phead';

	if ( $head_src ) {
		$head_class .= ' sm-phead--photo sm-phead--' . $head_mode . ' sm-phead--text-' . $head_side;
	} else {
		$head_class .= ' sm-phead--compact';
	}
	?>
	<section class="<?php echo esc_attr( trim( $head_class ) ); ?>" aria-labelledby="sm-about-title">
		<?php if ( $head_src ) : ?>
			<div class="sm-phead__bg">
				<img src="<?php echo esc_url( $head_src ); ?>"
				     alt="<?php echo esc_attr( $c['image_alt'] ?? '' ); ?>"
				     class="sm-phead__photo" loading="eager" fetchpriority="high" decoding="async">
			</div>
		<?php endif; ?>
		<div class="sm-wrap sm-phead__inner">
			<p class="sm-phead__eyebrow"><?php echo esc_html( $c['eyebrow'] ); ?></p>
			<h1 id="sm-about-title" class="sm-phead__title"><?php echo esc_html( $c['title'] ); ?></h1>
			<?php foreach ( $c['lead'] as $p ) : ?>
				<p class="sm-phead__lead"><?php echo esc_html( $p ); ?></p>
			<?php endforeach; ?>
		</div>
	</section>

	<section class="sm-section sm-protocol">
		<div class="sm-wrap">
			<header class="sm-section__head sm-section__head--center">
				<h2 class="sm-section__title"><?php echo esc_html( $c['phases_title'] ); ?></h2>
			</header>
			<ol class="sm-phases">
				<?php foreach ( $c['phases'] as $i => $ph ) : ?>
					<li class="sm-phase sm-reveal">
						<span class="sm-phase__num" aria-hidden="true"><?php echo esc_html( sm_fa_digits( $i + 1 ) ); ?></span>
						<span class="sm-phase__en"><?php echo esc_html( $ph['en'] ); ?></span>
						<h3 class="sm-phase__fa"><?php echo esc_html( $ph['fa'] ); ?></h3>
						<p class="sm-phase__text"><?php echo esc_html( $ph['text'] ); ?></p>
					</li>
				<?php endforeach; ?>
			</ol>
			<div class="sm-measure sm-measure--center">
				<?php foreach ( $c['after_phases'] as $t ) : ?>
					<p class="sm-block__text"><?php echo esc_html( $t ); ?></p>
				<?php endforeach; ?>
			</div>
		</div>
	</section>

	<section class="sm-section sm-founders" aria-labelledby="sm-founders-title">
		<div class="sm-wrap">
			<header class="sm-section__head sm-section__head--center">
				<h2 id="sm-founders-title" class="sm-section__title"><?php echo esc_html( $c['founders_title'] ); ?></h2>
			</header>
			<div class="sm-founders__list">
				<?php foreach ( $c['founders'] as $m ) : ?>
					<article class="sm-founder sm-reveal">
						<div class="sm-founder__side">
							<?php sm_person_avatar( $m ); ?>
							<h3 class="sm-founder__name"><?php echo esc_html( $m['name'] ); ?></h3>
							<p class="sm-founder__role"><?php echo esc_html( $m['role'] ); ?></p>
						</div>
						<div class="sm-founder__body">
							<?php foreach ( $m['text'] as $t ) : ?>
								<p><?php echo esc_html( $t ); ?></p>
							<?php endforeach; ?>
						</div>
					</article>
				<?php endforeach; ?>
			</div>
		</div>
	</section>

	<?php
	/*
	 * سکشنِ «همکاران آکادمی» از اینجا برداشته شد.
	 *
	 * رزومه‌ی سعید نمازی حالا صفحه‌ی مستقلِ خودش را دارد:
	 *     page-namazi.php  →  /saeednamazi/
	 * و از منوی سربرگ باز می‌شود، نه از میانه‌ی این صفحه.
	 */
	?>

	<?php /* ============ مدارک و گواهی‌نامه‌ها ============ */ ?>
	<?php $certs = isset( $c['certs'] ) ? $c['certs'] : array(); ?>
	<?php if ( ! empty( $certs['enabled'] ) && ! empty( $certs['items'] ) ) : ?>
		<section class="sm-section sm-certs" aria-labelledby="sm-certs-title">
			<div class="sm-wrap">
				<header class="sm-section__head sm-section__head--center">
					<h2 id="sm-certs-title" class="sm-section__title"><?php echo esc_html( $certs['title'] ); ?></h2>
					<?php if ( ! empty( $certs['text'] ) ) : ?>
						<p class="sm-section__lead"><?php echo esc_html( $certs['text'] ); ?></p>
					<?php endif; ?>
				</header>

				<ul class="sm-certs__grid">
					<?php foreach ( $certs['items'] as $cert ) : ?>
						<?php
						$csrc = sm_img_src( 'certs/' . $cert['file'] );
						if ( ! $csrc ) { continue; }
						$clabel = trim( $cert['title'] . ( ! empty( $cert['sub'] ) ? ' — ' . $cert['sub'] : '' ) );
						?>
						<li class="sm-cert sm-reveal">
							<a class="sm-cert__link" href="<?php echo esc_url( $csrc ); ?>"
							   data-sm-lightbox data-sm-caption="<?php echo esc_attr( $clabel ); ?>"
							   target="_blank" rel="noopener">
								<img class="sm-cert__img" src="<?php echo esc_url( $csrc ); ?>"
								     alt="<?php echo esc_attr( $clabel ); ?>" loading="lazy" decoding="async">
							</a>
							<p class="sm-cert__cap">
								<span class="sm-cert__title"><?php echo esc_html( $cert['title'] ); ?></span>
								<?php if ( ! empty( $cert['sub'] ) ) : ?>
									<span class="sm-cert__sub" dir="ltr"><?php echo esc_html( $cert['sub'] ); ?></span>
								<?php endif; ?>
							</p>
						</li>
					<?php endforeach; ?>
				</ul>
			</div>
		</section>
	<?php endif; ?>

	<section class="sm-section sm-prose-section">
		<div class="sm-wrap sm-measure">
			<h2 class="sm-block__title"><?php echo esc_html( $c['closing_title'] ); ?></h2>
			<?php foreach ( $c['closing_text'] as $t ) : ?>
				<p class="sm-block__text"><?php echo esc_html( $t ); ?></p>
			<?php endforeach; ?>
			<?php if ( ! empty( $c['quote'] ) ) : ?>
				<blockquote class="sm-pullquote"><p><?php echo esc_html( $c['quote'] ); ?></p></blockquote>
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
