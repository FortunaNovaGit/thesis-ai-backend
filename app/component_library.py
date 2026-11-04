from __future__ import annotations

import html
import re
import secrets
import hashlib
from typing import Any

from .models import DesignSystem, PageExperienceSpec, SectionContentSpec, PageLayoutSpec, SectionLayoutSpec
from .generative_design import section_layout


def _validated_media_url(asset: dict[str, Any]) -> str:
    url = str(asset.get("url", ""))
    return url if url.startswith("https://") and asset.get("id") else ""


def choose_matching_media(query: str, media: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Match real WordPress attachment metadata, never guess or import a photo.

    Use short word stems to handle Ukrainian inflections (цукерки/цукерок).
    Generic page labels should never cause unrelated media to appear.
    """
    ignored = {"головна", "сторінка", "контакти", "магазин", "додати", "створити", "нашого", "зробити", "перейти", "кнопка"}
    words = re.findall(r"[^\W\d_]{5,}", query.casefold())
    stems = {w[:5] for w in words if w not in ignored}
    if not stems:
        return None
    best_score = 0
    best = None
    for item in media:
        if not _validated_media_url(item):
            continue
        description = " ".join(str(item.get(k, "")) for k in ("alt", "title", "caption")).casefold()
        # Never assign a 24-piece product photo to a 16-piece card solely
        # because both share the words "асорті" and "цукерки".
        quantity_tokens = set(re.findall(r"\b\d+\b", query))
        if quantity_tokens and not quantity_tokens.issubset(set(re.findall(r"\b\d+\b", description))):
            continue
        description_stems = {w[:5] for w in re.findall(r"[^\W\d_]{5,}", description)}
        score = len(stems.intersection(description_stems))
        if score > best_score:
            best_score, best = score, item
    return best


def choose_page_media(page: PageExperienceSpec, media: list[dict[str, Any]]) -> dict[str, Any] | None:
    # An explicitly selected WP attachment is stronger evidence of media intent
    # than weak AI-text stem matching. This applies only to the homepage.
    if page.page_slug == "home":
        for item in media:
            if item.get("preferred_home_hero") and _validated_media_url(item):
                return item
    text = " ".join([page.page_name, page.page_goal] +
                    [" ".join([sec.heading, sec.body]) for sec in page.section_specs])
    return choose_matching_media(text, media)


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


def _readable_ink(background: str) -> str:
    """Choose accessible ink for variable AI-selected hex button colors."""
    color = background.lstrip("#")
    if len(color) == 3:
        color = "".join(c * 2 for c in color)
    if len(color) != 6:
        return "#FFFFFF"
    try:
        channels = [int(color[i:i+2], 16) / 255 for i in (0, 2, 4)]
    except ValueError:
        return "#FFFFFF"
    linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in channels]
    luminance = sum(a*b for a, b in zip(linear, (.2126, .7152, .0722)))
    return "#101015" if luminance > .179 else "#FFFFFF"


def _button(label: str, url: str, ds: DesignSystem, *, accent: bool = False) -> dict[str, Any]:
    bg = ds.accent if accent else ds.primary
    return _widget("button", {
        "text": html.escape(label, quote=False),
        "link": {"url": url, "is_external": "", "nofollow": ""},
        "size": "md",
        "background_color": bg,
        "button_text_color": _readable_ink(bg),
        "border_radius": _box(ds.radius, ds.radius, ds.radius, ds.radius),
        "typography_typography": "custom",
        "typography_font_family": ds.body_font,
        "typography_font_weight": "600",
    })


def _surface_card(title: str, body: str, ds: DesignSystem, *, width: int = 31, variant: str = "services", index: int = 0) -> dict[str, Any]:
    elements = []
    if variant == "process":
        elements.append(_widget("heading", {
            "title": f"{index+1:02d}", "header_size": "div", "title_color": ds.accent,
            "typography_typography": "custom", "typography_font_family": ds.heading_font,
            "typography_font_size": _px(36), "typography_font_weight": "500",
        }))
    elements.append(_heading(title, ds.text, ds, level="h3", size=23))
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
        "gap": _px(12), "css_classes": f"tai-feature-card tai-feature-card-{variant}",
    })


def _editorial_product_card(title: str, body: str, ds: DesignSystem, index: int, *, width: int = 48, media: dict[str, Any] | None = None) -> dict[str, Any]:
    """Editable catalog teaser. No counterfeit photographic or numeric placeholder.

    Without verified attachment, render a compact editorial row instead of a
    giant fake product-image rectangle. Commercial data still belongs to WC.
    """
    elements: list[dict[str, Any]] = []
    if media:
        elements.append(_container([_image_widget(media)], {
            "content_width": "full", "padding": _box(0, 0, 0, 0),
            "css_classes": "tai-product-art-photo",
        }))
    else:
        # Deliberate text-first preview; do not imply a product image exists.
        elements.append(_widget("heading", {
            "title": f"{index + 1:02d} /", "header_size": "div", "title_color": ds.accent,
            "typography_typography": "custom", "typography_font_family": ds.body_font,
            "typography_font_size": _px(14), "typography_font_weight": "600",
        }))
    elements.append(_heading(title, ds.text, ds, level="h3", size=26))
    if body:
        elements.append(_text(body, ds.muted, ds, size=16))
    return _container(elements, {
        "content_width": "full", "width": _pct(width), "width_mobile": _pct(100),
        "background_background": "classic", "background_color": ds.surface,
        "padding": _box(16, 16, 24, 16) if media else _box(28, 22, 30, 22),
        "border_radius": _box(ds.radius, ds.radius, ds.radius, ds.radius),
        "gap": _px(13), "css_classes": "tai-product-card " + ("tai-product-card-with-photo" if media else "tai-product-card-text-only"),
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
        # Palette-aware dark section; white type on a light background was
        # previously possible when AI selected an inverted global palette.
        from .design_safety import luminance
        bg = ds.text if luminance(ds.text) < .18 else (ds.background if luminance(ds.background) < .18 else ds.primary)
        ink = _readable_ink(bg)
        return bg, ink, ink
    if section.style_variant == "accent":
        ink = _readable_ink(ds.primary)
        return ds.primary, ink, ink
    if section.style_variant == "soft":
        return ds.surface, ds.text, ds.muted
    return ds.background, ds.text, ds.muted


def _section_shell(section: SectionContentSpec, body: list[dict[str, Any]], ds: DesignSystem) -> dict[str, Any]:
    bg, _, _ = _colors(section, ds)
    return _container(body, {
        "content_width": "full",
        "width": _pct(100),
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
            "title_color": ds.accent if section.style_variant not in {"accent", "dark"} else title_color,
            "typography_typography": "custom",
            "typography_font_family": ds.body_font,
            "typography_font_size": _px(13),
            "typography_font_weight": "700",
        }))
    out.append(_heading(section.heading, title_color, ds, level="h1" if h1 else "h2", size=46 if h1 else 34))
    if section.body:
        out.append(_text(section.body, body_color, ds, size=19 if h1 else 17))
    return out


def hero(section: SectionContentSpec, ds: DesignSystem, media: dict[str, Any] | None = None) -> dict[str, Any]:
    left_elements = _intro(section, ds, h1=True)
    if section.cta_label:
        left_elements.append(_button(section.cta_label, section.cta_url or "#", ds, accent=section.style_variant == "dark"))
    left = _container(left_elements, {
        "content_width": "full",
        # Widths + gap must fit the grid: the visual CSS uses minmax(0,fr).
        "width": _pct(100),
        "width_mobile": _pct(100),
        "padding": _box(0, 0, 0, 0),
        "css_classes": "tai-hero-copy",
        "gap": _px(22),
    })

    if media:
        # Only media already attached to this WordPress site can become a real image.
        right = _container([_image_widget(media)], {
            "content_width": "full", "width": _pct(100), "width_mobile": _pct(100),
            "padding": _box(0, 0, 0, 0), "css_classes": "tai-hero-photo",
        })
    else:
        # No image supplied: no large empty placeholder in the published draft.
        # A real photograph can be inserted later with native Elementor Image.
        right = None

    row = _container([left] + ([right] if right is not None else []), {
        "content_width": "full",
        "flex_direction": "row", "flex_direction_mobile": "column",
        "align_items": "center", "css_classes": "tai-hero-grid",
        "gap": _px(32), "padding": _box(0, 0, 0, 0),
    })
    shell = _section_shell(section, [row], ds)
    if media is None:
        shell["settings"]["css_classes"] += " tai-visual-typography"
    return shell


def cards(section: SectionContentSpec, ds: DesignSystem, media: dict[str, Any] | None = None, *, live_catalog: bool = False, product_names: list[str] | None = None, h1: bool = False, product_media: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    body = _intro(section, ds, h1=h1)
    pairs = _split_items(section.items)
    if section.section_type == "products":
        # Names typed by the Creative Director are NOT verified product entries.
        # Only explicit owner-provided items may become teaser cards. Otherwise
        # show the true WooCommerce catalog (if public products exist) or the
        # authored introductory copy/CTA without invented card inventory.
        pairs = [(name, "") for name in (product_names or [])[:4]]
    if section.section_type == "products":
        item_cards = [_editorial_product_card(title, text, ds, i, width=48 if len(pairs) <= 2 else 31,
                       media=choose_matching_media(title, product_media or []))
                      for i, (title, text) in enumerate(pairs)]
    else:
        item_cards = [_surface_card(title, text, ds, width=31 if len(pairs) >= 3 else 48, variant=section.section_type, index=i) for i, (title, text) in enumerate(pairs)]
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
            "css_classes": f"tai-card-grid tai-card-grid-{section.section_type}",
            "gap": _px(18),
            "padding": _box(12, 0, 10, 0),
        }))
    if section.cta_label:
        body.append(_button(section.cta_label, section.cta_url or "#", ds))
    return _section_shell(section, body, ds)


def faq(section: SectionContentSpec, ds: DesignSystem) -> dict[str, Any]:
    body = _intro(section, ds)
    for i, (title, text) in enumerate(_split_items(section.items)):
        body.append(_surface_card(title, text, ds, width=100, variant="faq", index=i))
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
    # Honor Creative Director surface: do not force all CTA sections dark.
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


def _apply_generative_layout(element: dict[str, Any], spec: SectionLayoutSpec, *, page_slug: str, index: int) -> None:
    """Only bounded native Elementor controls + allowlisted CSS classes.

    All copy/images remain separate editable Elementor widgets. No raw CSS or
    arbitrary selectors from an LLM make it into the execution plan.
    """
    root = element["settings"]
    # Quantization is a safe geometry constraint, not a selection of site templates.
    split = min(70, max(35, round(spec.text_width_pct / 5) * 5))
    max_width = min((960, 1120, 1280, 1440), key=lambda n: abs(n - spec.max_width))
    classes = [root.get("css_classes", ""), "tai-generative", f"tai-layout-{spec.composition}",
               f"tai-media-{spec.media_position}", f"tai-split-{split}",
               f"tai-max-{max_width}", f"tai-motif-{spec.motif}",
               f"tai-ratio-{spec.art_ratio}", f"tai-heading-{spec.heading_emphasis}",
               f"tai-columns-{spec.card_columns}",
               f"tai-presentation-{spec.card_presentation}",
               f"tai-surface-{spec.surface_treatment}",
               f"tai-content-{spec.content_alignment}",
               f"tai-visual-{spec.visual_treatment}",
               f"tai-detail-{spec.accent_detail}"]
    root["css_classes"] = " ".join(classes)
    root["padding"] = _box(spec.vertical_space, 24, spec.vertical_space, 24)
    if spec.surface_treatment == "tinted":
        root["background_color"] = root.get("background_color") or "#F8FAFC"
    # Stable root ID permits targeted delta repair and section-level comparisons.
    element["id"] = hashlib.sha256(f"thesis-ai:{page_slug}:{index}".encode()).hexdigest()[:8]
    # Elementor-native widths still apply when the companion CSS is not loaded.
    descendants = element.get("elements", [])
    for descendant in descendants:
        settings = descendant.get("settings", {})
        if "tai-hero-grid" in settings.get("css_classes", ""):
            if spec.visual_treatment == "typography":
                # A confident typographic editorial cover is better than a
                # generic fake image rectangle when no verified media exists.
                descendant["elements"] = [child for child in descendant.get("elements", [])
                     if not any(tag in child.get("settings", {}).get("css_classes", "")
                                for tag in ("tai-hero-art", "tai-hero-photo"))]
            settings["flex_direction"] = "column" if spec.composition in {"stacked", "centered"} or spec.visual_treatment == "typography" else "row"
            settings["flex_direction_mobile"] = "column"
            settings["gap"] = _px(32)
            for child_index, child in enumerate(descendant.get("elements", [])):
                child_settings = child.get("settings", {})
                if spec.composition in {"split", "offset"} and spec.visual_treatment != "typography":
                    width = split if child_index == 0 else 100 - split
                    child_settings["width"] = _pct(width)
                else:
                    child_settings["width"] = _pct(100)
                child_settings["width_mobile"] = _pct(100)
        if "tai-card-grid" in settings.get("css_classes", ""):
            settings["flex_wrap"] = "wrap"
            for card in descendant.get("elements", []):
                card["settings"]["width"] = _pct(100 // spec.card_columns)
                card["settings"]["width_mobile"] = _pct(100)


def compile_elementor_page(page: PageExperienceSpec, ds: DesignSystem, media: list[dict[str, Any]] | None = None, *, layout: PageLayoutSpec | None = None, live_catalog: bool = False, product_names: list[str] | None = None) -> list[dict[str, Any]]:
    elements: list[dict[str, Any]] = []
    specs = page.section_specs
    if not specs:
        specs = [SectionContentSpec(section_type="content", heading=page.page_name, body=page.page_goal)]
    selected_image = choose_page_media(page, media or [])
    # Defense in depth for direct compiler callers bypassing the planning gate.
    # Unique, valid Creative Director headings pass through unchanged.
    seen_headings: set[str] = set()
    for index, section in enumerate(specs):
        key = " ".join(section.heading.casefold().split())
        if key in seen_headings or (index > 0 and key == page.page_name.casefold()):
            label = section.items[0].split(" — ", 1)[0].strip() if section.items else ""
            if not label or len(label) > 68 or " ".join(label.casefold().split()) in seen_headings:
                label = f"{page.page_name} · {section.section_type.title()}"
            while " ".join(label.casefold().split()) in seen_headings:
                label += " ·"
            section = section.model_copy(update={"heading": label})
        seen_headings.add(" ".join(section.heading.casefold().split()))
        section_type = section.section_type.lower().strip() or "content"
        if index == 0 and section_type not in {"hero", "products"}:
            section_type = "hero"
            section = section.model_copy(update={"section_type": "hero"})
        renderer = COMPONENTS.get(section_type, simple_content)
        if section_type == "hero":
            element = hero(section, ds, selected_image)
        elif section_type in {"products", "services", "benefits", "trust", "team", "process", "stats"}:
            element = cards(section, ds, selected_image, live_catalog=live_catalog,
                            product_names=product_names, h1=(index == 0), product_media=media)
        else:
            element = renderer(section, ds)
        section_spec = section_layout(layout, index)
        if (section_spec is not None and section_type == "hero" and selected_image is None
            and section_spec.visual_treatment == "media"):
            # Never pretend that an empty graphic block is a real product photo.
            # Typography-first native Elementor widgets are the truthful fallback.
            section_spec = section_spec.model_copy(update={"visual_treatment": "typography"})
        if (section_spec is not None and section_type not in {"hero", "products"}
            and not section.items and section_spec.vertical_space > 110):
            # A simple heading + paragraph should not occupy a giant blank
            # full-height panel. This geometric guardrail preserves AI content.
            section_spec = section_spec.model_copy(update={"vertical_space": 88})
        if section_spec is not None:
            _apply_generative_layout(element, section_spec, page_slug=page.page_slug, index=index)
        elements.append(element)
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
