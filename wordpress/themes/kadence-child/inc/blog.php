<?php
/**
 * موتور بخش مقالات
 * ---------------------------------------------------------------------------
 *
 * این فایل را دست نزنید مگر بخواهید رفتار مقالات را عوض کنید.
 * برای ویرایش متن‌ها به inc/content-blog.php بروید.
 *
 * چه کارهایی اینجا انجام می‌شود:
 *   ۱. جعبه‌ی «تنظیمات مقاله» در ویرایشگر (نویسنده + سؤالات متداول)
 *   ۲. ساخت خودکار فهرست مطالب از تیترهای داخل متن
 *   ۳. مسیر راهنما (Breadcrumbs) + اسکیمای BreadcrumbList
 *   ۴. اسکیمای Article و FAQPage در تگ head
 *   ۵. کد کوتاه [کتاب] برای گذاشتن باکس کتاب وسط مقاله
 *
 * @package saadatmehr
 */

defined( 'ABSPATH' ) || exit;


/**
 * محتوای بخش مقالات را می‌خواند و در حافظه نگه می‌دارد.
 *
 * @param string $key کلید، یا خالی برای کل آرایه.
 * @return mixed
 */
function sm_blog_content( $key = '' ) {

	static $all = null;

	if ( null === $all ) {
		$file = get_stylesheet_directory() . '/inc/content-blog.php';
		$all  = file_exists( $file ) ? require $file : array();
	}

	if ( '' === $key ) {
		return $all;
	}

	return isset( $all[ $key ] ) ? $all[ $key ] : '';
}


/* ==========================================================================
   ۱. جعبه‌ی «تنظیمات مقاله» در ویرایشگر
   ========================================================================== */

/**
 * جعبه را به ویرایشگر نوشته‌ها اضافه می‌کند.
 */
function sm_add_article_meta_box() {

	add_meta_box(
		'sm-article-options',
		'تنظیمات مقاله — آکادمی سعادت‌مهر',
		'sm_render_article_meta_box',
		'post',
		'normal',
		'high'
	);
}
add_action( 'add_meta_boxes', 'sm_add_article_meta_box' );


/**
 * محتوای جعبه را چاپ می‌کند.
 *
 * @param WP_Post $post نوشته‌ی در حال ویرایش.
 */
