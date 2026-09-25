<?php
/**
 * Template Name: صفحه تماس با ما
 *
 * متن‌های اختصاصی در inc/content-pages.php کلید 'contact'.
 * اطلاعات تماس از inc/content-footer.php خوانده می‌شود تا در یک
 * جا مدیریت شود و دو نسخه‌ی ناهماهنگ به وجود نیاید.
 *
 * @package saadatmehr
 */

defined( 'ABSPATH' ) || exit;

$c = sm_page_content( 'contact' );
$f = sm_footer_content();

$mobile_raw = $f['contact']['mobile_raw'] ?? '';
$mobile_raw = preg_replace( '/[^0-9+]/', '', sm_fa_to_en_digits( $mobile_raw ) );

get_header();
?>

<main id="main" class="sm-page sm-page--contact" role="main">

	<section class="sm-phead sm-phead--compact" aria-labelledby="sm-contact-title">
		<div class="sm-wrap sm-phead__inner">
			<p class="sm-phead__eyebrow"><?php echo esc_html( $c['eyebrow'] ); ?></p>
			<h1 id="sm-contact-title" class="sm-phead__title"><?php echo esc_html( $c['title'] ); ?></h1>
			<?php foreach ( $c['lead'] as $p ) : ?>
				<p class="sm-phead__lead"><?php echo esc_html( $p ); ?></p>
			<?php endforeach; ?>
		</div>
	</section>

	<section class="sm-section sm-contact">
		<div class="sm-wrap sm-contact__grid">

			<?php /* دکمه‌های تماس — روی موبایل بزرگ و قابل لمس */ ?>
			<div class="sm-contact__actions">
				<?php if ( $mobile_raw ) : ?>
					<a class="sm-contact__btn sm-contact__btn--primary" href="tel:<?php echo esc_attr( $mobile_raw ); ?>">
						<span class="sm-contact__btn-icon" aria-hidden="true"><?php sm_footer_icon( 'phone' ); ?></span>
						<span>
							<span class="sm-contact__btn-label">تماس با آکادمی</span>
							<span class="sm-contact__btn-value"><?php echo esc_html( $f['contact']['mobile'] ?? '' ); ?></span>
						</span>
					</a>
				<?php endif; ?>

				<?php if ( ! empty( $f['social']['whatsapp'] ) ) : ?>
					<a class="sm-contact__btn" href="<?php echo esc_url( $f['social']['whatsapp'] ); ?>" target="_blank" rel="noopener noreferrer">
						<span class="sm-contact__btn-icon" aria-hidden="true"><?php sm_footer_icon( 'whatsapp' ); ?></span>
						<span>
							<span class="sm-contact__btn-label">ارتباط در واتساپ</span>
							<span class="sm-contact__btn-value">پاسخ‌گویی در ساعات کاری</span>
						</span>
					</a>
				<?php endif; ?>

				<?php if ( ! empty( $f['contact']['email'] ) ) : ?>
					<a class="sm-contact__btn" href="mailto:<?php echo esc_attr( $f['contact']['email'] ); ?>">
						<span class="sm-contact__btn-icon" aria-hidden="true"><?php sm_footer_icon( 'mail' ); ?></span>
						<span>
							<span class="sm-contact__btn-label">ارسال ایمیل</span>
							<span class="sm-contact__btn-value sm-latin"><?php echo esc_html( $f['contact']['email'] ); ?></span>
						</span>
					</a>
				<?php endif; ?>
			</div>

			<?php /* اطلاعات مکان و ساعات */ ?>
			<aside class="sm-contact__info">
				<h2 class="sm-block__title">اطلاعات مراجعه</h2>
				<ul class="sm-foot__contact sm-contact__list">
					<?php
					sm_contact_row( 'pin', $f['contact']['address'] ?? '', '', $f['contact']['address_note'] ?? '' );
					sm_contact_row( 'pin', ! empty( $f['contact']['postal'] ) ? 'کد پستی: ' . $f['contact']['postal'] : '', '' );
					$land = preg_replace( '/[^0-9+]/', '', sm_fa_to_en_digits( $f['contact']['phone'] ?? '' ) );
					sm_contact_row( 'phone', $f['contact']['phone'] ?? '', $land ? 'tel:' . $land : '', 'تلفن ثابت' );
					sm_contact_row( 'clock', $f['contact']['hours'] ?? '', '', $f['contact']['hours_note'] ?? '' );
					?>
				</ul>
			</aside>

		</div>
	</section>

	<section class="sm-section sm-prose-section">
		<div class="sm-wrap sm-measure">
			<div class="sm-callout">
				<h2 class="sm-block__title"><?php echo esc_html( $c['faq_title'] ); ?></h2>
				<p class="sm-block__text"><?php echo esc_html( $c['faq_text'] ); ?></p>
				<a class="sm-btn sm-btn--outline" href="<?php echo esc_url( home_url( $c['faq_link'] ) ); ?>"><?php echo esc_html( $c['faq_label'] ); ?></a>
			</div>
			<p class="sm-disclaimer"><?php echo esc_html( $c['disclaimer'] ); ?></p>
		</div>
	</section>

	<section class="sm-closing">
		<div class="sm-wrap sm-closing__inner">
			<p class="sm-closing__text"><?php echo esc_html( $c['after_cta'] ); ?></p>
			<a class="sm-btn sm-btn--gold" href="<?php echo esc_url( home_url( $c['cta_link'] ) ); ?>"><?php echo esc_html( $c['cta_text'] ); ?></a>
		</div>
	</section>

</main>

<?php
get_footer();
