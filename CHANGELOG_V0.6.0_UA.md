# v0.6.0 — Stable Pull Execution

## Головна зміна

Повністю прибрано `Render → WordPress` execution path під час build.

Тепер:

`WordPress → Render (планування) → WordPress локально виконує actions → Render (QA/repair)`.

Це прибирає дві основні проблеми попередніх версій:

- `429 Too Many Requests` від EasyWP firewall;
- `504 Gateway Timeout` через довгий синхронний WordPress/PHP request.

## Що працює

- 5 агентів: Orchestrator, Architect/Capability, Design/Content/SEO, Implementation, Quality/Security.
- Structured outputs через OpenAI Agents SDK.
- Preflight зі snapshot WordPress.
- Policy Engine перед кожною build action.
- Локальне поетапне виконання abilities у WordPress.
- Elementor Free renderer.
- Approved plugin auto-install/activation.
- Hello Elementor auto-install/activation.
- Contact Form 7 form provisioning.
- SEO metadata.
- Site title/tagline, navigation, static homepage.
- Basic WooCommerce configuration + core pages.
- ACF Free CPT/field scaffold для structured content.
- QA + repair loop.
- Draft-first + human publish.
- State resume: якщо закрити сторінку, build можна продовжити після повернення.
- Legacy v0.5 Application Password автоматично відкликається — v0.6 він не потрібен.

## OpenAI

Для реальних агентів у Render потрібні:

- `AGENT_MODE=auto`
- `OPENAI_API_KEY=...`
- `OPENAI_MODEL=gpt-5.6-sol`

Без API key backend свідомо переходить у `mock`.
