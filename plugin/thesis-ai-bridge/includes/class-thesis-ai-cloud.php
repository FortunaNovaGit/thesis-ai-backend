<?php

declare(strict_types=1);

if (!defined('ABSPATH')) {
    exit;
}

/**
 * Cloud coordinator for v0.6 pull execution.
 *
 * Render plans/verifies. WordPress executes every mutation locally, one short
 * admin-AJAX request at a time. This removes the Render -> EasyWP request burst
 * that caused 429s and removes long PHP requests that caused 504s.
 */
final class Thesis_AI_Cloud {
    private const OPTION_CONNECTION = 'thesis_ai_bridge_connection';
    private const OPTION_LAST_BUILD = 'thesis_ai_bridge_last_build';
    private const OPTION_ACTIVE_BUILD = 'thesis_ai_bridge_active_build';
    private const OPTION_BUILD_HISTORY = 'thesis_ai_bridge_build_history';
    private const OPTION_EVENT_LOG = 'thesis_ai_bridge_event_log';
    private const OPTION_UI_STATE = 'thesis_ai_bridge_ui_state';
    private const OPTION_LAST_PREFLIGHT = 'thesis_ai_bridge_last_preflight';
    private const OPTION_WORKER_LOCK = 'thesis_ai_bridge_worker_lock';
    private const ACTION_LOG_PREFIX = 'thesis_ai_action_done_';
    private const ACTION_LOCK_PREFIX = 'thesis_ai_action_lock_';
    private const WORKER_HOOK = 'thesis_ai_cloud_worker';

    public static function init(): void {
        add_action('admin_init', [self::class, 'migrate_legacy_credentials']);
        add_action(self::WORKER_HOOK, [self::class, 'worker_tick']);
    }

    public static function migrate_legacy_credentials(): void {
        $connection = get_option(self::OPTION_CONNECTION, []);
        if (!is_array($connection) || empty($connection['app_password_uuid']) || empty($connection['service_user_id'])) {
            return;
        }
        if (class_exists('WP_Application_Passwords')) {
            WP_Application_Passwords::delete_application_password((int)$connection['service_user_id'], (string)$connection['app_password_uuid']);
        }
        unset($connection['app_password_uuid'], $connection['service_user_id'], $connection['service_username']);
        $connection['execution_mode'] = 'wordpress_pull';
        update_option(self::OPTION_CONNECTION, $connection, false);
    }

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

    public static function active_build(): array {
        $value = get_option(self::OPTION_ACTIVE_BUILD, []);
        return is_array($value) ? $value : [];
    }

    public static function build_history(): array {
        $value = get_option(self::OPTION_BUILD_HISTORY, []);
        return is_array($value) ? array_values($value) : [];
    }

    public static function event_log(): array {
        $value = get_option(self::OPTION_EVENT_LOG, []);
        return is_array($value) ? array_values($value) : [];
    }

    public static function ui_state(): array {
        $value = get_option(self::OPTION_UI_STATE, []);
        return is_array($value) ? $value : [];
    }

    public static function last_preflight(): array {
        $value = get_option(self::OPTION_LAST_PREFLIGHT, []);
        return is_array($value) ? $value : [];
    }

    public static function save_ui_state(array $state): array {
        $clean = [
            'prompt' => sanitize_textarea_field((string)($state['prompt'] ?? '')),
            'renderer' => in_array((string)($state['renderer'] ?? 'elementor'), ['elementor', 'gutenberg', 'auto'], true) ? (string)$state['renderer'] : 'elementor',
            'allow_approved_plugins' => !empty($state['allow_approved_plugins']),
            'allow_site_setup' => !empty($state['allow_site_setup']),
            'updated_at' => gmdate('c'),
        ];
        update_option(self::OPTION_UI_STATE, $clean, false);
        return $clean;
    }

    public static function run_preflight(): array|WP_Error {
        if (!current_user_can('manage_options')) {
            return new WP_Error('thesis_ai_forbidden', __('Administrator permissions are required.', 'thesis-ai-bridge'));
        }
        $snapshot = Thesis_AI_Bridge::execute_named_ability('get-site-snapshot', []);
        if (is_wp_error($snapshot)) {
            return $snapshot;
        }
        $summary = [
            'checked_at' => gmdate('c'),
            'pages' => count((array)($snapshot['pages'] ?? [])),
            'plugins' => count((array)($snapshot['plugins'] ?? [])),
            'themes' => count((array)($snapshot['themes'] ?? [])),
            'active_theme' => (string)(($snapshot['structure']['active_theme'] ?? '') ?: ($snapshot['site']['theme'] ?? '')),
            'elementor_active' => false,
            'woocommerce_active' => false,
            'acf_active' => false,
            'snapshot' => $snapshot,
        ];
        foreach ((array)($snapshot['plugins'] ?? []) as $plugin) {
            if (!is_array($plugin) || empty($plugin['active'])) { continue; }
            $slug = (string)($plugin['slug'] ?? '');
            if ($slug === 'elementor') { $summary['elementor_active'] = true; }
            if ($slug === 'woocommerce') { $summary['woocommerce_active'] = true; }
            if (in_array($slug, ['advanced-custom-fields', 'acf'], true)) { $summary['acf_active'] = true; }
        }
        update_option(self::OPTION_LAST_PREFLIGHT, $summary, false);
        self::log_event('success', __('Preflight завершено. Поточний стан WordPress збережено.', 'thesis-ai-bridge'), ['stage' => 'preflight']);
        return $summary;
    }

    public static function record_poll_error(WP_Error $error): void {
        $active = self::active_build();
        if (!$active) { return; }
        $active['last_error'] = sanitize_text_field($error->get_error_message());
        $active['error_count'] = max(0, (int)($active['error_count'] ?? 0)) + 1;
        $active['last_error_at'] = gmdate('c');
        $active['updated_at'] = gmdate('c');
        update_option(self::OPTION_ACTIVE_BUILD, $active, false);
        self::log_event('error', $error->get_error_message(), ['stage' => (string)($active['stage'] ?? 'unknown')]);
        // Do not keep polling forever on an unrecoverable rejected payload.
        // 520 can be transient, but repeated origin failures must become a
        // terminal, inspectable result rather than an infinite spinner.
        $message = $error->get_error_message();
        $fatal_413 = str_contains($message, '(413)');
        if ($fatal_413 || (int)$active['error_count'] >= 5) {
            self::finalize_failed_build($active, $message, (string)($active['stage'] ?? 'backend'));
        }
    }

    public static function dashboard_state(): array {
        return [
            'connection' => self::connection(),
            'active_build' => self::active_build(),
            'last_build' => self::last_build(),
            'history' => self::build_history(),
            'events' => self::event_log(),
            'ui_state' => self::ui_state(),
            'preflight' => self::last_preflight(),
        ];
    }

