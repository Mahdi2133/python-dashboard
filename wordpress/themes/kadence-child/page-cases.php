<?php
/**
 * Template Name: صفحه پرونده‌های بالینی
 *
 * نشانی: /cases/
 * متن‌ها در inc/content-cases.php کلید 'cases' هستند.
 *
 * ⚠️ اگر 'enabled' در آن فایل false باشد، این صفحه به‌جای پرونده‌ها
 *    فقط یک پیام کوتاه نشان می‌دهد. برای وقتی است که هنوز
 *    رضایت‌نامه‌ی کتبیِ مراجعان جمع نشده.
 *
 * @package saadatmehr
 */

defined( 'ABSPATH' ) || exit;

$c = sm_page_content( 'cases' );

get_header();
?>

<main id="main" class="sm-page sm-page--cases" role="main">

	<section class="sm-phead sm-phead--compact" aria-labelledby="sm-cases-title">
		<div class="sm-phead__bg" aria-hidden="true">
			<img src="<?php echo esc_url( sm_img( 'logo-seal.png' ) ); ?>" alt="" class="sm-phead__seal" loading="eager" decoding="async">
		</div>
		<div class="sm-wrap sm-phead__inner">
			<p class="sm-phead__eyebrow"><?php echo esc_html( $c['eyebrow'] ); ?></p>
			<h1 id="sm-cases-title" class="sm-phead__title"><?php echo esc_html( $c['title'] ); ?></h1>
			<?php foreach ( (array) $c['lead'] as $t ) : ?>
				<p class="sm-phead__lead"><?php echo esc_html( $t ); ?></p>
			<?php endforeach; ?>
		</div>
	</section>

	<section class="sm-section sm-prose-section">
		<div class="sm-wrap">

			<?php if ( empty( $c['enabled'] ) || empty( $c['items'] ) ) : ?>

				<p class="sm-empty">این بخش به‌زودی منتشر می‌شود.</p>

			<?php else : ?>

				<?php /* سلب مسئولیت، بالای همه‌ی پرونده‌ها */ ?>
				<?php if ( ! empty( $c['notice'] ) ) : ?>
					<p class="sm-casenotice" role="note"><?php echo esc_html( $c['notice'] ); ?></p>
				<?php endif; ?>

				<?php /* فهرستِ میان‌بر */ ?>
				<nav class="sm-caseindex" aria-label="فهرست پرونده‌ها">
					<?php foreach ( $c['items'] as $i => $case ) : ?>
						<a class="sm-caseindex__item" href="#sm-case<?php echo (int) $i; ?>">
							<span class="sm-caseindex__no"><?php echo esc_html( $case['no'] ); ?></span>
							<span class="sm-caseindex__title"><?php echo esc_html( $case['title'] ); ?></span>
						</a>
					<?php endforeach; ?>
				</nav>

				<div class="sm-cases">
					<?php foreach ( $c['items'] as $i => $case ) : ?>
						<article class="sm-case sm-reveal" id="sm-case<?php echo (int) $i; ?>">

							<header class="sm-case__head">
								<p class="sm-case__no">پرونده بالینی <?php echo esc_html( $case['no'] ); ?></p>
								<h2 class="sm-case__title"><?php echo esc_html( $case['title'] ); ?></h2>

								<dl class="sm-case__facts">
									<div>
										<dt><?php echo esc_html( $c['label_who'] ); ?></dt>
										<dd><?php echo esc_html( $case['who'] ); ?></dd>
									</div>
									<div>
										<dt><?php echo esc_html( $c['label_challenge'] ); ?></dt>
										<dd><?php echo esc_html( $case['challenge'] ); ?></dd>
									</div>
									<div>
										<dt><?php echo esc_html( $c['label_duration'] ); ?></dt>
										<dd><?php echo esc_html( $case['duration'] ); ?></dd>
									</div>
								</dl>
							</header>

							<?php
							/*
							 * کارت‌های «پیش از / پس از».
							 *
							 * عمداً نمودار نیست: از هر پرونده فقط دو عدد در
							 * دست داریم (شروع و پایان)، نه روندِ صد روز.
							 * کشیدنِ منحنی بین دو نقطه یعنی ساختنِ داده‌ای
							 * که وجود ندارد — روی یک صفحه‌ی بالینی، این
							 * کار درستی نیست.
							 */
							?>
							<?php if ( ! empty( $case['metrics'] ) ) : ?>
								<div class="sm-metrics" role="group" aria-label="<?php echo esc_attr( $c['label_metrics'] ); ?>">
									<?php foreach ( $case['metrics'] as $m ) : ?>
										<div class="sm-metric">
											<p class="sm-metric__label"><?php echo esc_html( $m['label'] ); ?></p>
											<div class="sm-metric__pair">
												<span class="sm-metric__side">
													<span class="sm-metric__cap"><?php echo esc_html( $c['metric_before'] ); ?></span>
													<span class="sm-metric__val sm-metric__val--before"><?php echo esc_html( $m['before'] ); ?></span>
												</span>
												<span class="sm-metric__arrow" aria-hidden="true">
													<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
														<path d="M19 12H5M11 18l-6-6 6-6"/>
													</svg>
												</span>
												<span class="sm-metric__side">
													<span class="sm-metric__cap"><?php echo esc_html( $c['metric_after'] ); ?></span>
													<span class="sm-metric__val sm-metric__val--after"><?php echo esc_html( $m['after'] ); ?></span>
												</span>
											</div>
											<?php if ( ! empty( $m['note'] ) ) : ?>
												<p class="sm-metric__note"><?php echo esc_html( $m['note'] ); ?></p>
											<?php endif; ?>
										</div>
									<?php endforeach; ?>
								</div>
							<?php endif; ?>

							<?php
							/*
							 * نمودارهای آماری. فقط پرونده‌هایی که بلوکِ
							 * 'viz' دارند این بخش را می‌گیرند؛ بقیه بدون
							 * تغییر می‌مانند.
							 */
							?>
							<?php if ( ! empty( $case['viz'] ) ) : ?>
								<?php sm_case_viz( $case['viz'] ); ?>
							<?php endif; ?>

							<?php foreach ( $case['sections'] as $n => $sec ) : ?>
								<section class="sm-case__sec">
									<h3 class="sm-case__sectitle">
										<span class="sm-case__secno"><?php echo esc_html( sm_fa_digits( $n + 1 ) ); ?></span>
										<?php echo esc_html( $sec['title'] ); ?>
									</h3>
									<?php foreach ( (array) ( isset( $sec['text'] ) ? $sec['text'] : array() ) as $t ) : ?>
										<p class="sm-case__text"><?php echo esc_html( $t ); ?></p>
									<?php endforeach; ?>
									<?php if ( ! empty( $sec['list'] ) ) : ?>
										<ul class="sm-ticklist">
											<?php foreach ( $sec['list'] as $t ) : ?>
												<li><?php echo esc_html( $t ); ?></li>
											<?php endforeach; ?>
										</ul>
									<?php endif; ?>
								</section>
							<?php endforeach; ?>

							<?php if ( ! empty( $case['quote'] ) ) : ?>
								<blockquote class="sm-pullquote sm-case__quote">
									<p><?php echo esc_html( $case['quote'] ); ?></p>
								</blockquote>
							<?php endif; ?>

						</article>
					<?php endforeach; ?>
				</div>

			<?php endif; ?>

		</div>
	</section>

	<section class="sm-closing" aria-labelledby="sm-cases-cta">
		<div class="sm-wrap sm-closing__inner">
			<h2 id="sm-cases-cta" class="sm-closing__title"><?php echo esc_html( $c['cta_title'] ); ?></h2>
			<p class="sm-closing__text"><?php echo esc_html( $c['cta_text'] ); ?></p>
			<a class="sm-btn sm-btn--gold" href="<?php echo esc_url( home_url( $c['cta_link'] ) ); ?>">
				<?php echo esc_html( $c['cta_label'] ); ?>
			</a>
		</div>
	</section>

</main>

<?php
get_footer();
