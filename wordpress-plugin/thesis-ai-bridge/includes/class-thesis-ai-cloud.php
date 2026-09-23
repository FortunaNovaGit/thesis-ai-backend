<?php

declare(strict_types=1);

if (!defined('ABSPATH')) {
    exit;
}

final class Thesis_AI_Cloud {
    private const OPTION_CONNECTION = 'thesis_ai_bridge_connection';
    private const OPTION_LAST_BUILD = 'thesis_ai_bridge_last_build';
    private const USER_META_SERVICE = '_thesis_ai_service_user';
    private const USER_META_APP_UUID = '_thesis_ai_app_password_uuid';

    public static function connection(): array {
        $value = get_option(self::OPTION_CONNECTION, []);
        $value = is_array($value) ? $value : [];
        unset($value['site_token_encrypted']);
        return $value;
    }

    private static function full_connection(): array {
        $value = get_option(self::OPTION_CONNECTION, []);
        $value = is_array($value) ? $value : [];
        if (!empty($value['site_token_encrypted'])) {
            $token = self::decrypt_secret((string)$value['site_token_encrypted']);
            if (!is_wp_error($token)) {
                $value['site_token'] = $token;
            }
        }
        return $value;
    }

    public static function is_connected(): bool {
        $c = self::full_connection();
        return !empty($c['backend_url']) && !empty($c['site_id']) && !empty($c['site_token']);
    }

    public static function last_build(): array {
        $value = get_option(self::OPTION_LAST_BUILD, []);
        return is_array($value) ? $value : [];
    }

    public static function connect(string $backend_url): array|WP_Error {
        if (!current_user_can('manage_options')) {
            return new WP_Error('thesis_ai_forbidden', __('Administrator permissions are required.', 'thesis-ai-bridge'));
        }

        $backend_url = self::normalize_backend_url($backend_url);
        if (is_wp_error($backend_url)) {
            return $backend_url;
        }
        if (!wp_is_application_passwords_available()) {
            return new WP_Error('thesis_ai_app_passwords_unavailable', __('WordPress Application Passwords are unavailable. Use HTTPS and ensure they are not disabled by site policy.', 'thesis-ai-bridge'));
        }

        // Clicking Connect is explicit consent to expose only this plugin's authenticated
        // Bridge API. Other high-risk switches remain unchanged/off by default.
        $bridge_settings = Thesis_AI_Bridge::get_settings();
        $bridge_settings['external_api_enabled'] = true;
        update_option('thesis_ai_bridge_settings', $bridge_settings, false);

        // Reconnecting revokes only the previous credential created by this plugin.
        self::revoke_local_application_password();

        $user = self::ensure_service_user();
        if (is_wp_error($user)) {
            return $user;
        }

        $created = WP_Application_Passwords::create_new_application_password(
            (int)$user->ID,
            [
                'name' => 'Thesis AI Backend',
                'app_id' => wp_generate_uuid4(),
            ]
        );
        if (is_wp_error($created)) {
            return $created;
        }

        $application_password = (string)$created[0];
        $password_meta = is_array($created[1] ?? null) ? $created[1] : [];
        $uuid = (string)($password_meta['uuid'] ?? '');
        if ($uuid !== '') {
            update_user_meta((int)$user->ID, self::USER_META_APP_UUID, $uuid);
        }

        $response = wp_remote_post(
            $backend_url . '/v1/sites/connect',
            [
                'timeout' => 25,
                'redirection' => 2,
                'headers' => [
                    'Content-Type' => 'application/json',
                    'Accept' => 'application/json',
                    'User-Agent' => 'Thesis-AI-Bridge/' . THESIS_AI_BRIDGE_VERSION,
                ],
                'body' => wp_json_encode([
                    'site_url' => home_url('/'),
                    'site_name' => get_bloginfo('name'),
                    'username' => (string)$user->user_login,
                    'application_password' => $application_password,
                    'bridge_version' => THESIS_AI_BRIDGE_VERSION,
                ]),
            ]
        );

        if (is_wp_error($response)) {
            self::revoke_local_application_password();
            return new WP_Error('thesis_ai_backend_unreachable', sprintf(__('Could not reach AI backend: %s', 'thesis-ai-bridge'), $response->get_error_message()));
        }

        $code = (int)wp_remote_retrieve_response_code($response);
        $body = json_decode((string)wp_remote_retrieve_body($response), true);
        if ($code < 200 || $code >= 300 || !is_array($body) || empty($body['site_id']) || empty($body['site_token'])) {
            self::revoke_local_application_password();
            $detail = is_array($body) ? (string)($body['detail'] ?? 'Backend rejected the connection.') : 'Backend returned an invalid response.';
            return new WP_Error('thesis_ai_backend_rejected', sprintf(__('AI backend connection failed: %s', 'thesis-ai-bridge'), $detail));
        }

        $encrypted_token = self::encrypt_secret(sanitize_text_field((string)$body['site_token']));
        if (is_wp_error($encrypted_token)) {
            self::revoke_local_application_password();
            return $encrypted_token;
        }

        $connection = [
            'backend_url' => $backend_url,
            'site_id' => sanitize_text_field((string)$body['site_id']),
            'site_token_encrypted' => $encrypted_token,
            'service_user_id' => (int)$user->ID,
            'service_username' => (string)$user->user_login,
            'app_password_uuid' => $uuid,
            'connected_at' => gmdate('c'),
            'last_checked_at' => gmdate('c'),
        ];
        update_option(self::OPTION_CONNECTION, $connection, false);
        return $connection;
    }

