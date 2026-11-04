# Offline browser geometry QA

This directory contains two **synthetic Elementor-like DOM** smoke tests. Neither opens a real WordPress preview or invokes OpenAI.

- `python qa/layout_smoke.py`: original v0.8.4 hero width regression.
- `python qa/generative_layout_smoke.py`: v0.9.0 four creative combinations × desktop 1440 / tablet 900 / mobile 390, asserting no horizontal overflow, no heading/art intersection, CTA within viewport. The screenshots are written under `../synthetic-layout-evidence/` for review.

Requires `pip install playwright` and `/usr/bin/chromium` (or adapt the script for your system browser). Run from backend working directory with companion plugin checked out at `../plugin/thesis-ai-bridge/assets/front.css` for the CSS fixture. This is **not** a substitute for actual staging WordPress / Elementor E2E or accessible contrast checks.
