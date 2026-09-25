<?php
/**
 * قالب آرشیو مقالات
 *
 * همین فایل برای صفحه‌ی «مقالات»، آرشیو دسته‌ها، آرشیو تاریخ و
 * نتایج جست‌وجو استفاده می‌شود.
 *
 * @package saadatmehr
 */

defined( 'ABSPATH' ) || exit;

$b = (array) sm_blog_content( 'blog' );

if ( is_category() ) {
	$title = single_cat_title( '', false );
	$lead  = wp_strip_all_tags( category_description() );
} elseif ( is_search() ) {
	/* translators: %s: عبارت جست‌وجو */
	$title = sprintf( 'نتایج جست‌وجو برای «%s»', get_search_query() );
	$lead  = '';
} elseif ( is_archive() ) {
	$title = wp_strip_all_tags( get_the_archive_title() );
	$lead  = wp_strip_all_tags( get_the_archive_description() );
} else {
	$title = $b['title'];
	$lead  = $b['lead'];
}

get_header();
?>

<main id="main" class="sm-page sm-page--blog" role="main">

	<section class="sm-phead sm-phead--compact" aria-labelledby="sm-blog-title">
		<div class="sm-phead__bg" aria-hidden="true">
			<img src="<?php echo esc_url( sm_img( 'logo-seal.png' ) ); ?>" alt="" class="sm-phead__seal" loading="eager" decoding="async">
		</div>
		<div class="sm-wrap sm-phead__inner">
			<p class="sm-phead__eyebrow"><?php echo esc_html( $b['eyebrow'] ); ?></p>
			<h1 id="sm-blog-title" class="sm-phead__title"><?php echo esc_html( $title ); ?></h1>
			<?php if ( $lead ) : ?>
				<p class="sm-phead__lead"><?php echo esc_html( $lead ); ?></p>
			<?php endif; ?>
		</div>
	</section>

	<section class="sm-section sm-articles" aria-label="فهرست مقالات">
		<div class="sm-wrap">

			<?php if ( ! is_home() && ! is_front_page() ) : ?>
				<div class="sm-blog__crumbs"><?php sm_render_breadcrumbs(); ?></div>
			<?php endif; ?>

			<?php if ( have_posts() ) : ?>

				<ul class="sm-articles__grid">
					<?php
					while ( have_posts() ) :
						the_post();
						sm_article_card();
					endwhile;
					?>
				</ul>

				<?php
				the_posts_pagination(
					array(
						'class'              => 'sm-pagination',
						'mid_size'           => 1,
						'prev_text'          => 'قبلی',
						'next_text'          => 'بعدی',
						'screen_reader_text' => 'صفحه‌بندی مقالات',
					)
				);
				?>

			<?php else : ?>
				<p class="sm-empty"><?php echo esc_html( $b['empty_text'] ); ?></p>
			<?php endif; ?>

		</div>
	</section>

</main>

<?php
get_footer();
