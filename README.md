# WordPress Multi-Agent Thesis MVP — v0.7.2

Artifact-driven multi-agent WordPress/Elementor site builder.

## Pipeline

1. **Orchestrator** → compact `ProjectBrief`
2. **Architect & Capability** → site architecture, content matrix and capability requirements
3. **Design / Content / SEO** → site-wide `DesignSystem` + page-specific `ExperienceSpec`
4. **WordPress Implementation** → deterministic compiler turns validated artifacts into approved WordPress abilities / Elementor components
5. **Quality & Security** → deterministic checks + compact semantic QA; bounded delta repair

WordPress executes mutations locally. The Render backend never needs to burst requests into EasyWP during a build.

## v0.7.2 focus

- richer visitor-facing copy and Elementor components;
- no planning notes rendered as website copy;
- actual Elementor headings/buttons/forms/SEO returned to QA;
- draft-first is treated as expected, not a QA failure;
- Builder LLM review disabled by default to reduce time/tokens;
- background WordPress worker keeps build moving when the admin tab is refreshed/closed, with a stale-worker browser fallback;
- global DesignSystem can style the theme header/navigation as well as Elementor content.

## Recommended Render environment

```text
AGENT_MODE=auto
OPENAI_API_KEY=...
BACKEND_TOKEN_SECRET=<stable generated secret>
AUTO_APPROVE_MEDIUM_RISK=true
MAX_BUILD_COST_USD=0.30
MAX_TOTAL_LLM_TOKENS=20000
MAX_LLM_CALLS=8
MAX_REPAIR_LOOPS=1
ENABLE_BUILDER_LLM_REVIEW=false
```

Model router defaults remain role-specific. Keep `BACKEND_TOKEN_SECRET` unchanged across redeploys.

See `CHANGELOG_V0.7.2_UA.md`.
