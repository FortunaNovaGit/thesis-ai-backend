# Render — оновлення до v0.5.4

1. Замініть backend files у GitHub repo на v0.5.4.
2. Commit + Push у `main`.
3. Render автоматично redeploy.
4. Перевірте `/health` → `version: 0.5.4`.
5. Environment variables рекомендовано:

```text
WORDPRESS_MIN_REQUEST_INTERVAL_SECONDS=2.0
WORDPRESS_RATE_LIMIT_RETRIES=2
WORDPRESS_RATE_LIMIT_BASE_DELAY_SECONDS=180.0
WORDPRESS_RATE_LIMIT_MAX_DELAY_SECONDS=300.0
WORDPRESS_BATCH_SIZE=8
WORDPRESS_INTER_BATCH_DELAY_SECONDS=3.0
```

`BACKEND_TOKEN_SECRET` не змінюйте, інакше WordPress connection token стане недійсним.
