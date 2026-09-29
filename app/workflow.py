from __future__ import annotations

import asyncio
import inspect
import json
import uuid
from pathlib import Path
from typing import Awaitable, Callable

from .agents.runtime import AgentRuntime
from .config import Settings
from .models import AgentRole, ActionExecution, BuildAction, PolicyOutcome, ProjectRun, Renderer, SiteSnapshot
from .policy import PolicyEngine
from .tools.wordpress import WordPressExecutor


ProgressCallback = Callable[[str, int, str], Awaitable[None] | None]


class MultiAgentWorkflow:
    def __init__(self, settings: Settings, agents: AgentRuntime, wordpress: WordPressExecutor, run_dir: Path | None = None, progress_callback: ProgressCallback | None = None) -> None:
        self.settings = settings
        self.agents = agents
        self.wordpress = wordpress
        self.policy = PolicyEngine()
        self.run_dir = run_dir or Path("runs")
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.progress_callback = progress_callback

    async def _progress(self, stage: str, progress: int, detail: str = "") -> None:
        if not self.progress_callback:
            return
        result = self.progress_callback(stage, max(0, min(100, int(progress))), detail)
        if inspect.isawaitable(result):
            await result

    def _save(self, run: ProjectRun) -> None:
        (self.run_dir / f"{run.run_id}.json").write_text(run.model_dump_json(indent=2), encoding="utf-8")

    async def _execute_action(self, run: ProjectRun, action: BuildAction, actor: AgentRole, attempt: int = 1) -> ActionExecution:
        decision = self.policy.evaluate(actor=actor, action=action, auto_approve_medium=self.settings.auto_approve_medium_risk)
        if decision.outcome == PolicyOutcome.ALLOW:
            last_error: Exception | None = None
            retries = max(0, int(self.settings.transient_action_retries))
            for retry in range(retries + 1):
                try:
                    result = await self.wordpress.execute(action)
                    execution = ActionExecution(action=action, policy=decision, executed=True, result=result, attempt=attempt + retry)
                    break
                except Exception as exc:
                    last_error = exc
                    if retry < retries:
                        await asyncio.sleep(0.6 * (retry + 1))
            else:
                execution = ActionExecution(action=action, policy=decision, executed=False, error=str(last_error), attempt=attempt + retries)
        elif decision.outcome == PolicyOutcome.REQUIRE_APPROVAL:
            execution = ActionExecution(action=action, policy=decision, executed=False, error="Waiting for human approval", attempt=attempt)
        else:
            execution = ActionExecution(action=action, policy=decision, executed=False, error="Blocked by policy", attempt=attempt)
        run.executions.append(execution)
        self._save(run)
        return execution

    async def _inspect_site(self, run: ProjectRun, actor: AgentRole = AgentRole.ARCHITECT) -> SiteSnapshot:
        actions = [
            BuildAction(ability="thesis-ai-bridge/get-site-info", rationale="Inspect WordPress environment"),
            BuildAction(ability="thesis-ai-bridge/list-pages", rationale="Inspect existing pages"),
            BuildAction(ability="thesis-ai-bridge/list-plugins", rationale="Inspect installed plugins"),
            BuildAction(ability="thesis-ai-bridge/list-themes", rationale="Inspect installed themes"),
            BuildAction(ability="thesis-ai-bridge/inspect-capabilities", rationale="Resolve recognized capabilities"),
            BuildAction(ability="thesis-ai-bridge/get-site-structure", rationale="Inspect homepage/navigation/site structure"),
        ]
        results: dict[str, object] = {}
        for action in actions:
            execution = await self._execute_action(run, action, actor)
            if not execution.executed:
                raise RuntimeError(f"Site inspection failed for {action.ability}: {execution.error}")
            results[action.ability] = execution.result
        return SiteSnapshot(
            site_info=results.get("thesis-ai-bridge/get-site-info") or {},
            pages=results.get("thesis-ai-bridge/list-pages") or [],
            plugins=results.get("thesis-ai-bridge/list-plugins") or [],
            themes=results.get("thesis-ai-bridge/list-themes") or [],
            capabilities=results.get("thesis-ai-bridge/inspect-capabilities") or {},
            structure=results.get("thesis-ai-bridge/get-site-structure") or {},
        )

    def _executions_json(self, run: ProjectRun) -> str:
        return json.dumps([x.model_dump(mode="json") for x in run.executions], ensure_ascii=False)

    async def run(self, user_request: str, renderer: Renderer = "elementor") -> ProjectRun:
        run = ProjectRun(run_id=str(uuid.uuid4()), user_request=user_request, renderer=renderer)
        self._save(run)
        await self._progress("starting", 2, "Build accepted by the orchestration service")

        await self._progress("planning", 6, "Orchestrator is creating the task plan")
        run.task_plan = await self.agents.plan(user_request)
        run.status = "planned"
        self._save(run)

        await self._progress("preflight", 14, "Inspecting the current WordPress site")
        run.site_snapshot = await self._inspect_site(run, AgentRole.ARCHITECT)
        run.status = "inspected"
        self._save(run)

        await self._progress("architecture", 26, "Architect & Capability agent is resolving requirements")
        run.application_spec = await self.agents.architect(user_request, run.task_plan, run.site_snapshot, renderer)

        await self._progress("design", 38, "Design / Content / SEO agent is preparing the experience specification")
        run.experience_spec = await self.agents.design(run.application_spec, renderer)
        run.status = "specified"
        self._save(run)

        await self._progress("build_plan", 48, "Implementation agent is compiling the build plan")
        run.build_plan = await self.agents.build(run.application_spec, run.experience_spec, run.site_snapshot, renderer)
        has_pending_approval = False
        total_actions = max(1, len(run.build_plan.actions))
        for index, action in enumerate(run.build_plan.actions, start=1):
            pct = 50 + int((index - 1) / total_actions * 25)
            await self._progress("building", pct, f"Executing {action.ability} ({index}/{total_actions})")
            execution = await self._execute_action(run, action, AgentRole.BUILDER)
            if execution.policy.outcome == PolicyOutcome.REQUIRE_APPROVAL:
                has_pending_approval = True

        run.status = "built"
        self._save(run)

        await self._progress("verification", 78, "Inspecting the site after the build")
        run.verification_snapshot = await self._inspect_site(run, AgentRole.QUALITY)
        await self._progress("quality", 86, "Quality & Security agent is evaluating the result")
        report = await self.agents.quality(
            run.application_spec,
            run.experience_spec,
            self._executions_json(run),
            run.verification_snapshot,
            renderer,
        )
        run.quality_reports.append(report)
        run.usage = self.agents.usage
        self._save(run)

        repair_loop = 0
        while not report.passed and not has_pending_approval and repair_loop < max(0, int(self.settings.max_repair_loops)):
            repair_loop += 1
            run.repair_attempts = repair_loop
            run.status = "repairing"
            await self._progress("repair", min(94, 88 + repair_loop * 3), f"Repair loop {repair_loop} is preparing corrective actions")
            repair_plan = await self.agents.repair(
                run.application_spec,
                run.experience_spec,
                run.verification_snapshot,
                report,
                self._executions_json(run),
                renderer,
            )
            if not repair_plan.actions:
                break
            for action in repair_plan.actions:
                execution = await self._execute_action(run, action, AgentRole.BUILDER, attempt=repair_loop + 1)
                if execution.policy.outcome == PolicyOutcome.REQUIRE_APPROVAL:
                    has_pending_approval = True
            if has_pending_approval:
                break
            run.verification_snapshot = await self._inspect_site(run, AgentRole.QUALITY)
            report = await self.agents.quality(
                run.application_spec,
                run.experience_spec,
                self._executions_json(run),
                run.verification_snapshot,
                renderer,
            )
            run.quality_reports.append(report)
            run.usage = self.agents.usage
            self._save(run)

        if has_pending_approval:
            run.status = "needs_approval"
        elif report.passed:
            run.status = "passed"
        else:
            run.status = "failed"
        run.usage = self.agents.usage
        self._save(run)
        await self._progress("completed", 100, f"Build finished with status: {run.status}")
        return run
