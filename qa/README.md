# Offline layout smoke

This is a synthetic Elementor-like CSS fixture and does **not** inspect a real WordPress site.
It asserts that a long Ukrainian heading never horizontally overlaps the right art panel at 1440px, and that at 900px/390px there is no horizontal scroll. Images in `qa/preview-*.png` are for internal review only and not real WP screenshots.

On a machine with Playwright and Chromium installed run `python qa/layout_smoke.py`. The source visual stylesheet is under the companion WordPress plugin at `../plugin/thesis-ai-bridge/assets/front.css`.
