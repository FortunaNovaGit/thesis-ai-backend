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
        add_action('admin_enqueue_scripts', [self::class, 'enqueue_assets']);
        add_action('admin_post_thesis_ai_connect', [self::class, 'connect']);
        add_action('admin_post_thesis_ai_disconnect', [self::class, 'disconnect']);
        add_action('admin_post_thesis_ai_check', [self::class, 'check']);
        add_action('admin_post_thesis_ai_build', [self::class, 'build']);
        add_action('admin_post_thesis_ai_demo_build', [self::class, 'demo_build']);
        add_action('admin_post_thesis_ai_publish_build', [self::class, 'publish_build']);
        add_action('wp_ajax_thesis_ai_build_status', [self::class, 'build_status']);
        add_action('wp_ajax_thesis_ai_save_ui_state', [self::class, 'save_ui_state']);
        add_action('wp_ajax_thesis_ai_preflight', [self::class, 'preflight']);
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

    public static function enqueue_assets(string $hook): void {
        if ($hook !== 'toplevel_page_thesis-ai-builder') {
            return;
        }
        wp_enqueue_style(
            'thesis-ai-admin',
            plugins_url('assets/admin.css', THESIS_AI_BRIDGE_FILE),
            [],
            THESIS_AI_BRIDGE_VERSION
        );
        wp_enqueue_script(
            'thesis-ai-admin',
            plugins_url('assets/admin.js', THESIS_AI_BRIDGE_FILE),
            [],
            THESIS_AI_BRIDGE_VERSION,
            true
        );
        wp_localize_script('thesis-ai-admin', 'ThesisAIAdmin', [
            'ajaxUrl' => admin_url('admin-ajax.php'),
            'statusNonce' => wp_create_nonce('thesis_ai_build_status'),
            'uiNonce' => wp_create_nonce('thesis_ai_save_ui_state'),
            'preflightNonce' => wp_create_nonce('thesis_ai_preflight'),
            'pollMs' => 1400,
            'hasActiveBuild' => !empty(Thesis_AI_Cloud::active_build()['job_id']),
            'labels' => [
                'ready' => __('Готово до запуску', 'thesis-ai-bridge'),
                'pollError' => __('Не вдалося оновити статус. Повторюємо автоматично…', 'thesis-ai-bridge'),
                'preflightRunning' => __('Перевіряємо WordPress…', 'thesis-ai-bridge'),
                'preflightDone' => __('Preflight завершено', 'thesis-ai-bridge'),
            ],
        ]);
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
        $screen = get_current_screen();
        if ($screen && $screen->id === 'toplevel_page_thesis-ai-builder') {
            return; // Diagnostics are shown inside the dashboard instead of a noisy global notice.
        }
        echo '<div class="notice notice-info"><p>';
        echo esc_html__('AI Website Builder: WordPress Abilities API is unavailable, so the secure fallback bridge is active.', 'thesis-ai-bridge');
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

    /** Optional facts complement a free prompt; they never authorize invented claims. */
    private static function collect_optional_brief(array $input): array {
        $fields = [
            'brand' => 100, 'site_type' => 100, 'audience' => 160,
            'pages' => 220, 'style' => 160, 'facts' => 480,
        ];
        $brief = [];
        foreach ($fields as $key => $limit) {
            $raw = isset($input['brief_' . $key]) && is_scalar($input['brief_' . $key])
                ? (string)wp_unslash((string)$input['brief_' . $key]) : '';
            $value = sanitize_text_field($raw);
            $brief[$key] = function_exists('mb_substr') ? mb_substr($value, 0, $limit) : substr($value, 0, $limit);
        }
        $raw_count = isset($input['brief_product_count']) && is_scalar($input['brief_product_count'])
            ? trim((string)wp_unslash((string)$input['brief_product_count'])) : '';
        $brief['product_count'] = $raw_count !== '' && preg_match('/^\d{1,4}$/', $raw_count)
            ? (string)min(1000, (int)$raw_count) : '';
        $raw_colors = isset($input['brief_colors']) && is_scalar($input['brief_colors'])
            ? (string)wp_unslash((string)$input['brief_colors']) : '';
        $brief['colors'] = preg_match('/^#[A-Fa-f0-9]{6}(\s*,\s*#[A-Fa-f0-9]{6}){0,3}$/', trim($raw_colors))
            ? trim($raw_colors) : '';
        $assets = isset($input['brief_assets']) && is_scalar($input['brief_assets'])
            ? sanitize_key(wp_unslash((string)$input['brief_assets'])) : '';
        $brief['assets'] = in_array($assets, ['existing', 'none', 'unsure'], true) ? $assets : 'unsure';
        return $brief;
    }

    private static function enrich_prompt(string $prompt, array $brief): string {
        $labels = [
            'brand' => 'Назва бренду', 'site_type' => 'Тип сайту',
            'audience' => 'Цільова аудиторія', 'pages' => 'Бажані сторінки',
            'product_count' => 'Очікувана кількість товарів у каталозі',
            'style' => 'Дизайн-побажання (AI сам проєктує структуру)',
            'colors' => 'Брендові кольори HEX',
            'facts' => 'ПІДТВЕРДЖЕНІ факти для відвідувачів',
        ];
        $lines = [];
        foreach ($labels as $key => $label) {
            if (!empty($brief[$key])) { $lines[] = $label . ': ' . $brief[$key]; }
        }
        if (($brief['assets'] ?? 'unsure') === 'none') {
            $lines[] = 'Власних фотографій немає. Не видавай абстрактну графіку за фото реального товару.';
        } elseif (($brief['assets'] ?? 'unsure') === 'existing') {
            $lines[] = 'Є власні медіа у бібліотеці WordPress: використовуй тільки придатні зображення.';
        }
        if (!$lines) { return $prompt; }
        $lines[] = 'Кількість товарів — планована місткість каталогу, не дозвіл вигадати товари, склад, ціни, залишки чи фото.';
        return trim($prompt) . "\n\n[Уточнені параметри від власника сайту]\n" . implode("\n", $lines);
    }

    public static function build(): void {
        self::require_admin('thesis_ai_build');
        $prompt = isset($_POST['website_prompt']) ? sanitize_textarea_field(wp_unslash((string)$_POST['website_prompt'])) : '';
        $renderer = isset($_POST['renderer']) ? sanitize_key(wp_unslash((string)$_POST['renderer'])) : 'elementor';
        $renderer = in_array($renderer, ['elementor', 'gutenberg', 'auto'], true) ? $renderer : 'elementor';
        $brief = self::collect_optional_brief($_POST);
        $full_prompt = self::enrich_prompt($prompt, $brief);
        if ((function_exists('mb_strlen') ? mb_strlen($full_prompt) : strlen($full_prompt)) > 6000) {
            self::redirect_with_result('build', new WP_Error('thesis_ai_brief_long', __('Опис і додаткові параметри перевищують 6000 символів. Скоротіть текст перед запуском.', 'thesis-ai-bridge')));
            return;
        }
        $allow_plugins = !empty($_POST['allow_approved_plugins']);
        $allow_setup = !empty($_POST['allow_site_setup']);

        $settings = Thesis_AI_Bridge::get_settings();
        $settings['plugin_management_enabled'] = $allow_plugins;
        $settings['site_settings_enabled'] = $allow_setup;
        update_option(self::OPTION_SETTINGS, Thesis_AI_Bridge::sanitize_settings($settings), false);
        Thesis_AI_Cloud::save_ui_state([
            'prompt' => $prompt,
            'brief' => $brief,
            'renderer' => $renderer,
            'allow_approved_plugins' => $allow_plugins,
            'allow_site_setup' => $allow_setup,
        ]);
        $result = Thesis_AI_Cloud::start_build($full_prompt, $renderer);
        self::redirect_with_result('build', $result);
    }

    public static function build_status(): void {
        if (!current_user_can('manage_options')) {
            wp_send_json_error(['message' => __('Insufficient permissions.', 'thesis-ai-bridge')], 403);
        }
        check_ajax_referer('thesis_ai_build_status', 'nonce');
        // v0.7.2: the browser is an observer, not the execution engine. A
        // WordPress background worker advances planning/actions/verification, so
        // leaving or refreshing this page no longer pauses the build.
        Thesis_AI_Cloud::ensure_worker();
        Thesis_AI_Cloud::nudge_if_stale(20);
        $result = Thesis_AI_Cloud::active_build();
        if (!$result) {
            wp_send_json_success([
                'build' => ['status' => 'completed', 'stage' => 'completed', 'progress' => 100, 'reload' => true],
                'events' => Thesis_AI_Cloud::event_log(),
            ]);
        }
        wp_send_json_success([
            'build' => $result,
            'events' => Thesis_AI_Cloud::event_log(),
        ]);
    }

    public static function save_ui_state(): void {
        if (!current_user_can('manage_options')) {
            wp_send_json_error(['message' => __('Insufficient permissions.', 'thesis-ai-bridge')], 403);
        }
        check_ajax_referer('thesis_ai_save_ui_state', 'nonce');
        $state = Thesis_AI_Cloud::save_ui_state([
            'prompt' => isset($_POST['prompt']) ? wp_unslash((string)$_POST['prompt']) : '',
            'brief' => self::collect_optional_brief($_POST),
            'renderer' => isset($_POST['renderer']) ? sanitize_key(wp_unslash((string)$_POST['renderer'])) : 'elementor',
            'allow_approved_plugins' => !empty($_POST['allow_approved_plugins']),
            'allow_site_setup' => !empty($_POST['allow_site_setup']),
        ]);
        wp_send_json_success(['state' => $state]);
    }

    public static function preflight(): void {
        if (!current_user_can('manage_options')) {
            wp_send_json_error(['message' => __('Insufficient permissions.', 'thesis-ai-bridge')], 403);
        }
        check_ajax_referer('thesis_ai_preflight', 'nonce');
        $result = Thesis_AI_Cloud::run_preflight();
        if (is_wp_error($result)) {
            wp_send_json_error(['message' => $result->get_error_message()], 200);
        }
        unset($result['snapshot']);
        wp_send_json_success($result);
    }

    public static function demo_build(): void {
        self::require_admin('thesis_ai_demo_build');
        $prompt = isset($_POST['website_prompt']) ? sanitize_textarea_field(wp_unslash((string)$_POST['website_prompt'])) : '';
        $result = Thesis_AI_Cloud::demo_build($prompt);
        self::redirect_with_result('demo', $result);
    }

    public static function publish_build(): void {
        self::require_admin('thesis_ai_publish_build');
        $result = Thesis_AI_Cloud::publish_last_build();
        self::redirect_with_result('publish', $result);
    }

    public static function render_page(): void {
        if (!current_user_can('manage_options')) {
            return;
        }
        $connected = Thesis_AI_Cloud::is_connected();
        $connection = Thesis_AI_Cloud::connection();
        $last_build = Thesis_AI_Cloud::last_build();
        $active_build = Thesis_AI_Cloud::active_build();
        $history = Thesis_AI_Cloud::build_history();
        if (!$history && $last_build) {
            $history = [$last_build];
        }
        $events = Thesis_AI_Cloud::event_log();
        $ui_state = Thesis_AI_Cloud::ui_state();
        $preflight = Thesis_AI_Cloud::last_preflight();
        $settings = Thesis_AI_Bridge::get_settings();
        $status = Thesis_AI_Bridge::status_payload();
        $backend_url = (string)get_option(self::OPTION_BACKEND_URL, defined('THESIS_AI_CLOUD_URL') ? (string)THESIS_AI_CLOUD_URL : '');
        $message = isset($_GET['thesis_ai_message']) ? sanitize_text_field(wp_unslash((string)$_GET['thesis_ai_message'])) : '';
        $error = isset($_GET['thesis_ai_error']) ? sanitize_text_field(wp_unslash((string)$_GET['thesis_ai_error'])) : '';
        // Keep the free-form text separate from appended structured constraints.
        $prompt = (string)($ui_state['prompt'] ?? ($active_build['prompt'] ?? ''));
        $brief = (array)($ui_state['brief'] ?? []);
        $renderer = (string)($active_build['renderer'] ?? ($ui_state['renderer'] ?? 'elementor'));
        $allow_plugins = array_key_exists('allow_approved_plugins', $ui_state) ? !empty($ui_state['allow_approved_plugins']) : !empty($settings['plugin_management_enabled']);
        $allow_setup = array_key_exists('allow_site_setup', $ui_state) ? !empty($ui_state['allow_site_setup']) : !empty($settings['site_settings_enabled']);
        $progress = max(0, min(100, (int)($active_build['progress'] ?? (($last_build['status'] ?? '') === 'passed' ? 100 : 0))));
        $stage = (string)($active_build['stage'] ?? (($last_build['status'] ?? '') === 'passed' ? 'completed' : 'idle'));
        $detail = (string)($active_build['detail'] ?? (($last_build['quality_summary'] ?? '') ?: __('Опишіть сайт і запустіть створення.', 'thesis-ai-bridge')));
        $planned_pages = self::planned_pages($active_build, $last_build);
        $agent_mode = (string)($connection['agent_mode'] ?? ($last_build['agent_mode'] ?? ''));
        $model = (string)($connection['model'] ?? ($last_build['model'] ?? ''));
        $model_router = (array)($connection['model_router'] ?? ($last_build['model_router'] ?? []));
        ?>
        <div class="wrap thesis-ai-app" id="thesis-ai-app" data-stage="<?php echo esc_attr($stage); ?>">
            <?php if ($message) : ?><div class="notice notice-success is-dismissible"><p><?php echo esc_html($message); ?></p></div><?php endif; ?>
            <?php if ($error) : ?><div class="notice notice-error is-dismissible"><p><?php echo esc_html($error); ?></p></div><?php endif; ?>

            <section class="tai-header">
                <div class="tai-brand">
                    <span class="tai-brand-mark"><span class="dashicons dashicons-superhero-alt"></span></span>
                    <div>
                        <h1>AI Website Builder</h1>
                        <p><?php echo esc_html__('Створюйте професійні WordPress-сайти за допомогою мультиагентної системи', 'thesis-ai-bridge'); ?></p>
                    </div>
                </div>
                <div class="tai-site-pill">
                    <span class="dashicons dashicons-admin-site-alt3"></span>
                    <div><strong><?php echo esc_html(get_bloginfo('name') ?: __('Поточний сайт', 'thesis-ai-bridge')); ?></strong><small><?php echo esc_html((string)wp_parse_url(home_url('/'), PHP_URL_HOST)); ?></small></div>
                </div>
            </section>

            <div class="tai-top-status">
                <span class="tai-badge <?php echo $connected ? 'is-success' : 'is-danger'; ?>"><i></i><?php echo esc_html($connected ? __('Backend підключено', 'thesis-ai-bridge') : __('Backend не підключено', 'thesis-ai-bridge')); ?></span>
                <?php if ($agent_mode !== '') : ?><span class="tai-badge"><span class="dashicons dashicons-admin-generic"></span><?php echo esc_html('Mode: ' . $agent_mode); ?></span><?php endif; ?>
                <?php if ($model !== '') : ?><span class="tai-badge"><span class="dashicons dashicons-editor-code"></span><?php echo esc_html($model === 'multi-model' ? __('Multi-model router', 'thesis-ai-bridge') : $model); ?></span><?php endif; ?>
                <span class="tai-badge is-success"><span class="dashicons dashicons-database"></span><?php echo esc_html__('Стан зберігається', 'thesis-ai-bridge'); ?></span>
                <?php if ($connected && array_key_exists('stable_connection_tokens', $connection) && empty($connection['stable_connection_tokens'])) : ?>
                    <span class="tai-badge is-warning"><span class="dashicons dashicons-update"></span><?php echo esc_html__('Token auto-repair', 'thesis-ai-bridge'); ?></span>
                <?php endif; ?>
                <span class="tai-badge"><span class="dashicons dashicons-wordpress"></span><?php echo esc_html('Bridge ' . THESIS_AI_BRIDGE_VERSION); ?></span>
                <details class="tai-connection-menu">
                    <summary><?php echo esc_html__('З’єднання', 'thesis-ai-bridge'); ?></summary>
                    <div class="tai-popover">
                        <?php self::render_connection_controls($connected, $backend_url, $connection); ?>
                    </div>
                </details>
            </div>

            <div class="tai-main-grid">
                <section class="tai-card tai-create-card">
                    <div class="tai-card-head"><div><h2><span class="dashicons dashicons-superhero"></span><?php echo esc_html__('Створити новий сайт', 'thesis-ai-bridge'); ?></h2><p><?php echo esc_html__('Опишіть результат людською мовою. Агенти проаналізують вимоги, підберуть capabilities та побудують сайт.', 'thesis-ai-bridge'); ?></p></div></div>
                    <form id="thesis-ai-build-form" method="post" action="<?php echo esc_url(admin_url('admin-post.php')); ?>">
                        <input type="hidden" name="action" value="<?php echo $connected ? 'thesis_ai_build' : 'thesis_ai_demo_build'; ?>">
                        <?php wp_nonce_field($connected ? 'thesis_ai_build' : 'thesis_ai_demo_build'); ?>
                        <div class="tai-prompt-wrap">
                            <textarea id="thesis-ai-prompt" name="website_prompt" maxlength="6000" placeholder="Наприклад: Створи сучасний сайт стоматологічної клініки українською. Потрібні Головна, Послуги, Лікарі, Про нас, Контакти та форма запису. Світлий дизайн, сині акценти, SEO." required><?php echo esc_textarea($prompt); ?></textarea>
                            <span id="thesis-ai-prompt-count" class="tai-counter"><?php echo esc_html((string)self::text_length($prompt)); ?>/6000</span>
                        </div>
                        <details class="tai-brief-panel" id="tai-brief-panel" <?php echo array_filter($brief, static fn($v) => (string)$v !== '' && (string)$v !== 'unsure') ? 'open' : ''; ?>>
                            <summary><span class="dashicons dashicons-admin-settings"></span><strong>Уточнити результат</strong><small>Необов'язково · більше конкретики — менше здогадів</small></summary>
                            <div class="tai-brief-body">
                                <p class="tai-brief-intro">Промпту достатньо для старту. Заповнюйте лише те, що знаєте: AI сам створить композицію, але не повинен вигадувати факти про бізнес.</p>
                                <div class="tai-brief-grid">
                                    <label><span>Бренд</span><input type="text" name="brief_brand" maxlength="100" placeholder="Наприклад, Fortuna Nova" value="<?php echo esc_attr((string)($brief['brand'] ?? '')); ?>"></label>
                                    <label><span>Тип сайту</span><input type="text" name="brief_site_type" maxlength="100" placeholder="Магазин, портфоліо, послуги…" value="<?php echo esc_attr((string)($brief['site_type'] ?? '')); ?>"></label>
                                    <label><span>Цільова аудиторія</span><input type="text" name="brief_audience" maxlength="160" placeholder="Кому і для чого потрібен сайт" value="<?php echo esc_attr((string)($brief['audience'] ?? '')); ?>"></label>
                                    <label><span>Потрібні сторінки</span><input type="text" name="brief_pages" maxlength="220" placeholder="Головна, Магазин, Контакти" value="<?php echo esc_attr((string)($brief['pages'] ?? '')); ?>"></label>
                                    <label><span>Кількість товарів у майбутньому каталозі</span><input type="number" name="brief_product_count" min="0" max="1000" placeholder="Наприклад, 24" value="<?php echo esc_attr((string)($brief['product_count'] ?? '')); ?>"></label>
                                    <label><span>Власні зображення</span><select name="brief_assets"><option value="unsure" <?php selected((string)($brief['assets'] ?? 'unsure'), 'unsure'); ?>>Ще не визначено</option><option value="existing" <?php selected((string)($brief['assets'] ?? ''), 'existing'); ?>>Є в медіабібліотеці WordPress</option><option value="none" <?php selected((string)($brief['assets'] ?? ''), 'none'); ?>>Поки немає</option></select></label>
                                    <label><span>Візуальний характер</span><input type="text" name="brief_style" maxlength="160" placeholder="AI обирає сам або коротка творча підказка" value="<?php echo esc_attr((string)($brief['style'] ?? '')); ?>"></label>
                                    <label><span>Брендові кольори, за бажанням</span><input type="text" name="brief_colors" pattern="#[0-9a-fA-F]{6}(,\s*#[0-9a-fA-F]{6}){0,3}" placeholder="#35221D, #EACD9B" value="<?php echo esc_attr((string)($brief['colors'] ?? '')); ?>"><small>HEX, до чотирьох кольорів. Без заповнення палітру обирає AI.</small></label>
                                    <label class="tai-brief-wide"><span>Лише підтверджені факти</span><textarea name="brief_facts" rows="3" maxlength="480" placeholder="Наприклад, назви реальних товарів, підтверджені особливості виробництва, адреса — тільки якщо достовірно відома"><?php echo esc_textarea((string)($brief['facts'] ?? '')); ?></textarea></label>
                                </div>
                                <div class="tai-brief-note"><span class="dashicons dashicons-info-outline"></span><span>Це не імпорт каталогу: поточний WooCommerce Builder може створювати лише обмежену кількість демо-чернеток за явними назвами. Фото товарів, ціни, склад та залишки треба підтвердити окремо. Сторінки залишаються Draft.</span></div>
                            </div>
                        </details>
                        <?php if ($connected) : ?>
                            <div class="tai-build-options">
                                <label class="tai-field"><span><?php echo esc_html__('Конструктор сторінок', 'thesis-ai-bridge'); ?></span><select id="thesis-ai-renderer" name="renderer"><option value="elementor" <?php selected($renderer, 'elementor'); ?>>Elementor Free</option><option value="gutenberg" <?php selected($renderer, 'gutenberg'); ?>>Gutenberg</option><option value="auto" <?php selected($renderer, 'auto'); ?>>Auto</option></select></label>
                                <div class="tai-checks">
                                    <label><input id="thesis-ai-allow-plugins" type="checkbox" name="allow_approved_plugins" value="1" <?php checked($allow_plugins); ?>><span><?php echo esc_html__('Автоматично встановлювати потрібні approved plugins', 'thesis-ai-bridge'); ?></span></label>
                                    <label><input id="thesis-ai-allow-setup" type="checkbox" name="allow_site_setup" value="1" <?php checked($allow_setup); ?>><span><?php echo esc_html__('Автоматично налаштовувати тему, SEO і структуру сайту', 'thesis-ai-bridge'); ?></span></label>
                                </div>
                            </div>
                        <?php endif; ?>
                        <div class="tai-actions">
                            <button type="submit" class="button button-primary tai-primary" <?php disabled(!empty($active_build['job_id'])); ?>><span class="dashicons dashicons-superhero"></span><?php echo esc_html($connected ? (!empty($active_build['job_id']) ? __('Build уже виконується…', 'thesis-ai-bridge') : __('Створити сайт', 'thesis-ai-bridge')) : __('Спробувати локальне демо', 'thesis-ai-bridge')); ?><span class="dashicons dashicons-arrow-right-alt2"></span></button>
                            <?php if ($connected) : ?><button type="button" class="button tai-secondary" id="thesis-ai-preflight"><span class="dashicons dashicons-search"></span><?php echo esc_html__('Прогнати preflight', 'thesis-ai-bridge'); ?></button><?php endif; ?>
                            <span id="thesis-ai-autosave" class="tai-autosave"><?php echo esc_html__('Чернетка зберігається автоматично', 'thesis-ai-bridge'); ?></span>
                        </div>
                    </form>
                    <?php if ($preflight) : ?><div class="tai-preflight" id="thesis-ai-preflight-result"><strong><?php echo esc_html__('Останній preflight:', 'thesis-ai-bridge'); ?></strong> <?php echo esc_html(sprintf(__('%1$d сторінок · %2$d plugins · %3$d themes', 'thesis-ai-bridge'), (int)($preflight['pages'] ?? 0), (int)($preflight['plugins'] ?? 0), (int)($preflight['themes'] ?? 0))); ?></div><?php else : ?><div class="tai-preflight" id="thesis-ai-preflight-result" hidden></div><?php endif; ?>
                </section>

                <section class="tai-card tai-process-card <?php echo !empty($active_build['job_id']) ? 'is-running' : ''; ?>" id="thesis-ai-process">
                    <div class="tai-card-head"><div><h2><span class="dashicons dashicons-update"></span><?php echo esc_html__('Процес створення сайту', 'thesis-ai-bridge'); ?></h2><p><?php echo esc_html__('Стан зберігається у WordPress і не губиться після оновлення сторінки.', 'thesis-ai-bridge'); ?></p></div><span class="tai-status-pill" id="thesis-ai-build-pill"><?php echo esc_html(!empty($active_build['job_id']) ? __('У процесі', 'thesis-ai-bridge') : (($last_build['status'] ?? '') === 'passed' ? __('Завершено', 'thesis-ai-bridge') : __('Готово', 'thesis-ai-bridge'))); ?></span></div>
                    <?php self::render_steps($stage); ?>
                    <div class="tai-progress-row"><div class="tai-progress"><span id="thesis-ai-progress-bar" style="width:<?php echo esc_attr((string)$progress); ?>%"></span></div><strong id="thesis-ai-progress-number"><?php echo esc_html((string)$progress); ?>%</strong></div>
                    <div class="tai-process-note"><span class="dashicons dashicons-lightbulb"></span><div><strong id="thesis-ai-build-stage"><?php echo esc_html(self::stage_label($stage)); ?></strong><p id="thesis-ai-build-detail"><?php echo esc_html($detail); ?></p></div></div>
                    <div id="thesis-ai-build-error" class="tai-inline-error" <?php echo empty($active_build['last_error']) ? 'hidden' : ''; ?>><?php echo esc_html((string)($active_build['last_error'] ?? '')); ?></div>
                    <div class="tai-run-meta">
                        <span><small><?php echo esc_html__('Run ID', 'thesis-ai-bridge'); ?></small><strong><?php echo esc_html(self::short_id((string)($active_build['job_id'] ?? ($last_build['run_id'] ?? '—')))); ?></strong></span>
                        <span><small><?php echo esc_html__('Токени', 'thesis-ai-bridge'); ?></small><strong id="thesis-ai-token-count"><?php echo esc_html(number_format_i18n((int)($last_build['usage']['total_tokens'] ?? 0))); ?></strong></span>
                        <span><small><?php echo esc_html__('Repair loops', 'thesis-ai-bridge'); ?></small><strong><?php echo esc_html((string)($active_build['repair_attempts'] ?? ($last_build['repair_attempts'] ?? 0))); ?></strong></span>
                    </div>
                </section>
            </div>

            <div class="tai-info-grid">
                <section class="tai-card tai-pages-card">
                    <div class="tai-card-head compact"><div><h2><span class="dashicons dashicons-media-document"></span><?php echo esc_html__('Що буде створено', 'thesis-ai-bridge'); ?></h2><p><?php echo esc_html__('План сторінок поточного або останнього build', 'thesis-ai-bridge'); ?></p></div></div>
                    <ul id="thesis-ai-planned-pages" class="tai-page-list">
                        <?php if ($planned_pages) : ?>
                            <?php foreach ($planned_pages as $page) : ?><li><span class="tai-checkmark">✓</span><span><?php echo esc_html($page); ?></span></li><?php endforeach; ?>
                        <?php else : ?>
                            <li class="tai-page-placeholder"><span class="dashicons dashicons-clock"></span><span><?php echo esc_html__('План сторінок з’явиться після етапу Архітектора.', 'thesis-ai-bridge'); ?></span></li>
                        <?php endif; ?>
                    </ul>
                </section>

                <section class="tai-card tai-agents-card">
                    <div class="tai-card-head compact"><div><h2><span class="dashicons dashicons-groups"></span><?php echo esc_html__('AI агенти', 'thesis-ai-bridge'); ?></h2><p><?php echo esc_html__('П’ять спеціалізованих ролей працюють над одним build', 'thesis-ai-bridge'); ?></p></div></div>
                    <div class="tai-agents" id="thesis-ai-agents">
                        <?php self::agent_card('orchestrator', '🤖', __('Оркестратор', 'thesis-ai-bridge'), __('Планує процес і координує агентів', 'thesis-ai-bridge'), $stage); ?>
                        <?php self::agent_card('architect', '◫', __('Архітектор', 'thesis-ai-bridge'), __('Сторінки, capabilities, plugins і data model', 'thesis-ai-bridge'), $stage); ?>
                        <?php self::agent_card('design', '✦', __('Контент / SEO / UX', 'thesis-ai-bridge'), __('Створює структуру, тексти, дизайн і SEO', 'thesis-ai-bridge'), $stage); ?>
                        <?php self::agent_card('builder', '⚙', __('WordPress агент', 'thesis-ai-bridge'), __('Виконує контрольовані WordPress abilities', 'thesis-ai-bridge'), $stage); ?>
                        <?php self::agent_card('quality', '◆', __('QA / Безпека', 'thesis-ai-bridge'), __('Перевіряє результат і запускає repair', 'thesis-ai-bridge'), $stage); ?>
                    </div>
                </section>
            </div>

            <div class="tai-lower-grid">
                <section class="tai-card tai-activity-card">
                    <div class="tai-card-head compact"><div><h2><span class="dashicons dashicons-clock"></span><?php echo esc_html__('Останні дії', 'thesis-ai-bridge'); ?></h2><p><?php echo esc_html__('Живий журнал подій build', 'thesis-ai-bridge'); ?></p></div></div>
                    <div class="tai-events" id="thesis-ai-events"><?php self::render_events($events); ?></div>
                </section>
                <section class="tai-card tai-result-card">
                    <?php self::render_result_summary($last_build); ?>
                </section>
            </div>

            <?php self::render_history($history); ?>
            <?php self::render_advanced($settings, $status); ?>
        </div>
        <?php
    }

    private static function render_connection_controls(bool $connected, string $backend_url, array $connection): void {
        if ($connected) {
            echo '<p><strong>' . esc_html__('Підключено', 'thesis-ai-bridge') . '</strong><br><code>' . esc_html((string)($connection['execution_mode'] ?? 'wordpress_pull')) . '</code></p>';
            echo '<div class="tai-inline-actions">';
            echo '<form method="post" action="' . esc_url(admin_url('admin-post.php')) . '"><input type="hidden" name="action" value="thesis_ai_check">';
            wp_nonce_field('thesis_ai_check');
            submit_button(__('Перевірити', 'thesis-ai-bridge'), 'secondary small', 'submit', false);
            echo '</form>';
            echo '<form method="post" action="' . esc_url(admin_url('admin-post.php')) . '"><input type="hidden" name="action" value="thesis_ai_disconnect">';
            wp_nonce_field('thesis_ai_disconnect');
            submit_button(__('Відключити', 'thesis-ai-bridge'), 'link-delete small', 'submit', false);
            echo '</form></div>';
            return;
        }
        echo '<form method="post" action="' . esc_url(admin_url('admin-post.php')) . '"><input type="hidden" name="action" value="thesis_ai_connect">';
        wp_nonce_field('thesis_ai_connect');
        echo '<label><strong>' . esc_html__('Backend URL', 'thesis-ai-bridge') . '</strong><input type="url" name="backend_url" value="' . esc_attr($backend_url) . '" placeholder="https://...onrender.com" required></label>';
        submit_button(__('Підключити', 'thesis-ai-bridge'), 'primary small', 'submit', false);
        echo '</form>';
    }

    private static function render_steps(string $stage): void {
        $steps = [
            ['key' => 'analysis', 'label' => __('Аналіз запиту', 'thesis-ai-bridge')],
            ['key' => 'content', 'label' => __('Структура та контент', 'thesis-ai-bridge')],
            ['key' => 'plan', 'label' => __('План WordPress', 'thesis-ai-bridge')],
            ['key' => 'build', 'label' => __('Створення сайту', 'thesis-ai-bridge')],
            ['key' => 'qa', 'label' => __('Фінальні перевірки', 'thesis-ai-bridge')],
        ];
        $current = self::step_index($stage);
        echo '<ol class="tai-steps" id="thesis-ai-steps">';
        foreach ($steps as $index => $step) {
            $state = $index < $current ? 'done' : ($index === $current ? 'active' : 'waiting');
            echo '<li data-step="' . esc_attr($step['key']) . '" class="' . esc_attr($state) . '"><span>' . ($state === 'done' ? '✓' : (string)($index + 1)) . '</span><strong>' . esc_html($step['label']) . '</strong></li>';
        }
        echo '</ol>';
    }

    private static function agent_card(string $key, string $icon, string $title, string $description, string $stage): void {
        $state = self::agent_state($key, $stage);
        $label = $state === 'done' ? __('Готово', 'thesis-ai-bridge') : ($state === 'active' ? __('Працює', 'thesis-ai-bridge') : __('Очікує', 'thesis-ai-bridge'));
        echo '<article class="tai-agent ' . esc_attr($state) . '" data-agent="' . esc_attr($key) . '"><div class="tai-agent-icon">' . esc_html($icon) . '</div><div class="tai-agent-copy"><strong>' . esc_html($title) . '</strong><p>' . esc_html($description) . '</p><span>' . esc_html($label) . '</span></div></article>';
    }

    private static function render_events(array $events): void {
        if (!$events) {
            echo '<div class="tai-empty">' . esc_html__('Подій ще немає. Запустіть build або preflight.', 'thesis-ai-bridge') . '</div>';
            return;
        }
        foreach (array_slice($events, 0, 12) as $event) {
            if (!is_array($event)) { continue; }
            $type = in_array((string)($event['type'] ?? ''), ['info', 'success', 'warning', 'error'], true) ? (string)$event['type'] : 'info';
            echo '<div class="tai-event ' . esc_attr($type) . '"><time>' . esc_html(self::format_time((string)($event['time'] ?? ''))) . '</time><span class="tai-event-dot"></span><span class="tai-event-type">' . esc_html(strtoupper($type)) . '</span><p>' . esc_html((string)($event['message'] ?? '')) . '</p></div>';
        }
    }

    private static function render_result_summary(array $build): void {
        echo '<div class="tai-card-head compact"><div><h2><span class="dashicons dashicons-yes-alt"></span>' . esc_html__('Останній результат', 'thesis-ai-bridge') . '</h2><p>' . esc_html__('Фактичний результат останнього завершеного build', 'thesis-ai-bridge') . '</p></div></div>';
        if (!$build) {
            echo '<div class="tai-empty">' . esc_html__('Завершених build ще немає.', 'thesis-ai-bridge') . '</div>';
            return;
        }
        $passed = (string)($build['status'] ?? '') === 'passed';
        $pages = (array)($build['pages'] ?? []);
        $plugins = (array)($build['plugins'] ?? []);
        $themes = (array)($build['themes'] ?? []);
        $usage = (array)($build['usage'] ?? []);
        echo '<div class="tai-result-status ' . ($passed ? 'success' : 'failed') . '"><span>' . ($passed ? '✓' : '!') . '</span><div><strong>' . esc_html($passed ? __('Завершено успішно', 'thesis-ai-bridge') : __('Потрібна увага', 'thesis-ai-bridge')) . '</strong><p>' . esc_html((string)(($build['quality_summary'] ?? '') ?: __('Результат збережено.', 'thesis-ai-bridge'))) . '</p></div></div>';
        if (!empty($build['pages'])) {
            echo '<div class="tai-preflight">' . esc_html__('Нові сторінки залишаються чернетками. Поки ви не перевірите й не опублікуєте їх, публічна головна сторінка може залишатися без змін.', 'thesis-ai-bridge') . '</div>';
        }
        $estimated_cost = (float)($usage['estimated_cost_usd'] ?? 0);
        echo '<div class="tai-metrics"><div><strong>' . esc_html((string)count($pages)) . '</strong><small>' . esc_html__('Сторінки', 'thesis-ai-bridge') . '</small></div><div><strong>' . esc_html((string)count($plugins)) . '</strong><small>' . esc_html__('Plugins', 'thesis-ai-bridge') . '</small></div><div><strong>' . esc_html(number_format_i18n((int)($usage['total_tokens'] ?? 0))) . '</strong><small>' . esc_html__('Tokens', 'thesis-ai-bridge') . '</small></div><div><strong>$' . esc_html(number_format($estimated_cost, 3, '.', '')) . '</strong><small>' . esc_html__('API estimate', 'thesis-ai-bridge') . '</small></div></div>';
        if ($pages) {
            echo '<div class="tai-mini-list">';
            foreach (array_slice($pages, 0, 6) as $page) {
                if (!is_array($page)) { continue; }
                $title = (string)($page['title'] ?? ($page['slug'] ?? 'Page'));
                $edit_url = !empty($page['edit_url']) ? (string)$page['edit_url'] : (!empty($page['id']) ? (string)(get_edit_post_link((int)$page['id']) ?: '') : '');
                echo '<div><span>✓</span><strong>' . esc_html($title) . '</strong>' . ($edit_url !== '' ? '<a href="' . esc_url($edit_url) . '">' . esc_html__('Редагувати', 'thesis-ai-bridge') . '</a>' : '') . '</div>';
            }
            echo '</div>';
        }
        if ($passed && $pages) {
            echo '<div class="tai-review-next"><strong>Перед публікацією перевірте</strong><ul><li>Сторінки у редакторі Elementor і на телефоні: заголовки, відступи, посилання</li><li>Реальні зображення, ціни, характеристики, алергени та контакти</li><li>WooCommerce: каталог, кошик, доставка й оплата — якщо потрібні</li></ul><small>Успішний backend QA не означає, що фактичний дизайн пройшов Playwright або отримав незалежну оцінку.</small></div>';
        }
        if ($passed && empty($build['published_at']) && $pages) {
            echo '<form method="post" action="' . esc_url(admin_url('admin-post.php')) . '" class="tai-publish-form" onsubmit="return confirm(\'' . esc_js(__('Опублікувати всі AI-generated draft-сторінки?', 'thesis-ai-bridge')) . '\');"><input type="hidden" name="action" value="thesis_ai_publish_build">';
            wp_nonce_field('thesis_ai_publish_build');
            submit_button(__('Перевірив — опублікувати сторінки', 'thesis-ai-bridge'), 'primary', 'submit', false);
            echo '</form>';
        }
        $brief = (array)($build['project_brief'] ?? []);
        $architecture = (array)($build['architecture'] ?? []);
        $capabilities = (array)($build['capability_resolutions'] ?? []);
        if ($brief || $architecture || $capabilities) {
            echo '<details class="tai-diagnostics"><summary>' . esc_html__('Артефакти агентів', 'thesis-ai-bridge') . '</summary>';
            if ($brief) {
                echo '<p><strong>' . esc_html__('ProjectBrief:', 'thesis-ai-bridge') . '</strong> ' . esc_html((string)($brief['site_type'] ?? '')) . ' · ' . esc_html((string)($brief['primary_goal'] ?? '')) . '</p>';
            }
            if (!empty($architecture['pages']) && is_array($architecture['pages'])) {
                $labels = [];
                foreach ($architecture['pages'] as $p) { if (is_array($p)) { $labels[] = (string)($p['name'] ?? $p['slug'] ?? ''); } }
                echo '<p><strong>' . esc_html__('Архітектура:', 'thesis-ai-bridge') . '</strong> ' . esc_html(implode(' → ', array_filter($labels))) . '</p>';
            }
            if ($capabilities) {
                $labels = [];
                foreach ($capabilities as $c) { if (is_array($c)) { $labels[] = (string)($c['capability'] ?? '') . ':' . (string)($c['action'] ?? ''); } }
                echo '<p><strong>' . esc_html__('Capabilities:', 'thesis-ai-bridge') . '</strong> ' . esc_html(implode(', ', array_filter($labels))) . '</p>';
            }
            echo '</details>';
        }
        $issues = (array)($build['issues'] ?? []);
        $failed_actions = (array)($build['failed_actions'] ?? []);
        if ($issues || $failed_actions) {
            echo '<details class="tai-diagnostics"><summary>' . esc_html__('Діагностика проблем', 'thesis-ai-bridge') . ' (' . esc_html((string)(count($issues) + count($failed_actions))) . ')</summary>';
            foreach ($issues as $issue) {
                if (!is_array($issue)) { continue; }
                echo '<p><strong>' . esc_html((string)($issue['severity'] ?? '')) . '</strong> · ' . esc_html((string)($issue['description'] ?? '')) . '</p>';
            }
            foreach ($failed_actions as $failed) {
                if (!is_array($failed)) { continue; }
                echo '<p><code>' . esc_html(str_replace('thesis-ai-bridge/', '', (string)($failed['ability'] ?? ''))) . '</code><br>' . esc_html((string)($failed['error'] ?? 'Unknown error')) . '</p>';
            }
            echo '</details>';
        }
    }

    private static function render_history(array $history): void {
        echo '<section class="tai-card tai-history"><div class="tai-card-head compact"><div><h2><span class="dashicons dashicons-backup"></span>' . esc_html__('Останні запуски', 'thesis-ai-bridge') . '</h2><p>' . esc_html__('Історія зберігається локально у WordPress', 'thesis-ai-bridge') . '</p></div></div>';
        if (!$history) {
            echo '<div class="tai-empty">' . esc_html__('Історія порожня.', 'thesis-ai-bridge') . '</div></section>';
            return;
        }
        echo '<div class="tai-table-wrap"><table><thead><tr><th>' . esc_html__('Дата', 'thesis-ai-bridge') . '</th><th>' . esc_html__('Запит', 'thesis-ai-bridge') . '</th><th>' . esc_html__('Статус', 'thesis-ai-bridge') . '</th><th>' . esc_html__('Сторінки', 'thesis-ai-bridge') . '</th><th>' . esc_html__('Plugins', 'thesis-ai-bridge') . '</th><th>' . esc_html__('Тривалість', 'thesis-ai-bridge') . '</th></tr></thead><tbody>';
        foreach (array_slice($history, 0, 8) as $item) {
            if (!is_array($item)) { continue; }
            $prompt = trim((string)($item['prompt'] ?? ''));
            $prompt = $prompt !== '' ? self::truncate($prompt, 72) : __('Build', 'thesis-ai-bridge');
            $status = (string)($item['status'] ?? 'unknown');
            echo '<tr><td>' . esc_html(self::format_datetime((string)($item['started_at'] ?? $item['requested_at'] ?? ''))) . '</td><td>' . esc_html($prompt) . '</td><td><span class="tai-table-status ' . esc_attr($status) . '">' . esc_html($status) . '</span></td><td>' . esc_html((string)count((array)($item['pages'] ?? []))) . '</td><td>' . esc_html((string)count((array)($item['plugins'] ?? []))) . '</td><td>' . esc_html(self::format_duration((int)($item['duration_seconds'] ?? 0))) . '</td></tr>';
        }
        echo '</tbody></table></div></section>';
    }

    private static function render_advanced(array $settings, array $status): void {
        echo '<details class="tai-card tai-advanced"><summary><span class="dashicons dashicons-admin-tools"></span>' . esc_html__('Розширені налаштування та діагностика', 'thesis-ai-bridge') . '</summary><div class="tai-advanced-body">';
        echo '<form method="post" action="options.php">';
        settings_fields('thesis_ai_bridge_settings_group');
        echo '<table class="form-table" role="presentation">';
        self::checkbox_row('external_api_enabled', __('Зовнішній Bridge API', 'thesis-ai-bridge'), __('У pull-режимі зазвичай не потрібен.', 'thesis-ai-bridge'), $settings);
        self::checkbox_row('existing_page_updates_enabled', __('Зміна існуючих сторінок', 'thesis-ai-bridge'), __('AI-generated drafts можна оновлювати без цього дозволу.', 'thesis-ai-bridge'), $settings);
        self::checkbox_row('site_settings_enabled', __('Налаштування сайту', 'thesis-ai-bridge'), __('Головна сторінка, меню та site identity.', 'thesis-ai-bridge'), $settings);
        self::checkbox_row('plugin_management_enabled', __('Approved plugins', 'thesis-ai-bridge'), __('Встановлення лише з вбудованого allowlist.', 'thesis-ai-bridge'), $settings);
        echo '</table>';
        submit_button(__('Зберегти дозволи', 'thesis-ai-bridge'));
        echo '</form><div class="tai-diagnostic-grid">';
        self::diagnostic('Bridge', (string)($status['bridge_version'] ?? THESIS_AI_BRIDGE_VERSION));
        self::diagnostic('WordPress', (string)($status['wordpress_version'] ?? get_bloginfo('version')));
        self::diagnostic('PHP', (string)($status['php_version'] ?? PHP_VERSION));
        self::diagnostic('HTTPS', !empty($status['https']) ? 'Yes' : 'No');
        self::diagnostic('Abilities API', !empty($status['native_abilities_api']) ? 'Native' : 'Fallback bridge');
        self::diagnostic('Execution', 'wordpress_pull');
        echo '</div></div></details>';
    }

    private static function planned_pages(array $active, array $last): array {
        $pages = [];
        foreach ((array)($active['bundle']['application_spec']['pages'] ?? []) as $page) {
            if (is_array($page)) { $pages[] = (string)($page['name'] ?? $page['title'] ?? $page['slug'] ?? ''); }
        }
        $pages = array_values(array_filter(array_unique($pages)));
        if ($pages) {
            return $pages;
        }
        // While a new build is still being planned, never show stale pages from
        // the previous run. That made a 3-page request look like the old 4/7-page
        // plan until planning finished.
        if (!empty($active)) {
            return [];
        }
        foreach ((array)($last['pages'] ?? []) as $page) {
            if (is_array($page)) { $pages[] = (string)($page['title'] ?? $page['slug'] ?? ''); }
        }
        return array_values(array_filter(array_unique($pages)));
    }

    private static function step_index(string $stage): int {
        $stage = sanitize_key($stage);
        if (in_array($stage, ['completed', 'quality', 'verification'], true)) { return 4; }
        if (in_array($stage, ['local_execution', 'repair', 'repairing', 'executing'], true)) { return 3; }
        if (in_array($stage, ['implementation_plan', 'plan_ready', 'ready'], true)) { return 2; }
        if (in_array($stage, ['design'], true)) { return 1; }
        return 0;
    }

    private static function stage_label(string $stage): string {
        $map = [
            'queued' => __('Запит у черзі', 'thesis-ai-bridge'),
            'starting' => __('Запускаємо агентів', 'thesis-ai-bridge'),
            'orchestrator' => __('Аналіз запиту', 'thesis-ai-bridge'),
            'architecture' => __('Архітектура та capabilities', 'thesis-ai-bridge'),
            'design' => __('Структура, контент і SEO', 'thesis-ai-bridge'),
            'implementation_plan' => __('План WordPress-дій', 'thesis-ai-bridge'),
            'plan_ready' => __('План готовий', 'thesis-ai-bridge'),
            'local_execution' => __('Створюємо сайт у WordPress', 'thesis-ai-bridge'),
            'verification' => __('Перевіряємо результат', 'thesis-ai-bridge'),
            'quality' => __('QA та безпека', 'thesis-ai-bridge'),
            'repair' => __('Автоматичне виправлення', 'thesis-ai-bridge'),
            'completed' => __('Готово', 'thesis-ai-bridge'),
            'idle' => __('Готово до запуску', 'thesis-ai-bridge'),
        ];
        return $map[sanitize_key($stage)] ?? ($stage !== '' ? $stage : __('Готово до запуску', 'thesis-ai-bridge'));
    }

    private static function agent_state(string $agent, string $stage): string {
        $step = self::step_index($stage);
        $index = ['orchestrator' => 0, 'architect' => 0, 'design' => 1, 'builder' => 3, 'quality' => 4][$agent] ?? 0;
        if (sanitize_key($stage) === 'idle') { return 'waiting'; }
        if ($step > $index) { return 'done'; }
        if ($step === $index) { return 'active'; }
        return 'waiting';
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
                'connect' => __('AI Builder підключено.', 'thesis-ai-bridge'),
                'disconnect' => __('AI Builder відключено.', 'thesis-ai-bridge'),
                'check' => __('З’єднання працює.', 'thesis-ai-bridge'),
                'build' => __('Build запущено. Стан зберігається у WordPress.', 'thesis-ai-bridge'),
                'demo' => __('Локальне демо завершено.', 'thesis-ai-bridge'),
                'publish' => __('AI-generated сторінки опубліковано після підтвердження.', 'thesis-ai-bridge'),
            ];
            $args['thesis_ai_message'] = $messages[$action] ?? __('Готово.', 'thesis-ai-bridge');
        }
        wp_safe_redirect(add_query_arg($args, admin_url('admin.php')));
        exit;
    }

    private static function checkbox_row(string $key, string $label, string $description, array $settings): void {
        $name = self::OPTION_SETTINGS . '[' . $key . ']';
        echo '<tr><th scope="row">' . esc_html($label) . '</th><td><label><input type="checkbox" name="' . esc_attr($name) . '" value="1" ' . checked(!empty($settings[$key]), true, false) . '> ' . esc_html($description) . '</label></td></tr>';
    }

    private static function diagnostic(string $label, string $value): void {
        echo '<div><small>' . esc_html($label) . '</small><strong>' . esc_html($value) . '</strong></div>';
    }

    private static function short_id(string $id): string {
        if ($id === '' || $id === '—') { return '—'; }
        return strlen($id) > 16 ? substr($id, 0, 8) . '…' . substr($id, -5) : $id;
    }

    private static function format_time(string $iso): string {
        $ts = $iso !== '' ? strtotime($iso) : false;
        return $ts ? wp_date('H:i:s', $ts) : '—';
    }

    private static function format_datetime(string $iso): string {
        $ts = $iso !== '' ? strtotime($iso) : false;
        return $ts ? wp_date('d.m.Y H:i', $ts) : '—';
    }

    private static function format_duration(int $seconds): string {
        if ($seconds <= 0) { return '—'; }
        $minutes = intdiv($seconds, 60);
        $seconds = $seconds % 60;
        return $minutes > 0 ? sprintf('%d хв %02d с', $minutes, $seconds) : sprintf('%d с', $seconds);
    }

    private static function truncate(string $value, int $length): string {
        if (function_exists('mb_strlen') && mb_strlen($value) > $length) {
            return mb_substr($value, 0, $length - 1) . '…';
        }
        return strlen($value) > $length ? substr($value, 0, $length - 1) . '…' : $value;
    }

    private static function text_length(string $value): int {
        return function_exists('mb_strlen') ? (int)mb_strlen($value) : strlen($value);
    }
}
