<?php
/**
 * موتور فرم درخواست ارزیابی  (/smp/start/)
 * ---------------------------------------------------------------------------
 *
 * این فایل را دست نزنید مگر بخواهید رفتار فرم را عوض کنید.
 * برای ویرایش پرسش‌ها و متن‌ها به inc/content-forms.php بروید.
 *
 * چه کارهایی اینجا انجام می‌شود:
 *   ۱. ثبت نوع نوشته‌ی «درخواست‌ها» — درخواست‌ها داخل خود وردپرس
 *      ذخیره می‌شوند، نه روی سرویس بیرونی
 *   ۲. دریافت و اعتبارسنجی فرم
 *   ۳. اطلاع‌رسانی ایمیلی به مدیر
 *   ۴. ستون‌های جدول پیشخوان
 *
 * عمداً هیچ افزونه‌ای لازم ندارد و هیچ داده‌ای به بیرون نمی‌رود.
 *
 * @package saadatmehr
 */

defined( 'ABSPATH' ) || exit;


/**
 * محتوای فرم‌ها را می‌خواند و در حافظه نگه می‌دارد.
 *
 * @param string $key کلید: start یا check.
 * @return array
 */
function sm_form_content( $key ) {

	static $all = null;

	if ( null === $all ) {
		$file = get_stylesheet_directory() . '/inc/content-forms.php';
		$all  = file_exists( $file ) ? require $file : array();
	}

	return isset( $all[ $key ] ) ? $all[ $key ] : array();
}


/* ==========================================================================
   ۱. نوع نوشته‌ی «درخواست‌ها»
   ========================================================================== */

/**
 * نوع نوشته‌ی درخواست‌ها را ثبت می‌کند.
 *
 * public = false یعنی هیچ نشانی عمومی ندارد و در جست‌وجوی سایت هم
 * نمی‌آید. فقط از پیشخوان و فقط برای مدیر دیده می‌شود.
 */
function sm_register_lead_type() {

	register_post_type(
		'sm_lead',
		array(
			'labels'              => array(
				'name'          => 'درخواست‌های ارزیابی',
				'singular_name' => 'درخواست ارزیابی',
				'menu_name'     => 'درخواست‌های ارزیابی',
				'all_items'     => 'همه‌ی درخواست‌ها',
				'search_items'  => 'جست‌وجوی درخواست',
				'not_found'     => 'هنوز درخواستی ثبت نشده است.',
			),
			'public'              => false,
			'show_ui'             => true,
			'show_in_menu'        => true,
			'menu_icon'           => 'dashicons-clipboard',
			'menu_position'       => 26,
			'capability_type'     => 'post',
			'map_meta_cap'        => true,
			'capabilities'        => array( 'create_posts' => 'do_not_allow' ),
			'supports'            => array( 'title' ),
			'has_archive'         => false,
			'exclude_from_search' => true,
			'publicly_queryable'  => false,
			'rewrite'             => false,
			'show_in_rest'        => false,
		)
	);
}
add_action( 'init', 'sm_register_lead_type' );


/* ==========================================================================
   ۲. دریافت فرم
   ========================================================================== */

/**
 * فرم ارسال‌شده را می‌گیرد، اعتبارسنجی و ذخیره می‌کند.
 *
 * روی template_redirect سوار است تا پیش از چاپ هر خروجی اجرا شود و
 * بتواند بعد از ذخیره، کاربر را با Redirect به همان صفحه برگرداند.
 * این الگوی POST/Redirect/GET جلوی «ارسال دوباره با رفرش» را می‌گیرد.
 */
function sm_handle_lead_submit() {

	if ( 'POST' !== ( isset( $_SERVER['REQUEST_METHOD'] ) ? $_SERVER['REQUEST_METHOD'] : '' ) ) {
		return;
	}

	if ( ! isset( $_POST['sm_lead_form'] ) ) {
		return;
	}

	$redirect = wp_get_referer() ? wp_get_referer() : home_url( '/smp/start/' );
	$redirect = remove_query_arg( array( 'sm', 'sm_err' ), $redirect );

	// ---------- بررسی‌های امنیتی ----------

	$nonce = isset( $_POST['sm_lead_nonce'] ) ? sanitize_text_field( wp_unslash( $_POST['sm_lead_nonce'] ) ) : '';

	if ( ! wp_verify_nonce( $nonce, 'sm_lead_submit' ) ) {
		wp_safe_redirect( add_query_arg( 'sm', 'err', $redirect ) );
		exit;
	}

	// تله‌ی ربات: این فیلد برای کاربر نامرئی است، پس باید خالی بماند.
	if ( ! empty( $_POST['sm_website'] ) ) {
		wp_safe_redirect( add_query_arg( 'sm', 'ok', $redirect ) );
		exit;
	}

	// فرمی که در کمتر از سه ثانیه پر شده باشد، کار آدم نیست.
	$started = isset( $_POST['sm_t'] ) ? (int) $_POST['sm_t'] : 0;

	if ( $started && ( time() - $started ) < 3 ) {
		wp_safe_redirect( add_query_arg( 'sm', 'ok', $redirect ) );
		exit;
	}

	// ---------- جمع‌آوری مقادیر ----------

	$content = sm_form_content( 'start' );
	$values  = array();
	$missing = false;

	foreach ( $content['steps'] as $step ) {
		foreach ( $step['fields'] as $f ) {

			$raw = isset( $_POST[ 'sm_' . $f['name'] ] ) ? wp_unslash( $_POST[ 'sm_' . $f['name'] ] ) : '';

			if ( 'textarea' === $f['type'] ) {
				$val = sanitize_textarea_field( $raw );
			} elseif ( 'email' === $f['type'] ) {
				$val = sanitize_email( $raw );
			} else {
				$val = sanitize_text_field( $raw );
			}

			if ( ! empty( $f['req'] ) && '' === trim( $val ) ) {
				$missing = true;
			}

			$values[ $f['name'] ] = array(
				'label' => $f['label'],
				'value' => $val,
			);
		}
	}

	if ( $missing || empty( $_POST['sm_consent'] ) ) {
		wp_safe_redirect( add_query_arg( 'sm', 'err', $redirect ) );
		exit;
	}

	// ---------- ذخیره ----------

	$name  = isset( $values['name']['value'] ) ? $values['name']['value'] : 'بدون نام';
	$phone = isset( $values['phone']['value'] ) ? $values['phone']['value'] : '';

	$post_id = wp_insert_post(
		array(
			'post_type'   => 'sm_lead',
			'post_status' => 'publish',
			'post_title'  => trim( $name . ( $phone ? ' — ' . $phone : '' ) ),
		),
		true
	);

	if ( is_wp_error( $post_id ) ) {
		wp_safe_redirect( add_query_arg( 'sm', 'err', $redirect ) );
		exit;
	}

	foreach ( $values as $key => $item ) {
		update_post_meta( $post_id, '_sm_' . $key, $item['value'] );
	}

	update_post_meta( $post_id, '_sm_ip_hash', substr( wp_hash( sm_client_ip() ), 0, 16 ) );

	sm_notify_new_lead( $post_id, $values );

	wp_safe_redirect( add_query_arg( 'sm', 'ok', $redirect ) . '#sm-form' );
	exit;
}
add_action( 'template_redirect', 'sm_handle_lead_submit' );


/**
 * نشانی IP بازدیدکننده.
 *
 * فقط برای ساختن یک اثر انگشتِ درهم‌شده استفاده می‌شود تا اگر روزی
 * ارسال انبوه اسپم رخ داد، قابل تشخیص باشد. خودِ IP ذخیره نمی‌شود.
 *
 * @return string
 */
function sm_client_ip() {

	$keys = array( 'HTTP_CF_CONNECTING_IP', 'HTTP_X_FORWARDED_FOR', 'REMOTE_ADDR' );

	foreach ( $keys as $key ) {
		if ( ! empty( $_SERVER[ $key ] ) ) {
			$ip = sanitize_text_field( wp_unslash( $_SERVER[ $key ] ) );
			$ip = trim( explode( ',', $ip )[0] );
			if ( filter_var( $ip, FILTER_VALIDATE_IP ) ) {
				return $ip;
			}
		}
	}

	return '';
}


/**
 * ایمیل اطلاع‌رسانی درخواست تازه.
 *
 * @param int   $post_id شناسه‌ی درخواست.
 * @param array $values  مقادیر فرم.
 */
function sm_notify_new_lead( $post_id, $values ) {

	$to = get_option( 'admin_email' );

	if ( ! $to ) {
		return;
	}

	$lines = array( 'یک درخواست ارزیابی تازه ثبت شد.', '' );

	foreach ( $values as $item ) {
		if ( '' !== trim( $item['value'] ) ) {
			$lines[] = $item['label'] . ': ' . $item['value'];
		}
	}

	$lines[] = '';
	$lines[] = 'مشاهده در پیشخوان:';
	$lines[] = admin_url( 'post.php?post=' . $post_id . '&action=edit' );

	sm_mail(
		$to,
		'[' . get_bloginfo( 'name' ) . '] درخواست ارزیابی تازه',
		implode( "\n", $lines )
	);
}


/* ==========================================================================
   ۳. شمارش درخواست‌های همین ماه
   ========================================================================== */

/**
 * تعداد درخواست‌های ثبت‌شده در ۳۰ روز گذشته.
 *
 * برای نوار ظرفیت استفاده می‌شود. عدد واقعی است، نه ساختگی.
 *
 * @return int
 */
function sm_leads_this_month() {

	$cached = get_transient( 'sm_leads_month' );

	if ( false !== $cached ) {
		return (int) $cached;
	}

	$q = new WP_Query(
		array(
			'post_type'      => 'sm_lead',
			'post_status'    => 'publish',
			'posts_per_page' => 100,
			'fields'         => 'ids',
			'no_found_rows'  => false,
			'date_query'     => array(
				array( 'after' => '30 days ago' ),
			),
		)
	);

	$count = (int) $q->found_posts;

	set_transient( 'sm_leads_month', $count, 10 * MINUTE_IN_SECONDS );

	return $count;
}


/* ==========================================================================
   ۴. جدول پیشخوان
   ========================================================================== */

/**
 * ستون‌های جدول درخواست‌ها.
 *
 * @param array $cols ستون‌های پیش‌فرض.
 * @return array
 */
function sm_lead_columns( $cols ) {

	return array(
		'cb'            => isset( $cols['cb'] ) ? $cols['cb'] : '',
		'title'         => 'نام و شماره',
		'sm_challenge'  => 'چالش اصلی',
		'sm_city'       => 'شهر',
		'sm_commitment' => 'آمادگی',
		'date'          => 'تاریخ ثبت',
	);
}
add_filter( 'manage_sm_lead_posts_columns', 'sm_lead_columns' );


