"""v0.9.0 offline regression suite; never calls an OpenAI API."""
import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.agents.runtime import MockAgentRuntime, site_design_profile
from app.component_library import compile_elementor_page
from app.config import Settings
from app.content_quality import audit_experience
from app.editorial_repair import repair_duplicate_headings
from app.generative_design import validate_creative_layout
from app.models import (
    CreativeDirection, DesignSystem, ExperienceSpec, GenerativeDesignSpec,
    PageExperienceSpec, PageLayoutSpec, SectionContentSpec, SectionLayoutSpec,
    SeoSpec, SiteSnapshot,
)
from app.pull_workflow import PullPlanningWorkflow


def section(kind, title, body):
    return SectionContentSpec(section_type=kind, heading=title, body=body)


def page(slug, title, sections):
    return PageExperienceSpec(page_name=title, page_slug=slug, page_goal=title,
        sections=[s.section_type for s in sections], section_specs=sections,
        seo=SeoSpec(slug=f"/{slug}/", title=title,
            meta_description="Виберіть спосіб звернутися або переглянути асортимент.", h1=sections[0].heading))


def concepts():
    return [
        CreativeDirection(id="gallery", name="Gallery letterform", narrative="Editorial gallery with confident white space and expressive punctuation.",
            composition="Large visual followed by narrow text blocks", typographic_contrast="Expressive serif and minimal sans", visual_motif="Fine circular linework"),
        CreativeDirection(id="rhythm", name="Asymmetric catalogue", narrative="Measured asymmetry that uses flexible negative space to guide exploration.",
            composition="Compact grids offset against long headings", typographic_contrast="Monospace captions and bold headlines", visual_motif="Linear graphic framework"),
    ]


def creative(layouts, selected="gallery"):
    return GenerativeDesignSpec(candidates=concepts(), selected_direction_id=selected,
        selection_reason="This concept distinguishes navigation, introduction and collections.", page_layouts=layouts)


def sample_experience():
    return ExperienceSpec(design_direction="Editorial", design_system=DesignSystem(primary="#253A52",accent="#DFA75E"), pages=[
        page("home", "Головна", [
            section("hero", "Шоколадні подарунки з характером", "Обирайте набори для подарунку або події, яка варта вашої уваги."),
            section("products", "Асортимент для різних нагод", "Перегляньте формати наборів у магазині перед тим, як зробити вибір."),
            section("cta", "Відкрийте колекції", "Перегляньте доступні варіанти та поставте запитання перед покупкою."),
        ]),
        page("shop", "Магазин", [
            section("hero", "Магазин шоколадних наборів", "Дізнайтеся, які формати зручніше обрати для подарунка."),
            section("products", "Варіанти наборів", "Уточніть склад та алергени конкретного набору перед замовленням."),
        ]),
        page("contact", "Контакти", [
            section("hero", "Поставте нам запитання", "Напишіть нам, якщо потрібно уточнити інформацію про набори."),
        ]),
    ])


def walk(nodes):
    for item in nodes:
        yield item
        yield from walk(item.get("elements", []))


def test_duplicate_headings_four_times_in_home_and_shop_fixed_before_gate():
    exp = sample_experience()
    pages = []
    for p in exp.pages:
        if p.page_slug in ("home", "shop"):
            # Reproduces the 0.8.5 incident after repeated fallback headings.
            secs = [s.model_copy(update={"heading": "Колекції шоколаду"}) for s in p.section_specs]
            p = p.model_copy(update={"section_specs": secs})
        pages.append(p)
    exp = exp.model_copy(update={"pages": pages})
    assert sum(x.code == "duplicate_heading" for x in audit_experience(exp)) == 3
    assert any(x.code == "repeated_site_heading" for x in audit_experience(exp))
    repaired, notes = repair_duplicate_headings(exp)
    assert len(notes) == 4
    assert not [i for i in audit_experience(repaired) if i.code in {"duplicate_heading", "repeated_site_heading"}]
    assert repaired.pages[0].seo.h1 == repaired.pages[0].section_specs[0].heading
    assert sum(n.section_index == 0 for n in notes) == 1
    assert [s.heading for s in repaired.pages[0].section_specs] != [s.heading for s in repaired.pages[1].section_specs]


def test_gate_keeps_unsafe_cta_blocked_after_heading_repair():
    exp = sample_experience()
    sec = exp.pages[0].section_specs[1].model_copy(update={"heading": exp.pages[0].section_specs[0].heading,
                                                  "cta_label": "Get it", "cta_url": "javascript:alert(1)"})
    p = exp.pages[0].model_copy(update={"section_specs": [exp.pages[0].section_specs[0],sec,*exp.pages[0].section_specs[2:]]})
    after, notes = repair_duplicate_headings(exp.model_copy(update={"pages": [p,*exp.pages[1:]]}))
    assert notes
    assert "unsafe_cta" in {issue.code for issue in audit_experience(after)}


def test_creative_spec_rejects_arbitrary_css_js_and_invalid_geometry():
    with pytest.raises(ValidationError):
        SectionLayoutSpec.model_validate({"section_index": 0, "composition": "split", "custom_css": "@import url(https://evil.test)"})
    with pytest.raises(ValidationError):
        SectionLayoutSpec(section_index=0, text_width_pct=99)
    with pytest.raises(ValidationError):
        SectionLayoutSpec(section_index=0, motif="<script>alert(1)</script>")


