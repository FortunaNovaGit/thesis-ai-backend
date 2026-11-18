"""Offline visual preview of a compiled Fortuna Nova Home (no WordPress, no API).

Emulates the Elementor V3 DOM *and* the per-element CSS Elementor generates
from widget settings (colors, font sizes, font families, padding, widths), so
the screenshot is close to what the real page shows with the Bridge CSS.
It is still synthetic evidence, NOT a live EasyWP/Elementor screenshot.

Usage (inside the QA container, from the backend root):
    python qa/rich_preview.py qa/rich-evidence [--plugin ../src-bridge/thesis-ai-bridge]
"""
from __future__ import annotations

import argparse
import json
import sys
from html import escape
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.component_library import compile_elementor_page  # noqa: E402
from app.models import (DesignSystem, PageExperienceSpec, PageLayoutSpec,  # noqa: E402
                        SectionContentSpec, SectionLayoutSpec, SeoSpec)

FONTS = "https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,500;0,600;0,700;1,500;1,600&family=Manrope:wght@400;500;600;700&family=Unbounded:wght@400;500;600;700&family=Jost:ital,wght@0,400;0,500;0,600;0,700;1,500&display=swap"

FA = "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css"
ART = '''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="1400"><defs><radialGradient id="g" cx=".35" cy=".3" r=".9"><stop stop-color="#a1704a"/><stop offset=".55" stop-color="#4a2c1e"/><stop offset="1" stop-color="#1c110c"/></radialGradient></defs><rect width="1200" height="1400" fill="url(#g)"/><g fill="#d9b27c" opacity=".85"><circle cx="420" cy="620" r="150"/><circle cx="760" cy="760" r="120"/><circle cx="560" cy="930" r="135"/></g><g fill="#3a2117"><circle cx="420" cy="620" r="118"/><circle cx="760" cy="760" r="92"/><circle cx="560" cy="930" r="104"/></g></svg>'''
IMAGE = "data:image/svg+xml;charset=utf-8," + quote(ART)


