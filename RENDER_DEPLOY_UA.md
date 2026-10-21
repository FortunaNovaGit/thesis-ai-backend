# Render deploy — v0.7.2

Обов'язково збережіть незмінним:

```text
BACKEND_TOKEN_SECRET=<existing stable secret>
```

Рекомендований тестовий конфіг:

```text
AGENT_MODE=auto
OPENAI_API_KEY=<secret>
AUTO_APPROVE_MEDIUM_RISK=true
MAX_BUILD_COST_USD=0.30
MAX_TOTAL_LLM_TOKENS=20000
MAX_LLM_CALLS=8
MAX_REPAIR_LOOPS=1
ENABLE_BUILDER_LLM_REVIEW=false
```

Після deploy перевірте `/health`. Очікується `version=0.7.2`, `execution_mode=wordpress_pull`, `architecture_version=artifact_pipeline_v2`.
