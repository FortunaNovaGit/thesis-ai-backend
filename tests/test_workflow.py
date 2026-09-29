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
    assert any(x.action.ability == "thesis-ai-bridge/list-plugins" for x in result.executions)


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
