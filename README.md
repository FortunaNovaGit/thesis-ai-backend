# WordPress Multi-Agent Thesis MVP — v0.7.0

Artifact-driven multi-agent WordPress/Elementor site builder.

The backend plans and verifies. The WordPress plugin executes mutations locally, so EasyWP does not receive a burst of inbound Render → WordPress requests.

## Five agents

1. **Orchestrator** → ProjectBrief
2. **Architect & Capability** → site architecture + content matrix
3. **Design / Content / SEO** → coherent site-wide ExperienceSpec
4. **WordPress Implementation** → small advisory plan; exact renderer payloads are deterministic
5. **Quality & Security** → semantic QA on compact evidence

Deterministic layers handle capability→plugin mapping, policy, Elementor components, structural QA and most repair actions.

## Cost control

Default router:

- Orchestrator: `gpt-5.6-terra`
- Architect: `gpt-5.6-terra`
- Design: `gpt-5.6-terra`
- Builder: `gpt-5.6-luna`
- Quality: `gpt-5.6-luna`
- Repair escalation: `gpt-5.6-sol`

Default runtime guardrails (they stop subsequent LLM calls once the measured estimate reaches the limit):

```text
MAX_BUILD_COST_USD=0.50
MAX_TOTAL_LLM_TOKENS=30000
MAX_LLM_CALLS=10
MAX_REPAIR_LOOPS=1
```

`estimated_cost_usd` is an estimate based on configured model/token usage; the OpenAI billing dashboard remains authoritative.

See `ARCHITECTURE_V0.7_UA.md` and `CHANGELOG_V0.7.0_UA.md`.
