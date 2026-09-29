<?php
/**
 * Template Name: صفحه رسانه‌ها
 *
 * نشانی: /media/
 *
 * چهار بخش: ویدئوها · خبرگزاری‌ها · بریده‌های مطبوعات · مفدا
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

	<?php
	/*
	 * سربرگ — دقیقاً همان الگوی صفحه‌ی اصلی و «درباره ما».
	 *
	 * ⚠️ قبلاً اینجا یک چیدمانِ جداگانه نوشته بودم (عکس داخلِ ستون،
	 *    با مُهرِ لوگو در پس‌زمینه). دو مشکل داشت: هم با دو صفحه‌ی
	 *    دیگر یکدست نبود، هم قاعده‌ی CSSاش روی عکسِ سربرگِ «درباره
	 *    ما» هم می‌افتاد و آن را مربعی می‌کرد. حالا هر سه صفحه از
	 *    یک الگو استفاده می‌کنند و چنین چیزی دیگر ممکن نیست.
	 */
	$head_src  = ! empty( $c['image'] ) ? sm_img_src( $c['image'] ) : '';
	$head_side = ( 'left' === ( $c['text_side'] ?? 'right' ) ) ? 'left' : 'right';
	$head_mode = ( 'overlay' === ( $c['layout'] ?? 'split' ) ) ? 'overlay' : 'split';

	$head_class = 'sm-phead';

	if ( $head_src ) {
		$head_class .= ' sm-phead--photo sm-phead--' . $head_mode . ' sm-phead--text-' . $head_side;
	} else {
		$head_class .= ' sm-phead--compact';
	}

	/*
	 * نقطه‌ی کانونیِ عکس. وقتی عکس بریده می‌شود، این می‌گوید کدام
	 * قسمتش حتماً بماند. خالی باشد یعنی وسط. نمونه: '64% center'
	 */
	$head_focus = isset( $c['image_focus'] ) ? trim( (string) $c['image_focus'] ) : '';
	?>
	<section class="<?php echo esc_attr( trim( $head_class ) ); ?>"
		<?php if ( $head_focus ) : ?>style="--sm-phead-focus: <?php echo esc_attr( $head_focus ); ?>"<?php endif; ?> aria-labelledby="sm-media-title">
		<?php if ( $head_src ) : ?>
			<div class="sm-phead__bg">
				<img src="<?php echo esc_url( $head_src ); ?>"
				     alt="<?php echo esc_attr( $c['image_alt'] ?? '' ); ?>"
				     class="sm-phead__photo" loading="eager" fetchpriority="high" decoding="async">
			</div>
		<?php endif; ?>
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

				<?php foreach ( $c['groups'] as $g ) : ?>
					<?php
					$items = isset( $buckets[ $g['key'] ] ) ? $buckets[ $g['key'] ] : array();
					// «ویدئو» کارتِ بزرگ با تصویر می‌گیرد، بقیه کارتِ هم‌اندازه‌ی لوگودار.
					$is_video = ( 'video' === $g['key'] );
					?>
					<section class="sm-mediagroup sm-mediagroup--<?php echo esc_attr( $g['key'] ); ?>" aria-labelledby="sm-mg-<?php echo esc_attr( $g['key'] ); ?>">

						<h2 class="sm-mediagroup__title" id="sm-mg-<?php echo esc_attr( $g['key'] ); ?>">
							<?php echo esc_html( $g['title'] ); ?>
							<?php if ( $items ) : ?>
								<span class="sm-mediagroup__count"><?php echo esc_html( sm_fa_digits( count( $items ) ) ); ?></span>
							<?php endif; ?>
						</h2>

						<?php if ( empty( $items ) ) : ?>
							<p class="sm-mediagroup__empty"><?php echo esc_html( $g['empty'] ); ?></p>

						<?php elseif ( $is_video ) : ?>
							<ul class="sm-videos">
								<?php foreach ( $items as $m ) : ?>
									<?php
									$has_url = ! empty( $m['url'] );
									$shot    = ! empty( $m['image'] ) ? sm_img_src( 'media/' . $m['image'] ) : '';
									$tag     = $has_url ? 'a' : 'div';
									?>
									<li class="sm-video sm-reveal">
										<<?php echo $tag; // phpcs:ignore ?> class="sm-video__card<?php echo $has_url ? '' : ' is-soon'; ?>"
											<?php if ( $has_url ) : ?>
												href="<?php echo esc_url( $m['url'] ); ?>" target="_blank" rel="noopener noreferrer"
											<?php endif; ?>>

											<span class="sm-video__thumb">
												<?php if ( $shot ) : ?>
													<img src="<?php echo esc_url( $shot ); ?>"
													     alt="<?php echo esc_attr( $m['outlet'] ); ?>"
													     loading="lazy" decoding="async">
												<?php endif; ?>
												<?php if ( $has_url ) : ?>
													<span class="sm-video__play" aria-hidden="true">
														<svg viewBox="0 0 24 24" width="26" height="26" fill="currentColor"><path d="M8 5.5v13l11-6.5z"/></svg>
													</span>
												<?php endif; ?>
											</span>

											<span class="sm-video__body">
												<span class="sm-video__outlet"><?php echo esc_html( $m['outlet'] ); ?></span>
												<span class="sm-video__title"><?php echo esc_html( $m['title'] ); ?></span>
												<?php if ( $has_url ) : ?>
													<span class="sm-video__cta">
														تماشای ویدئو
														<span class="screen-reader-text">در <?php echo esc_html( $m['outlet'] ); ?> — در پنجره جدید باز می‌شود</span>
													</span>
												<?php else : ?>
													<span class="sm-video__cta sm-video__cta--soon">لینک به‌زودی</span>
												<?php endif; ?>
											</span>

										</<?php echo $tag; // phpcs:ignore ?>>
									</li>
								<?php endforeach; ?>
							</ul>

						<?php else : ?>
							<ul class="sm-outlets">
								<?php foreach ( $items as $m ) : ?>
									<?php $has_url = ! empty( $m['url'] ); ?>
									<?php $tag = $has_url ? 'a' : 'div'; ?>
									<li class="sm-outlet sm-reveal">
										<<?php echo $tag; // phpcs:ignore ?> class="sm-outlet__card<?php echo $has_url ? '' : ' is-soon'; ?>"
											<?php if ( $has_url ) : ?>
												href="<?php echo esc_url( $m['url'] ); ?>" target="_blank" rel="noopener noreferrer"
											<?php endif; ?>>

											<?php
											/*
											 * نوارِ لوگو ارتفاعِ ثابت دارد و لوگو با
											 * object-fit: contain داخلش می‌نشیند. به این
											 * ترتیب لوگوی مربعی و لوگوی کشیده هر دو یک
											 * اندازه دیده می‌شوند و کارت‌ها هم‌قد می‌مانند.
											 */
											?>
											<span class="sm-outlet__logo"><?php sm_media_logo( $m ); ?></span>
											<span class="sm-outlet__title"><?php echo esc_html( $m['title'] ); ?></span>
											<span class="sm-outlet__foot">
												<span class="sm-outlet__name"><?php echo esc_html( $m['outlet'] ); ?></span>
												<?php if ( $has_url ) : ?>
													<span class="sm-outlet__cta" aria-hidden="true">مشاهده مطلب</span>
													<span class="screen-reader-text">مشاهده مطلب در <?php echo esc_html( $m['outlet'] ); ?> — در پنجره جدید باز می‌شود</span>
												<?php endif; ?>
											</span>

										</<?php echo $tag; // phpcs:ignore ?>>
									</li>
								<?php endforeach; ?>
							</ul>
						<?php endif; ?>

					</section>
				<?php endforeach; ?>

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

					<?php $mlogo = ! empty( $min['logo'] ) ? sm_img_src( 'media/' . $min['logo'] ) : ''; ?>
					<div class="sm-ministry__head">
						<?php if ( $mlogo ) : ?>
							<span class="sm-ministry__logo">
								<img src="<?php echo esc_url( $mlogo ); ?>" alt="" loading="lazy" decoding="async">
							</span>
						<?php endif; ?>
						<h2 id="sm-ministry-title" class="sm-ministry__title"><?php echo esc_html( $min['title'] ); ?></h2>
					</div>

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
