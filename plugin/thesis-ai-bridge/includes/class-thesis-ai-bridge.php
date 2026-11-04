<?php

declare(strict_types=1);

if (!defined('ABSPATH')) {
    exit;
}

final class Thesis_AI_Bridge {
    private const CATEGORY = 'thesis-ai';
    private const OPTION_SETTINGS = 'thesis_ai_bridge_settings';
    private const OPTION_AUDIT = 'thesis_ai_bridge_audit_log';
    private const OPTION_DATA_MODELS = 'thesis_ai_bridge_data_models';
    private const OPTION_SITE_DESIGN = 'thesis_ai_bridge_site_design';
    private const ROLE = 'thesis_ai_builder';
    private const CAP_USE = 'thesis_ai_use_bridge';

    private const APPROVED_PLUGINS = [
        'elementor' => 'Elementor Website Builder',
        'woocommerce' => 'WooCommerce',
        'advanced-custom-fields' => 'Advanced Custom Fields',
        'contact-form-7' => 'Contact Form 7',
        'wordpress-seo' => 'Yoast SEO',
        'seo-by-rank-math' => 'Rank Math SEO',
    ];

    public static function init(): void {
        add_action('init', [self::class, 'ensure_role']);
        add_action('init', [self::class, 'ensure_admin_capability']);
        add_action('init', [self::class, 'register_dynamic_content_types'], 20);
        add_action('acf/init', [self::class, 'register_dynamic_acf_fields']);
        add_action('rest_api_init', [self::class, 'register_fallback_rest_routes']);
        // Lightweight SEO fallback for sites without a dedicated supported SEO plugin.
        // If Yoast or Rank Math is active, their own output takes precedence.
        add_filter('document_title_parts', [self::class, 'filter_document_title_parts']);
        add_action('wp_head', [self::class, 'output_meta_description'], 1);
        add_action('wp_head', [self::class, 'output_site_design_styles'], 30);
        add_action('wp_enqueue_scripts', [self::class, 'enqueue_visual_styles']);
        add_filter('body_class', [self::class, 'visual_body_class']);
        add_action('woocommerce_no_products_found', [self::class, 'output_demo_shop_preview'], 5);

        // These hooks exist only when the native Abilities API is available (WordPress 6.9+).
        add_action('wp_abilities_api_categories_init', [self::class, 'register_category']);
        add_action('wp_abilities_api_init', [self::class, 'register_abilities']);
    }

    private static function supported_seo_plugin_active(): bool {
        return defined('WPSEO_VERSION') || defined('RANK_MATH_VERSION');
    }

    public static function filter_document_title_parts(array $parts): array {
        if (self::supported_seo_plugin_active() || !is_singular('page')) {
            return $parts;
        }
        $post_id = get_queried_object_id();
        $title = $post_id ? trim((string)get_post_meta($post_id, '_thesis_ai_seo_title', true)) : '';
        if ($title !== '') {
            // A generated SEO title is already complete, so use it as the document title.
            return ['title' => $title];
        }
        return $parts;
    }

    public static function output_meta_description(): void {
        if (self::supported_seo_plugin_active() || !is_singular('page')) {
            return;
        }
        $post_id = get_queried_object_id();
        $description = $post_id ? trim((string)get_post_meta($post_id, '_thesis_ai_meta_description', true)) : '';
        if ($description !== '') {
            echo '<meta name="description" content="' . esc_attr($description) . '">' . "\n";
        }
    }


    public static function output_site_design_styles(): void {
        $design = get_option(self::OPTION_SITE_DESIGN, []);
        if (!is_array($design) || empty($design['primary'])) {
            return;
        }
        $primary = sanitize_hex_color((string)($design['primary'] ?? '')) ?: '#1D4ED8';
        $accent = sanitize_hex_color((string)($design['accent'] ?? '')) ?: '#0EA5E9';
        $background = sanitize_hex_color((string)($design['background'] ?? '')) ?: '#FFFFFF';
        $surface = sanitize_hex_color((string)($design['surface'] ?? '')) ?: '#F8FAFC';
        $text = sanitize_hex_color((string)($design['text'] ?? '')) ?: '#0F172A';
        $muted = sanitize_hex_color((string)($design['muted'] ?? '')) ?: '#475569';
        $radius = max(0, min(40, absint($design['radius'] ?? 18)));
        $heading_font = trim(preg_replace('/[^a-zA-Z0-9 ,\-]/', '', (string)($design['heading_font'] ?? 'Inter')) ?: 'Inter');
        $body_font = trim(preg_replace('/[^a-zA-Z0-9 ,\-]/', '', (string)($design['body_font'] ?? 'Inter')) ?: 'Inter');
        echo "<style id=\"thesis-ai-site-design\">\n";
        echo ':root{--tai-primary:' . esc_html($primary) . ';--tai-accent:' . esc_html($accent) . ';--tai-bg:' . esc_html($background) . ';--tai-surface:' . esc_html($surface) . ';--tai-text:' . esc_html($text) . ';--tai-muted:' . esc_html($muted) . ';--tai-radius:' . esc_html((string)$radius) . 'px;}';
        echo 'body.thesis-ai-generated,body.woocommerce-shop{background:var(--tai-bg);color:var(--tai-text);font-family:' . esc_html($body_font) . ',system-ui,sans-serif;}';
        echo 'body.thesis-ai-generated :is(h1,h2,h3,h4,h5,h6,.site-title),body.woocommerce-shop :is(h1,h2,h3,h4,h5,h6,.site-title){font-family:' . esc_html($heading_font) . ',system-ui,sans-serif;}';
        echo 'body.thesis-ai-generated a,body.woocommerce-shop a{color:var(--tai-primary);}';
        echo 'body.thesis-ai-generated :is(.site-header,.header-inner),body.woocommerce-shop :is(.site-header,.header-inner){background:var(--tai-bg);border-bottom:1px solid color-mix(in srgb,var(--tai-text) 12%,transparent);}';
        echo 'body.thesis-ai-generated :is(.site-title a,.site-branding .site-title a),body.woocommerce-shop :is(.site-title a,.site-branding .site-title a){color:var(--tai-primary)!important;}';
        echo 'body.thesis-ai-generated :is(.site-navigation a,.primary-menu a,.menu-item a),body.woocommerce-shop :is(.site-navigation a,.primary-menu a,.menu-item a){color:var(--tai-text);}';
        echo 'body.thesis-ai-generated :is(.site-navigation a:hover,.primary-menu a:hover,.menu-item a:hover),body.woocommerce-shop :is(.site-navigation a:hover,.primary-menu a:hover,.menu-item a:hover){color:var(--tai-primary);}';
        echo 'body.thesis-ai-generated .elementor-button{border-radius:var(--tai-radius)!important;}';
        echo "</style>\n";
    }

    /** Remove theme box constraints only from pages owned by the builder. */
    public static function visual_body_class(array $classes): array {
        if (is_singular('page')) {
            $id = get_queried_object_id();
            if ($id && get_post_meta($id, '_thesis_ai_generated', true) === '1') {
                $classes[] = 'thesis-ai-generated';
            }
        }
        return $classes;
    }

    /** Scoped visual styling for AI-created Elementor pages and WooCommerce archive. */
    public static function enqueue_visual_styles(): void {
        $design = get_option(self::OPTION_SITE_DESIGN, []);
        // Layout-safety CSS must work even if apply-site-design failed.
        // Scope all page rules to AI-created pages and WooCommerce's shop.
        if (!is_singular('page') && (!function_exists('is_shop') || !is_shop())) {
            return;
        }
        if (is_singular('page') && (string)get_post_meta(get_queried_object_id(), '_thesis_ai_generated', true) !== '1'
            && (!function_exists('is_shop') || !is_shop())) {
            return;
        }
        wp_enqueue_style(
            'thesis-ai-premium-visuals',
            plugins_url('assets/front.css', THESIS_AI_BRIDGE_FILE),
            [], THESIS_AI_BRIDGE_VERSION
        );
    }

    /**
     * Logged-in admin preview of AI draft products on an otherwise empty Shop archive.
     * Customers never see draft names, invented prices, or add-to-cart actions.
     */
    public static function output_demo_shop_preview(): void {
        if (!function_exists('is_shop') || !is_shop() || !current_user_can('edit_products')) {
            return;
        }
        $ids = get_posts([
            'post_type' => 'product', 'post_status' => 'draft', 'posts_per_page' => 8,
            'meta_key' => '_thesis_ai_generated', 'meta_value' => '1', 'fields' => 'ids',
        ]);
        if (!$ids) {
            return;
        }
        echo '<section class="tai-demo-products" aria-label="Демонстраційні товари">';
        echo '<div class="tai-demo-head"><span>ПЕРЕГЛЯД ДЛЯ РЕДАКТОРА</span><h2>Ваш майбутній каталог</h2>';
        echo '<p>Ці товари — чернетки. Додайте реальні зображення, ціни, склад та алергени й опублікуйте їх після перевірки.</p></div>';
        echo '<div class="tai-demo-grid">';
        foreach ($ids as $index => $id) {
            $id = absint($id);
            $title = get_the_title($id);
            $edit = get_edit_post_link($id, 'raw');
            echo '<article class="tai-demo-tile"><div class="tai-demo-art"><span>' . esc_html(sprintf('%02d', $index + 1)) . '</span></div>';
            echo '<div class="tai-demo-label">ЧЕРНЕТКА ТОВАРУ</div><h3>' . esc_html($title) . '</h3>';
            echo '<p>Фото та відомості про товар заповнюються перед публікацією.</p>';
            if ($edit) {
                echo '<a href="' . esc_url($edit) . '">Редагувати товар →</a>';
            }
            echo '</article>';
        }
        echo '</div></section>';
    }

    public static function activate(): void {
        $role = get_role(self::ROLE);
        if (!$role) {
            add_role(
                self::ROLE,
                __('AI Builder', 'thesis-ai-bridge'),
                [
                    'read' => true,
                    'edit_pages' => true,
                    'upload_files' => true,
                    self::CAP_USE => true,
                ]
            );
        } else {
            $role->add_cap(self::CAP_USE);
            $role->add_cap('read');
            $role->add_cap('edit_pages');
            $role->add_cap('upload_files');
        }

        self::ensure_admin_capability();

        if (get_option(self::OPTION_SETTINGS, null) === null) {
            add_option(self::OPTION_SETTINGS, self::default_settings(), '', false);
        }
        if (get_option(self::OPTION_AUDIT, null) === null) {
            add_option(self::OPTION_AUDIT, [], '', false);
        }
    }

    public static function ensure_role(): void {
        $role = get_role(self::ROLE);
        if (!$role) {
            add_role(
                self::ROLE,
                __('AI Builder', 'thesis-ai-bridge'),
                [
                    'read' => true,
                    'edit_pages' => true,
                    'upload_files' => true,
                    self::CAP_USE => true,
                ]
            );
            return;
        }
        foreach (['read', 'edit_pages', 'upload_files', self::CAP_USE] as $cap) {
            if (!$role->has_cap($cap)) {
                $role->add_cap($cap);
            }
        }
    }

    public static function ensure_admin_capability(): void {
        $admin = get_role('administrator');
        if ($admin && !$admin->has_cap(self::CAP_USE)) {
            $admin->add_cap(self::CAP_USE);
        }
    }

    public static function default_settings(): array {
        return [
            'external_api_enabled' => false,
            'existing_page_updates_enabled' => false,
            'site_settings_enabled' => false,
            'plugin_management_enabled' => false,
        ];
    }

    public static function get_settings(): array {
        $saved = get_option(self::OPTION_SETTINGS, []);
        return wp_parse_args(is_array($saved) ? $saved : [], self::default_settings());
    }

    public static function sanitize_settings(array $settings): array {
        $defaults = self::default_settings();
        $clean = [];
        foreach (array_keys($defaults) as $key) {
            $clean[$key] = !empty($settings[$key]);
        }
        return $clean;
    }

    public static function approved_plugins(): array {
        return self::APPROVED_PLUGINS;
    }

    public static function native_abilities_available(): bool {
        return class_exists('WP_Ability') && function_exists('wp_register_ability');
    }

    public static function register_category(): void {
        if (!function_exists('wp_register_ability_category')) {
            return;
        }

        wp_register_ability_category(
            self::CATEGORY,
            [
                'label' => __('Thesis AI Bridge', 'thesis-ai-bridge'),
                'description' => __('Controlled abilities for the thesis multi-agent system.', 'thesis-ai-bridge'),
            ]
        );
    }

    public static function register_abilities(): void {
        if (!function_exists('wp_register_ability')) {
            return;
        }

        foreach (self::ability_definitions() as $name => $definition) {
            wp_register_ability('thesis-ai-bridge/' . $name, $definition);
        }
    }