/**
 * محتوای ستون‌ها.
 *
 * @param string $col     نام ستون.
 * @param int    $post_id شناسه‌ی درخواست.
 */
function sm_lead_column_content( $col, $post_id ) {

	$map = array(
		'sm_challenge'  => '_sm_challenge',
		'sm_city'       => '_sm_city',
		'sm_commitment' => '_sm_commitment',
	);

	if ( isset( $map[ $col ] ) ) {
		echo esc_html( get_post_meta( $post_id, $map[ $col ], true ) );
	}
}
add_action( 'manage_sm_lead_posts_custom_column', 'sm_lead_column_content', 10, 2 );


/**
 * جعبه‌ی نمایش کامل یک درخواست در پیشخوان.
 */
function sm_lead_meta_box() {

	add_meta_box(
		'sm-lead-detail',
		'محتوای درخواست',
		'sm_render_lead_detail',
		'sm_lead',
		'normal',
		'high'
	);
}
add_action( 'add_meta_boxes', 'sm_lead_meta_box' );


/**
 * محتوای جعبه را چاپ می‌کند.
 *
 * @param WP_Post $post درخواست.
 */
function sm_render_lead_detail( $post ) {

	$content = sm_form_content( 'start' );
	?>
	<table class="widefat striped" dir="rtl" style="text-align:right">
		<tbody>
		<?php foreach ( $content['steps'] as $step ) : ?>
			<?php foreach ( $step['fields'] as $f ) : ?>
				<?php $val = get_post_meta( $post->ID, '_sm_' . $f['name'], true ); ?>
				<?php if ( '' === trim( (string) $val ) ) { continue; } ?>
				<tr>
					<th style="width:16rem"><?php echo esc_html( $f['label'] ); ?></th>
					<td style="white-space:pre-wrap"><?php echo esc_html( $val ); ?></td>
				</tr>
			<?php endforeach; ?>
		<?php endforeach; ?>
		</tbody>
	</table>
	<p style="margin-top:1rem;color:#666">
		این اطلاعات از فرم <code>/smp/start/</code> آمده است و فقط برای شما قابل مشاهده است.
	</p>
	<?php
}


/* ==========================================================================
   ۵. چاپ یک فیلد فرم
   ========================================================================== */

/**
 * یک فیلد فرم را چاپ می‌کند.
 *
 * @param array $f تعریف فیلد از inc/content-forms.php.
 */
function sm_form_field( $f ) {

	$id   = 'sm_' . $f['name'];
	$req  = ! empty( $f['req'] );
	$help = ! empty( $f['help'] ) ? $id . '_help' : '';
	$desc = $help ? ' aria-describedby="' . esc_attr( $help ) . '"' : '';

	// مقدار قبلی را برنمی‌گردانیم چون بعد از ارسال موفق Redirect
	// می‌شود و فرم دیگر نمایش داده نمی‌شود.
	?>
	<div class="sm-field sm-field--<?php echo esc_attr( $f['type'] ); ?>">

		<?php if ( 'radio' === $f['type'] ) : ?>

			<fieldset class="sm-radiogroup">
				<legend class="sm-field__label">
					<?php echo esc_html( $f['label'] ); ?>
					<?php if ( $req ) : ?><span class="sm-req" aria-hidden="true">*</span><?php endif; ?>
				</legend>
				<?php if ( $help ) : ?>
					<p class="sm-field__help" id="<?php echo esc_attr( $help ); ?>"><?php echo esc_html( $f['help'] ); ?></p>
				<?php endif; ?>
				<?php foreach ( $f['options'] as $n => $opt ) : ?>
					<label class="sm-check sm-check--radio">
						<input type="radio" name="<?php echo esc_attr( $id ); ?>"
						       value="<?php echo esc_attr( $opt ); ?>"
						       <?php echo $req && 0 === $n ? 'required' : ''; ?>>
						<span><?php echo esc_html( $opt ); ?></span>
					</label>
				<?php endforeach; ?>
			</fieldset>

		<?php else : ?>

			<label class="sm-field__label" for="<?php echo esc_attr( $id ); ?>">
				<?php echo esc_html( $f['label'] ); ?>
				<?php if ( $req ) : ?><span class="sm-req" aria-hidden="true">*</span><?php endif; ?>
			</label>

			<?php if ( $help ) : ?>
				<p class="sm-field__help" id="<?php echo esc_attr( $help ); ?>"><?php echo esc_html( $f['help'] ); ?></p>
			<?php endif; ?>

			<?php if ( 'textarea' === $f['type'] ) : ?>
				<textarea id="<?php echo esc_attr( $id ); ?>" name="<?php echo esc_attr( $id ); ?>"
				          rows="4" <?php echo $req ? 'required' : ''; ?><?php echo $desc; // phpcs:ignore WordPress.Security.EscapeOutput ?>></textarea>

			<?php elseif ( 'select' === $f['type'] ) : ?>
				<select id="<?php echo esc_attr( $id ); ?>" name="<?php echo esc_attr( $id ); ?>"
				        <?php echo $req ? 'required' : ''; ?><?php echo $desc; // phpcs:ignore WordPress.Security.EscapeOutput ?>>
					<option value="">— انتخاب کنید —</option>
					<?php foreach ( $f['options'] as $opt ) : ?>
						<option value="<?php echo esc_attr( $opt ); ?>"><?php echo esc_html( $opt ); ?></option>
					<?php endforeach; ?>
				</select>

			<?php else : ?>
				<input type="<?php echo esc_attr( $f['type'] ); ?>"
				       id="<?php echo esc_attr( $id ); ?>" name="<?php echo esc_attr( $id ); ?>"
				       <?php echo isset( $f['min'] ) ? 'min="' . (int) $f['min'] . '"' : ''; ?>
				       <?php echo isset( $f['max'] ) ? 'max="' . (int) $f['max'] . '"' : ''; ?>
				       <?php echo 'tel' === $f['type'] ? 'inputmode="tel" dir="ltr"' : ''; ?>
				       <?php echo 'email' === $f['type'] ? 'dir="ltr"' : ''; ?>
				       <?php echo $req ? 'required' : ''; ?><?php echo $desc; // phpcs:ignore WordPress.Security.EscapeOutput ?>>
			<?php endif; ?>

		<?php endif; ?>

	</div>
	<?php
}


/* ==========================================================================
   ۶. ثبت سفارش و پیش‌فاکتور  (/order/)
   --------------------------------------------------------------------------
   برای «اینماد» لازم است: فرآیند ثبت سفارش، صدور پیش‌فاکتور آنلاین و
   هدایت به درگاه باید تعریف‌شده باشد — حتی برای محصول غیرفیزیکی.
   ========================================================================== */

/**
 * نوع نوشته‌ی سفارش‌ها را ثبت می‌کند.
 */
function sm_register_order_type() {

	register_post_type(
		'sm_order',
		array(
			'labels'              => array(
				'name'          => 'سفارش‌ها',
				'singular_name' => 'سفارش',
				'menu_name'     => 'سفارش‌ها',
				'all_items'     => 'همه‌ی سفارش‌ها',
				'not_found'     => 'هنوز سفارشی ثبت نشده است.',
			),
			'public'              => false,
			'show_ui'             => true,
			'show_in_menu'        => true,
			'menu_icon'           => 'dashicons-cart',
			'menu_position'       => 27,
			'capability_type'     => 'post',
			'map_meta_cap'        => true,
			'capabilities'        => array( 'create_posts' => 'do_not_allow' ),
			'supports'            => array( 'title' ),
			'has_archive'         => false,
			'exclude_from_search' => true,
			'publicly_queryable'  => false,
			'rewrite'             => false,
			'show_in_rest'        => false,
		)
	);
}
add_action( 'init', 'sm_register_order_type' );


/**
 * شماره‌ی یکتای پیش‌فاکتور می‌سازد.
 *
 * قالب: SM-<سال شمسی><ماه><روزِ ترتیبی>-<شناسه>
 * شناسه‌ی نوشته در شماره هست تا هیچ‌وقت تکراری نشود.
 *
 * @param int $post_id شناسه‌ی سفارش.
 * @return string
 */
function sm_invoice_number( $post_id ) {
	return 'SM-' . gmdate( 'ymd', current_time( 'timestamp' ) ) . '-' . $post_id;
}


/**
 * محصول انتخاب‌شده را از روی کلیدش پیدا می‌کند.
 *
 * @param string $key کلید محصول.
 * @return array|null
 */
function sm_find_product( $key ) {

	$order = sm_form_content( 'order' );

	foreach ( (array) $order['products'] as $p ) {
		if ( ! empty( $p['enabled'] ) && $p['key'] === $key ) {
			return $p;
		}
	}

	return null;
}


/**
 * قیمت را با رقم فارسی و جداکننده‌ی هزارگان برمی‌گرداند.
 *
 * پارامترِ «تعداد» از نسخه ۵٫۳ برداشته شد؛ هر سفارش یک عدد است.
 *
 * @param string $price عدد خام، مثلاً '1200'.
 * @return string رشته‌ی آماده‌ی نمایش، یا رشته‌ی خالی اگر قیمت نداشته باشد.
 */
function sm_format_price( $price ) {

	$price = preg_replace( '/[^0-9.]/', '', sm_fa_to_en_digits( (string) $price ) );

	if ( '' === $price ) {
		return '';
	}

	$order = sm_form_content( 'order' );

	// جداکننده‌ی هزارگان فارسی «٬» است، نه ویرگول لاتین
	$num = number_format( (float) $price, 0, '٫', '٬' );

	return sm_fa_digits( $num ) . ' ' . $order['currency'];
}


/**
 * شماره‌ی موبایل ایرانی را به شکل استاندارد درمی‌آورد.
 *
 * ۰۹۱۲…  و  ۹۸۹۱۲…  و  +۹۸۹۱۲…  همه به 09xxxxxxxxx تبدیل می‌شوند.
 * اگر شماره معتبر نبود، رشته‌ی خالی برمی‌گردد.
 *
 * @param string $raw ورودی کاربر.
 * @return string
 */
function sm_normalize_mobile( $raw ) {

	$n = preg_replace( '/[^0-9]/', '', sm_fa_to_en_digits( (string) $raw ) );

	if ( 0 === strpos( $n, '0098' ) ) {
		$n = substr( $n, 4 );
	} elseif ( 0 === strpos( $n, '98' ) && 12 === strlen( $n ) ) {
		$n = substr( $n, 2 );
	}

	if ( 10 === strlen( $n ) && '9' === $n[0] ) {
		$n = '0' . $n;
	}

	return preg_match( '/^09[0-9]{9}$/', $n ) ? $n : '';
}