def fortuna_home(with_media: bool, direction: str = "warm") -> tuple[PageExperienceSpec, PageLayoutSpec, DesignSystem, list[dict]]:
    S = SectionContentSpec
    sections = [
        S(section_type="hero", eyebrow="Шоколадна майстерня · Львів",
          heading="Цукерки, які хочеться дарувати повільно",
          body="Fortuna Nova збирає авторські набори шоколадних цукерок ручної роботи — для подарунка, свята або тихого вечора з кавою.",
          items=["Ручна робота — кожна цукерка формується та декорується вручну",
                 "Подарункові набори — 16 і 24 цукерки в коробці",
                 "Замовлення онлайн — оберіть набір у каталозі"],
          cta_label="Обрати цукерки", cta_url="/shop/", style_variant="default"),
        S(section_type="statement", component_key="statement", eyebrow="Наша ідея",
          heading="Шоколад — це привід зупинитися на хвилину",
          body="Ми робимо невеликі партії, щоб кожен набір виглядав як особистий жест, а не як коробка з полиці супермаркету.",
          style_variant="soft"),
        S(section_type="benefits", eyebrow="Чому Fortuna Nova",
          heading="Що відрізняє наш набір від звичайної коробки",
          body="Три речі, на які варто звернути увагу, коли обираєте подарунок.",
          items=["Невеликі партії — цукерки готуються під замовлення, а не лежать місяцями на складі",
                 "Подарункова подача — коробка, яку не соромно вручити без додаткової упаковки",
                 "Чесний склад — точний перелік інгредієнтів вказаний на сторінці кожного набору"],
          style_variant="default"),
        S(section_type="products", eyebrow="Колекції", heading="Два формати для різних приводів",
          body="Невеликий набір для знайомства або більший — для свята та компанії.",
          cta_label="Перейти до магазину", cta_url="/shop/", style_variant="soft"),
        S(section_type="process", eyebrow="Як замовити", heading="Від вибору до подарунка — три кроки",
          body="Оформлення займає кілька хвилин.",
          items=["Оберіть набір — порівняйте формати в каталозі",
                 "Залиште замовлення — вкажіть контакт для підтвердження",
                 "Отримайте коробку — ми узгодимо зручну доставку"],
          style_variant="default"),
        S(section_type="faq", eyebrow="Питання", heading="Перед замовленням часто запитують",
          body="Коротко про найважливіше.",
          items=["Чи можна обрати смаки? — Напишіть нам через форму, і ми підкажемо доступні варіанти",
                 "Де подивитися склад? — Склад та алергени вказані на сторінці кожного набору",
                 "Як довго зберігаються цукерки? — Термін зберігання зазначений на упаковці"],
          style_variant="soft"),
        S(section_type="cta", heading="Подаруйте смак, який запам'ятається",
          body="Оберіть свій набір у каталозі або напишіть нам — допоможемо з вибором.",
          cta_label="Обрати цукерки", cta_url="/shop/", style_variant="dark"),
    ]
    page = PageExperienceSpec(page_name="Головна", page_slug="home", page_goal="Продаж наборів",
                              sections=[s.section_type for s in sections], section_specs=sections,
                              seo=SeoSpec(slug="/", title="Fortuna Nova", meta_description="Набори цукерок", h1=sections[0].heading))
    L = SectionLayoutSpec
    layout = PageLayoutSpec(page_slug="home", sections=[
        L(section_index=0, composition="split", hero_scene="editorial" if with_media else "typographic",
          hero_height="tall", visual_treatment="media" if with_media else "typography", heading_emphasis="dramatic", motif="halo"),
        L(section_index=1, composition="centered", content_alignment="center", heading_emphasis="dramatic"),
        L(section_index=2, card_presentation="bento", card_columns=3, accent_detail="index"),
        L(section_index=3, card_presentation="grid", card_columns=2),
        L(section_index=4, card_presentation="timeline", card_columns=3) if "timeline" in L.model_fields["card_presentation"].annotation.__args__ else L(section_index=4, card_presentation="list"),
        L(section_index=5, composition="split"),
        L(section_index=6, composition="centered", content_alignment="center", motif="halo"),
    ])
    ds = DesignSystem(primary="#4A2C1E", accent="#B8864B", background="#FBF6EE", surface="#F2E7D8",
                      text="#22150F", muted="#6B5446", heading_font="Cormorant Garamond", body_font="Manrope",
                      radius=14, section_spacing=104)
    if direction == "minimal":
        # Same copy, different Creative Direction: graphic minimalism.
        ds = DesignSystem(primary="#1B1B1F", accent="#C2502E", background="#FFFFFF", surface="#F3F1EE",
                          text="#141416", muted="#5E5A57", heading_font="Unbounded", body_font="Jost",
                          radius=4, section_spacing=112)
        page.section_specs[-1] = page.section_specs[-1].model_copy(update={"style_variant": "accent"})
        layout = PageLayoutSpec(page_slug="home", sections=[
            L(section_index=0, composition="centered", hero_scene="editorial" if with_media else "typographic",
              hero_height="standard", visual_treatment="media" if with_media else "typography", heading_emphasis="balanced"),
            L(section_index=1, composition="centered", content_alignment="center", heading_emphasis="calm"),
            L(section_index=2, card_presentation="list"),
            L(section_index=3, card_presentation="grid", card_columns=2),
            L(section_index=4, card_presentation="timeline"),
            L(section_index=5, composition="split"),
            L(section_index=6, composition="centered", content_alignment="center"),
        ])
    media = [{"id": 55, "url": "https://wp.local/hero.webp", "preferred_home_hero": True, "alt": "Цукерки"}] if with_media else []
    return page, layout, ds, media


def _dim(v) -> str:
    if isinstance(v, dict) and "size" in v:
        return f"{v['size']}{v.get('unit', 'px')}"
    return ""


def _box(v) -> str:
    if not isinstance(v, dict):
        return ""
    u = v.get("unit", "px")
    return " ".join(f"{v.get(k, 0)}{u}" for k in ("top", "right", "bottom", "left"))


