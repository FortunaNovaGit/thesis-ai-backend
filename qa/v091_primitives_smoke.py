"""Offline Chromium validation of the new typographic hero and bento/list grammar.

This exercises synthetic Elementor-like markup with the actual shipped CSS.
It does NOT claim to be a WordPress Elementor integration test.
"""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "plugin/thesis-ai-bridge/assets/front.css").read_text()
OUT = ROOT / "synthetic-layout-evidence"
OUT.mkdir(exist_ok=True)


def html(mode: str) -> str:
    visual = "typography" if mode == "typography-bento" else "abstract"
    presentation = "bento" if mode == "typography-bento" else "list"
    hero_art = "" if visual == "typography" else '<div class="e-con tai-hero-art"></div>'
    return f'''<!doctype html><html lang="uk"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>
:root{{--tai-primary:#382219;--tai-accent:#b58d52;--tai-bg:#faf6ee;--tai-surface:#f1e8db;--tai-text:#261a16}}
*,*:before,*:after{{box-sizing:border-box}}body{{margin:0;font-family:Georgia;background:var(--tai-bg);color:var(--tai-text)}}
.e-con{{display:flex;flex-direction:column}}.elementor-widget{{display:block}}.elementor-button{{display:inline-block;text-decoration:none;background:#382219;color:#fff;padding:16px 28px;border-radius:8px}}
.tai-hero-copy p{{font-size:19px;max-width:64ch;line-height:1.6}}.tai-card-grid>.e-con{{padding:28px;background:var(--tai-surface);border-radius:16px}}
</style><style>{CSS}</style></head><body class="thesis-ai-generated"><main id="content" class="site-main"><div class="elementor">
<section class="thesis-ai-section thesis-ai-hero tai-generative tai-layout-split tai-split-55 tai-media-end tai-visual-{visual} tai-content-center tai-heading-dramatic tai-max-1280 e-con"><div class="e-con-inner"><div class="e-con tai-hero-grid">
<div class="e-con tai-hero-copy"><div class="elementor-widget"><h1 class="elementor-heading-title">Шоколадні цукерки, що стають частиною особливих моментів</h1></div><div class="elementor-widget"><p>Подарунки для рідних, привід для зустрічі чи маленька радість для себе. Знайдіть формат набору, який хочеться дарувати.</p></div><div class="elementor-widget elementor-widget-button"><a class="elementor-button" href="/shop/">Переглянути колекції</a></div></div>{hero_art}</div></div></section>
<section class="thesis-ai-section thesis-ai-benefits tai-generative tai-presentation-{presentation} tai-surface-tinted tai-columns-2 e-con"><div class="e-con-inner"><h2>Чим особливий вибір</h2><div class="e-con tai-card-grid">
<div class="e-con"><h3>Для подарунка</h3><p>Тепла увага у важливий момент.</p></div>
<div class="e-con"><h3>Для зустрічі</h3><p>Приємний привід поділитися.</p></div>
<div class="e-con"><h3>Для себе</h3><p>Невелика пауза в щоденному ритмі.</p></div>
</div></div></section>
</div></main></body></html>'''


with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, executable_path="/usr/bin/chromium", args=["--no-sandbox"])
    count = 0
    for mode in ("typography-bento", "abstract-list"):
        for width in (1440, 1024, 768, 390, 320):
            page = browser.new_page(viewport={"width": width, "height": 900}, device_scale_factor=1)
            page.set_content(html(mode))
            data = page.evaluate('''() => ({
              overflow: document.documentElement.scrollWidth - window.innerWidth,
              cards: getComputedStyle(document.querySelector('.tai-card-grid')).gridTemplateColumns.split(' ').length,
              hero: document.querySelector('h1').getBoundingClientRect().toJSON(),
              cta: document.querySelector('.elementor-button').getBoundingClientRect().toJSON(),
              art: document.querySelector('.tai-hero-art')?.getBoundingClientRect().toJSON(),
            })''')
            assert data["overflow"] <= 1, (mode, width, data)
            assert data["hero"]["left"] >= -1 and data["hero"]["right"] <= width + 1, (mode, width, data)
            assert data["cta"]["left"] >= -1 and data["cta"]["right"] <= width + 1, (mode, width, data)
            if mode == "typography-bento" and width == 390:
                assert data["art"] is None
                assert data["cards"] == 1
            if mode == "typography-bento" and width == 1440:
                assert data["cards"] == 2
            if mode == "abstract-list":
                assert data["cards"] == 1
            if width in (1440, 390):
                page.screenshot(path=str(OUT / f"v091-{mode}-{width}.png"), full_page=True)
            count += 1
            print(f"{mode} @ {width}px: no overflow, CTA visible; {data['cards']} card columns")
            page.close()
    browser.close()
    print(f"OK: {count} geometry checks")
