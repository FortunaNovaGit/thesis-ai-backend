<?php

declare(strict_types=1);

if (!defined('ABSPATH')) {
    exit;
}

final class Thesis_AI_Bridge {
    private const CATEGORY = 'thesis-ai';
    private const OPTION_SETTINGS = 'thesis_ai_bridge_settings';
    private const OPTION_AUDIT = 'thesis_ai_bridge_audit_log';
    private const ROLE = 'thesis_ai_builder';
    private const CAP_USE = 'thesis_ai_use_bridge';

    private const APPROVED_PLUGINS = [
        'woocommerce' => 'WooCommerce',
        'advanced-custom-fields' => 'Advanced Custom Fields',
        'contact-form-7' => 'Contact Form 7',
        'wordpress-seo' => 'Yoast SEO',
        'seo-by-rank-math' => 'Rank Math SEO',
    ];

    public static function init(): void {
        add_action('init', [self::class, 'ensure_role']);
        add_action('init', [self::class, 'ensure_admin_capability']);
        add_action('rest_api_init', [self::class, 'register_fallback_rest_routes']);

        // These hooks exist only when the native Abilities API is available (WordPress 6.9+).
        add_action('wp_abilities_api_categories_init', [self::class, 'register_category']);
        add_action('wp_abilities_api_init', [self::class, 'register_abilities']);
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
            'external_api_enabled' => true,
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

    private static function ability_definitions(): array {
        return [
            'get-site-info' => [
                'label' => __('Get site info', 'thesis-ai-bridge'),
                'description' => __('Returns WordPress environment information for planning and verification.', 'thesis-ai-bridge'),
                'category' => self::CATEGORY,
                'output_schema' => self::schema_site_info(),
                'execute_callback' => static fn(): array => self::execute_named_ability('get-site-info', []),
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
    }

    public static function fallback_rest_permission(WP_REST_Request $request): bool|WP_Error {
        if (!self::external_api_enabled()) {
            return new WP_Error('thesis_ai_api_disabled', __('External Bridge API is disabled.', 'thesis-ai-bridge'), ['status' => 403]);
        }

        $ability = sanitize_key((string)$request['ability']);
        $input = self::request_input($request);

        return match ($ability) {
            'get-site-info', 'list-pages', 'get-page', 'list-plugins' => self::can_use_bridge(),
            'create-draft-page', 'ensure-draft-page' => self::can_write_pages(),
            'update-page' => self::can_update_page((int)($input['page_id'] ?? 0)),
            'set-homepage' => self::can_manage_site(),
            'install-approved-plugin', 'activate-approved-plugin', 'deactivate-approved-plugin' => self::can_manage_plugins(),
            default => new WP_Error('thesis_ai_unknown_ability', __('Unknown bridge ability.', 'thesis-ai-bridge'), ['status' => 404]),
        };
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

    public static function execute_named_ability(string $ability, array $input): array|WP_Error {
        $result = match ($ability) {
            'get-site-info' => self::do_get_site_info(),
            'list-pages' => self::do_list_pages(),
            'get-page' => self::do_get_page($input),
            'create-draft-page' => self::do_create_draft_page($input),
            'ensure-draft-page' => self::do_ensure_draft_page($input),
            'update-page' => self::do_update_page($input),
            'set-homepage' => self::do_set_homepage($input),
            'list-plugins' => self::do_list_plugins(),
            'install-approved-plugin' => self::do_install_approved_plugin($input),
            'activate-approved-plugin' => self::do_activate_approved_plugin($input),
            'deactivate-approved-plugin' => self::do_deactivate_approved_plugin($input),
            default => new WP_Error('thesis_ai_unknown_ability', __('Unknown bridge ability.', 'thesis-ai-bridge')),
        };

        if (is_wp_error($result)) {
            self::audit($ability, 'error', $input, $result->get_error_code());
        } else {
            self::audit($ability, 'success', $input);
        }
        return $result;
    }

    private static function do_get_site_info(): array {
        $theme = wp_get_theme();
        return [
            'name' => (string)get_bloginfo('name'),
            'url' => (string)home_url('/'),
            'wordpress_version' => (string)get_bloginfo('version'),
            'php_version' => (string)PHP_VERSION,
            'theme' => (string)$theme->get('Name'),
            'theme_version' => (string)$theme->get('Version'),
            'is_block_theme' => function_exists('wp_is_block_theme') ? (bool)wp_is_block_theme() : false,
            'permalink_structure' => (string)get_option('permalink_structure', ''),
            'https' => is_ssl(),
            'multisite' => is_multisite(),
            'native_abilities_api' => self::native_abilities_available(),
            'bridge_version' => THESIS_AI_BRIDGE_VERSION,
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
            return [
                'id' => (int)$post->ID,
                'title' => (string)get_the_title($post),
                'slug' => (string)$post->post_name,
                'status' => (string)$post->post_status,
                'author' => (int)$post->post_author,
                'url' => (string)get_permalink($post),
            ];
        }, $posts);
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

        return self::page_summary((int)$post_id);
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

        $existing = get_page_by_path($slug, OBJECT, 'page');
        if ($existing instanceof WP_Post) {
            if ((int)$existing->post_author !== get_current_user_id() || $existing->post_status !== 'draft') {
                return new WP_Error(
                    'thesis_ai_page_conflict',
                    __('A page with this slug exists, but it is not a draft owned by the current AI user. The bridge will not overwrite it.', 'thesis-ai-bridge'),
                    ['existing_page_id' => (int)$existing->ID]
                );
            }
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

        $result = [];
        foreach ($plugins as $file => $data) {
            $slug = self::plugin_slug_from_file($file);
            $result[] = [
                'file' => (string)$file,
                'slug' => $slug,
                'name' => (string)($data['Name'] ?? ''),
                'version' => (string)($data['Version'] ?? ''),
                'active' => is_plugin_active($file),
                'approved' => in_array($slug, $approved, true),
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

        $skin = new Automatic_Upgrader_Skin();
        $upgrader = new Plugin_Upgrader($skin);
        $result = $upgrader->install($download_link);
        if (is_wp_error($result)) {
            return $result;
        }
        if (!$result) {
            return new WP_Error('thesis_ai_plugin_install_failed', __('Plugin installation failed. The host may require filesystem credentials or may not allow writes.', 'thesis-ai-bridge'));
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
                'url' => ['type' => 'string'],
                'wordpress_version' => ['type' => 'string'],
                'php_version' => ['type' => 'string'],
                'theme' => ['type' => 'string'],
                'theme_version' => ['type' => 'string'],
                'is_block_theme' => ['type' => 'boolean'],
                'permalink_structure' => ['type' => 'string'],
                'https' => ['type' => 'boolean'],
                'multisite' => ['type' => 'boolean'],
                'native_abilities_api' => ['type' => 'boolean'],
                'bridge_version' => ['type' => 'string'],
            ],
            'required' => ['name', 'url', 'wordpress_version', 'php_version', 'theme', 'theme_version', 'is_block_theme', 'permalink_structure', 'https', 'multisite', 'native_abilities_api', 'bridge_version'],
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
                ],
                'required' => ['file', 'slug', 'name', 'version', 'active', 'approved'],
                'additionalProperties' => false,
            ],
        ];
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
