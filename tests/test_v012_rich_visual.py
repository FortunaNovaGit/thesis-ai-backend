"""v0.12 Rich Visual System: offline contract tests (no OpenAI, no WordPress)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.component_library import (ALLOWED_ICONS, balance_rhythm, choose_icon,
                                   compile_elementor_page)
from app.creative_pipeline import CreativeFoundation, CreativePage
from app.design_safety import cyrillic_font, cyrillic_safe_fonts
from app.models import (DesignSystem, PageExperienceSpec, PageLayoutSpec,
                        SectionContentSpec, SectionLayoutSpec, SeoSpec)

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugin" / "thesis-ai-bridge"
PHP_WIDGETS = {"heading", "text-editor", "button", "image", "icon", "spacer", "divider", "shortcode"}


def walk(nodes):
    for node in nodes:
        yield node
        yield from walk(node.get("elements", []))


def home(**hero_kwargs) -> PageExperienceSpec:
    S = SectionContentSpec
    hero = dict(section_type="hero", eyebrow="Шоколадна майстерня", heading="Цукерки, які хочеться дарувати повільно",
                body="Авторські набори шоколадних цукерок ручної роботи для подарунка.",
                items=["Ручна робота — кожна цукерка декорується вручну", "Подарункові набори — 16 і 24 цукерки"],
                cta_label="Обрати цукерки", cta_url="/shop/",
                secondary_cta_label="Як замовити", secondary_cta_url="#process")
    hero.update(hero_kwargs)
    sections = [
        S(**hero),
        S(section_type="statement", heading="Шоколад — це привід зупинитися", body="Ми робимо невеликі партії для особистих подарунків."),
        S(section_type="benefits", heading="Що відрізняє наш набір", body="Три речі, на які варто звернути увагу.",
          items=["Невеликі партії — готуємо під замовлення", "Подарункова подача — коробка без додаткової упаковки",
                 "Чесний склад — перелік інгредієнтів на сторінці набору"]),
        S(section_type="process", heading="Три кроки до подарунка", body="Оформлення займає кілька хвилин.",
          items=["Оберіть набір — у каталозі", "Залиште замовлення — через форму", "Отримайте коробку — узгодимо доставку"]),
        S(section_type="faq", heading="Перед замовленням запитують", body="Коротко про головне.",
          items=["Де склад? — На сторінці кожного набору", "Чи можна обрати смаки? — Напишіть нам через форму"]),
        S(section_type="cta", heading="Подаруйте смак, який запам'ятається", body="Оберіть набір у каталозі.",
          cta_label="Обрати цукерки", cta_url="/shop/", style_variant="dark"),
    ]
    return PageExperienceSpec(page_name="Головна", page_slug="home", page_goal="Продаж",
                              sections=[s.section_type for s in sections], section_specs=sections,
                              seo=SeoSpec(slug="/", title="Fortuna Nova", meta_description="Набори", h1=sections[0].heading))


def test_cyrillic_font_guard_replaces_latin_only_families():
    assert cyrillic_font("Poppins", role="body") == "Manrope"
    assert cyrillic_font("Fraunces", role="heading") == "Cormorant Garamond"
    assert cyrillic_font("DM Serif Display", role="heading") == "Cormorant Garamond"
    assert cyrillic_font("playfair  display", role="heading") == "Playfair Display"
    ds = cyrillic_safe_fonts(DesignSystem(heading_font="Syne", body_font="Cormorant Garamond"))
    assert ds.heading_font == "Unbounded"
    assert ds.body_font == "Manrope"  # display serif is not used as 16px body copy


def test_creative_foundation_applies_font_guard():
    foundation = CreativeFoundation.model_validate({
        "design_direction": "Теплий редакційний люкс із шоколадною палітрою",
        "design_system": {"heading_font": "Fraunces", "body_font": "DM Sans"},
        "candidates": [
            {"id": "editorial", "name": "Editorial", "narrative": "Велика серифна типографіка та повітря.",
             "composition": "Асиметрична сітка з акцентами", "typographic_contrast": "serif + sans", "visual_motif": "концентричні кільця"},
            {"id": "poster", "name": "Poster", "narrative": "Плакатний ритм із темними смугами.",
             "composition": "Центровані блоки та смуги", "typographic_contrast": "display + sans", "visual_motif": "тонкі горизонтальні лінії"},
        ],
        "selected_direction_id": "editorial", "selection_reason": "Найкраще передає ручну роботу.",
    })
    assert foundation.design_system.heading_font == "Cormorant Garamond"
    assert foundation.design_system.body_font == "Manrope"


def _creative_section(kind, **extra):
    base = {"kind": kind, "headline": f"Заголовок секції {kind} з деталями",
            "body": f"Корисний конкретний опис для секції {kind}, щоб відвідувач зрозумів наступний крок.",
            "composition": "split", "visual_treatment": "typography", "surface_treatment": "canvas",
            "card_presentation": "grid"}
    base.update(extra)
    return base


def test_creative_contract_accepts_statement_timeline_and_secondary_cta():
    page = CreativePage.model_validate({
        "page_slug": "home", "seo_title": "Fortuna Nova — цукерки ручної роботи",
        "meta_description": "Авторські набори шоколадних цукерок ручної роботи для подарунка та свята.",
        "sections": [
            _creative_section("hero", cta_label="Обрати цукерки", cta_url="/shop/",
                              secondary_cta_label="Як замовити", secondary_cta_url="#process"),
            _creative_section("statement"),
            _creative_section("process", card_presentation="timeline"),
        ]})
    assert page.sections[1].kind == "statement"
    assert page.sections[2].card_presentation == "timeline"


@pytest.mark.parametrize("url,label", [("https://evil.example", "Як замовити"), ("/shop/", "Обрати цукерки")])
def test_creative_contract_rejects_unsafe_or_duplicate_secondary_cta(url, label):
    with pytest.raises(ValidationError, match="secondary CTA"):
        CreativePage.model_validate({
            "page_slug": "home", "seo_title": "Fortuna Nova — цукерки ручної роботи",
            "meta_description": "Авторські набори шоколадних цукерок ручної роботи для подарунка та свята.",
            "sections": [_creative_section("hero", cta_label="Обрати цукерки", cta_url="/shop/",
                                           secondary_cta_label=label, secondary_cta_url=url),
                         _creative_section("cta")]})


def test_rich_home_compiles_to_allowlisted_native_widgets():
    nodes = list(walk(compile_elementor_page(home(), DesignSystem())))
    widgets = {n["widgetType"] for n in nodes if n["elType"] == "widget"}
    assert widgets <= PHP_WIDGETS
    assert "icon" in widgets
    icons = [n["settings"]["selected_icon"]["value"] for n in nodes if n.get("widgetType") == "icon"]
    assert icons and set(icons) <= ALLOWED_ICONS
    for node in nodes:
        for key in ("css_classes", "_css_classes"):
            for token in node["settings"].get(key, "").split():
                assert re.fullmatch(r"[a-z0-9_-]+", token), token
    assert sum(n.get("widgetType") == "heading" and n["settings"].get("header_size") == "h1" for n in nodes) == 1


def test_hero_has_highlights_and_secondary_ghost_action():
    nodes = list(walk(compile_elementor_page(home(), DesignSystem())))
    classes = " ".join(n["settings"].get("css_classes", "") + " " + n["settings"].get("_css_classes", "") for n in nodes)
    assert "tai-hero-highlights" in classes and "tai-btn-ghost" in classes and "tai-actions" in classes
    buttons = [n["settings"] for n in nodes if n.get("widgetType") == "button"]
    assert {"/shop/", "#process"} <= {b["link"]["url"] for b in buttons}
    anchors = {n["settings"].get("_element_id") for n in nodes if n["elType"] == "container"}
    assert "process" in anchors  # the secondary CTA target exists on the page


def test_hero_without_secondary_has_single_primary_button():
    page = home(secondary_cta_label=None, secondary_cta_url=None)
    hero = compile_elementor_page(page, DesignSystem())[0]
    assert sum(n.get("widgetType") == "button" for n in walk([hero])) == 1


def test_planning_notes_never_become_hero_highlights():
    page = home(items=["Основна посадкова сторінка, що пояснює цінність і веде до головної конверсії"])
    hero = compile_elementor_page(page, DesignSystem())[0]
    assert not any("tai-hero-highlights" in n["settings"].get("css_classes", "") for n in walk([hero]))


def test_presentations_and_faq_disclosure():
    layout = PageLayoutSpec(page_slug="home", sections=[
        SectionLayoutSpec(section_index=0), SectionLayoutSpec(section_index=2, card_presentation="bento"),
        SectionLayoutSpec(section_index=3, card_presentation="grid")])
    nodes = list(walk(compile_elementor_page(home(), DesignSystem(), layout=layout)))
    classes = " ".join(n["settings"].get("css_classes", "") for n in nodes)
    assert "tai-cards-bento" in classes
    assert "tai-cards-timeline" in classes  # process steps never render as an equal grid
    faq = [n["settings"]["editor"] for n in nodes if "tai-faq" in n["settings"].get("_css_classes", "")]
    assert len(faq) == 2 and all(e.startswith('<details class="tai-faq-item"') for e in faq)
    assert faq[0].startswith('<details class="tai-faq-item" open>')


def test_emphasis_is_escaped_and_preserves_words():
    page = home(heading="Шоколад <script>alert(1)</script> для близьких людей")
    h1 = next(n for n in walk(compile_elementor_page(page, DesignSystem())) if n["settings"].get("header_size") == "h1")
    assert "<script>" not in h1["settings"]["title"]
    assert re.sub(r"<[^>]+>", "", h1["settings"]["title"]).replace("&lt;", "<").replace("&gt;", ">") == page.section_specs[0].heading


def test_balance_rhythm_breaks_three_identical_light_bands_only():
    S = SectionContentSpec
    specs = [S(section_type="content", heading=f"Секція {i}", style_variant=v)
             for i, v in enumerate(["default", "default", "default", "dark", "dark", "dark"])]
    out = [s.style_variant for s in balance_rhythm(specs)]
    assert out == ["default", "default", "soft", "dark", "dark", "dark"]


def test_icon_choice_is_deterministic_and_unique_within_section():
    used: set[str] = set()
    a = choose_icon("Подарункова подача", 0, used)
    b = choose_icon("Подарунок для мами", 1, used)
    assert a == "fas fa-gift" and b != a and b in ALLOWED_ICONS


def _top_level_split(selector: str) -> list[str]:
    parts, depth, current = [], 0, ""
    for ch in selector:
        depth += ch == "("
        depth -= ch == ")"
        if ch == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += ch
    return parts + [current]


def test_rich_css_is_scoped_and_static():
    css = (PLUGIN / "assets" / "rich-sections.css").read_text()
    # Inline data: SVG (xmlns string) is allowed; network URLs are not.
    network = re.sub(r'url\("data:[^"]*"\)', "", css)
    assert "@import" not in css and "url(http" not in network and "http://" not in network and "https://" not in css and "expression(" not in css
    body = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    body = re.sub(r"@keyframes[^{]*\{(?:[^{}]*\{[^{}]*\})*\s*\}", "", body)  # animation steps
    body = re.sub(r"@(?:media|supports)[^{]*\{", "", body)  # unwrap conditional groups
    selectors = re.findall(r"(?:^|})\s*([^{}@][^{}]*)\{", body)
    for selector in selectors:
        sel = selector.strip()
        if not sel or sel.startswith(("from", "to")) or re.fullmatch(r"[\d.%\s,]+", sel):
            continue
        for part in _top_level_split(sel):
            assert part.strip().startswith("body.thesis-ai-generated"), part
    assert "prefers-reduced-motion:reduce" in css


def test_bridge_accepts_rich_settings_and_enqueues_stylesheet():
    php = (PLUGIN / "includes" / "class-thesis-ai-bridge.php").read_text()
    for key in ("'_css_classes'", "'_element_id'", "'typography_font_size_tablet'", "'typography_font_size_mobile'"):
        assert key in php
    assert "assets/rich-sections.css" in php
    assert "--tai-heading-font" in php
    assert "Version: 0.13.0" in (PLUGIN / "thesis-ai-bridge.php").read_text()
