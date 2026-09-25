<?php
/**
 * Template Name: صفحه شورای علمی
 *
 * نشانی: /book/council/   (این برگه باید فرزندِ برگه‌ی «کتاب» باشد)
 * متن‌ها در inc/content-book.php کلید 'council' هستند.
 *
 * ⚠️ زبان این صفحه عمداً محتاطانه است. هیچ‌جا نوشته نشده که این
 *    افراد پروتکل SMP را تأیید کرده‌اند یا با آکادمی همکاری دارند —
 *    دقیقاً طبق راهنمای خودِ کاربر در «نحوه استفاده از نام اساتید».
 *
 * @package saadatmehr
 */

defined( 'ABSPATH' ) || exit;

$c      = sm_page_content( 'council' );
$photos = ! empty( $c['photos_enabled'] );

/**
 * یک گروه از افراد را چاپ می‌کند.
 *
 * @param array $group  آرایه‌ی گروه (eyebrow، title، note، people).
 * @param bool  $photos عکس‌ها نمایش داده شوند یا نه.
 * @param string $kind  'expert' یا 'athlete'.
 * @param string $id    شناسه‌ی عنوان برای aria.
 */
function sm_council_group( $group, $photos, $kind, $id ) {
	?>
	<section class="sm-section sm-council sm-council--<?php echo esc_attr( $kind ); ?>" aria-labelledby="<?php echo esc_attr( $id ); ?>">
		<div class="sm-wrap">
			<header class="sm-section__head sm-section__head--center">
				<p class="sm-eyebrow"><?php echo esc_html( $group['eyebrow'] ); ?></p>
				<h2 id="<?php echo esc_attr( $id ); ?>" class="sm-section__title"><?php echo esc_html( $group['title'] ); ?></h2>
				<p class="sm-council__note"><?php echo esc_html( $group['note'] ); ?></p>
			</header>

			<ul class="sm-people<?php echo $photos ? ' sm-people--photo' : ''; ?>">
				<?php foreach ( $group['people'] as $p ) : ?>
					<li class="sm-person sm-reveal">

						<?php $psrc = $photos && ! empty( $p['photo'] ) ? sm_img_src( 'people/' . $p['photo'] ) : ''; ?>
						<?php if ( $psrc ) : ?>
							<img class="sm-person__photo"
							     src="<?php echo esc_url( $psrc ); ?>"
							     alt="<?php echo esc_attr( $p['name'] ); ?>"
							     width="480" height="480" loading="lazy" decoding="async">
						<?php endif; ?>

						<div class="sm-person__body">
							<h3 class="sm-person__name"><?php echo esc_html( $p['name'] ); ?></h3>
							<p class="sm-person__en" dir="ltr"><?php echo esc_html( $p['en'] ); ?></p>
							<p class="sm-person__role"><?php echo esc_html( $p['role'] ); ?></p>

							<?php if ( ! empty( $p['org'] ) ) : ?>
								<p class="sm-person__org"><?php echo esc_html( $p['org'] ); ?></p>
							<?php endif; ?>

							<?php if ( ! empty( $p['honor'] ) ) : ?>
								<p class="sm-person__honor"><?php echo esc_html( $p['honor'] ); ?></p>
							<?php endif; ?>

							<p class="sm-person__text"><?php echo esc_html( $p['text'] ); ?></p>

							<?php if ( ! empty( $p['url'] ) ) : ?>
								<a class="sm-person__link" href="<?php echo esc_url( $p['url'] ); ?>"
								   target="_blank" rel="noopener nofollow">
									پروفایل رسمی
									<span class="screen-reader-text"><?php echo esc_html( ' — ' . $p['name'] ); ?></span>
								</a>
							<?php endif; ?>
						</div>

					</li>
				<?php endforeach; ?>
			</ul>
		</div>
	</section>
	<?php
}

get_header();
?>

<main id="main" class="sm-page sm-page--council" role="main">

	<section class="sm-phead sm-phead--compact" aria-labelledby="sm-council-title">
		<div class="sm-phead__bg" aria-hidden="true">
			<img src="<?php echo esc_url( sm_img( 'logo-seal.png' ) ); ?>" alt="" class="sm-phead__seal" loading="eager" decoding="async">
		</div>
		<div class="sm-wrap sm-phead__inner">
			<p class="sm-phead__eyebrow"><?php echo esc_html( $c['eyebrow'] ); ?></p>
			<h1 id="sm-council-title" class="sm-phead__title"><?php echo esc_html( $c['title'] ); ?></h1>
			<?php foreach ( $c['lead'] as $t ) : ?>
				<p class="sm-phead__lead"><?php echo esc_html( $t ); ?></p>
			<?php endforeach; ?>
		</div>
	</section>

	<?php
	sm_council_group( $c['experts'], $photos, 'expert', 'sm-experts-title' );
	sm_council_group( $c['athletes'], $photos, 'athlete', 'sm-athletes-title' );
	?>

	<section class="sm-closing" aria-labelledby="sm-council-closing">
		<div class="sm-wrap sm-closing__inner">
			<h2 id="sm-council-closing" class="sm-closing__title"><?php echo esc_html( $c['closing_title'] ); ?></h2>
			<p class="sm-closing__text"><?php echo esc_html( $c['closing_text'] ); ?></p>
			<a class="sm-btn sm-btn--gold" href="<?php echo esc_url( home_url( $c['closing_link'] ) ); ?>">
				<?php echo esc_html( $c['closing_cta'] ); ?>
			</a>
		</div>
	</section>

</main>

<?php
get_footer();