    private static function common_meta(bool $readonly, bool $destructive = false, bool $idempotent = false): array {
        $settings = self::get_settings();
        return [
            'show_in_rest' => !empty($settings['external_api_enabled']),
            'annotations' => [
                'readonly' => $readonly,
                'destructive' => $destructive,
                'idempotent' => $idempotent,
            ],
        ];
    }

    public static function build_contract(): array {
        require_once ABSPATH . 'wp-admin/includes/file.php';
        return [
            'bridge_version' => THESIS_AI_BRIDGE_VERSION,
            'action_journal_version' => 1,
            'action_schema_version' => 1,
            'abilities' => array_values(array_unique(array_merge(array_keys(self::ability_definitions()), [
                'configure-woocommerce', 'apply-acf-model', 'ensure-woocommerce-product-draft',
            ]))),
            'plugin_management_enabled' => self::can_manage_plugins(),
            'filesystem_method' => (string)get_filesystem_method(),
            'uploads_writable' => is_writable(WP_CONTENT_DIR . '/uploads'),
        ];
    }

    private static function do_media_inventory(): array {
        $items = get_posts(['post_type' => 'attachment', 'post_status' => 'inherit',
            'post_mime_type' => 'image', 'posts_per_page' => 25,
            'orderby' => 'date', 'order' => 'DESC']);
        $media = [];
        foreach ($items as $post) {
            $url = wp_get_attachment_image_url($post->ID, 'large');
            if (!$url || !str_starts_with((string)$url, 'https://')) { continue; }
            $media[] = ['id' => (int)$post->ID, 'url' => (string)$url,
                'alt' => (string)get_post_meta($post->ID, '_wp_attachment_image_alt', true),
                'title' => (string)$post->post_title,
                'caption' => (string)$post->post_excerpt];
        }
        return $media;
    }

    private static function ability_definitions(): array {
        return [
            'get-build-contract' => [
                'label' => __('Get Bridge execution contract', 'thesis-ai-bridge'),
                'description' => __('Returns supported actions and installation diagnostics for preflight.', 'thesis-ai-bridge'),
                'category' => self::CATEGORY,
                'output_schema' => ['type' => 'object', 'additionalProperties' => true],
                'execute_callback' => static fn(): array => self::build_contract(),
                'permission_callback' => static fn(): bool => self::can_use_bridge(),
                'meta' => self::common_meta(true, false, true),
            ],
            'get-site-info' => [
                'label' => __('Get site info', 'thesis-ai-bridge'),
                'description' => __('Returns WordPress environment information for planning and verification.', 'thesis-ai-bridge'),
                'category' => self::CATEGORY,
                'output_schema' => self::schema_site_info(),
                'execute_callback' => static fn(): array => self::execute_named_ability('get-site-info', []),
                'permission_callback' => static fn(): bool => self::can_use_bridge(),
                'meta' => self::common_meta(true, false, true),
            ],
            'get-site-snapshot' => [
                'label' => __('Get site snapshot', 'thesis-ai-bridge'),
                'description' => __('Returns site info, pages, plugins, themes, recognized capabilities and site structure in one request to reduce API bursts on managed hosting.', 'thesis-ai-bridge'),
                'category' => self::CATEGORY,
                'output_schema' => ['type' => 'object', 'additionalProperties' => true],
                'execute_callback' => static fn(): array => self::execute_named_ability('get-site-snapshot', []),
                'permission_callback' => static fn(): bool => self::can_use_bridge(),
                'meta' => self::common_meta(true, false, true),
            ],
            'list-pages' => [
                'label' => __('List pages', 'thesis-ai-bridge'),
                'description' => __('Lists pages so the builder can inspect the site and avoid duplicates.', 'thesis-ai-bridge'),
                'category' => self::CATEGORY,
                'output_schema' => self::schema_page_list(),
                'execute_callback' => static fn(): array => self::execute_named_ability('list-pages', []),
                'permission_callback' => static fn(): bool => self::can_use_bridge(),
                'meta' => self::common_meta(true, false, true),
            ],
            'get-page' => [
                'label' => __('Get page', 'thesis-ai-bridge'),
                'description' => __('Returns one page including editable Gutenberg block content.', 'thesis-ai-bridge'),
                'category' => self::CATEGORY,
                'input_schema' => self::schema_page_id_input(),
                'output_schema' => self::schema_page_detail(),
                'execute_callback' => static fn(array $input): array|WP_Error => self::execute_named_ability('get-page', $input),
                'permission_callback' => static fn(array $input): bool => self::can_use_bridge(),
                'meta' => self::common_meta(true, false, true),
            ],
            'create-draft-page' => [
                'label' => __('Create draft page', 'thesis-ai-bridge'),
                'description' => __('Creates an editable WordPress page as draft only.', 'thesis-ai-bridge'),
                'category' => self::CATEGORY,
                'input_schema' => self::schema_create_page_input(),
                'output_schema' => self::schema_page_summary(),
                'execute_callback' => static fn(array $input): array|WP_Error => self::execute_named_ability('create-draft-page', $input),
                'permission_callback' => static fn(array $input): bool => self::can_write_pages(),
                'meta' => self::common_meta(false, false, false),
            ],
            'ensure-draft-page' => [
                'label' => __('Ensure draft page', 'thesis-ai-bridge'),
                'description' => __('Creates a draft page, or safely updates the current AI user’s existing draft with the same slug. It never overwrites another user’s or a published page.', 'thesis-ai-bridge'),
                'category' => self::CATEGORY,
                'input_schema' => self::schema_create_page_input(),
                'output_schema' => self::schema_ensure_page_result(),
                'execute_callback' => static fn(array $input): array|WP_Error => self::execute_named_ability('ensure-draft-page', $input),
                'permission_callback' => static fn(array $input): bool => self::can_write_pages(),
                'meta' => self::common_meta(false, false, true),
            ],
            'update-page' => [
                'label' => __('Update page', 'thesis-ai-bridge'),
                'description' => __('Updates an existing page. Disabled by default for the AI Builder role.', 'thesis-ai-bridge'),
                'category' => self::CATEGORY,
                'input_schema' => self::schema_update_page_input(),
                'output_schema' => self::schema_update_result(),
                'execute_callback' => static fn(array $input): array|WP_Error => self::execute_named_ability('update-page', $input),
                'permission_callback' => static fn(array $input): bool => self::can_update_page((int)($input['page_id'] ?? 0)),
                'meta' => self::common_meta(false, false, true),
            ],
            'set-homepage' => [
                'label' => __('Set homepage', 'thesis-ai-bridge'),
                'description' => __('Sets a WordPress page as the static homepage. Disabled by default.', 'thesis-ai-bridge'),
                'category' => self::CATEGORY,
                'input_schema' => self::schema_page_id_input(),
                'output_schema' => [
                    'type' => 'object',
                    'properties' => [
                        'homepage_id' => ['type' => 'integer'],
                        'show_on_front' => ['type' => 'string'],
                    ],
                    'required' => ['homepage_id', 'show_on_front'],
                    'additionalProperties' => false,
                ],
                'execute_callback' => static fn(array $input): array|WP_Error => self::execute_named_ability('set-homepage', $input),
                'permission_callback' => static fn(array $input): bool => self::can_manage_site(),
                'meta' => self::common_meta(false, false, true),
            ],
            'list-plugins' => [
                'label' => __('List plugins', 'thesis-ai-bridge'),
                'description' => __('Lists installed plugins, activation state and whether each slug is approved by the bridge.', 'thesis-ai-bridge'),
                'category' => self::CATEGORY,
                'output_schema' => self::schema_plugin_list(),
                'execute_callback' => static fn(): array => self::execute_named_ability('list-plugins', []),
                'permission_callback' => static fn(): bool => self::can_use_bridge(),
                'meta' => self::common_meta(true, false, true),
            ],
            'install-approved-plugin' => [
                'label' => __('Install approved plugin', 'thesis-ai-bridge'),
                'description' => __('Installs a plugin only when its slug is in the hard-coded approved catalogue and the administrator enabled plugin management.', 'thesis-ai-bridge'),
                'category' => self::CATEGORY,
                'input_schema' => self::schema_plugin_slug_input(),
                'output_schema' => self::schema_plugin_action_result(),
                'execute_callback' => static fn(array $input): array|WP_Error => self::execute_named_ability('install-approved-plugin', $input),
                'permission_callback' => static fn(array $input): bool => self::can_manage_plugins(),
                'meta' => self::common_meta(false, false, false),
            ],
            'activate-approved-plugin' => [
                'label' => __('Activate approved plugin', 'thesis-ai-bridge'),
                'description' => __('Activates an already installed plugin only when its slug is approved and plugin management is enabled.', 'thesis-ai-bridge'),
                'category' => self::CATEGORY,
                'input_schema' => self::schema_plugin_slug_input(),
                'output_schema' => self::schema_plugin_action_result(),
                'execute_callback' => static fn(array $input): array|WP_Error => self::execute_named_ability('activate-approved-plugin', $input),
                'permission_callback' => static fn(array $input): bool => self::can_manage_plugins(),
                'meta' => self::common_meta(false, false, true),
            ],
            'deactivate-approved-plugin' => [
                'label' => __('Deactivate approved plugin', 'thesis-ai-bridge'),
                'description' => __('Deactivates an approved plugin when plugin management is enabled.', 'thesis-ai-bridge'),
                'category' => self::CATEGORY,
                'input_schema' => self::schema_plugin_slug_input(),
                'output_schema' => self::schema_plugin_action_result(),
                'execute_callback' => static fn(array $input): array|WP_Error => self::execute_named_ability('deactivate-approved-plugin', $input),
                'permission_callback' => static fn(array $input): bool => self::can_manage_plugins(),
                'meta' => self::common_meta(false, false, true),
            ],
            'inspect-capabilities' => [
                'label' => __('Inspect capabilities', 'thesis-ai-bridge'),
                'description' => __('Summarizes installed plugins, approved capabilities, Elementor availability and whether controlled plugin management is enabled.', 'thesis-ai-bridge'),
                'category' => self::CATEGORY,
                'output_schema' => self::schema_capability_snapshot(),
                'execute_callback' => static fn(): array => self::execute_named_ability('inspect-capabilities', []),
                'permission_callback' => static fn(): bool => self::can_use_bridge(),
                'meta' => self::common_meta(true, false, true),
            ],
            'get-approved-plugin-info' => [
                'label' => __('Get approved plugin info', 'thesis-ai-bridge'),
                'description' => __('Reads WordPress.org metadata only for a plugin in the approved catalogue.', 'thesis-ai-bridge'),
                'category' => self::CATEGORY,
                'input_schema' => self::schema_plugin_slug_input(),
                'output_schema' => self::schema_plugin_info_result(),
                'execute_callback' => static fn(array $input): array|WP_Error => self::execute_named_ability('get-approved-plugin-info', $input),
                'permission_callback' => static fn(array $input): bool => self::can_use_bridge(),
                'meta' => self::common_meta(true, false, true),
            ],
            'ensure-approved-plugin' => [
                'label' => __('Ensure approved plugin', 'thesis-ai-bridge'),
                'description' => __('Idempotently ensures an approved WordPress.org plugin is installed and active.', 'thesis-ai-bridge'),
                'category' => self::CATEGORY,
                'input_schema' => self::schema_plugin_slug_input(),
                'output_schema' => self::schema_plugin_action_result(),
                'execute_callback' => static fn(array $input): array|WP_Error => self::execute_named_ability('ensure-approved-plugin', $input),
                'permission_callback' => static fn(array $input): bool => self::can_manage_plugins(),
                'meta' => self::common_meta(false, false, true),
            ],
            'elementor-get-status' => [
                'label' => __('Get Elementor status', 'thesis-ai-bridge'),
                'description' => __('Returns whether Elementor is installed/active and the detected version.', 'thesis-ai-bridge'),
                'category' => self::CATEGORY,
                'output_schema' => self::schema_elementor_status(),
                'execute_callback' => static fn(): array => self::execute_named_ability('elementor-get-status', []),
                'permission_callback' => static fn(): bool => self::can_use_bridge(),
                'meta' => self::common_meta(true, false, true),
            ],
            'elementor-get-page' => [
                'label' => __('Get Elementor page', 'thesis-ai-bridge'),
                'description' => __('Returns the safe Elementor document structure for a page.', 'thesis-ai-bridge'),
                'category' => self::CATEGORY,
                'input_schema' => self::schema_page_id_input(),
                'output_schema' => self::schema_elementor_page_result(),
                'execute_callback' => static fn(array $input): array|WP_Error => self::execute_named_ability('elementor-get-page', $input),
                'permission_callback' => static fn(array $input): bool => self::can_use_bridge(),
                'meta' => self::common_meta(true, false, true),
            ],
            'elementor-ensure-draft-page' => [
                'label' => __('Ensure Elementor draft page', 'thesis-ai-bridge'),
                'description' => __('Creates or safely updates the current AI user’s Elementor draft page using a restricted Elementor component set.', 'thesis-ai-bridge'),
                'category' => self::CATEGORY,
                'input_schema' => self::schema_elementor_page_input(),
                'output_schema' => self::schema_elementor_page_result(),
                'execute_callback' => static fn(array $input): array|WP_Error => self::execute_named_ability('elementor-ensure-draft-page', $input),
                'permission_callback' => static fn(array $input): bool => self::can_write_pages(),
                'meta' => self::common_meta(false, false, true),
            ],
            'list-themes' => [
                'label' => __('List themes', 'thesis-ai-bridge'),
                'description' => __('Lists installed themes and active/approved state.', 'thesis-ai-bridge'),
                'category' => self::CATEGORY,
                'output_schema' => ['type' => 'array', 'items' => ['type' => 'object', 'additionalProperties' => true]],
                'execute_callback' => static fn(): array => self::execute_named_ability('list-themes', []),
                'permission_callback' => static fn(): bool => self::can_use_bridge(),
                'meta' => self::common_meta(true, false, true),
            ],
            'get-site-structure' => [
                'label' => __('Get site structure', 'thesis-ai-bridge'),
                'description' => __('Returns site identity, homepage, menus and active theme.', 'thesis-ai-bridge'),
                'category' => self::CATEGORY,
                'output_schema' => ['type' => 'object', 'additionalProperties' => true],
                'execute_callback' => static fn(): array => self::execute_named_ability('get-site-structure', []),
                'permission_callback' => static fn(): bool => self::can_use_bridge(),
                'meta' => self::common_meta(true, false, true),
            ],
            'ensure-approved-theme' => [
                'label' => __('Ensure approved theme', 'thesis-ai-bridge'),
                'description' => __('Installs/activates an approved WordPress.org theme.', 'thesis-ai-bridge'),
                'category' => self::CATEGORY,
                'input_schema' => ['type' => 'object', 'properties' => ['theme_slug' => ['type' => 'string']], 'required' => ['theme_slug'], 'additionalProperties' => false],
                'output_schema' => ['type' => 'object', 'additionalProperties' => true],
                'execute_callback' => static fn(array $input): array|WP_Error => self::execute_named_ability('ensure-approved-theme', $input),
                'permission_callback' => static fn(array $input): bool => self::can_manage_plugins() && self::can_manage_site(),
                'meta' => self::common_meta(false, false, true),
            ],
            'apply-site-design' => [
                'label' => __('Apply site design', 'thesis-ai-bridge'),
                'description' => __('Stores and applies the generated site-wide design tokens without arbitrary CSS execution.', 'thesis-ai-bridge'),
                'category' => self::CATEGORY,
                'input_schema' => ['type' => 'object', 'additionalProperties' => true],
                'output_schema' => ['type' => 'object', 'additionalProperties' => true],
                'execute_callback' => static fn(array $input): array|WP_Error => self::execute_named_ability('apply-site-design', $input),
                'permission_callback' => static fn(array $input): bool => self::can_manage_site(),
                'meta' => self::common_meta(false, false, true),
            ],
            'update-site-identity' => [
                'label' => __('Update site identity', 'thesis-ai-bridge'),
                'description' => __('Updates site title and tagline.', 'thesis-ai-bridge'),
                'category' => self::CATEGORY,
                'input_schema' => ['type' => 'object', 'properties' => ['site_title' => ['type' => 'string'], 'tagline' => ['type' => 'string']], 'required' => ['site_title'], 'additionalProperties' => false],
                'output_schema' => ['type' => 'object', 'additionalProperties' => true],
                'execute_callback' => static fn(array $input): array|WP_Error => self::execute_named_ability('update-site-identity', $input),
                'permission_callback' => static fn(array $input): bool => self::can_manage_site(),
                'meta' => self::common_meta(false, false, true),
            ],
            'set-homepage-by-slug' => [
                'label' => __('Set homepage by slug', 'thesis-ai-bridge'),
                'description' => __('Configures an existing page as the static homepage by slug.', 'thesis-ai-bridge'),
                'category' => self::CATEGORY,
                'input_schema' => ['type' => 'object', 'properties' => ['slug' => ['type' => 'string']], 'required' => ['slug'], 'additionalProperties' => false],
                'output_schema' => ['type' => 'object', 'additionalProperties' => true],
                'execute_callback' => static fn(array $input): array|WP_Error => self::execute_named_ability('set-homepage-by-slug', $input),
                'permission_callback' => static fn(array $input): bool => self::can_manage_site(),
                'meta' => self::common_meta(false, false, true),
            ],
            'ensure-navigation-menu' => [
                'label' => __('Ensure navigation menu', 'thesis-ai-bridge'),
                'description' => __('Creates/updates a controlled primary menu from page slugs.', 'thesis-ai-bridge'),
                'category' => self::CATEGORY,
                'input_schema' => ['type' => 'object', 'properties' => ['menu_name' => ['type' => 'string'], 'page_slugs' => ['type' => 'array', 'items' => ['type' => 'string']], 'assign_primary' => ['type' => 'boolean']], 'required' => ['menu_name', 'page_slugs'], 'additionalProperties' => false],
                'output_schema' => ['type' => 'object', 'additionalProperties' => true],
                'execute_callback' => static fn(array $input): array|WP_Error => self::execute_named_ability('ensure-navigation-menu', $input),
                'permission_callback' => static fn(array $input): bool => self::can_manage_site(),
                'meta' => self::common_meta(false, false, true),
            ],
            'set-page-seo' => [
                'label' => __('Set page SEO metadata', 'thesis-ai-bridge'),
                'description' => __('Stores controlled SEO title/description and maps them to supported SEO plugins when active.', 'thesis-ai-bridge'),
                'category' => self::CATEGORY,
                'input_schema' => ['type' => 'object', 'properties' => ['slug' => ['type' => 'string'], 'seo_title' => ['type' => 'string'], 'meta_description' => ['type' => 'string']], 'required' => ['slug', 'seo_title', 'meta_description'], 'additionalProperties' => false],
                'output_schema' => ['type' => 'object', 'additionalProperties' => true],
                'execute_callback' => static fn(array $input): array|WP_Error => self::execute_named_ability('set-page-seo', $input),
                'permission_callback' => static fn(array $input): bool => self::can_manage_site(),
                'meta' => self::common_meta(false, false, true),
            ],
            'ensure-contact-form' => [
                'label' => __('Ensure contact form', 'thesis-ai-bridge'),
                'description' => __('Creates an idempotent Contact Form 7 form after the approved plugin is active.', 'thesis-ai-bridge'),
                'category' => self::CATEGORY,
                'input_schema' => ['type' => 'object', 'properties' => ['title' => ['type' => 'string']], 'required' => ['title'], 'additionalProperties' => false],
                'output_schema' => ['type' => 'object', 'additionalProperties' => true],
                'execute_callback' => static fn(array $input): array|WP_Error => self::execute_named_ability('ensure-contact-form', $input),
                'permission_callback' => static fn(array $input): bool => self::can_manage_plugins(),
                'meta' => self::common_meta(false, false, true),
            ],
        ];
    }

