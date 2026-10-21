import asyncio

from app.agents.runtime import MockAgentRuntime
from app.budget import BudgetLimits, BudgetTracker, estimate_cost
from app.capabilities import resolve_capabilities
from app.models import ArchitectureBundle, CapabilityRequirement, PageIntent, SiteSnapshot
from app.pull_workflow import PullPlanningWorkflow
from app.config import Settings


def _snapshot(active_plugins=None):
    active_plugins = active_plugins or []
    return SiteSnapshot(
        site_info={"name": "Test", "theme_slug": "hello-elementor"},
        pages=[],
        plugins=[{"slug": slug, "active": True} for slug in active_plugins],
        themes=[{"slug": "hello-elementor", "active": True}],
        capabilities={"recognized_capabilities": {}},
        structure={"homepage_slug": "", "active_theme_slug": "hello-elementor"},
    )


def test_capability_resolver_maps_semantics_to_approved_plugins_only():
    arch = ArchitectureBundle(
        site_title="Test",
        pages=[PageIntent(name="Home", slug="home", purpose="Convert")],
        capabilities=[
            CapabilityRequirement(capability="forms", reason="Need form"),
            CapabilityRequirement(capability="seo", reason="Need metadata"),
            CapabilityRequirement(capability="page_builder_elementor", reason="Renderer"),
        ],
    )
    result = resolve_capabilities(arch, _snapshot(), "elementor")
    mapped = {x.capability: x.plugin_slug for x in result}
    assert mapped["forms"] == "contact-form-7"
    assert mapped["page_builder_elementor"] == "elementor"
    assert mapped["seo"] is None
    assert all(x.plugin_slug != "random-ai-seo" for x in result)


def test_existing_plugin_is_reused_not_reinstalled():
    arch = ArchitectureBundle(
        site_title="Test",
        pages=[PageIntent(name="Home", slug="home", purpose="Convert")],
        capabilities=[CapabilityRequirement(capability="forms", reason="Need form")],
    )
    result = resolve_capabilities(arch, _snapshot(["contact-form-7", "elementor"]), "elementor")
    forms = next(x for x in result if x.capability == "forms")
    assert forms.source == "existing_plugin"
    assert forms.action == "reuse"


def test_artifact_pipeline_has_content_matrix_and_unique_pages():
    settings = Settings(agent_mode="mock", max_repair_loops=1)
    workflow = PullPlanningWorkflow(settings, MockAgentRuntime())
    bundle = asyncio.run(workflow.plan(
        "Створи сайт стоматології з послугами, лікарями, контактами та формою запису",
        "elementor",
        _snapshot(),
    ))
    pages = bundle["architecture"]["pages"]
    slugs = [p["slug"] for p in pages]
    assert len(slugs) == len(set(slugs))
    assert "home" in slugs
    assert len(bundle["content_matrix"]) == len(pages)
    assert bundle["architecture_version"] == "artifact_pipeline_v3_visual"
    assert bundle["project_brief"]["primary_goal"]


def test_cost_estimate_and_budget_tracker():
    assert estimate_cost("gpt-5.6-luna", 1_000_000, 1_000_000) == 1.4
    tracker = BudgetTracker(BudgetLimits(0.5, 30_000, 10))
    tracker.record("QA", "gpt-5.6-luna", 1, 1000, 500)
    state = tracker.state()
    assert state.used_llm_calls == 1
    assert state.used_total_tokens == 1500
    assert 0 < state.used_cost_usd < 0.01
