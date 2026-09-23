<?php

declare(strict_types=1);

if (!defined('ABSPATH')) {
    exit;
}

final class Thesis_AI_Bridge_Admin {
    private const OPTION_SETTINGS = 'thesis_ai_bridge_settings';
    private const OPTION_BACKEND_URL = 'thesis_ai_bridge_backend_url';

    public static function init(): void {
        add_action('admin_menu', [self::class, 'admin_menu']);
        add_action('admin_init', [self::class, 'register_settings']);
        add_action('admin_post_thesis_ai_connect', [self::class, 'connect']);
        add_action('admin_post_thesis_ai_disconnect', [self::class, 'disconnect']);
        add_action('admin_post_thesis_ai_check', [self::class, 'check']);
        add_action('admin_post_thesis_ai_build', [self::class, 'build']);
        add_action('admin_post_thesis_ai_demo_build', [self::class, 'demo_build']);
        add_action('admin_notices', [self::class, 'abilities_notice']);
    }

    public static function admin_menu(): void {
        add_menu_page(
            __('AI Website Builder', 'thesis-ai-bridge'),
            __('AI Website Builder', 'thesis-ai-bridge'),
            'manage_options',
            'thesis-ai-builder',
            [self::class, 'render_page'],
            'dashicons-superhero-alt',
            58
        );
    }

    public static function register_settings(): void {
        register_setting(
            'thesis_ai_bridge_settings_group',
            self::OPTION_SETTINGS,
            [
                'type' => 'array',
                'sanitize_callback' => ['Thesis_AI_Bridge', 'sanitize_settings'],
                'default' => Thesis_AI_Bridge::default_settings(),
            ]
        );
        register_setting(
            'thesis_ai_backend_group',
            self::OPTION_BACKEND_URL,
            [
                'type' => 'string',
                'sanitize_callback' => 'esc_url_raw',
                'default' => defined('THESIS_AI_CLOUD_URL') ? (string)THESIS_AI_CLOUD_URL : '',
            ]
        );
    }

    public static function abilities_notice(): void {
        if (!current_user_can('manage_options') || Thesis_AI_Bridge::native_abilities_available()) {
            return;
        }
        echo '<div class="notice notice-info"><p>';
        echo esc_html__('AI Website Builder: WordPress Abilities API is unavailable on this WordPress version, so the plugin will use its secure fallback REST bridge. WordPress 6.9+ is recommended for the native Abilities API.', 'thesis-ai-bridge');
        echo '</p></div>';
    }

    public static function connect(): void {
        self::require_admin('thesis_ai_connect');
        $backend = isset($_POST['backend_url']) ? esc_url_raw(wp_unslash((string)$_POST['backend_url'])) : '';
        update_option(self::OPTION_BACKEND_URL, $backend, false);
        $result = Thesis_AI_Cloud::connect($backend);
        self::redirect_with_result('connect', $result);
    }

    public static function disconnect(): void {
        self::require_admin('thesis_ai_disconnect');
        $result = Thesis_AI_Cloud::disconnect();
        self::redirect_with_result('disconnect', $result);
    }

    public static function check(): void {
        self::require_admin('thesis_ai_check');
        $result = Thesis_AI_Cloud::check_connection();
        self::redirect_with_result('check', $result);
    }

    public static function build(): void {
        self::require_admin('thesis_ai_build');
        $prompt = isset($_POST['website_prompt']) ? sanitize_textarea_field(wp_unslash((string)$_POST['website_prompt'])) : '';
        $result = Thesis_AI_Cloud::build($prompt);
        self::redirect_with_result('build', $result);
    }

    public static function demo_build(): void {
        self::require_admin('thesis_ai_demo_build');
        $prompt = isset($_POST['website_prompt']) ? sanitize_textarea_field(wp_unslash((string)$_POST['website_prompt'])) : '';
        $result = Thesis_AI_Cloud::demo_build($prompt);
        self::redirect_with_result('demo', $result);
    }