/**
 * نشانیِ IP برای ثبتِ لحظه‌ی امضای الکترونیکی.
 *
 * ⚠️ عمداً با sm_client_ip() فرق دارد و فقط REMOTE_ADDR را می‌خواند.
 *
 * آن یکی هدرهای پروکسی (X-Forwarded-For و مانندش) را هم نگاه می‌کند
 * که برای تشخیصِ اسپم خوب است، ولی آن هدرها را هر کسی می‌تواند جعل
 * کند. در یک سندِ حقوقی، IPِ جعل‌پذیر از نبودنِ IP بدتر است — چون
 * اعتمادی ایجاد می‌کند که پشتش چیزی نیست.
 *
 * @return string
 */
function sm_signing_ip() {

	$ip = isset( $_SERVER['REMOTE_ADDR'] ) ? sanitize_text_field( wp_unslash( $_SERVER['REMOTE_ADDR'] ) ) : '';
	$ip = filter_var( $ip, FILTER_VALIDATE_IP );

	return $ip ? $ip : '';
}


/**
 * وضعیتِ امضا را به فارسیِ قابل‌فهم برمی‌گرداند.
 *
 * یک جا نوشته شده تا پیشخوان و ایمیلِ اطلاع‌رسانی، دو جور حرف نزنند.
 *
 * @param string $state مقدارِ _sm_verified.
 * @return string
 */
function sm_verify_state_label( $state ) {

	$map = array(
		'yes'         => 'ایمیل تأیید شد و قوانین امضا شد ✔',
		'no'          => 'هنوز تأیید نشده — کد وارد نشده است',
		'off'         => 'تأیید ایمیلی خاموش بوده است',
		'mail-failed' => '⚠️ ارسال ایمیل ناموفق بود — قوانین امضا نشده',
		'skipped'     => '⚠️ خریدار گفت ایمیل نرسید — قوانین امضا نشده (تیکِ پذیرش ثبت است)',

		// سفارش‌های قدیمیِ پیش از نسخه ۵٫۳ که مسیرِ پیامکی داشتند
		'sms-failed'  => '⚠️ (سفارش قدیمی) ارسال پیامک ناموفق بود',
	);

	return isset( $map[ $state ] ) ? $map[ $state ] : '—';
}


/**
 * کد تأیید را ایمیل می‌کند.
 *
 * چرا ایمیل و نه پیامک: پنل پیامکی هزینه و ثبت‌نام دارد، ولی ایمیل
 * را خودِ وردپرس با wp_mail می‌فرستد.
 *
 * اگر سرور تنظیماتِ ارسالِ ایمیل نداشته باشد، wp_mail مقدار false
 * برمی‌گرداند و صداکننده تصمیم می‌گیرد چه کند — سفارش از بین
 * نمی‌رود.
 *
 * @param string $email   نشانی ایمیل.
 * @param string $code    کد پنج‌رقمی.
 * @param string $invoice شماره‌ی پیش‌فاکتور.
 * @return bool
 */
function sm_send_verify_email( $email, $code, $invoice = '' ) {

	$c = sm_form_content( 'order' );

	if ( ! is_email( $email ) ) {
		return false;
	}

	$lines = array();

	foreach ( (array) $c['mail_body'] as $line ) {
		$lines[] = str_replace(
			array( '{code}', '{invoice}' ),
			array( sm_fa_digits( $code ), $invoice ),
			$line
		);
	}

	return sm_mail(
		$email,
		$c['mail_subject'],
		implode( "\n\n", $lines )
	);
}


/**
 * نشانیِ فرستنده‌ی ایمیل‌های سایت.
 *
 * 🔴 چرا این تابع وجود دارد — یک اشتباهِ من در نسخه ۵٫۳
 *
 * آن نسخه نشانیِ «ایمیل مدیر» را به‌عنوان From می‌گذاشت. اگر ایمیلِ
 * مدیرِ وردپرس یک نشانیِ جی‌میل یا یاهو باشد — که تقریباً همیشه
 * همین‌طور است — سرورِ هاست اجازه‌ی ارسال از طرفِ آن دامنه را ندارد.
 *
 * نتیجه این می‌شود که سرورِ گیرنده (جی‌میل، یاهو، …) نامه را یا
 * دور می‌اندازد یا مستقیم به هرزنامه می‌برد، چون رکوردِ SPF دامنه‌ی
 * فرستنده این سرور را تأیید نمی‌کند. wp_mail هم مقدار true
 * برمی‌گرداند، چون از نظرِ خودِ سرور نامه «تحویل صف شد».
 *
 * پس فرستنده باید نشانی‌ای از دامنه‌ی خودِ سایت باشد. نشانیِ مدیر
 * به‌جایش در Reply-To می‌نشیند تا پاسخ‌ها همچنان به او برسد.
 *
 * @return string
 */
function sm_mail_from() {

	$c = sm_form_content( 'order' );

	$set = isset( $c['verify_from_email'] ) ? trim( (string) $c['verify_from_email'] ) : '';

	if ( $set && is_email( $set ) ) {
		return $set;
	}

	$host = wp_parse_url( home_url(), PHP_URL_HOST );
	$host = preg_replace( '/^www\./i', '', (string) $host );

	/*
	 * اگر به هر دلیلی دامنه خوانده نشد، رشته‌ی خالی برمی‌گردانیم و
	 * sm_mail() هدرِ From را اصلاً نمی‌گذارد. آن وقت وردپرس خودش
	 * wordpress@دامنه را می‌گذارد که باز هم هم‌دامنه است.
	 *
	 * عمداً به ایمیلِ مدیر برنمی‌گردیم — همان کاری بود که نسخه ۵٫۳
	 * می‌کرد و نامه‌ها را به هرزنامه می‌فرستاد.
	 */
	return $host ? 'noreply@' . $host : '';
}


/**
 * آخرین خطای ارسال ایمیل.
 *
 * wp_mail فقط true یا false می‌دهد و علتِ شکست را نمی‌گوید. وردپرس
 * علت را روی قلاب wp_mail_failed می‌فرستد؛ اینجا نگهش می‌داریم تا
 * در پیشخوان نشان داده شود. بدون این، «ایمیل نرفت» یک بن‌بست است.
 *
 * @param WP_Error|null $error خطا.
 * @return string
 */
function sm_mail_error( $error = null ) {

	static $last = '';

	// null یعنی «فقط بخوان». هر چیز دیگری — از جمله رشته‌ی خالی —
	// یعنی «بنویس»، وگرنه پاک کردنِ خطای قبلی ممکن نبود.
	if ( null !== $error ) {
		$last = is_wp_error( $error ) ? $error->get_error_message() : (string) $error;
	}

	return $last;
}

add_action(
	'wp_mail_failed',
	function ( $error ) {
		sm_mail_error( $error );
	}
);


/**
 * یک ایمیلِ متنیِ ساده می‌فرستد، با فرستنده‌ی درست.
 *
 * @param string $to      گیرنده.
 * @param string $subject موضوع.
 * @param string $body    متن.
 * @return bool
 */
function sm_mail( $to, $subject, $body ) {

	$c = sm_form_content( 'order' );

	$name = isset( $c['verify_from_name'] ) ? trim( (string) $c['verify_from_name'] ) : '';
	$name = $name ? $name : wp_specialchars_decode( get_bloginfo( 'name' ), ENT_QUOTES );

	$headers = array( 'Content-Type: text/plain; charset=UTF-8' );

	$from = sm_mail_from();

	if ( is_email( $from ) ) {
		$headers[] = sprintf( 'From: %s <%s>', $name, $from );
	}

	$admin = get_option( 'admin_email' );

	if ( $admin && is_email( $admin ) ) {
		$headers[] = 'Reply-To: ' . $admin;
	}

	return (bool) wp_mail( $to, $subject, $body, $headers );
}


/**
 * کد تازه می‌سازد، ذخیره و ایمیل می‌کند.
 *
 * خودِ کد ذخیره نمی‌شود؛ فقط درهم‌سازی‌اش. اگر روزی کسی به دیتابیس
 * دسترسی پیدا کند، کدهای در جریان را نمی‌بیند.
 *
 * @param int    $post_id شناسه‌ی سفارش.
 * @param string $email   نشانی ایمیل.
 * @return bool آیا ایمیل ارسال شد.
 */
function sm_issue_verify_code( $post_id, $email ) {

	$code = (string) wp_rand( 10000, 99999 );

	update_post_meta( $post_id, '_sm_code_hash', wp_hash_password( $code ) );
	update_post_meta( $post_id, '_sm_code_exp', time() + 10 * MINUTE_IN_SECONDS );
	update_post_meta( $post_id, '_sm_code_tries', 0 );

	$sent = sm_send_verify_email(
		$email,
		$code,
		(string) get_post_meta( $post_id, '_sm_invoice', true )
	);

	/*
	 * نتیجه‌ی ارسال روی خودِ سفارش ثبت می‌شود.
	 *
	 * ⚠️ نکته‌ای که باید بدانید: true یعنی «سرور نامه را پذیرفت»،
	 *    نه «نامه رسید». اگر نشانیِ فرستنده به دامنه‌ی سایت نخورَد،
	 *    سرورِ گیرنده بعداً و بی‌صدا نامه را دور می‌اندازد و ما
	 *    خبردار نمی‌شویم. برای همین نشانیِ فرستنده در پیشخوان
	 *    نشان داده می‌شود.
	 */
	update_post_meta( $post_id, '_sm_mail_at', time() );
	update_post_meta( $post_id, '_sm_mail_ok', $sent ? 'yes' : 'no' );
	update_post_meta( $post_id, '_sm_mail_from', sm_mail_from() );
	update_post_meta( $post_id, '_sm_mail_error', $sent ? '' : sm_mail_error() );

	return $sent;
}


/**
 * فرم سفارش را می‌گیرد، ذخیره می‌کند و — بسته به تنظیمات — یا به
 * مرحله‌ی تأیید شماره می‌برد یا مستقیم پیش‌فاکتور صادر می‌کند.
 */
