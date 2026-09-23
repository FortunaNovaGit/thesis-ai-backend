# v0.4.1 — що саме реалізовано

- Real site preflight before agents plan changes.
- Full installed plugin inventory with active/version/update metadata.
- Recognized capability map for Elementor, WooCommerce, ACF, forms and SEO.
- Approved plugin metadata lookup from WordPress.org.
- Idempotent `ensure-approved-plugin`.
- Elementor status/read/write abilities.
- Safe Elementor document sanitizer: max depth 8, max 250 elements, allowlisted widgets/settings.
- Elementor Document API save, built-with-Elementor flag, page-level cache/CSS invalidation handled by Elementor save flow.
- Elementor/Gutenberg renderer selection in WordPress UI.
- Per-build explicit checkbox for approved plugin auto-install.
- SiteSnapshot passed into Architect and Builder so they can reuse existing capabilities.
- Policy Engine updated with all v0.4 abilities and Elementor in plugin allowlist.
