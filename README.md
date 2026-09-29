# WordPress Multi-Agent Thesis MVP — v0.5.1

Робочий прототип магістерської системи для автоматизованого формування WordPress-вебзастосунків за допомогою п'яти спеціалізованих агентів.

## Що вже робить v0.5

1. **Orchestrator** — створює task graph і координує workflow.
2. **Architect & Capability** — аналізує prompt, реальний WordPress, plugins/themes і визначає, чого бракує.
3. **Design / Content / SEO** — формує структурований дизайн, контент, адаптивність та SEO-специфікацію.
4. **WordPress Implementation** — через Policy Engine виконує лише контрольовані Bridge abilities.
5. **Quality & Security** — повторно інспектує реальний WordPress, формує issues і може запустити repair loop.

Основний renderer: **Elementor Free**. Gutenberg лишається fallback.

## Основний flow

```text
WordPress plugin
  -> Render/FastAPI backend
  -> Orchestrator
  -> Site preflight
  -> Architect & Capability
  -> Design / Content / SEO
  -> Builder
  -> Policy Engine
  -> Thesis AI Bridge abilities
  -> WordPress / Elementor
  -> Post-build verification
  -> Quality & Security
  -> Repair loop (за потреби)
```

## Нове у v0.5

- реальні OpenAI agents при наявному `OPENAI_API_KEY`; без ключа автоматично використовується deterministic mock;
- structured Pydantic outputs для всіх агентів;
- usage metrics (requests/input/output/total tokens);
- стабільні stateless connection tokens через `BACKEND_TOKEN_SECRET`, тому Render redeploy більше не має скидати підключення;
- повний preflight: site info, pages, plugins, themes, recognized capabilities, homepage/menu structure;
- approved theme resolver та автоматичний Hello Elementor;
- approved plugin resolver / reuse / install / activate;
- Elementor PageSpec renderer зі стилями, responsive containers, cards, buttons і shortcode widget;
- Contact Form 7 auto-install + створення reusable `AI Contact` форми, якщо prompt потребує форми/запису;
- site title + tagline;
- navigation menu;
- static homepage;
- SEO title + meta description; інтеграція з Yoast/Rank Math, а без них Bridge має власний lightweight frontend fallback;
- post-build verification snapshot;
- до 2 repair loops для безпечних idempotent actions;
- retry transient WordPress actions;
- human-in-the-loop publishing: агенти залишають сторінки draft; адмін окремою кнопкою публікує AI-owned pages після перевірки;
- default-deny Policy Engine, allowlist plugins/themes, без shell/raw SQL/direct filesystem abilities.

## Approved dependencies у v0.5

Plugins:
- Elementor
- WooCommerce
- Advanced Custom Fields
- Contact Form 7
- Yoast SEO
- Rank Math SEO

Theme:
- Hello Elementor

Система може **інспектувати всі** встановлені plugins/themes, але автоматично встановлює лише allowlisted dependencies.

## Render environment

Для існуючого Render Web Service додайте:

```text
AGENT_MODE=auto
OPENAI_MODEL=gpt-5.6-terra
OPENAI_API_KEY=<secret>          # потрібен тільки для real-agent mode
BACKEND_TOKEN_SECRET=<generated random secret>
AUTO_APPROVE_MEDIUM_RISK=true
ALLOW_INSECURE_WORDPRESS=false
ALLOW_PRIVATE_WORDPRESS=false
```

**BACKEND_TOKEN_SECRET не змінюйте після підключення сайтів.** Це master secret для self-contained encrypted site tokens. Якщо його змінити, WordPress треба перепідключити.

Після переходу з v0.4 на v0.5 потрібно один раз `Відключити -> Підключити AI Builder`, бо старий site token був створений іншим ключем.

## Локальний запуск

```bash
cp .env.example .env
docker compose up -d --build
```

Backend: `http://localhost:8000/health`

## Тести

```bash
pytest -q
```

v0.5 test suite покриває Policy Engine, stateless connection tokens, rerunnable page creation, plugin/theme resolver і повний mock Elementor workflow із формою, menu/homepage/site identity.

## Що свідомо ще НЕ входить

- повний Playwright browser/visual QA;
- автоматична генерація/пошук зображень;
- повний ACF data-model executor;
- повна WooCommerce конфігурація/товари/shipping/checkout;
- PostgreSQL project/run history.

Ці речі логічно додавати після стабілізації real-agent Elementor generation. Поточна версія вже готує для них capability/plugin layer.


## Async build flow (v0.5.1)

WordPress no longer waits for the whole build in one `admin-post.php` request. The plugin starts a job using `POST /v1/sites/{site_id}/builds`, redirects back to wp-admin, and polls `GET /v1/sites/{site_id}/builds/{job_id}` via short AJAX requests. This avoids hosting gateway timeouts during long agent/Elementor workflows.

For the current test deployment the job registry is in process memory. Do not redeploy Render during an active build. A durable PostgreSQL queue is planned for the next infrastructure milestone.
