from __future__ import annotations

import html
import secrets
from typing import Any

from .models import DesignSystem, PageExperienceSpec, SectionContentSpec


def _validated_media_url(asset: dict[str, Any]) -> str:
    url = str(asset.get("url", ""))
    return url if url.startswith("https://") and asset.get("id") else ""


def choose_page_media(page: PageExperienceSpec, media: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Use only image attachments explicitly returned by the connected WordPress site."""
    if not media:
        return None
    target = " ".join([page.page_name, page.page_goal, page.page_slug]).casefold()
    scored: list[tuple[int, dict[str, Any]]] = []
    for item in media:
        url = _validated_media_url(item)
        if not url:
            continue
        description = " ".join(str(item.get(k, "")) for k in ("alt", "title", "caption")).casefold()
        score = sum(1 for word in target.split() if len(word) > 3 and word in description)
        scored.append((score, item))
    if not scored:
        return None
    scored.sort(key=lambda pair: pair[0], reverse=True)
    # Do not put an unrelated product photograph on a page merely because one exists.
    return scored[0][1] if scored[0][0] > 0 else None


def _image_widget(media: dict[str, Any]) -> dict[str, Any]:
    return _widget("image", {
        "image": {"id": int(media["id"]), "url": _validated_media_url(media)},
        "image_size": "large",
    })


def _eid() -> str:
    return secrets.token_hex(4)


def _px(size: int) -> dict[str, Any]:
    return {"unit": "px", "size": size, "sizes": []}


def _pct(size: int) -> dict[str, Any]:
    return {"unit": "%", "size": size, "sizes": []}


def _box(top: int, right: int, bottom: int, left: int) -> dict[str, Any]:
    return {"unit": "px", "top": str(top), "right": str(right), "bottom": str(bottom), "left": str(left), "isLinked": False}


def _widget(widget_type: str, settings: dict[str, Any]) -> dict[str, Any]:
    return {"id": _eid(), "elType": "widget", "widgetType": widget_type, "isInner": False, "settings": settings, "elements": []}


def _container(elements: list[dict[str, Any]], settings: dict[str, Any] | None = None) -> dict[str, Any]:
    base: dict[str, Any] = {
        "content_width": "boxed",
        "flex_direction": "column",
        "gap": _px(20),
        "padding": _box(52, 24, 52, 24),
    }
    if settings:
        base.update(settings)
    return {"id": _eid(), "elType": "container", "isInner": False, "settings": base, "elements": elements}


def _heading(text: str, color: str, ds: DesignSystem, *, level: str = "h2", size: int | None = None) -> dict[str, Any]:
    settings: dict[str, Any] = {
        "title": html.escape(text, quote=False),
        "header_size": level,
        "title_color": color,
        "typography_typography": "custom",
        "typography_font_family": ds.heading_font,
        "typography_font_weight": "700",
        "typography_line_height": {"unit": "em", "size": 1.12, "sizes": []},
    }
    if size:
        settings["typography_font_size"] = _px(size)
    return _widget("heading", settings)


def _text(text: str, color: str, ds: DesignSystem, *, size: int = 18) -> dict[str, Any]:
    return _widget("text-editor", {
        "editor": f"<p>{html.escape(text, quote=False)}</p>",
        "text_color": color,
        "typography_typography": "custom",
        "typography_font_family": ds.body_font,
        "typography_font_size": _px(size),
        "typography_line_height": {"unit": "em", "size": 1.65, "sizes": []},
    })


def _button(label: str, url: str, ds: DesignSystem, *, accent: bool = False) -> dict[str, Any]:
    return _widget("button", {
        "text": html.escape(label, quote=False),
        "link": {"url": url, "is_external": "", "nofollow": ""},
        "size": "md",
        "background_color": ds.accent if accent else ds.primary,
        "button_text_color": "#FFFFFF",
        "border_radius": _box(ds.radius, ds.radius, ds.radius, ds.radius),
        "typography_typography": "custom",
        "typography_font_family": ds.body_font,
        "typography_font_weight": "600",
    })


def _surface_card(title: str, body: str, ds: DesignSystem, *, width: int = 31) -> dict[str, Any]:
    elements = [_heading(title, ds.text, ds, level="h3", size=23)]
    if body:
        elements.append(_text(body, ds.muted, ds, size=16))
    return _container(elements, {
        "content_width": "full",
        "width": _pct(width),
        "width_mobile": _pct(100),
        "background_background": "classic",
        "background_color": ds.surface,
        "padding": _box(28, 28, 28, 28),
        "border_radius": _box(ds.radius, ds.radius, ds.radius, ds.radius),
        "gap": _px(12),
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
        return ds.text, "#FFFFFF", "#DCE6EF"
    if section.style_variant == "accent":
        return ds.primary, "#FFFFFF", "#EAF4FA"
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
        "gap": _px(26),
    })


def _intro(section: SectionContentSpec, ds: DesignSystem, *, h1: bool = False) -> list[dict[str, Any]]:
    _, title_color, body_color = _colors(section, ds)
    out: list[dict[str, Any]] = []
    if section.eyebrow:
        out.append(_widget("heading", {
            "title": html.escape(section.eyebrow.upper(), quote=False),
            "header_size": "div",
            "title_color": ds.accent if section.style_variant not in {"accent", "dark"} else "#FFFFFF",
            "typography_typography": "custom",
            "typography_font_family": ds.body_font,
            "typography_font_size": _px(13),
            "typography_font_weight": "700",
        }))
    out.append(_heading(section.heading, title_color, ds, level="h1" if h1 else "h2", size=48 if h1 else 34))
    if section.body:
        out.append(_text(section.body, body_color, ds, size=19 if h1 else 17))
    return out


def hero(section: SectionContentSpec, ds: DesignSystem, media: dict[str, Any] | None = None) -> dict[str, Any]:
    left_elements = _intro(section, ds, h1=True)
    if section.cta_label:
        left_elements.append(_button(section.cta_label, section.cta_url or "#", ds, accent=section.style_variant == "dark"))
    left = _container(left_elements, {
        "content_width": "full",
        "width": _pct(60),
        "width_mobile": _pct(100),
        "padding": _box(12, 12, 12, 12),
        "gap": _px(22),
    })

    item_pairs = _split_items(section.items)
    if media:
        # The image comes from this site's Media Library; never fabricate a stock photo.
        right = _container([_image_widget(media)], {
            "content_width": "full", "width": _pct(40), "width_mobile": _pct(100),
            "background_background": "classic", "background_color": ds.surface,
            "padding": _box(12, 12, 12, 12),
            "border_radius": _box(ds.radius, ds.radius, ds.radius, ds.radius),
        })
    else:
        # Abstract editorial hero: no unrelated stock photos or repetitive filler cards.
        right_bits: list[dict[str, Any]] = []
        if item_pairs:
            for title, body in item_pairs[:2]:
                right_bits.append(_heading(title, "#FFFFFF", ds, level="h3", size=26))
                if body:
                    right_bits.append(_text(body, "#FFFFFF", ds, size=16))
        else:
            right_bits = [
                _heading(section.eyebrow or section.heading, "#FFFFFF", ds, level="h3", size=28),
                _text(section.body[:145] if section.body else "", "#FFFFFF", ds, size=16),
            ]
        right = _container(right_bits, {
            "content_width": "full", "width": _pct(40), "width_mobile": _pct(100),
            "background_background": "classic", "background_color": ds.primary,
            "padding": _box(44, 34, 44, 34), "min_height": _px(300),
            "border_radius": _box(ds.radius, ds.radius, ds.radius, ds.radius),
            "justify_content": "center", "gap": _px(16),
        })

    row = _container([left, right], {
        "content_width": "boxed",
        "flex_direction": "row",
        "flex_direction_mobile": "column",
        "align_items": "center",
        "gap": _px(42),
        "padding": _box(0, 0, 0, 0),
    })
    return _section_shell(section, [row], ds)


def cards(section: SectionContentSpec, ds: DesignSystem, media: dict[str, Any] | None = None, *, live_catalog: bool = False) -> dict[str, Any]:
    body = _intro(section, ds)
    pairs = _split_items(section.items)
    item_cards = [_surface_card(title, text, ds, width=31 if len(pairs) >= 3 else 48) for title, text in pairs]
    if section.section_type == "products" and live_catalog:
        # Render actual WooCommerce products when present. The shortcode does not
        # create fictitious demo catalog entries.
        body.append(_container([_widget("shortcode", {"shortcode": '[products limit="6" columns="3" orderby="date" order="DESC"]'})], {
            "content_width": "boxed", "padding": _box(12, 0, 18, 0),
        }))
    elif item_cards:
        body.append(_container(item_cards, {
            "content_width": "full",
            "flex_direction": "row",
            "flex_wrap": "wrap",
            "flex_direction_mobile": "column",
            "gap": _px(18),
            "padding": _box(12, 0, 10, 0),
        }))
    if section.cta_label:
        body.append(_button(section.cta_label, section.cta_url or "#", ds))
    return _section_shell(section, body, ds)


def faq(section: SectionContentSpec, ds: DesignSystem) -> dict[str, Any]:
    body = _intro(section, ds)
    for title, text in _split_items(section.items):
        body.append(_surface_card(title, text, ds, width=100))
    return _section_shell(section, body, ds)


def booking(section: SectionContentSpec, ds: DesignSystem) -> dict[str, Any]:
    left = _container(_intro(section, ds), {
        "content_width": "full", "width": _pct(42), "width_mobile": _pct(100),
        "padding": _box(12, 12, 12, 12),
    })
    form = _container([
        _widget("shortcode", {"shortcode": '[contact-form-7 title="AI Contact"]'})
    ], {
        "content_width": "full", "width": _pct(56), "width_mobile": _pct(100),
        "background_background": "classic", "background_color": "#FFFFFF",
        "padding": _box(30, 30, 30, 30), "border_radius": _box(ds.radius, ds.radius, ds.radius, ds.radius),
    })
    row = _container([left, form], {
        "content_width": "boxed", "flex_direction": "row", "flex_direction_mobile": "column",
        "gap": _px(36), "align_items": "center", "padding": _box(0, 0, 0, 0),
    })
    return _section_shell(section, [row], ds)


def contact(section: SectionContentSpec, ds: DesignSystem) -> dict[str, Any]:
    pairs = _split_items(section.items)
    left = _container(_intro(section, ds), {
        "content_width": "full", "width": _pct(54), "width_mobile": _pct(100),
        "padding": _box(12, 12, 12, 12),
    })
    side_elements: list[dict[str, Any]] = [_heading("Як зв’язатися", ds.text, ds, level="h3", size=22)]
    if pairs:
        for title, body in pairs[:4]:
            side_elements.append(_heading(title, ds.primary, ds, level="h4", size=18))
            if body:
                side_elements.append(_text(body, ds.muted, ds, size=15))
    else:
        side_elements.append(_text("Вкажіть підтверджені телефон, email, адресу та графік роботи у редакторі, якщо їх не було у вихідному запиті.", ds.muted, ds, size=15))
    if section.cta_label:
        side_elements.append(_button(section.cta_label, section.cta_url or "#", ds))
    right = _container(side_elements, {
        "content_width": "full", "width": _pct(44), "width_mobile": _pct(100),
        "background_background": "classic", "background_color": ds.surface,
        "padding": _box(30, 30, 30, 30), "border_radius": _box(ds.radius, ds.radius, ds.radius, ds.radius),
        "gap": _px(10),
    })
    row = _container([left, right], {
        "content_width": "boxed", "flex_direction": "row", "flex_direction_mobile": "column",
        "gap": _px(36), "align_items": "center", "padding": _box(0, 0, 0, 0),
    })
    return _section_shell(section, [row], ds)


def cta(section: SectionContentSpec, ds: DesignSystem) -> dict[str, Any]:
    body = _intro(section, ds)
    if section.cta_label:
        body.append(_button(section.cta_label, section.cta_url or "#", ds, accent=True))
    inner = _container(body, {
        "content_width": "boxed", "align_items": "center", "padding": _box(6, 6, 6, 6), "gap": _px(18),
    })
    section = section.model_copy(update={"style_variant": "dark"})
    return _section_shell(section, [inner], ds)


def simple_content(section: SectionContentSpec, ds: DesignSystem) -> dict[str, Any]:
    body = _intro(section, ds)
    if section.items:
        pairs = _split_items(section.items)
        body.append(_container([_surface_card(t, b, ds, width=48 if len(pairs) <= 2 else 31) for t, b in pairs], {
            "content_width": "full", "flex_direction": "row", "flex_wrap": "wrap",
            "flex_direction_mobile": "column", "gap": _px(18), "padding": _box(8, 0, 8, 0),
        }))
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
    "contact": contact,
    "cta": cta,
    "content": simple_content,
}


def compile_elementor_page(page: PageExperienceSpec, ds: DesignSystem, media: list[dict[str, Any]] | None = None, *, live_catalog: bool = False) -> list[dict[str, Any]]:
    elements: list[dict[str, Any]] = []
    specs = page.section_specs
    if not specs:
        specs = [SectionContentSpec(section_type="content", heading=page.page_name, body=page.page_goal)]
    selected_image = choose_page_media(page, media or [])
    seen_headings: set[str] = set()
    better_headings = {
        "products": "Обирайте з колекції", "services": "Що ми пропонуємо",
        "benefits": "Чому обирають нас", "trust": "Наш підхід",
        "contact": "Зв’яжіться з нами", "cta": "Зробіть наступний крок",
        "faq": "Поширені запитання", "process": "Як усе працює",
    }
    for index, section in enumerate(specs):
        # Never render a second identical section heading on one page.
        key = section.heading.strip().casefold()
        if index > 0 and (key in seen_headings or key == page.page_name.casefold()):
            alternative = better_headings.get(section.section_type, "Дізнайтеся більше")
            if alternative.casefold() in seen_headings:
                alternative = f"{alternative} — {index + 1}"
            section = section.model_copy(update={"heading": alternative})
        seen_headings.add(section.heading.strip().casefold())
        section_type = section.section_type.lower().strip() or "content"
        if index == 0 and section_type not in {"hero", "products"}:
            section_type = "hero"
        renderer = COMPONENTS.get(section_type, simple_content)
        if section_type == "hero":
            elements.append(hero(section, ds, selected_image))
        elif section_type in {"products", "services", "benefits", "trust", "team", "process", "stats"}:
            elements.append(cards(section, ds, selected_image, live_catalog=live_catalog))
        else:
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
        if section.cta_label:
            parts.append(f'<!-- wp:buttons --><div class="wp-block-buttons"><!-- wp:button --><div class="wp-block-button"><a class="wp-block-button__link wp-element-button" href="{html.escape(section.cta_url or "#")}">{html.escape(section.cta_label)}</a></div><!-- /wp:button --></div><!-- /wp:buttons -->')
        parts.append('</div><!-- /wp:group -->')
    return "\n".join(parts)
