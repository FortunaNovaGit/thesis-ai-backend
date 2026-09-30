# Quick Start — v0.5.4

1. Оновіть backend на Render до v0.5.4 та дочекайтесь deploy.
2. Перевірте `/health` — `version` має бути `0.5.4`.
3. Оновіть WordPress plugin через Upload Plugin → Replace current with uploaded.
4. Не запускайте build одразу після серії 429. EasyWP описує 429 block як тимчасовий, що знімається протягом кількох хвилин. Практично зачекайте ~5 хвилин, щоб не продовжувати старе firewall window.
5. Запустіть той самий build.

## Рекомендовані Render variables

```text
WORDPRESS_MIN_REQUEST_INTERVAL_SECONDS=2.0
WORDPRESS_RATE_LIMIT_RETRIES=2
WORDPRESS_RATE_LIMIT_BASE_DELAY_SECONDS=180.0
WORDPRESS_RATE_LIMIT_MAX_DELAY_SECONDS=300.0
WORDPRESS_BATCH_SIZE=8
WORDPRESS_INTER_BATCH_DELAY_SECONDS=3.0
```

v0.5.4 виконує WordPress actions локальними batch-ами через один Bridge request. Post-build snapshot повертається в тому самому batch response, тому окремий verification request не надсилається.
