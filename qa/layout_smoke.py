"""Optional offline CSS/layout check using Chromium/Playwright.

This is a synthetic Elementor-like fixture, NOT a real WordPress or Elementor
integration test. Usage (dev only): python qa/layout_smoke.py
"""
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE=Path(__file__).resolve().parents[2]
CSS=(BASE/'plugin'/'thesis-ai-bridge'/'assets'/'front.css').read_text()
HTML='''<!doctype html><html lang="uk"><meta charset="utf-8"><style>body{margin:0;background:#faf6ef;font-family:Arial;color:#fff}.elementor{width:100%}.thesis-ai-section{padding:clamp(30px,5vw,90px) 30px; background:#2a1b15}.tai-hero-grid>.e-con{display:flex;flex-direction:column;gap:20px} .elementor-button{display:inline-block;padding:18px 28px;text-decoration:none;background:#b99259;color:white;border-radius:12px}.tai-hero-copy h1{font-family:Georgia;font-weight:600}.tai-hero-copy p{font-size:19px}.site-main{max-width:760px;margin:auto}</style><style>_CSS_</style><body class="thesis-ai-generated"><main id="content" class="site-main"><article><div class="elementor"><div class="thesis-ai-section thesis-ai-hero e-con"><div class="e-con-inner"><div class="e-con tai-hero-grid"><div class="e-con tai-hero-copy"><div class="elementor-widget"><div class="elementor-widget-container"><h1 class="elementor-heading-title">Шоколадні цукерки ручної роботи для особливих моментів</h1></div></div><div class="elementor-widget"><p>Натуральні цукерки ручної роботи для подарунків, теплих зустрічей та маленьких свят.</p></div><div class="elementor-widget"><a class="elementor-button" href="#">Обрати колекцію</a></div></div><div class="e-con tai-hero-art"></div></div></div></div></div></article></main></body></html>'''.replace('_CSS_',CSS)
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
    for width in (1440,900,390):
        page=browser.new_page(viewport={'width':width,'height':900},device_scale_factor=1)
        page.set_content(HTML)
        overflow=page.evaluate('document.documentElement.scrollWidth - window.innerWidth')
        h1=page.locator('h1').bounding_box()
        art=page.locator('.tai-hero-art').bounding_box()
        if width>1100:
            assert h1['x']+h1['width'] <= art['x']+2, f'Heading overlaps art at {width}: {h1}, {art}'
        assert overflow <= 1, f'Horizontal overflow at {width}: {overflow}'
        page.screenshot(path=str(BASE/f'preview-{width}.png'),full_page=True)
        print(f'width={width}px overflow={overflow}px, hero-safe=yes')
        page.close()
    browser.close()
