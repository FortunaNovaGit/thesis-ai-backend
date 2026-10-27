from __future__ import annotations

import json
import uuid
from typing import Any

from .agents.runtime import (
    AgentRuntime,
    architecture_to_application_spec,
    compact_site_summary,
    compile_build_plan,
    make_task_plan,
    merge_advisory_actions,
    normalize_architecture,
    reconcile_experience,
)
from .capabilities import resolve_capabilities
from .config import Settings
from .models import (
    AgentRole,
    ApplicationSpec,
    ArchitectureBundle,
    BuildAction,
    BuildPlan,
    ExperienceSpec,
    PolicyOutcome,
    ProjectBrief,
    QualityIssue,
    QualityReport,
    Renderer,
    SiteSnapshot,
)
from .policy import PolicyEngine


class PullPlanningWorkflow:
    """v0.7 artifact-driven multi-agent planning for WordPress Pull execution."""

    def __init__(self, settings: Settings, agents: AgentRuntime) -> None:
        self.settings = settings
        self.agents = agents
        self.policy = PolicyEngine()

    def _gate_actions(self, actions: list[BuildAction], actor: AgentRole = AgentRole.BUILDER) -> dict[str, Any]:
        allowed: list[dict[str, Any]] = []
        pending: list[dict[str, Any]] = []
        blocked: list[dict[str, Any]] = []
        for action in actions:
            decision = self.policy.evaluate(actor=actor, action=action, auto_approve_medium=self.settings.auto_approve_medium_risk)
            item = {"action": action.model_dump(mode="json"), "policy": decision.model_dump(mode="json")}
            if decision.outcome == PolicyOutcome.ALLOW:
                allowed.append(item)
            elif decision.outcome == PolicyOutcome.REQUIRE_APPROVAL:
                pending.append(item)
            else:
                blocked.append(item)
        return {"allowed": allowed, "pending": pending, "blocked": blocked}

    @staticmethod
    def _validate_bridge_contract(snapshot: SiteSnapshot, renderer: Renderer) -> None:
        """Check the WordPress executor before spending any model tokens.

        Fixture snapshots without a version remain allowed for offline unit tests;
        connected sites must use a Bridge with a discoverable ABI manifest.
        """
        if not snapshot.site_info.get("bridge_version") and not snapshot.bridge_contract:
            return
        contract = snapshot.bridge_contract
        if not contract or not isinstance(contract.get("abilities"), list):
            raise RuntimeError("Bridge compatibility preflight failed: upgrade WordPress Bridge to v0.8.0 before launching a paid build.")
        offered = set(str(x) for x in contract["abilities"])
        required = {"get-site-snapshot", "set-page-seo", "apply-site-design", "ensure-navigation-menu", "set-homepage-by-slug", "update-site-identity"}
        required.add("elementor-ensure-draft-page" if renderer in {"elementor", "auto"} else "ensure-draft-page")
        missing = sorted(required - offered)
        if missing:
            raise RuntimeError("Bridge compatibility preflight failed. Missing abilities: " + ", ".join(missing))
        if int(contract.get("action_journal_version", 0) or 0) < 1 or int(contract.get("action_schema_version", 0) or 0) < 1:
            raise RuntimeError("Bridge v0.8.1 is required: action journal and strict parameter contract are missing. Upgrade the WordPress plugin before a paid build.")

    async def plan(self, user_request: str, renderer: Renderer, site_snapshot: SiteSnapshot, progress=None) -> dict[str, Any]:
        async def report(stage: str, pct: int, detail: str) -> None:
            if progress is not None:
                value = progress(stage, pct, detail)
                if hasattr(value, "__await__"):
                    await value

        self._validate_bridge_contract(site_snapshot, renderer)
        await report("orchestrator", 8, "Orchestrator is normalizing the request into a compact ProjectBrief")
        brief: ProjectBrief = await self.agents.orchestrate(user_request, renderer)
        # The renderer selected by the user is authoritative.
        brief = brief.model_copy(update={"renderer": renderer})
        task_plan = make_task_plan(brief)

        await report("architecture", 24, "Architect is designing information architecture and semantic capabilities")
        architecture: ArchitectureBundle = await self.agents.architect(brief, compact_site_summary(site_snapshot))
        architecture = normalize_architecture(brief, architecture)
        capability_resolutions = resolve_capabilities(architecture, site_snapshot, renderer)
        app_spec = architecture_to_application_spec(brief, architecture, capability_resolutions)

        unavailable_required = {
            r.capability for r in capability_resolutions
            if r.source == "unavailable" and any(c.capability == r.capability and c.priority == "required" for c in architecture.capabilities)
        }
        if unavailable_required:
            raise RuntimeError("No approved implementation exists for required capabilities: " + ", ".join(sorted(unavailable_required)))

        # A missing, required plugin is a deployment dependency, not a creative
        # problem. Detect it before paying for design/content generation.
        required_capabilities = {r.capability for r in architecture.capabilities if r.priority == "required"}
        if renderer in {"elementor", "auto"}:
            required_capabilities.add("page_builder_elementor")
        install_needed = [r.plugin_slug for r in capability_resolutions if r.action == "install" and r.plugin_slug and r.capability in required_capabilities]
        if install_needed and site_snapshot.bridge_contract:
            contract = site_snapshot.bridge_contract
            if not contract.get("plugin_management_enabled", False):
                raise RuntimeError("Required plugins need installation, but WordPress plugin management is disabled: " + ", ".join(install_needed))
            method = str(contract.get("filesystem_method", "unknown"))
            if method != "direct":
                raise RuntimeError("WordPress filesystem method '" + method + "' prevents unattended plugin installation. Install these approved plugins manually, then retry: " + ", ".join(install_needed))

        await report("design", 46, "Design/Content/SEO agent is creating one coherent site-wide experience")
        experience: ExperienceSpec = await self.agents.design(brief, architecture)
        experience = reconcile_experience(brief, architecture, experience)

        await report("implementation_plan", 64, "Builder agent is reviewing the deterministic implementation manifest")
        baseline = compile_build_plan(app_spec, experience, site_snapshot, renderer)
        manifest = {
            "project": {"site_type": brief.site_type, "renderer": renderer},
            "capability_resolutions": [x.model_dump(mode="json") for x in capability_resolutions],
            "pages": [{"slug": p.slug, "purpose": p.purpose} for p in architecture.pages],
            "deterministic_actions": [a.ability for a in baseline.actions],
            "instruction": "Do not duplicate deterministic actions. Return only genuinely missing advisory setup actions.",
        }
        if self.settings.enable_builder_llm_review:
            advisory: BuildPlan = await self.agents.build(manifest)
        else:
            # The WordPress Implementation Agent is deterministic by default: it
            # compiles typed artifacts into allow-listed abilities without spending
            # another LLM call on a manifest that is already complete.
            advisory = BuildPlan(actions=[])
        build_plan = merge_advisory_actions(baseline, advisory)
        if site_snapshot.bridge_contract:
            offered = set(str(x) for x in site_snapshot.bridge_contract.get("abilities", []))
            missing_abilities = sorted({action.ability.removeprefix("thesis-ai-bridge/") for action in build_plan.actions} - offered)
            if missing_abilities:
                raise RuntimeError("This WordPress Bridge cannot execute the planned actions: " + ", ".join(missing_abilities))
        gated = self._gate_actions(build_plan.actions)

        await report("ready", 100, "Artifact-driven plan is ready for local WordPress execution")
        return {
            "plan_id": str(uuid.uuid4()),
            "user_request": user_request,
            "renderer": renderer,
            "project_brief": brief.model_dump(mode="json"),
            "task_plan": task_plan.model_dump(mode="json"),
            "site_snapshot": site_snapshot.model_dump(mode="json"),
            "architecture": architecture.model_dump(mode="json"),
            "content_matrix": [x.model_dump(mode="json") for x in architecture.content_matrix],
            "capability_resolutions": [x.model_dump(mode="json") for x in capability_resolutions],
            "application_spec": app_spec.model_dump(mode="json"),
            "experience_spec": experience.model_dump(mode="json"),
            "build_plan": build_plan.model_dump(mode="json"),
            "approved_actions": gated["allowed"],
            "pending_actions": gated["pending"],
            "blocked_actions": gated["blocked"],
            "agent_mode": self.settings.resolved_agent_mode,
            "model": self.settings.openai_design_model if self.settings.resolved_agent_mode == "openai" else "mock",
            "model_router": self.settings.model_router if self.settings.resolved_agent_mode == "openai" else {"all": "mock"},
            "usage": self.agents.usage.model_dump(mode="json"),
            "budget": self.agents.budget_state(),
            "architecture_version": "artifact_pipeline_v3_visual",
        }

    @staticmethod
    def _latest_executions(executions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        for item in executions:
            action = item.get("action") or {}
            key = str(action.get("ability", "")) + "|" + json.dumps(action.get("parameters", {}), sort_keys=True, ensure_ascii=False)
            latest[key] = item
        return list(latest.values())

    @classmethod
    def _deterministic_issues(
        cls,
        app_spec: ApplicationSpec,
        architecture: ArchitectureBundle,
        experience: ExperienceSpec,
        executions: list[dict[str, Any]],
        snapshot: SiteSnapshot,
    ) -> list[QualityIssue]:
        issues: list[QualityIssue] = []
        latest = cls._latest_executions(executions)
        failures = [
            item for item in latest
            if not bool(item.get("executed")) and str((item.get("policy") or {}).get("outcome", "")) != "require_approval"
        ]
        if failures:
            issues.append(QualityIssue(
                id="DET-actions", category="functional", severity="high",
                description=f"{len(failures)} latest WordPress actions failed or were blocked.",
                responsible_agent=AgentRole.BUILDER,
                suggested_fix="Retry only failed safe/idempotent actions; do not rebuild successful work.",
            ))

        required_slugs = {p.slug for p in app_spec.pages}
        actual_slugs = {str(p.get("slug", "")) for p in snapshot.pages}
        missing = sorted(required_slugs - actual_slugs)
        if missing:
            issues.append(QualityIssue(
                id="DET-pages", category="functional", severity="high",
                description="Missing required pages: " + ", ".join(missing),
                responsible_agent=AgentRole.BUILDER,
                suggested_fix="Create only the missing AI-owned draft pages and their SEO metadata.",
            ))

        # Detect duplicated logical pages by title; this caught the duplicated Home
        # behavior observed in the previous prototype even when slugs differed.
        titles: dict[str, int] = {}
        for page in snapshot.pages:
            title = str(page.get("title", "")).strip().casefold()
            if title:
                titles[title] = titles.get(title, 0) + 1
        duplicates = [title for title, count in titles.items() if count > 1]
        if duplicates:
            issues.append(QualityIssue(
                id="DET-duplicate-pages", category="functional", severity="medium",
                description="Duplicate page titles detected: " + ", ".join(duplicates[:8]),
                responsible_agent=AgentRole.ARCHITECT,
                suggested_fix="Keep one canonical page per architectural slug; do not create another duplicate.",
            ))

        required_plugins = {item.plugin_slug for item in app_spec.plugin_plan}
        active_plugins = {str(p.get("slug", "")) for p in snapshot.plugins if p.get("active")}
        if snapshot.bridge_contract and "ecommerce" in {c.capability for c in architecture.capabilities} and snapshot.commerce.get("published_products", 0) == 0:
            issues.append(QualityIssue(
                id="DET-empty-catalog", category="functional", severity="medium",
                description="WooCommerce catalog has no published products. Product descriptions on an Elementor page are not actual WooCommerce products.",
                responsible_agent=AgentRole.BUILDER,
                suggested_fix="Create and verify WooCommerce product drafts with real product data; do not invent prices or stock.",
            ))
        missing_plugins = sorted(required_plugins - active_plugins)
        if missing_plugins:
            issues.append(QualityIssue(
                id="DET-plugins", category="functional", severity="high",
                description="Required approved plugins are not active: " + ", ".join(missing_plugins),
                responsible_agent=AgentRole.BUILDER,
                suggested_fix="Install/activate only the approved dependency that is still missing.",
            ))

        if any(p.slug == "home" for p in app_spec.pages):
            homepage_slug = str(snapshot.structure.get("homepage_slug", ""))
            if homepage_slug not in {"home", ""}:
                issues.append(QualityIssue(
                    id="DET-home", category="functional", severity="medium",
                    description="The generated Home page is not configured as the static homepage.",
                    responsible_agent=AgentRole.BUILDER,
                    suggested_fix="Run set-homepage-by-slug for home.",
                ))

        # Content coherence checks are deterministic and cost $0.
        h1s = [p.seo.h1.strip().casefold() for p in experience.pages if p.seo.h1.strip()]
        if len(h1s) != len(set(h1s)):
            issues.append(QualityIssue(
                id="DET-duplicate-h1", category="content", severity="medium",
                description="Two or more generated pages use the same H1.",
                responsible_agent=AgentRole.DESIGN,
                suggested_fix="Give each page a distinct H1 aligned with its page goal.",
            ))
        page_slugs = {p.slug for p in architecture.pages}
        for row in architecture.content_matrix:
            invalid_links = [x for x in row.internal_links if x not in page_slugs]
            if invalid_links:
                issues.append(QualityIssue(
                    id=f"DET-links-{row.page_slug}", category="content", severity="medium",
                    description=f"Content matrix for {row.page_slug} references unknown pages: {', '.join(invalid_links)}",
                    responsible_agent=AgentRole.ARCHITECT,
                    suggested_fix="Use only canonical architecture slugs for internal linking.",
                ))

        # Zero-cost content-quality checks before semantic QA. These validate the
        # artifact we actually compiled instead of asking the QA model to infer
        # quality from page titles alone.
        internal_markers = (
            "ця сторінка", "сторінка має", "додайте", "після генерації",
            "контент секції", "мета сторінки", "надати канал",
            "допомогти зрозуміти", "сформувати довіру", "зменшити friction",
        )
        for page in experience.pages:
            headings = [s.heading.strip().casefold() for s in page.section_specs if s.heading.strip()]
            if len(headings) != len(set(headings)):
                issues.append(QualityIssue(
                    id=f"DET-section-headings-{page.page_slug}", category="content", severity="high",
                    description=f"Page {page.page_slug} contains repeated section headings.",
                    responsible_agent=AgentRole.DESIGN,
                    suggested_fix="Regenerate only the duplicated section headings and keep the rest of the page.",
                ))
            bad_copy = []
            for section in page.section_specs:
                combined = f"{section.heading} {section.body}".casefold()
                if any(marker in combined for marker in internal_markers):
                    bad_copy.append(section.section_type)
            if bad_copy:
                issues.append(QualityIssue(
                    id=f"DET-planning-copy-{page.page_slug}", category="content", severity="high",
                    description=f"Page {page.page_slug} exposes planning/editor language in sections: {', '.join(sorted(set(bad_copy)))}.",
                    responsible_agent=AgentRole.DESIGN,
                    suggested_fix="Replace planning language with visitor-facing copy for only those sections.",
                ))
            arch_page = next((p for p in architecture.pages if p.slug == page.page_slug), None)
            if arch_page and arch_page.primary_cta and not any(s.cta_label for s in page.section_specs):
                issues.append(QualityIssue(
                    id=f"DET-cta-{page.page_slug}", category="content", severity="high",
                    description=f"Page {page.page_slug} has no CTA although the architecture requires one.",
                    responsible_agent=AgentRole.DESIGN,
                    suggested_fix="Add the architecture CTA to the hero or final CTA section.",
                ))
            if len(page.section_specs) < 3:
                issues.append(QualityIssue(
                    id=f"DET-sections-{page.page_slug}", category="content", severity="medium",
                    description=f"Page {page.page_slug} has fewer than three meaningful sections.",
                    responsible_agent=AgentRole.DESIGN,
                    suggested_fix="Add only the missing architecture sections; do not rebuild the entire site.",
                ))


        # Verify the actual Elementor result using compact signals collected by
        # the Bridge. This costs no model tokens and avoids QA guessing from page
        # titles/status alone.
        actual_by_slug = {str(p.get("slug", "")): p for p in snapshot.pages}
        for page in experience.pages:
            actual = actual_by_slug.get(page.page_slug) or {}
            elementor = actual.get("elementor", {}) if isinstance(actual.get("elementor", {}), dict) else {}
            if actual and page.page_slug in required_slugs:
                element_count = int(elementor.get("element_count", 0) or 0)
                if elementor and element_count < 6:
                    issues.append(QualityIssue(
                        id=f"DET-render-sparse-{page.page_slug}", category="functional", severity="high",
                        description=f"Rendered Elementor page {page.page_slug} is unexpectedly sparse ({element_count} elements).",
                        responsible_agent=AgentRole.BUILDER,
                        suggested_fix="Re-render only this page from the existing ExperienceSpec.",
                    ))
                actual_headings = [str(x).strip().casefold() for x in elementor.get("headings", []) if str(x).strip()]
                if len(actual_headings) != len(set(actual_headings)):
                    issues.append(QualityIssue(
                        id=f"DET-render-headings-{page.page_slug}", category="content", severity="high",
                        description=f"Rendered page {page.page_slug} contains repeated headings.",
                        responsible_agent=AgentRole.DESIGN,
                        suggested_fix="Use the reconciled unique section headings and re-render this page only.",
                    ))
                arch_page = next((p for p in architecture.pages if p.slug == page.page_slug), None)
                if arch_page and arch_page.primary_cta and elementor and not elementor.get("buttons"):
                    issues.append(QualityIssue(
                        id=f"DET-render-cta-{page.page_slug}", category="content", severity="high",
                        description=f"Rendered page {page.page_slug} is missing its required CTA button.",
                        responsible_agent=AgentRole.BUILDER,
                        suggested_fix="Re-render this page with the CTA already present in the ExperienceSpec.",
                    ))
                needs_form = any(s.section_type == "booking" for s in page.section_specs)
                if needs_form and elementor and not elementor.get("shortcodes"):
                    issues.append(QualityIssue(
                        id=f"DET-render-form-{page.page_slug}", category="functional", severity="high",
                        description=f"Rendered page {page.page_slug} requires a form section but no form shortcode is present.",
                        responsible_agent=AgentRole.BUILDER,
                        suggested_fix="Re-render only the booking/contact section after ensuring the approved form plugin.",
                    ))
                # Older/mock snapshots may not expose persisted SEO metadata.
                # Only validate these fields when the Bridge explicitly returned them.
                if ("seo_title" in actual or "meta_description" in actual) and (
                    not str(actual.get("seo_title", "")).strip() or not str(actual.get("meta_description", "")).strip()
                ):
                    issues.append(QualityIssue(
                        id=f"DET-render-seo-{page.page_slug}", category="seo", severity="medium",
                        description=f"Generated page {page.page_slug} is missing stored SEO title or meta description.",
                        responsible_agent=AgentRole.BUILDER,
                        suggested_fix="Run set-page-seo only for this page.",
                    ))
        return issues

    @staticmethod
    def _compact_qa_evidence(
        brief: ProjectBrief,
        architecture: ArchitectureBundle,
        experience: ExperienceSpec,
        deterministic: list[QualityIssue],
        executions: list[dict[str, Any]],
        snapshot: SiteSnapshot,
    ) -> dict[str, Any]:
        latest = PullPlanningWorkflow._latest_executions(executions)
        failures = [
            {
                "ability": str((x.get("action") or {}).get("ability", "")),
                "error": str(x.get("error", ""))[:500],
            }
            for x in latest if not x.get("executed")
        ]
        successes = [
            str((x.get("action") or {}).get("ability", ""))
            for x in latest if x.get("executed")
        ]
        actual_pages = []
        for page in snapshot.pages:
            actual_pages.append({
                "slug": page.get("slug"),
                "title": page.get("title"),
                "status": page.get("status"),
                "ai_generated": page.get("ai_generated", False),
                "seo_title": page.get("seo_title", ""),
                "meta_description": page.get("meta_description", ""),
                "elementor": page.get("elementor", {}),
            })
        return {
            "prototype_contract": {
                "draft_first_expected": True,
                "human_publish_after_qa": True,
                "draft_status_is_not_a_defect": True,
            },
            "project_brief": {
                "site_type": brief.site_type,
                "primary_goal": brief.primary_goal,
                "requirements": brief.requirements,
                "missing_facts": brief.missing_facts,
            },
            "architecture": {
                "pages": [{"slug": p.slug, "purpose": p.purpose, "primary_cta": p.primary_cta} for p in architecture.pages],
                "content_matrix": [m.model_dump(mode="json") for m in architecture.content_matrix],
            },
            "intended_content_summary": [
                {
                    "slug": p.page_slug,
                    "goal": p.page_goal,
                    "h1": p.seo.h1,
                    "title": p.seo.title,
                    "meta_description": p.seo.meta_description,
                    "section_headings": [s.heading for s in p.section_specs],
                    "ctas": [{"label": s.cta_label, "url": s.cta_url} for s in p.section_specs if s.cta_label],
                    "section_types": [s.section_type for s in p.section_specs],
                }
                for p in experience.pages
            ],
            "actual_page_signals": actual_pages,
            "site_structure": snapshot.structure,
            "successful_abilities": successes,
            "latest_failures": failures,
            "deterministic_issues": [i.model_dump(mode="json") for i in deterministic],
            "evidence_limit": "No browser screenshots or Playwright evidence supplied; visual claims are out of scope.",
        }

    @staticmethod
    def _merge_quality(ai_report: QualityReport, deterministic: list[QualityIssue]) -> QualityReport:
        issues: list[QualityIssue] = []
        seen: set[str] = set()
        for issue in [*deterministic, *ai_report.issues]:
            if issue.id in seen:
                continue
            seen.add(issue.id)
            issues.append(issue)
        return ai_report.model_copy(update={
            "passed": len(issues) == 0,
            "issues": issues,
            "checks_performed": list(dict.fromkeys([
                *ai_report.checks_performed,
                "deterministic execution outcomes",
                "required page inventory",
                "capability/plugin activation",
                "homepage/site structure",
                "duplicate page/H1 detection",
                "content matrix internal links",
            ])),
            "summary": ai_report.summary if not issues else "Post-build verification found bounded issues that require repair or user attention.",
        })

    @staticmethod
    def _deterministic_repair_plan(
        bundle: dict[str, Any],
        executions: list[dict[str, Any]],
        report: QualityReport,
    ) -> BuildPlan:
        build_plan = BuildPlan.model_validate(bundle["build_plan"])
        latest = PullPlanningWorkflow._latest_executions(executions)
        actions: list[BuildAction] = []
        seen: set[tuple[str, str]] = set()
        safe_retry = {
            "thesis-ai-bridge/elementor-ensure-draft-page",
            "thesis-ai-bridge/ensure-draft-page",
            "thesis-ai-bridge/set-page-seo",
            "thesis-ai-bridge/update-site-identity",
            "thesis-ai-bridge/apply-site-design",
            "thesis-ai-bridge/ensure-navigation-menu",
            "thesis-ai-bridge/set-homepage-by-slug",
            "thesis-ai-bridge/ensure-approved-plugin",
            "thesis-ai-bridge/ensure-approved-theme",
            "thesis-ai-bridge/ensure-contact-form",
        }
        for item in latest:
            if item.get("executed"):
                continue
            raw = item.get("action") or {}
            ability = str(raw.get("ability", ""))
            if ability not in safe_retry:
                continue
            action = BuildAction.model_validate(raw)
            key = (action.ability, json.dumps(action.parameters, sort_keys=True, ensure_ascii=False))
            if key not in seen:
                actions.append(action)
                seen.add(key)

        repair_page_slugs: set[str] = set()
        needs_form_retry = False
        for issue in report.issues:
            if issue.id == "DET-pages" and ":" in issue.description:
                repair_page_slugs.update(x.strip() for x in issue.description.split(":", 1)[1].split(",") if x.strip())
            for prefix in [
                "DET-render-sparse-", "DET-render-headings-", "DET-render-cta-",
                "DET-render-form-", "DET-render-seo-", "DET-section-headings-",
                "DET-planning-copy-", "DET-cta-", "DET-sections-",
            ]:
                if issue.id.startswith(prefix):
                    repair_page_slugs.add(issue.id[len(prefix):])
                    if prefix == "DET-render-form-":
                        needs_form_retry = True
            if issue.id == "DET-home":
                candidate = next((a for a in build_plan.actions if a.ability == "thesis-ai-bridge/set-homepage-by-slug"), None)
                if candidate:
                    key = (candidate.ability, json.dumps(candidate.parameters, sort_keys=True, ensure_ascii=False))
                    if key not in seen:
                        actions.append(candidate); seen.add(key)

        if needs_form_retry:
            candidate = next((a for a in build_plan.actions if a.ability == "thesis-ai-bridge/ensure-contact-form"), None)
            if candidate:
                key = (candidate.ability, json.dumps(candidate.parameters, sort_keys=True, ensure_ascii=False))
                if key not in seen:
                    actions.append(candidate); seen.add(key)

        if repair_page_slugs:
            for candidate in build_plan.actions:
                if candidate.ability not in {"thesis-ai-bridge/elementor-ensure-draft-page", "thesis-ai-bridge/ensure-draft-page", "thesis-ai-bridge/set-page-seo"}:
                    continue
                if str(candidate.parameters.get("slug", "")) not in repair_page_slugs:
                    continue
                key = (candidate.ability, json.dumps(candidate.parameters, sort_keys=True, ensure_ascii=False))
                if key not in seen:
                    actions.append(candidate); seen.add(key)
        return BuildPlan(actions=actions)

    async def verify(
        self,
        *,
        bundle: dict[str, Any],
        executions: list[dict[str, Any]],
        verification_snapshot: SiteSnapshot,
        repair_attempts: int,
    ) -> dict[str, Any]:
        brief = ProjectBrief.model_validate(bundle["project_brief"])
        architecture = ArchitectureBundle.model_validate(bundle["architecture"])
        app_spec = ApplicationSpec.model_validate(bundle["application_spec"])
        experience = ExperienceSpec.model_validate(bundle["experience_spec"])

        deterministic = self._deterministic_issues(app_spec, architecture, experience, executions, verification_snapshot)
        qa_evidence = self._compact_qa_evidence(brief, architecture, experience, deterministic, executions, verification_snapshot)
        try:
            ai_report = await self.agents.quality(qa_evidence)
        except Exception as exc:
            # Deterministic QA remains useful even if the optional semantic QA call
            # hits its budget or transport limit.
            ai_report = QualityReport(
                passed=not deterministic,
                summary=f"Semantic QA unavailable; deterministic QA retained: {exc}",
                checks_performed=["deterministic fallback"],
                issues=[],
            )
        report = self._merge_quality(ai_report, deterministic)

        repair_actions: list[dict[str, Any]] = []
        pending: list[dict[str, Any]] = []
        blocked: list[dict[str, Any]] = []
        if not report.passed and repair_attempts < max(0, int(self.settings.max_repair_loops)):
            deterministic_repair = self._deterministic_repair_plan(bundle, executions, report)
            repair_plan = deterministic_repair
            if not repair_plan.actions and self.settings.enable_llm_repair_escalation and any(i.severity in {"high", "critical"} for i in report.issues):
                try:
                    repair_plan = await self.agents.repair({
                        "issues": [i.model_dump(mode="json") for i in report.issues if i.severity in {"high", "critical"}],
                        "allowed_abilities": list(self.policy.RULES.keys()),
                        "instruction": "Return only the smallest idempotent delta repair. Do not rebuild successful pages.",
                    })
                except Exception:
                    repair_plan = BuildPlan(actions=[])
            gated = self._gate_actions(repair_plan.actions)
            repair_actions, pending, blocked = gated["allowed"], gated["pending"], gated["blocked"]

        return {
            "quality_report": report.model_dump(mode="json"),
            "repair_actions": repair_actions,
            "pending_actions": pending,
            "blocked_actions": blocked,
            "done": report.passed or not repair_actions or repair_attempts >= int(self.settings.max_repair_loops),
            "usage": self.agents.usage.model_dump(mode="json"),
            "budget": self.agents.budget_state(),
            "agent_mode": self.settings.resolved_agent_mode,
            "model_router": self.settings.model_router if self.settings.resolved_agent_mode == "openai" else {"all": "mock"},
        }