    public static function connect(string $backend_url): array|WP_Error {
        if (!current_user_can('manage_options')) {
            return new WP_Error('thesis_ai_forbidden', __('Administrator permissions are required.', 'thesis-ai-bridge'));
        }
        $backend_url = self::normalize_backend_url($backend_url);
        if (is_wp_error($backend_url)) {
            return $backend_url;
        }

        // Pull execution does not require inbound Bridge REST access from the cloud.
        $bridge_settings = Thesis_AI_Bridge::get_settings();
        $bridge_settings['external_api_enabled'] = false;
        update_option('thesis_ai_bridge_settings', Thesis_AI_Bridge::sanitize_settings($bridge_settings), false);

        $response = wp_remote_post(
            $backend_url . '/v2/sites/connect',
            [
                'timeout' => 25,
                'redirection' => 2,
                'headers' => [
                    'Content-Type' => 'application/json',
                    'Accept' => 'application/json',
                    'User-Agent' => 'Thesis-AI-Bridge/' . THESIS_AI_BRIDGE_VERSION,
                    'X-Thesis-Pairing-Secret' => defined('THESIS_AI_BACKEND_PAIRING_SECRET') ? (string)THESIS_AI_BACKEND_PAIRING_SECRET : '',
                ],
                'body' => wp_json_encode([
                    'site_url' => home_url('/'),
                    'site_name' => get_bloginfo('name'),
                    'bridge_version' => THESIS_AI_BRIDGE_VERSION,
                ]),
            ]
        );
        if (is_wp_error($response)) {
            return new WP_Error('thesis_ai_backend_unreachable', sprintf(__('Could not reach AI backend: %s', 'thesis-ai-bridge'), $response->get_error_message()));
        }
        $code = (int)wp_remote_retrieve_response_code($response);
        $body = json_decode((string)wp_remote_retrieve_body($response), true);
        if ($code < 200 || $code >= 300 || !is_array($body) || empty($body['site_id']) || empty($body['site_token'])) {
            $detail = is_array($body) ? (string)($body['detail'] ?? 'Backend rejected the connection.') : 'Backend returned an invalid response.';
            return new WP_Error('thesis_ai_backend_rejected', sprintf(__('AI backend connection failed: %s', 'thesis-ai-bridge'), $detail));
        }
        $encrypted = self::encrypt_secret(sanitize_text_field((string)$body['site_token']));
        if (is_wp_error($encrypted)) {
            return $encrypted;
        }
        $connection = [
            'backend_url' => $backend_url,
            'site_id' => sanitize_text_field((string)$body['site_id']),
            'site_token_encrypted' => $encrypted,
            'execution_mode' => 'wordpress_pull',
            'agent_mode' => sanitize_key((string)($body['agent_mode'] ?? '')),
            'model' => sanitize_text_field((string)($body['model'] ?? '')),
            'model_router' => isset($body['model_router']) && is_array($body['model_router']) ? $body['model_router'] : [],
            'stable_connection_tokens' => (string)($body['token_persistence'] ?? '') === 'stable',
            'connected_at' => gmdate('c'),
            'last_checked_at' => gmdate('c'),
        ];
        update_option(self::OPTION_CONNECTION, $connection, false);
        self::log_event('success', __('Backend підключено.', 'thesis-ai-bridge'), ['stage' => 'connection']);
        return $connection;
    }

    public static function disconnect(): true|WP_Error {
        $c = self::full_connection();
        if ($c) {
            $response = self::backend_request('POST', '/v2/sites/' . rawurlencode((string)($c['site_id'] ?? '')) . '/disconnect', null, 10, $c, false);
            // Disconnect is local-first; backend unavailability must not trap the site.
            unset($response);
        }
        delete_option(self::OPTION_CONNECTION);
        delete_option(self::OPTION_ACTIVE_BUILD);
        self::log_event('info', __('Backend відключено.', 'thesis-ai-bridge'), ['stage' => 'connection']);
        return true;
    }

    public static function check_connection(): array|WP_Error {
        $c = self::full_connection();
        if (!self::is_connected()) {
            return new WP_Error('thesis_ai_not_connected', __('AI Builder is not connected.', 'thesis-ai-bridge'));
        }
        $result = self::backend_request('GET', '/v2/sites/' . rawurlencode((string)$c['site_id']) . '/check', null, 20, $c);
        if (is_wp_error($result)) {
            return $result;
        }
        $saved = get_option(self::OPTION_CONNECTION, []);
        if (is_array($saved)) {
            $saved['last_checked_at'] = gmdate('c');
            $saved['agent_mode'] = sanitize_key((string)($result['agent_mode'] ?? ($saved['agent_mode'] ?? '')));
            $saved['model'] = sanitize_text_field((string)($result['model'] ?? ($saved['model'] ?? '')));
            $saved['model_router'] = isset($result['model_router']) && is_array($result['model_router']) ? $result['model_router'] : ($saved['model_router'] ?? []);
            $saved['execution_mode'] = sanitize_key((string)($result['execution_mode'] ?? 'wordpress_pull'));
            if (array_key_exists('stable_connection_tokens', $result)) {
                $saved['stable_connection_tokens'] = !empty($result['stable_connection_tokens']);
            }
            update_option(self::OPTION_CONNECTION, $saved, false);
        }
        self::log_event('success', __('З’єднання з backend перевірено.', 'thesis-ai-bridge'), ['stage' => 'connection']);
        return $result;
    }

    public static function start_build(string $prompt, string $renderer = 'elementor'): array|WP_Error {
        $prompt = trim(wp_strip_all_tags($prompt));
        if (self::string_length($prompt) < 10) {
            return new WP_Error('thesis_ai_prompt_short', __('Please describe the website in a little more detail.', 'thesis-ai-bridge'));
        }
        if (self::string_length($prompt) > 6000) {
            return new WP_Error('thesis_ai_prompt_long', __('The website description is too long.', 'thesis-ai-bridge'));
        }
        if (!self::is_connected()) {
            return new WP_Error('thesis_ai_not_connected', __('Connect AI Builder before starting a real multi-agent build.', 'thesis-ai-bridge'));
        }
        $active = self::active_build();
        if (!empty($active['status']) && in_array((string)$active['status'], ['planning', 'executing', 'verifying', 'repairing'], true)) {
            return $active;
        }

        $snapshot = Thesis_AI_Bridge::execute_named_ability('get-site-snapshot', []);
        if (is_wp_error($snapshot)) {
            return $snapshot;
        }
        $c = self::full_connection();
        $path = '/v2/sites/' . rawurlencode((string)$c['site_id']) . '/plans';
        $body = self::backend_request('POST', $path, [
            'request' => $prompt,
            'renderer' => $renderer,
            'site_snapshot' => $snapshot,
        ], 25, $c);
        if (is_wp_error($body)) {
            return $body;
        }
        if (empty($body['job_id'])) {
            return new WP_Error('thesis_ai_plan_missing_job', __('Backend did not return a planning job.', 'thesis-ai-bridge'));
        }
        $active = [
            'job_id' => sanitize_text_field((string)$body['job_id']),
            'status' => 'planning',
            'phase' => 'planning',
            'stage' => sanitize_text_field((string)($body['stage'] ?? 'queued')),
            'progress' => 2,
            'detail' => sanitize_text_field((string)($body['detail'] ?? 'Multi-agent planning queued')),
            'prompt' => $prompt,
            'renderer' => $renderer,
            'executions' => [],
            'repair_attempts' => 0,
            'started_at' => gmdate('c'),
            'updated_at' => gmdate('c'),
            'initiated_by' => get_current_user_id(),
            'worker_mode' => 'wp_cron',
        ];
        $active['updated_at'] = gmdate('c');
        update_option(self::OPTION_ACTIVE_BUILD, $active, false);
        self::log_event('info', __('Build запущено. Аналізуємо запит і поточний стан сайту.', 'thesis-ai-bridge'), ['stage' => 'orchestrator', 'run_id' => (string)$active['job_id']]);
        self::kick_worker();
        return $active;
    }

