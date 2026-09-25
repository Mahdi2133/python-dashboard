<?php
/**
 * Template Name: صفحه ثبت سفارش
 *
 * نشانی: /order/
 * متن‌ها و پرسش‌ها در inc/content-forms.php کلید 'order' هستند.
 *
 * این صفحه سه حالت دارد و هر بار فقط یکی دیده می‌شود:
 *
 *   ۱. فرم        — حالت پیش‌فرض
 *   ۲. تأیید کد   — ?sm=verify   (کدی که به ایمیل خریدار رفته است)
 *   ۳. پیش‌فاکتور  — ?sm=inv     به‌همراه پاپ‌آپ هماهنگی پرداخت
 *
 * @package saadatmehr
 */

defined( 'ABSPATH' ) || exit;

$c = sm_form_content( 'order' );

$state = isset( $_GET['sm'] ) ? sanitize_key( wp_unslash( $_GET['sm'] ) ) : '';
$inv   = isset( $_GET['inv'] ) ? absint( wp_unslash( $_GET['inv'] ) ) : 0;
$token = isset( $_GET['t'] ) ? sanitize_text_field( wp_unslash( $_GET['t'] ) ) : '';
$vmsg  = isset( $_GET['e'] ) ? sanitize_key( wp_unslash( $_GET['e'] ) ) : '';

// هیچ سفارشی بدون نشانه‌ی درست نمایش داده نمی‌شود
$valid = sm_order_token_ok( $inv, $token );

$show_invoice = ( 'inv' === $state && $valid );
$show_verify  = ( 'verify' === $state && $valid );
$error        = ( 'err' === $state );

$products = array_values(
	array_filter(
		$c['products'],
		static function ( $p ) {
			return ! empty( $p['enabled'] );
		}
	)
);

get_header();
?>