    public static function disconnect(): true|WP_Error {
        $connection = self::full_connection();
        if ($connection) {
            $backend_url = isset($connection['backend_url']) ? untrailingslashit((string)$connection['backend_url']) : '';
            $site_id = isset($connection['site_id']) ? (string)$connection['site_id'] : '';
            $site_token = isset($connection['site_token']) ? (string)$connection['site_token'] : '';
            if ($backend_url && $site_id && $site_token) {
                wp_remote_post(
                    $backend_url . '/v1/sites/' . rawurlencode($site_id) . '/disconnect',
                    [
                        'timeout' => 10,
                        'headers' => [
                            'Authorization' => 'Bearer ' . $site_token,
                            'Accept' => 'application/json',
                        ],
                    ]
                );
            }
        }

        self::revoke_local_application_password();
        delete_option(self::OPTION_CONNECTION);
        return true;
    }

    public static function check_connection(): array|WP_Error {
        $c = self::full_connection();
        if (!self::is_connected()) {
            return new WP_Error('thesis_ai_not_connected', __('AI Builder is not connected.', 'thesis-ai-bridge'));
        }
        $response = wp_remote_get(
            untrailingslashit((string)$c['backend_url']) . '/v1/sites/' . rawurlencode((string)$c['site_id']) . '/check',
            [
                'timeout' => 20,
                'headers' => [
                    'Authorization' => 'Bearer ' . (string)$c['site_token'],
                    'Accept' => 'application/json',
                ],
            ]
        );
        if (is_wp_error($response)) {
            return $response;
        }
        $code = (int)wp_remote_retrieve_response_code($response);
        $body = json_decode((string)wp_remote_retrieve_body($response), true);
        if ($code < 200 || $code >= 300 || !is_array($body)) {
            return new WP_Error('thesis_ai_check_failed', __('Connection check failed.', 'thesis-ai-bridge'));
        }
        $c['last_checked_at'] = gmdate('c');
        update_option(self::OPTION_CONNECTION, $c, false);
        return $body;
    }

