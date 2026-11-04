=== Thesis AI Bridge ===
Contributors: thesis-prototype
Tags: ai, elementor, abilities-api, automation, wordpress
Requires at least: 6.6
Requires PHP: 8.0
Stable tag: 0.9.1
License: GPLv2 or later

Controlled local WordPress execution layer for a five-agent master's thesis prototype.

== Description ==

Version 0.9.1 adds safe generative Elementor section geometry and responsive artwork while retaining the v0.8.5 WordPress Pull executor:

* Five-role artifact pipeline: Orchestrator, Architect/Capability, Design/Content/SEO, deterministic WordPress Implementation, Quality/Security.
* WordPress background worker continues builds even if the admin tab is refreshed, backgrounded or closed.
* Browser polling is an observer with a stale-worker fallback for hosts where loopback cron is delayed.
* Richer Elementor component library and site-wide DesignSystem application.
* Actual Elementor headings, buttons, shortcodes and text signals are returned to QA.
* Draft-first is expected and does not count as a QA defect.
* Approved plugin/theme execution, SEO, menu, homepage, forms, WooCommerce/ACF foundations remain policy-controlled.
* No SSH, raw SQL, shell or arbitrary filesystem abilities are exposed to the LLM.

== Installation ==

1. Upload and activate the plugin.
2. Open AI Website Builder.
3. Connect the Render backend once.
4. Ensure Render has OPENAI_API_KEY and AGENT_MODE=auto for real agents.
5. Describe the website and start the build.
6. Keep the builder page open or return later; build state is persisted in WordPress.
7. Review generated drafts in Elementor.
8. Publish only after explicit administrator confirmation.