    public static function ensure_worker(): void {
        if (!self::active_build()) {
            return;
        }
        if (!wp_next_scheduled(self::WORKER_HOOK)) {
            self::kick_worker();
        }
    }

    /**
     * Browser-poll fallback for hosts where loopback WP-Cron is delayed/disabled.
     * The browser is not the primary executor, but if the background worker has not
     * updated build state for a while and no worker lock is active, advance exactly
     * one short step. This prevents a sleeping cron queue from making the UI appear
     * frozen while preserving bounded request times.
     */
    public static function nudge_if_stale(int $stale_seconds = 20): void {
        $active = self::active_build();
        if (!$active) {
            return;
        }
        $updated = isset($active['updated_at']) ? strtotime((string)$active['updated_at']) : false;
        if ($updated !== false && (time() - $updated) < $stale_seconds) {
            return;
        }
        $lock = get_option(self::OPTION_WORKER_LOCK, false);
        if ($lock !== false && (time() - (int)$lock) < 90) {
            return;
        }
        $result = self::poll_build(false);
        if (is_wp_error($result)) {
            self::record_poll_error($result);
        }
        self::kick_worker();
    }

    private static function kick_worker(): void {
        if (!self::active_build()) {
            return;
        }
        if (!wp_next_scheduled(self::WORKER_HOOK)) {
            wp_schedule_single_event(time(), self::WORKER_HOOK);
        }
        // Spawn WordPress' own non-blocking cron request. The build therefore
        // continues even when the admin page is refreshed or the tab is closed.
        if (function_exists('spawn_cron')) {
            spawn_cron();
        }
    }

    public static function worker_tick(): void {
        $lock = get_option(self::OPTION_WORKER_LOCK, false);
        $now = time();
        if ($lock !== false) {
            $locked_at = (int)$lock;
            if ($locked_at > 0 && ($now - $locked_at) < 90) {
                return;
            }
            delete_option(self::OPTION_WORKER_LOCK);
        }
        if (!add_option(self::OPTION_WORKER_LOCK, (string)$now, '', false)) {
            return;
        }

        $active = self::active_build();
        if (!$active) {
            delete_option(self::OPTION_WORKER_LOCK);
            return;
        }

        $user_id = absint($active['initiated_by'] ?? 0);
        $original_user = get_current_user_id();
        if ($user_id > 0) {
            $user = get_user_by('id', $user_id);
            if ($user instanceof WP_User && user_can($user, 'manage_options')) {
                wp_set_current_user($user_id);
            }
        }

        $started = microtime(true);
        $iterations = 0;
        try {
            // Keep each cron request bounded. Planning may need several short
            // polls, while local WordPress actions can usually be drained quickly.
            while ((microtime(true) - $started) < 18.0 && $iterations < 10) {
                $iterations++;
                $result = self::poll_build(true);
                if (is_wp_error($result)) {
                    self::record_poll_error($result);
                    break;
                }
                $active = self::active_build();
                if (!$active) {
                    break;
                }
                if (!empty($active['error_count'])) {
                    $active['error_count'] = 0;
                    unset($active['last_error'], $active['last_error_at']);
                    update_option(self::OPTION_ACTIVE_BUILD, $active, false);
                }
                $phase = (string)($active['phase'] ?? '');
                if ($phase === 'planning') {
                    sleep(2);
                    continue;
                }
                // Executing/repairing: consume another short local action in this
                // worker request while there is still time. Verification is also
                // allowed once the queue has drained.
                if (!in_array($phase, ['executing', 'repairing', 'verifying'], true)) {
                    break;
                }
                // New plugins/themes require a fresh WordPress bootstrap. Never
                // create WooCommerce products in the same request that activated
                // WooCommerce; its classes may not be loaded yet.
                $history = array_values((array)($active['executions'] ?? []));
                $last = $history ? end($history) : null;
                $ability = is_array($last) ? (string)($last['action']['ability'] ?? '') : '';
                if (in_array($ability, [
                    'thesis-ai-bridge/ensure-approved-plugin',
                    'thesis-ai-bridge/install-approved-plugin',
                    'thesis-ai-bridge/activate-approved-plugin',
                    'thesis-ai-bridge/ensure-approved-theme',
                ], true) && !empty($last['executed'])) {
                    break;
                }
            }
        } finally {
            if ($original_user !== get_current_user_id()) {
                wp_set_current_user($original_user);
            }
            delete_option(self::OPTION_WORKER_LOCK);
        }

        if (self::active_build()) {
            // Continue in a fresh short request instead of holding one PHP request
            // for the full site build.
            self::kick_worker();
        }
    }

    public static function poll_build(bool $background = false): array|WP_Error {
        if (!$background && !current_user_can('manage_options')) {
            return new WP_Error('thesis_ai_forbidden', __('Administrator permissions are required.', 'thesis-ai-bridge'));
        }
        $active = self::active_build();
        if (!$active) {
            return new WP_Error('thesis_ai_no_active_build', __('There is no active build.', 'thesis-ai-bridge'));
        }

        $phase = (string)($active['phase'] ?? $active['status'] ?? 'planning');
        if ($phase === 'planning') {
            return self::poll_planning($active);
        }
        if (in_array($phase, ['executing', 'repairing'], true)) {
            return self::execute_next_local_action($active);
        }
        if ($phase === 'verifying') {
            return self::verify_local_result($active);
        }
        return new WP_Error('thesis_ai_invalid_phase', __('Build state is invalid. Start the build again.', 'thesis-ai-bridge'));
    }

