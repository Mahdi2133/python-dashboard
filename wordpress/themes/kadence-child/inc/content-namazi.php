<?php
/**
 * Content — Saeed Namazi profile page  ·  /saeednamazi/
 * ---------------------------------------------------------------------------
 *
 *  این صفحه عمداً کاملاً انگلیسی است. خودِ کارفرما خواسته و نشانیِ
 *  پیشنهادی‌اش هم در بالای فایلِ ورد نوشته شده بود:
 *
 *      Saadatmehracademy.com/saeednamazi
 *
 *  پس برخلافِ بقیه‌ی فایل‌های محتوا، متن‌های این فایل انگلیسی‌اند و
 *  صفحه با dir="ltr" رندر می‌شود. فقط همین یک صفحه.
 *
 *  ✏️ هر متنی اینجا عوض شود، بی‌درنگ در صفحه دیده می‌شود.
 *     هر فیلدی که خالی بماند، اصلاً چاپ نمی‌شود.
 *
 *  ⚠️ چند ادعا در این رزومه هست که سند می‌خواهد — «۲۵٬۰۰۰ ورزشکار»،
 *     «رکوردهای جهانی»، «پریدن از روی خودروی در حال حرکت». متن عیناً
 *     همان چیزی است که فرستادید و یک کلمه‌اش عوض نشده؛ ولی اگر روزی
 *     کسی سند خواست، بهتر است آماده باشد. برای برداشتنِ هر بند کافی
 *     است خطش را پاک کنید.
 *
 * @package saadatmehr
 */

defined( 'ABSPATH' ) || exit;

return array(

'namazi' => array(

	/* 🔑 false ⇒ صفحه ساخته می‌شود ولی محتوایش نمایش داده نمی‌شود. */
	'enabled' => true,

	/* ---------------------------------------------------------------
	   Hero
	   --------------------------------------------------------------- */
	'eyebrow'  => 'Saadatmehr Wellness Academy',
	'name'     => 'Saeed Namazi',
	'role'     => 'Expert in Individual Sports, International Coach, and World Champion',
	'tagline'  => 'Three Decades of Excellence in Championship and Coaching',
	'portrait' => 'resume/namazi-IMG_20.webp',

	/*
	 * عکسِ پرتره افقی است و ایشان سمتِ راستِ کادر ایستاده‌اند. این
	 * درصد می‌گوید کادر روی کدام قسمتِ عکس بیفتد (۰٪ چپ، ۱۰۰٪ راست).
	 */
	'portrait_focus' => '74%',

	/*
	 * شمارنده‌های بالای صفحه.
	 *
	 *   'value'  عددِ نهایی — فقط رقم. با جاوااسکریپت از صفر تا همین
	 *            عدد بالا می‌رود. بدون جاوااسکریپت هم خودِ عدد دیده
	 *            می‌شود، پس هیچ‌وقت صفر نمی‌ماند.
	 *   'suffix' چیزی که بعدِ عدد می‌آید (مثلاً + یا ٪).
	 */
	'stats' => array(
		array( 'value' => 32,    'suffix' => '',  'label' => 'Years in professional sport' ),
		array( 'value' => 22,    'suffix' => '',  'label' => 'Years of coaching' ),
		array( 'value' => 25000, 'suffix' => '+', 'label' => 'Athletes mentored' ),
		array( 'value' => 7,     'suffix' => '',  'label' => 'International credentials' ),
	),

	/* ---------------------------------------------------------------
	   Biography
	   --------------------------------------------------------------- */
	'bio' => array(
		'title' => 'A strategist in the world of elite sports',
		'text'  => array(
			'Saeed Namazi is more than just a champion; he is a strategist in the world of elite sports. With 32 years of professional experience and over two decades dedicated to cultivating champions, he bridges the gap between martial arts performance and modern exercise science.',
			'As the founder of the Nirooye Bartar Academy, he has mentored over 25,000 athletes, blending extensive field experience with academic rigor to develop unique, high-performance training methodologies.',
		),
		'image' => 'resume/namazi-875f87.webp',
	),

	/* ---------------------------------------------------------------
	   سه بلوکِ رزومه
	   -------------------------------------------------------------
	   هر بلوک یک 'title' دارد و چند مورد. هر مورد یک 'label' کوتاه
	   (پررنگ) و یک 'text' دارد. اگر 'label' خالی بماند، فقط متن
	   چاپ می‌شود.
	   --------------------------------------------------------------- */
	'blocks' => array(

		array(
			'key'   => 'honors',
			'title' => 'Honors & World Records',
			'items' => array(
				array(
					'label' => 'Grand Champion',
					'text'  => 'Awarded top honors in global Individual Martial Arts and performance competitions.',
				),
				array(
					'label' => 'International & National Titles',
					'text'  => 'Multiple gold-medal wins in prestigious international and domestic tournaments.',
				),
				array(
					'label' => 'World Records',
					'text'  => 'Renowned for high-stakes athletic stunts, including leaping over moving vehicles and navigating flaming obstacles.',
				),
			),
		),

		array(
			'key'   => 'coaching',
			'title' => 'Coaching & Education',
			'items' => array(
				array(
					'label' => 'Professional Coaching',
					'text'  => '22-year tenure with a track record of mentoring hundreds of national and international champions.',
				),
				array(
					'label' => 'Academic Standing',
					'text'  => 'Holds Level 3 & 4 certifications from the European Fitness Academy.',
				),
				array(
					'label' => 'International Credentials',
					'text'  => 'Holder of 7 official international coaching and judging certifications.',
				),
				array(
					'label' => 'Domestic Qualifications',
					'text'  => 'First-class coaching and refereeing credentials from official Iranian sports federations.',
				),
			),
		),

		array(
			'key'   => 'expertise',
			'title' => 'Specializations & Expertise',
			'items' => array(
				array(
					'label' => 'Training Systems',
					'text'  => 'Expert in modern bodybuilding, fitness, and functional movement correction.',
				),
				array(
					'label' => 'Stunt Performance',
					'text'  => 'Specialist in the design and execution of complex, high-risk athletic performances.',
				),
				array(
					'label' => 'Professional Consulting',
					'text'  => 'Expert guidance on nutrition, supplementation, and athletic periodization for all levels.',
				),
				array(
					'label' => 'Officiating',
					'text'  => 'Certified international judge for elite-level competitions.',
				),
			),
		),
	),

	/* ---------------------------------------------------------------
	   Gallery
	   -------------------------------------------------------------
	   با کلیک روی هر عکس، نسخه‌ی بزرگش در همان صفحه باز می‌شود
	   (همان لایت‌باکسی که در صفحه‌ی رسانه‌ها هم هست).
	   --------------------------------------------------------------- */
	'gallery' => array(
		'title' => 'In the field',
		'text'  => 'Click any photograph to enlarge.',
		'items' => array(
			array( 'file' => 'resume/namazi-IMG_20.webp',  'cap' => 'Saeed Namazi — Nirooye Bartar Academy' ),
			array( 'file' => 'resume/namazi-875f87.webp',  'cap' => 'Saeed Namazi — training floor' ),
			array( 'file' => 'resume/namazi-6293fb.webp',  'cap' => 'Saeed Namazi — conditioning session' ),
		),
	),

	/* ---------------------------------------------------------------
	   Closing
	   --------------------------------------------------------------- */
	'cta' => array(
		'title' => 'Part of the Saadatmehr Wellness Academy network',
		'text'  => 'Saeed Namazi works alongside the Academy on performance, movement correction and athletic periodization.',
		'label' => 'Back to the Academy',
		'link'  => '/',
	),
),

);
