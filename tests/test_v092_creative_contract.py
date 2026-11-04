"""Offline regressions for the user's 0.9.1 12-field ExperienceSpec failure."""
import asyncio
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.agents.runtime import OpenAIAgentRuntime, _validate_agent_json
from app.budget import BudgetLimits, BudgetTracker
from app.component_library import compile_elementor_page
from app.content_quality import audit_experience
from app.creative_pipeline import CreativeFoundation, CreativePage, compose_experience
from app.design_safety import assert_design_palette, contrast
from app.generative_design import validate_creative_layout
from app.models import ArchitectureBundle, PageIntent, ProjectBrief, DesignSystem


def foundation_data():
    return {
        "design_direction": "Editorial serif typography and a quiet geometric rhythm",
        "design_system": {
            "primary": "#37241E", "accent": "#85623F", "background": "#FAF5EC",
            "surface": "#F0E8DC", "text": "#241C18", "muted": "#665650",
            "heading_font": "Georgia", "body_font": "Inter", "container_width": 1200,
            "section_spacing": 90, "radius": 14,
        },
        "candidates": [
            {"id":"editorial", "name":"Quiet editorial", "narrative":"Each page feels like a carefully typeset independent print story.", "composition":"Asymmetric chapters and unboxed typography", "typographic_contrast":"Bold serif against crisp restrained small labels", "visual_motif":"Fine warm rules"},
            {"id":"modern", "name":"Modern gallery", "narrative":"A modular gallery leads with people-first language and useful choices.", "composition":"Layered columns with generous whitespace", "typographic_contrast":"Clear sans-serif hierarchy with broad headings", "visual_motif":"Minimal circles and bold shapes"},
        ],
        "selected_direction_id":"editorial", "selection_reason":"A strong type system works without inventing product photography",
    }


def page_data(slug, kinds):
    stories = {
        "home": "Подарунки починаються з уваги до приводу: оберіть набір для зустрічі, свята чи теплого жесту. Знайдіть ідею, що відповідає вашому настрою.",
        "shop": "Порівняйте формати шоколадних наборів: кількість цукерок і зовнішній вигляд варто перевірити в описі. Перш ніж замовити, уточніть склад та наявність.",
        "contact": "Маєте запитання щодо замовлення або певного набору? Залиште звернення через форму, щоб уточнити асортимент чи інші деталі без зайвих здогадів.",
    }
    payload = {
        "page_slug": slug,
        "seo_title": f"Fortuna Nova — {slug} та шоколадні колекції",
        "meta_description": f"Fortuna Nova: {slug}. Перегляньте асортимент і знайдіть ідеї для подарунків, а деталі набору уточніть перед замовленням.",
        "sections": [
            {"kind": kind,
             "headline": f"{slug} — {kind}: рішення для особливої нагоди",
             "body": stories[slug] if kind == "hero" else (
                ("У магазині обирайте набори за форматом і сценарієм подарунка; перейдіть до каталогу, щоб побачити доступні картки." if slug == "shop" else
                 "На сторінці контактів можна залишити запитання, не розголошуючи зайвих деталей; повідомте, щодо якого набору потрібна відповідь." if slug == "contact" else
                 "Перейдіть до каталогу, щоб почати знайомство з наборами; порівнюйте пропозиції тільки за перевіреними описами.") if kind == "cta" else
                {"benefits":"Подарунок для близької людини, частування до зустрічі або невеликий знак уваги в будень — різні ситуації підказують власний формат вибору.",
                 "products":"У каталозі можна порівняти набори за їхнім форматом і оформленням. Звертайте увагу на опис конкретної позиції, а невідомі деталі уточнюйте перед оплатою.",
                 "contact":"Форма звернення допоможе поставити запитання про асортимент. Опишіть назву набору чи нагоду, щоб діалог почався із потрібного контексту."}.get(kind,
                {"home":"Перегляньте магазин, щоб знайти цікаві варіанти для подарунка. Відкрийте асортимент перед тим як визначити подальші деталі вибору.",
                 "shop":"Ознайомтеся з можливостями вибору наборів і скористайтеся контактною формою для уточнень щодо конкретного товару.",
                 "contact":"Опишіть своє запитання через контактну форму; назва набору й тема звернення допоможуть уникнути непотрібних уточнень."}[slug])
                + f" Розділ {slug} присвячено запитам про {kind}."),
             "items": ["Обрати нагоду — порівняйте доречні варіанти", "Уточнити деталі — поставте запитання перед замовленням", "Переглянути вибір — перейдіть до каталогу"],
             "cta_label": "Обрати набір" if kind in ("hero", "cta") else None,
             "cta_url": "/shop/" if kind in ("hero", "cta") else None,
             "composition": "centered" if i%2==0 else "offset",
             "visual_treatment": "typography", "surface_treatment": "canvas" if i%2==0 else "tinted",
             "card_presentation": "list" if kind=="process" else "bento"}
            for i, kind in enumerate(kinds)
        ],
    }

    # The original fixture accidentally repeated generic paragraphs across
    # architecture-expanded sections. Test real, page-specific visitor copy.
    context = {
        "home": "Насамперед подивіться на ідею подарунка та настрій події, а вже потім обирайте конкретний формат цукерок для себе чи близьких.",
        "shop": "Для порівняння пропозицій звертайте увагу на назву, формат та актуальний опис кожної позиції каталогу, а невідомі характеристики уточнюйте окремо.",
        "contact": "Щоб отримати точну відповідь, згадайте назву набору та опишіть своє питання у формі без надсилання конфіденційних платіжних реквізитів.",
    }
    for section in payload["sections"]:
        if section["kind"] != "hero":
            section["body"] += " " + context[slug]
    return payload


