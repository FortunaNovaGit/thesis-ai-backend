import asyncio

from app.agents.runtime import MockAgentRuntime
from app.config import Settings
from app.models import SiteSnapshot
from app.pull_workflow import PullPlanningWorkflow
from app.tools.wordpress import MockWordPressExecutor
from app.models import BuildAction


def _empty_snapshot():
    return SiteSnapshot(
        site_info={"name": "Test", "theme_slug": "mock-theme"},
        pages=[],
        plugins=[],
        themes=[{"slug": "mock-theme", "active": True}],
        capabilities={"recognized_capabilities": {}, "approved_plugins": {}},
        structure={"homepage_slug": ""},
    )


def test_pull_plan_contains_local_wordpress_actions():
    settings = Settings(agent_mode="mock", auto_approve_medium_risk=True)
    agents = MockAgentRuntime()
    workflow = PullPlanningWorkflow(settings, agents)
    bundle = asyncio.run(workflow.plan(
        "Створи сайт стоматології з послугами, лікарями та формою запису",
        "elementor",
        _empty_snapshot(),
    ))
    abilities = [item["action"]["ability"] for item in bundle["approved_actions"]]
    assert "thesis-ai-bridge/ensure-approved-plugin" in abilities
    assert "thesis-ai-bridge/elementor-ensure-draft-page" in abilities
    assert "thesis-ai-bridge/ensure-navigation-menu" in abilities
    assert bundle["blocked_actions"] == []


def test_pull_verify_passes_after_local_execution():
    settings = Settings(agent_mode="mock", auto_approve_medium_risk=True, max_repair_loops=2)
    agents = MockAgentRuntime()
    workflow = PullPlanningWorkflow(settings, agents)
    initial = _empty_snapshot()
    bundle = asyncio.run(workflow.plan("Створи простий сайт стоматології", "elementor", initial))

    executor = MockWordPressExecutor()
    executions = []
    for item in bundle["approved_actions"]:
        action = BuildAction.model_validate(item["action"])
        try:
            result = asyncio.run(executor.execute(action))
            executions.append({"action": item["action"], "policy": item["policy"], "executed": True, "result": result, "error": None, "attempt": 1})
        except Exception as exc:
            executions.append({"action": item["action"], "policy": item["policy"], "executed": False, "result": None, "error": str(exc), "attempt": 1})

    snapshot_raw = asyncio.run(executor.execute(BuildAction(
        ability="thesis-ai-bridge/get-site-snapshot", parameters={}, rationale="verify"
    )))
    result = asyncio.run(workflow.verify(
        bundle=bundle,
        executions=executions,
        verification_snapshot=SiteSnapshot.model_validate(snapshot_raw),
        repair_attempts=0,
    ))
    assert result["quality_report"]["passed"] is True
    assert result["repair_actions"] == []

def test_pull_shop_plan_includes_woocommerce_configuration():
    settings = Settings(agent_mode="mock", auto_approve_medium_risk=True)
    workflow = PullPlanningWorkflow(settings, MockAgentRuntime())
    bundle = asyncio.run(workflow.plan("Створи сучасний інтернет-магазин на WooCommerce", "elementor", _empty_snapshot()))
    abilities = [item["action"]["ability"] for item in bundle["approved_actions"]]
    assert "thesis-ai-bridge/ensure-approved-plugin" in abilities
    assert "thesis-ai-bridge/configure-woocommerce" in abilities