def element_css(node: dict, eid: str) -> str:
    """Approximate the CSS Elementor generates from element settings."""
    s = node.get("settings", {})
    # Same specificity as Elementor's generated post CSS (.elementor-<post> ...).
    sel = f".elementor-1 .elementor-element.elementor-element-{eid}"
    rules: list[str] = []
    if node["elType"] == "container":
        d = []
        if s.get("background_color"):
            d.append(f"background-color:{s['background_color']}")
        if s.get("padding"):
            d.append(f"padding:{_box(s['padding'])}")
        if s.get("border_radius"):
            d.append(f"border-radius:{_box(s['border_radius'])}")
        if s.get("gap"):
            d.append(f"gap:{_dim(s['gap'])}")
        if s.get("flex_direction"):
            d.append(f"flex-direction:{s['flex_direction']}")
        if s.get("flex_wrap"):
            d.append(f"flex-wrap:{s['flex_wrap']}")
        if s.get("align_items"):
            d.append(f"align-items:{s['align_items']}")
        if s.get("justify_content"):
            d.append(f"justify-content:{s['justify_content']}")
        if s.get("width"):
            d.append(f"--width:{_dim(s['width'])};width:var(--width)")
        rules.append(f"{sel}{{{';'.join(d)}}}")
        mob = []
        if s.get("width_mobile"):
            mob.append(f"--width:{_dim(s['width_mobile'])}")
        if s.get("flex_direction_mobile"):
            mob.append(f"flex-direction:{s['flex_direction_mobile']}")
        if mob:
            rules.append(f"@media(max-width:767px){{{sel}{{{';'.join(mob)}}}}}")
        return "".join(rules)
    t = node.get("widgetType")
    if t == "heading":
        d = []
        if s.get("title_color"):
            d.append(f"color:{s['title_color']}")
        if s.get("typography_font_family"):
            d.append(f"font-family:'{s['typography_font_family']}'")
        if s.get("typography_font_size"):
            d.append(f"font-size:{_dim(s['typography_font_size'])}")
        if s.get("typography_font_weight"):
            d.append(f"font-weight:{s['typography_font_weight']}")
        if s.get("typography_line_height"):
            d.append(f"line-height:{_dim(s['typography_line_height'])}")
        rules.append(f"{sel} .elementor-heading-title{{{';'.join(d)}}}")
        rules.append(_responsive(s, f"{sel} .elementor-heading-title"))
    elif t == "text-editor":
        d = []
        if s.get("text_color"):
            d.append(f"color:{s['text_color']}")
        if s.get("typography_font_family"):
            d.append(f"font-family:'{s['typography_font_family']}'")
        if s.get("typography_font_size"):
            d.append(f"font-size:{_dim(s['typography_font_size'])}")
        if s.get("typography_line_height"):
            d.append(f"line-height:{_dim(s['typography_line_height'])}")
        rules.append(f"{sel}{{{';'.join(d)}}}")
        rules.append(_responsive(s, sel))
    elif t == "button":
        d = []
        if s.get("background_color"):
            d.append(f"background-color:{s['background_color']}")
        if s.get("button_text_color"):
            d.append(f"color:{s['button_text_color']}")
        if s.get("typography_font_family"):
            d.append(f"font-family:'{s['typography_font_family']}'")
        if s.get("border_radius"):
            d.append(f"border-radius:{_box(s['border_radius'])}")
        if s.get("typography_font_weight"):
            d.append(f"font-weight:{s['typography_font_weight']}")
        rules.append(f"{sel} .elementor-button{{{';'.join(d)}}}")
    elif t == "icon":
        if s.get("primary_color"):
            rules.append(f"{sel} .elementor-icon{{color:{s['primary_color']}}}")
    elif t == "divider":
        if s.get("color"):
            rules.append(f"{sel} .elementor-divider-separator{{border-color:{s['color']}}}")
    return "".join(rules)


def _responsive(s: dict, selector: str) -> str:
    out = ""
    if s.get("typography_font_size_tablet"):
        out += f"@media(max-width:1024px){{{selector}{{font-size:{_dim(s['typography_font_size_tablet'])}}}}}"
    if s.get("typography_font_size_mobile"):
        out += f"@media(max-width:767px){{{selector}{{font-size:{_dim(s['typography_font_size_mobile'])}}}}}"
    return out


ICON_SVG = '<svg viewBox="0 0 24 24" width="1em" height="1em" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M12 3l2.6 5.6 6.1.7-4.5 4.2 1.2 6L12 16.6 6.6 19.5l1.2-6L3.3 9.3l6.1-.7z"/></svg>'