    private static function poll_planning(array $active): array|WP_Error {
        $c = self::full_connection();
        $path = '/v2/sites/' . rawurlencode((string)$c['site_id']) . '/plans/' . rawurlencode((string)$active['job_id']);
        $body = self::backend_request('GET', $path, null, 20, $c);
        if (is_wp_error($body)) {
            if ($body->get_error_code() === 'thesis_ai_backend_404') {
                return self::restart_planning_after_backend_reset($active);
            }
            return $body;
        }
        $status = (string)($body['status'] ?? 'running');
        if ($status === 'failed') {
            $message = sanitize_text_field((string)($body['error'] ?? $body['detail'] ?? 'Planning failed.'));
            if (!empty($body['usage']) && is_array($body['usage'])) {
                $active['failure_usage'] = $body['usage'];
            }
            if (!empty($body['budget']) && is_array($body['budget'])) {
                $active['failure_budget'] = $body['budget'];
            }
            self::finalize_failed_build($active, $message, 'planning');
            return new WP_Error('thesis_ai_planning_failed', $message);
        }
        if ($status !== 'completed' || empty($body['result']) || !is_array($body['result'])) {
            $backend_progress = max(0, min(100, (int)($body['progress'] ?? 0)));
            $previous_stage = (string)($active['stage'] ?? '');
            $active['status'] = 'planning';
            $active['stage'] = sanitize_text_field((string)($body['stage'] ?? 'planning'));
            $active['progress'] = min(28, 3 + (int)floor($backend_progress * 0.25));
            $active['detail'] = sanitize_text_field((string)($body['detail'] ?? 'Agents are planning the site'));
            $active['updated_at'] = gmdate('c');
        update_option(self::OPTION_ACTIVE_BUILD, $active, false);
            if ($previous_stage !== (string)$active['stage']) {
                self::log_event('info', (string)$active['detail'], ['stage' => (string)$active['stage'], 'run_id' => (string)($active['job_id'] ?? '')]);
            }
            return $active;
        }

        $bundle = $body['result'];
        $offered = array_fill_keys((array)(Thesis_AI_Bridge::build_contract()['abilities'] ?? []), true);
        foreach ((array)($bundle['approved_actions'] ?? []) as $planned) {
            $full = (string)(($planned['action']['ability'] ?? ''));
            $short = str_starts_with($full, 'thesis-ai-bridge/') ? substr($full, strlen('thesis-ai-bridge/')) : '';
            if ($short === '' || !isset($offered[$short])) {
                self::finalize_failed_build($active, 'Bridge cannot execute planned ability: ' . $full . '. Update both backend and WordPress Bridge.', 'preflight');
                return new WP_Error('thesis_ai_ability_contract_mismatch', 'Bridge cannot execute planned ability: ' . $full);
            }
        }
        $queue = isset($bundle['approved_actions']) && is_array($bundle['approved_actions']) ? $bundle['approved_actions'] : [];
        $executions = [];
        foreach (['pending_actions', 'blocked_actions'] as $key) {
            foreach ((array)($bundle[$key] ?? []) as $item) {
                if (!is_array($item)) {
                    continue;
                }
                $executions[] = [
                    'action' => (array)($item['action'] ?? []),
                    'policy' => (array)($item['policy'] ?? []),
                    'executed' => false,
                    'result' => null,
                    'error' => $key === 'pending_actions' ? 'Waiting for human approval' : 'Blocked by policy',
                    'attempt' => 1,
                ];
            }
        }
        $active['bundle'] = $bundle;
        $active['queue'] = array_values($queue);
        $active['action_index'] = 0;
        $active['executions'] = $executions;
        $active['phase'] = 'executing';
        $active['status'] = 'executing';
        $active['stage'] = 'local_execution';
        $active['progress'] = 30;
        $active['detail'] = sprintf(__('Plan ready. Executing %d controlled WordPress actions locally.', 'thesis-ai-bridge'), count($queue));
        $active['updated_at'] = gmdate('c');
        update_option(self::OPTION_ACTIVE_BUILD, $active, false);
        self::log_event('success', sprintf(__('План готовий. Заплановано %d контрольованих WordPress-дій.', 'thesis-ai-bridge'), count($queue)), ['stage' => 'implementation_plan', 'run_id' => (string)($active['job_id'] ?? '')]);
        return $active;
    }

    /** Stable across page refreshes and WP-Cron retries, scoped to one build plan. */
    private static function action_journal_key(array $active, string $ability, array $parameters): string {
        $plan_id = sanitize_text_field((string)($active['bundle']['plan_id'] ?? $active['job_id'] ?? ''));
        return hash('sha256', $plan_id . '|' . $ability . '|' . wp_json_encode($parameters));
    }

    /** Return prior successful result; never cache failures as completed changes. */
    private static function previous_action_result(string $key): ?array {
        $record = get_option(self::ACTION_LOG_PREFIX . $key, null);
        return is_array($record) && !empty($record['executed']) ? $record : null;
    }

    private static function claim_action(string $key): bool {
        $lock_key = self::ACTION_LOCK_PREFIX . $key;
        if (add_option($lock_key, time(), '', false)) { return true; }
        $locked_at = (int)get_option($lock_key, 0);
        if ($locked_at > 0 && (time() - $locked_at) < 600) { return false; }
        delete_option($lock_key);
        return add_option($lock_key, time(), '', false);
    }

    private static function remember_action(string $key, mixed $result): void {
        update_option(self::ACTION_LOG_PREFIX . $key, [
            'executed' => true,
            'result' => self::compact_result($result),
            'completed_at' => gmdate('c'),
        ], false);
    }

    private static function execute_next_local_action(array $active): array|WP_Error {
        $queue = isset($active['queue']) && is_array($active['queue']) ? $active['queue'] : [];
        $index = max(0, (int)($active['action_index'] ?? 0));
        $total = count($queue);
        if ($index >= $total) {
            $active['phase'] = 'verifying';
            $active['status'] = 'verifying';
            $active['stage'] = 'verification';
            $active['progress'] = 84;
            $active['detail'] = __('All local actions finished. Quality & Security agent is verifying the actual site.', 'thesis-ai-bridge');
            $active['updated_at'] = gmdate('c');
        update_option(self::OPTION_ACTIVE_BUILD, $active, false);
            return $active;
        }

        $item = is_array($queue[$index]) ? $queue[$index] : [];
        $action = isset($item['action']) && is_array($item['action']) ? $item['action'] : [];
        $policy = isset($item['policy']) && is_array($item['policy']) ? $item['policy'] : [];
        $ability = sanitize_text_field((string)($action['ability'] ?? ''));
        $parameters = isset($action['parameters']) && is_array($action['parameters']) ? $action['parameters'] : [];
        $short = str_starts_with($ability, 'thesis-ai-bridge/') ? substr($ability, strlen('thesis-ai-bridge/')) : '';
        $executed = false;
        $result = null;
        $error = null;

        if ($short === '') {
            $error = 'Unsupported local ability namespace.';
        } else {
            $journal_key = self::action_journal_key($active, $ability, $parameters);
            $previous = self::previous_action_result($journal_key);
            if ($previous !== null) {
                $executed = true;
                $result = (array)($previous['result'] ?? []);
            } elseif (!self::claim_action($journal_key)) {
                // Do not advance the action_index. A concurrent worker owns it.
                return new WP_Error('thesis_ai_action_busy', __('This action is already executing. Retry shortly.', 'thesis-ai-bridge'));
            } else {
                try {
                    $raw = Thesis_AI_Bridge::execute_named_ability($short, $parameters);
                    if (is_wp_error($raw)) {
                        $error = $raw->get_error_message();
                    } else {
                        // Record success BEFORE advancing the build cursor.
                        // A worker crash cannot replay a completed action.
                        self::remember_action($journal_key, $raw);
                        $executed = true;
                        $result = self::compact_result($raw);
                    }
                } catch (Throwable $throwable) {
                    $error = get_class($throwable) . ': ' . $throwable->getMessage();
                } finally {
                    delete_option(self::ACTION_LOCK_PREFIX . $journal_key);
                }
            }
        }

        $active['executions'][] = [
            'action' => $action,
            'policy' => $policy,
            'executed' => $executed,
            'result' => $result,
            'error' => $error,
            'attempt' => max(1, (int)($active['repair_attempts'] ?? 0) + 1),
        ];
        $active['action_index'] = $index + 1;
        $is_repair = (string)($active['phase'] ?? '') === 'repairing';
        $base = $is_repair ? 88 : 30;
        $span = $is_repair ? 8 : 52;
        $active['progress'] = $total > 0 ? min($is_repair ? 96 : 82, $base + (int)floor((($index + 1) / $total) * $span)) : $base;
        $active['stage'] = $is_repair ? 'repair' : 'local_execution';
        $active['detail'] = sprintf(
            '%s %d/%d: %s%s',
            $is_repair ? 'Repair' : 'Build',
            $index + 1,
            $total,
            $short,
            $error ? ' — ' . $error : ''
        );
        if (($index + 1) >= $total) {
            $active['phase'] = 'verifying';
            $active['status'] = 'verifying';
            $active['stage'] = 'verification';
            $active['progress'] = 84;
        }
        $active['updated_at'] = gmdate('c');
        update_option(self::OPTION_ACTIVE_BUILD, $active, false);
        $event_type = $executed ? 'success' : 'error';
        $event_message = $executed
            ? sprintf(__('Виконано: %s', 'thesis-ai-bridge'), $short)
            : sprintf(__('Помилка дії %1$s: %2$s', 'thesis-ai-bridge'), $short, (string)$error);
        self::log_event($event_type, $event_message, ['stage' => $is_repair ? 'repair' : 'builder', 'run_id' => (string)($active['job_id'] ?? '')]);
        return $active;
    }