function sm_handle_order_submit() {

	if ( 'POST' !== ( isset( $_SERVER['REQUEST_METHOD'] ) ? $_SERVER['REQUEST_METHOD'] : '' ) ) {
		return;
	}

	if ( ! isset( $_POST['sm_order_form'] ) ) {
		return;
	}

	$redirect = wp_get_referer() ? wp_get_referer() : home_url( '/order/' );
	$redirect = remove_query_arg( array( 'sm', 'inv', 't' ), $redirect );

	$nonce = isset( $_POST['sm_order_nonce'] ) ? sanitize_text_field( wp_unslash( $_POST['sm_order_nonce'] ) ) : '';

	if ( ! wp_verify_nonce( $nonce, 'sm_order_submit' ) ) {
		wp_safe_redirect( add_query_arg( 'sm', 'err', $redirect ) );
		exit;
	}

	if ( ! empty( $_POST['sm_website'] ) ) {
		wp_safe_redirect( $redirect );
		exit;
	}

	$content = sm_form_content( 'order' );

	$key     = isset( $_POST['sm_product'] ) ? sanitize_key( wp_unslash( $_POST['sm_product'] ) ) : '';
	$product = sm_find_product( $key );

	if ( ! $product || empty( $_POST['sm_consent'] ) ) {
		wp_safe_redirect( add_query_arg( 'sm', 'err', $redirect ) );
		exit;
	}

	$fields = array_merge( $content['fields'], $content['ship_fields'] );
	$values = array();
	$bad    = false;

	foreach ( $fields as $f ) {

		$raw = isset( $_POST[ 'sm_' . $f['name'] ] ) ? wp_unslash( $_POST[ 'sm_' . $f['name'] ] ) : '';

		if ( 'textarea' === $f['type'] ) {
			$val = sanitize_textarea_field( $raw );
		} elseif ( 'email' === $f['type'] ) {
			$val = sanitize_email( $raw );
		} else {
			$val = sanitize_text_field( $raw );
		}

		if ( ! empty( $f['req'] ) && '' === trim( $val ) ) {
			$bad = true;
		}

		$values[ $f['name'] ] = array(
			'label' => $f['label'],
			'value' => $val,
		);
	}

	$mobile = sm_normalize_mobile( $values['ophone']['value'] );

	if ( ! $mobile ) {
		$bad = true;
	}

	// ایمیل اجباری است: کدِ تأیید — یعنی امضای قوانین — به آن می‌رود.
	$email = sanitize_email( $values['oemail']['value'] );

	if ( ! is_email( $email ) ) {
		$bad = true;
	}

	// محصول فیزیکی بدون نشانی، سفارش ناقصی است
	if ( ! empty( $product['physical'] ) && '' === trim( $values['oaddress']['value'] ) ) {
		$bad = true;
	}

	if ( $bad ) {
		wp_safe_redirect( add_query_arg( 'sm', 'err', $redirect ) );
		exit;
	}

	$values['ophone']['value'] = $mobile;
	$values['oemail']['value'] = $email;

	$post_id = wp_insert_post(
		array(
			'post_type'   => 'sm_order',
			'post_status' => 'publish',
			'post_title'  => $product['label'] . ' — ' . $values['buyer']['value'],
		),
		true
	);

	if ( is_wp_error( $post_id ) ) {
		wp_safe_redirect( add_query_arg( 'sm', 'err', $redirect ) );
		exit;
	}

	$invoice = sm_invoice_number( $post_id );

	update_post_meta( $post_id, '_sm_invoice', $invoice );
	update_post_meta( $post_id, '_sm_product', $product['label'] );
	update_post_meta( $post_id, '_sm_product_key', $product['key'] );
	update_post_meta( $post_id, '_sm_price', (string) $product['price'] );
	update_post_meta( $post_id, '_sm_paid', 'no' );

	foreach ( $values as $name => $item ) {
		update_post_meta( $post_id, '_sm_' . $name, $item['value'] );
	}

	/*
	 * ردِ پذیرشِ قوانین.
	 *
	 * تیکِ «قوانین را می‌پذیرم» همین‌جا ثبت می‌شود، و نسخه‌ی قوانین
	 * هم کنارش می‌آید. بدون شماره‌ی نسخه، شش ماه بعد معلوم نیست
	 * خریدار کدام متن را پذیرفته بوده.
	 *
	 * امضای نهایی اما این نیست؛ امضا وقتی ثبت می‌شود که کدِ ایمیل
	 * درست وارد شود (پایین‌تر، در sm_handle_order_verify).
	 */
	$legal = sm_page_content( 'terms' );

	update_post_meta( $post_id, '_sm_consent_at', time() );
	update_post_meta( $post_id, '_sm_consent_ip', sm_signing_ip() );
	update_post_meta( $post_id, '_sm_terms_rev', isset( $legal['updated'] ) ? $legal['updated'] : '' );

	/*
	 * نشانه‌ی یکتای سفارش.
	 * بدون آن، هر کسی می‌توانست با حدس زدن شماره‌ی سفارش، صفحه‌ی
	 * پیش‌فاکتور یا تأیید سفارشِ دیگری را باز کند.
	 */
	$token = wp_generate_password( 20, false, false );
	update_post_meta( $post_id, '_sm_token', $token );

	$args = array( 'inv' => $post_id, 't' => $token );

	// ---------- مسیر با تأیید ایمیل ----------
	if ( ! empty( $content['verify_enabled'] ) ) {

		update_post_meta( $post_id, '_sm_verified', 'no' );

		$sent = sm_issue_verify_code( $post_id, $email );

		$args['sm'] = 'verify';

		if ( ! $sent ) {
			// ایمیل نرفت؛ سفارش از بین نمی‌رود، فقط تأییدنشده
			// می‌ماند و مدیر در پیشخوان می‌بیند.
			update_post_meta( $post_id, '_sm_verified', 'mail-failed' );
			$args['sm'] = 'inv';
			$args['e']  = 'mailfail';
			sm_notify_new_order( $post_id, $product, $values, $invoice );
		}

		wp_safe_redirect( add_query_arg( $args, $redirect ) . '#sm-form' );
		exit;
	}

	// ---------- مسیر بدون تأیید ----------
	update_post_meta( $post_id, '_sm_verified', 'off' );
	sm_notify_new_order( $post_id, $product, $values, $invoice );

	$args['sm'] = 'inv';
	wp_safe_redirect( add_query_arg( $args, $redirect ) . '#sm-form' );
	exit;
}
add_action( 'template_redirect', 'sm_handle_order_submit' );


/**
 * کد تأیید ارسال‌شده را بررسی می‌کند.
 */
function sm_handle_order_verify() {

	if ( 'POST' !== ( isset( $_SERVER['REQUEST_METHOD'] ) ? $_SERVER['REQUEST_METHOD'] : '' ) ) {
		return;
	}

	if ( ! isset( $_POST['sm_verify_form'] ) ) {
		return;
	}

	$nonce = isset( $_POST['sm_verify_nonce'] ) ? sanitize_text_field( wp_unslash( $_POST['sm_verify_nonce'] ) ) : '';

	if ( ! wp_verify_nonce( $nonce, 'sm_order_verify' ) ) {
		return;
	}

	$id    = isset( $_POST['sm_inv'] ) ? absint( wp_unslash( $_POST['sm_inv'] ) ) : 0;
	$token = isset( $_POST['sm_token'] ) ? sanitize_text_field( wp_unslash( $_POST['sm_token'] ) ) : '';

	if ( ! sm_order_token_ok( $id, $token ) ) {
		return;
	}

	$base     = wp_get_referer() ? wp_get_referer() : home_url( '/order/' );
	$base     = remove_query_arg( array( 'sm', 'inv', 't', 'e' ), $base );
	$back     = add_query_arg( array( 'sm' => 'verify', 'inv' => $id, 't' => $token ), $base );

	// ---------- درخواست ارسال دوباره ----------
	if ( isset( $_POST['sm_resend'] ) ) {

		$tries = (int) get_post_meta( $id, '_sm_mail_tries', true );
		update_post_meta( $id, '_sm_mail_tries', $tries + 1 );

		$sent = sm_issue_verify_code( $id, (string) get_post_meta( $id, '_sm_oemail', true ) );

		wp_safe_redirect( add_query_arg( 'e', $sent ? 'sent' : 'mailfail', $back ) . '#sm-form' );
		exit;
	}

	/*
	 * ---------- «ایمیل به دستم نرسید» ----------
	 *
	 * راهِ فرار، تا خریدار هیچ‌وقت پشتِ یک ایمیلِ نرسیده گیر نکند.
	 *
	 * چرا لازم است: اگر ارسالِ ایمیلِ هاست خراب باشد، بدونِ این دکمه
	 * خریدار به‌هیچ‌وجه نمی‌تواند خرید را تمام کند. یک سفارشِ
	 * ازدست‌رفته از یک امضای نداشته بدتر است.
	 *
	 * چرا سوءاستفاده نمی‌شود: این دکمه فقط بعد از یک دور تلاش دیده
	 * می‌شود (page-order.php)، و سفارش با برچسبِ روشنِ
	 * «بدون امضای الکترونیکی» ثبت می‌شود. تیکِ پذیرشِ قوانین و
	 * زمان و IP‌اش از همان مرحله‌ی اول ثبت شده و سر جایش است؛
	 * فقط اثباتِ مالکیتِ ایمیل کم است.
	 */
	if ( isset( $_POST['sm_skip'] ) ) {

		update_post_meta( $id, '_sm_verified', 'skipped' );
		update_post_meta( $id, '_sm_skipped_at', time() );

		delete_post_meta( $id, '_sm_code_hash' );
		delete_post_meta( $id, '_sm_code_exp' );

		$product = sm_find_product( (string) get_post_meta( $id, '_sm_product_key', true ) );

		if ( $product ) {
			sm_notify_new_order(
				$id,
				$product,
				sm_order_values( $id ),
				(string) get_post_meta( $id, '_sm_invoice', true )
			);
		}

		wp_safe_redirect(
			add_query_arg(
				array( 'sm' => 'inv', 'inv' => $id, 't' => $token, 'e' => 'skipped' ),
				$base
			) . '#sm-form'
		);
		exit;
	}

	$tries = (int) get_post_meta( $id, '_sm_code_tries', true );

	if ( $tries >= 5 ) {
		wp_safe_redirect( add_query_arg( 'e', 'locked', $back ) . '#sm-form' );
		exit;
	}

	$exp = (int) get_post_meta( $id, '_sm_code_exp', true );

	if ( ! $exp || time() > $exp ) {
		wp_safe_redirect( add_query_arg( 'e', 'expired', $back ) . '#sm-form' );
		exit;
	}

	$code = preg_replace( '/[^0-9]/', '', sm_fa_to_en_digits( isset( $_POST['sm_code'] ) ? wp_unslash( $_POST['sm_code'] ) : '' ) );
	$hash = (string) get_post_meta( $id, '_sm_code_hash', true );

	if ( ! $code || ! $hash || ! wp_check_password( $code, $hash ) ) {
		update_post_meta( $id, '_sm_code_tries', $tries + 1 );
		wp_safe_redirect( add_query_arg( 'e', 'wrong', $back ) . '#sm-form' );
		exit;
	}

	// ---------- درست بود ----------
	update_post_meta( $id, '_sm_verified', 'yes' );
	delete_post_meta( $id, '_sm_code_hash' );
	delete_post_meta( $id, '_sm_code_exp' );

	/*
	 * امضای الکترونیکی.
	 *
	 * خریدار کدی را وارد کرده که فقط به صندوقِ ایمیلِ خودش رفته
	 * بود. پس هم نشانیِ ایمیل تأیید شده، هم پذیرشِ قوانین.
	 * لحظه، IP و مرورگر را ثبت می‌کنیم تا اگر روزی اختلافی پیش
	 * آمد، سند وجود داشته باشد.
	 */
	update_post_meta( $id, '_sm_signed_at', time() );
	update_post_meta( $id, '_sm_signed_ip', sm_signing_ip() );
	update_post_meta(
		$id,
		'_sm_signed_ua',
		isset( $_SERVER['HTTP_USER_AGENT'] )
			? substr( sanitize_text_field( wp_unslash( $_SERVER['HTTP_USER_AGENT'] ) ), 0, 190 )
			: ''
	);

	$product = sm_find_product( (string) get_post_meta( $id, '_sm_product_key', true ) );
	$values  = sm_order_values( $id );

	if ( $product ) {
		sm_notify_new_order(
			$id,
			$product,
			$values,
			(string) get_post_meta( $id, '_sm_invoice', true )
		);
	}

	wp_safe_redirect( add_query_arg( array( 'sm' => 'inv', 'inv' => $id, 't' => $token ), $base ) . '#sm-form' );
	exit;
}
add_action( 'template_redirect', 'sm_handle_order_verify' );


