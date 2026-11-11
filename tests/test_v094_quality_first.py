"""Regression checks based on real v0.9.3 EasyWP screenshots.

All checks are offline and incur zero OpenAI API charges. Not an assertion
that the website is production-ready or actually visually delightful.
"""
from pathlib import Path
import pytest
from pydantic import ValidationError
from app.agents.runtime import explicitly_named_demo_products, safe_demo_products
from app.component_library import compile_elementor_page
from app.models import DesignSystem, SectionContentSpec, PageExperienceSpec, SeoSpec
from app.content_quality import audit_experience, looks_like_filler
from app.creative_pipeline import CreativePage
from test_v092_creative_contract import page_data

ROOT = Path(__file__).resolve().parents[1]


def walk(nodes):
    for node in nodes:
        yield node
        yield from walk(node.get('elements', []))


def sample_page(with_products=True):
    sections = [SectionContentSpec(
        section_type='hero', heading='Шоколадні набори для особливих подій',
        body='Перегляньте асортимент наборів із підтвердженими характеристиками та знайдіть варіант для подарунка.',
        cta_label='Обрати цукерки', cta_url='/shop/',
    )]
    if with_products:
        sections += [SectionContentSpec(section_type='products', heading='Формати асорті',
            body='У каталозі можна порівняти доступні позиції й уточнити актуальну інформацію перед покупкою.',
            items=['Уявна колекція', 'Обрати цукерки'])]
    return PageExperienceSpec(page_name='Головна', page_slug='home', page_goal='Каталог шоколадних наборів',
        sections=[s.section_type for s in sections], section_specs=sections,
        seo=SeoSpec(slug='/', title='Fortuna Nova — набори', meta_description='Каталог шоколадних наборів', h1=sections[0].heading))


def test_quoted_button_is_not_product():
    prompt = 'Головна: Hero з кнопкою «Обрати цукерки». Магазин: товари «Асорті 16 цукерок» та «Асорті 24 цукерки».'
    assert explicitly_named_demo_products(prompt) == ['Асорті 16 цукерок', 'Асорті 24 цукерки']
    assert safe_demo_products('Кнопка «Обрати цукерки» і магазин WooCommerce.') == []


def test_prohibits_fabricating_products_from_ai_copy():
    page = sample_page()
    nodes = list(walk(compile_elementor_page(page, DesignSystem(), media=[], product_names=[])))
    titles = [x['settings'].get('title','') for x in nodes if x.get('widgetType') == 'heading']
    assert 'Уявна колекція' not in titles
    assert not any('tai-product-card' in x.get('settings',{}).get('css_classes','') for x in nodes)
    assert sum(x.get('widgetType') == 'button' for x in nodes) == 1


def test_explicit_product_names_are_text_not_faux_image():
    page = sample_page()
    nodes = list(walk(compile_elementor_page(page, DesignSystem(), media=[],
                                             product_names=['Асорті 16 цукерок'])))
    assert any(x['settings'].get('title') == 'Асорті 16 цукерок' for x in nodes)
    assert any('tai-product-card-text-only' in x['settings'].get('css_classes','') for x in nodes)
    assert not any('tai-product-art' in x['settings'].get('css_classes','') for x in nodes)


def test_absent_hero_media_has_no_empty_visual_panel():
    page = sample_page(with_products=False)
    nodes = list(walk(compile_elementor_page(page, DesignSystem(), media=[])))
    assert any('tai-visual-typography' in x['settings'].get('css_classes', '') for x in nodes)
    assert not any('tai-hero-art' in x['settings'].get('css_classes','') for x in nodes)
    assert sum(x.get('widgetType') == 'heading' and x['settings'].get('header_size')=='h1' for x in nodes) == 1


def test_user_observed_vacuous_copy_is_rejected():
    assert looks_like_filler('Спокійний вибір без зайвих обіцянок')
    data = page_data('home', ['hero', 'benefits', 'cta'])
    data['sections'][1]['headline'] = 'Спокійний вибір без зайвих обіцянок'
    with pytest.raises(ValidationError, match='generic filler'):
        CreativePage.model_validate(data)
    page = sample_page(with_products=False)
    sections = list(page.section_specs)
    sections[0] = sections[0].model_copy(update={'heading':'Спокійний вибір без зайвих обіцянок'})
    issues = audit_experience(type('Fake', (), {'pages':[page.model_copy(update={'section_specs':sections})]})())
    assert any(issue.code == 'vacuous_copy' for issue in issues)


