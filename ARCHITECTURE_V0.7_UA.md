# Архітектура v0.7

```text
User prompt
   ↓
Orchestrator (Terra)
   ↓ ProjectBrief
Architect & Capability (Terra)
   ↓ ArchitectureBundle + ContentMatrix
Deterministic Capability Resolver
   ↓ approved dependency plan
Design / Content / SEO (Terra)
   ↓ ExperienceSpec + DesignSystem + PageSpecs
Builder (Luna)
   ↓ compact advisory BuildPlan
Deterministic Compiler + Component Library
   ↓ exact controlled WordPress actions
Policy Engine
   ↓ approved actions
WordPress Plugin executes locally
   ↓ actual SiteSnapshot
Deterministic QA ($0)
   + Quality Agent (Luna)
   ↓ bounded issues
Delta Repair
   ├ deterministic safe repair
   └ Sol escalation only when necessary
```

## Чому це справжня multi-agent pipeline

Кожен агент має окрему відповідальність та передає наступному не conversation history, а окремий typed artifact. Це робить систему вимірюваною, дешевшою та придатною для експериментального порівняння з single-agent baseline.

## Основні артефакти

- `ProjectBrief` — normalized business request.
- `ArchitectureBundle` — IA, page goals, CTAs, semantic capabilities, content matrix.
- `CapabilityResolution[]` — core/reuse/activate/install decision without LLM plugin slugs.
- `ExperienceSpec` — shared design system and logical content for every page.
- `BuildPlan` — controlled WordPress actions.
- `QualityReport` — deterministic + semantic QA evidence.
