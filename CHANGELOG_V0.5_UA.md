# v0.5.0 — Real agents + site assembly

## Agent layer
- `AGENT_MODE=auto`: OpenAI при наявному key, mock без key.
- 5 structured agents із Pydantic outputs.
- Token/request usage metrics.
- Post-build verification + repair loop.

## WordPress / Elementor
- Full preflight inventory: pages/plugins/themes/capabilities/site structure.
- Approved Hello Elementor theme resolver.
- Elementor responsive renderer: containers/headings/text/buttons/cards/shortcode.
- Contact Form 7 resolver + reusable AI Contact form.
- Site title/tagline, navigation, homepage.
- SEO metadata + Yoast/Rank Math mapping + internal fallback output.
- Human-approved publish button for AI-owned draft pages.

## Security / stability
- Stateless encrypted site token with stable `BACKEND_TOKEN_SECRET`.
- Policy allowlists for plugins/themes.
- Unknown abilities default-deny.
- No raw SQL, shell or direct filesystem ability for the LLM.
- Only AI-owned drafts are automatically updated.
- Human approval remains required for publishing.

## Deferred
- Playwright/visual QA.
- Full ACF model execution.
- Full WooCommerce store execution.
- Image generation/media selection.
- PostgreSQL project/run history.
