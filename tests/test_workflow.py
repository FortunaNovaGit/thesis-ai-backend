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
    assert any(x.action.ability == "thesis-ai-bridge/ensure-draft-page" for x in result.executions)


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
    result = asyncio.run(workflow.run("Створи магазин на WooCommerce"))
    assert result.status == "passed"
    assert "woocommerce" in executor.plugins
    assert executor.plugins["woocommerce"]["active"] is True
