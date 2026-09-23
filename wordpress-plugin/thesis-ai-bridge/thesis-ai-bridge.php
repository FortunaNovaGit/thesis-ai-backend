<?php
/**
 * Plugin Name: Thesis AI Bridge
 * Description: Controlled WordPress execution layer for the five-agent thesis prototype. Supports native Abilities API when available and a secure fallback REST API.
 * Version: 0.3.0
 * Requires at least: 6.6
 * Requires PHP: 8.0
 * Author: Thesis Prototype
 * License: GPL-2.0-or-later
 * Text Domain: thesis-ai-bridge
 */

declare(strict_types=1);

if (!defined('ABSPATH')) {
    exit;
}

define('THESIS_AI_BRIDGE_VERSION', '0.3.0');
define('THESIS_AI_BRIDGE_FILE', __FILE__);
define('THESIS_AI_BRIDGE_DIR', plugin_dir_path(__FILE__));

require_once THESIS_AI_BRIDGE_DIR . 'includes/class-thesis-ai-bridge.php';
require_once THESIS_AI_BRIDGE_DIR . 'includes/class-thesis-ai-cloud.php';
require_once THESIS_AI_BRIDGE_DIR . 'includes/class-thesis-ai-bridge-admin.php';

register_activation_hook(__FILE__, ['Thesis_AI_Bridge', 'activate']);

Thesis_AI_Bridge::init();
Thesis_AI_Bridge_Admin::init();
