# Thesis AI v0.9.0 — Generative Website Designer (foundation / Phase 1)

Дата: 2026-11-04. **Базується безпосередньо на v0.8.5**, без заміни FastAPI, PostgreSQL, Policy Engine, WordPress Pull або п'яти агентів.

## Що реалізовано

1. **Content Quality Gate v2**: `app/editorial_repair.py` виконує обмежений локальний ремонт повторів заголовків на сторінці та між сторінками. Не вигадує бізнес-факти та не вимикає `audit_experience()`. Діагностика показує page/section index/heading. Repair log додається до planning artifact як `content_quality.repairs`.
2. **Creative Director** — розширена роль існуючого Design/Content/SEO агента (всього агентів, як і раніше, **п'ять**). Один LLM design call пропонує 2–3 оригінальні концепції, обирає одну та видає `GenerativeDesignSpec` зі специфікаціями секцій. `creative_seed` — нове незалежне значення на кожний запуск; seed не потрапляє у відвідувацький текст. Не є гарантією унікальності.
3. **Типізований контракт** — `CreativeDirection`, `GenerativeDesignSpec`, `PageLayoutSpec`, `SectionLayoutSpec` з межами геометрії та забороною зайвих полів. `app/generative_design.py` перевіряє посилання на page slug/index і обраний direction. У режимі OpenAI Elementor-план блокується, якщо немає валідного GenerativeDesignSpec/Home hero. Немає довільного CSS/HTML/JS чи зовнішніх URL в layout spec.
4. **Elementor Free V3 adapter (розширений)** — нативні редаговані `container` / `widget` дерева, збережений stable root ID секції, варіативні композиції (`split`, `stacked`, `centered`, `offset`), пропорції колонок, медіа, адаптивні сітки 1–4, геометрія та абстрактні мотиви. Індексне зіставлення після reconcile / додавання product showcase.
5. **Creative palette precedence** — якщо Creative Director повернув `GenerativeDesignSpec`, старий жорстко прописаний «шоколадний preset» **не перезаписує** обрані ним кольори та шрифти. Старе правило залишене для legacy-планів без GenerativeDesignSpec.
6. **Bridge v0.9.0** — розширено `assets/front.css` адаптивними ізольованими стилями `body.thesis-ai-generated`; немає зміни схеми abilities чи алгоритму роботи локального executor. Додатково відфільтровано CSS font-family символи у PHP output. WooCommerce системна `/shop/` залишається чужою для Elementor-драфтів.
7. **Відтворювані offline тести** — нові `tests/test_v090_generative.py`, синтетичний `qa/generative_layout_smoke.py` для 4 композицій × 3 ширин.

## Перевірено на момент пакування

- `pytest -q`: **75 passed**. Немає OpenAI API викликів.
- PHP CLI lint 5 файлів: **усі без синтаксичних помилок**.
- Chromium/Playwright synthetic DOM: **12/12** на 1440/900/390 px. Немає горизонтального overflow, overlap H1/media чи виходу CTA за екран у підготовлених fixture-сценаріях.
- `python -m compileall -q app`: без помилок.

## Що ще НЕ реалізовано і НЕ доведено

- Реальне E2E на тестовому EasyWP із Elementor та порівняння скриншотів live preview (у поточному середовищі немає доступу до WP адмінки).
- Гарантований wow-результат, 100% оригінальність тексту/дизайну, сайт без ручного доопрацювання.
- Media Pipeline, генерація/ліцензування зображень, V4/MCP adapter, автоматичний live Playwright Visual Critic + targeted repair, accessibility/Lighthouse/ZAP і production-grade rollback/HMAC approvals.
- Важливо: стиль у synthetic preview доводить лише геометричну стійкість, не поведінку конкретної версії Elementor у клієнтському WordPress.

## Сумісність

| Backend | WP Bridge | Режим |
|---|---|---|
| 0.9.0 | 0.9.0 | Рекомендований для тестів Generative Design |
| 0.8.5 | 0.8.5 | Остання раніше підтверджена збірка / rollback |

Backend 0.9.0 повторно використовує старі allowlisted abilities; хмарні токени й PostgreSQL не потребують зміни. Не обертайте існуючі секрети заради оновлення.
