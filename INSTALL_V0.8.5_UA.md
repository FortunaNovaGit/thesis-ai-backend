# Оновлення Thesis AI до v0.8.5

1. Зробити backup тестового WordPress перед перебудовою AI-owned сторінок. **Не видаляти** WooCommerce, Elementor і дані товарів.
2. Розпакувати `wordpress-multiagent-mvp-v0.8.5-render.zip` і замінити backend-код у GitHub repo; Commit → Push → Render deploy. **Не змінювати** `BACKEND_TOKEN_SECRET`, `BACKEND_PAIRING_SECRET` чи існуючий `DATABASE_URL`.
3. Відкрити `https://<your-backend>.onrender.com/health`; перевірити `version: 0.8.5`, `editorial_quality_gate: v1`, `execution_mode: wordpress_pull`. Якщо `durable_jobs` false, перевірити PostgreSQL connection.
4. WordPress → Plugins → Add New → Upload Plugin → `thesis-ai-bridge-v0.8.5.zip` → Replace current with uploaded. Не видаляти попередній плагін з WP Admin, щоб не ризикувати його options.
5. AI Website Builder → Перевірити з'єднання → Прогнати preflight; переконатися, що Bridge 0.8.5.
6. Запустити 3-сторінковий тест. Додати 1–2 реальні фотографії з правильними описовими `alt`/title у Media Library, якщо потрібно тестувати медіа-підбір.
7. Перевірити Elementor-сторінки (desktop і mobile), що в кожній секції інший зміст, немає «ця сторінка має…», служебних підказок, дублювання заголовків і безглуздих товарних обіцянок.
8. Якщо planning завершиться `Content quality gate blocked deployment`, **це очікувана захисна зупинка**: перевірити вказані сторінку/тип issue перед наступним API build. Такий збій не означає, що плагін зламався.

## Важливо

- Новий CSS відображається на AI-owned сторінках; старі створені Elementor-документи треба **перебудувати**, щоб отримати нові класи та відмінні компоненти.
- Якщо WooCommerce Shop уже опублікована, Builder її не перезаписує.
- Якість «преміум» не гарантується без контентних джерел, зображень і реального browser QA. Не публікувати згенеровані сторінки автоматично.
