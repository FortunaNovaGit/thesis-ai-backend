"""Offline regression of v0.9.3's real-world 770px theme wrapper failure.

This renders a WordPress-like narrow entry-content wrapper with the actual
v0.9.4 Bridge CSS in Chromium. It does NOT claim real EasyWP E2E success.
No OpenAI API calls or external assets are used.
"""
from __future__ import annotations
import json
from pathlib import Path
import shutil
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT/'plugin/thesis-ai-bridge/assets/front.css').read_text()
OUT = ROOT/'v094-qa-evidence'
OUT.mkdir(exist_ok=True)

HTML = '''<!doctype html><html lang="uk"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>
*{box-sizing:border-box}body{margin:0;background:#fcf8f1;color:#251815;font-family:Arial,sans-serif}
#content{width:770px;max-width:calc(100% - 24px);margin-inline:auto}
.entry-header{padding:28px;background:white;text-align:center}.entry-title{font:36px Georgia}
.elementor{width:100%;max-width:770px;margin-inline:auto}
.e-con{display:flex;flex-direction:column;gap:24px}
.thesis-ai-section{padding:90px 24px;background:#361f19;color:#fff}
.thesis-ai-section.tai-surface-tinted{background:#fff;color:#361f19}
.elementor-widget{width:100%}
.tai-hero-grid{display:flex;flex-direction:row}
.tai-hero-copy h1{font:700 clamp(45px,5.2vw,78px)/1.08 Georgia,serif;letter-spacing:-.045em;max-width:16ch;margin:0}
.tai-hero-copy p{font-size:20px;line-height:1.6;max-width:47ch}
.elementor-button{display:inline-block;background:#9b743e;color:#fff;padding:18px 26px;text-decoration:none;border-radius:6px}
</style><style>__CSS__</style><style>/* Simulate a late theme rule that still boxes its content wrapper. */
body.thesis-ai-generated main#content{width:min(770px,calc(100% - 24px))!important;max-width:770px!important}
</style></head><body class="thesis-ai-generated">
<main id="content" class="site-main"><article><header class="entry-header"><h1 class="entry-title">Головна</h1></header><div class="entry-content"><div class="elementor">
<section class="e-con thesis-ai-section thesis-ai-hero tai-generative tai-visual-typography tai-max-1280 tai-layout-centered tai-content-start">
<div class="e-con tai-hero-grid"><div class="e-con tai-hero-copy">
<div class="elementor-widget"><div class="elementor-widget-container"><span>FORTUNA NOVA · КОЛЕКЦІЯ</span></div></div>
<div class="elementor-widget"><h1 class="elementor-heading-title">Шоколадне асорті для особливих моментів</h1></div>
<div class="elementor-widget"><p>Набори для подарунка та зустрічі. Перегляньте доступні позиції, щоб обрати потрібний формат.</p></div>
<div class="elementor-widget"><a href="/shop/" class="elementor-button">Переглянути набори</a></div>
</div></div></section>
<section class="e-con thesis-ai-section thesis-ai-products tai-generative tai-max-1280 tai-presentation-list tai-surface-tinted">
<div class="elementor-widget elementor-widget-heading"><h2>Асортимент, який легко порівняти</h2></div>
<div class="elementor-widget elementor-widget-text-editor"><p>Оберіть набір за розміром і доступним описом, а деталі уточніть у картці товару.</p></div>
<div class="e-con tai-card-grid"><div class="e-con tai-product-card tai-product-card-text-only"><div class="elementor-widget">01 /</div><h3>Асорті 16 цукерок</h3></div><div class="e-con tai-product-card tai-product-card-text-only"><div class="elementor-widget">02 /</div><h3>Асорті 24 цукерки</h3></div></div>
</section></div></div></article></main></body></html>'''.replace('__CSS__', CSS)

if __name__ == '__main__':
    measurements = {}
    with sync_playwright() as pw:
        system_chromium = shutil.which('chromium') or shutil.which('chromium-browser')
        options = {'executable_path': system_chromium} if system_chromium else {}
        browser = pw.chromium.launch(headless=True, args=['--no-sandbox'], **options)
        for width in (1440, 900, 390, 320):
            page = browser.new_page(viewport={'width':width,'height':900},device_scale_factor=1)
            page.set_content(HTML, wait_until='domcontentloaded')
            info=page.evaluate('''() => {
                const r=document.querySelector('.thesis-ai-section').getBoundingClientRect();
                const original=document.querySelector('#content').getBoundingClientRect();
                const title=document.querySelector('.entry-header');
                const cta=document.querySelector('.elementor-button').getBoundingClientRect();
                const w=window.innerWidth;
                return {viewport:w, themeWrapperWidth:Math.round(original.width), sectionX:Math.round(r.x),
                    sectionWidth:Math.round(r.width), overflow:document.documentElement.scrollWidth-w,
                    themeTitleVisible: getComputedStyle(title).display!=='none',
                    ctaFits: cta.left>=-2 && cta.right<=w+2};
            }''')
            assert info['themeWrapperWidth'] <= min(770,width), info
            assert info['sectionWidth'] >= width-2, info
            assert abs(info['sectionX']) <= 2, info
            assert not info['themeTitleVisible'] and info['ctaFits'], info
            assert info['overflow'] <= 3, info
            measurements[str(width)]=info
            page.screenshot(path=str(OUT/f'layout-{width}.png'),full_page=True)
            print(f'{width}px: full width {info["sectionWidth"]}px, theme wrapper {info["themeWrapperWidth"]}px, overflow {info["overflow"]}')
            page.close()
        browser.close()
    (OUT/'report.json').write_text(json.dumps({'kind':'offline-wordpress-like-fixture','passed':True,
        'measurements':measurements},ensure_ascii=False,indent=2),encoding='utf-8')