    public static function render_page(): void {
        if (!current_user_can('manage_options')) {
            return;
        }
        $connected = Thesis_AI_Cloud::is_connected();
        $connection = Thesis_AI_Cloud::connection();
        $last_build = Thesis_AI_Cloud::last_build();
        $settings = Thesis_AI_Bridge::get_settings();
        $status = Thesis_AI_Bridge::status_payload();
        $backend_url = (string)get_option(self::OPTION_BACKEND_URL, defined('THESIS_AI_CLOUD_URL') ? (string)THESIS_AI_CLOUD_URL : '');
        $message = isset($_GET['thesis_ai_message']) ? sanitize_text_field(wp_unslash((string)$_GET['thesis_ai_message'])) : '';
        $error = isset($_GET['thesis_ai_error']) ? sanitize_text_field(wp_unslash((string)$_GET['thesis_ai_error'])) : '';
        ?>
        <div class="wrap thesis-ai-wrap">
            <style>
                .thesis-ai-wrap{max-width:1100px}.thesis-ai-hero{background:#fff;border:1px solid #dcdcde;border-radius:10px;padding:24px;margin:18px 0}.thesis-ai-status{display:inline-flex;align-items:center;gap:8px;font-weight:600}.thesis-ai-dot{width:10px;height:10px;border-radius:50%;background:#b32d2e}.thesis-ai-dot.on{background:#00a32a}.thesis-ai-grid{display:grid;grid-template-columns:2fr 1fr;gap:20px}.thesis-ai-card{background:#fff;border:1px solid #dcdcde;border-radius:10px;padding:20px}.thesis-ai-card h2{margin-top:0}.thesis-ai-prompt{width:100%;min-height:150px;font-size:16px;padding:12px}.thesis-ai-muted{color:#646970}.thesis-ai-result ul{margin-left:20px;list-style:disc}.thesis-ai-chip{display:inline-block;background:#f0f0f1;border-radius:999px;padding:5px 9px;margin:2px;font-size:12px}@media(max-width:800px){.thesis-ai-grid{grid-template-columns:1fr}}
            </style>
            <h1><?php echo esc_html__('AI Website Builder', 'thesis-ai-bridge'); ?></h1>
            <p class="thesis-ai-muted"><?php echo esc_html__('Опиши сайт — п’ять спеціалізованих агентів спланують, побудують і перевірять WordPress-версію через контрольований Bridge.', 'thesis-ai-bridge'); ?></p>

            <?php if ($message) : ?><div class="notice notice-success is-dismissible"><p><?php echo esc_html($message); ?></p></div><?php endif; ?>
            <?php if ($error) : ?><div class="notice notice-error is-dismissible"><p><?php echo esc_html($error); ?></p></div><?php endif; ?>

            <div class="thesis-ai-hero">
                <div class="thesis-ai-status"><span class="thesis-ai-dot <?php echo $connected ? 'on' : ''; ?>"></span><?php echo esc_html($connected ? __('AI Builder підключено', 'thesis-ai-bridge') : __('AI Builder ще не підключено', 'thesis-ai-bridge')); ?></div>
                <?php if ($connected) : ?>
                    <p><?php printf(esc_html__('WordPress підключений через окремого технічного користувача %s. Основний пароль адміністратора нікуди не передається.', 'thesis-ai-bridge'), '<strong>' . esc_html((string)($connection['service_username'] ?? '')) . '</strong>'); ?></p>
                    <form style="display:inline-block;margin-right:8px" method="post" action="<?php echo esc_url(admin_url('admin-post.php')); ?>"><input type="hidden" name="action" value="thesis_ai_check"><?php wp_nonce_field('thesis_ai_check'); ?><?php submit_button(__('Перевірити з’єднання', 'thesis-ai-bridge'), 'secondary', 'submit', false); ?></form>
                    <form style="display:inline-block" method="post" action="<?php echo esc_url(admin_url('admin-post.php')); ?>"><input type="hidden" name="action" value="thesis_ai_disconnect"><?php wp_nonce_field('thesis_ai_disconnect'); ?><?php submit_button(__('Відключити', 'thesis-ai-bridge'), 'link-delete', 'submit', false); ?></form>
                <?php else : ?>
                    <p><?php echo esc_html__('Для продуктового сценарію користувач натискає одну кнопку. У цій тестовій збірці адресу backend треба вказати один раз, доки ми не розгорнули постійний cloud endpoint.', 'thesis-ai-bridge'); ?></p>
                    <form method="post" action="<?php echo esc_url(admin_url('admin-post.php')); ?>">
                        <input type="hidden" name="action" value="thesis_ai_connect"><?php wp_nonce_field('thesis_ai_connect'); ?>
                        <details <?php echo $backend_url === '' ? 'open' : ''; ?>><summary><strong><?php echo esc_html__('Advanced: адреса backend для prototype', 'thesis-ai-bridge'); ?></strong></summary><p><input type="url" name="backend_url" class="regular-text code" style="width:100%;max-width:650px" value="<?php echo esc_attr($backend_url); ?>" placeholder="https://ai-backend.example.com" required></p><p class="description"><?php echo esc_html__('У фінальному продукті ця адреса буде вбудована в плагін і користувач її не вводитиме.', 'thesis-ai-bridge'); ?></p></details>
                        <?php submit_button(__('Підключити AI Builder', 'thesis-ai-bridge'), 'primary', 'submit', false); ?>
                    </form>
                <?php endif; ?>
            </div>

            <div class="thesis-ai-grid">
                <div class="thesis-ai-card">
                    <h2><?php echo esc_html__('Створити сайт', 'thesis-ai-bridge'); ?></h2>
                    <form method="post" action="<?php echo esc_url(admin_url('admin-post.php')); ?>">
                        <input type="hidden" name="action" value="<?php echo $connected ? 'thesis_ai_build' : 'thesis_ai_demo_build'; ?>">
                        <?php wp_nonce_field($connected ? 'thesis_ai_build' : 'thesis_ai_demo_build'); ?>
                        <textarea class="thesis-ai-prompt" name="website_prompt" placeholder="Наприклад: Створи сучасний сайт стоматології українською мовою. Потрібні Головна, Послуги, Лікарі, Про нас, Контакти та форма запису." required></textarea>
                        <p class="description"><?php echo $connected ? esc_html__('Буде запущено реальний 5-агентний workflow. У v0.3 сторінки залишаються draft і не публікуються автоматично.', 'thesis-ai-bridge') : esc_html__('Backend ще не підключений, тому кнопка запустить локальне демо execution layer. Воно НЕ є запуском п’яти AI-агентів.', 'thesis-ai-bridge'); ?></p>
                        <?php submit_button($connected ? __('Створити сайт', 'thesis-ai-bridge') : __('Спробувати локальне демо', 'thesis-ai-bridge'), $connected ? 'primary' : 'secondary', 'submit', false); ?>
                    </form>
                </div>
                <div class="thesis-ai-card">
                    <h2><?php echo esc_html__('Що захищає сайт', 'thesis-ai-bridge'); ?></h2>
                    <p><span class="thesis-ai-chip">Least privilege</span><span class="thesis-ai-chip">Application Password</span><span class="thesis-ai-chip">Policy Engine</span><span class="thesis-ai-chip">Draft-first</span><span class="thesis-ai-chip">Allowlist plugins</span><span class="thesis-ai-chip">Audit log</span></p>
                    <p class="thesis-ai-muted"><?php echo esc_html__('Builder не отримує SSH, raw SQL або shell. Невідомі abilities блокуються за принципом default deny.', 'thesis-ai-bridge'); ?></p>
                </div>
            </div>

            <?php if ($last_build) : self::render_last_build($last_build); endif; ?>

            <div class="thesis-ai-card" style="margin-top:20px">
                <h2><?php echo esc_html__('Безпека та розширені дозволи', 'thesis-ai-bridge'); ?></h2>
                <p class="thesis-ai-muted"><?php echo esc_html__('Для звичайного business-сайту ці перемикачі можна не чіпати. Вони потрібні лише для дій підвищеного ризику.', 'thesis-ai-bridge'); ?></p>
                <form method="post" action="options.php">
                    <?php settings_fields('thesis_ai_bridge_settings_group'); ?>
                    <table class="form-table" role="presentation">
                        <?php self::checkbox_row('external_api_enabled', __('Дозволити зовнішній Bridge API', 'thesis-ai-bridge'), __('Потрібно для підключеного backend.', 'thesis-ai-bridge'), $settings); ?>
                        <?php self::checkbox_row('existing_page_updates_enabled', __('Дозволити змінювати існуючі сторінки', 'thesis-ai-bridge'), __('Вимкнено за замовчуванням. Власні AI draft можна оновлювати без цього.', 'thesis-ai-bridge'), $settings); ?>
                        <?php self::checkbox_row('site_settings_enabled', __('Дозволити змінювати налаштування сайту', 'thesis-ai-bridge'), __('Наприклад, призначити статичну головну сторінку.', 'thesis-ai-bridge'), $settings); ?>
                        <?php self::checkbox_row('plugin_management_enabled', __('Дозволити approved plugins', 'thesis-ai-bridge'), __('Дозволяє встановлення/активацію лише plugin-ів із вбудованого allowlist WordPress.org.', 'thesis-ai-bridge'), $settings); ?>
                    </table>
                    <?php submit_button(__('Зберегти дозволи', 'thesis-ai-bridge')); ?>
                </form>
                <details><summary><strong><?php echo esc_html__('Діагностика', 'thesis-ai-bridge'); ?></strong></summary>
                    <table class="widefat striped" style="max-width:900px;margin-top:12px"><tbody>
                        <?php self::row('Bridge', (string)$status['bridge_version']); ?>
                        <?php self::row('WordPress', (string)$status['wordpress_version']); ?>
                        <?php self::row('PHP', (string)$status['php_version']); ?>
                        <?php self::row('HTTPS', $status['https'] ? 'Yes' : 'No'); ?>
                        <?php self::row('Native Abilities API', $status['native_abilities_api'] ? 'Available' : 'Fallback REST'); ?>
                    </tbody></table>
                </details>
            </div>
        </div>
        <?php
    }

    private static function render_last_build(array $build): void {
        $pages = isset($build['pages']) && is_array($build['pages']) ? $build['pages'] : [];
        $issues = isset($build['issues']) && is_array($build['issues']) ? $build['issues'] : [];
        ?>
        <div class="thesis-ai-card thesis-ai-result" style="margin-top:20px">
            <h2><?php echo esc_html__('Останній результат', 'thesis-ai-bridge'); ?></h2>
            <p><strong><?php echo esc_html__('Статус:', 'thesis-ai-bridge'); ?></strong> <?php echo esc_html((string)($build['status'] ?? 'unknown')); ?></p>
            <?php if (!empty($build['quality_summary'])) : ?><p><?php echo esc_html((string)$build['quality_summary']); ?></p><?php endif; ?>
            <?php if ($pages) : ?><h3><?php echo esc_html__('Сторінки', 'thesis-ai-bridge'); ?></h3><ul><?php foreach ($pages as $page) : ?><li><?php echo esc_html((string)($page['title'] ?? ('Page #' . ($page['id'] ?? '')))); ?> — <?php echo esc_html((string)($page['status'] ?? 'draft')); ?><?php if (!empty($page['id'])) : ?> — <a href="<?php echo esc_url(get_edit_post_link((int)$page['id']) ?: '#'); ?>"><?php echo esc_html__('Редагувати', 'thesis-ai-bridge'); ?></a><?php endif; ?></li><?php endforeach; ?></ul><?php endif; ?>
            <?php if ($issues) : ?><h3><?php echo esc_html__('Проблеми / наступні дії', 'thesis-ai-bridge'); ?></h3><ul><?php foreach ($issues as $issue) : ?><li><strong><?php echo esc_html((string)($issue['severity'] ?? '')); ?></strong>: <?php echo esc_html((string)($issue['description'] ?? '')); ?></li><?php endforeach; ?></ul><?php endif; ?>
        </div>
        <?php
    }

    private static function require_admin(string $nonce_action): void {
        if (!current_user_can('manage_options')) {
            wp_die(esc_html__('Insufficient permissions.', 'thesis-ai-bridge'));
        }
        check_admin_referer($nonce_action);
    }

    private static function redirect_with_result(string $action, mixed $result): void {
        $args = ['page' => 'thesis-ai-builder'];
        if (is_wp_error($result)) {
            $args['thesis_ai_error'] = $result->get_error_message();
        } else {
            $messages = [
                'connect' => __('AI Builder підключено. Тепер можна описати сайт і запустити build.', 'thesis-ai-bridge'),
                'disconnect' => __('AI Builder відключено, а Application Password відкликано.', 'thesis-ai-bridge'),
                'check' => __('З’єднання з backend і WordPress Bridge працює.', 'thesis-ai-bridge'),
                'build' => __('Multi-agent build завершив поточний цикл. Результат показано нижче.', 'thesis-ai-bridge'),
                'demo' => __('Локальне демо завершено. Створено лише безпечні draft-сторінки.', 'thesis-ai-bridge'),
            ];
            $args['thesis_ai_message'] = $messages[$action] ?? __('Готово.', 'thesis-ai-bridge');
        }
        wp_safe_redirect(add_query_arg($args, admin_url('admin.php')));
        exit;
    }

    private static function row(string $label, string $value): void {
        echo '<tr><th style="width:260px">' . esc_html($label) . '</th><td>' . esc_html($value) . '</td></tr>';
    }

    private static function checkbox_row(string $key, string $label, string $description, array $settings): void {
        $name = self::OPTION_SETTINGS . '[' . $key . ']';
        ?>
        <tr><th scope="row"><?php echo esc_html($label); ?></th><td><label><input type="checkbox" name="<?php echo esc_attr($name); ?>" value="1" <?php checked(!empty($settings[$key])); ?>> <?php echo esc_html($description); ?></label></td></tr>
        <?php
    }
}
