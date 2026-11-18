# Thesis AI Bridge 0.12.0 — Rich Visual System

- New `assets/rich-sections.css`, enqueued only on AI-owned pages after `visual-composer.css`. Every selector is scoped to `body.thesis-ai-generated` and `.tai-rich` sections, so pages compiled by older backends keep their look.
- Elementor sanitizer accepts `_css_classes` (sanitize_html_class), `_element_id` (`[a-z0-9-]`, max 40), `typography_font_size_tablet/_mobile`, `typography_letter_spacing`, `typography_font_style` (`normal|italic`), `align_mobile`. The widget allowlist is unchanged.
- Site design CSS prints `--tai-heading-font` / `--tai-body-font` tokens.
- Requires backend 0.12.0 for the new section system. Not yet verified on live EasyWP/Elementor.