function sm_render_article_meta_box( $post ) {

	wp_nonce_field( 'sm_article_options', 'sm_article_nonce' );

	$authors = sm_blog_content( 'authors' );
	$current = get_post_meta( $post->ID, '_sm_author_box', true );

	if ( ! $current ) {
		$current = sm_blog_content( 'author_default' );
	}

	$faq = get_post_meta( $post->ID, '_sm_faq', true );
	?>
	<style>
		.sm-mb p { margin: .35rem 0 1rem; line-height: 1.9; }
		.sm-mb label { display: block; margin: .3rem 0; line-height: 1.9; }
		.sm-mb textarea { width: 100%; min-height: 11rem; font-family: inherit; line-height: 2; direction: rtl; }
		.sm-mb code { background: #f0f0f1; padding: 1px 4px; border-radius: 3px; }
		.sm-mb h4 { margin: 1.4rem 0 .2rem; font-size: 13px; }
	</style>

	<div class="sm-mb" dir="rtl">

		<h4>باکس «درباره‌ی نویسنده» پای این مقاله</h4>
		<p>کدام متن پای مقاله بنشیند؟</p>
		<?php foreach ( $authors as $key => $a ) : ?>
			<label>
				<input type="radio" name="sm_author_box" value="<?php echo esc_attr( $key ); ?>"
					<?php checked( $current, $key ); ?>>
				<?php echo esc_html( $a['label'] ); ?>
			</label>
		<?php endforeach; ?>
		<label>
			<input type="radio" name="sm_author_box" value="none" <?php checked( $current, 'none' ); ?>>
			هیچ‌کدام — باکس نویسنده نمایش داده نشود
		</label>

		<h4>سؤالات متداول این مقاله</h4>
		<p>
			هر سؤال را با <code>س:</code> و هر پاسخ را با <code>ج:</code> شروع کنید.
			بین هر جفت یک خط خالی بگذارید. اگر این کادر را خالی بگذارید، بخش
			سؤالات متداول اصلاً نمایش داده نمی‌شود.
		</p>
		<textarea name="sm_faq" placeholder="س: آیا این روش برای همه مناسب است؟&#10;ج: خیر. هر برنامه پس از بررسی شرایط فردی تنظیم می‌شود.&#10;&#10;س: چقدر طول می‌کشد؟&#10;ج: مسیر پایه ۱۰۰ روز است."><?php echo esc_textarea( $faq ); ?></textarea>
		<p>
			این سؤال‌ها هم پای مقاله نمایش داده می‌شوند و هم به‌صورت خودکار
			به‌شکل کد <code>FAQPage</code> برای گوگل در تگ <code>head</code> چاپ می‌شوند.
		</p>

		<h4>باکس کتاب وسط مقاله</h4>
		<p>
			باکس معرفی کتاب خودبه‌خود پای هر مقاله می‌آید. اگر وسط مقاله هم
			می‌خواهید، کافی است در همان‌جای متن یک بلوک «کد کوتاه» بسازید و
			داخلش بنویسید: <code>[کتاب]</code>
		</p>

	</div>
	<?php
}


/**
 * تنظیمات جعبه را ذخیره می‌کند.
 *
 * @param int $post_id شناسه‌ی نوشته.
 */
function sm_save_article_meta( $post_id ) {

	if ( ! isset( $_POST['sm_article_nonce'] ) ) {
		return;
	}

	$nonce = sanitize_text_field( wp_unslash( $_POST['sm_article_nonce'] ) );

	if ( ! wp_verify_nonce( $nonce, 'sm_article_options' ) ) {
		return;
	}

	if ( defined( 'DOING_AUTOSAVE' ) && DOING_AUTOSAVE ) {
		return;
	}

	if ( ! current_user_can( 'edit_post', $post_id ) ) {
		return;
	}

	if ( isset( $_POST['sm_author_box'] ) ) {
		$value   = sanitize_key( wp_unslash( $_POST['sm_author_box'] ) );
		$allowed = array_keys( (array) sm_blog_content( 'authors' ) );
		$allowed[] = 'none';

		if ( in_array( $value, $allowed, true ) ) {
			update_post_meta( $post_id, '_sm_author_box', $value );
		}
	}

	if ( isset( $_POST['sm_faq'] ) ) {
		$faq = sanitize_textarea_field( wp_unslash( $_POST['sm_faq'] ) );

		if ( '' === trim( $faq ) ) {
			delete_post_meta( $post_id, '_sm_faq' );
		} else {
			update_post_meta( $post_id, '_sm_faq', $faq );
		}
	}
}
add_action( 'save_post_post', 'sm_save_article_meta' );


/**
 * متن خام کادر سؤالات را به آرایه تبدیل می‌کند.
 *
 * قالب مورد انتظار:
 *     س: متن سؤال؟
 *     ج: متن پاسخ.
 *
 * خطوط بدون پیشوند، به پاسخِ قبلی چسبانده می‌شوند تا پاسخ‌های
 * چندخطی هم درست کار کنند.
 *
 * @param string $raw متن کادر.
 * @return array آرایه‌ای از array( 'q' => …, 'a' => … ).
 */
function sm_parse_faq( $raw ) {

	if ( ! $raw ) {
		return array();
	}

	$items   = array();
	$current = null;
	$mode    = '';

	foreach ( preg_split( '/\R/u', $raw ) as $line ) {

		$line = trim( $line );

		if ( '' === $line ) {
			continue;
		}

		// هم «س:» فارسی و هم «Q:» انگلیسی پذیرفته می‌شود.
		if ( preg_match( '/^(?:س|Q|q|سوال|سؤال)\s*[:：]\s*(.*)$/u', $line, $m ) ) {

			if ( $current && '' !== $current['q'] && '' !== $current['a'] ) {
				$items[] = $current;
			}

			$current = array( 'q' => trim( $m[1] ), 'a' => '' );
			$mode    = 'q';
			continue;
		}

		if ( preg_match( '/^(?:ج|A|a|جواب|پاسخ)\s*[:：]\s*(.*)$/u', $line, $m ) ) {

			if ( ! $current ) {
				$current = array( 'q' => '', 'a' => '' );
			}

			$current['a'] = trim( $m[1] );
			$mode         = 'a';
			continue;
		}

		// خط بدون پیشوند ⇐ ادامه‌ی بخش قبلی
		if ( $current && $mode ) {
			$current[ $mode ] = trim( $current[ $mode ] . ' ' . $line );
		}
	}

	if ( $current && '' !== $current['q'] && '' !== $current['a'] ) {
		$items[] = $current;
	}

	return $items;
}


/* ==========================================================================
   ۲. فهرست مطالب خودکار
   ========================================================================== */

/**
 * تیترهای داخل متن را شناسه‌دار می‌کند و فهرستشان را نگه می‌دارد.
 *
 * بدون شناسه (id) نمی‌شود از فهرست مطالب به تیتر پرش کرد، و ویرایشگر
 * وردپرس به‌صورت پیش‌فرض شناسه نمی‌گذارد.
 *
 * @param string $content متن مقاله.
 * @return string
 */
function sm_add_heading_ids( $content ) {

	if ( ! is_singular( 'post' ) || ! in_the_loop() || ! is_main_query() ) {
		return $content;
	}

	$used = array();

	$content = preg_replace_callback(
		'#<h([23])(\s[^>]*)?>(.*?)</h\1>#is',
		static function ( $m ) use ( &$used ) {

			$level = (int) $m[1];
			$attrs = isset( $m[2] ) ? $m[2] : '';
			$inner = $m[3];
			$text  = trim( wp_strip_all_tags( $inner ) );

			if ( '' === $text ) {
				return $m[0];
			}

			// اگر خود نویسنده id گذاشته، دست نمی‌زنیم.
			if ( preg_match( '/\sid\s*=\s*["\']([^"\']+)["\']/i', $attrs, $has ) ) {
				$id = $has[1];
			} else {
				$id = sanitize_title( $text );

				if ( '' === $id ) {
					$id = 'sm-h';
				}

				$base = $id;
				$n    = 2;
				while ( in_array( $id, $used, true ) ) {
					$id = $base . '-' . $n;
					++$n;
				}

				$attrs .= ' id="' . esc_attr( $id ) . '"';
			}

			$used[] = $id;

			sm_toc_items(
				array(
					'level' => $level,
					'id'    => $id,
					'text'  => $text,
				)
			);

			return '<h' . $level . $attrs . '>' . $inner . '</h' . $level . '>';
		},
		$content
	);

	return $content;
}
add_filter( 'the_content', 'sm_add_heading_ids', 8 );


/**
 * انبار تیترها.
 *
 * با آرگومان ⇐ یک تیتر اضافه می‌کند.
 * بی‌آرگومان   ⇐ فهرست را برمی‌گرداند.
 *
 * @param array|null $add تیتر جدید.
 * @return array
 */
function sm_toc_items( $add = null ) {

	static $items = array();

	if ( null !== $add ) {
		$items[] = $add;
	}

	return $items;
}


/**
 * فهرست مطالب را چاپ می‌کند.
 *
 * اگر مقاله کمتر از دو تیتر داشته باشد، فهرست ساخته نمی‌شود —
 * فهرستِ یک‌آیتمی فقط جای صفحه را می‌گیرد.
 */
function sm_render_toc() {

	$items = sm_toc_items();

	if ( count( $items ) < 2 ) {
		return;
	}
	?>
	<nav class="sm-toc" aria-labelledby="sm-toc-title">
		<h2 id="sm-toc-title" class="sm-toc__title"><?php echo esc_html( sm_blog_content( 'toc_title' ) ); ?></h2>
		<ol class="sm-toc__list">
			<?php foreach ( $items as $it ) : ?>
				<li class="sm-toc__item sm-toc__item--h<?php echo (int) $it['level']; ?>">
					<a href="#<?php echo esc_attr( $it['id'] ); ?>"><?php echo esc_html( $it['text'] ); ?></a>
				</li>
			<?php endforeach; ?>
		</ol>
	</nav>
	<?php
}


/* ==========================================================================
   ۳. مسیر راهنما (Breadcrumbs)
   ========================================================================== */

/**
 * فهرست پله‌های مسیر راهنما را می‌سازد.
 *
 * @return array آرایه‌ای از array( 'name' => …, 'url' => … ).
 */
function sm_breadcrumb_trail() {

	$trail = array(
		array(
			'name' => sm_blog_content( 'home_label' ),
			'url'  => home_url( '/' ),
		),
	);

	$blog_id = (int) get_option( 'page_for_posts' );

	$trail[] = array(
		'name' => sm_blog_content( 'blog_label' ),
		'url'  => $blog_id ? get_permalink( $blog_id ) : home_url( '/blog/' ),
	);

	if ( is_singular( 'post' ) ) {

		$cats = get_the_category();

		if ( ! empty( $cats ) ) {
			$trail[] = array(
				'name' => $cats[0]->name,
				'url'  => get_category_link( $cats[0]->term_id ),
			);
		}

		$trail[] = array(
			'name' => get_the_title(),
			'url'  => '',
		);

	} elseif ( is_category() ) {

		$trail[] = array(
			'name' => single_cat_title( '', false ),
			'url'  => '',
		);
	}

	return $trail;
}


/**
 * مسیر راهنما را چاپ می‌کند.
 */
function sm_render_breadcrumbs() {

	$trail = sm_breadcrumb_trail();

	if ( count( $trail ) < 2 ) {
		return;
	}
	?>
	<nav class="sm-crumbs" aria-label="مسیر صفحه">
		<ol class="sm-crumbs__list">
			<?php foreach ( $trail as $i => $step ) : ?>
				<li class="sm-crumbs__item">
					<?php if ( $step['url'] && $i < count( $trail ) - 1 ) : ?>
						<a href="<?php echo esc_url( $step['url'] ); ?>"><?php echo esc_html( $step['name'] ); ?></a>
					<?php else : ?>
						<span aria-current="page"><?php echo esc_html( $step['name'] ); ?></span>
					<?php endif; ?>
				</li>
			<?php endforeach; ?>
		</ol>
	</nav>
	<?php
}


/* ==========================================================================
   ۴. اسکیما (کد راهنما برای گوگل)
   ========================================================================== */

/**
 * اسکیمای Article، BreadcrumbList و FAQPage مقاله را در head چاپ می‌کند.
 */
function sm_print_article_schema() {

	if ( ! is_singular( 'post' ) ) {
		return;
	}

	/*
	 * اگر افزونه‌ی سئو نصب است، این بخش کنار می‌کشد.
	 *
	 * یوست خودش Article و BreadcrumbList می‌سازد. اگر ما هم بسازیم،
	 * هر نوشته دو تا از هرکدام دارد و سرچ کنسولِ گوگل آن را
	 * داده‌ی تکراری گزارش می‌کند.
	 *
	 * ⚠️ اسکیمای «سؤالات متداول» عمداً کنار نمی‌کشد — توضیحش در
	 *    functions.php کنار sm_print_faq_schema نوشته شده.
	 */
	if ( sm_seo_plugin_active() ) {
		return;
	}

	$post_id = get_queried_object_id();

	/* ---------- Article ---------- */
	$article = array(
		'@context'         => 'https://schema.org',
		'@type'            => 'Article',
		'headline'         => wp_strip_all_tags( get_the_title( $post_id ) ),
		'datePublished'    => get_the_date( 'c', $post_id ),
		'dateModified'     => get_the_modified_date( 'c', $post_id ),
		'inLanguage'       => 'fa-IR',
		'mainEntityOfPage' => array(
			'@type' => 'WebPage',
			'@id'   => get_permalink( $post_id ),
		),
		'publisher'        => array(
			'@type' => 'Organization',
			'name'  => get_bloginfo( 'name' ),
		),
	);

	$excerpt = get_the_excerpt( $post_id );

	if ( $excerpt ) {
		$article['description'] = wp_strip_all_tags( $excerpt );
	}

	$author = sm_article_author( $post_id );

	if ( $author ) {
		$article['author'] = array(
			'@type' => 'Person',
			'name'  => $author['name'],
		);
	}

	$img = sm_post_image_src( $post_id, 'full' );

	if ( $img ) {
		$article['image'] = $img;
	}

	sm_print_json_ld( $article );

	/* ---------- BreadcrumbList ---------- */
	$elements = array();
	$position = 1;

	foreach ( sm_breadcrumb_trail() as $step ) {
		$element = array(
			'@type'    => 'ListItem',
			'position' => $position,
			'name'     => wp_strip_all_tags( $step['name'] ),
		);

		if ( $step['url'] ) {
			$element['item'] = $step['url'];
		}

		$elements[] = $element;
		++$position;
	}

	sm_print_json_ld(
		array(
			'@context'        => 'https://schema.org',
			'@type'           => 'BreadcrumbList',
			'itemListElement' => $elements,
		)
	);

	/* ---------- FAQPage ---------- */
	$faq = sm_parse_faq( get_post_meta( $post_id, '_sm_faq', true ) );

	if ( $faq ) {
		sm_faq_schema(
			array_map(
				static function ( $item ) {
					return array(
						'q' => $item['q'],
						'a' => array( $item['a'] ),
					);
				},
				$faq
			)
		);
	}
}
add_action( 'wp_head', 'sm_print_article_schema', 6 );


/**
 * یک آرایه را به‌صورت JSON-LD چاپ می‌کند.
 *
 * @param array $data داده‌ی اسکیما.
 */
function sm_print_json_ld( $data ) {

	printf(
		'<script type="application/ld+json">%s</script>' . "\n",
		wp_json_encode( $data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES )
	);
}


/* ==========================================================================
   ۵. باکس نویسنده و باکس کتاب
   ========================================================================== */

/**
 * باکس نویسنده‌ی انتخاب‌شده برای یک مقاله را برمی‌گرداند.
 *
 * @param int $post_id شناسه‌ی نوشته.
 * @return array|null
 */
function sm_article_author( $post_id = 0 ) {

	$post_id = $post_id ? $post_id : get_the_ID();
	$authors = (array) sm_blog_content( 'authors' );
	$key     = get_post_meta( $post_id, '_sm_author_box', true );

	if ( 'none' === $key ) {
		return null;
	}

	if ( ! $key || ! isset( $authors[ $key ] ) ) {
		$key = sm_blog_content( 'author_default' );
	}

	return isset( $authors[ $key ] ) ? $authors[ $key ] : null;
}


/**
 * باکس «درباره‌ی نویسنده» را چاپ می‌کند.
 */
function sm_render_author_box() {

	$a = sm_article_author();

	if ( ! $a ) {
		return;
	}
	?>
	<aside class="sm-authorbox" aria-labelledby="sm-authorbox-title">
		<div class="sm-authorbox__media">
			<?php sm_person_avatar( $a ); ?>
		</div>
		<div class="sm-authorbox__body">
			<p id="sm-authorbox-title" class="sm-authorbox__eyebrow"><?php echo esc_html( sm_blog_content( 'author_heading' ) ); ?></p>
			<p class="sm-authorbox__name"><?php echo esc_html( $a['name'] ); ?></p>
			<p class="sm-authorbox__role"><?php echo esc_html( $a['role'] ); ?></p>
			<p class="sm-authorbox__text"><?php echo esc_html( $a['text'] ); ?></p>
		</div>
	</aside>
	<?php
}


/**
 * باکس معرفی کتاب را برمی‌گرداند.
 *
 * @return string
 */
function sm_book_box_html() {

	$b = (array) sm_blog_content( 'book_box' );

	if ( empty( $b['title'] ) ) {
		return '';
	}

	ob_start();
	?>
	<aside class="sm-bookbox">
		<span class="sm-bookbox__eyebrow"><?php echo esc_html( $b['eyebrow'] ); ?></span>
		<p class="sm-bookbox__title"><?php echo esc_html( $b['title'] ); ?></p>
		<p class="sm-bookbox__text"><?php echo esc_html( $b['text'] ); ?></p>
		<a class="sm-btn sm-btn--gold" href="<?php echo esc_url( home_url( $b['link'] ) ); ?>">
			<?php echo esc_html( $b['cta'] ); ?>
		</a>
	</aside>
	<?php
	return (string) ob_get_clean();
}


/**
 * کد کوتاه [کتاب] — برای گذاشتن باکس کتاب وسط مقاله.
 *
 * @return string
 */
function sm_book_box_shortcode() {
	return sm_book_box_html();
}
add_shortcode( 'کتاب', 'sm_book_box_shortcode' );
add_shortcode( 'sm_book', 'sm_book_box_shortcode' );


/**
 * بخش سؤالات متداول پای مقاله را چاپ می‌کند.
 */
function sm_render_article_faq() {

	$faq = sm_parse_faq( get_post_meta( get_the_ID(), '_sm_faq', true ) );

	if ( ! $faq ) {
		return;
	}
	?>
	<section class="sm-afaq" aria-labelledby="sm-afaq-title">
		<h2 id="sm-afaq-title" class="sm-afaq__title"><?php echo esc_html( sm_blog_content( 'faq_title' ) ); ?></h2>
		<div class="sm-afaq__list">
			<?php foreach ( $faq as $item ) : ?>
				<details class="sm-afaq__item">
					<summary class="sm-afaq__q"><?php echo esc_html( $item['q'] ); ?></summary>
					<p class="sm-afaq__a"><?php echo esc_html( $item['a'] ); ?></p>
				</details>
			<?php endforeach; ?>
		</div>
	</section>
	<?php
}


/**
 * زمان تقریبی مطالعه را برمی‌گرداند.
 *
 * مبنا: ۲۰۰ کلمه در دقیقه — نرخ متعارف برای متن غیرتخصصی فارسی.
 *
 * @param int $post_id شناسه‌ی نوشته.
 * @return string
 */
function sm_read_time( $post_id = 0 ) {

	$post_id = $post_id ? $post_id : get_the_ID();
	$words   = str_word_count( wp_strip_all_tags( get_post_field( 'post_content', $post_id ) ), 0, 'آابپتثجچحخدذرزژسشصضطظعغفقکگلمنوهیءأإؤئًٌٍَُِّْ۰۱۲۳۴۵۶۷۸۹' );

	// str_word_count روی فارسی دقیق نیست؛ شمارش بر پایه‌ی فاصله مطمئن‌تر است.
	$words = max( $words, count( preg_split( '/\s+/u', trim( wp_strip_all_tags( get_post_field( 'post_content', $post_id ) ) ) ) ) );

	$minutes = max( 1, (int) ceil( $words / 200 ) );

	return sm_fa_digits( $minutes ) . ' ' . sm_blog_content( 'read_time_suffix' );
}


/**
 * یک کارت مقاله در شبکه‌ها چاپ می‌کند.
 *
 * از همان نشانه‌گذاری سکشن مقالاتِ صفحه‌ی اصلی استفاده می‌کند تا
 * صفحه‌ی اصلی، آرشیو و «مقالات مرتبط» یک شکل باشند و استایلشان
 * در یک جا بماند.
 *
 * @param WP_Post|int|null $post نوشته. خالی = نوشته‌ی جاری حلقه.
 */
function sm_article_card( $post = null ) {

	$post = get_post( $post );

	if ( ! $post ) {
		return;
	}
	?>
	<li class="sm-article sm-reveal">
		<a class="sm-article__link" href="<?php echo esc_url( get_permalink( $post ) ); ?>">
			<span class="sm-article__thumb">
				<?php if ( sm_post_has_image( $post ) ) : ?>
					<?php echo sm_post_image( $post ); // phpcs:ignore WordPress.Security.EscapeOutput ?>
				<?php else : ?>
					<span class="sm-article__thumb-fallback" aria-hidden="true"></span>
				<?php endif; ?>
			</span>
			<span class="sm-article__date"><?php echo esc_html( get_the_date( '', $post ) ); ?></span>
			<h3 class="sm-article__title"><?php echo esc_html( get_the_title( $post ) ); ?></h3>
			<span class="sm-article__excerpt"><?php echo esc_html( wp_trim_words( get_the_excerpt( $post ), 22, ' …' ) ); ?></span>
		</a>
	</li>
	<?php
}


/* ==========================================================================
   ۶. سئوی پایه بدون افزونه
   --------------------------------------------------------------------------
   سایت هنوز افزونه‌ی سئو ندارد. این بخش دو چیزِ پایه را تأمین می‌کند:
   عنوان صفحه در نتایج گوگل و توضیح زیر آن.

   اگر بعداً Rank Math یا Yoast نصب کردید، این کد خودش کنار می‌رود
   (آن افزونه‌ها همین تگ‌ها را خودشان می‌سازند) — پس تداخلی پیش
   نمی‌آید و لازم نیست چیزی را حذف کنید.
   ========================================================================== */

/**
 * آیا افزونه‌ی سئو فعال است؟
 *
 * @return bool
 */
function sm_seo_plugin_active() {

	return defined( 'WPSEO_VERSION' )               // Yoast SEO
		|| defined( 'RANK_MATH_VERSION' )           // Rank Math
		|| defined( 'SEOPRESS_VERSION' )            // SEOPress
		|| defined( 'AIOSEO_VERSION' )              // All in One SEO
		|| defined( 'THE_SEO_FRAMEWORK_VERSION' );  // The SEO Framework
}


/**
 * عنوان سفارشی صفحه را (اگر در تنظیمات مقاله ثبت شده باشد) جایگزین می‌کند.
 *
 * @param array $parts اجزای عنوان.
 * @return array
 */
function sm_document_title( $parts ) {

	if ( sm_seo_plugin_active() || ! is_singular() ) {
		return $parts;
	}

	$custom = get_post_meta( get_queried_object_id(), '_sm_seo_title', true );

	if ( $custom ) {
		$parts['title'] = $custom;
	}

	return $parts;
}
add_filter( 'document_title_parts', 'sm_document_title' );


/**
 * تگ توضیحات و تگ‌های اشتراک‌گذاری را در head چاپ می‌کند.
 */
function sm_print_meta_description() {

	if ( sm_seo_plugin_active() ) {
		return;
	}

	$desc = '';

	if ( is_singular() ) {
		$id   = get_queried_object_id();
		$desc = (string) get_post_meta( $id, '_sm_seo_desc', true );

		if ( ! $desc ) {
			$desc = (string) get_the_excerpt( $id );
		}

		if ( ! $desc ) {
			$desc = wp_trim_words( wp_strip_all_tags( get_post_field( 'post_content', $id ) ), 28, '…' );
		}
	} elseif ( is_front_page() || is_home() ) {
		$home = sm_home_content();
		$desc = isset( $home['hero']['subtitle'] ) ? $home['hero']['subtitle'] : get_bloginfo( 'description' );
	} elseif ( is_category() ) {
		$desc = wp_strip_all_tags( category_description() );
	}

	$desc = trim( wp_strip_all_tags( $desc ) );

	if ( ! $desc ) {
		return;
	}

	// گوگل حدود ۱۶۰ نویسه را نشان می‌دهد؛ بلندتر از آن بریده می‌شود.
	if ( function_exists( 'mb_substr' ) && mb_strlen( $desc, 'UTF-8' ) > 165 ) {
		$desc = rtrim( mb_substr( $desc, 0, 162, 'UTF-8' ) ) . '…';
	}

	printf( '<meta name="description" content="%s">' . "\n", esc_attr( $desc ) );
	printf( '<meta property="og:description" content="%s">' . "\n", esc_attr( $desc ) );
	printf( '<meta property="og:title" content="%s">' . "\n", esc_attr( wp_get_document_title() ) );
	printf( '<meta property="og:type" content="%s">' . "\n", is_singular( 'post' ) ? 'article' : 'website' );
	printf( '<meta property="og:locale" content="%s">' . "\n", 'fa_IR' );
	printf( '<meta property="og:site_name" content="%s">' . "\n", esc_attr( get_bloginfo( 'name' ) ) );

	if ( is_singular() ) {
		printf( '<meta property="og:url" content="%s">' . "\n", esc_url( get_permalink( get_queried_object_id() ) ) );

		$og = is_singular( 'post' ) ? sm_post_image_src( get_queried_object_id(), 'large' ) : '';

		if ( ! $og && has_post_thumbnail( get_queried_object_id() ) ) {
			$src = wp_get_attachment_image_src( get_post_thumbnail_id( get_queried_object_id() ), 'large' );
			$og  = $src ? $src[0] : '';
		}

		if ( $og ) {
			printf( '<meta property="og:image" content="%s">' . "\n", esc_url( $og ) );
		}
	}

	echo '<meta name="twitter:card" content="summary_large_image">' . "\n";
}
add_action( 'wp_head', 'sm_print_meta_description', 4 );

/* ==========================================================================
   ۷. تصویر شاخص مقاله
   --------------------------------------------------------------------------
   اگر برای نوشته «تصویر شاخص» انتخاب شده باشد، همان استفاده می‌شود.
   وگرنه قالب داخل assets/images/articles/ دنبال فایلی می‌گردد که نامش
   با نامکِ نوشته یکی باشد.

   چرا این‌طور؟ چون تصاویر پنج مقاله‌ی اول از قبل داخل خود قالب هستند و
   کاربر لازم نیست یکی‌یکی آن‌ها را در کتابخانه‌ی رسانه آپلود کند و به
   هر نوشته وصل کند. هر وقت خواست تصویر بهتری بگذارد، کافی است از
   پیشخوان «تصویر شاخص» انتخاب کند — آن انتخاب همیشه اولویت دارد.
   ========================================================================== */

/**
 * نشانی تصویر نوشته را برمی‌گرداند.
 *
 * @param WP_Post|int|null $post  نوشته.
 * @param string           $size  اندازه‌ی تصویر شاخص.
 * @return string نشانی، یا رشته‌ی خالی.
 */
function sm_post_image_src( $post = null, $size = 'large' ) {

	$post = get_post( $post );

	if ( ! $post ) {
		return '';
	}

	if ( has_post_thumbnail( $post ) ) {
		$img = wp_get_attachment_image_src( get_post_thumbnail_id( $post ), $size );
		if ( $img ) {
			return $img[0];
		}
	}

	if ( empty( $post->post_name ) ) {
		return '';
	}

	return sm_img_src( 'articles/' . $post->post_name . '.webp' );
}


/**
 * آیا این نوشته تصویری دارد؟
 *
 * @param WP_Post|int|null $post نوشته.
 * @return bool
 */
function sm_post_has_image( $post = null ) {
	return '' !== sm_post_image_src( $post );
}


/**
 * تگ تصویر نوشته را چاپ‌آماده برمی‌گرداند.
 *
 * @param WP_Post|int|null $post  نوشته.
 * @param string           $size  اندازه‌ی تصویر شاخص.
 * @param bool             $eager بارگذاری فوری (برای تصویر بالای مقاله).
 * @return string
 */
function sm_post_image( $post = null, $size = 'medium_large', $eager = false ) {

	$post = get_post( $post );

	if ( ! $post ) {
		return '';
	}

	if ( has_post_thumbnail( $post ) ) {
		return get_the_post_thumbnail(
			$post,
			$size,
			array(
				'loading'  => $eager ? 'eager' : 'lazy',
				'decoding' => 'async',
				'alt'      => '',
			)
		);
	}

	$src = sm_post_image_src( $post, $size );

	if ( ! $src ) {
		return '';
	}

	return sprintf(
		'<img src="%s" alt="" decoding="async" %s>',
		esc_url( $src ),
		$eager ? 'loading="eager" fetchpriority="high"' : 'loading="lazy"'
	);
}
