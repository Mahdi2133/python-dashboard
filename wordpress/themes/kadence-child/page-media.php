<?php
/**
 * Template Name: صفحه رسانه‌ها
 *
 * نشانی: /media/
 *
 * سه ستون: رادیو و تلویزیون · خبرگزاری‌ها · روزنامه‌ها
 *
 * متن‌های خودِ صفحه در inc/content-pages.php کلید 'media' هستند.
 * فهرست مصاحبه‌ها از inc/content-home.php بخش proof → media خوانده
 * می‌شود تا یک لینک را مجبور نباشید در دو فایل ویرایش کنید.
 *
 * @package saadatmehr
 */

defined( 'ABSPATH' ) || exit;

$c    = sm_page_content( 'media' );
$home = sm_home_content();
$list = isset( $home['proof']['media'] ) ? $home['proof']['media'] : array();
$min  = isset( $c['ministry'] ) ? $c['ministry'] : array();

// هر مورد را زیر ستون خودش می‌گذاریم
$buckets = array();

foreach ( $c['groups'] as $g ) {
	$buckets[ $g['key'] ] = array();
}

foreach ( $list as $m ) {
	$key = isset( $m['group'] ) ? $m['group'] : 'agency';

	if ( ! isset( $buckets[ $key ] ) ) {
		$buckets[ $key ] = array();
	}

	$buckets[ $key ][] = $m;
}

get_header();
?>

