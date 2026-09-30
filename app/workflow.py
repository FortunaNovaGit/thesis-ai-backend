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

    async def _execute_actions_batched(
        self,
        run: ProjectRun,
        actions: list[BuildAction],
        actor: AgentRole,
        *,
        attempt: int = 1,
        progress_start: int = 50,
        progress_end: int = 75,
    ) -> tuple[bool, SiteSnapshot | None]:
        """Policy-check actions individually, then execute allowed actions in small HTTP batches.

        This is specifically designed for managed WordPress hosts such as EasyWP:
        dozens of agent actions become only a few inbound REST requests. The final
        batch returns a fresh site snapshot, so verification does not need another
        immediate request that could trip Anti-DDoS rate limiting.
        """
        has_pending_approval = False
        approved: list[tuple[BuildAction, object]] = []

        for action in actions:
            decision = self.policy.evaluate(
                actor=actor, action=action, auto_approve_medium=self.settings.auto_approve_medium_risk
            )
            if decision.outcome == PolicyOutcome.ALLOW:
                approved.append((action, decision))
            elif decision.outcome == PolicyOutcome.REQUIRE_APPROVAL:
                has_pending_approval = True
                run.executions.append(ActionExecution(
                    action=action, policy=decision, executed=False,
                    error="Waiting for human approval", attempt=attempt
                ))
            else:
                run.executions.append(ActionExecution(
                    action=action, policy=decision, executed=False,
                    error="Blocked by policy", attempt=attempt
                ))
        self._save(run)

        if not approved:
            return has_pending_approval, None

        batch_size = max(1, int(self.settings.wordpress_batch_size))
        latest_snapshot: SiteSnapshot | None = None
        total = len(approved)
        chunks = [approved[i:i + batch_size] for i in range(0, total, batch_size)]

        processed = 0
        for chunk_index, chunk in enumerate(chunks):
            chunk_actions = [item[0] for item in chunk]
            include_snapshot = chunk_index == len(chunks) - 1
            pct = progress_start + int((processed / max(1, total)) * max(1, progress_end - progress_start))
            await self._progress(
                "building" if actor == AgentRole.BUILDER else "repair",
                min(progress_end, pct),
                f"Executing WordPress batch {chunk_index + 1}/{len(chunks)} ({len(chunk_actions)} actions)",
            )
            try:
                payload = await self.wordpress.execute_batch(chunk_actions, include_snapshot=include_snapshot)
            except Exception as exc:
                for action, decision in chunk:
                    run.executions.append(ActionExecution(
                        action=action, policy=decision, executed=False, error=str(exc), attempt=attempt
                    ))
                self._save(run)
                # Do not hammer a managed-host firewall with additional batches after
                # a transport/rate-limit failure. Stop this phase immediately.
                break

            result_items = payload.get("results", []) if isinstance(payload, dict) else []
            by_index = {int(item.get("index", -1)): item for item in result_items if isinstance(item, dict)}
            for local_index, (action, decision) in enumerate(chunk):
                item = by_index.get(local_index, {})
                ok = bool(item.get("ok"))
                run.executions.append(ActionExecution(
                    action=action,
                    policy=decision,
                    executed=ok,
                    result=item.get("result") if ok else None,
                    error=None if ok else str(item.get("error") or "Unknown batch execution error"),
                    attempt=attempt,
                ))
            processed += len(chunk)

            raw_snapshot = payload.get("snapshot") if isinstance(payload, dict) else None
            if isinstance(raw_snapshot, dict):
                latest_snapshot = SiteSnapshot(
                    site_info=raw_snapshot.get("site_info") or {},
                    pages=raw_snapshot.get("pages") or [],
                    plugins=raw_snapshot.get("plugins") or [],
                    themes=raw_snapshot.get("themes") or [],
                    capabilities=raw_snapshot.get("capabilities") or {},
                    structure=raw_snapshot.get("structure") or {},
                )
            self._save(run)

            if chunk_index < len(chunks) - 1 and self.settings.wordpress_inter_batch_delay_seconds > 0:
                await asyncio.sleep(float(self.settings.wordpress_inter_batch_delay_seconds))

        return has_pending_approval, latest_snapshot

    async def _inspect_site(self, run: ProjectRun, actor: AgentRole = AgentRole.ARCHITECT) -> SiteSnapshot:
        # One composite Bridge call replaces six back-to-back REST requests. This
        # materially reduces managed-hosting firewall pressure during preflight,
        # verification and repair loops.
        action = BuildAction(ability="thesis-ai-bridge/get-site-snapshot", rationale="Inspect WordPress environment in one throttling-friendly request")
        execution = await self._execute_action(run, action, actor)
        if not execution.executed:
            raise RuntimeError(f"Site inspection failed for {action.ability}: {execution.error}")
        result = execution.result or {}
        if not isinstance(result, dict):
            raise RuntimeError("Site snapshot returned an unexpected payload")
        return SiteSnapshot(
            site_info=result.get("site_info") or {},
            pages=result.get("pages") or [],
            plugins=result.get("plugins") or [],
            themes=result.get("themes") or [],
            capabilities=result.get("capabilities") or {},
            structure=result.get("structure") or {},
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
        has_pending_approval, batch_snapshot = await self._execute_actions_batched(
            run, run.build_plan.actions, AgentRole.BUILDER, attempt=1, progress_start=50, progress_end=75
        )

        run.status = "built"
        self._save(run)

        await self._progress("verification", 78, "Using the post-build snapshot returned by the final WordPress batch")
        # The Bridge returns a snapshot inside the final execution batch. Avoid an
        # immediate extra inbound REST request, which is exactly what EasyWP's
        # Anti-DDoS layer was rate-limiting in v0.5.3.
        run.verification_snapshot = batch_snapshot or run.site_snapshot
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
            repair_pending, repair_snapshot = await self._execute_actions_batched(
                run,
                repair_plan.actions,
                AgentRole.BUILDER,
                attempt=repair_loop + 1,
                progress_start=min(92, 88 + repair_loop * 2),
                progress_end=min(96, 92 + repair_loop * 2),
            )
            has_pending_approval = has_pending_approval or repair_pending
            if has_pending_approval:
                break
            if repair_snapshot is not None:
                run.verification_snapshot = repair_snapshot
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