def test_full_bleed_css_and_title_hiding_are_scoped_to_ai_owned_pages():
    css = (ROOT/'plugin/thesis-ai-bridge/assets/front.css').read_text()
    assert 'width:100vw!important' in css
    assert 'margin-left:calc(50% - 50vw)!important' in css
    assert 'body.thesis-ai-generated .entry-header' in css
    assert 'body.thesis-ai-generated .elementor .thesis-ai-section' in css
    php = (ROOT/'plugin/thesis-ai-bridge/includes/class-thesis-ai-bridge.php').read_text()
    assert "$settings['hide_title'] = 'yes'" in php
    assert php.count("update_post_meta($page_id, '_wp_page_template', 'elementor_full_width')") >= 2


def test_preferred_hero_is_real_verified_wordpress_attachment():
    from app.component_library import choose_page_media
    page = sample_page(with_products=False)
    selected = {'id': 219, 'url': 'https://demo.test/wp-content/uploads/hero.jpg',
                'alt': 'Власна фотографія бренду', 'preferred_home_hero': True}
    assert choose_page_media(page, [selected]) == selected
    # Do not trust a broken/insecure media record even if selected in UI.
    bad = dict(selected, url='http://unsafe.test/hero.jpg')
    assert choose_page_media(page, [bad]) is None
    assert choose_page_media(page.model_copy(update={'page_slug':'contact'}), [selected]) is None


def test_media_inventory_uses_confirmed_wp_image_and_does_not_accept_user_url():
    php = (ROOT/'plugin/thesis-ai-bridge/includes/class-thesis-ai-bridge.php').read_text()
    assert 'wp_attachment_is_image($chosen)' in php
    assert "'preferred_home_hero' => (int)$post->ID === $preferred" in php
    assert 'wp_get_attachment_image_url($post->ID' in php
    admin = (ROOT/'plugin/thesis-ai-bridge/includes/class-thesis-ai-bridge-admin.php').read_text()
    assert 'wp_enqueue_media();' in admin
    assert "wp_attachment_is_image($selected_hero)" in admin
    assert 'name="brief_hero_image_id"' in admin


def test_owner_confirmed_product_field_wins_over_hero_marketing_quotes():
    prompt = ('Створи Hero із заголовком «Асорті 16 цукерок» і кнопкою «Обрати цукерки».\n'
              '[Уточнені параметри від власника сайту]\n'
              'ПІДТВЕРДЖЕНІ назви демотоварів (тільки WooCommerce Draft): «Подарунковий набір А»; «Асорті 24 цукерки»')
    assert explicitly_named_demo_products(prompt) == ['Подарунковий набір А', 'Асорті 24 цукерки']
    assert explicitly_named_demo_products('Hero із заголовком «Асорті 16 цукерок»') == []


def test_unspecified_demo_products_do_not_create_fake_inventory():
    assert safe_demo_products('Створи 50 демонстраційних товарів для магазину WooCommerce') == []
    assert safe_demo_products('Планова кількість товарів: 24') == []


def test_simple_text_section_is_not_padded_to_giant_empty_panel():
    from app.models import SectionLayoutSpec, PageLayoutSpec
    page = sample_page(with_products=False)
    more = SectionContentSpec(section_type='content', heading='Знайомство з колекцією',
        body='Перед вибором набору перегляньте доступні позиції та інформацію про кожен набір.')
    page = page.model_copy(update={'section_specs':[*page.section_specs, more]})
    layout = PageLayoutSpec(page_slug='home', sections=[SectionLayoutSpec(
        section_index=1, composition='stacked', visual_treatment='typography',
        surface_treatment='canvas', card_presentation='list', vertical_space=168)])
    compiled = compile_elementor_page(page,DesignSystem(),layout=layout)
    assert compiled[1]['settings']['padding']['top'] == '88'