<main id="main" class="sm-page sm-page--media" role="main">

	<section class="sm-phead sm-phead--compact" aria-labelledby="sm-media-title">
		<div class="sm-phead__bg" aria-hidden="true">
			<img src="<?php echo esc_url( sm_img( 'logo-seal.png' ) ); ?>" alt="" class="sm-phead__seal" loading="eager" decoding="async">
		</div>
		<div class="sm-wrap sm-phead__inner">
			<p class="sm-phead__eyebrow"><?php echo esc_html( $c['eyebrow'] ); ?></p>
			<h1 id="sm-media-title" class="sm-phead__title"><?php echo esc_html( $c['title'] ); ?></h1>
			<?php foreach ( $c['lead'] as $t ) : ?>
				<p class="sm-phead__lead"><?php echo esc_html( $t ); ?></p>
			<?php endforeach; ?>
		</div>
	</section>

	<section class="sm-section sm-prose-section" aria-label="فهرست مصاحبه‌ها">
		<div class="sm-wrap">

			<?php if ( empty( $list ) ) : ?>
				<p class="sm-empty"><?php echo esc_html( $c['empty_text'] ); ?></p>
			<?php else : ?>

				<div class="sm-mediacols">
					<?php foreach ( $c['groups'] as $g ) : ?>
						<?php $items = isset( $buckets[ $g['key'] ] ) ? $buckets[ $g['key'] ] : array(); ?>
						<section class="sm-mediacol sm-mediacol--<?php echo esc_attr( $g['key'] ); ?>" aria-labelledby="sm-mg-<?php echo esc_attr( $g['key'] ); ?>">

							<h2 class="sm-mediacol__title" id="sm-mg-<?php echo esc_attr( $g['key'] ); ?>">
								<?php echo esc_html( $g['title'] ); ?>
								<?php if ( $items ) : ?>
									<span class="sm-mediacol__count"><?php echo esc_html( sm_fa_digits( count( $items ) ) ); ?></span>
								<?php endif; ?>
							</h2>

							<?php if ( empty( $items ) ) : ?>
								<p class="sm-mediacol__empty"><?php echo esc_html( $g['empty'] ); ?></p>
							<?php else : ?>
								<ul class="sm-mediacol__list">
									<?php foreach ( $items as $m ) : ?>
										<?php
										/*
										 * موردی که هنوز لینک ندارد (مثل برنامه‌های
										 * رادیویی تا وقتی در آپارات آپلود نشده‌اند)
										 * به‌صورت کارتِ ساده و غیرقابلِ کلیک می‌آید،
										 * نه لینکِ مرده. لینکِ مرده هم کاربر را
										 * سرگردان می‌کند هم برای گوگل بد است.
										 */
										$has_url = ! empty( $m['url'] );
										$shot    = ! empty( $m['image'] ) ? sm_img_src( 'media/' . $m['image'] ) : '';
										$tag     = $has_url ? 'a' : 'div';
										?>
										<li class="sm-media__item sm-reveal">
											<<?php echo $tag; // phpcs:ignore ?> class="sm-media__card<?php echo $shot ? ' sm-media__card--shot' : ''; ?><?php echo $has_url ? '' : ' is-soon'; ?>"
												<?php if ( $has_url ) : ?>
													href="<?php echo esc_url( $m['url'] ); ?>" target="_blank" rel="noopener noreferrer"
												<?php endif; ?>>
												<?php if ( $shot ) : ?>
													<img class="sm-media__shot" src="<?php echo esc_url( $shot ); ?>"
													     alt="<?php echo esc_attr( $m['outlet'] ); ?>" loading="lazy" decoding="async">
												<?php else : ?>
													<span class="sm-media__logo"><?php sm_media_logo( $m ); ?></span>
												<?php endif; ?>
												<span class="sm-media__title"><?php echo esc_html( $m['title'] ); ?></span>
												<span class="sm-media__outlet"><?php echo esc_html( $m['outlet'] ); ?></span>
												<?php if ( $has_url ) : ?>
													<span class="sm-media__cta">
														مشاهده مطلب
														<span class="screen-reader-text">در <?php echo esc_html( $m['outlet'] ); ?> — در پنجره جدید باز می‌شود</span>
													</span>
												<?php else : ?>
													<span class="sm-media__cta sm-media__cta--soon">لینک به‌زودی</span>
												<?php endif; ?>
											</<?php echo $tag; // phpcs:ignore ?>>
										</li>
									<?php endforeach; ?>
								</ul>
							<?php endif; ?>

						</section>
					<?php endforeach; ?>
				</div>

			<?php endif; ?>

			<?php /* ---------- بریده‌های مطبوعاتِ چاپی ---------- */ ?>
			<?php if ( ! empty( $c['clips'] ) ) : ?>
				<section class="sm-clips" aria-labelledby="sm-clips-title">
					<h2 id="sm-clips-title" class="sm-clips__title"><?php echo esc_html( $c['clips_title'] ); ?></h2>
					<?php if ( ! empty( $c['clips_text'] ) ) : ?>
						<p class="sm-clips__text"><?php echo esc_html( $c['clips_text'] ); ?></p>
					<?php endif; ?>

					<ul class="sm-clips__grid">
						<?php foreach ( $c['clips'] as $clip ) : ?>
							<?php
							$thumb = sm_img_src( 'press/thumb/' . $clip['file'] );
							$full  = sm_img_src( 'press/' . $clip['file'] );
							if ( ! $thumb ) { continue; }
							$label = trim( $clip['paper'] . ( $clip['title'] ? ' — ' . $clip['title'] : '' ) );
							?>
							<li class="sm-clip sm-reveal">
								<?php
								/*
								 * لینکِ واقعی به تصویرِ بزرگ. اگر جاوااسکریپت
								 * نباشد یا هنوز بارگذاری نشده باشد، همین لینک
								 * تصویر را در تبِ تازه باز می‌کند. جاوااسکریپت
								 * فقط جلویش را می‌گیرد و به‌جایش لایت‌باکس
								 * را باز می‌کند.
								 */
								?>
								<a class="sm-clip__link" href="<?php echo esc_url( $full ); ?>"
								   data-sm-lightbox
								   data-sm-caption="<?php echo esc_attr( $label ); ?>"
								   target="_blank" rel="noopener">
									<img class="sm-clip__img" src="<?php echo esc_url( $thumb ); ?>"
									     alt="<?php echo esc_attr( $label ); ?>"
									     width="640" height="900" loading="lazy" decoding="async">
									<span class="sm-clip__zoom" aria-hidden="true">
										<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round">
											<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5M11 8v6M8 11h6"/>
										</svg>
									</span>
								</a>
								<p class="sm-clip__cap">
									<span class="sm-clip__paper"><?php echo esc_html( $clip['paper'] ); ?></span>
									<?php if ( $clip['title'] ) : ?>
										<span class="sm-clip__head"><?php echo esc_html( $clip['title'] ); ?></span>
									<?php endif; ?>
								</p>
							</li>
						<?php endforeach; ?>
					</ul>
				</section>
			<?php endif; ?>

			<?php /* ---------- مصاحبه‌های وزارت بهداشت ---------- */ ?>
			<?php if ( ! empty( $min['enabled'] ) ) : ?>
				<section class="sm-ministry" aria-labelledby="sm-ministry-title">
					<?php if ( ! empty( $min['eyebrow'] ) ) : ?>
						<p class="sm-eyebrow"><?php echo esc_html( $min['eyebrow'] ); ?></p>
					<?php endif; ?>

					<h2 id="sm-ministry-title" class="sm-ministry__title"><?php echo esc_html( $min['title'] ); ?></h2>

					<?php if ( ! empty( $min['text'] ) ) : ?>
						<p class="sm-ministry__text"><?php echo esc_html( $min['text'] ); ?></p>
					<?php endif; ?>

					<?php if ( empty( $min['items'] ) ) : ?>
						<p class="sm-ministry__soon"><?php echo esc_html( $min['soon'] ); ?></p>
					<?php else : ?>
						<ul class="sm-ministry__list">
							<?php foreach ( $min['items'] as $m ) : ?>
								<?php if ( empty( $m['url'] ) ) { continue; } ?>
								<li class="sm-media__item sm-reveal">
									<a class="sm-media__card" href="<?php echo esc_url( $m['url'] ); ?>" target="_blank" rel="noopener noreferrer">
										<span class="sm-media__title"><?php echo esc_html( $m['title'] ); ?></span>
										<?php if ( ! empty( $m['outlet'] ) ) : ?>
											<span class="sm-media__outlet"><?php echo esc_html( $m['outlet'] ); ?></span>
										<?php endif; ?>
										<?php if ( ! empty( $m['date'] ) ) : ?>
											<span class="sm-media__date"><?php echo esc_html( $m['date'] ); ?></span>
										<?php endif; ?>
										<span class="sm-media__cta">
											<?php echo esc_html( $min['cta'] ); ?>
											<span class="screen-reader-text">— در پنجره جدید باز می‌شود</span>
										</span>
									</a>
								</li>
							<?php endforeach; ?>
						</ul>
					<?php endif; ?>
				</section>
			<?php endif; ?>

		</div>
	</section>

	<section class="sm-section sm-councilbar" aria-labelledby="sm-press-title">
		<div class="sm-wrap sm-councilbar__inner">
			<h2 id="sm-press-title" class="sm-councilbar__title"><?php echo esc_html( $c['press_title'] ); ?></h2>
			<p class="sm-councilbar__text"><?php echo esc_html( $c['press_text'] ); ?></p>
			<a class="sm-btn sm-btn--ghost" href="<?php echo esc_url( home_url( $c['press_link'] ) ); ?>">
				<?php echo esc_html( $c['press_cta'] ); ?>
			</a>
		</div>
	</section>

</main>

<?php
get_footer();
