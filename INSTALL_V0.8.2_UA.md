# Оновлення до v0.8.2 (Render + WordPress)

1. **Переконайтесь, що backup є.** Зробіть копію WordPress перед оновленням, хоча система повинна змінювати тільки AI-owned drafts.
2. **Render:** повністю замініть backend v0.8.1 файлами ZIP v0.8.2 у GitHub. Commit → Push → redeploy.
3. Збережіть незмінними `BACKEND_TOKEN_SECRET` і `BACKEND_PAIRING_SECRET`. Для персистентного зберігання jobs встановіть `DATABASE_URL` через Internal Database URL з PostgreSQL у Render. Перевірте, що `GET /health` повертає `version: 0.8.2`, `architecture_version: artifact_pipeline_v4_commerce`, `durable_jobs: true`.
4. **WordPress:** Plugins → Add New Plugin → Upload Plugin → виберіть `thesis-ai-bridge-v0.8.2.zip` → Replace current with uploaded. **Не видаляйте старий плагін вручну.** Якщо помилка `Could not create directory .../wp-content/upgrade/...`, перевірте filesystem permissions/вільний простір або замініть файли через SFTP (із backup). Перепакування ZIP не усуває permission issue.
5. AI Website Builder → Перевірити з'єднання → Preflight.
6. **Безплатний контрольний тест:** у Render `AGENT_MODE=mock` і короткий ecommerce prompt з двома явно названими товарами `«Асорті 16 цукерок»`, `«Асорті 24 цукерки»`. Ці назви з'являться як WooCommerce draft products, якщо WooCommerce активний та доступні medium-risk abilities. Не очікуйте, що mock створить повноцінний брендований сайт.
7. Перед реальним AI-тестом перевірте `MAX_BUILD_COST_USD`, `MAX_TOTAL_LLM_TOKENS`, `MAX_LLM_CALLS`; поверніть `AGENT_MODE=auto`, переконайтеся, що API key лише в Render. Старі 3 сторінки можна залишити: AI-owned drafts мають бути перевикористані, а не дубльовані.
8. Після build перевірте WordPress → Products → All Products. Обидва товари повинні мати **Draft** і порожні price/stock/image. Перевірте сторінки Elementor і QA. Не публікуйте неповний checkout/каталог.

## Тестовий prompt

> Створи мінімалістичний сайт майстерні шоколадних цукерок українською. Три сторінки: Головна, Магазин, Контакти. Використай Elementor і WooCommerce. Створи чернетки товарів «Асорті 16 цукерок» і «Асорті 24 цукерки». Не вигадуй ціни, склад, алергени, адресу, фотографії чи відгуки. Налаштуй меню, SEO і homepage, але нічого не публікуй. Використовуй наявні фото із WordPress Media Library, лише якщо вони справді відповідають товару.

## Якщо знову з'явиться помилка

- `413`: перевірте, що backend і Bridge обидва **v0.8.2**. Новий `/verify` має надсилати `plan_job_id` і компактні executions, не bundle.
- `409 Planning job unavailable`: перевірте `DATABASE_URL`, health `durable_jobs=true`, тривалість retention і що обидва сервіси звертаються до тієї самої БД.
- `520`: перевірте Render Logs навколо timestamp. Це може бути проблема origin, не обов'язково payload.
- `WooCommerce must be installed and active`: перевірте installed/active plugins. Після активації background worker має продовжити роботу в новому PHP request.

Не змінюйте `BACKEND_TOKEN_SECRET`, не публікуйте без ручного перегляду.
