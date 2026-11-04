"""Offline Chromium geometry smoke for v0.9 generated class combinations.

This is synthetic Elementor-like DOM, NOT real Elementor/WordPress Visual QA.
No HTTP requests or OpenAI calls are made. Usage: python qa/generative_layout_smoke.py
"""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "plugin/thesis-ai-bridge/assets/front.css").read_text()
OUT = ROOT / "synthetic-layout-evidence"
OUT.mkdir(exist_ok=True)

def markup(mode: str, media_position: str, columns: int) -> str:
    return f'''<!DOCTYPE html><html lang="uk"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{{--tai-primary:#3b2851;--tai-accent:#dfae7b;--tai-bg:#faf8f4;--tai-surface:#f3eee8;--tai-text:#21192b}}
*,*::before,*::after{{box-sizing:border-box}}body{{margin:0;background:var(--tai-bg);color:var(--tai-text);font-family:Arial}}
.e-con{{display:flex;flex-direction:column}} .elementor-widget{{display:block}}
.tai-hero-grid>.e-con{{gap:24px}}.elementor-button{{display:inline-block;background:var(--tai-accent);padding:14px 24px;color:#1d1429;text-decoration:none;border-radius:12px}}
.tai-hero-copy h1{{margin:0}} .tai-hero-copy p{{font-size:18px;line-height:1.55;max-width:50ch}}
.tai-card-grid .e-con{{padding:24px;background:var(--tai-surface);border-radius:20px}}
</style><style>{CSS}</style></head>
<body class="thesis-ai-generated"><main id="content" class="site-main"><div class="elementor">
<section class="thesis-ai-section thesis-ai-hero tai-generative tai-layout-{mode} tai-media-{media_position} tai-split-45 tai-heading-dramatic tai-ratio-landscape tai-motif-lines tai-max-1280 tai-columns-{columns} e-con">
<div class="e-con-inner"><div class="e-con tai-hero-grid">
<div class="e-con tai-hero-copy"><div class="elementor-widget"><h1 class="elementor-heading-title">Шоколадні цукерки ручної роботи для особливих моментів</h1></div>
<div class="elementor-widget"><p>Для подарунків, теплих зустрічей і важливих подій. Перегляньте колекції та уточніть деталі набору перед замовленням.</p></div>
<div class="elementor-widget elementor-widget-button"><a class="elementor-button" href="/shop/">Переглянути колекції</a></div></div>
<div class="e-con tai-hero-art" aria-hidden="true"></div></div></div></section>
<section class="thesis-ai-section thesis-ai-products tai-generative tai-layout-offset tai-max-1280 tai-columns-{columns} e-con">
<div class="e-con-inner"><div class="elementor-widget"><h2>Колекції для вибору</h2></div>
<div class="e-con tai-card-grid"><div class="e-con"><h3>Подарункові набори</h3><p>Різні формати для ваших нагод.</p></div><div class="e-con"><h3>Шоколадне асорті</h3><p>Перед замовленням уточніть склад.</p></div><div class="e-con"><h3>Запитання</h3><p>Напишіть нам перед вибором.</p></div></div></div></section>
</div></main></body></html>'''


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True, executable_path="/usr/bin/chromium", args=["--no-sandbox"])
    for mode, media_position, columns in [("split", "end", 3), ("stacked", "start", 2), ("centered", "end", 1), ("offset", "end", 4)]:
        for width in (1440, 900, 390):
            page = browser.new_page(viewport={"width":width,"height":900},device_scale_factor=1)
            page.set_content(markup(mode, media_position, columns))
            overflow = page.evaluate("document.documentElement.scrollWidth-window.innerWidth")
            heading = page.locator("h1").bounding_box()
            art = page.locator(".tai-hero-art").bounding_box()
            button = page.locator(".elementor-button").bounding_box()
            assert heading is not None and art is not None and button is not None
            horizontal_overlap = heading["x"] < art["x"] + art["width"] and art["x"] < heading["x"] + heading["width"]
            vertical_overlap = heading["y"] < art["y"] + art["height"] and art["y"] < heading["y"] + heading["height"]
            assert not (horizontal_overlap and vertical_overlap), f"Headline/art overlap: {mode}@{width}: {heading} vs {art}"
            assert overflow <= 1, f"Horizontal overflow {mode}@{width}: {overflow}px"
            assert 0 <= button["x"] and button["x"] + button["width"] <= width + 1
            if width == 390:
                page.screenshot(path=str(OUT / f"{mode}-mobile.png"), full_page=True)
            elif width == 1440:
                page.screenshot(path=str(OUT / f"{mode}-desktop.png"), full_page=True)
            print(f"{mode:8s} {width:4d}px: overflow={overflow}px; heading/art separate; CTA in viewport")
            page.close()
    browser.close()
