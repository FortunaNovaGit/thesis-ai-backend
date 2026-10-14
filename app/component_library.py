from __future__ import annotations

import html
import secrets
from typing import Any

from .models import DesignSystem, PageExperienceSpec, SectionContentSpec


def _eid() -> str:
    return secrets.token_hex(4)


def _px(size: int) -> dict[str, Any]:
    return {"unit": "px", "size": size, "sizes": []}


def _box(top: int, right: int, bottom: int, left: int) -> dict[str, Any]:
    return {"unit": "px", "top": str(top), "right": str(right), "bottom": str(bottom), "left": str(left), "isLinked": False}


def _widget(widget_type: str, settings: dict[str, Any]) -> dict[str, Any]:
    return {"id": _eid(), "elType": "widget", "widgetType": widget_type, "isInner": False, "settings": settings, "elements": []}


def _container(elements: list[dict[str, Any]], settings: dict[str, Any] | None = None) -> dict[str, Any]:
    base: dict[str, Any] = {
        "content_width": "boxed",
        "flex_direction": "column",
        "gap": _px(20),
        "padding": _box(56, 24, 56, 24),
    }
    if settings:
        base.update(settings)
    return {"id": _eid(), "elType": "container", "isInner": False, "settings": base, "elements": elements}


def _heading(text: str, color: str, *, level: str = "h2") -> dict[str, Any]:
    return _widget("heading", {
        "title": html.escape(text, quote=False),
        "header_size": level,
        "title_color": color,
    })


def _text(text: str, color: str) -> dict[str, Any]:
    return _widget("text-editor", {
        "editor": f"<p>{html.escape(text, quote=False)}</p>",
        "text_color": color,
    })


def _button(label: str, url: str, ds: DesignSystem, *, accent: bool = False) -> dict[str, Any]:
    return _widget("button", {
        "text": html.escape(label, quote=False),
        "link": {"url": url, "is_external": "", "nofollow": ""},
        "size": "md",
        "background_color": ds.accent if accent else ds.primary,
        "button_text_color": "#FFFFFF",
        "border_radius": _box(ds.radius, ds.radius, ds.radius, ds.radius),
    })


def _surface_card(title: str, body: str, ds: DesignSystem) -> dict[str, Any]:
    elements = [_heading(title, ds.text, level="h3")]
    if body:
        elements.append(_text(body, ds.muted))
    return _container(elements, {
        "background_background": "classic",
        "background_color": ds.background,
        "padding": _box(26, 26, 26, 26),
        "border_radius": _box(ds.radius, ds.radius, ds.radius, ds.radius),
        "border_border": "solid",
        "border_width": _box(1, 1, 1, 1),
        "border_color": "#E2E8F0",
    })


