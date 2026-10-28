import asyncio
from pathlib import Path

import pytest

from app.content_quality import audit_experience, too_similar, safe_cta_url
from app.models import DesignSystem, ExperienceSpec, PageExperienceSpec, SeoSpec, SectionContentSpec, SiteSnapshot
from app.component_library import compile_elementor_page
from app.agents.runtime import MockAgentRuntime
from app.config import Settings
from app.pull_workflow import PullPlanningWorkflow


def _page(slug, sections):
    return PageExperienceSpec(page_name=slug, page_slug=slug, page_goal=slug,
        sections=[s.section_type for s in sections], section_specs=sections,
        seo=SeoSpec(slug=slug, title=slug, meta_description='Тут можна побачити шоколадні подарунки і вибрати асортимент за своїми потребами.', h1=sections[0].heading))


def _hero(body, url='/shop/'):
    return SectionContentSpec(section_type='hero', heading='Колекції авторського шоколаду', body=body,
        cta_label='Побачити набори', cta_url=url)


def test_editorial_audit_detects_internal_copy_and_repeated_paragraphs():
    same = 'Вибирайте авторський шоколад для святкової нагоди або особливого вечора разом із близькими людьми.'
    exp = ExperienceSpec(design_direction='editorial', pages=[
        _page('home', [_hero(same), SectionContentSpec(section_type='benefits', heading='Чому цукерки', body='Ця сторінка має пояснити ключову конверсію')]),
        _page('contact', [_hero(same)]),
    ])
    codes = [e.code for e in audit_experience(exp)]
    assert 'planning_copy' in codes
    assert 'repeated_body' in codes


def test_editorial_audit_rejects_unsafe_cta_and_sparse_hero():
    exp = ExperienceSpec(design_direction='editorial', pages=[_page('home', [_hero('Дивіться.', 'javascript:alert(1)')])])
    assert {'unsafe_cta', 'empty_hero'}.issubset({e.code for e in audit_experience(exp)})
    assert safe_cta_url('/shop/') is True
    assert safe_cta_url('//evil.test') is False
    assert safe_cta_url('https://evil.test') is False


def test_editorial_audit_accepts_distinct_draft_pages():
    page = _page('home', [_hero('Майстерня пропонує шоколадні подарункові набори для особливих нагод. Перегляньте доступні формати в каталозі.')])
    assert audit_experience(ExperienceSpec(design_direction='premium', pages=[page])) == []


def test_compiler_uses_distinct_editable_card_classes_without_editor_instructions():
    page = _page('home', [
        _hero('Шоколадні набори ручної роботи для святкових подій, привітань і теплих зустрічей. Обирайте у нашій колекції.'),
        SectionContentSpec(section_type='process', heading='Як обрати', body='Три прості кроки до вибору набору.',
            items=['Нагода — оберіть привід для подарунка', 'Колекція — визначте формат набору', 'Деталі — уточніть склад перед замовленням']),
        SectionContentSpec(section_type='products', heading='Шоколадні набори', body='Колекція подарунків для близьких.', items=[]),
    ])
    def nodes(xs):
        for x in xs:
            yield x
            yield from nodes(x.get('elements',[]))
    elements = list(nodes(compile_elementor_page(page, DesignSystem(), product_names=['Асорті 16 цукерок'])))
    classes = [x.get('settings',{}).get('css_classes','') for x in elements]
    assert 'tai-card-grid tai-card-grid-process' in classes
    assert 'tai-feature-card tai-feature-card-process' in classes
    rendered = ' '.join(str(x.get('settings',{}).get('editor','')) for x in elements)
    assert 'Чернетка товару' not in rendered and 'додайте фотографію' not in rendered


def test_existing_mock_three_page_build_passes_new_content_quality_gate():
    snapshot = SiteSnapshot(site_info={'name': 'Fortuna Nova', 'theme_slug': 'hello-elementor'},
        plugins=[{'slug':'elementor','active':True}], themes=[{'slug':'hello-elementor','active':True}],
        capabilities={'approved_plugins':{'elementor':{'installed':True,'active':True}}},
        structure={'active_theme_slug':'hello-elementor'})
    result=asyncio.run(PullPlanningWorkflow(Settings(agent_mode='mock',auto_approve_medium_risk=True), MockAgentRuntime()).plan(
        'Створи магазин шоколадних цукерок із сторінками Головна, Магазин та Контакти', 'elementor', snapshot))
    assert result['content_quality']['passed'] is True


def test_reconciliation_uses_distinct_domain_copy_when_llm_repeats_same_paragraph():
    from app.agents.runtime import reconcile_experience
    from app.models import ArchitectureBundle, ProjectBrief, PageIntent
    same = 'Відкрийте колекцію шоколадних наборів для подарунків, свят і зустрічей з близькими людьми. Оберіть формат у нашому магазині.'
    brief = ProjectBrief(site_type='ecommerce', primary_goal='Продавати шоколадні набори', requested_pages=['Головна','Контакти'])
    architecture = ArchitectureBundle(site_title='Майстерня шоколаду', pages=[
        PageIntent(name='Головна',slug='home',purpose='Представити набори', section_goals=['hero', 'benefits', 'cta']),
        PageIntent(name='Контакти',slug='contact',purpose='Допомогти звернутися', section_goals=['hero', 'contact']),
    ])
    experience = ExperienceSpec(design_direction='editorial', pages=[
        _page('home', [_hero(same)]), _page('contact', [_hero(same)])])
    fixed = reconcile_experience(brief, architecture, experience)
    assert fixed.pages[0].section_specs[0].body != fixed.pages[1].section_specs[0].body
    assert fixed.pages[0].section_specs[0].heading != fixed.pages[1].section_specs[0].heading
    assert not any(i.code == 'repeated_body' for i in audit_experience(fixed))


def test_css_cards_are_scoped_to_generated_pages():
    css = (Path(__file__).resolve().parents[2] / 'plugin' / 'thesis-ai-bridge' / 'assets' / 'front.css').read_text()
    assert 'body.thesis-ai-generated .elementor .tai-card-grid-benefits' in css
    assert 'body.thesis-ai-generated .elementor .tai-card-grid-process' in css