/**
 * آیا این نشانه با این سفارش می‌خواند؟
 *
 * @param int    $id    شناسه‌ی سفارش.
 * @param string $token نشانه.
 * @return bool
 */
function sm_order_token_ok( $id, $token ) {

	if ( ! $id || ! $token ) {
		return false;
	}

	if ( 'sm_order' !== get_post_type( $id ) ) {
		return false;
	}

	$stored = (string) get_post_meta( $id, '_sm_token', true );

	return $stored && hash_equals( $stored, $token );
}


/**
 * مقادیر ذخیره‌شده‌ی یک سفارش را به شکل آرایه‌ی برچسب‌دار برمی‌گرداند.
 *
 * @param int $id شناسه‌ی سفارش.
 * @return array
 */
function sm_order_values( $id ) {

	$c      = sm_form_content( 'order' );
	$out    = array();

	foreach ( array_merge( $c['fields'], $c['ship_fields'] ) as $f ) {
		$out[ $f['name'] ] = array(
			'label' => $f['label'],
			'value' => (string) get_post_meta( $id, '_sm_' . $f['name'], true ),
		);
	}

	return $out;
}


/**
 * ایمیل اطلاع‌رسانی سفارش تازه.
 *
 * @param int    $post_id شناسه‌ی سفارش.
 * @param array  $product محصول.
 * @param array  $values  مقادیر فرم.
 * @param string $invoice شماره‌ی پیش‌فاکتور.
 */
function sm_notify_new_order( $post_id, $product, $values, $invoice ) {

	$to = get_option( 'admin_email' );

	if ( ! $to ) {
		return;
	}

	$verified = (string) get_post_meta( $post_id, '_sm_verified', true );
	$state    = sm_verify_state_label( $verified );
	$price    = sm_format_price( $product['price'] );

	$lines = array(
		'سفارش تازه ثبت شد.',
		'',
		'شماره پیش‌فاکتور: ' . $invoice,
		'محصول: ' . $product['label'],
		'مبلغ: ' . ( $price ? $price : 'استعلام قیمت' ),
		'وضعیت امضا: ' . $state,
		'',
	);

	$signed = (int) get_post_meta( $post_id, '_sm_signed_at', true );

	if ( $signed ) {
		$lines[] = 'زمان امضا: ' . sm_jalali_datetime( $signed );
		$lines[] = 'IP امضا: ' . get_post_meta( $post_id, '_sm_signed_ip', true );
		$lines[] = 'نسخه‌ی قوانین: ' . get_post_meta( $post_id, '_sm_terms_rev', true );
		$lines[] = '';
	}

	foreach ( $values as $item ) {
		if ( '' !== trim( $item['value'] ) ) {
			$lines[] = $item['label'] . ': ' . $item['value'];
		}
	}

	$lines[] = '';
	$lines[] = admin_url( 'post.php?post=' . $post_id . '&action=edit' );

	sm_mail(
		$to,
		'[' . get_bloginfo( 'name' ) . '] سفارش تازه — ' . $invoice,
		implode( "\n", $lines )
	);
}


/**
 * ستون‌های جدول سفارش‌ها.
 *
 * @param array $cols ستون‌های پیش‌فرض.
 * @return array
 */
function sm_order_columns( $cols ) {

	return array(
		'cb'          => isset( $cols['cb'] ) ? $cols['cb'] : '',
		'title'       => 'سفارش',
		'sm_invoice'  => 'شماره پیش‌فاکتور',
		'sm_ophone'   => 'تماس',
		'sm_verified' => 'تأیید شماره',
		'sm_paid'     => 'پرداخت',
		'date'        => 'تاریخ',
	);
}
add_filter( 'manage_sm_order_posts_columns', 'sm_order_columns' );


/**
 * محتوای ستون‌های سفارش.
 *
 * @param string $col     نام ستون.
 * @param int    $post_id شناسه‌ی سفارش.
 */
function sm_order_column_content( $col, $post_id ) {

	if ( 'sm_invoice' === $col ) {
		echo esc_html( get_post_meta( $post_id, '_sm_invoice', true ) );
	} elseif ( 'sm_ophone' === $col ) {
		echo esc_html( get_post_meta( $post_id, '_sm_ophone', true ) );
	} elseif ( 'sm_paid' === $col ) {
		echo 'yes' === get_post_meta( $post_id, '_sm_paid', true ) ? 'پرداخت‌شده' : '— در انتظار';
	} elseif ( 'sm_verified' === $col ) {

		$map = array(
			'yes'        => '✔ تأیید شد',
			'no'         => '— در انتظار کد',
			'off'        => '— خاموش',
			'sms-failed' => '⚠️ پیامک نرفت',
		);

		$v = (string) get_post_meta( $post_id, '_sm_verified', true );

		echo esc_html( isset( $map[ $v ] ) ? $map[ $v ] : '—' );
	}
}
add_action( 'manage_sm_order_posts_custom_column', 'sm_order_column_content', 10, 2 );


/**
 * جعبه‌ی جزئیات سفارش در پیشخوان.
 */
function sm_order_meta_box() {

	add_meta_box( 'sm-order-detail', 'جزئیات سفارش', 'sm_render_order_detail', 'sm_order', 'normal', 'high' );
}
add_action( 'add_meta_boxes', 'sm_order_meta_box' );


/**
 * جزئیات سفارش را چاپ می‌کند.
 *
 * @param WP_Post $post سفارش.
 */
function sm_render_order_detail( $post ) {

	$content = sm_form_content( 'order' );
	$fields  = array_merge( $content['fields'], $content['ship_fields'] );
	?>
	<table class="widefat striped" dir="rtl" style="text-align:right">
		<tbody>
			<tr><th style="width:16rem">شماره پیش‌فاکتور</th><td><?php echo esc_html( get_post_meta( $post->ID, '_sm_invoice', true ) ); ?></td></tr>
			<tr><th>محصول</th><td><?php echo esc_html( get_post_meta( $post->ID, '_sm_product', true ) ); ?></td></tr>
			<?php $total = sm_format_price( get_post_meta( $post->ID, '_sm_price', true ) ); ?>
			<tr><th>مبلغ</th><td><?php echo esc_html( $total ? $total : 'استعلام قیمت' ); ?></td></tr>
			<?php
			$v      = (string) get_post_meta( $post->ID, '_sm_verified', true );
			$signed = (int) get_post_meta( $post->ID, '_sm_signed_at', true );
			?>
			<tr><th>وضعیت امضا</th><td><?php echo esc_html( sm_verify_state_label( $v ) ); ?></td></tr>
			<?php if ( $signed ) : ?>
				<tr><th>زمان امضای قوانین</th><td><?php echo esc_html( sm_jalali_datetime( $signed ) ); ?></td></tr>
				<tr><th>IP لحظه‌ی امضا</th><td dir="ltr" style="text-align:right"><?php echo esc_html( get_post_meta( $post->ID, '_sm_signed_ip', true ) ); ?></td></tr>
				<tr><th>مرورگر</th><td dir="ltr" style="text-align:right;white-space:pre-wrap"><?php echo esc_html( get_post_meta( $post->ID, '_sm_signed_ua', true ) ); ?></td></tr>
			<?php endif; ?>
			<?php if ( get_post_meta( $post->ID, '_sm_terms_rev', true ) ) : ?>
				<tr><th>نسخه‌ی قوانینِ پذیرفته‌شده</th><td><?php echo esc_html( get_post_meta( $post->ID, '_sm_terms_rev', true ) ); ?></td></tr>
			<?php endif; ?>
			<?php $mail_at = (int) get_post_meta( $post->ID, '_sm_mail_at', true ); ?>
			<?php if ( $mail_at ) : ?>
				<tr>
					<th>ارسال کد به ایمیل</th>
					<td>
						<?php
						$mok = 'yes' === get_post_meta( $post->ID, '_sm_mail_ok', true );
						echo esc_html( ( $mok ? 'سرور پذیرفت — ' : 'سرور نپذیرفت — ' ) . sm_jalali_datetime( $mail_at ) );
						?>
						<?php if ( $mok ) : ?>
							<br><span style="color:#996800">«پذیرفت» یعنی تحویلِ صف شد، نه اینکه حتماً رسید.</span>
						<?php endif; ?>
					</td>
				</tr>
				<tr><th>فرستنده</th><td dir="ltr" style="text-align:right"><?php echo esc_html( get_post_meta( $post->ID, '_sm_mail_from', true ) ); ?></td></tr>
				<?php if ( get_post_meta( $post->ID, '_sm_mail_error', true ) ) : ?>
					<tr><th>خطای ارسال</th><td dir="ltr" style="text-align:right"><?php echo esc_html( get_post_meta( $post->ID, '_sm_mail_error', true ) ); ?></td></tr>
				<?php endif; ?>
			<?php endif; ?>
			<?php foreach ( $fields as $f ) : ?>
				<?php $val = get_post_meta( $post->ID, '_sm_' . $f['name'], true ); ?>
				<?php if ( '' === trim( (string) $val ) ) { continue; } ?>
				<tr>
					<th><?php echo esc_html( $f['label'] ); ?></th>
					<td style="white-space:pre-wrap"><?php echo esc_html( $val ); ?></td>
				</tr>
			<?php endforeach; ?>
		</tbody>
	</table>
	<p style="margin-top:1rem;color:#666">
		وضعیت پرداخت را پس از تأیید، از فیلد <code>_sm_paid</code> روی <code>yes</code> بگذارید
		(یا فعلاً همین‌جا یادداشت کنید).
	</p>
	<?php
}