def test_creative_spec_rejects_unknown_selected_and_out_of_bounds_section():
    exp = sample_experience()
    good = PageLayoutSpec(page_slug="home", sections=[SectionLayoutSpec(section_index=0)])
    exp = exp.model_copy(update={"generative_design": creative([good], selected="missing")})
    with pytest.raises(ValueError, match="selected"):
        validate_creative_layout(exp, required=True)
    exp = exp.model_copy(update={"generative_design": creative([
        PageLayoutSpec(page_slug="home", sections=[SectionLayoutSpec(section_index=10)])
    ])})
    # An in-schema value that is larger than the actual page still fails before deployment.
    exp.generative_design.page_layouts[0].sections[0] = SectionLayoutSpec(section_index=10)
    with pytest.raises(ValueError, match="out of bounds"):
        validate_creative_layout(exp, required=True)


def test_layout_compiles_two_original_compositions_without_losing_editability():
    exp = sample_experience()
    p = exp.pages[0]
    gallery = PageLayoutSpec(page_slug="home", sections=[
        SectionLayoutSpec(section_index=0, composition="stacked", art_ratio="wide", motif="frame", heading_emphasis="dramatic"),
        SectionLayoutSpec(section_index=1, composition="offset", card_columns=2, vertical_space=96),
    ])
    asymmetric = PageLayoutSpec(page_slug="home", sections=[
        SectionLayoutSpec(section_index=0, composition="split", media_position="start", text_width_pct=40, motif="lines"),
        SectionLayoutSpec(section_index=1, composition="centered", card_columns=4, vertical_space=64),
    ])
    a = compile_elementor_page(p, exp.design_system, layout=gallery)
    b = compile_elementor_page(p, exp.design_system, layout=asymmetric)
    assert a[0]["id"] == b[0]["id"]  # Stable AI-owned section for targeted repair.
    assert a[0]["settings"]["css_classes"] != b[0]["settings"]["css_classes"]
    assert "tai-layout-stacked" in a[0]["settings"]["css_classes"]
    assert "tai-layout-split" in b[0]["settings"]["css_classes"]
    assert "tai-split-40" in b[0]["settings"]["css_classes"]
    assert all(x["elType"] in {"container", "widget"} for x in walk(a))
    assert all(x["widgetType"] in {"heading", "text-editor", "image", "button", "shortcode"}
               for x in walk(a) if x["elType"] == "widget")
    for design in (a, b):
        titles = [x["settings"]["title"] for x in walk(design) if x.get("widgetType") == "heading"]
        assert p.section_specs[0].heading in titles
        assert p.section_specs[1].heading in titles
    assert p.section_specs[0].heading not in str(a[0]["settings"])  # geometry never stores visitor copy


def test_new_generated_design_preserves_creative_director_palette():
    exp = sample_experience()
    assert site_design_profile("Шоколад", exp.design_system).primary != exp.design_system.primary
    from app.agents.runtime import compile_build_plan
    from app.models import ApplicationSpec, PageRequirement
    app = ApplicationSpec(site_type="ecommerce", site_title="Fortuna Nova", goals=["Каталог"],
        pages=[PageRequirement(name="Головна", slug="home", purpose="Представити")], features=[])
    exp = exp.model_copy(update={"generative_design": creative([
        PageLayoutSpec(page_slug="home", sections=[SectionLayoutSpec(section_index=0)])
    ])})
    plan = compile_build_plan(app, exp, SiteSnapshot(site_info={"theme_slug":"hello-elementor"},structure={"active_theme_slug":"hello-elementor"}),
                              "elementor", "Шоколадні набори")
    design_action = next(x for x in plan.actions if x.ability.endswith("apply-site-design"))
    assert design_action.parameters["primary"] == "#253A52"


def test_three_page_mock_plan_keeps_shop_untouched_and_has_creative_artifacts():
    snapshot = SiteSnapshot(site_info={"name":"Fortuna Nova", "theme_slug":"hello-elementor"},
        plugins=[{"slug":"elementor","active":True},{"slug":"woocommerce","active":True}],
        structure={"active_theme_slug":"hello-elementor"},
        pages=[{"id":11,"slug":"shop","status":"publish","ai_generated":False}])
    request = "Створи магазин шоколадних цукерок Fortuna Nova. Сторінки Головна, Магазин, Контакти. Товари «Асорті 16 цукерок» та «Асорті 24 цукерки»."
    result = asyncio.run(PullPlanningWorkflow(Settings(agent_mode="mock", auto_approve_medium_risk=True), MockAgentRuntime()).plan(request,"elementor",snapshot))
    assert result["content_quality"]["passed"]
    assert result["creative_direction"] is not None
    assert len(result["experience_spec"]["generative_design"]["candidates"]) >= 2
    actions = result["build_plan"]["actions"]
    assert not any(a["parameters"].get("slug") == "shop" and a["ability"].endswith("ensure-draft-page") for a in actions)
    home = next(a for a in actions if a["ability"].endswith("elementor-ensure-draft-page") and a["parameters"].get("slug") == "home")
    assert "tai-generative" in home["parameters"]["elements"][0]["settings"]["css_classes"]
    assert result["usage"]["requests"] == 0


def test_generatively_scoped_css_and_readable_mobile_rules_exist():
    css = (Path(__file__).parents[2] / "plugin" / "thesis-ai-bridge" / "assets" / "front.css").read_text()
    assert "body.thesis-ai-generated .elementor .tai-generative" in css
    assert ".tai-layout-centered" in css and ".tai-media-start" in css
    assert "@media(max-width:767px)" in css
    assert "max-width:100%;text-wrap:balance" in css