    public static function register_fallback_rest_routes(): void {
        register_rest_route('thesis-ai/v1', '/status', [
            'methods' => WP_REST_Server::READABLE,
            'callback' => static fn(WP_REST_Request $request): WP_REST_Response => rest_ensure_response(self::status_payload()),
            'permission_callback' => static fn(): bool => self::external_api_enabled() && self::can_use_bridge(),
        ]);

        register_rest_route('thesis-ai/v1', '/run/(?P<ability>[a-z0-9-]+)', [
            'methods' => [WP_REST_Server::READABLE, WP_REST_Server::CREATABLE],
            'callback' => [self::class, 'fallback_rest_run'],
            'permission_callback' => [self::class, 'fallback_rest_permission'],
            'args' => [
                'ability' => [
                    'type' => 'string',
                    'required' => true,
                    'sanitize_callback' => 'sanitize_key',
                ],
            ],
        ]);

        // Managed-hosting friendly batch endpoint. The backend still applies its
        // Policy Engine per logical action; WordPress independently re-checks
        // permissions per action before executing anything. One HTTP request can
        // therefore safely carry several local WordPress operations.
        register_rest_route('thesis-ai/v1', '/batch', [
            'methods' => WP_REST_Server::CREATABLE,
            'callback' => [self::class, 'fallback_rest_batch'],
            'permission_callback' => static fn(): bool|WP_Error => self::external_api_enabled()
                ? (self::can_use_bridge() ? true : new WP_Error('thesis_ai_forbidden', __('Bridge access denied.', 'thesis-ai-bridge'), ['status' => 403]))
                : new WP_Error('thesis_ai_api_disabled', __('External Bridge API is disabled.', 'thesis-ai-bridge'), ['status' => 403]),
        ]);
    }

    public static function fallback_rest_permission(WP_REST_Request $request): bool|WP_Error {
        if (!self::external_api_enabled()) {
            return new WP_Error('thesis_ai_api_disabled', __('External Bridge API is disabled.', 'thesis-ai-bridge'), ['status' => 403]);
        }

        $ability = sanitize_key((string)$request['ability']);
        $input = self::request_input($request);
        return self::permission_for_ability($ability, $input);
    }

    private static function permission_for_ability(string $ability, array $input): bool|WP_Error {
        $allowed = match ($ability) {
            'get-build-contract', 'get-site-snapshot', 'get-site-info', 'list-pages', 'get-page', 'list-plugins', 'list-themes', 'inspect-capabilities', 'get-approved-plugin-info', 'elementor-get-status', 'elementor-get-page', 'get-site-structure' => self::can_use_bridge(),
            'create-draft-page', 'ensure-draft-page', 'elementor-ensure-draft-page' => self::can_write_pages(),
            'update-page' => self::can_update_page((int)($input['page_id'] ?? 0)),
            'set-homepage', 'set-homepage-by-slug', 'update-site-identity', 'apply-site-design', 'ensure-navigation-menu', 'set-page-seo' => self::can_manage_site(),
            'install-approved-plugin', 'activate-approved-plugin', 'deactivate-approved-plugin', 'ensure-approved-plugin', 'ensure-contact-form' => self::can_manage_plugins(),
            'ensure-approved-theme' => self::can_manage_plugins() && self::can_manage_site(),
            'configure-woocommerce', 'apply-acf-model', 'ensure-woocommerce-product-draft' => self::can_manage_plugins() && self::can_manage_site(),
            default => null,
        };
        if ($allowed === null) {
            return new WP_Error('thesis_ai_unknown_ability', __('Unknown bridge ability.', 'thesis-ai-bridge'), ['status' => 404]);
        }
        if (!$allowed) {
            return new WP_Error('thesis_ai_forbidden', __('This Bridge ability is not permitted for the current service user/settings.', 'thesis-ai-bridge'), ['status' => 403]);
        }
        return true;
    }