/* ==========================================================================
   ۷. پاپ‌آپ هماهنگی پرداخت
   --------------------------------------------------------------------------
   جای درگاه بانکی را می‌گیرد تا وقتی درگاه گرفته شود.

   ⚠️ عمداً هیچ شماره کارت، شماره شبا یا نام بانکی اینجا نیست. تنها
      راه هماهنگی، واتساپ است. اگر روزی شماره حساب اضافه شد، باید
      حتماً به نام همان شخص یا شرکتی باشد که در قوانین سایت معرفی
      شده، وگرنه از نظر حقوقی مشکل‌ساز است.
   ========================================================================== */

/**
 * پاپ‌آپ پرداخت را چاپ می‌کند.
 *
 * تگ <dialog> پایه‌ی کار است، پس بستن با Escape، قفل پس‌زمینه و
 * مدیریت فوکوس را خود مرورگر انجام می‌دهد و لازم نیست دستی بنویسیم.
 *
 * @param array  $c       محتوای بخش order.
 * @param string $invoice شماره‌ی پیش‌فاکتور.
 * @param string $total   مبلغ آماده‌ی نمایش.
 */
function sm_render_paysheet( $c, $invoice, $total ) {

	$wa_text = str_replace( '{invoice}', $invoice, (string) $c['pay_message'] );

	$wa_link = 'https://wa.me/' . rawurlencode( $c['pay_number_raw'] )
		. '?text=' . rawurlencode( $wa_text );
	?>
	<dialog class="sm-paysheet" id="sm-paysheet" aria-labelledby="sm-paysheet-title">
		<form method="dialog" class="sm-paysheet__dismiss">
			<button class="sm-paysheet__x" aria-label="<?php echo esc_attr( $c['pay_close'] ); ?>">&times;</button>
		</form>

		<div class="sm-paysheet__grip" aria-hidden="true"></div>

		<h2 class="sm-paysheet__title" id="sm-paysheet-title"><?php echo esc_html( $c['pay_title'] ); ?></h2>

		<p class="sm-paysheet__intro"><?php echo esc_html( $c['pay_intro'] ); ?></p>

		<dl class="sm-paysheet__facts">
			<div>
				<dt><?php echo esc_html( $c['invoice_no'] ); ?></dt>
				<dd dir="ltr"><?php echo esc_html( $invoice ); ?></dd>
			</div>
			<?php if ( $total ) : ?>
				<div>
					<dt>مبلغ</dt>
					<dd class="sm-paysheet__amount"><?php echo esc_html( $total ); ?></dd>
				</div>
			<?php endif; ?>
		</dl>

		<p class="sm-paysheet__label"><?php echo esc_html( $c['pay_number_label'] ); ?></p>

		<div class="sm-paysheet__number">
			<span dir="ltr" id="sm-pay-number"><?php echo esc_html( $c['pay_number'] ); ?></span>
		</div>

		<button type="button" class="sm-btn sm-btn--ghost sm-paysheet__copy"
		        data-sm-copy="<?php echo esc_attr( sm_fa_to_en_digits( $c['pay_number'] ) ); ?>"
		        data-sm-done="<?php echo esc_attr( $c['pay_copied'] ); ?>">
			<?php echo esc_html( $c['pay_copy'] ); ?>
		</button>

		<a class="sm-btn sm-paysheet__wa" href="<?php echo esc_url( $wa_link ); ?>" target="_blank" rel="noopener">
			<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
				<path d="M20.5 11.6a8.4 8.4 0 0 1-12.5 7.3L3.5 20.5l1.6-4.4A8.4 8.4 0 1 1 20.5 11.6Z"/>
				<path d="M8.6 8.2c.4-.1.8 0 1 .4l.7 1.2c.2.3.1.6-.1.9l-.4.5c.6 1.1 1.5 2 2.6 2.6l.5-.5c.2-.2.6-.3.9-.1l1.2.7c.4.2.5.6.4 1-.2.8-1 1.4-1.9 1.3-2.9-.4-5.2-2.7-5.6-5.6-.1-.9.4-1.7 1.2-1.9Z" fill="currentColor" stroke="none"/>
			</svg>
			<?php echo esc_html( $c['pay_whatsapp'] ); ?>
		</a>

		<p class="sm-paysheet__hours"><?php echo esc_html( $c['pay_hours'] ); ?></p>
	</dialog>
	<?php
}


/* ===========================================================================
   آزمایش ایمیل  —  پیشخوان → سفارش‌ها → آزمایش ایمیل
   ---------------------------------------------------------------------------
   چرا این صفحه لازم شد:

   وقتی کدِ تأیید نمی‌رسد، «ایمیل کار نمی‌کند» یک بن‌بست است. باید
   بشود دید سرور دقیقاً چه می‌کند. این صفحه سه چیز را نشان می‌دهد که
   هیچ‌کدامشان در پیشخوانِ وردپرس پیدا نیست:

     ۱) نشانی‌ای که سایت با آن نامه می‌فرستد (From)
     ۲) اینکه wp_mail چه جوابی داد
     ۳) متنِ دقیقِ خطا، اگر خطایی بود

   ⚠️ و یک هشدارِ صریح: «پذیرفته شد» با «رسید» فرق دارد.
   =========================================================================== */

/**
 * منوی «آزمایش ایمیل» را زیر سفارش‌ها اضافه می‌کند.
 */
function sm_add_mailtest_page() {

	add_submenu_page(
		'edit.php?post_type=sm_order',
		'آزمایش ایمیل',
		'آزمایش ایمیل',
		'manage_options',
		'sm-mailtest',
		'sm_render_mailtest_page'
	);
}
add_action( 'admin_menu', 'sm_add_mailtest_page' );


/**
 * صفحه‌ی آزمایش ایمیل را چاپ می‌کند.
 */
function sm_render_mailtest_page() {

	if ( ! current_user_can( 'manage_options' ) ) {
		return;
	}

	$result = null;
	$to     = (string) get_option( 'admin_email' );

	if ( isset( $_POST['sm_mailtest'] ) && check_admin_referer( 'sm_mailtest' ) ) {

		$to = isset( $_POST['sm_mailtest_to'] )
			? sanitize_email( wp_unslash( $_POST['sm_mailtest_to'] ) )
			: '';

		if ( is_email( $to ) ) {

			sm_mail_error( '' );   // پاک کردنِ خطای قبلی

			$ok = sm_mail(
				$to,
				'آزمایش ایمیل — ' . get_bloginfo( 'name' ),
				implode(
					"\n\n",
					array(
						'این یک نامه‌ی آزمایشی از وب‌سایت شماست.',
						'اگر این نامه را می‌بینید، یعنی ارسال ایمیلِ سایت کار می‌کند و کدهای تأیید هم خواهند رسید.',
						'زمان ارسال: ' . sm_jalali_datetime( time() ),
					)
				)
			);

			$result = array(
				'ok'    => $ok,
				'error' => sm_mail_error(),
				'to'    => $to,
			);
		}
	}

	$from   = sm_mail_from();
	$host   = preg_replace( '/^www\./i', '', (string) wp_parse_url( home_url(), PHP_URL_HOST ) );
	$admin  = (string) get_option( 'admin_email' );
	$amatch = $admin && false !== strpos( $admin, '@' . $host );
	?>
	<div class="wrap" dir="rtl" style="text-align:right;max-width:52rem">
		<h1>آزمایش ایمیل</h1>

		<p>اگر کدِ تأیید به دستِ خریدارها نمی‌رسد، از همین‌جا شروع کنید.</p>

		<table class="widefat striped" style="margin:1.5rem 0">
			<tbody>
				<tr>
					<th style="width:18rem">نامه‌ها با این نشانی فرستاده می‌شوند</th>
					<td dir="ltr" style="text-align:right"><code><?php echo esc_html( $from ); ?></code></td>
				</tr>
				<tr>
					<th>دامنه‌ی سایت</th>
					<td dir="ltr" style="text-align:right"><code><?php echo esc_html( $host ); ?></code></td>
				</tr>
				<tr>
					<th>ایمیل مدیر (فقط برای پاسخ)</th>
					<td dir="ltr" style="text-align:right">
						<code><?php echo esc_html( $admin ); ?></code>
						<?php if ( ! $amatch ) : ?>
							<span style="color:#996800"> — از دامنه‌ی سایت نیست. اشکالی ندارد؛ فقط در Reply-To استفاده می‌شود.</span>
						<?php endif; ?>
					</td>
				</tr>
			</tbody>
		</table>

		<?php if ( $result ) : ?>
			<?php if ( $result['ok'] ) : ?>
				<div class="notice notice-success"><p>
					<strong>سرور نامه را پذیرفت.</strong>
					نامه به <code dir="ltr"><?php echo esc_html( $result['to'] ); ?></code> تحویلِ صفِ ارسال شد.
				</p></div>
				<div class="notice notice-warning"><p>
					⚠️ <strong>«پذیرفته شد» با «رسید» فرق دارد.</strong>
					حالا صندوقتان را ببینید — و حتماً پوشه‌ی هرزنامه (Spam) را هم.
					اگر تا دو دقیقه نیامد، یعنی سرور نامه را گرفته ولی جایی در
					مسیر دور انداخته شده. در این حالت باید WP Mail SMTP را
					راه بیندازید؛ راهنمایش پایینِ همین صفحه است.
				</p></div>
			<?php else : ?>
				<div class="notice notice-error"><p>
					<strong>سرور نامه را نپذیرفت.</strong>
					<?php if ( $result['error'] ) : ?>
						<br>متنِ خطا:
						<code dir="ltr" style="display:inline-block;margin-top:.4rem"><?php echo esc_html( $result['error'] ); ?></code>
					<?php else : ?>
						<br>سرور دلیلی اعلام نکرد — یعنی تابعِ ارسال ایمیل روی این هاست خاموش است.
					<?php endif; ?>
				</p></div>
			<?php endif; ?>
		<?php endif; ?>

		<form method="post">
			<?php wp_nonce_field( 'sm_mailtest' ); ?>
			<p>
				<label for="sm_mailtest_to"><strong>نامه‌ی آزمایشی به این نشانی فرستاده شود:</strong></label><br>
				<input type="email" id="sm_mailtest_to" name="sm_mailtest_to" dir="ltr"
				       value="<?php echo esc_attr( $to ); ?>" class="regular-text" required>
			</p>
			<p>
				<button type="submit" name="sm_mailtest" value="1" class="button button-primary">
					فرستادن نامه‌ی آزمایشی
				</button>
			</p>
		</form>

		<hr style="margin:2rem 0">

		<?php sm_render_dns_health( $host ); ?>

		<hr style="margin:2rem 0">

		<h2>اگر نامه اصلاً نرسید</h2>

		<p>
			تقریباً همیشه علتش این است که هاست‌های اشتراکی اجازه‌ی ارسالِ
			مستقیم ندارند. راه‌حلِ رایگان و همیشگی این است:
		</p>

		<ol style="line-height:2.2">
			<li>در cPanel یک صندوق ایمیل بسازید، مثلاً
				<code dir="ltr">noreply@<?php echo esc_html( $host ); ?></code>
				و رمزش را یادداشت کنید.</li>
			<li>افزونه‌ی رایگانِ <strong>WP Mail SMTP</strong> را نصب و فعال کنید.</li>
			<li>در ویزاردش گزینه‌ی <strong>Other SMTP</strong> را بزنید و این‌ها را وارد کنید:
				<ul style="list-style:disc;margin-inline-start:1.5rem">
					<li>SMTP Host: <code dir="ltr">mail.<?php echo esc_html( $host ); ?></code></li>
					<li>Encryption: <code>SSL</code> · Port: <code>465</code></li>
					<li>Username: همان نشانیِ کامل صندوق</li>
					<li>Password: رمزِ همان صندوق</li>
					<li>From Email: همان نشانی · From Name: نام آکادمی</li>
				</ul>
			</li>
			<li>برگردید به همین صفحه و دوباره نامه‌ی آزمایشی بفرستید.</li>
		</ol>

		<p>
			<strong>تا آن موقع هیچ سفارشی گم نمی‌شود.</strong> اگر کدِ تأیید
			نرسد، خریدار می‌تواند روی «ایمیل به دستم نرسید» بزند؛ سفارش و
			پیش‌فاکتورش ثبت می‌شود و در فهرستِ سفارش‌ها با برچسبِ روشن
			می‌بینیدش — فقط امضای الکترونیکی ندارد.
		</p>
	</div>
	<?php
}


