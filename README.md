# WordPress Multi-Agent Thesis MVP — v0.6.0

Multi-agent WordPress website builder with WordPress-driven pull execution.

## Architecture

```text
WordPress Plugin
   │ outbound HTTPS
   ▼
Render Backend
   ├─ Orchestrator
   ├─ Architect & Capability
   ├─ Design / Content / SEO
   ├─ WordPress Implementation Planner
   ├─ Quality & Security
   └─ Policy Engine
   │
   ▼
Approved Build Plan
   │
   ▼
WordPress executes abilities LOCALLY
   ├─ plugins/themes
   ├─ Elementor pages
   ├─ CF7 form
   ├─ SEO
   ├─ menu/homepage/site identity
   ├─ WooCommerce basic setup
   └─ ACF structured-content scaffold
   │
   ▼
Fresh WordPress snapshot → Render QA/repair
```

The backend does not call WordPress during builds. This is intentional for managed hosts with aggressive external request rate limiting.

See `QUICK_START_UA.md` and `CHANGELOG_V0.6.0_UA.md`.
