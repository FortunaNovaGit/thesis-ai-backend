# Thesis AI v0.10.0 — Generative Visual Composer (перший працюючий зріз)

Дата збірки: 11 листопада 2026 року. **Статус: staging preview, НЕ фінальний production-ready реліз.**

## Реалізовано

- Новий детермінований модуль `app/visual_composer.py`: вибір безпечної Hero-композиції, перевірка медіа-можливостей, чесні fallback-рішення.
- Creative Director може задавати `hero_scene` (`editorial`, `cinematic`, `collage`, `poster`, `typographic`, `auto`), `hero_height` і `hero_motion` у кожній сторінці. Поля проходять Pydantic `Literal`-валідацію, `extra=forbid` збережено. Старі артефакти без нових полів сумісні через `auto`.
- `app/creative_pipeline.py` передає нові параметри у `SectionLayoutSpec` без зміни п'яти агентів або WordPress Pull.
- Elementor-компілятор залишає **окремими редагованими віджетами** H1, абзац, кнопку і до двох зображень. Немає довільного HTML/CSS/JS від LLM.
- Новий `assets/visual-composer.css` із п'ятьма окремими просторовими композиціями, CSS Grid, керованими накладаннями, масштабною типографікою, мобільними правилами та `prefers-reduced-motion`.
- Друге Hero-фото можна добровільно вибрати в адмінці WordPress Media Library. PHP перевіряє attachment ID і тип через `wp_attachment_is_image`, а URL бере лише з WordPress.
- `cinematic`/`collage` без відповідних власних фото перетворюються на `editorial` або `typographic`, замість вигаданих товарних фотографій чи великих порожніх заглушок.
- PHP Bridge додає стилі через `wp_enqueue_style()` з версією для скидання кешу. CSS не змінює чужі сторінки.
- `/health` та header плагіна оновлено до 0.10.0.

## Перевірено офлайн

- `118 passed` Python unit/regression tests (без OpenAI API).
- PHP syntax — 6 файлів без синтаксичних помилок; окремий PHP smoke для брифу пройдено.
- `node --check` для `admin.js` — успішно.
- `20/20` синтетичних браузерних перевірок: 5 Hero-сцен × 1440/900/390/320 px. Перевірено переповнення, видимість H1, декодування тестових зображень, JavaScript-помилки, стекування на mobile. Ранні проблеми специфічності CSS були знайдені та виправлені.

**Це не живий Elementor/EasyWP E2E і не підтвердження «wow» якості.** У синтетичних скриншотах зображення замінено локальними абстрактними SVG для тесту геометрії — вони НЕ включені в продакшн-сайт як фотографії товару.

## Не реалізовано в цьому зрізі

- Генерація ліцензованих фото, Media Pipeline та реальна автоматична перевірка авторських прав.
- V4/MCP adapter та складні власні Elementor custom widgets.
- Повний універсальний Visual Tree для всіх секцій — нові сцени застосовані насамперед до Hero; секції каталогу та текстових блоків використовують успадкований v0.9.4 компілятор.
- Автоматичне отримання та виправлення живих скриншотів EasyWP; `qa/visual_composer_smoke.py` є синтетичним, а `qa/visual_audit.py` лишається окремим ручним CLI.
- Повний Elementor Free Theme Builder для WooCommerce Shop Archive (це окремий технічний напрям).

## Наступні критерії приймання

1. Деплой backend і Bridge 0.10.0 на **staging**; перевірка `/health`, preflight, WordPress Pull.
2. Створення 3-page Fortuna Nova; вибір власного Hero-фото (і другого фото для колажу); перевірка Elementor editor.
3. Desktop/tablet/mobile скриншоти з реальних URL, перевірка overflow, навігації, CTA, WooCommerce, логів, Content Quality Gate.
4. Три незалежні генерації одного запиту, оцінка композицій, змісту, часу, token usage, фактичного API cost та кількості ручних правок.
