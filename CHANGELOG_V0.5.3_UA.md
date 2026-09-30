# v0.5.3 — захист від EasyWP 429 / rate limiting

## Що виправлено

1. Додано `get-site-snapshot` — один composite Bridge request замість шести REST-запитів підряд під час preflight/verification.
2. Додано глобальний pacing для запитів до WordPress (за замовчуванням мінімум 1 секунда між запитами).
3. Додано adaptive retry для HTTP 429:
   - використовується `Retry-After`, якщо хостинг його повертає;
   - інакше exponential backoff + jitter;
   - 429 більше не запускає миттєвий запит на fallback URL, який раніше міг ще сильніше посилювати блок.
4. Додано Render env vars для керування pacing/backoff без зміни коду.
5. Preflight, verification і кожен repair-loop тепер потребують лише одного snapshot request замість шести.

## Рекомендовані Render variables

```text
WORDPRESS_MIN_REQUEST_INTERVAL_SECONDS=1.0
WORDPRESS_RATE_LIMIT_RETRIES=5
WORDPRESS_RATE_LIMIT_BASE_DELAY_SECONDS=3.0
WORDPRESS_RATE_LIMIT_MAX_DELAY_SECONDS=45.0
```

Якщо EasyWP все одно часто повертає 429, першим кроком підніміть `WORDPRESS_MIN_REQUEST_INTERVAL_SECONDS` до `1.5` або `2.0`.
