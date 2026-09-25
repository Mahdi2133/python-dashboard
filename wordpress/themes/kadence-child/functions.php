<?php
/**
 * قالب فرزند آکادمی تندرستی سعادت‌مهر
 *
 * این فایل جایگزین نسخه‌ی قبلی شده است. نسخه‌ی قبلی شامل یک فایل
 * رمزنگاری‌شده‌ی ionCube و یک بارگذارِ دور زدن لایسنس بود که سایت را
 * روی PHP 7.4 قفل کرده بود. اینجا هیچ کد رمزنگاری‌شده‌ای وجود ندارد؛
 * هر خط قابل خواندن و بازبینی است.
 *
 * @package saadatmehr
 */

// جلوگیری از دسترسی مستقیم به فایل
defined( 'ABSPATH' ) || exit;

define( 'SM_CHILD_VERSION', '5.6.0' );

// توابع کمکی و رندر بخش‌های صفحه‌ی اصلی
require_once get_stylesheet_directory() . '/inc/helpers.php';

// فوتر اختصاصی — جایگزین فوتر قالب دمو
require_once get_stylesheet_directory() . '/inc/footer.php';

// موتور بخش مقالات — فهرست مطالب، مسیر راهنما، اسکیما، باکس نویسنده
require_once get_stylesheet_directory() . '/inc/blog.php';

// فرم درخواست ارزیابی، خودارزیابی و ثبت سفارش
require_once get_stylesheet_directory() . '/inc/forms.php';


/* ==========================================================================
   ۱. بارگذاری استایل‌ها و فونت
   ========================================================================== */

/**
 * استایل قالب مادر (Kadence) و سپس استایل قالب فرزند را صف می‌کند.
 *
 * ترتیب مهم است: استایل فرزند باید بعد از مادر بیاید تا بتواند
 * مقادیر آن را بازنویسی کند.
 */
function sm_enqueue_styles() {

	// اگر هندل استایل Kadence ثبت شده بود، آن را وابستگی قرار می‌دهیم.
	// این بررسی لازم است: اگر وابستگیِ ثبت‌نشده اعلام کنیم، وردپرس
	// استایل ما را اصلاً بارگذاری نمی‌کند.
	$deps = array();
	foreach ( array( 'kadence-global', 'kadence-content' ) as $handle ) {
		if ( wp_style_is( $handle, 'registered' ) || wp_style_is( $handle, 'enqueued' ) ) {
			$deps[] = $handle;
		}
	}

	$style_path = get_stylesheet_directory() . '/style.css';
	$version    = file_exists( $style_path ) ? filemtime( $style_path ) : SM_CHILD_VERSION;

	wp_enqueue_style(
		'sm-child',
		get_stylesheet_uri(),
		$deps,
		$version
	);

	// تعریف فونت وزیرمتن به‌صورت inline تا یک درخواست HTTP اضافه نشود
	wp_add_inline_style( 'sm-child', sm_font_face_css() );

	// استایل و اسکریپت صفحه‌ی اصلی.
	//
	// عمداً بدون شرط بارگذاری می‌شوند. نسخه‌ی قبلی شرط
	// is_page_template( 'page-home.php' ) داشت، ولی آن شرط فقط وقتی
	// درست است که الگو از کشوی «الگو» در ویرایشگر انتخاب شده باشد.
	// اگر وردپرس همان فایل را از راه سلسله‌مراتب قالب‌ها بردارد
	// (مثلاً برگه‌ای که نامک آن home است)، شرط false می‌شود و صفحه
	// بدون استایل بالا می‌آید — دقیقاً همان اتفاقی که افتاد.
	//
	// هزینه‌ی بارگذاری همیشگی ناچیز است: کل فایل حدود ۱۲ کیلوبایت و
	// همه‌ی کلاس‌هایش با پیشوند sm- هستند، پس روی هیچ صفحه‌ی دیگری
	// اثری ندارد.

	$home_css = get_stylesheet_directory() . '/assets/css/home.css';
	if ( file_exists( $home_css ) ) {
		wp_enqueue_style(
			'sm-home',
			get_stylesheet_directory_uri() . '/assets/css/home.css',
			array( 'sm-child' ),
			filemtime( $home_css )
		);
	}

	$pages_css = get_stylesheet_directory() . '/assets/css/pages.css';
	if ( file_exists( $pages_css ) ) {
		wp_enqueue_style(
			'sm-pages',
			get_stylesheet_directory_uri() . '/assets/css/pages.css',
			array( 'sm-home' ),
			filemtime( $pages_css )
		);
	}

	$blog_css = get_stylesheet_directory() . '/assets/css/blog.css';
	if ( file_exists( $blog_css ) ) {
		wp_enqueue_style(
			'sm-blog',
			get_stylesheet_directory_uri() . '/assets/css/blog.css',
			array( 'sm-pages' ),
			filemtime( $blog_css )
		);
	}

	$forms_css = get_stylesheet_directory() . '/assets/css/forms.css';
	if ( file_exists( $forms_css ) ) {
		wp_enqueue_style(
			'sm-forms',
			get_stylesheet_directory_uri() . '/assets/css/forms.css',
			array( 'sm-pages' ),
			filemtime( $forms_css )
		);
	}

	$home_js = get_stylesheet_directory() . '/assets/js/home.js';
	if ( file_exists( $home_js ) ) {
		wp_enqueue_script(
			'sm-home',
			get_stylesheet_directory_uri() . '/assets/js/home.js',
			array(),
			filemtime( $home_js ),
			true
		);
	}

	// اسکریپت فرم‌ها فقط جایی که فرم هست بارگذاری می‌شود.
	// برخلاف استایل‌ها، اینجا شرط امن است: اگر فایل بارگذاری نشود
	// فرم همچنان کامل کار می‌کند، فقط تک‌صفحه‌ای می‌ماند.
	$forms_js = get_stylesheet_directory() . '/assets/js/forms.js';

	if ( file_exists( $forms_js ) ) {
		wp_enqueue_script(
			'sm-forms',
			get_stylesheet_directory_uri() . '/assets/js/forms.js',
			array(),
			filemtime( $forms_js ),
			true
		);
	}
}


