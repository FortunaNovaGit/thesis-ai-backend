=== Thesis AI Bridge ===
Contributors: thesis-prototype
Tags: ai, elementor, abilities-api, rest-api, automation, wordpress
Requires at least: 6.6
Requires PHP: 8.0
Stable tag: 0.5.0
License: GPLv2 or later

Controlled WordPress execution layer for a five-agent master's thesis prototype.

== Description ==

Version 0.5 includes:

* One-click backend connection through a dedicated low-privilege AI Builder user and Application Password.
* Native WordPress Abilities API support when available plus authenticated fallback REST.
* Full page/plugin/theme/site-structure preflight.
* Approved plugin and Hello Elementor theme installation/activation.
* Elementor Free document creation with controlled widgets and responsive settings.
* Site identity, primary navigation and static homepage setup.
* Contact Form 7 reusable form creation when required.
* Controlled SEO metadata with Yoast/Rank Math mapping and a lightweight fallback.
* Draft-first generation and a separate administrator-confirmed publish action.
* Audit logging and permission switches.

The LLM never receives SSH, raw SQL, shell, or arbitrary filesystem abilities.
Unknown abilities are blocked by the backend Policy Engine.

== Installation ==

1. Upload and activate the plugin.
2. Open AI Website Builder.
3. Connect the cloud backend.
4. Describe the website and start a build.
5. Review generated drafts in Elementor.
6. Publish only after explicit administrator confirmation.