def _split_items(items: list[str]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for item in items[:8]:
        if " — " in item:
            title, body = item.split(" — ", 1)
        elif ": " in item:
            title, body = item.split(": ", 1)
        else:
            title, body = item, ""
        result.append((title.strip(), body.strip()))
    return result


def _colors(section: SectionContentSpec, ds: DesignSystem) -> tuple[str, str, str]:
    if section.style_variant == "dark":
        return ds.primary, "#FFFFFF", "#E2E8F0"
    if section.style_variant == "accent":
        return ds.accent, "#FFFFFF", "#F8FAFC"
    if section.style_variant == "soft":
        return ds.surface, ds.text, ds.muted
    return ds.background, ds.text, ds.muted


def _section_shell(section: SectionContentSpec, body: list[dict[str, Any]], ds: DesignSystem) -> dict[str, Any]:
    bg, _, _ = _colors(section, ds)
    return _container(body, {
        "background_background": "classic",
        "background_color": bg,
        "css_classes": f"thesis-ai-section thesis-ai-{section.section_type} thesis-ai-{section.component_key}",
        "padding": _box(ds.section_spacing, 24, ds.section_spacing, 24),
    })


def _intro(section: SectionContentSpec, ds: DesignSystem, *, h1: bool = False) -> list[dict[str, Any]]:
    _, title_color, body_color = _colors(section, ds)
    out: list[dict[str, Any]] = []
    if section.eyebrow:
        out.append(_widget("heading", {
            "title": html.escape(section.eyebrow.upper(), quote=False),
            "header_size": "div",
            "title_color": ds.accent if section.style_variant not in {"accent", "dark"} else "#FFFFFF",
        }))
    out.append(_heading(section.heading, title_color, level="h1" if h1 else "h2"))
    if section.body:
        out.append(_text(section.body, body_color))
    return out


def hero(section: SectionContentSpec, ds: DesignSystem) -> dict[str, Any]:
    left = _container(_intro(section, ds, h1=True) + ([
        _button(section.cta_label, section.cta_url or "#", ds, accent=section.style_variant == "dark")
    ] if section.cta_label else []), {
        "content_width": "full",
        "padding": _box(18, 18, 18, 18),
        "flex_grow": 1,
    })
    side_title = "Ваш наступний крок"
    side_body = section.section_goal or "Оберіть потрібний розділ або скористайтеся основною дією сторінки."
    right = _surface_card(side_title, side_body, ds)
    row = _container([left, right], {
        "content_width": "boxed",
        "flex_direction": "row",
        "flex_direction_mobile": "column",
        "align_items": "center",
        "gap": _px(36),
        "padding": _box(0, 0, 0, 0),
    })
    return _section_shell(section, [row], ds)


def cards(section: SectionContentSpec, ds: DesignSystem) -> dict[str, Any]:
    body = _intro(section, ds)
    item_cards = [_surface_card(title, text, ds) for title, text in _split_items(section.items)]
    if item_cards:
        body.append(_container(item_cards, {
            "content_width": "full",
            "flex_direction": "row",
            "flex_wrap": "wrap",
            "flex_direction_mobile": "column",
            "gap": _px(18),
            "padding": _box(18, 0, 12, 0),
        }))
    if section.cta_label:
        body.append(_button(section.cta_label, section.cta_url or "#", ds))
    return _section_shell(section, body, ds)


def faq(section: SectionContentSpec, ds: DesignSystem) -> dict[str, Any]:
    body = _intro(section, ds)
    for title, text in _split_items(section.items):
        body.append(_surface_card(title, text, ds))
    return _section_shell(section, body, ds)


def booking(section: SectionContentSpec, ds: DesignSystem) -> dict[str, Any]:
    intro = _intro(section, ds)
    intro.append(_widget("shortcode", {"shortcode": '[contact-form-7 title="AI Contact"]'}))
    return _section_shell(section, intro, ds)


def simple_content(section: SectionContentSpec, ds: DesignSystem) -> dict[str, Any]:
    body = _intro(section, ds)
    if section.items:
        body.extend(_surface_card(t, b, ds) for t, b in _split_items(section.items))
    if section.cta_label:
        body.append(_button(section.cta_label, section.cta_url or "#", ds, accent=section.style_variant == "dark"))
    return _section_shell(section, body, ds)


COMPONENTS = {
    "hero": hero,
    "services": cards,
    "benefits": cards,
    "trust": cards,
    "team": cards,
    "process": cards,
    "stats": cards,
    "products": cards,
    "faq": faq,
    "booking": booking,
    "contact": simple_content,
    "cta": simple_content,
    "content": simple_content,
}


def compile_elementor_page(page: PageExperienceSpec, ds: DesignSystem) -> list[dict[str, Any]]:
    elements: list[dict[str, Any]] = []
    specs = page.section_specs
    if not specs:
        specs = [SectionContentSpec(section_type="content", heading=page.page_name, body=page.page_goal)]
    for index, section in enumerate(specs):
        # First section is always treated as a hero if the Design agent forgot one.
        section_type = section.section_type.lower().strip() or "content"
        if index == 0 and section_type not in {"hero", "products"}:
            section_type = "hero"
        renderer = COMPONENTS.get(section_type, simple_content)
        elements.append(renderer(section, ds))
    return elements


def compile_gutenberg_page(page: PageExperienceSpec) -> str:
    parts: list[str] = []
    for index, section in enumerate(page.section_specs):
        level = 1 if index == 0 else 2
        tag = "h1" if level == 1 else "h2"
        parts.append(
            '<!-- wp:group {"layout":{"type":"constrained"}} --><div class="wp-block-group">'
            f'<!-- wp:heading {{"level":{level}}} --><{tag} class="wp-block-heading">{html.escape(section.heading)}</{tag}><!-- /wp:heading -->'
        )
        if section.body:
            parts.append(f'<!-- wp:paragraph --><p>{html.escape(section.body)}</p><!-- /wp:paragraph -->')
        if section.items:
            lis = "".join(f"<li>{html.escape(x)}</li>" for x in section.items)
            parts.append(f'<!-- wp:list --><ul>{lis}</ul><!-- /wp:list -->')
        parts.append('</div><!-- /wp:group -->')
    return "\n".join(parts)