/**
 * اسکیمای FAQPage را فقط روی صفحه‌ی سؤالات متداول چاپ می‌کند.
 *
 * روی wp_head سوار می‌شود تا کد داخل تگ head قرار بگیرد — جایی که
 * گوگل انتظارش را دارد.
 */
function sm_print_faq_schema() {

	// هم وقتی الگو از کشوی ویرایشگر انتخاب شده باشد، هم وقتی وردپرس
	// خودش فایل را از راه سلسله‌مراتب (برگه‌ای با نامک faq) برداشته باشد.
	if ( ! is_page_template( 'page-faq.php' ) && ! is_page( 'faq' ) ) {
		return;
	}

	/*
	 * ⚠️ برخلافِ Article، این یکی حتی وقتی یوست نصب است هم چاپ
	 *    می‌شود — و عمدی است. نسخه‌ی رایگانِ یوست FAQPage نمی‌سازد
	 *    مگر با بلوکِ مخصوصِ خودش، و پرسش‌های این سایت در
	 *    inc/content-pages.php هستند نه در ویرایشگر. پس اینجا
	 *    تکراری ساخته نمی‌شود؛ چیزی ساخته می‌شود که وگرنه
	 *    وجود نداشت.
	 */

	$faq = sm_page_content( 'faq' );

	if ( ! empty( $faq['items'] ) ) {
		sm_faq_schema( $faq['items'] );
	}
}
add_action( 'wp_head', 'sm_print_faq_schema', 5 );
add_action( 'wp_enqueue_scripts', 'sm_enqueue_styles', 20 );


/**
 * قواعد ‎@font-face فونت وزیرمتن.
 *
 * فونت روی همین سرور میزبانی می‌شود، نه روی Google Fonts. دلیل:
 * سرعت بالاتر برای کاربر ایرانی و مستقل ماندن از دسترسی به سرویس خارجی.
 * وزیرمتن لایسنس آزاد SIL OFL 1.1 دارد و استفاده‌ی تجاری آن رایگان است.
 *
 * @return string
 */
function sm_font_face_css() {

	$dir  = get_stylesheet_directory_uri() . '/assets/fonts/';
	$weights = array(
		400 => 'Vazirmatn-Regular.woff2',
		500 => 'Vazirmatn-Medium.woff2',
		700 => 'Vazirmatn-Bold.woff2',
		900 => 'Vazirmatn-Black.woff2',
	);

	$css = '';
	foreach ( $weights as $weight => $file ) {
		$css .= sprintf(
			'@font-face{font-family:"Vazirmatn";src:url("%s") format("woff2");font-weight:%d;font-style:normal;font-display:swap;}',
			esc_url( $dir . $file ),
			$weight
		);
	}

	return $css;
}


