<?php

declare(strict_types=1);

if (!defined('ABSPATH')) {
    exit;
}

final class Thesis_AI_Site_Setup {
    private const APPROVED_THEMES = [
        'hello-elementor' => 'Hello Elementor',
    ];

    /** Idempotent draft-only WooCommerce product scaffold; never creates a live offer. */
    public static function ensure_woocommerce_product_draft(array $input): array|WP_Error {
        if (!class_exists('WC_Product_Simple') || !function_exists('wc_get_product')) {
            return new WP_Error('thesis_ai_woocommerce_inactive', 'WooCommerce must be installed and active before creating product drafts.');
        }
        $name = sanitize_text_field((string)($input['name'] ?? ''));
        $description = sanitize_textarea_field((string)($input['description'] ?? ''));
        if ($name === '' || strlen($name) > 280 || strlen($description) > 1000) {
            return new WP_Error('thesis_ai_product_invalid', 'Product name or draft description is invalid.');
        }
        $slug = sanitize_title($name);
        if ($slug === '') {
            return new WP_Error('thesis_ai_product_slug', 'Product slug is empty.');
        }
        $existing = get_page_by_path($slug, OBJECT, 'product');
        $existing_id = $existing instanceof WP_Post ? (int)$existing->ID : 0;
        if ($existing_id && get_post_meta($existing_id, '_thesis_ai_generated', true) !== '1') {
            return new WP_Error('thesis_ai_product_collision', 'A non-AI-owned product already uses this slug. The system will not overwrite it.');
        }
        if ($existing_id && $existing->post_status !== 'draft') {
            // Published and non-draft products must never be changed by this ability.
            return new WP_Error('thesis_ai_product_not_draft', 'Existing product is not a draft; automatic edits are blocked.');
        }
        if ($existing_id) {
            // Preserve manual edits on an existing AI-owned draft.
            return ['product_id' => $existing_id, 'product_slug' => $slug,
                'status' => 'draft', 'changed' => false, 'reused' => true,
                'requires_review' => ['price', 'ingredients', 'allergens', 'images', 'availability']];
        }
        $product = new WC_Product_Simple();
        if (!$product instanceof WC_Product) {
            return new WP_Error('thesis_ai_product_type', 'Existing AI-owned product cannot be opened as a WooCommerce product.');
        }
        $product->set_name($name);
        $product->set_slug($slug);
        $product->set_status('draft');
        $product->set_description($description);
        $product->set_short_description('');
        // Never invent a price, discount, stock level, category, image or checkout configuration.
        $product_id = $product->save();
        if (!$product_id) {
            return new WP_Error('thesis_ai_product_save', 'WooCommerce could not save the product draft.');
        }
        update_post_meta((int)$product_id, '_thesis_ai_generated', '1');
        return [
            'product_id' => (int)$product_id,
            'product_slug' => $slug,
            'status' => (string)get_post_status((int)$product_id),
            'changed' => !$existing_id,
            'requires_review' => ['price', 'description', 'ingredients', 'allergens', 'images', 'availability'],
        ];
    }

    public static function approved_themes(): array {
        return self::APPROVED_THEMES;
    }

    public static function list_themes(): array {
        $themes = wp_get_themes();
        $active = get_stylesheet();
        $result = [];
        foreach ($themes as $slug => $theme) {
            $result[] = [
                'slug' => (string)$slug,
                'name' => (string)$theme->get('Name'),
                'version' => (string)$theme->get('Version'),
                'active' => (string)$slug === (string)$active,
                'approved' => isset(self::APPROVED_THEMES[(string)$slug]),
            ];
        }
        return $result;
    }

