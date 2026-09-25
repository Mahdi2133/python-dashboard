<?php
/**
 * Template Name: صفحه خودارزیابی (smp/check)
 *
 * نشانی: /smp/check/   (این برگه باید فرزندِ «پروتکل SMP» باشد)
 * پرسش‌ها و متن‌ها در inc/content-forms.php کلید 'check' هستند.
 *
 * ⚠️ هیچ داده‌ای ذخیره یا ارسال نمی‌شود. محاسبه کاملاً داخل مرورگر
 *    کاربر انجام می‌شود و با بستن صفحه از بین می‌رود. این عمدی است:
 *    نگه‌داشتن پاسخ‌های سلامتی افراد، مسئولیت حقوقی می‌آورد و برای
 *    کاری که این صفحه می‌کند هیچ لازم نیست.
 *
 * @package saadatmehr
 */

defined( 'ABSPATH' ) || exit;

$c = sm_form_content( 'check' );

get_header();
?>

<main id="main" class="sm-page sm-page--check" role="main">

	<section class="sm-phead sm-phead--compact" aria-labelledby="sm-check-title">
		<div class="sm-phead__bg" aria-hidden="true">
			<img src="<?php echo esc_url( sm_img( 'logo-seal.png' ) ); ?>" alt="" class="sm-phead__seal" loading="eager" decoding="async">
		</div>
		<div class="sm-wrap sm-phead__inner">
			<p class="sm-phead__eyebrow"><?php echo esc_html( $c['eyebrow'] ); ?></p>
			<h1 id="sm-check-title" class="sm-phead__title"><?php echo esc_html( $c['title'] ); ?></h1>
			<?php foreach ( $c['lead'] as $t ) : ?>
				<p class="sm-phead__lead"><?php echo esc_html( $t ); ?></p>
			<?php endforeach; ?>
		</div>
	</section>

	<section class="sm-section sm-formsection">
		<div class="sm-wrap sm-form__col">

			<p class="sm-warnbox"><?php echo esc_html( $c['warning'] ); ?></p>

			<form class="sm-quiz" id="sm-quiz" novalidate>
				<?php $n = 0; ?>
				<?php foreach ( $c['groups'] as $gi => $g ) : ?>
					<fieldset class="sm-quiz__group">
						<legend class="sm-quiz__glegend">
							<span class="sm-fieldset__num"><?php echo esc_html( sm_fa_digits( $gi + 1 ) ); ?></span>
							<?php echo esc_html( $g['title'] ); ?>
						</legend>
						<p class="sm-quiz__gintro"><?php echo esc_html( $g['intro'] ); ?></p>

						<?php foreach ( $g['items'] as $item ) : ?>
							<?php ++$n; ?>
							<fieldset class="sm-quiz__q" data-axis="<?php echo esc_attr( $item['axis'] ); ?>">
								<legend class="sm-quiz__qtext"><?php echo esc_html( $item['q'] ); ?></legend>
								<div class="sm-quiz__opts">
									<?php foreach ( $item['a'] as $score => $opt ) : ?>
										<label class="sm-opt">
											<input type="radio" name="q<?php echo (int) $n; ?>" value="<?php echo (int) $score; ?>">
											<span><?php echo esc_html( $opt ); ?></span>
										</label>
									<?php endforeach; ?>
								</div>
							</fieldset>
						<?php endforeach; ?>
					</fieldset>
				<?php endforeach; ?>

				<p class="sm-quiz__count" data-total="<?php echo (int) $n; ?>" aria-live="polite"></p>

				<div class="sm-form__actions">
					<button type="submit" class="sm-btn sm-btn--gold"><?php echo esc_html( $c['submit'] ); ?></button>
					<button type="reset" class="sm-btn sm-btn--ghost"><?php echo esc_html( $c['reset'] ); ?></button>
				</div>

				<p class="sm-quiz__warn" role="alert" hidden><?php echo esc_html( $c['unanswered'] ); ?></p>
			</form>

			<?php /* نتیجه — با جاوااسکریپت پر می‌شود */ ?>
			<div class="sm-result" id="sm-result" hidden tabindex="-1">
				<span class="sm-result__badge" id="sm-result-badge"></span>
				<h2 class="sm-result__title" id="sm-result-title"></h2>
				<p class="sm-result__text" id="sm-result-text"></p>

				<div class="sm-result__meter" aria-hidden="true">
					<span class="sm-result__fill" id="sm-result-fill"></span>
				</div>

				<div class="sm-result__leak">
					<h3 class="sm-result__leaktitle" id="sm-result-leaktitle"></h3>
					<p class="sm-result__leaktext" id="sm-result-leaktext"></p>
					<p class="sm-result__book" id="sm-result-book"></p>
				</div>

				<div class="sm-hero__actions">
					<a class="sm-btn sm-btn--gold" href="<?php echo esc_url( home_url( $c['result_link'] ) ); ?>"><?php echo esc_html( $c['result_cta'] ); ?></a>
					<a class="sm-btn sm-btn--ghost" href="<?php echo esc_url( home_url( $c['result_link2'] ) ); ?>"><?php echo esc_html( $c['result_cta2'] ); ?></a>
				</div>

				<p class="sm-result__note"><?php echo esc_html( $c['result_note'] ); ?></p>
			</div>

			<?php
			/*
			 * متن‌های نتیجه به‌صورت داده به جاوااسکریپت داده می‌شوند تا
			 * ویرایششان در همان فایل محتوا ممکن بماند و لازم نباشد
			 * کسی به کد جاوااسکریپت دست بزند.
			 */
			$payload = array(
				'zones' => $c['zones'],
				'leaks' => $c['leaks'],
			);
			?>
			<script type="application/json" id="sm-quiz-data">
				<?php echo wp_json_encode( $payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES ); // phpcs:ignore WordPress.Security.EscapeOutput ?>
			</script>

		</div>
	</section>

</main>

<?php
get_footer();
