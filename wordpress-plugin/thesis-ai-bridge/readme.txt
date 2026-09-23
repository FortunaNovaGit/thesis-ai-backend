=== Thesis AI Bridge ===
Contributors: thesis-prototype
Tags: ai, abilities-api, rest-api, automation, wordpress
Requires at least: 6.6
Requires PHP: 8.0
Stable tag: 0.4.0
License: GPLv2 or later

Controlled WordPress execution layer for a five-agent master's thesis prototype.

== Description ==

Version 0.2 adds:

* Native WordPress Abilities API integration on WordPress 6.9+.
* Authenticated fallback REST API for older supported WordPress versions.
* Dedicated AI Builder role with a custom bridge capability.
* Draft page creation, page inspection and controlled existing-page updates.
* Installed plugin inspection.
* Approved WordPress.org plugin install/activate/deactivate operations.
* Security switches in Tools > Thesis AI Bridge.
* A safe self-test that creates a draft page only.
* A capped audit log that omits page content.

The plugin does not store LLM API keys or WordPress Application Passwords.
Use a dedicated WordPress user and an Application Password over HTTPS.

== Installation ==

1. Upload and activate the plugin.
2. Open Tools > Thesis AI Bridge.
3. Run the safe draft-page self-test.
4. Create a dedicated user with the AI Builder role.
5. Create an Application Password on that user profile.
6. Configure the external Python backend.

Plugin management, existing-page updates, and site-setting changes are disabled by default.
