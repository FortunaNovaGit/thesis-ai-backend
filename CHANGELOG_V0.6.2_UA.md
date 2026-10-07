# v0.6.2 — стабільний JSON transport для 5 агентів

## Виправлено

- Повністю прибрано залежність real-agent workflow від `AgentOutputSchema` / strict structured-output conversion OpenAI Agents SDK.
- Усі 5 агентів тепер повертають звичайний JSON-текст; backend сам витягує JSON і валідовує його через Pydantic.
- Якщо агент один раз повернув невалідний JSON, дозволено рівно один bounded formatter retry. Нескінченного retry loop немає.
- `/health` тепер показує `agent_output_mode: json_text_pydantic`, щоб у Render одразу було видно, що запущена правильна збірка.
- Backend version: `0.6.2`.
- Залежність OpenAI Agents SDK зафіксована в діапазоні `>=0.22.0,<0.23.0`, щоб Render rebuild не підтягнув несумісний major/minor безконтрольно.

## Чому

На реальному Render deployment помилка strict JSON schema продовжувала виникати до першої WordPress action. Нова схема переносить контракт структурованого результату з SDK-рівня у наш власний validation layer: модель генерує JSON, а Pydantic залишається авторитетним валідатором.

WordPress Bridge оновлювати не потрібно. v0.6.3 сумісний з backend v0.6.2.