def architecture():
    return ArchitectureBundle(site_title="Fortuna Nova", pages=[
        PageIntent(name="Головна", slug="home", purpose="Перше знайомство", section_goals=["hero", "benefits", "cta"]),
        PageIntent(name="Магазин", slug="shop", purpose="Переглянути набори", section_goals=["hero", "products", "cta"]),
        PageIntent(name="Контакти", slug="contact", purpose="Звернення", section_goals=["hero", "contact", "cta"]),
    ])


def test_user_reported_structure_is_rejected_before_wordpress():
    # The observed v0.9.1 output omitted the page's required semantic content.
    bad = '{"page_slug":"home","sections":[{"style_variant":"default"}],"seo_title":"Title","meta_description":"Description"}'
    with pytest.raises(ValidationError) as error:
        _validate_agent_json(bad, CreativePage)
    details = str(error.value)
    assert "kind" in details and "headline" in details and "body" in details


def test_creative_is_split_and_compiles_typed_editable_elementor():
    arch = architecture()
    foundation = CreativeFoundation.model_validate(foundation_data())
    pages = [CreativePage.model_validate(page_data(p.slug, p.section_goals)) for p in arch.pages]
    exp = compose_experience(arch, foundation, pages)
    lookup = validate_creative_layout(exp, required=True)
    assert set(lookup) == {"home", "shop", "contact"}
    for page in exp.pages:
        assert page.section_specs[0].section_type == "hero"
        assert page.section_specs[0].heading.startswith(page.page_slug)
        compiled = compile_elementor_page(page, exp.design_system, layout=lookup[page.page_slug])
        assert len(compiled) == 3
        assert all(element["elType"] == "container" for element in compiled)
        assert all("tai-generative" in element["settings"]["css_classes"] for element in compiled)
    assert not audit_experience(exp)


def test_partial_page_does_not_discard_strong_ai_copy():
    data = page_data("home", ["hero", "benefits", "cta"])
    data["sections"][0]["headline"] = "Ніжні історії з шоколаду"
    source = CreativePage.model_validate(data)
    exp = compose_experience(architecture().model_copy(update={"pages":architecture().pages[:1]}),
                             CreativeFoundation.model_validate(foundation_data()), [source])
    assert exp.pages[0].section_specs[0].heading == "Ніжні історії з шоколаду"


def test_invalid_choice_and_missing_page_fail_closed():
    bad = foundation_data(); bad["selected_direction_id"] = "missing"
    with pytest.raises(ValidationError):
        CreativeFoundation.model_validate(bad)
    arch = architecture()
    with pytest.raises(ValueError, match="coverage mismatch"):
        compose_experience(arch, CreativeFoundation.model_validate(foundation_data()), [CreativePage.model_validate(page_data("home", ["hero", "benefits", "cta"]))])


def test_palette_repairs_unreadable_colors_and_rejects_unsafe_fonts():
    good = CreativeFoundation.model_validate(foundation_data())
    assert contrast(good.design_system.text, good.design_system.background) > 4.5
    unreadable = foundation_data(); unreadable["design_system"]["text"] = "#FBFAF5"
    fixed = CreativeFoundation.model_validate(unreadable)
    assert contrast(fixed.design_system.text, fixed.design_system.background) >= 4.5
    unsafe = foundation_data(); unsafe["design_system"]["heading_font"] = "Georgia;body{display:none}"
    with pytest.raises(ValidationError, match="font"):
        CreativeFoundation.model_validate(unsafe)


