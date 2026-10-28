# Thesis AI — v0.8.4 Layout Safety & Elementor MCP Discovery

## Обсяг цього релізу

Це **перший контрольований крок до професійного Visual Engine**, а не готовий V4/MCP builder.

- Виправлено геометрію Hero: замість 60% + 46% + 52 px використовується двоколонкова CSS Grid із `minmax(0, fr)`, яка переходить в одну колонку на вузьких екранах.
- Обмежено заголовки `clamp()`, додано перенесення довгих українських слів та адаптивні відступи.
- Нові AI-owned Elementor draft pages використовують справжню мета-настройку WordPress `_wp_page_template=elementor_full_width`, а не лише поле Elementor document settings. Жодних змін сторінок, які не належать Builder.
- CSS стилів завантажується для створених Builder сторінок, навіть якщо `apply-site-design` не спрацювала, та обмежується `.thesis-ai-generated`.
- Вилучено випадковий декоративний текст з правого блоку Hero. Без реального зображення лишається лише нейтральний CSS placeholder.
- Media matcher враховує назви і тексти секцій та українські словоформи. Для реальних товарних карток можна використати фото із WordPress Media Library, але лише якщо назва/alt підтверджують релевантність.
- `elementor-get-status` містить **read-only** ознаки сумісності з Elementor MCP для WordPress 6.8+ / Elementor 4.3+. Це не MCP-клієнт і не його активація.
- Додані Python regression тести та окремий синтетичний Chromium smoke test на ширинах 1440, 900 і 390 px.

## Що цей реліз НЕ робить

- Не підключається автоматично до Elementor MCP і не отримує Application Password. Потрібна явна згода адміністратора.
- Не замінює старий V3 Document Adapter на Elementor V4 Atomic API.
- Не генерує фото шоколадних виробів і не вигадує дані магазину.
- Не підтверджує відсутність visual-багів на реальному EasyWP — для цього потрібен browser QA після деплою.
- Не гарантує, що макет без справжніх фотографій буде готовий до публікації.

## Наступний крок

Протестувати на тестовому сайті Elementor MCP v4.3+ після явної авторизації, отримати read-only список доступних tools / abilities, створити одну тестову Atomic draft page, порівняти її з нашим V3 Document Adapter та додати desktop/mobile screenshot QA. Не передавати Application Password у prompt до звичайного LLM, GitHub або логи.