    public static function ensure_approved_theme(array $input): array|WP_Error {
        $slug = sanitize_key((string)($input['theme_slug'] ?? ''));
        if (!isset(self::APPROVED_THEMES[$slug])) {
            return new WP_Error('thesis_ai_theme_not_approved', __('Theme is not in the approved catalogue.', 'thesis-ai-bridge'));
        }
        $installed = wp_get_theme($slug)->exists();
        $installed_now = false;
        if (!$installed) {
            require_once ABSPATH . 'wp-admin/includes/theme.php';
            require_once ABSPATH . 'wp-admin/includes/class-wp-upgrader.php';
            require_once ABSPATH . 'wp-admin/includes/file.php';
            if (get_filesystem_method() !== 'direct') {
                return new WP_Error('thesis_ai_theme_filesystem', __('Automatic theme installation requires direct WordPress filesystem access.', 'thesis-ai-bridge'));
            }
            if (!WP_Filesystem()) {
                return new WP_Error('thesis_ai_theme_filesystem_init', __('Could not initialize the WordPress filesystem.', 'thesis-ai-bridge'));
            }
            $api = themes_api('theme_information', ['slug' => $slug, 'fields' => ['sections' => false, 'description' => false]]);
            if (is_wp_error($api)) {
                return $api;
            }
            $package = (string)($api->download_link ?? '');
            if ($package === '' || !str_starts_with($package, 'https://downloads.wordpress.org/')) {
                return new WP_Error('thesis_ai_theme_source', __('Theme package is not from the approved WordPress.org source.', 'thesis-ai-bridge'));
            }
            $upgrader = new Theme_Upgrader(new Automatic_Upgrader_Skin());
            $installed_result = $upgrader->install($package);
            if (is_wp_error($installed_result)) {
                return $installed_result;
            }
            if (!$installed_result) {
                return new WP_Error('thesis_ai_theme_install_failed', __('Theme installation failed.', 'thesis-ai-bridge'));
            }
            $installed_now = true;
        }
        $activated_now = get_stylesheet() !== $slug;
        if ($activated_now) {
            switch_theme($slug);
        }
        return [
            'theme_slug' => $slug,
            'installed' => true,
            'active' => get_stylesheet() === $slug,
            'changed' => $installed_now || $activated_now,
            'message' => $installed_now ? 'Theme installed and activated.' : ($activated_now ? 'Theme activated.' : 'Theme already installed and active.'),
        ];
    }

    public static function update_site_identity(array $input): array|WP_Error {
        $title = sanitize_text_field((string)($input['site_title'] ?? ''));
        $tagline = sanitize_text_field((string)($input['tagline'] ?? ''));
        if ($title === '') {
            return new WP_Error('thesis_ai_site_title_missing', __('Site title is required.', 'thesis-ai-bridge'));
        }
        update_option('blogname', $title);
        update_option('blogdescription', $tagline);
        return ['site_title' => (string)get_option('blogname'), 'tagline' => (string)get_option('blogdescription')];
    }

    public static function set_homepage_by_slug(array $input): array|WP_Error {
        $slug = sanitize_title((string)($input['slug'] ?? ''));
        $page = $slug !== '' ? get_page_by_path($slug, OBJECT, 'page') : null;
        if (!$page instanceof WP_Post) {
            return new WP_Error('thesis_ai_homepage_missing', __('Homepage page could not be found by slug.', 'thesis-ai-bridge'));
        }
        update_option('show_on_front', 'page');
        update_option('page_on_front', (int)$page->ID);
        return ['homepage_id' => (int)$page->ID, 'homepage_slug' => (string)$page->post_name, 'show_on_front' => 'page', 'public_visibility' => $page->post_status === 'publish' ? 'public' : 'draft_not_public', 'note' => $page->post_status === 'publish' ? '' : 'This homepage is a draft; the public homepage will not display it until approved and published.'];
    }

