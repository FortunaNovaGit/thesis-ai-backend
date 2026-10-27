# v0.8.1 — Reliability Core

## Що реалізовано

- **SQLAlchemy JobRepository**: `planning_jobs`, `verification_reports`, `revoked_sites`. SQLite для локальної розробки, PostgreSQL через `DATABASE_URL` для Render. Зберігаються статус, прогрес, план, помилка, час і статистика LLM. Зберігання завершених запусків за замовчуванням 14 діб.
- **Resume on poll**: якщо Render перезапустився під час planning, запит статусу може повторно запустити planning зі збереженого input із тим самим `job_id`. Це *не* відновлення посеред окремого LLM-виклику; на повторну генерацію можуть бути витрачені токени. Для цього MVP передбачено **один** backend process/instance. Multi-worker lease/queue ще не реалізовано.
- **WordPress action journal**: ключ SHA-256(`plan_id|ability|parameters`), запис успішного результату до зміщення курсора, lock на 600 секунд. Повтор завершеної дії повертає результат із журналу. Вплив crash між WordPress mutation і записом журналу ще не може бути виключений повністю.
- **Дворівнева перевірка команд**: строгі Pydantic-моделі в backend (`extra=forbid`) + незалежні PHP-перевірки в Bridge. Ліміт payload і перевірка page/menu slugs, plugins/theme.
- **Контракт Bridge**: потрібні `action_journal_version: 1` і `action_schema_version: 1`; старий Bridge не проходить preflight до платних викликів LLM.
- **Токени**: нові pull tokens не містять WordPress Application Password; `/disconnect` відкликає site_id у БД. Існуючі encrypted legacy tokens читаються для сумісності до перепідключення.
- **Ліміти**: 413 при надмірному `site_snapshot`/`verify` payload; налаштований retention для завершених jobs.
- **Тести / CI**: pytest, PHP syntax і standalone journal test. Додано CI для backend; плагін має тестовий script у source package.

## Що свідомо не готове

- Розподілена queue, atomic distributed lease, надійне відновлення на кількох Render replicas.
- Наскрізний HMAC-підпис build plan, TTL/rotation токенів, інтерактивне підтвердження всіх medium/high-risk змін.
- Повноцінний rollback усіх змін і cleanup WordPress action journal.
- Browser/Playwright/Lighthouse/axe QA, створення товарів WooCommerce, медіагенерація — наступні релізи.
- Тестування на реальному EasyWP/Render (зробити окремо; тести локальні).

## Увага до зберігання

`DATABASE_URL` **потрібен для фактичної persistence на Render**. Якщо його не задано, SQLite у filesystem без persistent disk втрачається після redeploy. На `/health`: `durable_jobs: true` лише для PostgreSQL.

`BACKEND_TOKEN_SECRET` має залишатися незмінним після оновлення.

- **Опційний pairing secret**: параметр `BACKEND_PAIRING_SECRET` захищає endpoint підключення; у WordPress відповідний `THESIS_AI_BACKEND_PAIRING_SECRET` у `wp-config.php`. Для публічних серверів настійно рекомендується увімкнути.