/**
 * وزن‌های اصلی فونت را از قبل بارگذاری می‌کند تا متن هنگام باز شدن
 * صفحه نپرد. فقط دو وزن پرکاربرد، چون preload بیش از حد خودش کند می‌کند.
 */
function sm_preload_fonts() {

	$dir = get_stylesheet_directory_uri() . '/assets/fonts/';

	foreach ( array( 'Vazirmatn-Regular.woff2', 'Vazirmatn-Bold.woff2' ) as $file ) {
		printf(
			'<link rel="preload" href="%s" as="font" type="font/woff2" crossorigin>' . "\n",
			esc_url( $dir . $file )
		);
	}
}
add_action( 'wp_head', 'sm_preload_fonts', 1 );


/**
 * کلاس sm-js را پیش از نخستین رنگ‌آمیزی صفحه روی تگ html می‌گذارد.
 *
 * چرا درون‌خطی و چرا در head؟
 *   استایلِ «محو تا ظاهر شدن» فقط زیر کلاس sm-js فعال است، تا اگر
 *   جاوااسکریپت اجرا نشود محتوا نامرئی نماند. ولی اگر این کلاس را
 *   اسکریپت فوتر می‌گذاشت، صفحه یک‌بار دیده می‌شد، بعد ناپدید و
 *   دوباره ظاهر می‌شد — یعنی یک پرش زشت. این چند بایت در head
 *   پیش از رنگ‌آمیزی اجرا می‌شود و پرش را حذف می‌کند.
 *
 *   اگر کاربر «کاهش حرکت» را روشن کرده باشد یا مرورگرش قدیمی باشد،
 *   کلاس اصلاً گذاشته نمی‌شود و هیچ انیمیشنی در کار نیست.
 */
function sm_reveal_bootstrap() {
	echo '<script>(function(){var m=window.matchMedia;'
		. 'if(m&&m("(prefers-reduced-motion: reduce)").matches){return;}'
		. 'if(!("IntersectionObserver" in window)){return;}'
		. 'document.documentElement.className+=" sm-js";}());</script>' . "\n";
}
add_action( 'wp_head', 'sm_reveal_bootstrap', 3 );


/* ==========================================================================
   ۲. آیکون سایت (Favicon)
   ========================================================================== */

/**
 * آیکون‌های سایت را اضافه می‌کند.
 *
 * فقط زمانی اجرا می‌شود که در تنظیمات وردپرس آیکون سایت تعیین نشده باشد،
 * تا اگر بعداً از پیشخوان آیکون گذاشتید، انتخاب شما نادیده گرفته نشود.
 */
function sm_site_icons() {

	if ( has_site_icon() ) {
		return;
	}

	$dir = get_stylesheet_directory_uri() . '/assets/images/';

	printf( '<link rel="icon" href="%s" sizes="32x32">' . "\n", esc_url( $dir . 'favicon-32.png' ) );
	printf( '<link rel="apple-touch-icon" href="%s">' . "\n", esc_url( $dir . 'favicon-180.png' ) );
	printf( '<meta name="theme-color" content="%s">' . "\n", '#0C243C' );
}
add_action( 'wp_head', 'sm_site_icons', 2 );


/* ==========================================================================
   ۳. صفحه‌ی موقت مسیرهای /smp/ — کدهای QR کتاب
   --------------------------------------------------------------------------
   کتاب «معماری متابولیک» در انتهای فصل‌ها کدهای QR دارد که به چهار نشانی
   زیر اشاره می‌کنند. کتاب هنوز چاپ نشده، ولی این چهار نشانی تثبیت شده‌اند
   و پس از چاپ دیگر قابل تغییر نخواهند بود. تا وقتی صفحه‌ی واقعی ساخته
   نشده، این کد به‌جای خطای ۴۰۴ یک صفحه‌ی برنددار نشان می‌دهد.

   این تابع فقط و فقط وقتی فعال می‌شود که:
     ۱. مسیر درخواستی دقیقاً یکی از چهار نشانی زیر باشد، و
     ۲. وردپرس برای آن مسیر هیچ محتوایی پیدا نکرده باشد (۴۰۴).

   بنابراین به‌محض اینکه صفحه‌ی واقعی را در پیشخوان بسازید، این کد
   خود‌به‌خود از مدار خارج می‌شود. نیازی به حذف آن نیست.
   ========================================================================== */

