# Встановлення v0.8.1 — Render + WordPress

1. **Зупинити нові build-и**. Не розпочинати оновлення під час активного запуску.
2. Створити PostgreSQL DB в Render (або іншу доступну PostgreSQL). У Web Service → Environment додати `DATABASE_URL`, взявши internal connection string із Render DB. SQLAlchemy підтримує `postgresql://...` та `postgresql+psycopg://...`. Пароль DB не публікувати.
3. **Не змінювати** `BACKEND_TOKEN_SECRET`, `OPENAI_API_KEY`. Рекомендовано один instance/worker (поточний Dockerfile запускає один uvicorn worker).
4. Замінити в GitHub файли backend на вміст `wordpress-multiagent-mvp-v0.8.1-render.zip` (саму ZIP у GitHub не завантажувати як застосунок), зробити Commit → Push → Render Deploy.
5. Відкрити `/health`: повинно бути `version: 0.8.1`, `durable_jobs: true`, `job_store: postgresql`, `stable_connection_tokens: true`. Якщо `durable_jobs: false` — PostgreSQL не налаштовано й persistence у Render **не гарантована**.
6. WordPress: Plugins → Add New → Upload Plugin → новий `thesis-ai-bridge-v0.8.1.zip` → Replace current with uploaded. Не видаляти старий плагін перед оновленням. Якщо EasyWP знову дасть `Could not create directory` у `wp-content/upgrade`, перевірити права/вільне місце або скопіювати розпаковану папку `thesis-ai-bridge/` через SFTP (з резервною копією).
7. Перевірити Bridge `0.8.1` → З'єднання → Перевірити, потім «Прогнати preflight». Existing site token сумісний, якщо secret незмінний.
8. Для **безкоштовної локальної перевірки**: з backend repository виконати `pytest -q`; з PHP source пакета — `php -d zend.assertions=1 -d assert.exception=1 tests/test_action_journal.php`.
9. Для AI-тесту в Render бажано встановити `MAX_BUILD_COST_USD=0.30`, `MAX_TOTAL_LLM_TOKENS=20000`, `MAX_LLM_CALLS=8`, `MAX_REPAIR_LOOPS=1` — guardrails перевіряються між викликами LLM, не є абсолютною гарантією суми.

## Примітки

- Нові WordPress-токени не містять administrator credentials. Старі токени залишаються сумісними — бажано пізніше оновити їх через ручне перепідключення.
- Новий журнал idempotency діє в межах одного плану. Визначені AI-сторінки повинні редагуватися, а не дублюватися.
- Persisted planning jobs можуть бути перевідтворені з початку після restart; це може повторно витратити API-токени. Це не distributed-queue production гарантія.
- Не рекомендуємо застосовувати до публічного платіжного магазину без staging, approvals і browser QA.

## Рекомендований захист від сторонніх реєстрацій

API `/v2/sites/connect` без захисту від анонімного підключення може дозволити стороннім користувачам витрачати ваші LLM-кредити. Для тестового публічного Render **налаштуйте окремий pairing secret**:

1. Render Environment → `BACKEND_PAIRING_SECRET` (згенеруйте новий довгий випадковий секрет, відмінний від `BACKEND_TOKEN_SECRET`).
2. У `wp-config.php` WordPress додайте `define('THESIS_AI_BACKEND_PAIRING_SECRET', 'такий_самий_рядок');` до рядка `/* That's all, stop editing! */`. Не публікуйте значення у Git.
3. Після цього нові підключення/автоматичне перепідключення вимагатимуть цей секрет. Існуюче валідне підключення продовжить працювати.
4. `/health` показує `pairing_protection_enabled: true`.

Це початковий адміністративний захист, а не повноцінна довірена реєстрація сайтів. Рекомендовані також IP/site quotas, секрет-сканування, ротація токенів і production authentication (наступні релізи).