    public static function ensure_navigation_menu(array $input): array|WP_Error {
        $menu_name = sanitize_text_field((string)($input['menu_name'] ?? 'AI Primary')) ?: 'AI Primary';
        $page_slugs = array_values(array_filter(array_map('sanitize_title', (array)($input['page_slugs'] ?? []))));
        if (!$page_slugs) {
            return new WP_Error('thesis_ai_menu_empty', __('At least one page slug is required.', 'thesis-ai-bridge'));
        }
        $menu = wp_get_nav_menu_object($menu_name);
        $menu_id = $menu ? (int)$menu->term_id : (int)wp_create_nav_menu($menu_name);
        if (is_wp_error($menu_id)) {
            return $menu_id;
        }

        foreach (wp_get_nav_menu_items($menu_id) ?: [] as $item) {
            wp_delete_post((int)$item->ID, true);
        }
        $added = [];
        foreach ($page_slugs as $slug) {
            $page = get_page_by_path($slug, OBJECT, 'page');
            if (!$page instanceof WP_Post) {
                continue;
            }
            $item_id = wp_update_nav_menu_item($menu_id, 0, [
                'menu-item-object-id' => (int)$page->ID,
                'menu-item-object' => 'page',
                'menu-item-type' => 'post_type',
                'menu-item-status' => 'publish',
                'menu-item-title' => (string)get_the_title($page),
            ]);
            if (!is_wp_error($item_id)) {
                $added[] = $slug;
            }
        }

        $assigned = false;
        $location_used = '';
        if (!empty($input['assign_primary'])) {
            $registered = get_registered_nav_menus();
            $locations = get_theme_mod('nav_menu_locations', []);
            foreach (['primary', 'menu-1', 'main-menu', 'header'] as $candidate) {
                if (isset($registered[$candidate])) {
                    $locations[$candidate] = $menu_id;
                    set_theme_mod('nav_menu_locations', $locations);
                    $assigned = true;
                    $location_used = $candidate;
                    break;
                }
            }
        }
        return ['menu_id' => $menu_id, 'menu_name' => $menu_name, 'page_slugs' => $added, 'assigned' => $assigned, 'location' => $location_used];
    }

    public static function set_page_seo(array $input): array|WP_Error {
        $slug = sanitize_title((string)($input['slug'] ?? ''));
        $page = $slug !== '' ? get_page_by_path($slug, OBJECT, 'page') : null;
        if (!$page instanceof WP_Post) {
            return new WP_Error('thesis_ai_seo_page_missing', __('SEO target page not found.', 'thesis-ai-bridge'));
        }
        $title = sanitize_text_field((string)($input['seo_title'] ?? ''));
        $description = sanitize_textarea_field((string)($input['meta_description'] ?? ''));
        update_post_meta((int)$page->ID, '_thesis_ai_seo_title', $title);
        update_post_meta((int)$page->ID, '_thesis_ai_meta_description', $description);
        wp_update_post(['ID' => (int)$page->ID, 'post_excerpt' => $description]);

        if (defined('WPSEO_VERSION')) {
            update_post_meta((int)$page->ID, '_yoast_wpseo_title', $title);
            update_post_meta((int)$page->ID, '_yoast_wpseo_metadesc', $description);
        }
        if (defined('RANK_MATH_VERSION')) {
            update_post_meta((int)$page->ID, 'rank_math_title', $title);
            update_post_meta((int)$page->ID, 'rank_math_description', $description);
        }
        return ['page_id' => (int)$page->ID, 'slug' => $slug, 'seo_title' => $title, 'meta_description' => $description];
    }