    public static function fallback_rest_batch(WP_REST_Request $request): WP_REST_Response|WP_Error {
        $json = $request->get_json_params();
        $actions = is_array($json) && isset($json['actions']) && is_array($json['actions']) ? $json['actions'] : [];
        $include_snapshot = !is_array($json) || !array_key_exists('include_snapshot', $json) || !empty($json['include_snapshot']);
        if (!$actions) {
            return new WP_Error('thesis_ai_empty_batch', __('The execution batch is empty.', 'thesis-ai-bridge'), ['status' => 400]);
        }
        if (count($actions) > 12) {
            return new WP_Error('thesis_ai_batch_too_large', __('A Bridge batch may contain at most 12 actions.', 'thesis-ai-bridge'), ['status' => 400]);
        }

        $results = [];
        foreach (array_values($actions) as $index => $item) {
            if (!is_array($item)) {
                $results[] = ['index' => $index, 'ability' => '', 'ok' => false, 'error' => 'Invalid batch action payload.'];
                continue;
            }
            $ability = sanitize_key((string)($item['ability'] ?? ''));
            $input = isset($item['input']) && is_array($item['input']) ? $item['input'] : [];
            try {
                $permission = self::permission_for_ability($ability, $input);
                if (is_wp_error($permission)) {
                    $results[] = [
                        'index' => $index, 'ability' => $ability, 'ok' => false,
                        'error' => $permission->get_error_message(), 'error_code' => $permission->get_error_code(),
                    ];
                    continue;
                }
                $result = self::execute_named_ability($ability, $input);
                if (is_wp_error($result)) {
                    $results[] = [
                        'index' => $index, 'ability' => $ability, 'ok' => false,
                        'error' => $result->get_error_message(), 'error_code' => $result->get_error_code(),
                    ];
                    continue;
                }
                $results[] = ['index' => $index, 'ability' => $ability, 'ok' => true, 'result' => $result];
            } catch (\Throwable $throwable) {
                // Never let one plugin/theme/Elementor failure collapse the entire
                // REST batch into WordPress's generic "critical error" response.
                // Return the exact logical action failure so the orchestrator can
                // repair or isolate it while other independent actions continue.
                self::audit($ability ?: 'batch-action', 'error', $input, 'throwable:' . get_class($throwable));
                $results[] = [
                    'index' => $index,
                    'ability' => $ability,
                    'ok' => false,
                    'error' => $throwable->getMessage(),
                    'error_code' => 'thesis_ai_throwable',
                    'error_class' => get_class($throwable),
                ];
            }
        }

        $snapshot = null;
        $snapshot_error = null;
        if ($include_snapshot) {
            try {
                $snapshot = self::do_get_site_snapshot();
            } catch (\Throwable $throwable) {
                $snapshot_error = [
                    'error' => $throwable->getMessage(),
                    'error_code' => 'thesis_ai_snapshot_throwable',
                    'error_class' => get_class($throwable),
                ];
                self::audit('get-site-snapshot', 'error', [], 'throwable:' . get_class($throwable));
            }
        }

        return rest_ensure_response([
            'results' => $results,
            'snapshot' => $snapshot,
            'snapshot_error' => $snapshot_error,
            'bridge_version' => THESIS_AI_BRIDGE_VERSION,
            'action_journal_version' => 1,
            'action_schema_version' => 1,
        ]);
    }

    public static function fallback_rest_run(WP_REST_Request $request): WP_REST_Response|WP_Error {
        $ability = sanitize_key((string)$request['ability']);
        $input = self::request_input($request);
        $result = self::execute_named_ability($ability, $input);
        if (is_wp_error($result)) {
            return $result;
        }
        return rest_ensure_response(['result' => $result]);
    }

    private static function request_input(WP_REST_Request $request): array {
        $json = $request->get_json_params();
        if (is_array($json) && isset($json['input']) && is_array($json['input'])) {
            return $json['input'];
        }
        if (is_array($json)) {
            return $json;
        }

        $input = $request->get_param('input');
        if (is_string($input) && $input !== '') {
            $decoded = json_decode($input, true);
            return is_array($decoded) ? $decoded : [];
        }
        return [];
    }

    /** Validate the mutating execution contract independently of the Python policy. */
    public static function validate_execution_parameters(string $ability, array $input): true|WP_Error {
        $encoded = wp_json_encode($input);
        if (!is_string($encoded) || strlen($encoded) > 350000) {
            return new WP_Error('thesis_ai_action_too_large', 'Action parameters exceed 350 KB.');
        }
        $allowed = [
            'ensure-approved-plugin' => ['plugin_slug'],
            'install-approved-plugin' => ['plugin_slug'],
            'activate-approved-plugin' => ['plugin_slug'],
            'deactivate-approved-plugin' => ['plugin_slug'],
            'ensure-approved-theme' => ['theme_slug'],
            'set-page-seo' => ['slug', 'seo_title', 'meta_description'],
            'update-site-identity' => ['site_title', 'tagline'],
            'ensure-navigation-menu' => ['menu_name', 'page_slugs', 'assign_primary'],
            'set-homepage-by-slug' => ['slug'],
            'elementor-ensure-draft-page' => ['title', 'slug', 'elements', 'settings'],
            'ensure-draft-page' => ['title', 'slug', 'content'],
            'create-draft-page' => ['title', 'slug', 'content'],
            'apply-site-design' => ['primary', 'accent', 'background', 'surface', 'text', 'muted', 'heading_font', 'body_font', 'container_width', 'radius'],
            'ensure-contact-form' => ['title'],
            'configure-woocommerce' => ['currency'],
            'ensure-woocommerce-product-draft' => ['name', 'description'],
            'apply-acf-model' => ['content_types'],
        ];
        if (!isset($allowed[$ability])) { return true; }
        $unknown = array_diff(array_keys($input), $allowed[$ability]);
        if ($unknown) {
            return new WP_Error('thesis_ai_unknown_parameter', 'Unsupported action parameter: ' . (string)reset($unknown));
        }
        if (isset($input['slug']) && (!is_string($input['slug']) || !preg_match('/^[a-z0-9]+(?:-[a-z0-9]+)*$/D', $input['slug']))) {
            return new WP_Error('thesis_ai_bad_slug', 'Page slug is invalid.');
        }
        if (isset($input['page_slugs'])) {
            if (!is_array($input['page_slugs']) || count($input['page_slugs']) > 30) {
                return new WP_Error('thesis_ai_invalid_menu', 'Invalid number of menu pages.');
            }
            foreach ($input['page_slugs'] as $slug) {
                if (!is_string($slug) || strlen($slug) > 120 || !preg_match('/^[a-z0-9]+(?:-[a-z0-9]+)*$/D', $slug)) {
                    return new WP_Error('thesis_ai_bad_slug', 'Invalid menu page slug.');
                }
            }
        }
        if (isset($input['elements']) && (!is_array($input['elements']) || count($input['elements']) > 300)) {
            return new WP_Error('thesis_ai_invalid_elements', 'Too many Elementor root elements.');
        }
        if ($ability === 'ensure-approved-theme' && (!isset($input['theme_slug']) || $input['theme_slug'] !== 'hello-elementor')) {
            return new WP_Error('thesis_ai_theme_not_approved', 'Theme is not approved.');
        }
        if (str_contains($ability, 'approved-plugin') && isset($input['plugin_slug']) && !array_key_exists((string)$input['plugin_slug'], self::APPROVED_PLUGINS)) {
            return new WP_Error('thesis_ai_plugin_not_approved', 'Plugin is not approved.');
        }
        return true;
    }

    public static function execute_named_ability(string $ability, array $input): array|WP_Error {
        $validated = self::validate_execution_parameters($ability, $input);
        if (is_wp_error($validated)) { return $validated; }
        $result = match ($ability) {
            'get-build-contract' => self::build_contract(),
            'get-site-snapshot' => self::do_get_site_snapshot(),
            'get-site-info' => self::do_get_site_info(),
            'list-pages' => self::do_list_pages(),
            'get-page' => self::do_get_page($input),
            'create-draft-page' => self::do_create_draft_page($input),
            'ensure-draft-page' => self::do_ensure_draft_page($input),
            'update-page' => self::do_update_page($input),
            'set-homepage' => self::do_set_homepage($input),
            'set-homepage-by-slug' => Thesis_AI_Site_Setup::set_homepage_by_slug($input),
            'apply-site-design' => self::do_apply_site_design($input),
            'update-site-identity' => Thesis_AI_Site_Setup::update_site_identity($input),
            'ensure-navigation-menu' => Thesis_AI_Site_Setup::ensure_navigation_menu($input),
            'set-page-seo' => Thesis_AI_Site_Setup::set_page_seo($input),
            'list-plugins' => self::do_list_plugins(),
            'list-themes' => Thesis_AI_Site_Setup::list_themes(),
            'install-approved-plugin' => self::do_install_approved_plugin($input),
            'activate-approved-plugin' => self::do_activate_approved_plugin($input),
            'deactivate-approved-plugin' => self::do_deactivate_approved_plugin($input),
            'inspect-capabilities' => self::do_inspect_capabilities(),
            'get-approved-plugin-info' => self::do_get_approved_plugin_info($input),
            'ensure-approved-plugin' => self::do_ensure_approved_plugin($input),
            'ensure-approved-theme' => Thesis_AI_Site_Setup::ensure_approved_theme($input),
            'ensure-contact-form' => Thesis_AI_Site_Setup::ensure_contact_form($input),
            'configure-woocommerce' => Thesis_AI_Site_Setup::configure_woocommerce($input),
            'ensure-woocommerce-product-draft' => Thesis_AI_Site_Setup::ensure_woocommerce_product_draft($input),
            'apply-acf-model' => self::do_apply_acf_model($input),
            'get-site-structure' => Thesis_AI_Site_Setup::get_site_structure(),
            'elementor-get-status' => self::do_elementor_get_status(),
            'elementor-get-page' => self::do_elementor_get_page($input),
            'elementor-ensure-draft-page' => self::do_elementor_ensure_draft_page($input),
            default => new WP_Error('thesis_ai_unknown_ability', __('Unknown bridge ability.', 'thesis-ai-bridge')),
        };

        if (is_wp_error($result)) {
            self::audit($ability, 'error', $input, $result->get_error_code());
        } else {
            self::audit($ability, 'success', $input);
        }
        return $result;
    }

    private static function do_apply_site_design(array $input): array|WP_Error {
        $colors = [];
        foreach (['primary', 'accent', 'background', 'surface', 'text', 'muted'] as $key) {
            $color = sanitize_hex_color((string)($input[$key] ?? ''));
            if ($color) {
                $colors[$key] = $color;
            }
        }
        if (empty($colors['primary']) || empty($colors['text'])) {
            return new WP_Error('thesis_ai_design_invalid', __('Primary and text colors are required.', 'thesis-ai-bridge'));
        }
        $design = array_merge($colors, [
            'heading_font' => sanitize_text_field((string)($input['heading_font'] ?? 'Inter')),
            'body_font' => sanitize_text_field((string)($input['body_font'] ?? 'Inter')),
            'container_width' => max(760, min(1600, absint($input['container_width'] ?? 1180))),
            'radius' => max(0, min(40, absint($input['radius'] ?? 18))),
            'updated_at' => gmdate('c'),
        ]);
        update_option(self::OPTION_SITE_DESIGN, $design, false);
        return ['applied' => true, 'design' => $design];
    }

    private static function commerce_snapshot(): array {
        if (!post_type_exists('product')) {
            return ['published_products' => 0, 'draft_products' => 0, 'generated_product_names' => []];
        }
        $counts = wp_count_posts('product');
        $generated = get_posts([
            'post_type' => 'product', 'post_status' => 'draft', 'posts_per_page' => 15,
            'meta_key' => '_thesis_ai_generated', 'meta_value' => '1', 'fields' => 'ids',
        ]);
        return [
            'published_products' => (int)($counts->publish ?? 0),
            'draft_products' => (int)($counts->draft ?? 0),
            'generated_product_names' => array_values(array_map(static fn($id) => (string)get_the_title((int)$id), $generated)),
        ];
    }

    private static function do_get_site_snapshot(): array {
        return [
            'site_info' => self::do_get_site_info(),
            'pages' => self::do_list_pages(),
            'plugins' => self::do_list_plugins(),
            'themes' => Thesis_AI_Site_Setup::list_themes(),
            'capabilities' => self::do_inspect_capabilities(),
            'structure' => Thesis_AI_Site_Setup::get_site_structure(),
            'bridge_contract' => self::build_contract(),
            'media' => self::do_media_inventory(),
            'commerce' => self::commerce_snapshot(),
            'generated_at' => gmdate('c'),
        ];
    }

    private static function do_get_site_info(): array {
        $theme = wp_get_theme();
        return [
            'name' => (string)get_bloginfo('name'),
            'tagline' => (string)get_bloginfo('description'),
            'url' => (string)home_url('/'),
            'wordpress_version' => (string)get_bloginfo('version'),
            'php_version' => (string)PHP_VERSION,
            'theme' => (string)$theme->get('Name'),
            'theme_slug' => (string)get_stylesheet(),
            'theme_version' => (string)$theme->get('Version'),
            'is_block_theme' => function_exists('wp_is_block_theme') ? (bool)wp_is_block_theme() : false,
            'permalink_structure' => (string)get_option('permalink_structure', ''),
            'https' => is_ssl(),
            'multisite' => is_multisite(),
            'native_abilities_api' => self::native_abilities_available(),
            'bridge_version' => THESIS_AI_BRIDGE_VERSION,
            'action_journal_version' => 1,
            'action_schema_version' => 1,
        ];
    }

