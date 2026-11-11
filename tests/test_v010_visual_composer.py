"""Offline v0.10.0 Visual Composer contract and media safety."""
from pathlib import Path
import pytest
from pydantic import ValidationError

from app.component_library import compile_elementor_page
from app.models import DesignSystem, SectionLayoutSpec, PageLayoutSpec
from app.visual_composer import resolve_scene, scene_classes
from test_v094_quality_first import sample_page, walk
from app.creative_pipeline import CreativePage
from test_v092_creative_contract import page_data

ROOT=Path(__file__).resolve().parents[1]
PRIMARY={'id': 45, 'url': 'https://wp.example/wp-content/uploads/genuine1.jpg',
         'preferred_home_hero': True, 'alt':'Owner-provided photo'}
SECONDARY={'id': 46, 'url': 'https://wp.example/wp-content/uploads/genuine2.jpg',
           'preferred_home_hero_secondary': True, 'alt':'Owner-provided second photo'}

def compile_scene(name, images):
    page=sample_page(with_products=False)
    layout=PageLayoutSpec(page_slug='home',sections=[SectionLayoutSpec(section_index=0,hero_scene=name,
        hero_height='tall', hero_motion='subtle', visual_treatment='media')])
    return compile_elementor_page(page,DesignSystem(),media=images,layout=layout)

@pytest.mark.parametrize('name', ['editorial','cinematic','collage','poster','typographic'])
def test_all_five_scenes_use_editable_native_widgets(name):
    compiled=compile_scene(name,[PRIMARY,SECONDARY])
    all_nodes=list(walk(compiled))
    assert all(n['elType'] in {'container','widget'} for n in all_nodes)
    assert all(n.get('widgetType') in {None,'heading','text-editor','image','button'} for n in all_nodes)
    assert sum(n.get('widgetType')=='heading' and n['settings'].get('header_size')=='h1' for n in all_nodes)==1
    assert f'tai-scene-{name}' in compiled[0]['settings']['css_classes']
    assert all('html' not in n.get('settings',{}) and 'custom_css' not in n.get('settings',{}) for n in all_nodes)
    expected=0 if name=='typographic' else 2 if name=='collage' else 1
    assert sum(n.get('widgetType')=='image' for n in all_nodes)==expected


def test_collage_without_second_image_downgrades_to_single_real_image():
    compiled=compile_scene('collage',[PRIMARY]); root=compiled[0]
    assert 'tai-scene-editorial' in root['settings']['css_classes']
    assert sum(n.get('widgetType')=='image' for n in walk(compiled))==1
    assert resolve_scene(SectionLayoutSpec(section_index=0,hero_scene='collage'),1).downgrade_reason=='missing_second_real_image'


def test_all_photographic_scenes_without_image_become_typographic():
    for name in ('collage','cinematic','poster','editorial'):
        compiled=compile_scene(name,[])
        assert 'tai-scene-typographic' in compiled[0]['settings']['css_classes']
        assert not any(n.get('widgetType')=='image' for n in walk(compiled))


def test_reject_unsafe_scene_codes_and_arbitrary_css():
    with pytest.raises(ValidationError):
        SectionLayoutSpec(section_index=0,hero_scene='cinematic; background:url(https://evil.test)')
    with pytest.raises(ValidationError):
        SectionLayoutSpec.model_validate({'section_index':0,'hero_scene':'cinematic','css':'.site{display:none}'})
    spec=SectionLayoutSpec(section_index=0,hero_scene='cinematic')
    assert 'http' not in scene_classes(spec,resolve_scene(spec,1))


def test_user_hero_scene_flows_through_creative_page_schema():
    data=page_data('home',['hero','benefits','cta'])
    data['sections'][0]['hero_scene']='collage'
    data['sections'][0]['hero_height']='fullscreen'
    data['sections'][0]['hero_motion']='subtle'
    page=CreativePage.model_validate(data)
    assert page.sections[0].hero_scene=='collage'


def test_bridge_includes_scoped_css_and_owner_selected_secondary_image():
    bridge=ROOT/'plugin/thesis-ai-bridge'
    css=(bridge/'assets/visual-composer.css').read_text()
    assert all(f'.tai-scene-{name}' in css for name in ('editorial','cinematic','collage','poster','typographic'))
    assert 'body.thesis-ai-generated .elementor' in css
    assert 'prefers-reduced-motion:reduce' in css
    assert '<script' not in css.lower() and '@import' not in css
    php=(bridge/'includes/class-thesis-ai-bridge.php').read_text()
    assert "'preferred_home_hero_secondary'" in php
    assert 'wp_attachment_is_image($chosen)' in php
    assert 'wp_enqueue_style(' in php and 'visual-composer.css' in php
    admin=(bridge/'includes/class-thesis-ai-bridge-admin.php').read_text()
    assert 'name="brief_hero_secondary_image_id"' in admin