/* ===========================================================================
   سلامتِ ایمیلِ دامنه  —  چرا نامه‌ها به «هرزنامه» می‌روند
   ---------------------------------------------------------------------------
   وقتی نامه می‌رسد ولی در پوشه‌ی Spam می‌نشیند، مشکل از سایت یا از متنِ
   نامه نیست. مشکل این است که سرورِ گیرنده نمی‌تواند ثابت کند این نامه
   واقعاً از طرفِ دامنه‌ی شما فرستاده شده.

   این کار با سه رکوردِ DNS انجام می‌شود:

     SPF   — می‌گوید «این سرورها حق دارند از طرفِ دامنه‌ی من نامه بفرستند»
     DKIM  — امضای رمزنگاری‌شده‌ی نامه، تا دست‌کاری معلوم شود
     DMARC — می‌گوید «اگر SPF یا DKIM نخواند، چه کن»

   هیچ‌کدامشان را نمی‌شود از داخلِ وردپرس ساخت؛ جایشان در DNS دامنه است.
   ولی می‌شود نشان داد کدامشان هست و کدام نیست — که کارِ همین تابع است.

   ⚠️ dns_get_record روی بعضی هاست‌ها خاموش است. در آن حالت به‌جای
      حدس زدن، صریح می‌گوییم که نتوانستیم بخوانیم.
   =========================================================================== */

/**
 * یک رکوردِ TXT مشخص را می‌خواند.
 *
 * @param string $name  نامِ کامل.
 * @param string $begin آغازِ مقدارِ موردِ نظر، مثلاً v=spf1.
 * @return string مقدار، یا رشته‌ی خالی.
 */
function sm_find_txt( $name, $begin ) {

	if ( ! function_exists( 'dns_get_record' ) ) {
		return '';
	}

	// @ لازم است: اگر DNS جواب ندهد، پیشخوان نباید پر از اخطار شود.
	$rows = @dns_get_record( $name, DNS_TXT ); // phpcs:ignore

	foreach ( (array) $rows as $r ) {
		$v = isset( $r['txt'] ) ? (string) $r['txt'] : '';
		if ( 0 === stripos( $v, $begin ) ) {
			return $v;
		}
	}

	return '';
}


/**
 * IP سرور را در فهرست‌های سیاهِ معروف جست‌وجو می‌کند.
 *
 * روشِ کار استاندارد است: IP را وارونه می‌کنیم و به‌عنوان نامِ میزبان
 * از سرورِ فهرست می‌پرسیم. اگر جواب داد، یعنی در فهرست است.
 *
 * @param string $ip نشانی IP.
 * @return array آرایه‌ای از نامِ فهرست‌هایی که IP در آن‌هاست.
 */
function sm_blocklist_hits( $ip ) {

	if ( ! function_exists( 'dns_get_record' ) || ! filter_var( $ip, FILTER_VALIDATE_IP, FILTER_FLAG_IPV4 ) ) {
		return array();
	}

	$rev  = implode( '.', array_reverse( explode( '.', $ip ) ) );
	$hits = array();

	$lists = array(
		'zen.spamhaus.org'       => 'Spamhaus',
		'bl.spamcop.net'         => 'SpamCop',
		'b.barracudacentral.org' => 'Barracuda',
		'psbl.surriel.com'       => 'PSBL',
	);

	foreach ( $lists as $zone => $label ) {
		if ( @dns_get_record( $rev . '.' . $zone, DNS_A ) ) { // phpcs:ignore
			$hits[] = $label;
		}
	}

	return $hits;
}


/**
 * وضعیتِ سلامتِ ایمیلِ دامنه را نشان می‌دهد.
 *
 * ⚠️ این بخش عمداً «نتیجه‌محور» است، نه یک فهرستِ ثابت. اول می‌بیند
 *    چه چیزی واقعاً هست و چه چیزی نیست، بعد فقط همان کاری را پیشنهاد
 *    می‌دهد که باقی مانده. یک فهرستِ ده‌بندیِ همیشگی به کسی که وقت
 *    ندارد کمکی نمی‌کند.
 *
 * @param string $host دامنه‌ی سایت، بدون www.
 */
