# v0.6.1 — Agents SDK structured-output compatibility

## Виправлено

- Виправлено падіння real OpenAI-agent workflow з помилкою `Strict JSON schema is enabled, but the output type is not valid`.
- Для всіх 5 агентів Pydantic outputs тепер явно обгортаються в `AgentOutputSchema(..., strict_json_schema=False)`.
- Pydantic validation результатів збережена: агенти й надалі повертають `TaskPlan`, `ApplicationSpec`, `ExperienceSpec`, `BuildPlan` та `QualityReport`, але SDK більше не намагається перетворити наші складні моделі з default/default_factory у strict OpenAI JSON Schema.
- WordPress plugin оновлювати не потрібно; це backend-only fix.

## Причина

OpenAI Agents SDK за замовчуванням використовує strict JSON schema для `output_type`. Частина наших Pydantic моделей містить optional/default поля, які не проходять strict schema conversion SDK. Через це planning job завершувався ще до створення WordPress actions.