/**
 * فهرست مسیرهای چاپ‌شده در کتاب و متن صفحه‌ی موقت هر کدام.
 *
 * @return array
 */
function sm_book_routes() {
	return array(
		'smp/check' => array(
			'eyebrow' => 'فرم ارزیابی استراتژیک',
			'title'   => 'این فرم به‌زودی در دسترس قرار می‌گیرد',
			'text'    => 'شما از طریق کتاب «معماری متابولیک» به این صفحه رسیده‌اید. فرم ارزیابی اولیه در حال آماده‌سازی نهایی است. تا آن زمان می‌توانید درخواستتان را از راه‌های ارتباطی زیر ثبت کنید تا در نوبت بررسی قرار بگیرید.',
		),
		'smp/map' => array(
			'eyebrow' => 'نقشه راه سه‌فازی SMP',
			'title'   => 'نقشه راه به‌زودی منتشر می‌شود',
			'text'    => 'شما از طریق کتاب «معماری متابولیک» به این صفحه رسیده‌اید. نقشه‌ی راه تصویری سه فاز بازیابی، فعال‌سازی و بهینه‌سازی همراه با ویدیوی توضیحی، به‌زودی در همین نشانی منتشر می‌شود.',
		),
		'smp/start' => array(
			'eyebrow' => 'شروع پروتکل اختصاصی',
			'title'   => 'ثبت درخواست به‌زودی فعال می‌شود',
			'text'    => 'شما از طریق کتاب «معماری متابولیک» به این صفحه رسیده‌اید. ظرفیت پذیرش هر ماه محدود است. برای اینکه جای شما محفوظ بماند، می‌توانید از راه‌های ارتباطی زیر با ما تماس بگیرید.',
		),
		'smp/book' => array(
			'eyebrow' => 'پورتال خوانندگان کتاب',
			'title'   => 'پورتال به‌زودی باز می‌شود',
			'text'    => 'شما از طریق کتاب «معماری متابولیک» به این صفحه رسیده‌اید. ابزارهای پایش، چک‌لیست کالیبراسیون روزانه، فایل صوتی تنفس ۴–۲–۶ و ماتریس پایش ۳۰ روزه در حال آماده‌سازی هستند.',
		),
	);
}


/**
 * اگر یکی از مسیرهای کتاب درخواست شد و صفحه‌ای برایش وجود نداشت،
 * به‌جای ۴۰۴ یک صفحه‌ی برنددار نشان می‌دهد.
 */
function sm_serve_book_holding_page() {

	if ( ! is_404() ) {
		return;
	}

	// مسیر درخواستی را از URL بیرون می‌کشیم و اسلش‌های اضافه را می‌بریم.
	$request = wp_parse_url( isset( $_SERVER['REQUEST_URI'] ) ? wp_unslash( $_SERVER['REQUEST_URI'] ) : '', PHP_URL_PATH );
	$path    = trim( (string) $request, '/' );
	$path    = strtolower( $path );

	$routes = sm_book_routes();

	if ( ! isset( $routes[ $path ] ) ) {
		return;
	}

	// ۲۰۰ برمی‌گردانیم نه ۴۰۴، چون این یک صفحه‌ی معتبر و عمدی است.
	status_header( 200 );
	nocache_headers();

	sm_render_holding_page( $routes[ $path ] );
	exit;
}
add_action( 'template_redirect', 'sm_serve_book_holding_page' );


/**
 * صفحه‌ی موقت را رندر می‌کند.
 *
 * @param array $data شامل eyebrow و title و text.
 */