    public static function build(string $prompt): array|WP_Error {
        $prompt = trim(wp_strip_all_tags($prompt));
        if (self::string_length($prompt) < 10) {
            return new WP_Error('thesis_ai_prompt_short', __('Please describe the website in a little more detail.', 'thesis-ai-bridge'));
        }
        if (self::string_length($prompt) > 6000) {
            return new WP_Error('thesis_ai_prompt_long', __('The website description is too long for this prototype.', 'thesis-ai-bridge'));
        }
        $c = self::full_connection();
        if (!self::is_connected()) {
            return new WP_Error('thesis_ai_not_connected', __('Connect AI Builder before starting a real multi-agent build.', 'thesis-ai-bridge'));
        }

        $response = wp_remote_post(
            untrailingslashit((string)$c['backend_url']) . '/v1/sites/' . rawurlencode((string)$c['site_id']) . '/build',
            [
                'timeout' => 120,
                'headers' => [
                    'Authorization' => 'Bearer ' . (string)$c['site_token'],
                    'Content-Type' => 'application/json',
                    'Accept' => 'application/json',
                    'User-Agent' => 'Thesis-AI-Bridge/' . THESIS_AI_BRIDGE_VERSION,
                ],
                'body' => wp_json_encode(['request' => $prompt]),
            ]
        );
        if (is_wp_error($response)) {
            return new WP_Error('thesis_ai_build_unreachable', sprintf(__('The AI backend did not finish the request: %s', 'thesis-ai-bridge'), $response->get_error_message()));
        }
        $code = (int)wp_remote_retrieve_response_code($response);
        $body = json_decode((string)wp_remote_retrieve_body($response), true);
        if ($code < 200 || $code >= 300 || !is_array($body)) {
            $detail = is_array($body) ? (string)($body['detail'] ?? 'Unknown backend error.') : 'Invalid backend response.';
            return new WP_Error('thesis_ai_build_failed', $detail);
        }
        $body['requested_at'] = gmdate('c');
        update_option(self::OPTION_LAST_BUILD, $body, false);
        return $body;
    }

    public static function demo_build(string $prompt): array|WP_Error {
        if (!current_user_can('manage_options')) {
            return new WP_Error('thesis_ai_forbidden', __('Administrator permissions are required.', 'thesis-ai-bridge'));
        }
        $prompt = trim(wp_strip_all_tags($prompt));
        if (self::string_length($prompt) < 5) {
            return new WP_Error('thesis_ai_prompt_short', __('Add a short website description for the demo.', 'thesis-ai-bridge'));
        }

        $lower = function_exists('mb_strtolower') ? mb_strtolower($prompt) : strtolower($prompt);
        $pages = [
            ['title' => 'Головна', 'slug' => 'ai-demo-home', 'sections' => ['Hero', 'Переваги', 'Заклик до дії']],
            ['title' => 'Про нас', 'slug' => 'ai-demo-about', 'sections' => ['Про проєкт', 'Цінності']],
            ['title' => 'Контакти', 'slug' => 'ai-demo-contact', 'sections' => ['Контакти', 'Форма зв’язку']],
        ];
        if (str_contains($lower, 'послуг') || str_contains($lower, 'service')) {
            array_splice($pages, 1, 0, [[ 'title' => 'Послуги', 'slug' => 'ai-demo-services', 'sections' => ['Послуги', 'FAQ', 'CTA'] ]]);
        }
        if (str_contains($lower, 'магазин') || str_contains($lower, 'shop') || str_contains($lower, 'store')) {
            array_splice($pages, 1, 0, [[ 'title' => 'Магазин', 'slug' => 'ai-demo-shop', 'sections' => ['Каталог', 'Переваги', 'CTA'] ]]);
        }

        $created = [];
        foreach ($pages as $page) {
            $parts = [];
            $parts[] = '<!-- wp:paragraph {"backgroundColor":"tertiary"} --><p class="has-tertiary-background-color has-background"><strong>LOCAL DEMO:</strong> ця сторінка створена локальним тестом execution layer. П’ять AI-агентів у цьому режимі не запускались.</p><!-- /wp:paragraph -->';
            $parts[] = '<!-- wp:heading {"level":1} --><h1 class="wp-block-heading">' . esc_html((string)$page['title']) . '</h1><!-- /wp:heading -->';
            foreach ((array)$page['sections'] as $section) {
                $parts[] = '<!-- wp:group {"layout":{"type":"constrained"}} --><div class="wp-block-group"><!-- wp:heading --><h2 class="wp-block-heading">' . esc_html((string)$section) . '</h2><!-- /wp:heading --><!-- wp:paragraph --><p>Тестовий редагований Gutenberg-контент для опису: ' . esc_html($prompt) . '</p><!-- /wp:paragraph --></div><!-- /wp:group -->';
            }
            $result = Thesis_AI_Bridge::execute_named_ability('ensure-draft-page', [
                'title' => (string)$page['title'],
                'slug' => (string)$page['slug'],
                'content' => implode("\n", $parts),
            ]);
            if (is_wp_error($result)) {
                return $result;
            }
            $created[] = $result;
        }

        $result = [
            'status' => 'demo_completed',
            'mode' => 'local_demo',
            'pages' => $created,
            'quality_summary' => 'Локальне демо перевіряє лише безпечне створення Gutenberg draft-сторінок. Multi-agent backend і реальний QA не запускались.',
            'requested_at' => gmdate('c'),
        ];
        update_option(self::OPTION_LAST_BUILD, $result, false);
        return $result;
    }

