# Render deploy v0.7

Backend залишається Docker Web Service.

Обов’язково збережіть існуючий `BACKEND_TOKEN_SECRET` незмінним. Нове значення інвалідовує старі site tokens.

Рекомендовані env:

```text
AGENT_MODE=auto
OPENAI_API_KEY=<secret>
OPENAI_ORCHESTRATOR_MODEL=gpt-5.6-terra
OPENAI_ARCHITECT_MODEL=gpt-5.6-terra
OPENAI_DESIGN_MODEL=gpt-5.6-terra
OPENAI_BUILDER_MODEL=gpt-5.6-luna
OPENAI_QUALITY_MODEL=gpt-5.6-luna
OPENAI_REPAIR_MODEL=gpt-5.6-sol
MAX_BUILD_COST_USD=0.50
MAX_TOTAL_LLM_TOKENS=30000
MAX_LLM_CALLS=10
MAX_REPAIR_LOOPS=1
AUTO_APPROVE_MEDIUM_RISK=true
```

Перевірка:

```text
GET /health
```

має показати `0.7.0`, `wordpress_pull`, `artifact_pipeline_v1` і model router.