    public static function ensure_contact_form(array $input): array|WP_Error {
        if (!function_exists('wpcf7_save_contact_form')) {
            return new WP_Error('thesis_ai_cf7_unavailable', __('Contact Form 7 is not active.', 'thesis-ai-bridge'));
        }
        $title = sanitize_text_field((string)($input['title'] ?? 'AI Contact')) ?: 'AI Contact';
        $existing = function_exists('wpcf7_get_contact_form_by_title') ? wpcf7_get_contact_form_by_title($title) : null;
        if ($existing) {
            return ['id' => (int)$existing->id(), 'title' => $title, 'shortcode' => (string)$existing->shortcode(), 'created' => false];
        }
        $site_domain = wp_parse_url(home_url('/'), PHP_URL_HOST) ?: 'example.com';
        $form = "<label>Ім’я\n[text* your-name autocomplete:name]</label>\n<label>Email\n[email* your-email autocomplete:email]</label>\n<label>Телефон\n[tel your-phone]</label>\n<label>Повідомлення\n[textarea your-message]</label>\n[submit \"Надіслати\"]";
        $mail = [
            'active' => true,
            'subject' => '[' . get_bloginfo('name') . '] Нова заявка',
            'sender' => get_bloginfo('name') . ' <wordpress@' . $site_domain . '>',
            'recipient' => (string)get_option('admin_email'),
            'body' => "Ім’я: [your-name]\nEmail: [your-email]\nТелефон: [your-phone]\n\n[your-message]",
            'additional_headers' => 'Reply-To: [your-email]',
            'attachments' => '',
            'use_html' => false,
            'exclude_blank' => false,
        ];
        $created = wpcf7_save_contact_form(['id' => -1, 'title' => $title, 'form' => $form, 'mail' => $mail], 'save');
        if (!$created || !is_object($created)) {
            return new WP_Error('thesis_ai_cf7_create_failed', __('Could not create Contact Form 7 form.', 'thesis-ai-bridge'));
        }
        return ['id' => (int)$created->id(), 'title' => $title, 'shortcode' => (string)$created->shortcode(), 'created' => true];
    }


    public static function configure_woocommerce(array $input): array|WP_Error {
        if (!current_user_can('manage_options')) {
            return new WP_Error('thesis_ai_woo_forbidden', __('Administrator permissions are required to configure WooCommerce.', 'thesis-ai-bridge'));
        }
        if (!class_exists('WooCommerce') && !defined('WC_VERSION')) {
            return new WP_Error('thesis_ai_woo_unavailable', __('WooCommerce is not active.', 'thesis-ai-bridge'));
        }
        $currency = strtoupper(sanitize_text_field((string)($input['currency'] ?? 'USD')));
        if (!preg_match('/^[A-Z]{3}$/', $currency)) {
            $currency = 'USD';
        }
        update_option('woocommerce_currency', $currency);

        if (class_exists('WC_Install') && method_exists('WC_Install', 'create_pages')) {
            WC_Install::create_pages();
        }
        $page_keys = ['shop', 'cart', 'checkout', 'myaccount'];
        $pages = [];
        foreach ($page_keys as $key) {
            $id = function_exists('wc_get_page_id') ? (int)wc_get_page_id($key) : (int)get_option('woocommerce_' . $key . '_page_id', 0);
            if ($id > 0) {
                $pages[$key] = ['id' => $id, 'title' => (string)get_the_title($id), 'url' => (string)get_permalink($id)];
            }
        }
        return [
            'configured' => true,
            'currency' => (string)get_option('woocommerce_currency', $currency),
            'pages' => $pages,
        ];
    }

    public static function get_site_structure(): array {
        $homepage_id = (int)get_option('page_on_front', 0);
        $homepage = $homepage_id ? get_post($homepage_id) : null;
        $menus = [];
        foreach (wp_get_nav_menus() as $menu) {
            $menus[] = ['id' => (int)$menu->term_id, 'name' => (string)$menu->name, 'count' => (int)$menu->count];
        }
        return [
            'site_title' => (string)get_option('blogname'),
            'tagline' => (string)get_option('blogdescription'),
            'homepage_id' => $homepage_id,
            'homepage_slug' => $homepage instanceof WP_Post ? (string)$homepage->post_name : '',
            'show_on_front' => (string)get_option('show_on_front'),
            'menus' => $menus,
            'menu_locations' => get_theme_mod('nav_menu_locations', []),
            'active_theme_slug' => (string)get_stylesheet(),
        ];
    }
}
