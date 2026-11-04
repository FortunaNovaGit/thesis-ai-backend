"""v0.9.1 release regressions. Fully offline: no requests and no OpenAI charges."""
import asyncio
import sys
import types
from unittest.mock import patch

import pytest

from app.agents.prompts import (
    architect_prompt, builder_prompt, design_prompt, orchestrator_prompt,
    quality_prompt, repair_prompt,
)
from app.agents.runtime import MockAgentRuntime, OpenAIAgentRuntime, reconcile_experience
from app.budget import BudgetLimits
from app.component_library import _readable_ink, compile_elementor_page
from app.content_quality import audit_experience
from app.editorial_repair import repair_duplicate_headings
from app.models import (
    ArchitectureBundle, CreativeDirection, DesignSystem, ExperienceSpec,
    GenerativeDesignSpec, PageExperienceSpec, PageIntent, PageLayoutSpec,
    ProjectBrief, SectionContentSpec, SectionLayoutSpec, SeoSpec,
)


def _walk(nodes):
    for node in nodes:
        yield node
        yield from _walk(node.get("elements", []))


def _fixture():
    sections = [
        SectionContentSpec(section_type="hero", heading="Неочікуваний погляд на шоколад",
            eyebrow="FORTUNA NOVA", body="Відкрийте набори для теплих зустрічей і невеликих подарунків.",
            cta_label="Переглянути колекції", cta_url="/shop/"),
        SectionContentSpec(section_type="benefits", heading="Теплі нагоди для солодких історій",
            body="Для подій, яких чекають, і зустрічей, що залишаються у пам'яті.",
            items=["Для друзів — маленька увага для близьких", "Для сім'ї — ідея до домашньої зустрічі", "Для себе — тепла пауза у дні"]),
        SectionContentSpec(section_type="cta", heading="Обрати набір до нагоди",
            body="Перегляньте формат, а деталі конкретного виробу уточніть перед замовленням.",
            cta_label="До магазину", cta_url="/shop/"),
    ]
    page = PageExperienceSpec(page_name="Головна", page_slug="home", page_goal="Вибір набору",
        sections=[x.section_type for x in sections], section_specs=sections,
        seo=SeoSpec(slug="/", title="Fortuna Nova", meta_description="Знайдіть подарункові набори для особливих нагод.", h1=sections[0].heading))
    creative = GenerativeDesignSpec(candidates=[
        CreativeDirection(id="type", name="Typographic gesture", narrative="Typography creates hierarchy and a gentle reading rhythm.", composition="One confident letterform-led opening", typographic_contrast="Large serif with compact captions", visual_motif="Fine line work"),
        CreativeDirection(id="editorial", name="Editorial collection", narrative="A magazine-like reading progression through selected collections.", composition="Quiet opening with an asymmetric card grid", typographic_contrast="Restrained italic and bold headings", visual_motif="Measured ornamental framing"),
    ], selected_direction_id="type", selection_reason="A typographic cover avoids unverified product photographs.",
        page_layouts=[PageLayoutSpec(page_slug="home", sections=[
            SectionLayoutSpec(section_index=0, visual_treatment="typography", content_alignment="center", accent_detail="rule"),
            SectionLayoutSpec(section_index=1, card_presentation="bento", surface_treatment="tinted", card_columns=2, accent_detail="index"),
            SectionLayoutSpec(section_index=2, content_alignment="center", surface_treatment="bordered"),
        ])])
    return ExperienceSpec(design_direction="Editorial", design_system=DesignSystem(),
                          pages=[page], generative_design=creative)


def test_all_agent_prompts_evaluate_without_runtime_name_errors():
    # Regression for 0.9.0 design_prompt f-string: generative_design{candidates,...}
    for make in (orchestrator_prompt, architect_prompt, design_prompt, builder_prompt, quality_prompt, repair_prompt):
        prompt = make()
        assert isinstance(prompt, str) and len(prompt) > 200
    assert "generative_design{candidates," in design_prompt()
    assert "card_presentation" in design_prompt()


def test_openai_runtime_constructs_all_six_role_configs_without_api():
    fake_sdk = types.SimpleNamespace(Agent=lambda **kwargs: types.SimpleNamespace(**kwargs))
    router = {name:"offline-model" for name in ("orchestrator", "architect", "design", "builder", "quality", "repair")}
    with patch.dict(sys.modules, {"agents":fake_sdk}):
        runtime = OpenAIAgentRuntime(router, BudgetLimits(.25,10000,7))
    assert set(runtime.agents) == set(router)
    assert "Creative Director" in runtime.agents["design"].instructions
    assert runtime.usage.total_tokens == 0


def test_generated_design_renders_a_native_typographic_hero_and_bento_layout():
    spec = _fixture(); page = spec.pages[0]
    native = compile_elementor_page(page, spec.design_system, layout=spec.generative_design.page_layouts[0])
    assert len(native)==3
    assert "tai-visual-typography" in native[0]["settings"]["css_classes"]
    assert "tai-presentation-bento" in native[1]["settings"]["css_classes"]
    assert "tai-surface-tinted" in native[1]["settings"]["css_classes"]
    nodes = list(_walk(native))
    assert not any("tai-hero-art" in n.get("settings", {}).get("css_classes", "") for n in nodes)
    h1 = [n for n in nodes if n.get("widgetType")=="heading" and n["settings"].get("header_size")=="h1"]
    assert len(h1)==1 and "Неочікуваний погляд" in h1[0]["settings"]["title"]
    assert all(n["elType"] in {"widget","container"} for n in nodes)
    assert all("<script" not in str(n) for n in nodes)


def test_original_heading_is_preserved_when_it_is_not_repeated():
    exp = _fixture()
    brief = ProjectBrief(site_type="ecommerce", primary_goal="Крамниця шоколаду",requested_pages=["Головна"])
    architecture = ArchitectureBundle(site_title="Fortuna Nova",pages=[
        PageIntent(name="Головна",slug="home",purpose="Знайомство і колекції",section_goals=["hero","benefits","cta"]),
    ])
    after = reconcile_experience(brief,architecture,exp)
    assert after.pages[0].section_specs[0].heading == "Неочікуваний погляд на шоколад"
    assert after.pages[0].section_specs[1].heading == "Теплі нагоди для солодких історій"
    repaired, notes = repair_duplicate_headings(after)
    assert notes==[]
    assert not audit_experience(repaired)


def test_contrast_aware_buttons_do_not_always_assume_white_ink():
    assert _readable_ink("#FBEAD0")=="#101015"
    assert _readable_ink("#1B1327")=="#FFFFFF"


def test_design_primitives_are_strict_and_do_not_accept_custom_css():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        SectionLayoutSpec.model_validate({"section_index":0,"surface_treatment":"url(javascript:evil)"})
    with pytest.raises(ValidationError):
        SectionLayoutSpec.model_validate({"section_index":0,"unknown_css":"body{display:none}"})
