<?php
/**
 * قالب یک مقاله
 *
 * ساختار طبق «چک‌لیست الزامات فنی و طراحی بخش مقالات»:
 *   مسیر راهنما · عنوان · فراداده · تصویر شاخص · فهرست مطالب ·
 *   متن با عرض ۷۰۰–۸۰۰ پیکسل · سؤالات متداول · باکس کتاب ·
 *   باکس نویسنده · سلب مسئولیت · مقالات مرتبط
 *
 * ⚠️ کلاس‌ها عمداً با پیشوند sm-post هستند، نه sm-article.
 *    sm-article از قبل برای «کارت مقاله» در شبکه‌ها استفاده می‌شود
 *    و اگر اینجا هم همان را می‌گذاشتیم، دو استایل با هم تداخل داشتند.
 *
 * @package saadatmehr
 */

defined( 'ABSPATH' ) || exit;

get_header();
?>

<main id="main" class="sm-page sm-page--post" role="main">

	<?php
	while ( have_posts() ) :
		the_post();

		/*
		 * متن را از قبل فیلتر می‌کنیم تا فیلتر sm_add_heading_ids اجرا
		 * شود و فهرست تیترها پر شود. بدون این کار، فهرست مطالب که بالای
		 * متن چاپ می‌شود هنوز خالی است.
		 */
		$body = apply_filters( 'the_content', get_the_content() );
		?>

		<article <?php post_class( 'sm-post' ); ?>>

			<header class="sm-post__head">
				<div class="sm-wrap sm-post__col">
					<?php sm_render_breadcrumbs(); ?>

					<?php
					$cats = get_the_category();
					if ( ! empty( $cats ) ) :
						?>
						<p class="sm-post__cat">
							<a href="<?php echo esc_url( get_category_link( $cats[0]->term_id ) ); ?>">
								<?php echo esc_html( $cats[0]->name ); ?>
							</a>
						</p>
					<?php endif; ?>

					<h1 class="sm-post__title"><?php the_title(); ?></h1>

					<ul class="sm-post__meta">
						<li><time datetime="<?php echo esc_attr( get_the_date( 'c' ) ); ?>"><?php echo esc_html( get_the_date() ); ?></time></li>
						<li><?php echo esc_html( sm_read_time() ); ?></li>
						<?php
						$author = sm_article_author();
						if ( $author ) :
							?>
							<li><?php echo esc_html( $author['name'] ); ?></li>
						<?php endif; ?>
					</ul>
				</div>
			</header>

			<?php if ( sm_post_has_image() ) : ?>
				<figure class="sm-post__hero">
					<div class="sm-wrap sm-post__col">
						<?php echo sm_post_image( null, 'large', true ); // phpcs:ignore WordPress.Security.EscapeOutput ?>
					</div>
				</figure>
			<?php endif; ?>

			<div class="sm-wrap sm-post__col">

				<?php sm_render_toc(); ?>

				<div class="sm-post__body">
					<?php echo $body; // phpcs:ignore WordPress.Security.EscapeOutput -- از فیلتر the_content گذشته است. ?>
				</div>

				<?php sm_render_article_faq(); ?>

				<?php echo sm_book_box_html(); // phpcs:ignore WordPress.Security.EscapeOutput -- خروجی داخلی و escape‌شده است. ?>

				<?php sm_render_author_box(); ?>

				<p class="sm-post__disclaimer"><?php echo esc_html( sm_blog_content( 'disclaimer' ) ); ?></p>

			</div>

		</article>

		<?php
		/* ---------- مقالات مرتبط ---------- */
		$related_args = array(
			'post_type'           => 'post',
			'posts_per_page'      => 3,
			'post__not_in'        => array( get_the_ID() ),
			'ignore_sticky_posts' => true,
			'no_found_rows'       => true,
		);

		$cats = get_the_category();

		if ( ! empty( $cats ) ) {
			$related_args['cat'] = $cats[0]->term_id;
		}

		$related = new WP_Query( $related_args );

		if ( $related->have_posts() ) :
			?>
			<section class="sm-section sm-articles" aria-labelledby="sm-related-title">
				<div class="sm-wrap">
					<header class="sm-section__head sm-section__head--center">
						<h2 id="sm-related-title" class="sm-section__title">مقالات مرتبط</h2>
					</header>
					<ul class="sm-articles__grid">
						<?php
						while ( $related->have_posts() ) :
							$related->the_post();
							sm_article_card();
						endwhile;
						?>
					</ul>
				</div>
			</section>
			<?php
		endif;

		wp_reset_postdata();

	endwhile;
	?>

</main>

<?php
get_footer();
