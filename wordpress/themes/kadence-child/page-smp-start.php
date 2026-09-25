<?php
/**
 * Template Name: صفحه درخواست ارزیابی (smp/start)
 *
 * نشانی: /smp/start/   (این برگه باید فرزندِ «پروتکل SMP» باشد)
 * متن‌ها و پرسش‌ها در inc/content-forms.php کلید 'start' هستند.
 *
 * فرم بدون جاوااسکریپت هم کار می‌کند: در آن حالت همه‌ی گام‌ها
 * پشت سر هم دیده می‌شوند و یک دکمه‌ی ارسال دارد. جاوااسکریپت فقط
 * آن‌ها را به سه گام تقسیم می‌کند.
 *
 * @package saadatmehr
 */

defined( 'ABSPATH' ) || exit;

$c = sm_form_content( 'start' );

$state = isset( $_GET['sm'] ) ? sanitize_key( wp_unslash( $_GET['sm'] ) ) : '';
$sent  = ( 'ok' === $state );
$error = ( 'err' === $state );

get_header();
?>

<main id="main" class="sm-page sm-page--form" role="main">

	<section class="sm-phead sm-phead--compact" aria-labelledby="sm-start-title">
		<div class="sm-phead__bg" aria-hidden="true">
			<img src="<?php echo esc_url( sm_img( 'logo-seal.png' ) ); ?>" alt="" class="sm-phead__seal" loading="eager" decoding="async">
		</div>
		<div class="sm-wrap sm-phead__inner">
			<p class="sm-phead__eyebrow"><?php echo esc_html( $c['eyebrow'] ); ?></p>
			<h1 id="sm-start-title" class="sm-phead__title"><?php echo esc_html( $c['title'] ); ?></h1>
			<?php foreach ( $c['lead'] as $t ) : ?>
				<p class="sm-phead__lead"><?php echo esc_html( $t ); ?></p>
			<?php endforeach; ?>
		</div>
	</section>

	<section id="sm-form" class="sm-section sm-formsection">
		<div class="sm-wrap sm-form__col">

			<?php if ( $sent ) : ?>

				<div class="sm-done" role="status">
					<span class="sm-done__mark" aria-hidden="true">
						<svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
							<circle cx="24" cy="24" r="21"/><path d="m14 25 7 7 14-15"/>
						</svg>
					</span>
					<h2 class="sm-done__title"><?php echo esc_html( $c['success_title'] ); ?></h2>
					<?php foreach ( $c['success_text'] as $t ) : ?>
						<p class="sm-done__text"><?php echo esc_html( $t ); ?></p>
					<?php endforeach; ?>
					<a class="sm-btn sm-btn--ghost" href="<?php echo esc_url( home_url( $c['success_link'] ) ); ?>">
						<?php echo esc_html( $c['success_cta'] ); ?>
					</a>
				</div>

			<?php else : ?>

				<?php if ( ! empty( $c['capacity_show'] ) ) : ?>
					<?php
					$taken = min( sm_leads_this_month(), (int) $c['capacity'] );
					?>
					<p class="sm-capacity">
						<?php echo esc_html( $c['capacity_text'] ); ?>:
						<strong><?php echo esc_html( sm_fa_digits( $taken ) . ' از ' . sm_fa_digits( (int) $c['capacity'] ) ); ?></strong>
					</p>
				<?php endif; ?>

				<?php if ( $error ) : ?>
					<p class="sm-formerror" role="alert"><?php echo esc_html( $c['error_text'] ); ?></p>
				<?php endif; ?>

				<form class="sm-form" method="post" action="<?php echo esc_url( home_url( add_query_arg( array() ) ) ); ?>" novalidate>

					<input type="hidden" name="sm_lead_form" value="1">
					<input type="hidden" name="sm_t" value="<?php echo esc_attr( time() ); ?>">
					<?php wp_nonce_field( 'sm_lead_submit', 'sm_lead_nonce' ); ?>

					<?php /* تله‌ی ربات — برای کاربر نامرئی است */ ?>
					<div class="sm-hp" aria-hidden="true">
						<label for="sm_website">این فیلد را خالی بگذارید</label>
						<input type="text" id="sm_website" name="sm_website" tabindex="-1" autocomplete="off">
					</div>

					<ol class="sm-steps" aria-hidden="true" hidden>
						<?php foreach ( $c['steps'] as $i => $step ) : ?>
							<li class="sm-steps__item<?php echo 0 === $i ? ' is-current' : ''; ?>">
								<span class="sm-steps__num"><?php echo esc_html( sm_fa_digits( $i + 1 ) ); ?></span>
								<span class="sm-steps__label"><?php echo esc_html( $step['title'] ); ?></span>
							</li>
						<?php endforeach; ?>
					</ol>

					<?php foreach ( $c['steps'] as $i => $step ) : ?>
						<fieldset class="sm-fieldset" data-step="<?php echo (int) $i; ?>">
							<legend class="sm-fieldset__legend">
								<span class="sm-fieldset__num"><?php echo esc_html( sm_fa_digits( $i + 1 ) ); ?></span>
								<?php echo esc_html( $step['title'] ); ?>
							</legend>

							<?php foreach ( $step['fields'] as $f ) : ?>
								<?php sm_form_field( $f ); ?>
							<?php endforeach; ?>
						</fieldset>
					<?php endforeach; ?>

					<div class="sm-field sm-field--consent">
						<label class="sm-check">
							<input type="checkbox" name="sm_consent" value="1" required>
							<span><?php echo esc_html( $c['consent'] ); ?></span>
						</label>
					</div>

					<div class="sm-form__actions">
						<button type="button" class="sm-btn sm-btn--ghost sm-form__prev" hidden><?php echo esc_html( $c['prev'] ); ?></button>
						<button type="button" class="sm-btn sm-btn--gold sm-form__next" hidden><?php echo esc_html( $c['next'] ); ?></button>
						<button type="submit" class="sm-btn sm-btn--gold sm-form__submit"><?php echo esc_html( $c['submit'] ); ?></button>
					</div>

					<p class="sm-form__note"><?php echo esc_html( $c['disclaimer'] ); ?></p>

				</form>

			<?php endif; ?>

		</div>
	</section>

</main>

<?php
get_footer();
