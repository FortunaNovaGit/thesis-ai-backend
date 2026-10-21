import asyncio

from app.agents.runtime import MockAgentRuntime
from app.config import Settings
from app.models import SiteSnapshot
from app.pull_workflow import PullPlanningWorkflow


def _snapshot():
    return SiteSnapshot(
        site_info={"name": "Test", "theme_slug": "hello-elementor"},
        pages=[],
        plugins=[{"slug": "elementor", "active": True}],
        themes=[{"slug": "hello-elementor", "active": True}],
        capabilities={
            "recognized_capabilities": {"page_builder_elementor": True},
            "approved_plugins": {"elementor": {"installed": True, "active": True}},
        },
        structure={"homepage_slug": ""},
    )


def test_v072_dental_artifacts_are_visitor_facing_and_actionable():
    settings = Settings(agent_mode="mock", auto_approve_medium_risk=True)
    bundle = asyncio.run(
        PullPlanningWorkflow(settings, MockAgentRuntime()).plan(
            "Створи сайт стоматології з послугами та формою запису",
            "elementor",
            _snapshot(),
        )
    )
    pages = {p["page_slug"]: p for p in bundle["experience_spec"]["pages"]}
    assert {"home", "services", "contact"}.issubset(pages)

    forbidden = ("ця сторінка", "сторінка має", "контент секції", "надати канал", "сформувати довіру")
    for page in pages.values():
        headings = [s["heading"].strip().casefold() for s in page["section_specs"]]
        assert len(headings) == len(set(headings))
        rendered_copy = " ".join(
            f'{s.get("heading", "")} {s.get("body", "")}' for s in page["section_specs"]
        ).casefold()
        assert not any(marker in rendered_copy for marker in forbidden)

    assert any(s.get("cta_label") for s in pages["home"]["section_specs"])
    assert any(s["section_type"] == "booking" for s in pages["contact"]["section_specs"])

    abilities = [x["action"]["ability"] for x in bundle["approved_actions"]]
    assert "thesis-ai-bridge/apply-site-design" in abilities


def test_builder_llm_review_is_disabled_by_default():
    settings = Settings()
    assert settings.enable_builder_llm_review is False
