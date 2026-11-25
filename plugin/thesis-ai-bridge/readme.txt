=== Thesis AI Bridge ===
Contributors: thesis-prototype
Tags: ai, elementor, abilities-api, automation, wordpress
Requires at least: 6.6
Requires PHP: 8.0
Stable tag: 0.13.0
License: GPLv2 or later

Controlled local WordPress execution layer for a five-agent master's thesis prototype.

== Description ==

Version 0.11.0 adds safe generative Elementor section geometry and responsive artwork while retaining the v0.8.5 WordPress Pull executor:

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

== v0.13.0 Auto Imagery ==
* AI images are generated automatically for every page opening and image-friendly section (up to 10 per build) unless the owner chooses "existing photos only".
* Owner-selected photos always take priority; generated images are native, replaceable Elementor Image widgets labelled as AI concepts.
* If image generation is not enabled on the backend, or a batch fails, the site is built without AI images instead of failing.
* Requires backend 0.13.0.

== v0.12.0 Rich Visual System ==
* New scoped stylesheet assets/rich-sections.css (only AI-owned pages, only sections compiled by backend 0.12).
* Sanitizer accepts native responsive font sizes, widget CSS classes (_css_classes) and in-page anchors (_element_id).
* Site design prints --tai-heading-font / --tai-body-font tokens.
* Requires backend 0.12.0 for the new look; older plans keep their previous look.

== v0.11.0 Hero Visual Composer ==

The WordPress Bridge now loads a scoped visual-composer.css stylesheet on AI-owned pages. It supports native Elementor editable Hero scenes selected by the Creative Director and an optional second WordPress attachment for owner-supplied collages. No arbitrary AI-generated HTML, CSS or JavaScript is executed. This is a staging preview; production quality must be verified in the actual editor.