    private static function verify_local_result(array $active): array|WP_Error {
        $snapshot = Thesis_AI_Bridge::execute_named_ability('get-site-snapshot', []);
        if (is_wp_error($snapshot)) {
            return $snapshot;
        }
        $c = self::full_connection();
        $path = '/v2/sites/' . rawurlencode((string)$c['site_id']) . '/verify';
        $plan_actions = array_values((array)(($active['bundle']['approved_actions'] ?? [])));
        $compact_executions = [];
        foreach (array_values((array)($active['executions'] ?? [])) as $execution) {
            if (!is_array($execution)) { continue; }
            $action = (array)($execution['action'] ?? []);
            $index = null;
            foreach ($plan_actions as $n => $candidate) {
                if (($candidate['action']['ability'] ?? '') === ($action['ability'] ?? '') &&
                    ($candidate['action']['parameters'] ?? []) === ($action['parameters'] ?? [])) {
                    $index = $n;
                    break;
                }
            }
            $short_action = $action;
            // Elementor element arrays are already in the stored plan.
            if (isset($short_action['parameters']) && is_array($short_action['parameters'])) {
                unset($short_action['parameters']['elements'], $short_action['parameters']['content']);
            }
            $short_result = (array)($execution['result'] ?? []);
            // Results can include sizable opaque plugin data; only evidence is needed.
            $compact_executions[] = [
                'planned_action_index' => $index,
                'action' => $short_action,
                'policy' => (array)($execution['policy'] ?? []),
                'executed' => !empty($execution['executed']),
                'result' => array_intersect_key($short_result, array_flip(['id','slug','status','plugin_slug','product_id','product_slug','changed'])),
                'error' => substr((string)($execution['error'] ?? ''), 0, 400),
                'attempt' => max(1, (int)($execution['attempt'] ?? 1)),
            ];
        }
        $body = self::backend_request('POST', $path, [
            'plan_job_id' => (string)($active['job_id'] ?? ''),
            'executions' => $compact_executions,
            'verification_snapshot' => $snapshot,
            'repair_attempts' => max(0, (int)($active['repair_attempts'] ?? 0)),
        ], 55, $c);
        if (is_wp_error($body)) {
            return $body;
        }

        $quality = isset($body['quality_report']) && is_array($body['quality_report']) ? $body['quality_report'] : [];
        $repair = isset($body['repair_actions']) && is_array($body['repair_actions']) ? $body['repair_actions'] : [];
        if (!$quality) {
            return new WP_Error('thesis_ai_quality_missing', __('Backend did not return a quality report.', 'thesis-ai-bridge'));
        }

        if (empty($quality['passed']) && $repair) {
            $active['quality_report'] = $quality;
            $active['queue'] = array_values($repair);
            $active['action_index'] = 0;
            $active['repair_attempts'] = max(0, (int)($active['repair_attempts'] ?? 0)) + 1;
            $active['phase'] = 'repairing';
            $active['status'] = 'repairing';
            $active['stage'] = 'repair';
            $active['progress'] = 88;
            $active['detail'] = sprintf(__('Quality agent requested %d repair actions.', 'thesis-ai-bridge'), count($repair));
            $active['verification_usage'] = (array)($body['usage'] ?? []);
            $active['updated_at'] = gmdate('c');
        update_option(self::OPTION_ACTIVE_BUILD, $active, false);
            self::log_event('warning', sprintf(__('QA запросив repair loop #%d (%d дій).', 'thesis-ai-bridge'), (int)$active['repair_attempts'], count($repair)), ['stage' => 'repair', 'run_id' => (string)($active['job_id'] ?? '')]);
            return $active;
        }

        $summary = self::build_summary($active, $snapshot, $body);
        update_option(self::OPTION_LAST_BUILD, $summary, false);
        self::add_history($summary);
        self::log_event(!empty($quality['passed']) ? 'success' : 'error', !empty($quality['passed']) ? __('Build завершено успішно.', 'thesis-ai-bridge') : __('Build завершено з невирішеними проблемами.', 'thesis-ai-bridge'), ['stage' => 'completed', 'run_id' => (string)($summary['run_id'] ?? '')]);
        delete_option(self::OPTION_ACTIVE_BUILD);
        return [
            'status' => 'completed',
            'stage' => 'completed',
            'progress' => 100,
            'detail' => !empty($quality['passed']) ? __('Build completed and passed verification.', 'thesis-ai-bridge') : __('Build completed with unresolved issues.', 'thesis-ai-bridge'),
            'reload' => true,
        ];
    }

