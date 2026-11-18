# Offline browser geometry QA

This directory contains two **synthetic Elementor-like DOM** smoke tests. Neither opens a real WordPress preview or invokes OpenAI.

- `python qa/layout_smoke.py`: original v0.8.4 hero width regression.
- `python qa/generative_layout_smoke.py`: v0.9.0 four creative combinations × desktop 1440 / tablet 900 / mobile 390, asserting no horizontal overflow, no heading/art intersection, CTA within viewport. The screenshots are written under `../synthetic-layout-evidence/` for review.

Requires `pip install playwright` and `/usr/bin/chromium` (or adapt the script for your system browser). Run from backend working directory with companion plugin checked out at `../plugin/thesis-ai-bridge/assets/front.css` for the CSS fixture. This is **not** a substitute for actual staging WordPress / Elementor E2E or accessible contrast checks.

## v0.9.4 regression from live screenshot defects

- `python qa/v094_breakout_smoke.py`: synthetic WordPress-like **770px narrow theme** forced on a 1440px viewport; checks full-bleed, theme title hidden, overflow, CTA at 1440/900/390/320. Does **not** access WordPress or OpenAI.
- `python qa/visual_audit.py --url 'https://your-staging-url/' --output qa/evidence`: actual staging screenshot + DOM checks with `narrow_ai_canvas`, `duplicate_theme_page_title`, `large_decorative_placeholder`, `offscreen_ai_section`. Requires optional Playwright. For a private preview use a locally created `--storage-state` and keep that file confidential. Browser-based aesthetic judgement and automated repair are not yet implemented.

## v0.12 Rich Visual System preview

- `python qa/rich_preview.py <out> --plugin <path-to>/thesis-ai-bridge [--direction warm|minimal] [--tag name]`: compiles a 7-section Fortuna Nova Home with the real compiler, emulates Elementor's per-widget CSS at the same specificity (`.elementor-<post> .elementor-element.elementor-element-<id>`), loads `front.css` + `visual-composer.css` + `rich-sections.css`, and captures 1440/390 screenshots with and without a hero photo. Asserts: no horizontal overflow, no clipped headings, exactly one H1, no JS errors. Synthetic evidence only — not a live Elementor render.
