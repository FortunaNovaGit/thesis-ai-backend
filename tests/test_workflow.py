import asyncio
from pathlib import Path

from app.agents.runtime import MockAgentRuntime
from app.config import Settings
from app.models import BuildAction
from app.tools.wordpress import MockWordPressExecutor
from app.workflow import MultiAgentWorkflow


def test_mock_workflow_passes(tmp_path: Path):
    settings = Settings(agent_mode="mock", wordpress_mode="mock", auto_approve_medium_risk=True)
    executor = MockWordPressExecutor()
    workflow = MultiAgentWorkflow(settings, MockAgentRuntime(), executor, tmp_path)
    result = asyncio.run(workflow.run("Створи простий сайт стоматології"))
    assert result.status == "passed"
    assert result.application_spec is not None
    assert result.experience_spec is not None
    assert any(x.executed for x in result.executions)
    assert any(x.action.ability == "thesis-ai-bridge/elementor-ensure-draft-page" for x in result.executions)
    assert result.site_snapshot is not None
    assert any(x.action.ability == "thesis-ai-bridge/get-site-snapshot" for x in result.executions)


def test_ensure_draft_page_is_rerunnable():
    executor = MockWordPressExecutor()
    action = BuildAction(
        ability="thesis-ai-bridge/ensure-draft-page",
        parameters={"title": "Home", "slug": "home", "content": "first"},
        rationale="test",
    )
    first = asyncio.run(executor.execute(action))
    action.parameters["content"] = "second"
    second = asyncio.run(executor.execute(action))
    assert first["created"] is True
    assert second["created"] is False
    assert second["id"] == first["id"]
    assert second["content"] == "second"


def test_mock_shop_installs_only_approved_woocommerce(tmp_path: Path):
    settings = Settings(agent_mode="mock", wordpress_mode="mock", auto_approve_medium_risk=True)
    executor = MockWordPressExecutor()
    workflow = MultiAgentWorkflow(settings, MockAgentRuntime(), executor, tmp_path)
    result = asyncio.run(workflow.run("Створи магазин на WooCommerce", "elementor"))
    assert result.status == "passed"
    assert "woocommerce" in executor.plugins
    assert executor.plugins["woocommerce"]["active"] is True
    assert "elementor" in executor.plugins
    assert executor.plugins["elementor"]["active"] is True


def test_mock_booking_site_installs_form_theme_and_site_structure(tmp_path: Path):
    settings = Settings(agent_mode="mock", wordpress_mode="mock", auto_approve_medium_risk=True)
    executor = MockWordPressExecutor()
    workflow = MultiAgentWorkflow(settings, MockAgentRuntime(), executor, tmp_path)
    result = asyncio.run(
        workflow.run(
            "Створи сайт стоматології з послугами, лікарями та формою запису",
            "elementor",
        )
    )
    assert result.status == "passed"
    assert executor.plugins["elementor"]["active"] is True
    assert executor.plugins["contact-form-7"]["active"] is True
    assert executor.themes["hello-elementor"]["active"] is True
    assert executor.homepage_id is not None
    assert executor.site_title == "Стоматологічна клініка"
    assert "home" in executor.menu
    abilities = [x.action.ability for x in result.executions if x.executed]
    assert "thesis-ai-bridge/ensure-contact-form" in abilities
    assert "thesis-ai-bridge/update-site-identity" in abilities
    assert "thesis-ai-bridge/ensure-navigation-menu" in abilities
    assert "thesis-ai-bridge/set-homepage-by-slug" in abilities
    assert result.verification_snapshot is not None
    assert result.verification_snapshot.structure.get("homepage_slug") == "home"

class FlakyPageExecutor(MockWordPressExecutor):
    def __init__(self):
        super().__init__()
        self.failed_once = False

    async def execute(self, action):
        if action.ability == "thesis-ai-bridge/elementor-ensure-draft-page" and action.parameters.get("slug") == "home" and not self.failed_once:
            self.failed_once = True
            raise RuntimeError("Transient page creation failure")
        return await super().execute(action)


def test_repair_success_overrides_historical_failure(tmp_path: Path):
    settings = Settings(agent_mode="mock", wordpress_mode="mock", auto_approve_medium_risk=True, max_repair_loops=2, transient_action_retries=0)
    executor = FlakyPageExecutor()
    workflow = MultiAgentWorkflow(settings, MockAgentRuntime(), executor, tmp_path)
    result = asyncio.run(workflow.run("Створи простий сайт стоматології"))
    assert result.status == "passed"
    assert result.repair_attempts >= 1
    home_attempts = [x for x in result.executions if x.action.ability == "thesis-ai-bridge/elementor-ensure-draft-page" and x.action.parameters.get("slug") == "home"]
    assert any(not x.executed for x in home_attempts)
    assert home_attempts[-1].executed is True

class CountingBatchExecutor(MockWordPressExecutor):
    def __init__(self):
        super().__init__()
        self.batch_calls = 0
        self.snapshot_calls = 0

    async def execute(self, action):
        if action.ability == "thesis-ai-bridge/get-site-snapshot":
            self.snapshot_calls += 1
        return await super().execute(action)

    async def execute_batch(self, actions, *, include_snapshot=True):
        self.batch_calls += 1
        return await super().execute_batch(actions, include_snapshot=include_snapshot)


def test_workflow_uses_batches_and_no_extra_verification_request(tmp_path: Path):
    settings = Settings(
        agent_mode="mock",
        wordpress_mode="mock",
        auto_approve_medium_risk=True,
        wordpress_batch_size=50,
        max_repair_loops=0,
    )
    executor = CountingBatchExecutor()
    workflow = MultiAgentWorkflow(settings, MockAgentRuntime(), executor, tmp_path)
    result = asyncio.run(workflow.run("Створи простий сайт стоматології"))
    assert result.status == "passed"
    # One preflight snapshot, then two guarded phases: content and final site
    # assembly. The final assembly batch returns the verification snapshot, so
    # there is no third remote verification call.
    assert executor.batch_calls == 2
    assert executor.snapshot_calls == 2


def test_staged_execution_skips_preflight_satisfied_elementor_dependency(tmp_path: Path):
    settings = Settings(
        agent_mode="mock", wordpress_mode="mock", auto_approve_medium_risk=True,
        wordpress_batch_size=50, max_repair_loops=0,
    )
    executor = CountingBatchExecutor()
    executor.plugins["elementor"] = {
        "plugin_slug": "elementor", "plugin_file": "elementor/elementor.php",
        "installed": True, "active": True, "version": "3.x",
    }
    executor.themes["mock-theme"]["active"] = False
    executor.themes["hello-elementor"] = {"slug": "hello-elementor", "name": "Hello Elementor", "version": "1.0", "active": True}
    workflow = MultiAgentWorkflow(settings, MockAgentRuntime(), executor, tmp_path)
    result = asyncio.run(workflow.run("Створи простий сайт стоматології"))
    assert result.status == "passed"
    elementor_dep = [x for x in result.executions if x.action.ability == "thesis-ai-bridge/ensure-approved-plugin" and x.action.parameters.get("plugin_slug") == "elementor"]
    # Architect/capability resolution may prune the dependency entirely when the
    # preflight snapshot already proves Elementor is active. Either way there must
    # be no remote activation attempt.
    assert elementor_dep == []
