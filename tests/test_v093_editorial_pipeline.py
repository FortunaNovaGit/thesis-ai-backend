"""Regression for user's 2026-11-04 failure: repetitive page-name headlines."""
import asyncio
from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.agents.runtime import reconcile_experience, OpenAIAgentRuntime
from app.budget import BudgetLimits, BudgetTracker
from app.content_quality import audit_experience
from app.creative_pipeline import CreativePage, CreativeFoundation, compose_experience
from app.models import ProjectBrief, PageIntent, ArchitectureBundle
from test_v092_creative_contract import page_data, foundation_data


def _arch():
    return ArchitectureBundle(site_title="Fortuna Nova", pages=[
        PageIntent(name="Головна", slug="home", purpose="Перше знайомство", section_goals=["hero", "benefits", "cta"]),
        PageIntent(name="Магазин", slug="shop", purpose="Вибір набору", section_goals=["hero", "products", "cta"]),
        PageIntent(name="Контакти", slug="contact", purpose="Звернення", section_goals=["hero", "contact", "cta"]),
    ])


def test_unique_creative_sections_survive_reconciliation_unchanged():
    arch = _arch()
    pages = [CreativePage.model_validate(page_data(p.slug, p.section_goals)) for p in arch.pages]
    original = compose_experience(arch, CreativeFoundation.model_validate(foundation_data()), pages)
    brief = ProjectBrief(site_type="shop", primary_goal="Шоколадні набори")
    reconciled = reconcile_experience(brief, arch, original)
    assert reconciled.generation_contract == "creative_page_v093"
    for before, after in zip(original.pages, reconciled.pages):
        assert [s.heading for s in after.section_specs] == [s.heading for s in before.section_specs]
        assert [s.body for s in after.section_specs] == [s.body for s in before.section_specs]
        assert [s.section_type for s in after.section_specs] == [s.section_type for s in before.section_specs]
        assert [s.eyebrow for s in after.section_specs] == [s.eyebrow for s in before.section_specs]
        assert all(s.heading not in {"Головна", "Магазин", "Контакти"} for s in after.section_specs)
    assert audit_experience(reconciled) == []


def test_page_with_repeated_navigation_heading_fails_pydantic_before_deployment():
    bad = page_data("home", ["hero", "benefits", "cta"])
    bad["sections"][1]["headline"] = "Головна"
    bad["sections"][2]["headline"] = "Головна"
    with pytest.raises(ValidationError, match="generic navigation label|duplicate headline"):
        CreativePage.model_validate(bad)


def test_same_page_body_duplicate_fails_prior_to_reconciler():
    bad = page_data("contact", ["hero", "contact", "cta"])
    bad["sections"][2]["body"] = bad["sections"][1]["body"]
    with pytest.raises(ValidationError, match="repeats body text"):
        CreativePage.model_validate(bad)


def test_cross_page_repeated_copy_never_silently_deploys():
    arch = _arch()
    pages = [CreativePage.model_validate(page_data(p.slug, p.section_goals)) for p in arch.pages]
    shop = pages[1].model_copy(update={"sections": [
        pages[1].sections[0],
        pages[1].sections[1].model_copy(update={"body": pages[0].sections[1].body}),
        pages[1].sections[2],
    ]})
    with pytest.raises(ValueError, match="repeated site copy"):
        compose_experience(arch, CreativeFoundation.model_validate(foundation_data()), [pages[0], shop, pages[2]])


def test_one_page_only_crosspage_retry_without_real_openai():
    arch = _arch()
    fake = object.__new__(OpenAIAgentRuntime)
    fake.budget = BudgetTracker(BudgetLimits(1.0, 30000, 10))
    calls = []
    first_home_body = page_data('home', ['hero','benefits','cta'])['sections'][1]['body']

    async def typed(key, payload, model):
        calls.append((payload['task'], payload.get('page', {}).get('slug')))
        if model is CreativeFoundation:
            return CreativeFoundation.model_validate(foundation_data())
        data = page_data(payload['page']['slug'], payload['page']['section_goals'])
        if payload['page']['slug'] == 'shop' and 'editorial_failures' not in payload:
            data['sections'][1]['body'] = first_home_body
        return CreativePage.model_validate(data)

    fake._run_typed = typed
    result = asyncio.run(fake.design(ProjectBrief(site_type='shop', primary_goal='Сайт бренду'), arch))
    assert len(result.pages) == 3
    assert calls == [
        ('creative_foundation_only', None),
        ('creative_page_content_and_layout_only', 'home'),
        ('creative_page_content_and_layout_only', 'shop'),
        ('creative_page_content_and_layout_only', 'shop'),
        ('creative_page_content_and_layout_only', 'contact'),
    ]
    assert audit_experience(result) == []


def test_editorial_gate_reports_real_section_index_for_repeated_body():
    arch = _arch()
    pages = [CreativePage.model_validate(page_data(p.slug, p.section_goals)) for p in arch.pages]
    exp = compose_experience(arch, CreativeFoundation.model_validate(foundation_data()), pages)
    target = exp.pages[2]
    sections = list(target.section_specs)
    sections[2] = sections[2].model_copy(update={"body": sections[1].body})
    modified = exp.model_copy(update={"pages": [*exp.pages[:2], target.model_copy(update={"section_specs": sections})]})
    found = [issue for issue in audit_experience(modified) if issue.code == 'repeated_body']
    assert found and found[0].section_index == 2
    assert 'contact:section[1]' in found[0].detail


def test_unavailable_hero_photo_becomes_editable_typographic_layout():
    from app.component_library import compile_elementor_page
    from app.models import SectionLayoutSpec, PageLayoutSpec
    arch = _arch()
    page = CreativePage.model_validate(page_data('home', ['hero','benefits','cta']))
    exp = compose_experience(arch.model_copy(update={'pages':arch.pages[:1]}),
                             CreativeFoundation.model_validate(foundation_data()), [page])
    spec = exp.generative_design.page_layouts[0]
    sections = list(spec.sections)
    sections[0] = sections[0].model_copy(update={'visual_treatment':'media'})
    spec = spec.model_copy(update={'sections': sections})
    items = compile_elementor_page(exp.pages[0], exp.design_system, [], layout=spec)
    assert 'tai-visual-typography' in items[0]['settings']['css_classes']
    assert all('tai-hero-art' not in str(el) for el in items[0]['elements'])