def test_openai_design_page_by_page_without_network():
    arch = architecture()
    fake = object.__new__(OpenAIAgentRuntime)
    fake.budget = BudgetTracker(BudgetLimits(1.0, 30000, 10))
    calls = []

    async def mock_typed(key, payload, model):
        calls.append((payload["task"], model.__name__))
        if model is CreativeFoundation:
            return CreativeFoundation.model_validate(foundation_data())
        if model is CreativePage:
            slug = payload["page"]["slug"]
            kinds = next(page.section_goals for page in arch.pages if page.slug == slug)
            return CreativePage.model_validate(page_data(slug, kinds))
        raise AssertionError("Old oversized ExperienceSpec contract should never be used")

    fake._run_typed = mock_typed
    brief = ProjectBrief(site_type="ecommerce", primary_goal="Шоколадні подарунки", known_facts={"brand":"Fortuna Nova"})
    result = asyncio.run(fake.design(brief, arch))
    assert isinstance(result.design_direction, str)
    assert calls == [("creative_foundation_only", "CreativeFoundation")] + [("creative_page_content_and_layout_only", "CreativePage")]*3
    assert len(result.pages) == 3


def test_missing_budget_fails_before_spending_or_mutating_wordpress():
    fake = object.__new__(OpenAIAgentRuntime)
    fake.budget = BudgetTracker(BudgetLimits(.50, 30000, 2))
    async def no_api(*args, **kwargs):
        raise AssertionError("Should not call OpenAI")
    fake._run_typed = no_api
    with pytest.raises(RuntimeError, match="Increase MAX_LLM_CALLS"):
        asyncio.run(fake.design(ProjectBrief(site_type="ecommerce",primary_goal="store"),architecture()))


def test_schema_failure_correction_is_bounded_and_page_local():
    fake = object.__new__(OpenAIAgentRuntime)
    fake.agents = {"design": SimpleNamespace(name="Creative Director")}
    inputs = []
    valid = page_data("home", ["hero", "benefits", "cta"])
    async def fake_raw(key, prompt):
        inputs.append(prompt)
        if len(inputs) == 1:
            return '{"page_slug":"home","sections":[{"style_variant":"default"}]}'
        import json
        return json.dumps(valid, ensure_ascii=False)
    fake._run_raw = fake_raw
    result = asyncio.run(fake._run_typed("design", {"task":"creative_page_content_and_layout_only"}, CreativePage))
    assert len(inputs) == 2
    assert "EXACT JSON SCHEMA" in inputs[0]
    assert "validation_error" in inputs[1]
    assert len(result.sections) == 3


def test_full_wordpress_pull_plan_with_split_creative_artifacts_offline():
    """Pass the new contract through normalization, editorial checks, policy & compiler."""
    from app.agents.runtime import MockAgentRuntime
    from app.config import Settings
    from app.models import SiteSnapshot
    from app.pull_workflow import PullPlanningWorkflow

    arch = architecture()

    class OfflineAgents(MockAgentRuntime):
        async def orchestrate(self, user_request, renderer):
            return ProjectBrief(site_type="ecommerce", primary_goal="Шоколадні цукерки Fortuna Nova",
                                requested_pages=["Головна", "Магазин", "Контакти"], renderer=renderer)

        async def architect(self, brief, site_summary):
            return arch

        async def design(self, brief, architecture):
            typed_pages = [CreativePage.model_validate(page_data(p.slug, p.section_goals))
                           for p in architecture.pages]
            return compose_experience(architecture, CreativeFoundation.model_validate(foundation_data()), typed_pages)

    snapshot = SiteSnapshot(
        site_info={"name":"Fortuna Nova", "theme_slug":"hello-elementor"},
        plugins=[{"slug":"elementor", "active":True},{"slug":"woocommerce","active":True},
                 {"slug":"contact-form-7","active":True}],
        pages=[{"id":123,"slug":"shop","status":"publish","ai_generated":False}],
        structure={"active_theme_slug":"hello-elementor"},
    )
    result = asyncio.run(PullPlanningWorkflow(Settings(agent_mode="openai", auto_approve_medium_risk=True),
                                               OfflineAgents()).plan("Створи магазин Fortuna Nova, Головна, Магазин, Контакти", "elementor", snapshot))
    assert result["content_quality"]["passed"]
    assert result["experience_spec"]["generative_design"]["selected_direction_id"] == "editorial"
    actions = result["build_plan"]["actions"]
    assert any(a["ability"].endswith("elementor-ensure-draft-page") and a["parameters"].get("slug")=="home" for a in actions)
    assert not any(a["ability"].endswith("elementor-ensure-draft-page") and a["parameters"].get("slug")=="shop" for a in actions)