    private static function string_length(string $value): int {
        return function_exists('mb_strlen') ? (int)mb_strlen($value) : strlen($value);
    }

    private static function encrypt_secret(string $plain): string|WP_Error {
        $key = hash('sha256', wp_salt('auth') . '|thesis-ai-bridge-v0.3', true);
        if (function_exists('sodium_crypto_secretbox')) {
            $nonce = random_bytes(SODIUM_CRYPTO_SECRETBOX_NONCEBYTES);
            $cipher = sodium_crypto_secretbox($plain, $nonce, $key);
            return 'sodium:' . base64_encode($nonce . $cipher);
        }
        if (function_exists('openssl_encrypt')) {
            $iv = random_bytes(12);
            $tag = '';
            $cipher = openssl_encrypt($plain, 'aes-256-gcm', $key, OPENSSL_RAW_DATA, $iv, $tag);
            if ($cipher === false) {
                return new WP_Error('thesis_ai_secret_encrypt', __('Could not protect the backend token.', 'thesis-ai-bridge'));
            }
            return 'openssl:' . base64_encode($iv . $tag . $cipher);
        }
        return new WP_Error('thesis_ai_crypto_missing', __('The server needs Sodium or OpenSSL to protect the backend token.', 'thesis-ai-bridge'));
    }

    private static function decrypt_secret(string $sealed): string|WP_Error {
        $key = hash('sha256', wp_salt('auth') . '|thesis-ai-bridge-v0.3', true);
        if (str_starts_with($sealed, 'sodium:') && function_exists('sodium_crypto_secretbox_open')) {
            $raw = base64_decode(substr($sealed, 7), true);
            if ($raw === false || strlen($raw) <= SODIUM_CRYPTO_SECRETBOX_NONCEBYTES) {
                return new WP_Error('thesis_ai_secret_invalid', __('Stored backend token is invalid.', 'thesis-ai-bridge'));
            }
            $nonce = substr($raw, 0, SODIUM_CRYPTO_SECRETBOX_NONCEBYTES);
            $cipher = substr($raw, SODIUM_CRYPTO_SECRETBOX_NONCEBYTES);
            $plain = sodium_crypto_secretbox_open($cipher, $nonce, $key);
            return $plain === false ? new WP_Error('thesis_ai_secret_decrypt', __('Could not decrypt the backend token.', 'thesis-ai-bridge')) : $plain;
        }
        if (str_starts_with($sealed, 'openssl:') && function_exists('openssl_decrypt')) {
            $raw = base64_decode(substr($sealed, 8), true);
            if ($raw === false || strlen($raw) <= 28) {
                return new WP_Error('thesis_ai_secret_invalid', __('Stored backend token is invalid.', 'thesis-ai-bridge'));
            }
            $iv = substr($raw, 0, 12);
            $tag = substr($raw, 12, 16);
            $cipher = substr($raw, 28);
            $plain = openssl_decrypt($cipher, 'aes-256-gcm', $key, OPENSSL_RAW_DATA, $iv, $tag);
            return $plain === false ? new WP_Error('thesis_ai_secret_decrypt', __('Could not decrypt the backend token.', 'thesis-ai-bridge')) : $plain;
        }
        return new WP_Error('thesis_ai_secret_format', __('Stored backend token uses an unsupported protection format.', 'thesis-ai-bridge'));
    }