    private static function build_summary(array $active, array $snapshot, array $verify): array {
        $bundle = isset($active['bundle']) && is_array($active['bundle']) ? $active['bundle'] : [];
        $app = isset($bundle['application_spec']) && is_array($bundle['application_spec']) ? $bundle['application_spec'] : [];
        $required = [];
        foreach ((array)($app['pages'] ?? []) as $page) {
            if (is_array($page) && !empty($page['slug'])) {
                $required[(string)$page['slug']] = (string)($page['name'] ?? $page['slug']);
            }
        }
        $pages = [];
        foreach ((array)($snapshot['pages'] ?? []) as $page) {
            if (!is_array($page)) {
                continue;
            }
            $slug = (string)($page['slug'] ?? '');
            if ($slug === '' || ($required && !isset($required[$slug]))) {
                continue;
            }
            $page['title'] = (string)($page['title'] ?? ($required[$slug] ?? $slug));
            $page_id = (int)($page['id'] ?? 0);
            if ($page_id > 0 && class_exists('\\Elementor\\Plugin')) {
                $doc = \Elementor\Plugin::$instance->documents->get($page_id, false);
                if ($doc) {
                    $page['edit_url'] = (string)$doc->get_edit_url();
                }
            }
            $pages[] = $page;
        }

        $latest = [];
        foreach ((array)($active['executions'] ?? []) as $execution) {
            if (!is_array($execution)) {
                continue;
            }
            $action = (array)($execution['action'] ?? []);
            $key = (string)($action['ability'] ?? '') . '|' . wp_json_encode($action['parameters'] ?? []);
            $latest[$key] = $execution;
        }
        $failed = [];
        $plugins = [];
        $themes = [];
        $site_setup = [];
        foreach ($latest as $execution) {
            $action = (array)($execution['action'] ?? []);
            $ability = (string)($action['ability'] ?? '');
            if (empty($execution['executed'])) {
                $failed[] = [
                    'ability' => $ability,
                    'parameters' => self::safe_parameters((array)($action['parameters'] ?? [])),
                    'policy_reason' => (string)(($execution['policy']['reason'] ?? '')),
                    'error' => (string)($execution['error'] ?? 'Unknown execution error'),
                    'attempt' => (int)($execution['attempt'] ?? 1),
                ];
                continue;
            }
            $result = is_array($execution['result'] ?? null) ? $execution['result'] : [];
            if (str_contains($ability, 'approved-plugin')) {
                $plugins[] = ['slug' => $result['plugin_slug'] ?? ($action['parameters']['plugin_slug'] ?? ''), 'active' => $result['active'] ?? true, 'message' => $result['message'] ?? ''];
            } elseif ($ability === 'thesis-ai-bridge/ensure-approved-theme') {
                $themes[] = ['slug' => $result['theme_slug'] ?? ($action['parameters']['theme_slug'] ?? ''), 'active' => $result['active'] ?? true, 'message' => $result['message'] ?? ''];
            } elseif (in_array($ability, ['thesis-ai-bridge/apply-site-design', 'thesis-ai-bridge/update-site-identity', 'thesis-ai-bridge/ensure-navigation-menu', 'thesis-ai-bridge/set-homepage-by-slug', 'thesis-ai-bridge/set-page-seo', 'thesis-ai-bridge/ensure-contact-form', 'thesis-ai-bridge/configure-woocommerce'], true)) {
                $site_setup[] = ['ability' => $ability, 'result' => $result];
            }
        }

        $quality = isset($verify['quality_report']) && is_array($verify['quality_report']) ? $verify['quality_report'] : [];
        $usage = self::merge_usage((array)($bundle['usage'] ?? []), (array)($verify['usage'] ?? []));
        return [
            'run_id' => (string)($bundle['plan_id'] ?? ''),
            'status' => !empty($quality['passed']) ? 'passed' : 'failed',
            'agent_mode' => (string)($bundle['agent_mode'] ?? ($verify['agent_mode'] ?? 'unknown')),
            'model' => (string)($bundle['model'] ?? ($verify['model'] ?? '')),
            'model_router' => (array)($bundle['model_router'] ?? ($verify['model_router'] ?? [])),
            'project_brief' => (array)($bundle['project_brief'] ?? []),
            'architecture' => (array)($bundle['architecture'] ?? []),
            'content_matrix' => (array)($bundle['content_matrix'] ?? []),
            'capability_resolutions' => (array)($bundle['capability_resolutions'] ?? []),
            'budget' => (array)($bundle['budget'] ?? []),
            'pages' => $pages,
            'plugins' => $plugins,
            'themes' => $themes,
            'site_setup' => $site_setup,
            'issues' => array_values((array)($quality['issues'] ?? [])),
            'failed_actions' => $failed,
            'quality_summary' => (string)($quality['summary'] ?? ''),
            'renderer' => (string)($active['renderer'] ?? 'elementor'),
            'repair_attempts' => (int)($active['repair_attempts'] ?? 0),
            'usage' => $usage,
            'verification' => $snapshot,
            'execution_mode' => 'wordpress_pull',
            'prompt' => (string)($active['prompt'] ?? ''),
            'started_at' => (string)($active['started_at'] ?? ''),
            'completed_at' => gmdate('c'),
            'duration_seconds' => self::duration_seconds((string)($active['started_at'] ?? ''), gmdate('c')),
            'requested_at' => (string)($active['started_at'] ?? gmdate('c')),
        ];
    }

    public static function publish_last_build(): array|WP_Error {
        if (!current_user_can('manage_options')) {
            return new WP_Error('thesis_ai_forbidden', __('Administrator permissions are required.', 'thesis-ai-bridge'));
        }
        $build = self::last_build();
        if (($build['status'] ?? '') !== 'passed') {
            return new WP_Error('thesis_ai_publish_not_ready', __('Only a successfully verified build can be published.', 'thesis-ai-bridge'));
        }
        $pages = isset($build['pages']) && is_array($build['pages']) ? $build['pages'] : [];
        $published = [];
        foreach ($pages as &$page_summary) {
            $page_id = (int)($page_summary['id'] ?? 0);
            $post = $page_id > 0 ? get_post($page_id) : null;
            if (!$post instanceof WP_Post || $post->post_type !== 'page') {
                continue;
            }
            if ((string)get_post_meta($page_id, '_thesis_ai_generated', true) !== '1') {
                continue;
            }
            if ($post->post_status === 'publish') {
                $published[] = $page_id;
                continue;
            }
            if (!in_array($post->post_status, ['draft', 'pending'], true)) {
                continue;
            }
            $updated = wp_update_post(['ID' => $page_id, 'post_status' => 'publish'], true);
            if (is_wp_error($updated)) {
                return $updated;
            }
            $published[] = $page_id;
            $page_summary['status'] = 'publish';
            $page_summary['url'] = get_permalink($page_id) ?: ($page_summary['url'] ?? '');
        }
        unset($page_summary);
        if (!$published) {
            return new WP_Error('thesis_ai_publish_none', __('No AI-generated draft pages were eligible for publishing.', 'thesis-ai-bridge'));
        }
        $build['pages'] = $pages;
        $build['published_at'] = gmdate('c');
        $build['published_page_ids'] = $published;
        update_option(self::OPTION_LAST_BUILD, $build, false);
        self::add_history($build);
        self::log_event('success', sprintf(__('Опубліковано AI-сторінок: %d.', 'thesis-ai-bridge'), count($published)), ['stage' => 'published', 'run_id' => (string)($build['run_id'] ?? '')]);
        return ['published' => true, 'page_ids' => $published, 'count' => count($published)];
    }

    public static function demo_build(string $prompt): array|WP_Error {
        if (!current_user_can('manage_options')) {
            return new WP_Error('thesis_ai_forbidden', __('Administrator permissions are required.', 'thesis-ai-bridge'));
        }
        $result = Thesis_AI_Bridge::execute_named_ability('ensure-draft-page', [
            'title' => 'AI Demo', 'slug' => 'ai-demo',
            'content' => '<!-- wp:heading {"level":1} --><h1 class="wp-block-heading">AI Demo</h1><!-- /wp:heading --><!-- wp:paragraph --><p>' . esc_html($prompt) . '</p><!-- /wp:paragraph -->',
        ]);
        if (is_wp_error($result)) {
            return $result;
        }
        $out = ['status' => 'demo_completed', 'mode' => 'local_demo', 'pages' => [$result], 'quality_summary' => 'Local demo only.', 'requested_at' => gmdate('c')];
        update_option(self::OPTION_LAST_BUILD, $out, false);
        self::add_history($out);
        self::log_event('success', __('Локальне демо завершено.', 'thesis-ai-bridge'), ['stage' => 'demo']);
        return $out;
    }