def render(node: dict, css: list[str], counter: list[int]) -> str:
    counter[0] += 1
    eid = node.get("id") or f"x{counter[0]}"
    eid = f"{eid}-{counter[0]}"
    css.append(element_css(node, eid))
    s = node.get("settings", {})
    classes = f"elementor-element elementor-element-{eid} " + s.get("css_classes", s.get("_css_classes", ""))
    anchor = f' id="{escape(s["_element_id"], quote=True)}"' if s.get("_element_id") else ""
    if node["elType"] == "container":
        inner = "".join(render(ch, css, counter) for ch in node.get("elements", []))
        boxed = s.get("content_width") == "boxed"
        if boxed:
            inner = f'<div class="e-con-inner">{inner}</div>'
        return f'<div{anchor} class="e-con e-flex {"e-con-boxed" if boxed else "e-con-full"} {escape(classes, quote=True)}">{inner}</div>'
    kind = node.get("widgetType", "widget")
    if kind == "heading":
        tag = s.get("header_size", "h2")
        tag = tag if tag in ("div", "h1", "h2", "h3", "h4", "p", "span") else "div"
        child = f'<{tag} class="elementor-heading-title elementor-size-default">{s.get("title", "")}</{tag}>'
    elif kind == "text-editor":
        child = s.get("editor", "")
    elif kind == "button":
        child = f'<div class="elementor-button-wrapper"><a class="elementor-button elementor-size-{s.get("size", "md")}" href="#"><span class="elementor-button-content-wrapper"><span class="elementor-button-text">{escape(str(s.get("text", "")))}</span></span></a></div>'
    elif kind == "image":
        child = f'<img src="{IMAGE}" alt="Synthetic test graphic" width="1200" height="1400">'
    elif kind == "icon":
        icon = escape(str((s.get("selected_icon") or {}).get("value", "")), quote=True)
        child = f'<div class="elementor-icon-wrapper"><div class="elementor-icon"><i class="{icon}" aria-hidden="true"></i></div></div>' if icon else ICON_SVG
    elif kind == "divider":
        child = '<div class="elementor-divider"><span class="elementor-divider-separator"></span></div>'
    elif kind == "shortcode":
        child = '<div class="elementor-shortcode"><form class="wpcf7-form"><p><label>Ім’я<br><input type="text"></label></p><p><label>Email<br><input type="email"></label></p><p><input type="submit" value="Надіслати" class="wpcf7-submit"></p></form></div>'
    else:
        child = ""
    return f'<div class="elementor-widget elementor-widget-{escape(kind)} {escape(classes, quote=True)}"><div class="elementor-widget-container">{child}</div></div>'


ELEMENTOR_BASE = """
*{box-sizing:border-box}html,body{margin:0;padding:0}
body{font:16px/1.5 Manrope,system-ui,sans-serif;-webkit-font-smoothing:antialiased}
.e-con{display:flex;flex-direction:column;position:relative;min-width:0}
.e-con-boxed>.e-con-inner{display:flex;flex-direction:inherit;flex-wrap:inherit;gap:inherit;align-items:inherit;justify-content:inherit;width:100%;max-width:1180px;margin:0 auto}
.elementor-heading-title{margin:0;padding:0}
.elementor-widget-text-editor p{margin:0 0 .6em}.elementor-widget-text-editor p:last-child{margin-bottom:0}
.elementor-button{display:inline-block;padding:15px 30px;font-size:15px;line-height:1;text-decoration:none;background:#69727d;color:#fff;transition:all .3s}
.elementor-icon{display:inline-block;font-size:50px;line-height:1;color:#69727d}
.elementor-divider{display:flex;padding:12px 0}.elementor-divider-separator{display:block;width:100%;border-top:1px solid #d5d8dc}
img{max-width:100%;height:auto;display:block}
.site-header{display:flex;justify-content:space-between;align-items:center;padding:18px 32px;font:600 15px Manrope}
.site-header nav a{margin-left:26px;text-decoration:none}
@media(max-width:600px){.site-header{flex-wrap:wrap;gap:8px;padding:14px 20px}.site-header nav a{margin:0 16px 0 0}}
"""


