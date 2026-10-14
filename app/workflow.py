from __future__ import annotations

import asyncio
import inspect
import json
import uuid
from pathlib import Path
from typing import Awaitable, Callable

from .agents.runtime import AgentRuntime
from .config import Settings
from .models import AgentRole, ActionExecution, BuildAction, PolicyOutcome, ProjectRun, QualityReport, Renderer, SiteSnapshot
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
        include_final_snapshot: bool = True,
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
            include_snapshot = include_final_snapshot and chunk_index == len(chunks) - 1
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

            if (
                chunk_index < len(chunks) - 1
                and self.settings.wordpress_mode != "mock"
                and self.settings.wordpress_inter_batch_delay_seconds > 0
            ):
                await asyncio.sleep(float(self.settings.wordpress_inter_batch_delay_seconds))

        return has_pending_approval, latest_snapshot


    @staticmethod
    def _snapshot_plugin_active(snapshot: SiteSnapshot, slug: str) -> bool:
        for plugin in snapshot.plugins:
            if str(plugin.get("slug", "")) == slug:
                return bool(plugin.get("active"))
        approved = snapshot.capabilities.get("approved_plugins", {}) if isinstance(snapshot.capabilities, dict) else {}
        state = approved.get(slug) if isinstance(approved, dict) else None
        return bool(isinstance(state, dict) and state.get("active"))

    @staticmethod
    def _snapshot_theme_active(snapshot: SiteSnapshot, slug: str) -> bool:
        return str(snapshot.site_info.get("theme_slug", "")) == slug

    async def _execute_actions_staged(
        self,
        run: ProjectRun,
        actions: list[BuildAction],
        actor: AgentRole,
        snapshot: SiteSnapshot,
        *,
        attempt: int = 1,
        progress_start: int = 50,
        progress_end: int = 75,
    ) -> tuple[bool, SiteSnapshot | None]:
        """Execute actions in fresh-request phases.

        Plugin/theme activation must never share the same PHP request with
        Elementor document creation: WordPress loads active plugins/themes during
        bootstrap, so newly activated code is not guaranteed to be fully initialized
        until the next request. v0.5.4 batched across that boundary and could turn
        one Elementor/activation error into a whole-batch HTTP 500.

        We still keep request volume low:
        - already-satisfied dependencies are resolved from preflight with zero HTTP calls;
        - dependency changes run as isolated requests (fresh bootstrap barrier);
        - page + SEO work runs in one guarded batch;
        - site assembly runs in a final guarded batch that returns the snapshot.
        """
        dependency_abilities = {
            "thesis-ai-bridge/ensure-approved-plugin",
            "thesis-ai-bridge/ensure-approved-theme",
        }
        dependent_setup = {"thesis-ai-bridge/ensure-contact-form"}
        assembly_abilities = {
            "thesis-ai-bridge/update-site-identity",
            "thesis-ai-bridge/ensure-navigation-menu",
            "thesis-ai-bridge/set-homepage-by-slug",
        }

        dependencies: list[BuildAction] = []
        setup: list[BuildAction] = []
        content: list[BuildAction] = []
        assembly: list[BuildAction] = []

        for action in actions:
            if action.ability in dependency_abilities:
                # Resolve no-op dependency actions from the preflight snapshot.
                if action.ability.endswith("ensure-approved-plugin"):
                    slug = str(action.parameters.get("plugin_slug", ""))
                    if slug and self._snapshot_plugin_active(snapshot, slug):
                        decision = self.policy.evaluate(actor=actor, action=action, auto_approve_medium=self.settings.auto_approve_medium_risk)
                        run.executions.append(ActionExecution(
                            action=action, policy=decision, executed=True,
                            result={"plugin_slug": slug, "active": True, "changed": False, "message": "Already active at preflight."},
                            attempt=attempt,
                        ))
                        continue
                if action.ability.endswith("ensure-approved-theme"):
                    slug = str(action.parameters.get("theme_slug", ""))
                    if slug and self._snapshot_theme_active(snapshot, slug):
                        decision = self.policy.evaluate(actor=actor, action=action, auto_approve_medium=self.settings.auto_approve_medium_risk)
                        run.executions.append(ActionExecution(
                            action=action, policy=decision, executed=True,
                            result={"theme_slug": slug, "active": True, "changed": False, "message": "Already active at preflight."},
                            attempt=attempt,
                        ))
                        continue
                dependencies.append(action)
            elif action.ability in dependent_setup:
                setup.append(action)
            elif action.ability in assembly_abilities:
                assembly.append(action)
            else:
                content.append(action)
        self._save(run)

        has_pending = False
        latest_snapshot: SiteSnapshot | None = None

        # Dependencies are intentionally isolated. A fresh WordPress bootstrap after
        # activation is a correctness boundary, not an optimization detail.
        for idx, action in enumerate(dependencies):
            pct = progress_start + min(8, idx * 2)
            await self._progress("building" if actor == AgentRole.BUILDER else "repair", pct, f"Preparing dependency: {action.ability}")
            ex = await self._execute_action(run, action, actor, attempt=attempt)
            if ex.policy.outcome == PolicyOutcome.REQUIRE_APPROVAL:
                has_pending = True
            if not ex.executed and ex.policy.outcome == PolicyOutcome.ALLOW:
                # If a dependency cannot be prepared, dependent page work would only
                # create noise. Stop this phase and let QA report the exact failure.
                return has_pending, latest_snapshot
            if self.settings.wordpress_mode != "mock" and self.settings.wordpress_inter_batch_delay_seconds > 0:
                await asyncio.sleep(float(self.settings.wordpress_inter_batch_delay_seconds))

        # Contact Form 7 forms (or similar setup) need a request after plugin bootstrap.
        if setup and not has_pending:
            pending, _ = await self._execute_actions_batched(
                run, setup, actor, attempt=attempt,
                progress_start=progress_start + 10, progress_end=progress_start + 14,
                include_final_snapshot=False,
            )
            has_pending = has_pending or pending
            if self.settings.wordpress_mode != "mock" and self.settings.wordpress_inter_batch_delay_seconds > 0:
                await asyncio.sleep(float(self.settings.wordpress_inter_batch_delay_seconds))

        if content and not has_pending:
            pending, snap = await self._execute_actions_batched(
                run, content, actor, attempt=attempt,
                progress_start=progress_start + 15, progress_end=max(progress_start + 16, progress_end - 6),
                include_final_snapshot=False,
            )
            has_pending = has_pending or pending
            latest_snapshot = snap or latest_snapshot

        # Final assembly happens only after pages exist. Returning snapshot here avoids
        # another verification request and is safe because no plugin/theme bootstrap
        # change is mixed into this request.
        if assembly and not has_pending:
            pending, snap = await self._execute_actions_batched(
                run, assembly, actor, attempt=attempt,
                progress_start=max(progress_start + 16, progress_end - 5), progress_end=progress_end,
                include_final_snapshot=True,
            )
            has_pending = has_pending or pending
            latest_snapshot = snap or latest_snapshot

        return has_pending, latest_snapshot

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
        # Legacy/local executor retained for tests and CLI. It follows the same
        # v0.7 artifact pipeline as the pull API, but executes against the local
        # WordPressExecutor abstraction.
        from .agents.runtime import (
            architecture_to_application_spec, compact_site_summary, compile_build_plan,
            make_task_plan, merge_advisory_actions, normalize_architecture, reconcile_experience,
        )
        from .capabilities import resolve_capabilities
        from .pull_workflow import PullPlanningWorkflow

        run = ProjectRun(run_id=str(uuid.uuid4()), user_request=user_request, renderer=renderer)
        self._save(run)
        await self._progress("starting", 2, "Build accepted")

        run.project_brief = await self.agents.orchestrate(user_request, renderer)
        run.project_brief = run.project_brief.model_copy(update={"renderer": renderer})
        run.task_plan = make_task_plan(run.project_brief)
        run.status = "planned"

        await self._progress("preflight", 14, "Inspecting WordPress")
        run.site_snapshot = await self._inspect_site(run, AgentRole.ARCHITECT)
        run.status = "inspected"

        run.architecture = await self.agents.architect(run.project_brief, compact_site_summary(run.site_snapshot))
        run.architecture = normalize_architecture(run.project_brief, run.architecture)
        run.capability_resolutions = resolve_capabilities(run.architecture, run.site_snapshot, renderer)
        run.application_spec = architecture_to_application_spec(run.project_brief, run.architecture, run.capability_resolutions)

        run.experience_spec = await self.agents.design(run.project_brief, run.architecture)
        run.experience_spec = reconcile_experience(run.project_brief, run.architecture, run.experience_spec)
        run.status = "specified"

        baseline = compile_build_plan(run.application_spec, run.experience_spec, run.site_snapshot, renderer)
        advisory = await self.agents.build({
            "pages": [{"slug": p.slug} for p in run.architecture.pages],
            "deterministic_actions": [a.ability for a in baseline.actions],
            "instruction": "Only missing advisory actions; do not duplicate deterministic actions.",
        })
        run.build_plan = merge_advisory_actions(baseline, advisory)
        has_pending, batch_snapshot = await self._execute_actions_staged(
            run, run.build_plan.actions, AgentRole.BUILDER, run.site_snapshot,
            attempt=1, progress_start=50, progress_end=75
        )
        run.status = "built"
        run.verification_snapshot = batch_snapshot or run.site_snapshot

        bundle = {
            "project_brief": run.project_brief.model_dump(mode="json"),
            "architecture": run.architecture.model_dump(mode="json"),
            "application_spec": run.application_spec.model_dump(mode="json"),
            "experience_spec": run.experience_spec.model_dump(mode="json"),
            "build_plan": run.build_plan.model_dump(mode="json"),
            "renderer": renderer,
            "usage": self.agents.usage.model_dump(mode="json"),
        }
        verifier = PullPlanningWorkflow(self.settings, self.agents)
        verification = await verifier.verify(
            bundle=bundle,
            executions=[x.model_dump(mode="json") for x in run.executions],
            verification_snapshot=run.verification_snapshot,
            repair_attempts=0,
        )
        report = QualityReport.model_validate(verification["quality_report"])
        run.quality_reports.append(report)

        if not report.passed and not has_pending and verification.get("repair_actions") and self.settings.max_repair_loops > 0:
            run.repair_attempts = 1
            repair_actions = [BuildAction.model_validate(item["action"]) for item in verification["repair_actions"]]
            _, repair_snapshot = await self._execute_actions_staged(
                run, repair_actions, AgentRole.BUILDER, run.verification_snapshot,
                attempt=2, progress_start=88, progress_end=96
            )
            if repair_snapshot is not None:
                run.verification_snapshot = repair_snapshot
            verification = await verifier.verify(
                bundle=bundle,
                executions=[x.model_dump(mode="json") for x in run.executions],
                verification_snapshot=run.verification_snapshot,
                repair_attempts=1,
            )
            report = QualityReport.model_validate(verification["quality_report"])
            run.quality_reports.append(report)

        run.status = "needs_approval" if has_pending else ("passed" if report.passed else "failed")
        run.usage = self.agents.usage
        self._save(run)
        await self._progress("completed", 100, f"Build finished with status: {run.status}")
        return run

