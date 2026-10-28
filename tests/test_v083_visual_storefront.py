"""Regression tests for the visual storefront without OpenAI API calls."""
import asyncio
from app.agents.runtime import (
    compile_build_plan, safe_demo_products, explicitly_named_demo_products,
    site_design_profile, MockAgentRuntime,
)
from app.component_library import compile_elementor_page
from app.config import Settings
from app.models import DesignSystem, SiteSnapshot
from app.pull_workflow import PullPlanningWorkflow


def walk(nodes):
    for node in nodes:
        yield node
        yield from walk(node.get('elements', []))


def test_woocommerce_shop_page_remains_wc_owned_and_no_collision():
    snap = SiteSnapshot(site_info={'theme_slug':'hello-elementor'},
                        plugins=[{'slug':'woocommerce','active':True}, {'slug':'elementor','active':True}],
                        structure={'active_theme_slug':'hello-elementor'},
                        pages=[{'id': 42,'slug':'shop','status':'publish','ai_generated':False}])
    async def run():
        runtime = MockAgentRuntime()
        brief = await runtime.orchestrate('Створи магазин шоколадних цукерок з Головною, Магазином і Контактами', 'elementor')
        brief = brief.model_copy(update={'requested_pages':['Головна','Магазин','Контакти']})
        arch = await runtime.architect(brief, {'site_info':snap.site_info,'plugins':snap.plugins})
        from app.agents.runtime import architecture_to_application_spec, reconcile_experience
        from app.capabilities import resolve_capabilities
        resolutions = resolve_capabilities(arch, snap, 'elementor')
        app = architecture_to_application_spec(brief, arch, resolutions)
        exp = reconcile_experience(brief, arch, await runtime.design(brief, arch))
        return compile_build_plan(app, exp, snap, 'elementor', 'Створи магазин шоколадних цукерок')
    plan = asyncio.run(run())
    assert not any(a.parameters.get('slug')=='shop' and a.ability.endswith('ensure-draft-page') for a in plan.actions)
    assert not any(a.parameters.get('slug')=='shop' and a.ability.endswith('set-page-seo') for a in plan.actions)
    assert any(a.ability.endswith('configure-woocommerce') for a in plan.actions)
    assert any(a.ability.endswith('ensure-navigation-menu') and 'shop' in a.parameters['page_slugs'] for a in plan.actions)


def test_opt_in_placeholder_products_and_no_unrequested_fake_inventory():
    assert safe_demo_products('Створи магазин шоколаду') == []
    names = safe_demo_products('Додай демонстраційні товари для WooCommerce магазину')
    assert len(names) == 3 and all('Демо-товар' in n for n in names)
    assert safe_demo_products('Зроби магазин і додай «Асорті 16 цукерок»') == ['Асорті 16 цукерок']


def test_chocolatier_palette_is_consistent_but_regular_business_is_unchanged():
    original=DesignSystem(primary='#115599')
    themed=site_design_profile('Шоколадні цукерки ручної роботи', original)
    assert themed.primary == '#382219' and themed.container_width == 1280
    assert site_design_profile('Сайт для ремонту комп’ютерів', original) is original


def test_hero_does_not_reuse_internal_planning_notes_in_visual_panel():
    from app.models import PageExperienceSpec,SeoSpec,SectionContentSpec
    p=PageExperienceSpec(page_name='Головна',page_slug='home',page_goal='Конверсія',sections=['hero'],
       seo=SeoSpec(slug='home',title='Головна',meta_description='Подарункові шоколадні набори',h1='Шоколад'),
       section_specs=[SectionContentSpec(section_type='hero',heading='Шоколадні набори',
         body='Відкрийте для себе наші набори шоколадних цукерок ручної роботи.',
         items=['Основна посадкова сторінка, що пояснює цінність і веде до головної конверсії'])])
    nodes=compile_elementor_page(p, DesignSystem())
    titles=[str(n.get('settings',{}).get('title','')) for n in walk(nodes)]
    assert not any('посадкова' in title or 'конверсії' in title for title in titles)
    assert any('tai-hero-art' in str(n.get('settings',{}).get('css_classes','')) for n in walk(nodes))


def test_ecommerce_home_adds_visual_product_showcase_even_when_agent_omits_it():
    from app.models import (ApplicationSpec, PageRequirement, PluginPlanItem, ExperienceSpec,
                            PageExperienceSpec, SeoSpec, SectionContentSpec)
    app=ApplicationSpec(site_type='ecommerce', site_title='Fortuna Nova', goals=['Показати колекції'],
        pages=[PageRequirement(name='Головна',slug='home',purpose='Представити бренд')],
        features=[],required_capabilities=['ecommerce'],
        plugin_plan=[PluginPlanItem(capability='ecommerce',plugin_slug='woocommerce',reason='Store')])
    page=PageExperienceSpec(page_name='Головна',page_slug='home',page_goal='Представити бренд',sections=['hero','cta'],
        section_specs=[SectionContentSpec(section_type='hero',heading='Шоколад для близьких',body='Обирайте подарункові набори шоколадних цукерок ручної роботи.'),
                       SectionContentSpec(section_type='cta',heading='Зробіть замовлення',body='Дізнайтесь більше про колекції.')],
        seo=SeoSpec(slug='home',title='Fortuna Nova',h1='Шоколад для близьких',meta_description='Шоколадні цукерки'))
    exp=ExperienceSpec(design_direction='luxury',pages=[page])
    snap=SiteSnapshot(site_info={'theme_slug':'hello-elementor'}, structure={'active_theme_slug':'hello-elementor'},
        plugins=[{'slug':'woocommerce','active':True},{'slug':'elementor','active':True}])
    plan=compile_build_plan(app, exp, snap, 'elementor', 'Магазин цукерок. Товари «Асорті 16 цукерок» та «Асорті 24 цукерки»')
    home=next(a for a in plan.actions if a.ability.endswith('elementor-ensure-draft-page'))
    titles=[str(n.get('settings',{}).get('title','')) for n in walk(home.parameters['elements'])]
    assert 'Обрані колекції' in titles
    assert 'Асорті 16 цукерок' in titles and 'Асорті 24 цукерки' in titles
    assert not any('посадкова сторінка' in t for t in titles)