function sm_render_holding_page( $data ) {

	$logo    = get_stylesheet_directory_uri() . '/assets/images/logo-seal.png';
	$style   = get_stylesheet_directory_uri() . '/style.css';
	$contact = home_url( '/contact/' );

	?><!DOCTYPE html>
<html <?php language_attributes(); ?> dir="rtl">
<head>
	<meta charset="<?php bloginfo( 'charset' ); ?>">
	<meta name="viewport" content="width=device-width, initial-scale=1">
	<meta name="robots" content="noindex, follow">
	<title><?php echo esc_html( $data['title'] . ' — ' . get_bloginfo( 'name' ) ); ?></title>
	<link rel="stylesheet" href="<?php echo esc_url( $style ); ?>">
	<style><?php echo sm_font_face_css(); // phpcs:ignore WordPress.Security.EscapeOutput ?></style>
</head>
<body class="smp-holding">
	<div class="smp-holding__inner">
		<img class="smp-holding__logo" src="<?php echo esc_url( $logo ); ?>" alt="<?php echo esc_attr( get_bloginfo( 'name' ) ); ?>" width="132" height="132">
		<p class="smp-holding__eyebrow"><?php echo esc_html( $data['eyebrow'] ); ?></p>
		<h1 class="smp-holding__title"><?php echo esc_html( $data['title'] ); ?></h1>
		<hr class="smp-holding__rule">
		<p class="smp-holding__text"><?php echo esc_html( $data['text'] ); ?></p>
		<a class="smp-holding__cta" href="<?php echo esc_url( $contact ); ?>">راه‌های ارتباطی</a>
		<p class="smp-holding__note">
			این نشانی از کتاب «معماری متابولیک» می‌آید و معتبر است.<br>
			لطفاً آن را ذخیره کنید و بعداً دوباره سر بزنید.
		</p>
	</div>
</body>
</html>
	<?php
}


/* ==========================================================================
   ۴. پاک‌سازی و بهینه‌سازی سبک
   ========================================================================== */

/**
 * ایموجی‌های وردپرس را غیرفعال می‌کند.
 *
 * وردپرس در هر صفحه یک اسکریپت و یک استایل برای ایموجی بارگذاری می‌کند
 * که مرورگرهای امروزی به آن نیازی ندارند. حذفش چند کیلوبایت و یک
 * درخواست HTTP صرفه‌جویی می‌کند.
 */
function sm_disable_emojis() {
	remove_action( 'wp_head', 'print_emoji_detection_script', 7 );
	remove_action( 'admin_print_scripts', 'print_emoji_detection_script' );
	remove_action( 'wp_print_styles', 'print_emoji_styles' );
	remove_action( 'admin_print_styles', 'print_emoji_styles' );
	remove_filter( 'the_content_feed', 'wp_staticize_emoji' );
	remove_filter( 'comment_text_rss', 'wp_staticize_emoji' );
	remove_filter( 'wp_mail', 'wp_staticize_emoji_for_email' );
}
add_action( 'init', 'sm_disable_emojis' );


/**
 * نسخه‌ی وردپرس را از هدر و فید حذف می‌کند.
 *
 * افشای شماره‌ی نسخه به مهاجم می‌گوید دقیقاً کدام آسیب‌پذیری‌های
 * شناخته‌شده را روی این سایت امتحان کند.
 */
remove_action( 'wp_head', 'wp_generator' );
add_filter( 'the_generator', '__return_empty_string' );


/**
 * پیام خطای ورود را یکسان می‌کند.
 *
 * پیام پیش‌فرض وردپرس فرق می‌گذارد بین «نام کاربری اشتباه است» و
 * «رمز اشتباه است» — یعنی به مهاجم تأیید می‌کند که کدام نام کاربری
 * روی سایت وجود دارد.
 *
 * @return string
 */
function sm_generic_login_error() {
	return 'نام کاربری یا گذرواژه نادرست است.';
}
add_filter( 'login_errors', 'sm_generic_login_error' );


/* ==========================================================================
   ۵. بهبود دسترس‌پذیری و RTL
   ========================================================================== */

/**
 * ویژگی lang و dir را برای محتوای فارسی تضمین می‌کند و
 * کلاس کمکی به body اضافه می‌کند.
 *
 * @param array $classes کلاس‌های فعلی body.
 * @return array
 */
function sm_body_classes( $classes ) {
	$classes[] = 'sm-theme';
	if ( is_rtl() ) {
		$classes[] = 'sm-rtl';
	}
	return $classes;
}
add_filter( 'body_class', 'sm_body_classes' );


/**
 * متن «ادامه مطلب» را فارسی و معنادار می‌کند.
 *
 * @return string
 */
function sm_excerpt_more() {
	return ' …';
}
add_filter( 'excerpt_more', 'sm_excerpt_more' );