    private static function finalize_failed_build(array $active, string $message, string $stage): void {
        $finished = gmdate('c');
        $summary = [
            'run_id' => (string)($active['job_id'] ?? ''),
            'status' => 'failed',
            'agent_mode' => (string)(($active['bundle']['agent_mode'] ?? '') ?: ''),
            'model' => (string)(($active['bundle']['model'] ?? '') ?: ''),
            'pages' => [],
            'plugins' => [],
            'themes' => [],
            'site_setup' => [],
            'issues' => [[
                'severity' => 'high',
                'description' => $message,
            ]],
            'failed_actions' => [],
            'quality_summary' => $message,
            'renderer' => (string)($active['renderer'] ?? 'elementor'),
            'repair_attempts' => (int)($active['repair_attempts'] ?? 0),
            'usage' => (array)(($active['bundle']['usage'] ?? []) ?: ($active['failure_usage'] ?? [])),
            'budget' => (array)(($active['bundle']['budget'] ?? []) ?: ($active['failure_budget'] ?? [])),
            'verification' => [],
            'execution_mode' => 'wordpress_pull',
            'prompt' => (string)($active['prompt'] ?? ''),
            'started_at' => (string)($active['started_at'] ?? ''),
            'completed_at' => $finished,
            'duration_seconds' => self::duration_seconds((string)($active['started_at'] ?? ''), $finished),
            'requested_at' => (string)($active['started_at'] ?? $finished),
            'failed_stage' => $stage,
        ];
        update_option(self::OPTION_LAST_BUILD, $summary, false);
        self::add_history($summary);
        self::log_event('error', $message, ['stage' => $stage, 'run_id' => (string)($active['job_id'] ?? '')]);
        delete_option(self::OPTION_ACTIVE_BUILD);
    }

    private static function add_history(array $summary): void {
        $history = self::build_history();
        $run_id = (string)($summary['run_id'] ?? '');
        if ($run_id !== '') {
            $history = array_values(array_filter($history, static fn($item): bool => !is_array($item) || (string)($item['run_id'] ?? '') !== $run_id));
        }
        array_unshift($history, $summary);
        $history = array_slice($history, 0, 12);
        update_option(self::OPTION_BUILD_HISTORY, $history, false);
    }

    private static function log_event(string $type, string $message, array $context = []): void {
        $events = self::event_log();
        $type = in_array($type, ['info', 'success', 'warning', 'error'], true) ? $type : 'info';
        $message = sanitize_text_field($message);
        if ($message === '') { return; }
        $fingerprint = md5($type . '|' . $message . '|' . (string)($context['stage'] ?? '') . '|' . (string)($context['run_id'] ?? ''));
        $last = $events[0] ?? null;
        if (is_array($last) && (string)($last['fingerprint'] ?? '') === $fingerprint) { return; }
        array_unshift($events, [
            'id' => wp_generate_uuid4(),
            'type' => $type,
            'message' => $message,
            'stage' => sanitize_key((string)($context['stage'] ?? '')),
            'run_id' => sanitize_text_field((string)($context['run_id'] ?? '')),
            'time' => gmdate('c'),
            'fingerprint' => $fingerprint,
        ]);
        update_option(self::OPTION_EVENT_LOG, array_slice($events, 0, 80), false);
    }

    private static function duration_seconds(string $start, string $end): int {
        $start_ts = $start !== '' ? strtotime($start) : false;
        $end_ts = $end !== '' ? strtotime($end) : false;
        if ($start_ts === false || $end_ts === false) { return 0; }
        return max(0, (int)($end_ts - $start_ts));
    }

    private static function compact_result(mixed $result): mixed {
        if (!is_array($result)) {
            return $result;
        }
        $copy = $result;
        unset($copy['elements'], $copy['content']);
        return $copy;
    }

    private static function safe_parameters(array $parameters): array {
        $allowed = ['plugin_slug', 'theme_slug', 'page_id', 'title', 'slug', 'site_title', 'menu_name'];
        return array_intersect_key($parameters, array_flip($allowed));
    }

    private static function merge_usage(array $a, array $b): array {
        $out = [];
        foreach (['requests', 'input_tokens', 'output_tokens', 'total_tokens'] as $key) {
            $out[$key] = (int)($a[$key] ?? 0) + (int)($b[$key] ?? 0);
        }
        $out['estimated_cost_usd'] = round((float)($a['estimated_cost_usd'] ?? 0) + (float)($b['estimated_cost_usd'] ?? 0), 6);
        $out['calls'] = array_values(array_merge((array)($a['calls'] ?? []), (array)($b['calls'] ?? [])));
        return $out;
    }

    /**
     * Request the planning backend. If a Render redeploy invalidated the
     * self-contained bearer token, reconnect once and transparently retry with
     * the new site_id/token. This keeps WordPress builds usable even when an
     * ephemeral backend key was rotated.
     */
    private static function backend_request(string $method, string $path, ?array $payload, int $timeout, ?array $connection = null, bool $allow_token_refresh = true): array|WP_Error {
        $c = $connection ?? self::full_connection();
        if (empty($c['backend_url'])) {
            return new WP_Error('thesis_ai_not_connected', __('AI Builder is not connected.', 'thesis-ai-bridge'));
        }
        $headers = ['Accept' => 'application/json', 'User-Agent' => 'Thesis-AI-Bridge/' . THESIS_AI_BRIDGE_VERSION];
        if (!empty($c['site_token'])) {
            $headers['Authorization'] = 'Bearer ' . (string)$c['site_token'];
        }
        $args = ['method' => $method, 'timeout' => $timeout, 'redirection' => 2, 'headers' => $headers];
        if ($payload !== null) {
            $headers['Content-Type'] = 'application/json';
            $args['headers'] = $headers;
            $args['body'] = wp_json_encode($payload);
        }

        $response = wp_remote_request(untrailingslashit((string)$c['backend_url']) . $path, $args);
        if (is_wp_error($response)) {
            return new WP_Error('thesis_ai_backend_unreachable', sprintf(__('Backend request failed: %s', 'thesis-ai-bridge'), $response->get_error_message()));
        }

        $code = (int)wp_remote_retrieve_response_code($response);
        $raw = (string)wp_remote_retrieve_body($response);
        $body = json_decode($raw, true);

        // Tokens issued without a persistent BACKEND_TOKEN_SECRET become invalid
        // after a Render restart/redeploy. Pull mode can safely establish a new
        // planning session because WordPress remains the source of truth.
        if ($code === 401 && $allow_token_refresh && !str_contains($path, '/connect')) {
            $old_site_id = (string)($c['site_id'] ?? '');
            $refreshed = self::refresh_connection($c);
            if (!is_wp_error($refreshed)) {
                $new_path = self::rewrite_site_path($path, $old_site_id, (string)($refreshed['site_id'] ?? ''));
                self::log_event(
                    'warning',
                    __('Backend token був недійсний після перезапуску сервісу. З’єднання оновлено автоматично.', 'thesis-ai-bridge'),
                    ['stage' => 'connection']
                );
                return self::backend_request($method, $new_path, $payload, $timeout, $refreshed, false);
            }
        }

        if ($code < 200 || $code >= 300 || !is_array($body)) {
            $detail = is_array($body) ? (string)($body['detail'] ?? 'Backend rejected the request.') : (function_exists('mb_substr') ? mb_substr(wp_strip_all_tags($raw), 0, 500) : substr(wp_strip_all_tags($raw), 0, 500));
            $error_code = $code === 404 ? 'thesis_ai_backend_404' : ($code === 401 ? 'thesis_ai_backend_401' : 'thesis_ai_backend_error');
            return new WP_Error($error_code, sprintf(__('AI backend error (%1$d): %2$s', 'thesis-ai-bridge'), $code, $detail));
        }
        return $body;
    }

