import asyncio
import pytest
from app.agents.runtime import MockAgentRuntime
from app.component_library import choose_page_media, compile_elementor_page
from app.config import Settings
from app.models import DesignSystem, PageExperienceSpec, SectionContentSpec, SeoSpec, SiteSnapshot
from app.pull_workflow import PullPlanningWorkflow


def page():
    return PageExperienceSpec(
        page_name="Магазин", page_slug="shop", page_goal="Продати шоколадні цукерки",
        sections=["hero", "products", "cta"],
        seo=SeoSpec(slug="shop", title="Магазин", meta_description="Каталог шоколадних цукерок", h1="Магазин"),
        section_specs=[
            SectionContentSpec(section_type="hero", heading="Магазин", body="Шоколадні цукерки ручної роботи", cta_label="Переглянути", cta_url="/shop/"),
            SectionContentSpec(section_type="products", heading="Магазин", items=["Асорті 16: натуральний шоколад"]),
            SectionContentSpec(section_type="cta", heading="Магазин", cta_label="Замовити", cta_url="/contact/"),
        ],
    )


def walk(elements):
    for element in elements:
        yield element
        yield from walk(element.get("elements", []))


def test_contract_blocks_old_bridge_before_agent_requests():
    runtime = MockAgentRuntime()
    wf = PullPlanningWorkflow(Settings(agent_mode="mock"), runtime)
    snap = SiteSnapshot(site_info={"bridge_version": "0.7.2"})
    with pytest.raises(RuntimeError, match="upgrade WordPress Bridge"):
        asyncio.run(wf.plan("Створи сайт шоколадного магазину", "elementor", snap))


def test_missing_ability_detected():
    snap = SiteSnapshot(site_info={"bridge_version": "0.8.0"}, bridge_contract={"abilities": ["get-site-snapshot"]})
    with pytest.raises(RuntimeError, match="apply-site-design"):
        PullPlanningWorkflow._validate_bridge_contract(snap, "elementor")


def test_media_is_only_used_if_related_and_on_site():
    p = page()
    media = [{"id": 23, "url": "https://shop.example/wp-content/uploads/chocolates.jpg", "alt": "шоколадні цукерки подарунок"}]
    assert choose_page_media(p, media)["id"] == 23
    assert choose_page_media(p, [{"id": 44, "url": "http://insecure/photo.jpg", "alt": "шоколадні"}]) is None


def test_hero_is_editable_and_no_repeated_heading_or_false_products():
    p=page(); ds=DesignSystem()
    elements=compile_elementor_page(p, ds)
    widgets=list(walk(elements))
    h=[i["settings"]["title"] for i in widgets if i.get("widgetType")=="heading" and i["settings"].get("header_size") in {"h1", "h2"}]
    assert len(h)==len(set(h))
    assert len([i for i in widgets if i.get("widgetType")=="heading" and i["settings"].get("header_size")=="h1"])==1
    assert not any(i.get("widgetType")=="shortcode" and "[products" in i["settings"]["shortcode"] for i in widgets)
    live=compile_elementor_page(p, ds, live_catalog=True)
    assert any(i.get("widgetType")=="shortcode" and "[products" in i["settings"]["shortcode"] for i in walk(live))
