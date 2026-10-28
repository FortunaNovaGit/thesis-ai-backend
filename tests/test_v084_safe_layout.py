"""Regression guards for the user's overflowing chocolate storefront hero."""
from pathlib import Path
from app.component_library import compile_elementor_page, choose_page_media, choose_matching_media
from app.models import DesignSystem, PageExperienceSpec, SeoSpec, SectionContentSpec


def nodes(items):
    for item in items:
        yield item
        yield from nodes(item.get('elements', []))


def sample_page():
    return PageExperienceSpec(page_name='Головна', page_slug='home', page_goal='Шоколадні подарунки',
        sections=['hero'], seo=SeoSpec(slug='home', title='Fortuna Nova',
        meta_description='Шоколадні цукерки ручної роботи', h1='Шоколадні цукерки'),
        section_specs=[SectionContentSpec(section_type='hero', heading='Шоколадні цукерки ручної роботи для особливих моментів',
            body='Майстерня натуральних шоколадних цукерок.',
            items=['Основна посадкова сторінка, що пояснює цінність і веде до конверсії'])])


def test_hero_grid_has_unconstrained_children_but_safe_responsive_css():
    components=list(nodes(compile_elementor_page(sample_page(),DesignSystem())))
    grid=next(n for n in components if n.get('settings',{}).get('css_classes')=='tai-hero-grid')
    assert len(grid['elements']) == 2
    assert grid['elements'][0]['settings']['css_classes']=='tai-hero-copy'
    assert all(child['settings']['width']['size']==100 for child in grid['elements'])
    css=Path(__file__).resolve().parents[2]/'plugin'/'thesis-ai-bridge'/'assets'/'front.css'
    # This test can run in backend-only repos, where the plugin source is absent.
    if css.exists():
        text=css.read_text()
        assert 'grid-template-columns:minmax(0,1.05fr) minmax(0,.95fr)' in text
        assert '@media(max-width:1100px)' in text


def test_hero_no_internal_planning_content_or_fake_product_photo():
    components=list(nodes(compile_elementor_page(sample_page(),DesignSystem())))
    texts=[str(n.get('settings',{}).get('title','')) for n in components]
    assert not any('посадкова' in t or 'конверсії' in t for t in texts)
    art=next(n for n in components if n.get('settings',{}).get('css_classes')=='tai-hero-art')
    assert art['elements']==[]


def test_relevant_real_media_can_fill_hero_and_unrelated_cannot():
    media=[{'id':123,'url':'https://example.org/wp-content/uploads/choco.jpg',
            'alt':'Шоколадні набори ручної роботи', 'title':'Фото цукерок'}]
    assert choose_page_media(sample_page(),media)==media[0]
    assert choose_matching_media('Деревʼяні будинки',media) is None
    assert choose_matching_media('Шоколадні набори',[{'id':0,'url':'https://example.org/img.jpg','alt':'Шоколадні набори'}]) is None


def test_product_card_uses_real_media_when_its_name_matches():
    products=SectionContentSpec(section_type='products',heading='Колекції',items=['Асорті 16 цукерок'])
    page=sample_page().model_copy(update={'section_specs':[sample_page().section_specs[0],products]})
    media=[{'id':442,'url':'https://example.org/wp-content/uploads/assorti.jpg',
            'alt':'Асорті 16 шоколадних цукерок','title':'Набір Асорті 16'}]
    compiled=list(nodes(compile_elementor_page(page,DesignSystem(),media=media)))
    assert any(n.get('widgetType')=='image' and n['settings']['image']['id']==442 for n in compiled)


def test_wordpress_bridge_sets_real_full_width_template_without_mcp_autoconnection():
    # Pure compile-time guarantee, not a claim of real EasyWP rendering.
    # In standalone backend distribution this test can be skipped.
    code=Path(__file__).resolve().parents[2]/'plugin'/'thesis-ai-bridge'/'includes'/'class-thesis-ai-bridge.php'
    if code.exists():
        source=code.read_text()
        assert "update_post_meta($page_id, '_wp_page_template', 'elementor_full_width')" in source
        assert "'mcp_requires_admin_opt_in' => true" in source


def test_no_wrong_quantity_product_image():
    media=[{'id':23, 'url':'https://example.org/upload/24.jpg', 'alt':'Асорті 24 цукерки', 'title':'Асорті 24'}]
    assert choose_matching_media('Асорті 16 цукерок',media) is None
    assert choose_matching_media('Асорті 24 цукерки',media)==media[0]
