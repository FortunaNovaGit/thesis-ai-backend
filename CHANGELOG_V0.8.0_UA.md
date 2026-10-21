# v0.8.0 — Stability + Visual Engine foundation

## Backend
- Обов'язкова перевірка Bridge ability contract для підключених сайтів до першого платного LLM-виклику. Старий Bridge без контракту завершується зрозумілою помилкою.
- Перевірка **всіх** abilities фактичного BuildPlan перед передачею до WordPress.
- Ранній контроль можливості встановити required plugins: налаштування plugin-management і спосіб доступу до файлової системи WordPress.
- SiteSnapshot включає `bridge_contract`, `media` та `commerce`.
- Elementor hero відображає релевантне зображення з **поточної медіатеки WordPress** або безпечну типографічну композицію (не зовнішню картинку).
- Заголовки секцій детерміновано нормалізуються без повторів H1 як H2.
- Секція `products` використовує WooCommerce `[products]` **лише коли вже є опубліковані товари**. Не видаємо текстові картки за реальні продукти.
- Додані вказівки агенту щодо композиції, UX й відсутності вигаданих фактів.
- QA для реального підключеного e-commerce сайту попереджає про порожній каталог.
- 35 Python tests passed; PHP syntax lint passed (середовище не WordPress).

## WordPress Bridge
- `get-build-contract`: список доступних abilities, версія, файловий метод, можливість plugin management.
- `get-site-snapshot` повертає контракт, до 25 фото з Media Library та кількість опублікованих WooCommerce products.
- Локальний worker перевіряє весь action queue **до першої зміни сайту**.
- Встановлення плагінів повертає конкретніші помилки щодо filesystem credentials / writable plugin directory / upgrader errors.
- Elementor image widget може посилатися тільки на валідний attachment ID цього самого WordPress (URL не довіряється моделі).
- `configure-woocommerce` / `apply-acf-model` отримали відсутню перевірку дозволів для локального виконання.
- У результаті є нагадування: Draft не стане публічною головною сторінкою без перевірки та публікації.

## Що ще не реалізовано
- Автоматичне створення WooCommerce product drafts та управління цінами/складом/залишками.
- AI-generated продуктова фотозйомка, генерація картинок та автоматичний пошук зображень із ліцензіями.
- Повноцінний Playwright/visual QA в реальному браузері.
- Продакшн-тест на EasyWP і OpenAI API: це окремий інтеграційний етап.

## Наступна ітерація
- v0.8.1: більш різноманітна типографіка і шаблони, повноцінна медіа-секція, скриншоти responsive QA.
- v0.8.2: WooCommerce draft products + каталоги + контрольовані тестові checkout flows.
