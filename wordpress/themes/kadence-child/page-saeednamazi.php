<?php
/**
 * Template Name: صفحه سعید نمازی (انگلیسی)
 *
 * نشانی: /saeednamazi/
 *
 * نامِ فایل عمداً page-saeednamazi.php است، یعنی دقیقاً هم‌نامِ نامکِ
 * برگه. با این کار حتی اگر کسی یادش برود در ویرایشگر «الگو» را
 * انتخاب کند، وردپرس خودش همین فایل را پیدا می‌کند.
 *
 * این تنها صفحه‌ی انگلیسیِ سایت است. کلِ <main> با dir="ltr" رندر
 * می‌شود تا نقطه و کاما و پرانتزها سرِ جای درستشان بنشینند؛ بقیه‌ی
 * صفحه (هدر و فوتر) فارسی و راست‌چین می‌ماند و دست نمی‌خورد.
 *
 * متن‌ها در inc/content-namazi.php هستند.
 *
 * @package saadatmehr
 */

defined( 'ABSPATH' ) || exit;

$c = sm_page_content( 'namazi' );

get_header();
?>

<main id="main" class="sm-page sm-page--namazi" role="main" dir="ltr" lang="en">

<?php if ( empty( $c['enabled'] ) ) : ?>

	<section class="sm-section">
		<div class="sm-wrap">
			<p class="sm-empty">This page is not published yet.</p>
		</div>
	</section>

