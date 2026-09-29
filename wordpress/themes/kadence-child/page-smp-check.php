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
			<?php if ( ! empty( $c['en'] ) ) : ?>
				<p class="sm-phead__en" dir="ltr"><?php echo esc_html( $c['en'] ); ?></p>
			<?php endif; ?>
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
							<?php if ( ! empty( $g['en'] ) ) : ?>
								<span class="sm-quiz__gen" dir="ltr"><?php echo esc_html( $g['en'] ); ?></span>
							<?php endif; ?>
						</legend>
						<p class="sm-quiz__gintro"><?php echo esc_html( $g['intro'] ); ?></p>

						<?php foreach ( $g['items'] as $item ) : ?>
							<?php ++$n; ?>
							<fieldset class="sm-quiz__q" data-axis="<?php echo esc_attr( $item['axis'] ); ?>" data-no="<?php echo (int) $n; ?>">
								<legend class="sm-quiz__qtext">
									<span class="sm-quiz__qno" aria-hidden="true"><?php echo esc_html( sm_fa_digits( $n ) ); ?></span>
									<?php echo esc_html( $item['q'] ); ?>
								</legend>
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

			<?php /* ---------- نتیجه — با جاوااسکریپت پر می‌شود ---------- */ ?>
			<div class="sm-result" id="sm-result" hidden tabindex="-1">

				<span class="sm-result__badge" id="sm-result-badge"></span>
				<h2 class="sm-result__title" id="sm-result-title"></h2>
				<p class="sm-result__text" id="sm-result-text"></p>

				<?php /* «گام بعدی» — فقط در وضعیت قرمز متن دارد */ ?>
				<p class="sm-result__next" id="sm-result-next" hidden></p>

				<?php
				/*
				 * نوارِ اصطکاک. عدد کنارش می‌آید تا نوار به‌تنهایی تفسیر
				 * نشود؛ «۷ از ۱۰» را می‌شود فهمید، یک نوارِ رنگی را نه.
				 */
				?>
				<div class="sm-result__score">
					<div class="sm-result__meter" aria-hidden="true">
						<span class="sm-result__fill" id="sm-result-fill"></span>
					</div>
					<p class="sm-result__num" id="sm-result-num"></p>
				</div>

				<p class="sm-result__time" id="sm-result-time"></p>

				<?php /* ---------- فرمِ تماس ---------- */ ?>
				<?php $f = isset( $c['form'] ) ? $c['form'] : array(); ?>
				<?php if ( ! empty( $f['enabled'] ) ) : ?>
					<?php
					$sent = isset( $_GET['sm_audit'] ) ? sanitize_key( wp_unslash( $_GET['sm_audit'] ) ) : ''; // phpcs:ignore WordPress.Security.NonceVerification
					?>
					<div class="sm-auditform" id="sm-auditform">

						<?php if ( 'ok' === $sent ) : ?>
							<p class="sm-formok" role="status"><?php echo esc_html( $f['ok'] ); ?></p>
						<?php else : ?>

							<?php if ( 'err' === $sent ) : ?>
								<p class="sm-formerror" role="alert"><?php echo esc_html( $f['err'] ); ?></p>
							<?php endif; ?>

							<h3 class="sm-auditform__title"><?php echo esc_html( $f['title'] ); ?></h3>
							<p class="sm-auditform__text"><?php echo esc_html( $f['text'] ); ?></p>

							<form class="sm-auditform__form" method="post" action="<?php echo esc_url( home_url( add_query_arg( array() ) ) ); ?>#sm-result">
								<input type="hidden" name="sm_audit_form" value="1">
								<?php wp_nonce_field( 'sm_audit_submit', 'sm_audit_nonce' ); ?>
								<input type="hidden" name="sm_t" value="<?php echo esc_attr( time() ); ?>">

								<?php
								/*
								 * این سه فیلد را جاوااسکریپت پر می‌کند تا نتیجه‌ی
								 * محاسبه‌شده هم همراه درخواست ذخیره شود. اگر
								 * جاوااسکریپت کار نکند، فرم باز هم ارسال می‌شود
								 * و فقط این سه خانه خالی می‌مانند — یعنی تماسِ
								 * کاربر از دست نمی‌رود.
								 */
								?>
								<input type="hidden" name="sm_audit_zone"    id="sm-audit-zone"    value="">
								<input type="hidden" name="sm_audit_score"   id="sm-audit-score"   value="">
								<input type="hidden" name="sm_audit_answers" id="sm-audit-answers" value="">

								<?php /* تله‌ی ربات — برای کاربر نامرئی است */ ?>
								<p class="sm-hp" aria-hidden="true">
									<label>وب‌سایت<input type="text" name="sm_website" tabindex="-1" autocomplete="off"></label>
								</p>

								<div class="sm-auditform__grid">
									<?php foreach ( $f['fields'] as $fld ) : ?>
										<div class="sm-field">
											<label class="sm-field__label" for="sm_<?php echo esc_attr( $fld['name'] ); ?>">
												<?php echo esc_html( $fld['label'] ); ?>
												<?php if ( ! empty( $fld['req'] ) ) : ?>
													<span class="sm-req" aria-hidden="true">*</span>
												<?php endif; ?>
											</label>
											<input type="<?php echo esc_attr( $fld['type'] ); ?>"
											       id="sm_<?php echo esc_attr( $fld['name'] ); ?>"
											       name="sm_<?php echo esc_attr( $fld['name'] ); ?>"
											       <?php if ( ! empty( $fld['auto'] ) ) : ?>autocomplete="<?php echo esc_attr( $fld['auto'] ); ?>"<?php endif; ?>
											       <?php if ( ! empty( $fld['req'] ) ) : ?>required<?php endif; ?>>
											<?php if ( ! empty( $fld['hint'] ) ) : ?>
												<span class="sm-field__help"><?php echo esc_html( $fld['hint'] ); ?></span>
											<?php endif; ?>
										</div>
									<?php endforeach; ?>
								</div>

								<div class="sm-field sm-field--consent">
									<label class="sm-check">
										<input type="checkbox" name="sm_consent" value="1" required>
										<span><?php echo esc_html( $f['consent'] ); ?></span>
									</label>
								</div>

								<div class="sm-form__actions">
									<button type="submit" class="sm-btn sm-btn--gold" id="sm-audit-submit"><?php echo esc_html( $c['zones']['amber']['cta'] ); ?></button>
								</div>
							</form>

						<?php endif; ?>
					</div>
				<?php endif; ?>

				<div class="sm-hero__actions">
					<a class="sm-btn sm-btn--ghost" href="<?php echo esc_url( home_url( $c['result_link'] ) ); ?>"><?php echo esc_html( $c['result_cta'] ); ?></a>
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
				'zones'     => $c['zones'],
				'timeNotes' => isset( $c['time_notes'] ) ? $c['time_notes'] : array(),
				'cutAmber'  => isset( $c['cut_amber'] ) ? (int) $c['cut_amber'] : 3,
				'cutRed'    => isset( $c['cut_red'] ) ? (int) $c['cut_red'] : 7,
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