function sm_render_dns_health( $host ) {

	$admin  = (string) get_option( 'admin_email' );
	$rua    = is_email( $admin ) ? $admin : 'postmaster@' . $host;
	$dmarc_suggest = 'v=DMARC1; p=none; rua=mailto:' . $rua;

	$can = function_exists( 'dns_get_record' );

	$spf   = $can ? sm_find_txt( $host, 'v=spf1' ) : '';
	$dkim  = $can ? sm_find_txt( 'default._domainkey.' . $host, 'v=DKIM1' ) : '';
	$dmarc = $can ? sm_find_txt( '_dmarc.' . $host, 'v=DMARC1' ) : '';

	$ip   = '';
	if ( $can ) {
		$a  = @dns_get_record( $host, DNS_A ); // phpcs:ignore
		$ip = ! empty( $a[0]['ip'] ) ? $a[0]['ip'] : '';
	}

	$hits    = $ip ? sm_blocklist_hits( $ip ) : array();
	$all_ok  = $spf && $dkim && $dmarc && ! $hits;
	?>
	<h2>چرا نامه به پوشه‌ی هرزنامه می‌رود</h2>

	<p>
		نامه رسیده، یعنی ارسال کار می‌کند. حالا باید به سرورِ گیرنده
		(جی‌میل، یاهو، …) <strong>ثابت</strong> شود که نامه واقعاً از
		طرفِ دامنه‌ی شماست. جدولِ زیر وضعیتِ همین لحظه را نشان می‌دهد.
	</p>

	<?php if ( ! $can ) : ?>
		<div class="notice notice-warning inline"><p>
			این هاست اجازه‌ی خواندنِ DNS را به وردپرس نمی‌دهد، پس نمی‌توانم
			بگویم کدام رکورد هست و کدام نیست.
		</p></div>
	<?php else : ?>
		<?php
		$rows = array(
			array(
				'name' => 'SPF',
				'ok'   => (bool) $spf,
				'val'  => $spf,
				'why'  => 'می‌گوید کدام سرورها حق دارند از طرفِ دامنه‌ی شما نامه بفرستند.',
			),
			array(
				'name' => 'DKIM',
				'ok'   => (bool) $dkim,
				'val'  => $dkim ? 'کلید ثبت شده است (سلکتور default)' : '',
				'why'  => 'امضای رمزنگاری‌شده‌ی نامه.',
			),
			array(
				'name' => 'DMARC',
				'ok'   => (bool) $dmarc,
				'val'  => $dmarc,
				'why'  => 'به سرورِ گیرنده می‌گوید با نامه‌های تأییدنشده چه کند.',
			),
			array(
				'name' => 'فهرست سیاه',
				'ok'   => empty( $hits ),
				'val'  => $hits
					? ( 'در این فهرست‌ها هست: ' . implode( '، ', $hits ) )
					: ( $ip ? 'IP سرور (' . $ip . ') در چهار فهرستِ معروف تمیز است.' : '' ),
				'why'  => 'اگر IP سرور در فهرست سیاه باشد، هیچ رکوردی نجاتش نمی‌دهد.',
			),
		);
		?>
		<table class="widefat striped" style="margin:1.2rem 0">
			<thead>
				<tr><th style="width:8rem">مورد</th><th style="width:8rem">وضعیت</th><th>توضیح</th></tr>
			</thead>
			<tbody>
				<?php foreach ( $rows as $r ) : ?>
					<tr>
						<td><strong><?php echo esc_html( $r['name'] ); ?></strong></td>
						<td>
							<?php if ( $r['ok'] ) : ?>
								<span style="color:#1b7a2f;font-weight:700">✔ درست است</span>
							<?php else : ?>
								<span style="color:#b5372b;font-weight:700">✘ مشکل دارد</span>
							<?php endif; ?>
						</td>
						<td>
							<?php echo esc_html( $r['why'] ); ?>
							<?php if ( $r['val'] ) : ?>
								<br><code dir="ltr" style="display:inline-block;margin-top:.35rem;word-break:break-all"><?php echo esc_html( $r['val'] ); ?></code>
							<?php endif; ?>
						</td>
					</tr>
				<?php endforeach; ?>
			</tbody>
		</table>
	<?php endif; ?>

	<?php if ( $can && $all_ok ) : ?>

		<div class="notice notice-success inline" style="margin:1.2rem 0"><p>
			<strong>رکوردهای دامنه‌ی شما درست‌اند و سرورتان در فهرست سیاه نیست.</strong>
			پس علتِ رفتن به هرزنامه یکی از سه چیزِ زیر است — به همین ترتیب.
		</p></div>

		<ol style="line-height:2.3">
			<li>
				<strong>ناهماهنگیِ «فرستنده‌ی پاکت» — که در همین نسخه درست شد.</strong><br>
				<span style="color:#555">
					هر نامه دو فرستنده دارد: آن‌که شما می‌بینید (From) و آن‌که
					سرورها با هم ردوبدل می‌کنند (envelope). رکوردِ SPF روی دومی
					بررسی می‌شود. وردپرس دومی را تنظیم نمی‌کرد، پس هاست نامِ
					خودش را می‌گذاشت و SPF شما اصلاً بررسی نمی‌شد — با اینکه
					کاملاً درست بود. از این نسخه هر دو یکی هستند.
					<strong>اول یک نامه‌ی آزمایشی تازه بفرستید و ببینید هنوز
					به هرزنامه می‌رود یا نه.</strong>
				</span>
			</li>

			<li>
				<strong>صندوقِ فرستنده وجود ندارد.</strong><br>
				cPanel → Email Accounts → Create →
				<code dir="ltr">noreply@<?php echo esc_html( $host ); ?></code><br>
				<span style="color:#555">
					سایت با همین نشانی نامه می‌فرستد. بعضی سرورهای گیرنده
					بررسی می‌کنند که نشانیِ فرستنده واقعاً وجود دارد.
				</span>
			</li>

			<li>
				<strong>دامنه‌ی تازه، بدون سابقه.</strong><br>
				<span style="color:#555">
					جی‌میل با دامنه‌هایی که تازه شروع به فرستادن کرده‌اند
					محتاط است. این با گذشتِ چند روز و چند ده نامه‌ی سالم
					خودبه‌خود بهتر می‌شود. کمکش کنید: نامه را از Spam بیرون
					بیاورید و «Report not spam» بزنید؛ و نشانیِ
					<code dir="ltr">noreply@<?php echo esc_html( $host ); ?></code>
					را به دفترچه‌ی نشانی‌های خودتان اضافه کنید.
				</span>
			</li>
		</ol>

		<?php if ( $dmarc && false === stripos( $dmarc, 'rua=' ) ) : ?>
			<p style="color:#555">
				نکته‌ی اختیاری: رکوردِ DMARC شما بخشِ گزارش‌گیری ندارد. اگر
				مقدارش را به این تغییر دهید، هفته‌ای یک گزارش می‌گیرید که
				نشان می‌دهد نامه‌هایتان کجا و چرا رد می‌شوند:<br>
				<code dir="ltr" style="word-break:break-all"><?php echo esc_html( $dmarc_suggest ); ?></code>
			</p>
		<?php endif; ?>

	<?php else : ?>

		<h3>راهِ حل — به ترتیب</h3>

		<ol style="line-height:2.3">
			<?php if ( ! $spf || ! $dkim ) : ?>
				<li>
					<strong>اول این؛ معمولاً همین کافی است.</strong><br>
					cPanel → بخش <strong>Email</strong> → ابزارِ
					<strong>Email Deliverability</strong> → جلوی
					<code dir="ltr"><?php echo esc_html( $host ); ?></code>
					دکمه‌ی <strong>Repair</strong> را بزنید.<br>
					<span style="color:#555">
						SPF و DKIM را خودش می‌سازد و روی DNS می‌نشاند. اگر گفت
						«Manual Repair»، یعنی DNS دامنه جای دیگری است؛ همان صفحه
						مقدارها را نشان می‌دهد تا در پنلِ DNS کپی کنید.
					</span>
				</li>
			<?php endif; ?>

			<?php if ( ! $dmarc ) : ?>
				<li>
					<strong>DMARC را دستی اضافه کنید.</strong> cPanel معمولاً این
					یکی را نمی‌سازد. یک رکوردِ TXT بسازید:
					<table class="widefat" style="margin:.6rem 0;max-width:44rem">
						<tbody>
							<tr><th style="width:8rem">نوع</th><td><code>TXT</code></td></tr>
							<tr><th>نام (Host)</th><td><code dir="ltr">_dmarc</code></td></tr>
							<tr><th>مقدار</th><td><code dir="ltr" style="word-break:break-all"><?php echo esc_html( $dmarc_suggest ); ?></code></td></tr>
						</tbody>
					</table>
					<span style="color:#555">
						<code>p=none</code> یعنی «فقط گزارش بده، چیزی را رد نکن» —
						امن‌ترین نقطه‌ی شروع.
					</span>
				</li>
			<?php endif; ?>

			<?php if ( $hits ) : ?>
				<li>
					<strong style="color:#b5372b">IP سرور در فهرستِ سیاه است.</strong>
					تا وقتی بیرون نیاید، هیچ تنظیمی جواب نمی‌دهد. این را به
					پشتیبانیِ هاست اطلاع دهید؛ خارج کردنِ IP کارِ آن‌هاست، نه شما.
					راهِ دورزدنش، فرستادنِ نامه‌ها از یک سرویسِ بیرونی است.
				</li>
			<?php endif; ?>

			<li>
				<strong>بعد از هر تغییر، همین صفحه را دوباره باز کنید.</strong><br>
				<span style="color:#555">
					تغییرِ DNS بینِ چند دقیقه تا چند ساعت طول می‌کشد تا پخش شود.
				</span>
			</li>
		</ol>

	<?php endif; ?>
	<?php
}



/* ===========================================================================
   دو تنظیمِ ریزِ ایمیل که تأثیرشان بزرگ است
   ---------------------------------------------------------------------------
   نامه‌ها دو «فرستنده» دارند و مردم معمولاً فقط یکی‌اش را می‌بینند:

     From:          چیزی که در ایمیل‌خوان نشان داده می‌شود
     envelope-from  چیزی که سرورها موقعِ تحویل با هم ردوبدل می‌کنند

   🔴 نکته‌ی مهم: رکوردِ SPF روی envelope-from بررسی می‌شود، نه روی From.

   وردپرس به‌صورت پیش‌فرض envelope-from را تنظیم نمی‌کند، پس PHP از
   نامِ کاربریِ هاست استفاده می‌کند — چیزی مثل user@server47.hostname.net
   که با دامنه‌ی شما نمی‌خواند. آن وقت SPF «نمی‌خوانَد» و نامه به
   هرزنامه می‌رود، حتی اگر SPF دامنه‌تان کامل و درست باشد.

   این دو قلاب همین را درست می‌کنند.
   =========================================================================== */

/**
 * envelope-from و Message-ID را با دامنه‌ی سایت هم‌تراز می‌کند.
 *
 * ⚠️ با اولویت ۵ سوار می‌شود، یعنی زودتر از افزونه‌ها. اگر روزی
 *    WP Mail SMTP یا هر افزونه‌ی دیگری نصب شد، تنظیماتِ آن‌ها
 *    (اولویت ۱۰ به بعد) روی این می‌نشیند و برنده است — همان‌طور
 *    که باید باشد، چون آن تنظیمات صریح و دستیِ خودِ شماست.
 *
 * @param PHPMailer $phpmailer شیء ارسال‌کننده.
 */
function sm_align_mail_sender( $phpmailer ) {

	$from = sm_mail_from();

	if ( ! is_email( $from ) ) {
		return;
	}

	// فقط وقتی هنوز کسی تنظیمش نکرده. این‌طوری جلوی افزونه‌ها را نمی‌گیریم.
	if ( empty( $phpmailer->Sender ) ) {
		$phpmailer->Sender = $from;
	}

	/*
	 * Message-ID را هم هم‌دامنه می‌کنیم.
	 *
	 * PHPMailer اگر خالی باشد خودش یکی می‌سازد، ولی از نامِ میزبانِ
	 * سرور — مثلاً <…@server47.hostname.net>. ناهمخوانیِ دامنه‌ی
	 * Message-ID با دامنه‌ی From یکی از نشانه‌هایی است که فیلترها
	 * به آن امتیازِ منفی می‌دهند.
	 */
	if ( empty( $phpmailer->MessageID ) ) {
		$domain = substr( strrchr( $from, '@' ), 1 );

		$phpmailer->MessageID = sprintf(
			'<%s.%s@%s>',
			time(),
			wp_generate_password( 12, false, false ),
			$domain
		);
	}
}
add_action( 'phpmailer_init', 'sm_align_mail_sender', 5 );


/**
 * نشانیِ پیش‌فرضِ فرستنده برای نامه‌هایی که خودِ وردپرس می‌فرستد.
 *
 * بدون این، وردپرس از wordpress@دامنه استفاده می‌کند. بد نیست، ولی
 * بهتر است همه‌ی نامه‌های سایت از یک نشانیِ واحد بیایند — هم برای
 * فیلترها بهتر است، هم برای کسی که نامه را می‌بیند.
 *
 * ⚠️ این فیلتر فقط وقتی اثر دارد که فرستنده صریحاً تعیین نشده باشد،
 *    پس جلوی هیچ افزونه‌ای را نمی‌گیرد.
 *
 * @param string $email نشانی پیش‌فرض.
 * @return string
 */
function sm_default_mail_from( $email ) {

	$from = sm_mail_from();

	return is_email( $from ) ? $from : $email;
}
add_filter( 'wp_mail_from', 'sm_default_mail_from' );


/**
 * نامِ پیش‌فرضِ فرستنده — به‌جای «WordPress».
 *
 * @param string $name نام پیش‌فرض.
 * @return string
 */
function sm_default_mail_from_name( $name ) {

	$c   = sm_form_content( 'order' );
	$set = isset( $c['verify_from_name'] ) ? trim( (string) $c['verify_from_name'] ) : '';

	if ( $set ) {
		return $set;
	}

	$site = wp_specialchars_decode( get_bloginfo( 'name' ), ENT_QUOTES );

	return $site ? $site : $name;
}
add_filter( 'wp_mail_from_name', 'sm_default_mail_from_name' );