    private static function do_list_pages(): array {
        $posts = get_posts([
            'post_type' => 'page',
            'post_status' => ['publish', 'draft', 'pending', 'private', 'future'],
            'numberposts' => 200,
            'orderby' => 'ID',
            'order' => 'ASC',
        ]);

        return array_map(static function (WP_Post $post): array {
            $page_id = (int)$post->ID;
            $generated = (string)get_post_meta($page_id, '_thesis_ai_generated', true) === '1';
            $summary = [];
            if ($generated && class_exists('\\Elementor\\Plugin')) {
                try {
                    $document = \Elementor\Plugin::$instance->documents->get($page_id, false);
                    if ($document) {
                        $raw = $document->get_elements_raw_data(null, false);
                        if (is_array($raw)) {
                            $summary = self::summarize_elementor_elements($raw);
                            $summary['built_with_elementor'] = (bool)$document->is_built_with_elementor();
                        }
                    }
                } catch (Throwable $throwable) {
                    $summary = ['summary_error' => get_class($throwable)];
                }
            }
            return [
                'id' => $page_id,
                'title' => (string)get_the_title($post),
                'slug' => (string)$post->post_name,
                'status' => (string)$post->post_status,
                'author' => (int)$post->post_author,
                'url' => (string)get_permalink($post),
                'ai_generated' => $generated,
                'seo_title' => (string)get_post_meta($page_id, '_thesis_ai_seo_title', true),
                'meta_description' => (string)get_post_meta($page_id, '_thesis_ai_meta_description', true),
                'elementor' => $summary,
            ];
        }, $posts);
    }

    private static function summarize_elementor_elements(array $elements): array {
        $result = [
            'element_count' => 0,
            'widget_counts' => [],
            'headings' => [],
            'buttons' => [],
            'shortcodes' => [],
            'text_excerpt' => '',
        ];
        $text_parts = [];
        $walk = static function (array $items) use (&$walk, &$result, &$text_parts): void {
            foreach ($items as $element) {
                if (!is_array($element)) { continue; }
                $result['element_count']++;
                if (($element['elType'] ?? '') === 'widget') {
                    $type = sanitize_key((string)($element['widgetType'] ?? ''));
                    if ($type !== '') {
                        $result['widget_counts'][$type] = (int)($result['widget_counts'][$type] ?? 0) + 1;
                    }
                    $settings = is_array($element['settings'] ?? null) ? $element['settings'] : [];
                    if ($type === 'heading' && !empty($settings['title']) && count($result['headings']) < 20) {
                        $result['headings'][] = sanitize_text_field(wp_strip_all_tags((string)$settings['title']));
                    } elseif ($type === 'button' && count($result['buttons']) < 12) {
                        $link = is_array($settings['link'] ?? null) ? (string)($settings['link']['url'] ?? '') : '';
                        $result['buttons'][] = [
                            'label' => sanitize_text_field(wp_strip_all_tags((string)($settings['text'] ?? ''))),
                            'url' => esc_url_raw($link),
                        ];
                    } elseif ($type === 'shortcode' && !empty($settings['shortcode']) && count($result['shortcodes']) < 8) {
                        $result['shortcodes'][] = sanitize_text_field((string)$settings['shortcode']);
                    } elseif ($type === 'text-editor' && !empty($settings['editor'])) {
                        $text_parts[] = sanitize_text_field(wp_strip_all_tags((string)$settings['editor']));
                    }
                }
                if (!empty($element['elements']) && is_array($element['elements'])) {
                    $walk($element['elements']);
                }
                if ($result['element_count'] >= 250) { return; }
            }
        };
        $walk($elements);
        $joined_text = trim(implode(' ', array_filter($text_parts)));
        $result['text_excerpt'] = function_exists('mb_substr') ? mb_substr($joined_text, 0, 1200) : substr($joined_text, 0, 1200);
        return $result;
    }

    private static function do_get_page(array $input): array|WP_Error {
        $page_id = absint($input['page_id'] ?? 0);
        $post = $page_id ? get_post($page_id) : null;
        if (!$post || $post->post_type !== 'page') {
            return new WP_Error('thesis_ai_page_not_found', __('Page not found.', 'thesis-ai-bridge'));
        }
        if (!current_user_can('read_post', $page_id) && !current_user_can('edit_post', $page_id)) {
            return new WP_Error('thesis_ai_forbidden', __('You cannot access this page.', 'thesis-ai-bridge'));
        }

        return [
            'id' => (int)$post->ID,
            'title' => (string)get_the_title($post),
            'slug' => (string)$post->post_name,
            'status' => (string)$post->post_status,
            'content' => (string)$post->post_content,
            'url' => (string)get_permalink($post),
        ];
    }

    private static function do_create_draft_page(array $input): array|WP_Error {
        $title = sanitize_text_field((string)($input['title'] ?? ''));
        if ($title === '') {
            return new WP_Error('thesis_ai_missing_title', __('Page title is required.', 'thesis-ai-bridge'));
        }

        $slug = sanitize_title((string)($input['slug'] ?? ''));
        if ($slug !== '') {
            $existing = get_page_by_path($slug, OBJECT, 'page');
            if ($existing instanceof WP_Post) {
                return new WP_Error(
                    'thesis_ai_page_exists',
                    __('A page with this slug already exists.', 'thesis-ai-bridge'),
                    ['existing_page_id' => (int)$existing->ID]
                );
            }
        }

        $postarr = [
            'post_type' => 'page',
            'post_status' => 'draft',
            'post_title' => $title,
            'post_content' => self::sanitize_block_content((string)($input['content'] ?? '')),
            'post_author' => get_current_user_id(),
        ];
        if ($slug !== '') {
            $postarr['post_name'] = $slug;
        }

        $post_id = wp_insert_post(wp_slash($postarr), true);
        if (is_wp_error($post_id)) {
            return $post_id;
        }
        update_post_meta((int)$post_id, '_thesis_ai_generated', '1');

        return self::page_summary((int)$post_id);
    }

    /**
     * Resolve an existing slug without getting stuck on drafts from previous test runs.
     * AI-owned trashed pages are safe to restore to draft and reuse. Other users'
     * content and published AI pages remain protected from automatic overwrite.
     */
    private static function safe_ai_draft_by_slug(string $slug): WP_Post|WP_Error|null {
        $matches = get_posts([
            'name' => $slug,
            'post_type' => 'page',
            'post_status' => ['publish', 'draft', 'pending', 'private', 'future', 'trash'],
            'numberposts' => 1,
            'orderby' => 'ID',
            'order' => 'DESC',
        ]);
        $existing = $matches && $matches[0] instanceof WP_Post ? $matches[0] : null;
        if (!$existing instanceof WP_Post) {
            return null;
        }

        $author = get_userdata((int)$existing->post_author);
        $legacy_ai_author = $author instanceof WP_User && (
            in_array('thesis_ai_builder', (array)$author->roles, true)
            || (string)get_user_meta((int)$author->ID, '_thesis_ai_service_user', true) === '1'
        );
        $owned = ((string)get_post_meta((int)$existing->ID, '_thesis_ai_generated', true) === '1')
            || ((int)$existing->post_author === get_current_user_id())
            || $legacy_ai_author;

        if ($owned && in_array($existing->post_status, ['draft', 'trash'], true)) {
            if ($existing->post_status === 'trash') {
                wp_untrash_post((int)$existing->ID);
                $restored = wp_update_post([
                    'ID' => (int)$existing->ID,
                    'post_status' => 'draft',
                    'post_name' => $slug,
                ], true);
                if (is_wp_error($restored)) {
                    return $restored;
                }
                clean_post_cache((int)$existing->ID);
                $existing = get_post((int)$existing->ID);
                if (!$existing instanceof WP_Post) {
                    return new WP_Error('thesis_ai_page_restore_failed', __('Could not restore the previous AI draft.', 'thesis-ai-bridge'));
                }
            }
            update_post_meta((int)$existing->ID, '_thesis_ai_generated', '1');
            return $existing;
        }

        return new WP_Error(
            'thesis_ai_page_conflict',
            sprintf(
                __('A page with slug "%1$s" already exists (status: %2$s, author: %3$d) and is not a safe AI-owned draft. Rename/archive the conflicting page or choose another slug.', 'thesis-ai-bridge'),
                $slug,
                (string)$existing->post_status,
                (int)$existing->post_author
            ),
            ['existing_page_id' => (int)$existing->ID, 'status' => (string)$existing->post_status, 'author' => (int)$existing->post_author]
        );
    }

    private static function do_ensure_draft_page(array $input): array|WP_Error {
        $title = sanitize_text_field((string)($input['title'] ?? ''));
        if ($title === '') {
            return new WP_Error('thesis_ai_missing_title', __('Page title is required.', 'thesis-ai-bridge'));
        }
        $slug = sanitize_title((string)($input['slug'] ?? ''));
        if ($slug === '') {
            return new WP_Error('thesis_ai_missing_slug', __('A stable slug is required for ensure-draft-page.', 'thesis-ai-bridge'));
        }

        $existing = self::safe_ai_draft_by_slug($slug);
        if (is_wp_error($existing)) {
            return $existing;
        }
        if ($existing instanceof WP_Post) {
            $updated = wp_update_post(wp_slash([
                'ID' => (int)$existing->ID,
                'post_title' => $title,
                'post_content' => self::sanitize_block_content((string)($input['content'] ?? '')),
            ]), true);
            if (is_wp_error($updated)) {
                return $updated;
            }
            return array_merge(self::page_summary((int)$existing->ID), ['created' => false]);
        }

        $created = self::do_create_draft_page($input);
        if (is_wp_error($created)) {
            return $created;
        }
        return array_merge($created, ['created' => true]);
    }

    private static function do_update_page(array $input): array|WP_Error {
        $page_id = absint($input['page_id'] ?? 0);
        $post = $page_id ? get_post($page_id) : null;
        if (!$post || $post->post_type !== 'page') {
            return new WP_Error('thesis_ai_page_not_found', __('Page not found.', 'thesis-ai-bridge'));
        }
        if (!self::can_update_page($page_id)) {
            return new WP_Error('thesis_ai_forbidden', __('Updating existing pages is not allowed for this request/user.', 'thesis-ai-bridge'));
        }

        $update = ['ID' => $page_id];
        if (array_key_exists('title', $input)) {
            $title = sanitize_text_field((string)$input['title']);
            if ($title === '') {
                return new WP_Error('thesis_ai_missing_title', __('Page title cannot be empty.', 'thesis-ai-bridge'));
            }
            $update['post_title'] = $title;
        }
        if (array_key_exists('content', $input)) {
            $update['post_content'] = self::sanitize_block_content((string)$input['content']);
        }

        $result = wp_update_post(wp_slash($update), true);
        if (is_wp_error($result)) {
            return $result;
        }

        return [
            'id' => $page_id,
            'status' => (string)get_post_status($page_id),
            'updated' => true,
        ];
    }

    private static function do_set_homepage(array $input): array|WP_Error {
        $page_id = absint($input['page_id'] ?? 0);
        $post = $page_id ? get_post($page_id) : null;
        if (!$post || $post->post_type !== 'page') {
            return new WP_Error('thesis_ai_page_not_found', __('Page not found.', 'thesis-ai-bridge'));
        }
        if (!self::can_manage_site()) {
            return new WP_Error('thesis_ai_forbidden', __('Site-setting changes are disabled.', 'thesis-ai-bridge'));
        }

        update_option('show_on_front', 'page');
        update_option('page_on_front', $page_id);
        return ['homepage_id' => $page_id, 'show_on_front' => 'page'];
    }

    private static function do_list_plugins(): array {
        if (!function_exists('get_plugins')) {
            require_once ABSPATH . 'wp-admin/includes/plugin.php';
        }
        $plugins = get_plugins();
        $approved = array_keys(self::APPROVED_PLUGINS);
        $updates = get_site_transient('update_plugins');
        $update_response = is_object($updates) && isset($updates->response) && is_array($updates->response) ? $updates->response : [];

        $result = [];
        foreach ($plugins as $file => $data) {
            $slug = self::plugin_slug_from_file($file);
            $update = $update_response[$file] ?? null;
            $result[] = [
                'file' => (string)$file,
                'slug' => $slug,
                'name' => (string)($data['Name'] ?? ''),
                'version' => (string)($data['Version'] ?? ''),
                'active' => is_plugin_active($file),
                'approved' => in_array($slug, $approved, true),
                'update_available' => is_object($update),
                'new_version' => is_object($update) ? (string)($update->new_version ?? '') : '',
                'requires_php' => (string)($data['RequiresPHP'] ?? ''),
                'requires_wp' => (string)($data['RequiresWP'] ?? ''),
            ];
        }
        usort($result, static fn(array $a, array $b): int => strcasecmp($a['name'], $b['name']));
        return $result;
    }