<main id="main" class="sm-page sm-page--order" role="main">

	<section class="sm-phead sm-phead--compact" aria-labelledby="sm-order-title">
		<div class="sm-phead__bg" aria-hidden="true">
			<img src="<?php echo esc_url( sm_img( 'logo-seal.png' ) ); ?>" alt="" class="sm-phead__seal" loading="eager" decoding="async">
		</div>
		<div class="sm-wrap sm-phead__inner">
			<p class="sm-phead__eyebrow"><?php echo esc_html( $c['eyebrow'] ); ?></p>
			<h1 id="sm-order-title" class="sm-phead__title">
				<?php echo esc_html( $show_verify ? $c['verify_title'] : $c['title'] ); ?>
			</h1>
			<?php if ( ! $show_verify && ! $show_invoice ) : ?>
				<?php foreach ( $c['lead'] as $t ) : ?>
					<p class="sm-phead__lead"><?php echo esc_html( $t ); ?></p>
				<?php endforeach; ?>
			<?php endif; ?>
		</div>
	</section>

	<section id="sm-form" class="sm-section sm-formsection">
		<div class="sm-wrap sm-form__col">

		<?php if ( $show_verify ) : ?>

			<?php /* ============ حالت ۲ — تأیید کد ============ */ ?>
			<?php
			/*
			 * نشانیِ ایمیل نیمه‌پوشیده نشان داده می‌شود.
			 * کامل نشان نمی‌دهیم چون این صفحه با یک لینکِ حاوی
			 * نشانه باز می‌شود و ممکن است لینک جایی فوروارد شود.
			 */
			$mailto = (string) get_post_meta( $inv, '_sm_oemail', true );
			$mask   = '';

			if ( $mailto && false !== strpos( $mailto, '@' ) ) {
				list( $local, $domain ) = explode( '@', $mailto, 2 );
				$keep = ( strlen( $local ) > 2 ) ? 2 : 1;
				$mask = substr( $local, 0, $keep ) . '•••@' . $domain;
			}

			$msgs = array(
				'wrong'    => array( $c['verify_wrong'], 'error' ),
				'expired'  => array( $c['verify_expired'], 'error' ),
				'locked'   => array( $c['verify_locked'], 'error' ),
				'mailfail' => array( $c['verify_failed'], 'error' ),
				'sent'     => array( $c['verify_sent'], 'ok' ),
			);
			?>

			<?php if ( isset( $msgs[ $vmsg ] ) ) : ?>
				<p class="<?php echo 'ok' === $msgs[ $vmsg ][1] ? 'sm-warnbox' : 'sm-formerror'; ?>" role="alert">
					<?php echo esc_html( $msgs[ $vmsg ][0] ); ?>
				</p>
			<?php endif; ?>

			<p class="sm-verify__text"><?php echo esc_html( $c['verify_text'] ); ?></p>

			<?php if ( $mask ) : ?>
				<p class="sm-verify__phone" dir="ltr"><?php echo esc_html( $mask ); ?></p>
			<?php endif; ?>

			<?php if ( ! empty( $c['verify_sign'] ) ) : ?>
				<p class="sm-verify__sign"><?php echo esc_html( $c['verify_sign'] ); ?></p>
			<?php endif; ?>

			<form class="sm-verifyform" method="post" action="<?php echo esc_url( home_url( add_query_arg( array() ) ) ); ?>">
				<input type="hidden" name="sm_verify_form" value="1">
				<input type="hidden" name="sm_inv" value="<?php echo (int) $inv; ?>">
				<input type="hidden" name="sm_token" value="<?php echo esc_attr( $token ); ?>">
				<?php wp_nonce_field( 'sm_order_verify', 'sm_verify_nonce' ); ?>

				<div class="sm-field">
					<label class="sm-field__label" for="sm_code"><?php echo esc_html( $c['verify_label'] ); ?></label>
					<input class="sm-codeinput" type="text" id="sm_code" name="sm_code"
					       inputmode="numeric" autocomplete="one-time-code" maxlength="5"
					       dir="ltr" required autofocus>
				</div>

				<div class="sm-form__actions">
					<button type="submit" class="sm-btn sm-btn--gold"><?php echo esc_html( $c['verify_submit'] ); ?></button>
					<button type="submit" name="sm_resend" value="1" class="sm-btn sm-btn--ghost"><?php echo esc_html( $c['verify_resend'] ); ?></button>
				</div>

				<p class="sm-form__note"><?php echo esc_html( $c['verify_note'] ); ?></p>

				<?php
				/*
				 * راهِ فرار.
				 *
				 * عمداً فقط بعد از یک دورِ تلاش دیده می‌شود — یعنی وقتی
				 * خریدار یک بار «کد را دوباره بفرست» زده یا ارسالِ ایمیل
				 * شکست خورده. اگر از همان اول نشان داده می‌شد، خیلی‌ها
				 * راهِ آسان را می‌زدند و امضای الکترونیکی از بین می‌رفت.
				 *
				 * ولی باید وجود داشته باشد: اگر ایمیلِ هاست خراب باشد،
				 * بدونِ این دکمه خریدار اصلاً نمی‌تواند خرید را تمام کند.
				 */
				$mail_ok  = get_post_meta( $inv, '_sm_mail_ok', true );
				$tried    = (int) get_post_meta( $inv, '_sm_mail_tries', true );
				$show_esc = ( $tried > 0 )
					|| in_array( $vmsg, array( 'sent', 'mailfail', 'expired' ), true )
					|| ( 'no' === $mail_ok );
				?>
				<?php if ( $show_esc && ! empty( $c['skip_label'] ) ) : ?>
					<div class="sm-verify__escape">
						<p class="sm-verify__escape-help"><?php echo esc_html( $c['skip_help'] ); ?></p>
						<button type="submit" name="sm_skip" value="1" class="sm-verify__escape-btn">
							<?php echo esc_html( $c['skip_label'] ); ?>
						</button>
					</div>
				<?php endif; ?>
			</form>

		<?php elseif ( $show_invoice ) : ?>

			<?php /* ============ حالت ۳ — پیش‌فاکتور ============ */ ?>
			<?php
			$order   = get_post( $inv );
			$invoice = (string) get_post_meta( $inv, '_sm_invoice', true );
			$total   = sm_format_price( get_post_meta( $inv, '_sm_price', true ) );
			?>

			<?php if ( 'mailfail' === $vmsg && ! empty( $c['verify_failed'] ) ) : ?>
				<p class="sm-formerror" role="alert"><?php echo esc_html( $c['verify_failed'] ); ?></p>
			<?php elseif ( 'skipped' === $vmsg && ! empty( $c['skip_done'] ) ) : ?>
				<p class="sm-formerror" role="alert"><?php echo esc_html( $c['skip_done'] ); ?></p>
			<?php endif; ?>

			<div class="sm-done" role="status">
				<span class="sm-done__mark" aria-hidden="true">
					<svg viewBox="0 0 48 48" width="48" height="48" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
						<circle cx="24" cy="24" r="21"/><path d="m14 25 7 7 14-15"/>
					</svg>
				</span>
				<h2 class="sm-done__title"><?php echo esc_html( $c['invoice_title'] ); ?></h2>
			</div>

			<div class="sm-invoice">
				<div class="sm-invoice__head">
					<span class="sm-invoice__no">
						<?php echo esc_html( $c['invoice_no'] ); ?>:
						<strong dir="ltr"><?php echo esc_html( $invoice ); ?></strong>
					</span>
					<span class="sm-invoice__date">
						<?php
						// تاریخ شمسی، چون کنارش تاریخِ امضا هم شمسی است و
						// دو تاریخِ ناهمخوان روی یک سند بد است.
						echo esc_html( $c['invoice_date'] . ': ' . sm_jalali_datetime( get_post_time( 'U', true, $order ), false ) );
						?>
					</span>
				</div>

				<div class="sm-invoice__body">
					<table>
						<tbody>
							<tr>
								<th>خدمت</th>
								<td><?php echo esc_html( get_post_meta( $inv, '_sm_product', true ) ); ?></td>
							</tr>
							<?php foreach ( array_merge( $c['fields'], $c['ship_fields'] ) as $f ) : ?>
								<?php $val = get_post_meta( $inv, '_sm_' . $f['name'], true ); ?>
								<?php if ( '' === trim( (string) $val ) ) { continue; } ?>
								<tr>
									<th><?php echo esc_html( $f['label'] ); ?></th>
									<td><?php echo esc_html( $val ); ?></td>
								</tr>
							<?php endforeach; ?>
							<?php
							/*
							 * ردِ امضای الکترونیکی روی خودِ پیش‌فاکتور.
							 * خریدار باید ببیند چه چیزی و کی امضا شده،
							 * نه اینکه فقط در پیشخوانِ ما ثبت شده باشد.
							 */
							$signed_at = (int) get_post_meta( $inv, '_sm_signed_at', true );
							?>
							<?php if ( $signed_at ) : ?>
								<tr>
									<th>پذیرش قوانین</th>
									<td><?php echo esc_html( 'امضای الکترونیکی — ' . sm_jalali_datetime( $signed_at ) ); ?></td>
								</tr>
							<?php endif; ?>
							<tr class="sm-invoice__total">
								<th>مبلغ</th>
								<td><?php echo esc_html( $total ? $total : $c['price_ask'] ); ?></td>
							</tr>
						</tbody>
					</table>

					<div class="sm-form__actions">
						<?php if ( ! empty( $c['gateway_url'] ) ) : ?>
							<a class="sm-btn sm-btn--gold" href="<?php echo esc_url( $c['gateway_url'] ); ?>">
								<?php echo esc_html( $c['pay_label'] ); ?>
							</a>
						<?php else : ?>
							<button type="button" class="sm-btn sm-btn--gold" data-sm-paysheet="open">
								<?php echo esc_html( $c['pay_open'] ); ?>
							</button>
						<?php endif; ?>
					</div>

					<?php foreach ( $c['invoice_note'] as $t ) : ?>
						<p class="sm-form__note"><?php echo esc_html( $t ); ?></p>
					<?php endforeach; ?>
				</div>
			</div>

			<?php
			if ( empty( $c['gateway_url'] ) ) {
				sm_render_paysheet( $c, $invoice, $total );
			}
			?>

		<?php elseif ( empty( $products ) ) : ?>

			<p class="sm-warnbox"><?php echo esc_html( $c['empty_products'] ); ?></p>

		<?php else : ?>

			<?php /* ============ حالت ۱ — فرم ============ */ ?>
			<?php if ( $error ) : ?>
				<p class="sm-formerror" role="alert"><?php echo esc_html( $c['error_text'] ); ?></p>
			<?php endif; ?>

			<form class="sm-orderform" method="post" action="<?php echo esc_url( home_url( add_query_arg( array() ) ) ); ?>" novalidate>

				<input type="hidden" name="sm_order_form" value="1">
				<?php wp_nonce_field( 'sm_order_submit', 'sm_order_nonce' ); ?>

				<div class="sm-hp" aria-hidden="true">
					<label for="sm_website_o">این فیلد را خالی بگذارید</label>
					<input type="text" id="sm_website_o" name="sm_website" tabindex="-1" autocomplete="off">
				</div>

				<fieldset class="sm-fieldset">
					<legend class="sm-fieldset__legend">
						<span class="sm-fieldset__num">۱</span>
						انتخاب خدمت
					</legend>

					<?php foreach ( $products as $n => $p ) : ?>
						<?php $price = sm_format_price( $p['price'] ); ?>
						<label class="sm-check sm-check--radio sm-plan">
							<input type="radio" name="sm_product" value="<?php echo esc_attr( $p['key'] ); ?>" <?php echo 0 === $n ? 'required' : ''; ?>>
							<span class="sm-plan__body">
								<span class="sm-plan__name"><?php echo esc_html( $p['label'] ); ?></span>
								<?php if ( ! empty( $p['note'] ) ) : ?>
									<span class="sm-plan__note"><?php echo esc_html( $p['note'] ); ?></span>
								<?php endif; ?>
								<span class="sm-plan__price"><?php echo esc_html( $price ? $price : $c['price_ask'] ); ?></span>
							</span>
						</label>
					<?php endforeach; ?>
				</fieldset>

				<fieldset class="sm-fieldset">
					<legend class="sm-fieldset__legend">
						<span class="sm-fieldset__num">۲</span>
						اطلاعات خریدار
					</legend>
					<?php foreach ( $c['fields'] as $f ) : ?>
						<?php sm_form_field( $f ); ?>
					<?php endforeach; ?>
				</fieldset>

				<?php
				$has_physical = false;
				foreach ( $products as $p ) {
					if ( ! empty( $p['physical'] ) ) {
						$has_physical = true;
						break;
					}
				}
				?>
				<?php if ( $has_physical ) : ?>
					<fieldset class="sm-fieldset">
						<legend class="sm-fieldset__legend">
							<span class="sm-fieldset__num">۳</span>
							نشانی ارسال
						</legend>
						<p class="sm-field__help">فقط برای محصول فیزیکی لازم است.</p>
						<?php foreach ( $c['ship_fields'] as $f ) : ?>
							<?php sm_form_field( $f ); ?>
						<?php endforeach; ?>
					</fieldset>
				<?php endif; ?>

				<div class="sm-field sm-field--consent">
					<label class="sm-check">
						<input type="checkbox" name="sm_consent" value="1" required>
						<span>
							<?php echo esc_html( $c['consent'] ); ?>
							<a href="<?php echo esc_url( home_url( $c['terms_link'] ) ); ?>" target="_blank" rel="noopener">
								<?php echo esc_html( $c['terms_label'] ); ?>
							</a>
						</span>
					</label>
				</div>

				<div class="sm-form__actions">
					<button type="submit" class="sm-btn sm-btn--gold"><?php echo esc_html( $c['submit'] ); ?></button>
				</div>

				<p class="sm-form__note"><?php echo esc_html( $c['disclaimer'] ); ?></p>

			</form>

		<?php endif; ?>

		</div>
	</section>

</main>

<?php
get_footer();
