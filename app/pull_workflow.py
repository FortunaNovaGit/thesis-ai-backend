from __future__ import annotations

import json
import uuid
from typing import Any

from .agents.runtime import AgentRuntime
from .config import Settings
from .models import (
    AgentRole,
    ApplicationSpec,
    BuildAction,
    BuildPlan,
    ExperienceSpec,
    PolicyOutcome,
    QualityIssue,
    QualityReport,
    Renderer,
    SiteSnapshot,
    TaskPlan,
)
from .policy import PolicyEngine


class PullPlanningWorkflow:
    """Plan/verify workflow for WordPress-driven (pull) execution.

    The backend never calls the WordPress site. WordPress sends a local snapshot,
    receives a policy-approved build plan, executes abilities locally, then sends
    execution evidence + a fresh snapshot back for Quality/Repair.
    """

    def __init__(self, settings: Settings, agents: AgentRuntime) -> None:
        self.settings = settings
        self.agents = agents
        self.policy = PolicyEngine()

    def _gate_actions(self, actions: list[BuildAction], actor: AgentRole = AgentRole.BUILDER) -> dict[str, Any]:
        allowed: list[dict[str, Any]] = []
        pending: list[dict[str, Any]] = []
        blocked: list[dict[str, Any]] = []
        for action in actions:
            decision = self.policy.evaluate(
                actor=actor,
                action=action,
                auto_approve_medium=self.settings.auto_approve_medium_risk,
            )
            item = {
                "action": action.model_dump(mode="json"),
                "policy": decision.model_dump(mode="json"),
            }
            if decision.outcome == PolicyOutcome.ALLOW:
                allowed.append(item)
            elif decision.outcome == PolicyOutcome.REQUIRE_APPROVAL:
                pending.append(item)
            else:
                blocked.append(item)
        return {"allowed": allowed, "pending": pending, "blocked": blocked}

    async def plan(
        self,
        user_request: str,
        renderer: Renderer,
        site_snapshot: SiteSnapshot,
        progress=None,
    ) -> dict[str, Any]:
        async def report(stage: str, pct: int, detail: str) -> None:
            if progress is not None:
                result = progress(stage, pct, detail)
                if hasattr(result, "__await__"):
                    await result

        await report("orchestrator", 8, "Orchestrator is decomposing the website request")
        task_plan: TaskPlan = await self.agents.plan(user_request)

        await report("architecture", 22, "Architect is resolving pages, capabilities, plugins and data needs")
        app_spec: ApplicationSpec = await self.agents.architect(user_request, task_plan, site_snapshot, renderer)

        await report("design", 42, "Design/Content/SEO agent is creating the site experience specification")
        experience_spec: ExperienceSpec = await self.agents.design(app_spec, renderer)

        await report("implementation_plan", 62, "Implementation agent is compiling controlled WordPress abilities")
        build_plan: BuildPlan = await self.agents.build(app_spec, experience_spec, site_snapshot, renderer)
        gated = self._gate_actions(build_plan.actions)

        await report("ready", 100, "Plan is ready for local WordPress execution")
        return {
            "plan_id": str(uuid.uuid4()),
            "user_request": user_request,
            "renderer": renderer,
            "task_plan": task_plan.model_dump(mode="json"),
            "site_snapshot": site_snapshot.model_dump(mode="json"),
            "application_spec": app_spec.model_dump(mode="json"),
            "experience_spec": experience_spec.model_dump(mode="json"),
            "build_plan": build_plan.model_dump(mode="json"),
            "approved_actions": gated["allowed"],
            "pending_actions": gated["pending"],
            "blocked_actions": gated["blocked"],
            "agent_mode": self.settings.resolved_agent_mode,
            "model": self.settings.openai_model if self.settings.resolved_agent_mode == "openai" else "mock",
            "usage": self.agents.usage.model_dump(mode="json"),
        }

    @staticmethod
    def _latest_execution_failures(executions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        for item in executions:
            action = item.get("action") or {}
            key = str(action.get("ability", "")) + "|" + json.dumps(
                action.get("parameters", {}), sort_keys=True, ensure_ascii=False
            )
            latest[key] = item
        return [
            item
            for item in latest.values()
            if not bool(item.get("executed"))
            and str((item.get("policy") or {}).get("outcome", "")) != "require_approval"
        ]

    @staticmethod
    def _augment_quality(
        report: QualityReport,
        app_spec: ApplicationSpec,
        executions: list[dict[str, Any]],
        snapshot: SiteSnapshot,
    ) -> QualityReport:
        """Hard deterministic checks are authoritative even with an LLM QA agent."""
        issues = list(report.issues)
        ids = {issue.id for issue in issues}

        failures = PullPlanningWorkflow._latest_execution_failures(executions)
        if failures and "DET-actions" not in ids:
            issues.append(QualityIssue(
                id="DET-actions",
                category="functional",
                severity="high",
                description=f"{len(failures)} latest build actions failed or were blocked.",
                responsible_agent=AgentRole.BUILDER,
                suggested_fix="Retry only the failed safe/idempotent actions and re-verify.",
            ))

        required_slugs = {page.slug for page in app_spec.pages}
        actual_slugs = {str(page.get("slug", "")) for page in snapshot.pages}
        missing = sorted(required_slugs - actual_slugs)
        if missing and "DET-pages" not in ids:
            issues.append(QualityIssue(
                id="DET-pages",
                category="functional",
                severity="high",
                description=f"Missing required pages: {', '.join(missing)}",
                responsible_agent=AgentRole.BUILDER,
                suggested_fix="Create or restore the missing AI-generated draft pages.",
            ))

        required_plugins = {item.plugin_slug for item in app_spec.plugin_plan}
        active_plugins = {str(p.get("slug", "")) for p in snapshot.plugins if p.get("active")}
        missing_plugins = sorted(required_plugins - active_plugins)
        if missing_plugins and "DET-plugins" not in ids:
            issues.append(QualityIssue(
                id="DET-plugins",
                category="functional",
                severity="high",
                description=f"Required plugins are not active: {', '.join(missing_plugins)}",
                responsible_agent=AgentRole.BUILDER,
                suggested_fix="Install/activate only the approved required plugins and re-verify.",
            ))

        if any(page.slug == "home" for page in app_spec.pages):
            homepage_slug = str(snapshot.structure.get("homepage_slug", ""))
            if homepage_slug not in {"", "home"} and "DET-home" not in ids:
                issues.append(QualityIssue(
                    id="DET-home",
                    category="functional",
                    severity="medium",
                    description="The generated Home page is not configured as the static homepage.",
                    responsible_agent=AgentRole.BUILDER,
                    suggested_fix="Run set-homepage-by-slug for home.",
                ))

        return report.model_copy(update={
            "passed": len(issues) == 0,
            "issues": issues,
            "checks_performed": list(dict.fromkeys(report.checks_performed + [
                "deterministic execution outcome check",
                "required page inventory",
                "required plugin activation",
                "homepage/site structure",
            ])),
            "summary": report.summary if not issues else "Post-build verification found issues that require repair or user attention.",
        })

    async def verify(
        self,
        *,
        bundle: dict[str, Any],
        executions: list[dict[str, Any]],
        verification_snapshot: SiteSnapshot,
        repair_attempts: int,
    ) -> dict[str, Any]:
        app_spec = ApplicationSpec.model_validate(bundle["application_spec"])
        experience_spec = ExperienceSpec.model_validate(bundle["experience_spec"])
        renderer: Renderer = bundle.get("renderer", "elementor")

        report = await self.agents.quality(
            app_spec,
            experience_spec,
            json.dumps(executions, ensure_ascii=False),
            verification_snapshot,
            renderer,
        )
        report = self._augment_quality(report, app_spec, executions, verification_snapshot)

        repair_actions: list[dict[str, Any]] = []
        pending: list[dict[str, Any]] = []
        blocked: list[dict[str, Any]] = []
        if not report.passed and repair_attempts < max(0, int(self.settings.max_repair_loops)):
            repair_plan = await self.agents.repair(
                app_spec,
                experience_spec,
                verification_snapshot,
                report,
                json.dumps(executions, ensure_ascii=False),
                renderer,
            )
            gated = self._gate_actions(repair_plan.actions)
            repair_actions = gated["allowed"]
            pending = gated["pending"]
            blocked = gated["blocked"]

        return {
            "quality_report": report.model_dump(mode="json"),
            "repair_actions": repair_actions,
            "pending_actions": pending,
            "blocked_actions": blocked,
            "done": report.passed or not repair_actions or repair_attempts >= int(self.settings.max_repair_loops),
            "usage": self.agents.usage.model_dump(mode="json"),
            "agent_mode": self.settings.resolved_agent_mode,
            "model": self.settings.openai_model if self.settings.resolved_agent_mode == "openai" else "mock",
        }
