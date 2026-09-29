# v0.5.1 — асинхронний build без 504

## Чому виникав 504

У v0.5.0 WordPress admin request виконував один синхронний `wp_remote_post()` до backend і чекав завершення всього multi-agent workflow до 300 секунд. Під час цього backend багато разів звертався назад до того ж WordPress через Bridge API. На managed hosting reverse proxy може завершити браузерний/PHP request раніше, навіть якщо CPU/RAM не досягли ліміту.

## Що змінено

- Build тепер запускається як background job на backend.
- WordPress отримує `202 Accepted + job_id` приблизно одразу.
- Плагін більше не тримає довгий PHP request.
- WordPress admin poll-ить короткий status endpoint через AJAX.
- Додано stage/progress: planning, preflight, architecture, design, build, verification, quality, repair.
- Повторне натискання не запускає другий паралельний build для того самого сайту.
- Після завершення результат зберігається як попередній `last_build`.
- Якщо Render перезапустився посеред тестового build, UI повідомляє, що job втрачено, замість нескінченного очікування.

## Обмеження тестової реалізації

Job registry v0.5.1 зберігається у пам'яті одного Render process. Це достатньо для development/test, але не є production-durable queue. Наступний production-like крок — PostgreSQL job state + worker/queue.