def build_html(elements: list[dict], css_files: list[Path], ds: DesignSystem) -> str:
    css: list[str] = []
    counter = [0]
    body = "".join(render(x, css, counter) for x in elements)
    site_vars = (f":root{{--tai-primary:{ds.primary};--tai-accent:{ds.accent};--tai-bg:{ds.background};"
                 f"--tai-surface:{ds.surface};--tai-text:{ds.text};--tai-muted:{ds.muted};--tai-radius:{ds.radius}px;"
                 f"--tai-on-primary:#FFFFFF;--tai-heading-font:'{ds.heading_font}',serif;--tai-body-font:'{ds.body_font}',sans-serif}}"
                 f"body.thesis-ai-generated{{background:var(--tai-bg);color:var(--tai-text)}}"
                 f"body.thesis-ai-generated .site-header{{background:var(--tai-bg);color:var(--tai-primary)}}"
                 f"body.thesis-ai-generated .site-header a{{color:var(--tai-text)}}")
    plugin_css = "".join(f"<style>{p.read_text()}</style>" for p in css_files if p.is_file())
    return ("<!doctype html><html lang=uk><head><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<link rel=stylesheet href='{FONTS}'><link rel=stylesheet href='{FA}'><style>{ELEMENTOR_BASE}</style>"
            f"<style>{''.join(css)}</style><style>{site_vars}</style>{plugin_css}</head>"
            "<body class='page thesis-ai-generated'>"
            f"<header class='site-header'><strong style=\"font-family:'{ds.heading_font}';font-size:24px\">Fortuna Nova</strong>"
            "<nav><a href='#'>Головна</a><a href='#'>Магазин</a><a href='#'>Контакти</a></nav></header>"
            f"<main class='site-main'><div class='elementor elementor-1'>{body}</div></main></body></html>")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?", default=str(ROOT / "qa" / "rich-evidence"))
    ap.add_argument("--plugin", default=str(ROOT / "plugin" / "thesis-ai-bridge"))
    ap.add_argument("--tag", default="current")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--direction", default="warm", choices=["warm", "minimal"])
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    assets = Path(args.plugin) / "assets"
    css_files = [assets / "front.css", assets / "visual-composer.css", assets / "rich-sections.css"]
    results = []
    variants = {}
    for with_media in (False, True):
        page, layout, ds, media = fortuna_home(with_media, args.direction)
        elements = compile_elementor_page(page, ds, media=media, layout=layout, product_names=["Асорті 16 цукерок", "Асорті 24 цукерки"])
        name = f"{args.tag}-{'photo' if with_media else 'type'}"
        html = build_html(elements, css_files, ds)
        (out / f"{name}.html").write_text(html)
        variants[name] = html
    if args.no_browser:
        print("HTML written to", out)
        return
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox"])
        for name, html in variants.items():
            for width in (1440, 390):
                # Reduced motion = final state of scroll-reveal animations in a full-page capture.
                p = browser.new_page(viewport={"width": width, "height": 900}, reduced_motion="reduce")
                errors: list[str] = []
                p.on("pageerror", lambda e: errors.append(str(e)))
                p.set_content(html, wait_until="networkidle")
                p.wait_for_timeout(400)
                metrics = p.evaluate("""() => {
                  const sw = document.documentElement.scrollWidth;
                  const hs = [...document.querySelectorAll('h1,h2,h3')].filter(h => {
                    const r = h.getBoundingClientRect(); return r.width > 0 && (r.left < -2 || r.right > innerWidth + 2);});
                  return {scrollWidth: sw, clippedHeadings: hs.length, h1: document.querySelectorAll('h1').length,
                          height: document.documentElement.scrollHeight};
                }""")
                metrics.update(variant=name, viewport=width, errors=errors)
                results.append(metrics)
                p.screenshot(path=str(out / f"{name}-{width}.png"), full_page=True)
                p.close()
        browser.close()
    (out / f"{args.tag}-results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    bad = [r for r in results if r["scrollWidth"] > r["viewport"] + 2 or r["clippedHeadings"] or r["h1"] != 1 or r["errors"]]
    print(json.dumps(results, ensure_ascii=False))
    if bad:
        raise SystemExit(f"FAIL: {bad}")
    print("PASS", len(results), "synthetic viewport checks ->", out)


if __name__ == "__main__":
    main()
