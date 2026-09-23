from __future__ import annotations

import json
import uuid
from pathlib import Path

from .agents.runtime import AgentRuntime
from .config import Settings
from .models import AgentRole, ActionExecution, BuildAction, PolicyOutcome, ProjectRun, Renderer, SiteSnapshot
from .policy import PolicyEngine
from .tools.wordpress import WordPressExecutor


class MultiAgentWorkflow:
    def __init__(self, settings: Settings, agents: AgentRuntime, wordpress: WordPressExecutor, run_dir: Path | None = None) -> None:
        self.settings = settings
        self.agents = agents
        self.wordpress = wordpress
        self.policy = PolicyEngine()
        self.run_dir = run_dir or Path("runs")
        self.run_dir.mkdir(parents=True, exist_ok=True)

    def _save(self, run: ProjectRun) -> None:
        (self.run_dir / f"{run.run_id}.json").write_text(run.model_dump_json(indent=2), encoding="utf-8")

    async def _execute_action(self, run: ProjectRun, action: BuildAction, actor: AgentRole) -> ActionExecution:
        decision = self.policy.evaluate(actor=actor, action=action, auto_approve_medium=self.settings.auto_approve_medium_risk)
        if decision.outcome == PolicyOutcome.ALLOW:
            try:
                result = await self.wordpress.execute(action)
                execution = ActionExecution(action=action, policy=decision, executed=True, result=result)
            except Exception as exc:
                execution = ActionExecution(action=action, policy=decision, executed=False, error=str(exc))
        elif decision.outcome == PolicyOutcome.REQUIRE_APPROVAL:
            execution = ActionExecution(action=action, policy=decision, executed=False, error="Waiting for human approval")
        else:
            execution = ActionExecution(action=action, policy=decision, executed=False, error="Blocked by policy")
        run.executions.append(execution)
        self._save(run)
        return execution

    async def _inspect_site(self, run: ProjectRun) -> SiteSnapshot:
        actions = [
            BuildAction(ability="thesis-ai-bridge/get-site-info", rationale="Preflight: inspect WordPress environment"),
            BuildAction(ability="thesis-ai-bridge/list-plugins", rationale="Preflight: inspect every installed plugin"),
            BuildAction(ability="thesis-ai-bridge/inspect-capabilities", rationale="Preflight: resolve known capabilities and builder availability"),
        ]
        results: dict[str, object] = {}
        for action in actions:
            execution = await self._execute_action(run, action, AgentRole.ARCHITECT)
            if not execution.executed:
                raise RuntimeError(f"Site preflight failed for {action.ability}: {execution.error}")
            results[action.ability] = execution.result
        return SiteSnapshot(
            site_info=results.get("thesis-ai-bridge/get-site-info") or {},
            plugins=results.get("thesis-ai-bridge/list-plugins") or [],
            capabilities=results.get("thesis-ai-bridge/inspect-capabilities") or {},
        )

    async def run(self, user_request: str, renderer: Renderer = "elementor") -> ProjectRun:
        run = ProjectRun(run_id=str(uuid.uuid4()), user_request=user_request, renderer=renderer)
        self._save(run)

        run.task_plan = await self.agents.plan(user_request)
        run.status = "planned"
        self._save(run)

        run.site_snapshot = await self._inspect_site(run)
        run.status = "inspected"
        self._save(run)

        run.application_spec = await self.agents.architect(user_request, run.task_plan, run.site_snapshot, renderer)
        run.experience_spec = await self.agents.design(run.application_spec, renderer)
        run.status = "specified"
        self._save(run)

        run.build_plan = await self.agents.build(run.application_spec, run.experience_spec, run.site_snapshot, renderer)

        has_pending_approval = False
        for action in run.build_plan.actions:
            execution = await self._execute_action(run, action, AgentRole.BUILDER)
            if execution.policy.outcome == PolicyOutcome.REQUIRE_APPROVAL:
                has_pending_approval = True

        report = await self.agents.quality(
            run.application_spec,
            run.experience_spec,
            json.dumps([x.model_dump(mode="json") for x in run.executions], ensure_ascii=False),
            renderer,
        )
        run.quality_reports.append(report)

        if has_pending_approval:
            run.status = "needs_approval"
        elif report.passed:
            run.status = "passed"
        else:
            run.status = "failed"
        self._save(run)
        return run
