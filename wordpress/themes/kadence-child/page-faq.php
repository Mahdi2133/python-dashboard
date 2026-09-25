<?php
/**
 * Template Name: صفحه سؤالات متداول
 *
 * متن‌ها در inc/content-pages.php کلید 'faq' هستند.
 * اسکیمای FAQPage گوگل به‌صورت خودکار از همین پرسش‌ها ساخته می‌شود.
 *
 * @package saadatmehr
 */

defined( 'ABSPATH' ) || exit;

$c = sm_page_content( 'faq' );

get_header();
?>

<main id="main" class="sm-page sm-page--faq" role="main">

	<section class="sm-phead sm-phead--compact" aria-labelledby="sm-faq-title">
		<div class="sm-wrap sm-phead__inner">
			<p class="sm-phead__eyebrow"><?php echo esc_html( $c['eyebrow'] ); ?></p>
			<h1 id="sm-faq-title" class="sm-phead__title"><?php echo esc_html( $c['title'] ); ?></h1>
			<p class="sm-phead__lead"><?php echo esc_html( $c['lead'] ); ?></p>
		</div>
	</section>

	<section class="sm-section sm-faq">
		<div class="sm-wrap sm-measure">
			<?php foreach ( $c['items'] as $i => $item ) : ?>
				<details class="sm-faq__item"<?php echo 0 === $i ? ' open' : ''; ?>>
					<summary class="sm-faq__q">
						<span class="sm-faq__num" aria-hidden="true"><?php echo esc_html( sm_fa_digits( $i + 1 ) ); ?></span>
						<span class="sm-faq__q-text"><?php echo esc_html( $item['q'] ); ?></span>
						<span class="sm-faq__chevron" aria-hidden="true"></span>
					</summary>
					<div class="sm-faq__a">
						<?php foreach ( (array) $item['a'] as $a ) : ?>
							<p><?php echo esc_html( $a ); ?></p>
						<?php endforeach; ?>
					</div>
				</details>
			<?php endforeach; ?>
		</div>
	</section>

	<section class="sm-closing">
		<div class="sm-wrap sm-closing__inner">
			<h2 class="sm-closing__title"><?php echo esc_html( $c['cta_title'] ); ?></h2>
			<p class="sm-closing__text"><?php echo esc_html( $c['cta_text'] ); ?></p>
			<a class="sm-btn sm-btn--gold" href="<?php echo esc_url( home_url( $c['cta_link'] ) ); ?>"><?php echo esc_html( $c['cta_label'] ); ?></a>
		</div>
	</section>

</main>

<?php
get_footer();
