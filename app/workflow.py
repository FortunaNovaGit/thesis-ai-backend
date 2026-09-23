from __future__ import annotations

import json
import uuid
from pathlib import Path

from .agents.runtime import AgentRuntime
from .config import Settings
from .models import AgentRole, ActionExecution, PolicyOutcome, ProjectRun
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

    async def run(self, user_request: str) -> ProjectRun:
        run = ProjectRun(run_id=str(uuid.uuid4()), user_request=user_request)
        self._save(run)

        run.task_plan = await self.agents.plan(user_request)
        run.status = "planned"
        self._save(run)

        run.application_spec = await self.agents.architect(user_request, run.task_plan)
        run.experience_spec = await self.agents.design(run.application_spec)
        run.status = "specified"
        self._save(run)

        run.build_plan = await self.agents.build(run.application_spec, run.experience_spec)

        has_pending_approval = False
        for action in run.build_plan.actions:
            decision = self.policy.evaluate(
                actor=AgentRole.BUILDER,
                action=action,
                auto_approve_medium=self.settings.auto_approve_medium_risk,
            )
            if decision.outcome == PolicyOutcome.ALLOW:
                try:
                    result = await self.wordpress.execute(action)
                    execution = ActionExecution(action=action, policy=decision, executed=True, result=result)
                except Exception as exc:  # executor errors are evidence for QA/replanning
                    execution = ActionExecution(action=action, policy=decision, executed=False, error=str(exc))
            elif decision.outcome == PolicyOutcome.REQUIRE_APPROVAL:
                has_pending_approval = True
                execution = ActionExecution(action=action, policy=decision, executed=False, error="Waiting for human approval")
            else:
                execution = ActionExecution(action=action, policy=decision, executed=False, error="Blocked by policy")
            run.executions.append(execution)
            self._save(run)

        report = await self.agents.quality(
            run.application_spec,
            run.experience_spec,
            json.dumps([x.model_dump(mode="json") for x in run.executions], ensure_ascii=False),
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