    private static function do_install_approved_plugin(array $input): array|WP_Error {
        if (!self::can_manage_plugins()) {
            return new WP_Error('thesis_ai_plugin_management_disabled', __('Plugin management is disabled.', 'thesis-ai-bridge'));
        }

        $slug = sanitize_key((string)($input['plugin_slug'] ?? ''));
        if (!isset(self::APPROVED_PLUGINS[$slug])) {
            return new WP_Error('thesis_ai_plugin_not_approved', __('Plugin is not in the approved catalogue.', 'thesis-ai-bridge'));
        }

        $installed = self::find_plugin_file($slug);
        if ($installed !== null) {
            return [
                'plugin_slug' => $slug,
                'plugin_file' => $installed,
                'installed' => true,
                'active' => is_plugin_active($installed),
                'changed' => false,
                'message' => 'Plugin is already installed.',
            ];
        }

        require_once ABSPATH . 'wp-admin/includes/plugin.php';
        require_once ABSPATH . 'wp-admin/includes/plugin-install.php';
        require_once ABSPATH . 'wp-admin/includes/class-wp-upgrader.php';
        require_once ABSPATH . 'wp-admin/includes/class-automatic-upgrader-skin.php';

        $api = plugins_api('plugin_information', [
            'slug' => $slug,
            'fields' => ['sections' => false, 'download_link' => true],
        ]);
        if (is_wp_error($api)) {
            return $api;
        }
        $download_link = isset($api->download_link) ? (string)$api->download_link : '';
        $host = strtolower((string)wp_parse_url($download_link, PHP_URL_HOST));
        if ($download_link === '' || $host !== 'downloads.wordpress.org') {
            return new WP_Error('thesis_ai_untrusted_download', __('Plugin download URL is not from downloads.wordpress.org.', 'thesis-ai-bridge'));
        }

        require_once ABSPATH . 'wp-admin/includes/file.php';
        $method = (string)get_filesystem_method();
        if ($method !== 'direct') {
            return new WP_Error('thesis_ai_plugin_filesystem_credentials',
                sprintf(__('Automatic installation of %1$s needs WordPress filesystem credentials (method: %2$s). Please install it through Plugins → Add New.', 'thesis-ai-bridge'), $slug, $method));
        }
        if (!WP_Filesystem()) {
            return new WP_Error('thesis_ai_plugin_filesystem_unavailable',
                __('WordPress could not initialize direct filesystem access. Check wp-content/plugins permissions.', 'thesis-ai-bridge'));
        }
        if (!is_writable(WP_PLUGIN_DIR)) {
            return new WP_Error('thesis_ai_plugin_directory_readonly',
                __('wp-content/plugins is not writable by PHP. Install the plugin manually or contact hosting support.', 'thesis-ai-bridge'));
        }
        $skin = new Automatic_Upgrader_Skin();
        $upgrader = new Plugin_Upgrader($skin);
        $result = $upgrader->install($download_link);
        if (is_wp_error($result)) {
            return $result;
        }
        if (!$result) {
            $errors = method_exists($skin, 'get_errors') ? $skin->get_errors() : null;
            if (is_wp_error($errors) && $errors->has_errors()) {
                return new WP_Error('thesis_ai_plugin_install_failed', $errors->get_error_message());
            }
            return new WP_Error('thesis_ai_plugin_install_failed',
                sprintf(__('Plugin installation of %s failed. Verify PHP file permissions and available disk space.', 'thesis-ai-bridge'), $slug));
        }

        $plugin_file = $upgrader->plugin_info();
        if (!$plugin_file) {
            $plugin_file = self::find_plugin_file($slug);
        }
        if (!$plugin_file) {
            return new WP_Error('thesis_ai_plugin_file_unknown', __('Plugin installed but its main plugin file could not be identified.', 'thesis-ai-bridge'));
        }

        return [
            'plugin_slug' => $slug,
            'plugin_file' => (string)$plugin_file,
            'installed' => true,
            'active' => is_plugin_active($plugin_file),
            'changed' => true,
            'message' => 'Plugin installed from WordPress.org.',
        ];
    }

    private static function do_activate_approved_plugin(array $input): array|WP_Error {
        if (!self::can_manage_plugins()) {
            return new WP_Error('thesis_ai_plugin_management_disabled', __('Plugin management is disabled.', 'thesis-ai-bridge'));
        }
        require_once ABSPATH . 'wp-admin/includes/plugin.php';

        $slug = sanitize_key((string)($input['plugin_slug'] ?? ''));
        if (!isset(self::APPROVED_PLUGINS[$slug])) {
            return new WP_Error('thesis_ai_plugin_not_approved', __('Plugin is not in the approved catalogue.', 'thesis-ai-bridge'));
        }
        $plugin_file = self::find_plugin_file($slug);
        if (!$plugin_file) {
            return new WP_Error('thesis_ai_plugin_not_installed', __('Plugin is not installed.', 'thesis-ai-bridge'));
        }
        if (is_plugin_active($plugin_file)) {
            return [
                'plugin_slug' => $slug,
                'plugin_file' => $plugin_file,
                'installed' => true,
                'active' => true,
                'changed' => false,
                'message' => 'Plugin is already active.',
            ];
        }

        $result = activate_plugin($plugin_file, '', false, false);
        if (is_wp_error($result)) {
            return $result;
        }
        return [
            'plugin_slug' => $slug,
            'plugin_file' => $plugin_file,
            'installed' => true,
            'active' => true,
            'changed' => true,
            'message' => 'Plugin activated.',
        ];
    }

    private static function do_deactivate_approved_plugin(array $input): array|WP_Error {
        if (!self::can_manage_plugins()) {
            return new WP_Error('thesis_ai_plugin_management_disabled', __('Plugin management is disabled.', 'thesis-ai-bridge'));
        }
        require_once ABSPATH . 'wp-admin/includes/plugin.php';

        $slug = sanitize_key((string)($input['plugin_slug'] ?? ''));
        if (!isset(self::APPROVED_PLUGINS[$slug])) {
            return new WP_Error('thesis_ai_plugin_not_approved', __('Plugin is not in the approved catalogue.', 'thesis-ai-bridge'));
        }
        $plugin_file = self::find_plugin_file($slug);
        if (!$plugin_file) {
            return new WP_Error('thesis_ai_plugin_not_installed', __('Plugin is not installed.', 'thesis-ai-bridge'));
        }
        if (!is_plugin_active($plugin_file)) {
            return [
                'plugin_slug' => $slug,
                'plugin_file' => $plugin_file,
                'installed' => true,
                'active' => false,
                'changed' => false,
                'message' => 'Plugin is already inactive.',
            ];
        }

        deactivate_plugins($plugin_file, false, false);
        return [
            'plugin_slug' => $slug,
            'plugin_file' => $plugin_file,
            'installed' => true,
            'active' => false,
            'changed' => true,
            'message' => 'Plugin deactivated.',
        ];
    }


    private static function do_inspect_capabilities(): array {
        $plugins = self::do_list_plugins();
        $by_slug = [];
        foreach ($plugins as $plugin) {
            $by_slug[(string)$plugin['slug']] = $plugin;
        }
        $approved = [];
        foreach (self::APPROVED_PLUGINS as $slug => $name) {
            $state = $by_slug[$slug] ?? null;
            $approved[$slug] = [
                'name' => $name,
                'installed' => is_array($state),
                'active' => is_array($state) ? (bool)$state['active'] : false,
                'version' => is_array($state) ? (string)$state['version'] : '',
                'update_available' => is_array($state) ? (bool)($state['update_available'] ?? false) : false,
            ];
        }
        $settings = self::get_settings();
        return [
            'approved_plugins' => $approved,
            'recognized_capabilities' => [
                'page_builder_elementor' => !empty($approved['elementor']['active']),
                'ecommerce' => !empty($approved['woocommerce']['active']),
                'structured_content' => !empty($approved['advanced-custom-fields']['active']),
                'forms' => !empty($approved['contact-form-7']['active']),
                'seo' => !empty($approved['wordpress-seo']['active']) || !empty($approved['seo-by-rank-math']['active']),
            ],
            'plugin_management_enabled' => !empty($settings['plugin_management_enabled']),
            'filesystem_method' => function_exists('get_filesystem_method') ? (string)get_filesystem_method() : 'unknown',
            'elementor' => self::do_elementor_get_status(),
        ];
    }

    private static function do_get_approved_plugin_info(array $input): array|WP_Error {
        $slug = sanitize_key((string)($input['plugin_slug'] ?? ''));
        if (!isset(self::APPROVED_PLUGINS[$slug])) {
            return new WP_Error('thesis_ai_plugin_not_approved', __('Plugin is not in the approved catalogue.', 'thesis-ai-bridge'));
        }
        require_once ABSPATH . 'wp-admin/includes/plugin-install.php';
        $api = plugins_api('plugin_information', [
            'slug' => $slug,
            'fields' => [
                'sections' => false,
                'description' => false,
                'short_description' => true,
                'download_link' => false,
                'icons' => false,
                'banners' => false,
            ],
        ]);
        if (is_wp_error($api)) {
            return $api;
        }
        return [
            'plugin_slug' => $slug,
            'name' => (string)($api->name ?? self::APPROVED_PLUGINS[$slug]),
            'version' => (string)($api->version ?? ''),
            'requires' => (string)($api->requires ?? ''),
            'requires_php' => (string)($api->requires_php ?? ''),
            'tested' => (string)($api->tested ?? ''),
            'active_installs' => (int)($api->active_installs ?? 0),
            'rating' => (int)($api->rating ?? 0),
        ];
    }

    private static function do_ensure_approved_plugin(array $input): array|WP_Error {
        $slug = sanitize_key((string)($input['plugin_slug'] ?? ''));
        if (!isset(self::APPROVED_PLUGINS[$slug])) {
            return new WP_Error('thesis_ai_plugin_not_approved', __('Plugin is not in the approved catalogue.', 'thesis-ai-bridge'));
        }
        if (!self::can_manage_plugins()) {
            return new WP_Error('thesis_ai_plugin_management_disabled', __('Plugin management is disabled.', 'thesis-ai-bridge'));
        }
        $plugin_file = self::find_plugin_file($slug);
        $installed_now = false;
        if (!$plugin_file) {
            $install = self::do_install_approved_plugin(['plugin_slug' => $slug]);
            if (is_wp_error($install)) {
                return $install;
            }
            $installed_now = !empty($install['changed']);
            $plugin_file = (string)($install['plugin_file'] ?? '');
        }
        if ($plugin_file === '') {
            return new WP_Error('thesis_ai_plugin_file_unknown', __('Could not identify plugin file after installation.', 'thesis-ai-bridge'));
        }
        require_once ABSPATH . 'wp-admin/includes/plugin.php';
        $activated_now = false;
        if (!is_plugin_active($plugin_file)) {
            $activation = self::do_activate_approved_plugin(['plugin_slug' => $slug]);
            if (is_wp_error($activation)) {
                return $activation;
            }
            $activated_now = !empty($activation['changed']);
        }
        return [
            'plugin_slug' => $slug,
            'plugin_file' => $plugin_file,
            'installed' => true,
            'active' => is_plugin_active($plugin_file),
            'changed' => $installed_now || $activated_now,
            'message' => $installed_now ? 'Plugin installed and activated.' : ($activated_now ? 'Plugin activated.' : 'Plugin already installed and active.'),
        ];
    }


    private static function do_apply_acf_model(array $input): array|WP_Error {
        if (!current_user_can('manage_options')) {
            return new WP_Error('thesis_ai_acf_forbidden', __('Administrator permissions are required to configure structured content.', 'thesis-ai-bridge'));
        }
        if (!function_exists('acf_add_local_field_group')) {
            return new WP_Error('thesis_ai_acf_unavailable', __('Advanced Custom Fields is not active.', 'thesis-ai-bridge'));
        }
        $types = isset($input['content_types']) && is_array($input['content_types']) ? $input['content_types'] : [];
        $models = [];
        foreach ($types as $type) {
            if (!is_array($type) || (string)($type['implementation'] ?? '') !== 'cpt') {
                continue;
            }
            $name = sanitize_text_field((string)($type['name'] ?? 'Item')) ?: 'Item';
            $slug = substr(sanitize_key((string)($type['slug'] ?? sanitize_title($name))), 0, 20);
            if ($slug === '') {
                $slug = 'ai_item';
            }
            $fields = [];
            foreach ((array)($type['fields'] ?? []) as $field) {
                $label = sanitize_text_field((string)$field);
                if ($label === '') { continue; }
                $fname = sanitize_key(str_replace('-', '_', sanitize_title($label)));
                if ($fname === '') { continue; }
                $ftype = preg_match('/price|cost|amount|area|rooms|duration|year|number|кільк|ціна|площа|тривал/i', $label) ? 'number' : 'text';
                if (preg_match('/url|link|website|trailer|video|посилан/i', $label)) { $ftype = 'url'; }
                $fields[] = ['name' => $fname, 'label' => $label, 'type' => $ftype];
            }
            $models[] = ['slug' => $slug, 'name' => $name, 'fields' => $fields];
        }
        update_option(self::OPTION_DATA_MODELS, $models, false);
        self::register_dynamic_content_types();
        self::register_dynamic_acf_fields();
        return ['configured' => true, 'content_types' => $models];
    }