    private static function normalize_backend_url(string $backend_url): string|WP_Error {
        $backend_url = untrailingslashit(esc_url_raw(trim($backend_url)));
        if ($backend_url === '') {
            return new WP_Error('thesis_ai_backend_missing', __('Backend URL is required in this prototype build.', 'thesis-ai-bridge'));
        }
        $scheme = strtolower((string)wp_parse_url($backend_url, PHP_URL_SCHEME));
        $host = strtolower((string)wp_parse_url($backend_url, PHP_URL_HOST));
        if ($scheme === 'https') {
            return $backend_url;
        }
        if ($scheme === 'http' && in_array($host, ['localhost', '127.0.0.1', '::1'], true)) {
            return $backend_url;
        }
        if (defined('THESIS_AI_ALLOW_INSECURE_BACKEND') && THESIS_AI_ALLOW_INSECURE_BACKEND) {
            return $backend_url;
        }
        return new WP_Error('thesis_ai_backend_https', __('The AI backend must use HTTPS.', 'thesis-ai-bridge'));
    }

    private static function ensure_service_user(): WP_User|WP_Error {
        $users = get_users([
            'meta_key' => self::USER_META_SERVICE,
            'meta_value' => '1',
            'number' => 1,
            'count_total' => false,
        ]);
        if ($users && $users[0] instanceof WP_User) {
            $user = $users[0];
            $user->set_role('thesis_ai_builder');
            return $user;
        }

        $base = 'thesis_ai_builder';
        $login = $base;
        $suffix = 2;
        while (username_exists($login)) {
            $login = $base . '_' . $suffix;
            $suffix++;
        }
        $user_id = wp_insert_user([
            'user_login' => $login,
            'user_pass' => wp_generate_password(48, true, true),
            'display_name' => 'Thesis AI Builder',
            'role' => 'thesis_ai_builder',
        ]);
        if (is_wp_error($user_id)) {
            return $user_id;
        }
        update_user_meta((int)$user_id, self::USER_META_SERVICE, '1');
        return get_user_by('id', (int)$user_id) ?: new WP_Error('thesis_ai_user_create_failed', __('Could not load the AI service user.', 'thesis-ai-bridge'));
    }

    private static function revoke_local_application_password(): void {
        $connection = self::connection();
        $user_id = (int)($connection['service_user_id'] ?? 0);
        $uuid = (string)($connection['app_password_uuid'] ?? '');

        if ($user_id <= 0) {
            $users = get_users([
                'meta_key' => self::USER_META_SERVICE,
                'meta_value' => '1',
                'number' => 1,
                'count_total' => false,
            ]);
            if ($users && $users[0] instanceof WP_User) {
                $user_id = (int)$users[0]->ID;
                $uuid = (string)get_user_meta($user_id, self::USER_META_APP_UUID, true);
            }
        }

        if ($user_id > 0 && $uuid !== '' && class_exists('WP_Application_Passwords')) {
            WP_Application_Passwords::delete_application_password($user_id, $uuid);
            delete_user_meta($user_id, self::USER_META_APP_UUID);
        }
    }
}
