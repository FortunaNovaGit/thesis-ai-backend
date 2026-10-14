# v0.7.0 — Multi-Agent Core

Ця версія перебудовує систему навколо структурованих артефактів між агентами замість передачі великого спільного контексту.

## Головні зміни

- **Orchestrator → `ProjectBrief`**: цілі, аудиторії, відомі/відсутні факти, вимоги та constraints.
- **Architect → `ArchitectureBundle`**: унікальні сторінки, логіка кожної сторінки, CTA, content matrix і semantic capabilities.
- **Deterministic Capability Resolver**: LLM більше не вибирає plugin slug. `forms → contact-form-7`, `ecommerce → woocommerce`, `structured_content → advanced-custom-fields`, `page_builder_elementor → elementor`. Існуючі capabilities перевикористовуються.
- **Design/Content/SEO → один `ExperienceSpec`**: єдиний DesignSystem, зв'язні PageSpecs, distinct H1/SEO, internal-link logic і фактичний контент без вигаданих бізнес-фактів.
- **Deterministic Elementor Component Library**: AI вибирає semantic section/component, Python компілює безпечний Elementor JSON. Додані hero/cards/benefits/trust/team/process/FAQ/booking/CTA layouts.
- **Builder agent** працює на дешевшій моделі і лише перевіряє implementation manifest. Обов'язкові сторінки, SEO, меню, homepage та dependencies компілюються кодом.
- **Quality Agent** отримує compact evidence замість повної історії виконання. Перед LLM виконуються безкоштовні deterministic checks.
- **Delta repair**: спочатку повторюються лише конкретні failed/missing idempotent actions. Sol використовується лише як escalation, якщо deterministic repair не знає безпечного виправлення.
- **Model routing**: Terra — Orchestrator/Architect/Design; Luna — Builder/QA; Sol — тільки repair escalation.
- **Runtime build budget guardrails**: `MAX_BUILD_COST_USD`, `MAX_TOTAL_LLM_TOKENS`, `MAX_LLM_CALLS`.
- **API cost estimate** зберігається разом з token/call breakdown по агентах.
- Default `MAX_REPAIR_LOOPS=1`.
- WordPress Pull execution з v0.6 збережено: Render не бомбардує EasyWP REST-запитами.

## Ціль v0.7

Для стандартного business-site прагнемо приблизно до 5–6 основних LLM calls, 15k–30k total tokens і значно нижчої вартості, ніж у v0.6. Це цільова межа, а не гарантія: реальна ціна залежить від prompt та generated output.

## Render env

```text
AGENT_MODE=auto
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
BACKEND_TOKEN_SECRET=<stable generated secret>
```
