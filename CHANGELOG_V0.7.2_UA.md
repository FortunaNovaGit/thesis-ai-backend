# v0.7.2 — Quality + Background Execution

Ця версія фокусується на двох проблемах, виявлених у реальному EasyWP тесті v0.7.1: слабкий/повторюваний Elementor-контент і build, який фактично міг зупинятися, коли вкладка браузера не була активною.

## Якість контенту

- Посилено Design / Content / SEO Agent: він генерує visitor-facing copy, а не planning notes.
- Додано deterministic content quality gate: у WordPress не повинні потрапляти фрази типу «ця сторінка має», «надати канал», «сформувати довіру», «контент секції» тощо.
- Architect нормалізує minimum page structure (hero, meaningful sections, CTA) до генерації контенту.
- Додано безпечний domain fallback для стоматології без вигаданих лікарів, адрес, цін, років досвіду чи статистики.
- Повторні section headings нормалізуються до запису в Elementor.
- Розширено Elementor component library: hero split, services/benefits/trust/process cards, contact split, booking form, FAQ та CTA band.
- DesignSystem тепер застосовується не лише до Elementor widgets, а й до базового theme chrome через Bridge ability `apply-site-design`.

## Менше LLM-викликів

- WordPress Implementation Agent за замовчуванням працює як deterministic compiler.
- Advisory Builder LLM вимкнено (`ENABLE_BUILDER_LLM_REVIEW=false`), оскільки точний BuildPlan уже можна зібрати із валідованих артефактів.
- Orchestrator, Architect, Design/Content/SEO та Quality залишаються окремими агентними ролями; deterministic execution layer не витрачає токени.

## QA

- Bridge передає в backend компактні сигнали фактичного Elementor документа: headings, buttons, shortcodes, widget counts та text excerpt.
- QA більше не вважає draft status проблемою: draft-first є очікуваною політикою безпеки.
- Structural QA без LLM перевіряє repeated headings, CTA, form shortcode, sparse Elementor tree, planning-copy leakage та SEO metadata.
- Repair є delta-based: виправляється лише проблемна сторінка/SEO/form, а не весь сайт.

## Швидкість та persistence

- Build більше не залежить від відкритої вкладки: WordPress WP-Cron worker продовжує planning → local actions → verification у коротких bounded requests.
- UI polling лише читає стан.
- Для хостингів із затриманим/відключеним loopback cron залишено browser fallback: якщо worker не оновлював стан 20 секунд, admin polling виконує лише один короткий безпечний step і знову запускає worker.
- `updated_at` зберігається при кожній зміні build state, що дозволяє відрізнити реальний довгий етап від завислого worker.

## Версія

Backend: `0.7.2`, architecture: `artifact_pipeline_v2`.
Bridge: `0.7.2`.