<?php else : ?>

	<?php /* ============================ Hero ============================ */ ?>
	<?php $portrait = ! empty( $c['portrait'] ) ? sm_img_src( $c['portrait'] ) : ''; ?>
	<section class="sm-nmhero" aria-labelledby="sm-nm-name">
		<div class="sm-wrap sm-nmhero__inner">

			<div class="sm-nmhero__text">
				<?php if ( ! empty( $c['eyebrow'] ) ) : ?>
					<p class="sm-nmhero__eyebrow"><?php echo esc_html( $c['eyebrow'] ); ?></p>
				<?php endif; ?>

				<h1 id="sm-nm-name" class="sm-nmhero__name"><?php echo esc_html( $c['name'] ); ?></h1>

				<?php if ( ! empty( $c['role'] ) ) : ?>
					<p class="sm-nmhero__role"><?php echo esc_html( $c['role'] ); ?></p>
				<?php endif; ?>

				<?php if ( ! empty( $c['tagline'] ) ) : ?>
					<p class="sm-nmhero__tagline">&ldquo;<?php echo esc_html( $c['tagline'] ); ?>&rdquo;</p>
				<?php endif; ?>
			</div>

			<?php if ( $portrait ) : ?>
				<div class="sm-nmhero__media">
					<?php
					/*
					 * قابِ عکس سه لایه است: یک هاله‌ی طلایی پشتش، خودِ
					 * عکس، و یک خطِ نازکِ طلایی که با اسکرول کمی
					 * جابه‌جا می‌شود. هر سه با CSS کار می‌کنند و
					 * بدون جاوااسکریپت هم عکس سرِ جایش است.
					 */
					?>
					<span class="sm-nmhero__glow" aria-hidden="true"></span>
					<img class="sm-nmhero__photo" src="<?php echo esc_url( $portrait ); ?>"
					     alt="<?php echo esc_attr( $c['name'] ); ?>"
					     style="object-position: <?php echo esc_attr( $c['portrait_focus'] ?? '50%' ); ?> center;"
					     width="900" height="600" loading="eager" decoding="async" fetchpriority="high">
					<span class="sm-nmhero__frame" aria-hidden="true"></span>
				</div>
			<?php endif; ?>

		</div>

		<?php if ( ! empty( $c['stats'] ) ) : ?>
			<div class="sm-wrap">
				<ul class="sm-nmstats">
					<?php foreach ( $c['stats'] as $s ) : ?>
						<li class="sm-nmstat sm-reveal">
							<?php
							/*
							 * عدد از همان اول داخل صفحه هست. جاوااسکریپت
							 * فقط آن را از صفر تا همین عدد بالا می‌برد.
							 * اگر اجرا نشود، عددِ درست سرِ جایش می‌ماند.
							 */
							?>
							<span class="sm-nmstat__num" data-sm-count="<?php echo esc_attr( (int) $s['value'] ); ?>">
								<?php echo esc_html( number_format( (int) $s['value'] ) ); ?><?php echo esc_html( $s['suffix'] ); ?>
							</span>
							<span class="sm-nmstat__label"><?php echo esc_html( $s['label'] ); ?></span>
						</li>
					<?php endforeach; ?>
				</ul>
			</div>
		<?php endif; ?>
	</section>

	<?php /* ========================= Biography ========================= */ ?>
	<?php $bio = isset( $c['bio'] ) ? $c['bio'] : array(); ?>
	<?php if ( ! empty( $bio['text'] ) ) : ?>
		<?php $bsrc = ! empty( $bio['image'] ) ? sm_img_src( $bio['image'] ) : ''; ?>
		<section class="sm-section sm-nmbio" aria-labelledby="sm-nm-bio">
			<div class="sm-wrap sm-nmbio__inner">

				<?php if ( $bsrc ) : ?>
					<figure class="sm-nmbio__media sm-reveal">
						<img src="<?php echo esc_url( $bsrc ); ?>" alt="<?php echo esc_attr( $c['name'] ); ?>"
						     width="900" height="900" loading="lazy" decoding="async">
					</figure>
				<?php endif; ?>

				<div class="sm-nmbio__body sm-reveal">
					<?php if ( ! empty( $bio['title'] ) ) : ?>
						<h2 id="sm-nm-bio" class="sm-nmbio__title"><?php echo esc_html( $bio['title'] ); ?></h2>
					<?php endif; ?>
					<?php foreach ( $bio['text'] as $t ) : ?>
						<p class="sm-nmbio__text"><?php echo esc_html( $t ); ?></p>
					<?php endforeach; ?>
				</div>

			</div>
		</section>
	<?php endif; ?>

	<?php /* ====================== Résumé blocks ======================= */ ?>
	<?php if ( ! empty( $c['blocks'] ) ) : ?>
		<section class="sm-section sm-nmblocks" aria-label="Career record">
			<div class="sm-wrap">
				<?php foreach ( $c['blocks'] as $bi => $block ) : ?>
					<?php if ( empty( $block['items'] ) ) { continue; } ?>
					<div class="sm-nmblock sm-nmblock--<?php echo esc_attr( $block['key'] ); ?>">

						<h2 class="sm-nmblock__title sm-reveal">
							<span class="sm-nmblock__no" aria-hidden="true"><?php echo esc_html( sprintf( '%02d', $bi + 1 ) ); ?></span>
							<?php echo esc_html( $block['title'] ); ?>
						</h2>

						<ul class="sm-nmblock__list">
							<?php foreach ( $block['items'] as $item ) : ?>
								<li class="sm-nmitem sm-reveal">
									<?php if ( ! empty( $item['label'] ) ) : ?>
										<h3 class="sm-nmitem__label"><?php echo esc_html( $item['label'] ); ?></h3>
									<?php endif; ?>
									<p class="sm-nmitem__text"><?php echo esc_html( $item['text'] ); ?></p>
								</li>
							<?php endforeach; ?>
						</ul>

					</div>
				<?php endforeach; ?>
			</div>
		</section>
	<?php endif; ?>

	<?php /* ========================== Gallery ========================== */ ?>
	<?php $gal = isset( $c['gallery'] ) ? $c['gallery'] : array(); ?>
	<?php if ( ! empty( $gal['items'] ) ) : ?>
		<section class="sm-section sm-nmgal" aria-labelledby="sm-nm-gal">
			<div class="sm-wrap">
				<h2 id="sm-nm-gal" class="sm-nmgal__title sm-reveal"><?php echo esc_html( $gal['title'] ); ?></h2>
				<?php if ( ! empty( $gal['text'] ) ) : ?>
					<p class="sm-nmgal__text sm-reveal"><?php echo esc_html( $gal['text'] ); ?></p>
				<?php endif; ?>

				<ul class="sm-nmgal__grid">
					<?php foreach ( $gal['items'] as $shot ) : ?>
						<?php $src = sm_img_src( $shot['file'] ); ?>
						<?php if ( ! $src ) { continue; } ?>
						<li class="sm-nmshot sm-reveal">
							<a class="sm-nmshot__link" href="<?php echo esc_url( $src ); ?>"
							   data-sm-lightbox data-sm-caption="<?php echo esc_attr( $shot['cap'] ); ?>"
							   target="_blank" rel="noopener">
								<img src="<?php echo esc_url( $src ); ?>" alt="<?php echo esc_attr( $shot['cap'] ); ?>"
								     width="900" height="700" loading="lazy" decoding="async">
							</a>
						</li>
					<?php endforeach; ?>
				</ul>
			</div>
		</section>
	<?php endif; ?>

	<?php /* ============================ CTA ============================ */ ?>
	<?php $cta = isset( $c['cta'] ) ? $c['cta'] : array(); ?>
	<?php if ( ! empty( $cta['title'] ) ) : ?>
		<section class="sm-section sm-nmcta" aria-labelledby="sm-nm-cta">
			<div class="sm-wrap sm-nmcta__inner">
				<h2 id="sm-nm-cta" class="sm-nmcta__title"><?php echo esc_html( $cta['title'] ); ?></h2>
				<?php if ( ! empty( $cta['text'] ) ) : ?>
					<p class="sm-nmcta__text"><?php echo esc_html( $cta['text'] ); ?></p>
				<?php endif; ?>
				<?php if ( ! empty( $cta['label'] ) ) : ?>
					<a class="sm-btn sm-btn--gold" href="<?php echo esc_url( home_url( $cta['link'] ) ); ?>">
						<?php echo esc_html( $cta['label'] ); ?>
					</a>
				<?php endif; ?>
			</div>
		</section>
	<?php endif; ?>

<?php endif; ?>

</main>

<?php
get_footer();