    public static function register_dynamic_content_types(): void {
        $models = get_option(self::OPTION_DATA_MODELS, []);
        if (!is_array($models)) { return; }
        foreach ($models as $model) {
            if (!is_array($model)) { continue; }
            $slug = substr(sanitize_key((string)($model['slug'] ?? '')), 0, 20);
            $name = sanitize_text_field((string)($model['name'] ?? 'Item'));
            if ($slug === '' || post_type_exists($slug)) { continue; }
            register_post_type($slug, [
                'labels' => ['name' => $name, 'singular_name' => $name, 'add_new_item' => sprintf(__('Add %s', 'thesis-ai-bridge'), $name)],
                'public' => true,
                'show_ui' => true,
                'show_in_rest' => true,
                'has_archive' => true,
                'rewrite' => ['slug' => $slug],
                'supports' => ['title', 'editor', 'thumbnail', 'excerpt'],
                'menu_icon' => 'dashicons-database',
            ]);
        }
    }

    public static function register_dynamic_acf_fields(): void {
        if (!function_exists('acf_add_local_field_group')) { return; }
        $models = get_option(self::OPTION_DATA_MODELS, []);
        if (!is_array($models)) { return; }
        foreach ($models as $model) {
            if (!is_array($model)) { continue; }
            $slug = substr(sanitize_key((string)($model['slug'] ?? '')), 0, 20);
            if ($slug === '') { continue; }
            $fields = [];
            foreach ((array)($model['fields'] ?? []) as $field) {
                if (!is_array($field)) { continue; }
                $name = sanitize_key((string)($field['name'] ?? ''));
                if ($name === '') { continue; }
                $fields[] = [
                    'key' => 'field_' . substr(md5($slug . '|' . $name), 0, 20),
                    'label' => sanitize_text_field((string)($field['label'] ?? $name)),
                    'name' => $name,
                    'type' => in_array((string)($field['type'] ?? 'text'), ['text', 'number', 'url'], true) ? (string)$field['type'] : 'text',
                    'required' => 0,
                ];
            }
            acf_add_local_field_group([
                'key' => 'group_' . substr(md5('thesis_ai|' . $slug), 0, 20),
                'title' => sprintf(__('%s fields', 'thesis-ai-bridge'), sanitize_text_field((string)($model['name'] ?? $slug))),
                'fields' => $fields,
                'location' => [[['param' => 'post_type', 'operator' => '==', 'value' => $slug]]],
                'position' => 'normal',
                'style' => 'default',
                'active' => true,
            ]);
        }
    }

    private static function do_elementor_get_status(): array {
        $plugin_file = self::find_plugin_file('elementor');
        $active = false;
        if ($plugin_file) {
            if (!function_exists('is_plugin_active')) {
                require_once ABSPATH . 'wp-admin/includes/plugin.php';
            }
            $active = is_plugin_active($plugin_file);
        }
        return [
            'installed' => $plugin_file !== null,
            'active' => $active,
            'version' => defined('ELEMENTOR_VERSION') ? (string)ELEMENTOR_VERSION : '',
            'runtime_loaded' => class_exists('\\Elementor\\Plugin'),
            'plugin_file' => $plugin_file ?? '',
            // A read-only readiness signal, NOT an MCP connection or consent.
            // MCP must be enabled explicitly in Elementor's admin UI.
            'mcp_elementor_version_eligible' => $active && defined('ELEMENTOR_VERSION') && version_compare((string)ELEMENTOR_VERSION, '4.3.0', '>='),
            'mcp_wordpress_version_eligible' => version_compare((string)get_bloginfo('version'), '6.8', '>='),
            'mcp_requires_admin_opt_in' => true,
            'builder_adapter' => 'elementor_v3_document',
        ];
    }

    private static function do_elementor_get_page(array $input): array|WP_Error {
        $page_id = absint($input['page_id'] ?? 0);
        $post = $page_id ? get_post($page_id) : null;
        if (!$post || $post->post_type !== 'page') {
            return new WP_Error('thesis_ai_page_not_found', __('Page not found.', 'thesis-ai-bridge'));
        }
        if (!class_exists('\\Elementor\\Plugin')) {
            return new WP_Error('thesis_ai_elementor_unavailable', __('Elementor is not active.', 'thesis-ai-bridge'));
        }
        $document = \Elementor\Plugin::$instance->documents->get($page_id, false);
        if (!$document) {
            return new WP_Error('thesis_ai_elementor_document_missing', __('Elementor document is unavailable for this page.', 'thesis-ai-bridge'));
        }
        $elements = $document->get_elements_raw_data(null, false);
        return [
            'id' => $page_id,
            'title' => (string)get_the_title($page_id),
            'slug' => (string)$post->post_name,
            'status' => (string)$post->post_status,
            'url' => (string)get_permalink($page_id),
            'edit_url' => (string)$document->get_edit_url(),
            'built_with_elementor' => (bool)$document->is_built_with_elementor(),
            'elements' => is_array($elements) ? $elements : [],
        ];
    }

    private static function do_elementor_ensure_draft_page(array $input): array|WP_Error {
        if (!class_exists('\\Elementor\\Plugin')) {
            return new WP_Error('thesis_ai_elementor_unavailable', __('Elementor is not active. Ensure the approved Elementor plugin first.', 'thesis-ai-bridge'));
        }
        $title = sanitize_text_field((string)($input['title'] ?? ''));
        $slug = sanitize_title((string)($input['slug'] ?? ''));
        $elements = isset($input['elements']) && is_array($input['elements']) ? $input['elements'] : [];
        $settings = isset($input['settings']) && is_array($input['settings']) ? $input['settings'] : [];
        if ($title === '' || $slug === '') {
            return new WP_Error('thesis_ai_invalid_page', __('Elementor page title and slug are required.', 'thesis-ai-bridge'));
        }
        $count = 0;
        $sanitized = self::sanitize_elementor_elements($elements, 0, $count);
        if (is_wp_error($sanitized)) {
            return $sanitized;
        }
        $settings = self::sanitize_elementor_settings($settings, 'page');

        $existing = self::safe_ai_draft_by_slug($slug);
        if (is_wp_error($existing)) {
            return $existing;
        }
        if ($existing instanceof WP_Post) {
            $page_id = (int)$existing->ID;
            $updated = wp_update_post(['ID' => $page_id, 'post_title' => $title, 'post_status' => 'draft'], true);
            if (is_wp_error($updated)) {
                return $updated;
            }
        } else {
            $page_id = wp_insert_post(wp_slash([
                'post_type' => 'page',
                'post_status' => 'draft',
                'post_title' => $title,
                'post_name' => $slug,
                'post_author' => get_current_user_id(),
                'post_content' => '',
            ]), true);
            if (is_wp_error($page_id)) {
                return $page_id;
            }
            $page_id = (int)$page_id;
        }
        update_post_meta($page_id, '_thesis_ai_generated', '1');
        // The document setting alone does not reliably set the WordPress
        // page template. The Hello theme's default layout can constrain the
        // entire Elementor canvas to a narrow article column.
        // Only AI-owned drafts reach this branch; never change foreign pages.
        update_post_meta($page_id, '_wp_page_template', 'elementor_full_width');

        $document = \Elementor\Plugin::$instance->documents->get($page_id, false);
        if (!$document) {
            return new WP_Error('thesis_ai_elementor_document_missing', __('Elementor could not create a document for the page.', 'thesis-ai-bridge'));
        }
        $document->set_is_built_with_elementor(true);
        $saved = $document->save([
            'settings' => $settings,
            'elements' => $sanitized,
        ]);
        if (!$saved) {
            return new WP_Error('thesis_ai_elementor_save_failed', __('Elementor rejected the document save.', 'thesis-ai-bridge'));
        }
        clean_post_cache($page_id);
        return [
            'id' => $page_id,
            'title' => (string)get_the_title($page_id),
            'slug' => (string)get_post_field('post_name', $page_id),
            'status' => (string)get_post_status($page_id),
            'url' => (string)get_permalink($page_id),
            'edit_url' => (string)$document->get_edit_url(),
            'built_with_elementor' => true,
            'elements' => $sanitized,
        ];
    }

    private static function sanitize_elementor_elements(array $elements, int $depth, int &$count): array|WP_Error {
        if ($depth > 8) {
            return new WP_Error('thesis_ai_elementor_depth', __('Elementor structure is nested too deeply.', 'thesis-ai-bridge'));
        }
        $clean = [];
        $allowed_widgets = ['heading', 'text-editor', 'button', 'image', 'icon', 'spacer', 'divider', 'shortcode'];
        foreach ($elements as $element) {
            if (!is_array($element)) {
                continue;
            }
            $count++;
            if ($count > 250) {
                return new WP_Error('thesis_ai_elementor_too_large', __('Elementor page exceeds the safe element limit.', 'thesis-ai-bridge'));
            }
            $el_type = sanitize_key((string)($element['elType'] ?? ''));
            if (!in_array($el_type, ['container', 'widget'], true)) {
                return new WP_Error('thesis_ai_elementor_type', __('Unsupported Elementor element type.', 'thesis-ai-bridge'));
            }
            $item = [
                'id' => self::sanitize_elementor_id((string)($element['id'] ?? '')),
                'elType' => $el_type,
                'isInner' => !empty($element['isInner']),
                'settings' => self::sanitize_elementor_settings(is_array($element['settings'] ?? null) ? $element['settings'] : [], $el_type),
                'elements' => [],
            ];
            if ($el_type === 'widget') {
                $widget_type = sanitize_key((string)($element['widgetType'] ?? ''));
                if (!in_array($widget_type, $allowed_widgets, true)) {
                    return new WP_Error('thesis_ai_elementor_widget', sprintf(__('Unsupported Elementor widget: %s', 'thesis-ai-bridge'), $widget_type));
                }
                $item['widgetType'] = $widget_type;
            }
            $children = is_array($element['elements'] ?? null) ? $element['elements'] : [];
            if ($children) {
                $nested = self::sanitize_elementor_elements($children, $depth + 1, $count);
                if (is_wp_error($nested)) {
                    return $nested;
                }
                $item['elements'] = $nested;
            }
            $clean[] = $item;
        }
        return $clean;
    }

    private static function sanitize_elementor_id(string $id): string {
        $id = strtolower(preg_replace('/[^a-f0-9]/i', '', $id) ?? '');
        if (strlen($id) < 6 || strlen($id) > 12) {
            return substr(md5(wp_generate_uuid4()), 0, 8);
        }
        return $id;
    }

    private static function sanitize_elementor_settings(array $settings, string $scope): array {
        $allowed = [
            'title', 'header_size', 'editor', 'text', 'link', 'selected_icon', 'image', 'image_size', 'size', 'align',
            'content_width', 'flex_direction', 'flex_wrap', 'justify_content', 'align_items', 'gap', 'padding', 'margin',
            'min_height', 'background_background', 'background_color', 'text_color', 'title_color', 'primary_color',
            'secondary_color', 'border_radius', 'space', 'weight', 'style', 'width', 'width_tablet', 'width_mobile', 'css_classes', 'html_tag', 'hide_title', 'page_layout', 'shortcode',
            'padding_tablet', 'padding_mobile', 'gap_tablet', 'gap_mobile', 'flex_direction_tablet', 'flex_direction_mobile',
            'typography_typography', 'typography_font_family', 'typography_font_size', 'typography_font_weight', 'typography_line_height', 'button_text_color', 'button_css_id',
        ];
        $clean = [];
        foreach ($settings as $key => $value) {
            $key = sanitize_key((string)$key);
            if (!in_array($key, $allowed, true)) {
                continue;
            }
            if (in_array($key, ['title', 'editor', 'text', 'shortcode'], true)) {
                $clean[$key] = wp_kses_post((string)$value);
            } elseif ($key === 'link' && is_array($value)) {
                $clean[$key] = [
                    'url' => esc_url_raw((string)($value['url'] ?? '')),
                    'is_external' => !empty($value['is_external']) ? 'on' : '',
                    'nofollow' => !empty($value['nofollow']) ? 'on' : '',
                ];
            } elseif ($key === 'image' && is_array($value)) {
                // Never trust an agent-supplied media URL. Elementor may use
                // only image attachments owned by this WordPress installation.
                $attachment_id = absint($value['id'] ?? 0);
                $image_url = $attachment_id > 0 && wp_attachment_is_image($attachment_id)
                    ? wp_get_attachment_image_url($attachment_id, 'large') : false;
                if ($image_url) {
                    $clean[$key] = ['id' => $attachment_id, 'url' => esc_url_raw((string)$image_url)];
                }
            } elseif (in_array($key, ['background_color', 'text_color', 'title_color', 'primary_color', 'secondary_color'], true)) {
                $color = sanitize_hex_color((string)$value);
                if ($color) {
                    $clean[$key] = $color;
                }
            } elseif ($key === 'css_classes') {
                $classes = preg_split('/\s+/', (string)$value) ?: [];
                $clean[$key] = implode(' ', array_filter(array_map('sanitize_html_class', $classes)));
            } elseif ($key === 'typography_font_family') {
                // Elementor CSS output must never contain agent-supplied CSS tokens.
                $family = preg_replace('/[^a-zA-Z0-9 ,\-]/', '', (string)$value) ?: '';
                $clean[$key] = substr(trim($family), 0, 80);
            } elseif (is_array($value)) {
                $clean[$key] = self::sanitize_elementor_scalar_array($value);
            } else {
                $clean[$key] = sanitize_text_field((string)$value);
            }
        }
        return $clean;
    }

