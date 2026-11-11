"""Offline browser smoke for v0.10 Hero scenes (no WordPress / no API calls).

The HTML emulates the Elementor container DOM. The real Elementor rendering and
EasyWP theme interplay must still be checked on staging.
"""
from __future__ import annotations
from html import escape
from pathlib import Path
import json
import sys
import os

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.component_library import compile_elementor_page
from app.models import DesignSystem, SectionLayoutSpec, PageLayoutSpec
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tests"))
from test_v094_quality_first import sample_page
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
OUT=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'qa'/'v010-evidence'
OUT.mkdir(parents=True,exist_ok=True)
BG='''<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="1400"><defs><linearGradient id="g" x2="1" y2="1"><stop stop-color="#815c41"/><stop offset="1" stop-color="#261713"/></linearGradient></defs><rect width="1400" height="1400" fill="url(#g)"/><circle cx="780" cy="530" r="430" fill="#c79d73" opacity=".7"/><circle cx="390" cy="990" r="200" fill="#efd8b6" opacity=".4"/></svg>'''
IMAGE='data:image/svg+xml;charset=utf-8,' + __import__('urllib.parse',fromlist=['quote']).quote(BG)
PRIMARY={'id':55,'url':'https://wp.local/owner-one.jpg','preferred_home_hero':True}
SECONDARY={'id':56,'url':'https://wp.local/owner-two.jpg','preferred_home_hero_secondary':True}

def render(node):
    cls='e-con elementor-element ' + node.get('settings',{}).get('css_classes','')
    if node['elType']=='container':
        return f'<div class="{escape(cls,quote=True)}">'+''.join(render(ch) for ch in node['elements'])+'</div>'
    kind=node.get('widgetType'); settings=node['settings']
    if kind=='heading':
        tag=settings.get('header_size','h2')
        tag=tag if tag in ('div','h1','h2','h3') else 'div'
        child=f'<{tag} class="elementor-heading-title">{settings.get("title","")}</{tag}>'
    elif kind=='text-editor': child=f'<div class="elementor-text-editor">{settings.get("editor","")}</div>'
    elif kind=='button': child='<a class="elementor-button" href="#">'+escape(settings['text'])+'</a>'
    elif kind=='image': child='<div class="elementor-widget-container"><img src="'+IMAGE+'" alt="Synthetic test graphic"></div>'
    else: child=''
    return f'<div class="elementor-widget elementor-widget-{escape(kind or "widget")}">{child}</div>'

css1=(ROOT/'plugin/thesis-ai-bridge/assets/front.css').read_text()
css2=(ROOT/'plugin/thesis-ai-bridge/assets/visual-composer.css').read_text()
viewports=[1440,900,390,320]
results=[]
with sync_playwright() as pl:
    executable = os.getenv('CHROMIUM_PATH', '')
    if not executable and Path('/usr/bin/chromium').is_file():
        executable = '/usr/bin/chromium'
    options={'headless': True, 'args': ['--no-sandbox']}
    if executable: options['executable_path']=executable
    browser=pl.chromium.launch(**options)
    for name in ['editorial','cinematic','collage','poster','typographic']:
        page_spec=sample_page(with_products=False)
        layout=PageLayoutSpec(page_slug='home',sections=[SectionLayoutSpec(
            section_index=0,composition='split',hero_scene=name,hero_height='tall',
            visual_treatment='media',hero_motion='none')])
        elements=compile_elementor_page(page_spec,DesignSystem(),media=[PRIMARY,SECONDARY],layout=layout)
        html='''<!doctype html><html lang="uk"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
        <style>'''+css1+'''</style><style>'''+css2+'''</style>
        <style>*{box-sizing:border-box}html,body{margin:0;padding:0}body{background:#faf5ec;--tai-text:#241c18;--tai-bg:#faf5ec;--tai-accent:#85623f;--tai-primary:#37241e;--tai-surface:#f0e8dc;font:18px/1.5 Arial,sans-serif}.elementor-button{display:inline-flex;background:#85623f;color:white;padding:12px 24px;text-decoration:none;border-radius:8px}.e-con{display:flex;flex-direction:column}.elementor-widget-text-editor p{margin:0}.elementor-heading-title{margin:0}img{max-width:100%;display:block}body.thesis-ai-generated{overflow-x:clip}</style>
        <body class="thesis-ai-generated"><div class="elementor">'''+''.join(render(x) for x in elements)+'''</div></body></html>'''
        html_path=OUT/f'{name}.html'; html_path.write_text(html)
        for width in viewports:
            p=browser.new_page(viewport={'width':width,'height':850},device_scale_factor=1)
            errors=[]
            p.on('pageerror',lambda error: errors.append(str(error)))
            p.set_content(html,wait_until='load')
            p.locator('img').evaluate_all('(xs) => Promise.all(xs.map(x => x.decode().catch(() => {})))')
            r=p.evaluate('''() => {
              const root=document.querySelector('.tai-vc'),copy=document.querySelector('.tai-hero-copy'),photo=document.querySelector('.tai-hero-photo'),h1=document.querySelector('h1');
              const rb=root.getBoundingClientRect(), cb=copy.getBoundingClientRect(), hb=h1.getBoundingClientRect(), pb=photo?.getBoundingClientRect();
              return {scrollWidth:document.documentElement.scrollWidth,rootWidth:rb.width,
                h1Visible:hb.width>0&&hb.height>0&&hb.left>=-2&&hb.right<=window.innerWidth+2,copyBottom:cb.bottom,photoTop:pb?.top ?? null,
                noBrokenImages:[...document.images].every(x=>x.complete&&x.naturalWidth>0)};
            }''')
            r.update(scene=name,viewport=width,errors=errors)
            if r['scrollWidth']>width+2: raise AssertionError(f'overflow {name} {width}: {r}')
            if not r['h1Visible'] or not r['noBrokenImages'] or errors: raise AssertionError(f'invalid scene: {r}')
            if width<=900 and r['photoTop'] is not None and r['photoTop'] < r['copyBottom']-12:
                raise AssertionError(f'overlay in stacked mobile {name} {width}: {r}')
            if width in (1440,390): p.screenshot(path=str(OUT/f'{name}-{width}.png'),full_page=True)
            results.append(r);p.close()
    browser.close()
(OUT/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
print(f'PASS: {len(results)} synthetic viewport checks; evidence {OUT}')
