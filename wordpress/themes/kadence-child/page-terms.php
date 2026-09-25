<?php
/**
 * Template Name: صفحه قوانین و مقررات
 *
 * نشانی: /terms/
 * متن در inc/content-legal.php کلید 'terms' است.
 *
 * ⚠️ این صفحه یکی از سه شرط اصلی «اینماد» را پوشش می‌دهد.
 *    پیش از ثبت درخواست اینماد، جاهای علامت‌خورده با [[ ]] را پر کنید.
 *
 * @package saadatmehr
 */

defined( 'ABSPATH' ) || exit;

$c = sm_page_content( 'terms' );


/**
 * یک بلوکِ حقوقی را چاپ می‌کند — متن، فهرست، زیربند و گام.
 *
 * 🔴 چرا بازنویسی شد
 *
 * نسخه‌ی قبلی فقط text و list و steps را چاپ می‌کرد و کلیدِ subs را
 * بی‌سروصدا نادیده می‌گرفت. نتیجه این شد که زیربندهای ماده ۳ اصلاً
 * دیده نمی‌شدند و ماده ۵ فقط یک عنوانِ خالی بود — با اینکه متنشان
 * درست در inc/content-legal.php نوشته شده بود.
 *
 * این نسخه بازگشتی است: هر بلوک می‌تواند خودش زیربند داشته باشد و
 * هر عمقی کار می‌کند. پس اگر روزی بندِ تازه‌ای با ساختارِ تودرتو
 * اضافه شد، دیگر چیزی گم نمی‌شود.
 *
 * @param array $block بلوک (title، text، list، subs، steps، after).
 * @param int   $depth عمق — ۰ یعنی خودِ ماده، ۱ یعنی زیربند.
 */
function sm_legal_block( $block, $depth = 0 ) {

	if ( ! is_array( $block ) ) {
		return;
	}

	if ( $depth > 0 && ! empty( $block['title'] ) ) {
		printf(
			'<h3 class="sm-legal__subtitle">%s</h3>',
			esc_html( $block['title'] )
		);
	}

	foreach ( (array) ( isset( $block['text'] ) ? $block['text'] : array() ) as $t ) {
		printf( '<p class="sm-legal__text">%s</p>', esc_html( $t ) );
	}

	if ( ! empty( $block['list'] ) ) {
		echo '<ul class="sm-ticklist">';
		foreach ( $block['list'] as $t ) {
			printf( '<li>%s</li>', esc_html( $t ) );
		}
		echo '</ul>';
	}

	if ( ! empty( $block['steps'] ) ) {
		echo '<ol class="sm-flow">';
		foreach ( $block['steps'] as $st ) {
			printf(
				'<li class="sm-flow__item"><span class="sm-flow__num" aria-hidden="true">%s</span>'
				. '<div><h3 class="sm-flow__title">%s</h3><p class="sm-flow__text">%s</p></div></li>',
				esc_html( $st['n'] ),
				esc_html( $st['t'] ),
				esc_html( $st['d'] )
			);
		}
		echo '</ol>';
	}

	if ( ! empty( $block['subs'] ) ) {
		echo '<div class="sm-legal__subs">';
		foreach ( $block['subs'] as $sub ) {
			echo '<div class="sm-legal__sub">';
			sm_legal_block( $sub, $depth + 1 );
			echo '</div>';
		}
		echo '</div>';
	}

	foreach ( (array) ( isset( $block['after'] ) ? $block['after'] : array() ) as $t ) {
		printf( '<p class="sm-legal__text sm-legal__text--note">%s</p>', esc_html( $t ) );
	}
}

get_header();
?>

<main id="main" class="sm-page sm-page--terms" role="main">

	<section class="sm-phead sm-phead--compact" aria-labelledby="sm-terms-title">
		<div class="sm-phead__bg" aria-hidden="true">
			<img src="<?php echo esc_url( sm_img( 'logo-seal.png' ) ); ?>" alt="" class="sm-phead__seal" loading="eager" decoding="async">
		</div>
		<div class="sm-wrap sm-phead__inner">
			<p class="sm-phead__eyebrow"><?php echo esc_html( $c['eyebrow'] ); ?></p>
			<h1 id="sm-terms-title" class="sm-phead__title"><?php echo esc_html( $c['title'] ); ?></h1>
			<?php
			/*
			 * {site} در متن، جای نشانیِ سایت است و به یک لینکِ واقعی
			 * تبدیل می‌شود. این‌طوری متن در فایل محتوا ساده می‌ماند و
			 * لازم نیست کسی HTML بنویسد.
			 */
			$site_url = ! empty( $c['site_url'] ) ? $c['site_url'] : home_url( '/' );
			$site_tag = sprintf(
				'<a href="%s" dir="ltr">%s</a>',
				esc_url( $site_url ),
				esc_html( ! empty( $c['site_label'] ) ? $c['site_label'] : wp_parse_url( $site_url, PHP_URL_HOST ) )
			);
			?>
			<?php foreach ( $c['lead'] as $t ) : ?>
				<p class="sm-phead__lead">
					<?php
					echo wp_kses(
						str_replace( '{site}', $site_tag, esc_html( $t ) ),
						array( 'a' => array( 'href' => array(), 'dir' => array() ) )
					);
					?>
				</p>
			<?php endforeach; ?>
			<?php if ( ! empty( $c['updated'] ) ) : ?>
				<p class="sm-phead__trust">
					<?php echo esc_html( $c['updated_label'] . ': ' . $c['updated'] ); ?>
				</p>
			<?php endif; ?>
		</div>
	</section>

	<section class="sm-section sm-prose-section">
		<div class="sm-wrap sm-form__col">

			<?php /* فهرست بندها */ ?>
			<nav class="sm-toc" aria-labelledby="sm-terms-toc">
				<h2 id="sm-terms-toc" class="sm-toc__title">بندهای این صفحه</h2>
				<ol class="sm-toc__list">
					<?php foreach ( $c['sections'] as $i => $sec ) : ?>
						<li class="sm-toc__item sm-toc__item--h2">
							<a href="#sm-t<?php echo (int) $i; ?>"><?php echo esc_html( $sec['title'] ); ?></a>
						</li>
					<?php endforeach; ?>
				</ol>
			</nav>

			<div class="sm-legal">
				<?php foreach ( $c['sections'] as $i => $sec ) : ?>
					<section class="sm-legal__sec" id="sm-t<?php echo (int) $i; ?>">
						<h2 class="sm-legal__title"><?php echo esc_html( $sec['title'] ); ?></h2>
						<?php sm_legal_block( $sec ); ?>
					</section>
				<?php endforeach; ?>
			</div>

		</div>
	</section>

	<section class="sm-section sm-councilbar" aria-labelledby="sm-terms-cta">
		<div class="sm-wrap sm-councilbar__inner">
			<h2 id="sm-terms-cta" class="sm-councilbar__title"><?php echo esc_html( $c['cta_title'] ); ?></h2>
			<p class="sm-councilbar__text"><?php echo esc_html( $c['cta_text'] ); ?></p>
			<a class="sm-btn sm-btn--ghost" href="<?php echo esc_url( home_url( $c['cta_link'] ) ); ?>">
				<?php echo esc_html( $c['cta_label'] ); ?>
			</a>
		</div>
	</section>

</main>

<?php
get_footer();
