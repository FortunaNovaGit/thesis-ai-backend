# Render deployment — v0.6.0

Backend більше не підключається до WordPress напряму. Render використовується для LLM-агентів, orchestration, Policy Engine і QA/repair.

Рекомендовані Environment Variables:

```text
AGENT_MODE=auto
OPENAI_MODEL=gpt-5.6-sol
OPENAI_API_KEY=<secret>
BACKEND_TOKEN_SECRET=<stable secret — НЕ змінювати між deploy>
AUTO_APPROVE_MEDIUM_RISK=true
MAX_REPAIR_LOOPS=2
ALLOW_INSECURE_WORDPRESS=false
ALLOW_PRIVATE_WORDPRESS=false
```

Після deploy:

```text
GET /health
```

повинен повернути `version=0.6.0` та `execution_mode=wordpress_pull`.

## Чому більше немає EasyWP 429

У v0.6 backend не робить build-time HTTP requests до EasyWP. WordPress сам виконує abilities локально з wp-admin AJAX. До Render йдуть лише outbound requests: planning/status/verification.