    private static function sanitize_elementor_scalar_array(array $value): array {
        $clean = [];
        foreach ($value as $key => $item) {
            $safe_key = is_int($key) ? $key : sanitize_key((string)$key);
            if (is_array($item)) {
                $clean[$safe_key] = self::sanitize_elementor_scalar_array($item);
            } elseif (is_bool($item) || is_int($item) || is_float($item)) {
                $clean[$safe_key] = $item;
            } else {
                $clean[$safe_key] = sanitize_text_field((string)$item);
            }
        }
        return $clean;
    }

    private static function sanitize_block_content(string $content): string {
        // Preserve valid Gutenberg block comments. Content is still filtered through
        // WordPress KSES for users who do not have unfiltered_html.
        return current_user_can('unfiltered_html') ? $content : wp_kses_post($content);
    }

    private static function page_summary(int $post_id): array {
        $post = get_post($post_id);
        return [
            'id' => $post_id,
            'title' => (string)get_the_title($post_id),
            'slug' => $post ? (string)$post->post_name : '',
            'status' => $post ? (string)$post->post_status : 'draft',
            'url' => (string)get_permalink($post_id),
            'ai_generated' => (string)get_post_meta($post_id, '_thesis_ai_generated', true) === '1',
        ];
    }

    private static function plugin_slug_from_file(string $file): string {
        $parts = explode('/', $file, 2);
        if (count($parts) === 2) {
            return sanitize_key($parts[0]);
        }
        return sanitize_key(pathinfo($file, PATHINFO_FILENAME));
    }

    private static function find_plugin_file(string $slug): ?string {
        if (!function_exists('get_plugins')) {
            require_once ABSPATH . 'wp-admin/includes/plugin.php';
        }
        foreach (get_plugins() as $file => $data) {
            if (self::plugin_slug_from_file((string)$file) === $slug) {
                return (string)$file;
            }
        }
        return null;
    }

    public static function status_payload(): array {
        $settings = self::get_settings();
        $user = wp_get_current_user();
        return [
            'bridge_version' => THESIS_AI_BRIDGE_VERSION,
            'action_journal_version' => 1,
            'action_schema_version' => 1,
            'wordpress_version' => (string)get_bloginfo('version'),
            'php_version' => (string)PHP_VERSION,
            'native_abilities_api' => self::native_abilities_available(),
            'external_api_enabled' => (bool)$settings['external_api_enabled'],
            'https' => is_ssl(),
            'authenticated_user' => [
                'id' => (int)$user->ID,
                'login' => (string)$user->user_login,
                'roles' => array_values((array)$user->roles),
            ],
            'permissions' => [
                'use_bridge' => self::can_use_bridge(),
                'write_pages' => self::can_write_pages(),
                'update_existing_pages' => !empty($settings['existing_page_updates_enabled']),
                'site_settings' => !empty($settings['site_settings_enabled']),
                'plugin_management' => !empty($settings['plugin_management_enabled']),
            ],
            'approved_plugins' => self::APPROVED_PLUGINS,
            'approved_themes' => Thesis_AI_Site_Setup::approved_themes(),
            'endpoints' => [
                'fallback_status' => rest_url('thesis-ai/v1/status'),
                'fallback_run_base' => rest_url('thesis-ai/v1/run/'),
                'native_abilities_base' => self::native_abilities_available() ? rest_url('wp-abilities/v1/') : null,
            ],
        ];
    }

    public static function audit_log(): array {
        $log = get_option(self::OPTION_AUDIT, []);
        return is_array($log) ? $log : [];
    }

    public static function audit(string $ability, string $status, array $input = [], string $detail = ''): void {
        $safe_input = [];
        foreach (['page_id', 'title', 'slug', 'plugin_slug'] as $key) {
            if (isset($input[$key])) {
                $safe_input[$key] = is_scalar($input[$key]) ? (string)$input[$key] : '[complex]';
            }
        }
        if (array_key_exists('content', $input)) {
            $safe_input['content'] = '[omitted]';
        }

        $log = self::audit_log();
        array_unshift($log, [
            'time' => gmdate('c'),
            'user_id' => get_current_user_id(),
            'ability' => sanitize_key($ability),
            'status' => sanitize_key($status),
            'input' => $safe_input,
            'detail' => sanitize_text_field($detail),
        ]);
        $log = array_slice($log, 0, 100);
        update_option(self::OPTION_AUDIT, $log, false);
    }

    private static function external_api_enabled(): bool {
        $settings = self::get_settings();
        return !empty($settings['external_api_enabled']);
    }

    private static function can_use_bridge(): bool {
        return is_user_logged_in() && current_user_can(self::CAP_USE);
    }

    private static function can_write_pages(): bool {
        return self::can_use_bridge() && current_user_can('edit_pages');
    }

    private static function can_update_page(int $page_id): bool {
        if (!self::can_use_bridge() || $page_id <= 0 || !current_user_can('edit_post', $page_id)) {
            return false;
        }
        $post = get_post($page_id);
        if (!$post || $post->post_type !== 'page') {
            return false;
        }
        if ((int)$post->post_author === get_current_user_id() && $post->post_status === 'draft') {
            return true;
        }
        $settings = self::get_settings();
        return !empty($settings['existing_page_updates_enabled']);
    }

    private static function can_manage_site(): bool {
        $settings = self::get_settings();
        return self::can_use_bridge() && !empty($settings['site_settings_enabled']);
    }

    private static function can_manage_plugins(): bool {
        $settings = self::get_settings();
        return self::can_use_bridge() && !empty($settings['plugin_management_enabled']);
    }

    private static function schema_site_info(): array {
        return [
            'type' => 'object',
            'properties' => [
                'name' => ['type' => 'string'],
                'tagline' => ['type' => 'string'],
                'url' => ['type' => 'string'],
                'wordpress_version' => ['type' => 'string'],
                'php_version' => ['type' => 'string'],
                'theme' => ['type' => 'string'],
                'theme_slug' => ['type' => 'string'],
                'theme_version' => ['type' => 'string'],
                'is_block_theme' => ['type' => 'boolean'],
                'permalink_structure' => ['type' => 'string'],
                'https' => ['type' => 'boolean'],
                'multisite' => ['type' => 'boolean'],
                'native_abilities_api' => ['type' => 'boolean'],
                'bridge_version' => ['type' => 'string'],
            ],
            'required' => ['name', 'tagline', 'url', 'wordpress_version', 'php_version', 'theme', 'theme_slug', 'theme_version', 'is_block_theme', 'permalink_structure', 'https', 'multisite', 'native_abilities_api', 'bridge_version'],
            'additionalProperties' => false,
        ];
    }

    private static function schema_page_list(): array {
        return [
            'type' => 'array',
            'items' => [
                'type' => 'object',
                'properties' => [
                    'id' => ['type' => 'integer'],
                    'title' => ['type' => 'string'],
                    'slug' => ['type' => 'string'],
                    'status' => ['type' => 'string'],
                    'author' => ['type' => 'integer'],
                    'url' => ['type' => 'string'],
                ],
                'required' => ['id', 'title', 'slug', 'status', 'author', 'url'],
                'additionalProperties' => false,
            ],
        ];
    }

    private static function schema_page_id_input(): array {
        return [
            'type' => 'object',
            'properties' => ['page_id' => ['type' => 'integer', 'minimum' => 1]],
            'required' => ['page_id'],
            'additionalProperties' => false,
        ];
    }

    private static function schema_create_page_input(): array {
        return [
            'type' => 'object',
            'properties' => [
                'title' => ['type' => 'string', 'minLength' => 1, 'maxLength' => 200],
                'slug' => ['type' => 'string', 'maxLength' => 200],
                'content' => ['type' => 'string'],
            ],
            'required' => ['title'],
            'additionalProperties' => false,
        ];
    }

    private static function schema_update_page_input(): array {
        return [
            'type' => 'object',
            'properties' => [
                'page_id' => ['type' => 'integer', 'minimum' => 1],
                'title' => ['type' => 'string', 'minLength' => 1, 'maxLength' => 200],
                'content' => ['type' => 'string'],
            ],
            'required' => ['page_id'],
            'additionalProperties' => false,
        ];
    }

    private static function schema_page_summary(): array {
        return [
            'type' => 'object',
            'properties' => [
                'id' => ['type' => 'integer'],
                'title' => ['type' => 'string'],
                'slug' => ['type' => 'string'],
                'status' => ['type' => 'string'],
                'url' => ['type' => 'string'],
            ],
            'required' => ['id', 'title', 'slug', 'status', 'url'],
            'additionalProperties' => false,
        ];
    }

    private static function schema_ensure_page_result(): array {
        $schema = self::schema_page_summary();
        $schema['properties']['created'] = ['type' => 'boolean'];
        $schema['required'][] = 'created';
        return $schema;
    }

    private static function schema_page_detail(): array {
        $schema = self::schema_page_summary();
        $schema['properties']['content'] = ['type' => 'string'];
        $schema['required'][] = 'content';
        return $schema;
    }

    private static function schema_update_result(): array {
        return [
            'type' => 'object',
            'properties' => [
                'id' => ['type' => 'integer'],
                'status' => ['type' => 'string'],
                'updated' => ['type' => 'boolean'],
            ],
            'required' => ['id', 'status', 'updated'],
            'additionalProperties' => false,
        ];
    }

    private static function schema_plugin_slug_input(): array {
        return [
            'type' => 'object',
            'properties' => ['plugin_slug' => ['type' => 'string', 'minLength' => 1, 'maxLength' => 100]],
            'required' => ['plugin_slug'],
            'additionalProperties' => false,
        ];
    }

    private static function schema_plugin_list(): array {
        return [
            'type' => 'array',
            'items' => [
                'type' => 'object',
                'properties' => [
                    'file' => ['type' => 'string'],
                    'slug' => ['type' => 'string'],
                    'name' => ['type' => 'string'],
                    'version' => ['type' => 'string'],
                    'active' => ['type' => 'boolean'],
                    'approved' => ['type' => 'boolean'],
                    'update_available' => ['type' => 'boolean'],
                    'new_version' => ['type' => 'string'],
                    'requires_php' => ['type' => 'string'],
                    'requires_wp' => ['type' => 'string'],
                ],
                'required' => ['file', 'slug', 'name', 'version', 'active', 'approved', 'update_available', 'new_version', 'requires_php', 'requires_wp'],
                'additionalProperties' => false,
            ],
        ];
    }


    private static function schema_capability_snapshot(): array {
        return ['type' => 'object', 'additionalProperties' => true];
    }

    private static function schema_plugin_info_result(): array {
        return ['type' => 'object', 'additionalProperties' => true];
    }

    private static function schema_elementor_status(): array {
        return ['type' => 'object', 'additionalProperties' => true];
    }

    private static function schema_elementor_page_input(): array {
        return [
            'type' => 'object',
            'properties' => [
                'title' => ['type' => 'string', 'minLength' => 1, 'maxLength' => 200],
                'slug' => ['type' => 'string', 'minLength' => 1, 'maxLength' => 200],
                'elements' => ['type' => 'array'],
                'settings' => ['type' => 'object'],
            ],
            'required' => ['title', 'slug', 'elements'],
            'additionalProperties' => false,
        ];
    }

    private static function schema_elementor_page_result(): array {
        return ['type' => 'object', 'additionalProperties' => true];
    }

    private static function schema_plugin_action_result(): array {
        return [
            'type' => 'object',
            'properties' => [
                'plugin_slug' => ['type' => 'string'],
                'plugin_file' => ['type' => 'string'],
                'installed' => ['type' => 'boolean'],
                'active' => ['type' => 'boolean'],
                'changed' => ['type' => 'boolean'],
                'message' => ['type' => 'string'],
            ],
            'required' => ['plugin_slug', 'plugin_file', 'installed', 'active', 'changed', 'message'],
            'additionalProperties' => false,
        ];
    }
}