    /**
     * Establish a fresh pull-mode connection using the already configured
     * backend URL. No WordPress credentials are sent to the cloud in v0.6.
     */
    private static function refresh_connection(array $previous): array|WP_Error {
        $backend_url = (string)($previous['backend_url'] ?? '');
        if ($backend_url === '') {
            return new WP_Error('thesis_ai_reconnect_missing_url', __('Backend URL is missing; reconnect AI Builder manually.', 'thesis-ai-bridge'));
        }
        $result = self::connect($backend_url);
        if (is_wp_error($result)) {
            return $result;
        }
        return self::full_connection();
    }

    private static function rewrite_site_path(string $path, string $old_site_id, string $new_site_id): string {
        if ($old_site_id === '' || $new_site_id === '' || $old_site_id === $new_site_id) {
            return $path;
        }
        foreach (['/v2/sites/', '/v1/sites/'] as $prefix) {
            $needle = $prefix . rawurlencode($old_site_id);
            if (str_starts_with($path, $needle)) {
                return $prefix . rawurlencode($new_site_id) . substr($path, strlen($needle));
            }
        }
        return $path;
    }

    /**
     * Planning jobs are intentionally in backend memory. If Render restarted,
     * the old job no longer exists. Re-plan automatically once from the prompt
     * persisted in WordPress instead of forcing the user to start over.
     */
    private static function restart_planning_after_backend_reset(array $active): array|WP_Error {
        $attempts = max(0, (int)($active['replan_attempts'] ?? 0));
        if ($attempts >= 1) {
            $message = __('Backend перезапустився повторно під час планування. Запустіть build ще раз.', 'thesis-ai-bridge');
            self::finalize_failed_build($active, $message, 'planning');
            return new WP_Error('thesis_ai_plan_lost', $message);
        }

        $c = self::full_connection();
        $snapshot = Thesis_AI_Bridge::execute_named_ability('get-site-snapshot', []);
        if (is_wp_error($snapshot)) {
            return $snapshot;
        }
        $path = '/v2/sites/' . rawurlencode((string)($c['site_id'] ?? '')) . '/plans';
        $body = self::backend_request('POST', $path, [
            'request' => (string)($active['prompt'] ?? ''),
            'renderer' => (string)($active['renderer'] ?? 'elementor'),
            'site_snapshot' => $snapshot,
        ], 25, $c);
        if (is_wp_error($body)) {
            return $body;
        }
        if (empty($body['job_id'])) {
            return new WP_Error('thesis_ai_plan_missing_job', __('Backend did not return a planning job after reconnect.', 'thesis-ai-bridge'));
        }

        $active['job_id'] = sanitize_text_field((string)$body['job_id']);
        $active['status'] = 'planning';
        $active['phase'] = 'planning';
        $active['stage'] = sanitize_text_field((string)($body['stage'] ?? 'queued'));
        $active['progress'] = max(2, min(8, (int)($active['progress'] ?? 2)));
        $active['detail'] = __('Backend session restored. Multi-agent planning restarted automatically.', 'thesis-ai-bridge');
        $active['replan_attempts'] = $attempts + 1;
        $active['last_error'] = '';
        $active['updated_at'] = gmdate('c');
        update_option(self::OPTION_ACTIVE_BUILD, $active, false);
        self::log_event('warning', $active['detail'], ['stage' => 'orchestrator', 'run_id' => (string)$active['job_id']]);
        return $active;
    }

    private static function string_length(string $value): int {
        return function_exists('mb_strlen') ? (int)mb_strlen($value) : strlen($value);
    }

    private static function encrypt_secret(string $plain): string|WP_Error {
        $key = hash('sha256', wp_salt('auth') . '|thesis-ai-bridge-v0.6', true);
        if (function_exists('sodium_crypto_secretbox')) {
            $nonce = random_bytes(SODIUM_CRYPTO_SECRETBOX_NONCEBYTES);
            return 'sodium:' . base64_encode($nonce . sodium_crypto_secretbox($plain, $nonce, $key));
        }
        if (function_exists('openssl_encrypt')) {
            $iv = random_bytes(12); $tag = '';
            $cipher = openssl_encrypt($plain, 'aes-256-gcm', $key, OPENSSL_RAW_DATA, $iv, $tag);
            if ($cipher !== false) {
                return 'openssl:' . base64_encode($iv . $tag . $cipher);
            }
        }
        return new WP_Error('thesis_ai_crypto_missing', __('The server needs Sodium or OpenSSL to protect the backend token.', 'thesis-ai-bridge'));
    }

    private static function decrypt_secret(string $sealed): string|WP_Error {
        // First try v0.6 key, then legacy v0.4/v0.5 key so upgrades keep the connection.
        foreach (['thesis-ai-bridge-v0.6', 'thesis-ai-bridge-v0.4'] as $suffix) {
            $key = hash('sha256', wp_salt('auth') . '|' . $suffix, true);
            if (str_starts_with($sealed, 'sodium:') && function_exists('sodium_crypto_secretbox_open')) {
                $raw = base64_decode(substr($sealed, 7), true);
                if ($raw !== false && strlen($raw) > SODIUM_CRYPTO_SECRETBOX_NONCEBYTES) {
                    $plain = sodium_crypto_secretbox_open(substr($raw, SODIUM_CRYPTO_SECRETBOX_NONCEBYTES), substr($raw, 0, SODIUM_CRYPTO_SECRETBOX_NONCEBYTES), $key);
                    if ($plain !== false) { return $plain; }
                }
            }
            if (str_starts_with($sealed, 'openssl:') && function_exists('openssl_decrypt')) {
                $raw = base64_decode(substr($sealed, 8), true);
                if ($raw !== false && strlen($raw) > 28) {
                    $plain = openssl_decrypt(substr($raw, 28), 'aes-256-gcm', $key, OPENSSL_RAW_DATA, substr($raw, 0, 12), substr($raw, 12, 16));
                    if ($plain !== false) { return $plain; }
                }
            }
        }
        return new WP_Error('thesis_ai_secret_decrypt', __('Could not decrypt the stored backend token.', 'thesis-ai-bridge'));
    }

    private static function normalize_backend_url(string $backend_url): string|WP_Error {
        $backend_url = untrailingslashit(esc_url_raw(trim($backend_url)));
        if ($backend_url === '') {
            return new WP_Error('thesis_ai_backend_missing', __('Backend URL is required.', 'thesis-ai-bridge'));
        }
        $scheme = strtolower((string)wp_parse_url($backend_url, PHP_URL_SCHEME));
        $host = strtolower((string)wp_parse_url($backend_url, PHP_URL_HOST));
        if ($scheme === 'https') { return $backend_url; }
        if ($scheme === 'http' && in_array($host, ['localhost', '127.0.0.1', '::1'], true)) { return $backend_url; }
        if (defined('THESIS_AI_ALLOW_INSECURE_BACKEND') && THESIS_AI_ALLOW_INSECURE_BACKEND) { return $backend_url; }
        return new WP_Error('thesis_ai_backend_https', __('The AI backend must use HTTPS.', 'thesis-ai-bridge'));
    }
}
