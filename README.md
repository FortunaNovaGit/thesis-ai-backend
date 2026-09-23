# WordPress Multi-Agent Thesis MVP v0.4.1

Ця версія додає повний preflight сайту, автоматичну інвентаризацію plugins, capability resolution, безпечне auto-install/activate approved plugins та Elementor Free adapter.

## Що змінилося у v0.4

1. Перед planning backend обов'язково виконує read-only preflight:
   - `get-site-info`
   - `list-plugins` — усі встановлені plugins
   - `inspect-capabilities` — відомі capabilities та стан approved plugins
2. Architect отримує реальний `SiteSnapshot` і не повинен планувати встановлення plugin, якщо capability уже доступна.
3. Додана atomic ability `ensure-approved-plugin`: якщо plugin відсутній — встановити з WordPress.org; якщо неактивний — активувати; якщо вже активний — нічого не змінювати.
4. Approved catalogue: Elementor, WooCommerce, ACF Free, Contact Form 7, Yoast SEO, Rank Math SEO.
5. Доданий Elementor Free renderer:
   - `elementor-get-status`
   - `elementor-get-page`
   - `elementor-ensure-draft-page`
6. Elementor payload проходить deterministic validation: дозволені тільки containers і обмежений список Free widgets; unknown widgets/settings відкидаються або блокуються.
7. Elementor document зберігається через Elementor Document API (`documents->get()->save()`), сторінки залишаються draft.
8. В UI можна вибрати Elementor / Gutenberg / Auto та окремо дозволити auto-install approved plugins.

## Безпека

- SSH / shell / raw SQL не використовуються.
- Plugin install дозволений тільки для hard-coded allowlist та тільки з WordPress.org.
- Unknown plugin slugs Policy Engine блокує.
- Builder не отримує Administrator password; використовується окремий AI Builder user + Application Password.
- Generated Elementor structure має limits на depth/element count і allowlist widget types.
- Existing/published/foreign pages не перезаписуються автоматично.
- Сторінки створюються як Draft.

## Тестовий workflow

`Prompt → Orchestrator → site/plugin preflight → Architect/Capability → Design/Content/SEO → Policy Engine → ensure plugins → Elementor/Gutenberg renderer → structural QA`

Browser/Playwright QA ще не підключений і не заявляється як пройдений.

## Render

Поточний backend сумісний з Render Docker Web Service. Після push нового коду Render auto-deploy має показати `/health` version `0.4.1`.

## Важливо для Render Free

Поточний SiteStore ще файловий. Для тестів це прийнятно, але deploy/restart може стерти connection state. Для production наступний етап — PostgreSQL.
