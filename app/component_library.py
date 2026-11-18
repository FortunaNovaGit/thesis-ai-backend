from __future__ import annotations

import html
import re
import secrets
import hashlib
from typing import Any

from .models import DesignSystem, PageExperienceSpec, SectionContentSpec, PageLayoutSpec, SectionLayoutSpec
from .generative_design import section_layout
from .visual_composer import resolve_scene, scene_classes


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
        for item in media:
            if item.get("ai_generated_role") == "hero" and _validated_media_url(item):
                return item
    text = " ".join([page.page_name, page.page_goal] +
                    [" ".join([sec.heading, sec.body]) for sec in page.section_specs])
    # AI concepts are assigned explicitly by role. Never repurpose an
    # illustration of a collection as if it were a genuine product photograph.
    return choose_matching_media(text, [m for m in media if not m.get("ai_generated_role")])


def choose_secondary_page_media(page: PageExperienceSpec, media: list[dict[str, Any]], primary: dict[str, Any] | None) -> dict[str, Any] | None:
    """Only the site owner's explicitly chosen second Hero image is eligible.

    Never take an arbitrary product photo from the Media Library to fill a collage.
    """
    if page.page_slug != "home" or primary is None:
        return None
    for item in media:
        if (item.get("preferred_home_hero_secondary") and _validated_media_url(item)
                and item.get("id") != primary.get("id")):
            return item
    # Collection concept belongs inside the collection section, not twice
    # in the Hero and the catalogue. A second Hero image must be explicitly
    # provided by the owner; otherwise collage downgrades to a single image.
    return None


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


# ---------------------------------------------------------------------------
# v0.12 Rich Visual System
#
# Every visible element is still a separate native Elementor widget (heading,
# text-editor, button, icon, image, shortcode). The richer look comes from
# (1) a real type scale with native responsive sizes, (2) structure per
# section kind/presentation, (3) allowlisted CSS classes styled by the Bridge
# stylesheet `rich-sections.css`. No LLM-authored CSS/HTML/URLs are emitted.
# ---------------------------------------------------------------------------

# Font Awesome 5 Free (bundled with Elementor Free). Deterministic keyword
# mapping; the LLM never supplies icon names.
ICON_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("подар", "gift", "сюрприз"), "fas fa-gift"),
    (("ручн", "hand", "майстер", "craft", "авторськ"), "fas fa-hand-sparkles"),
    (("склад", "інгред", "натурал", "ingred", "organic", "еко", "рослин"), "fas fa-leaf"),
    (("достав", "deliver", "shipping", "кур'єр", "курʼєр", "відправ"), "fas fa-shipping-fast"),
    (("замов", "order", "кошик", "cart", "купі", "купу", "оплат"), "fas fa-shopping-bag"),
    (("парті", "свіж", "fresh", "термін", "швидк", "хвилин", "time", "годин"), "fas fa-clock"),
    (("консульт", "підтрим", "support", "напиш", "chat", "питан", "зв'яз", "звʼяз", "форм"), "fas fa-comments"),
    (("безпеч", "гаранті", "надійн", "secure", "safe", "захист", "чесн"), "fas fa-shield-alt"),
    (("преміум", "якіст", "quality", "premium", "розкіш", "елегант"), "fas fa-gem"),
    (("кав", "coffee", "чай", "вечір", "вечор"), "fas fa-mug-hot"),
    (("коробк", "упаков", "box", "pack", "подач"), "fas fa-box-open"),
    (("телефон", "phone", "дзвін"), "fas fa-phone-alt"),
    (("пошт", "email", "e-mail", "лист"), "fas fa-envelope"),
    (("адрес", "локац", "map", "місто", "район"), "fas fa-map-marker-alt"),
    (("зуб", "стомат", "dental", "tooth", "усміш"), "fas fa-tooth"),
    (("лікар", "доктор", "doctor", "спеціаліст", "фахів"), "fas fa-user-md"),
    (("запис", "booking", "календ", "дат", "візит"), "fas fa-calendar-check"),
    (("обер", "вибір", "вибер", "порівн", "choose", "compar", "пошук", "каталог"), "fas fa-search"),
    (("турбот", "care", "догляд", "комфорт"), "fas fa-hand-holding-heart"),
    (("дизайн", "стиль", "design", "естет"), "fas fa-palette"),
    (("смак", "цукер", "шоколад", "taste", "candy", "десерт", "солод"), "fas fa-cookie-bite"),
    (("ідея", "idea", "натхнен"), "fas fa-lightbulb"),
)
FALLBACK_ICONS = ("fas fa-star", "fas fa-heart", "fas fa-check-circle", "fas fa-feather-alt")
ALLOWED_ICONS = frozenset([icon for _, icon in ICON_RULES] + list(FALLBACK_ICONS))


def choose_icon(text: str, index: int = 0, used: set[str] | None = None) -> str:
    """Pick a semantically related icon; avoid repeating one inside a section."""
    key = text.casefold()
    used = used if used is not None else set()
    for stems, icon in ICON_RULES:
        if icon not in used and any(stem in key for stem in stems):
            used.add(icon)
            return icon
    for offset in range(len(FALLBACK_ICONS)):
        icon = FALLBACK_ICONS[(index + offset) % len(FALLBACK_ICONS)]
        if icon not in used:
            used.add(icon)
            return icon
    return FALLBACK_ICONS[index % len(FALLBACK_ICONS)]


def _icon(icon: str, color: str, *, classes: str = "tai-icon") -> dict[str, Any]:
    if icon not in ALLOWED_ICONS:
        icon = FALLBACK_ICONS[0]
    return _widget("icon", {
        "selected_icon": {"value": icon, "library": "fa-solid"},
        "primary_color": color,
        "align": "left",
        "_css_classes": classes,
    })


def _emphasize(text: str) -> str:
    """Escape heading text and set its final words in an accent italic.

    Purely presentational (`<em>`), the words themselves are unchanged and
    remain editable in Elementor; snapshot QA strips the tag.
    """
    words = text.split()
    if len(words) < 4:
        return html.escape(text, quote=False)
    n = 2 if len(words) >= 6 else 1
    head, tail = " ".join(words[:-n]), " ".join(words[-n:])
    return f'{html.escape(head, quote=False)} <em class="tai-em">{html.escape(tail, quote=False)}</em>'


# Native responsive type scale (desktop, tablet, mobile) in px.
TYPE_SCALE = {
    "h1-calm": (58, 46, 36), "h1-balanced": (66, 50, 38), "h1-dramatic": (78, 56, 40),
    "h2": (48, 38, 30), "h2-display": (60, 44, 32), "h3": (24, 22, 20),
    "lead": (20, 19, 17), "body": (17, 17, 16), "small": (15, 15, 14),
}


def _scaled(settings: dict[str, Any], key: str, scale: str) -> None:
    desktop, tablet, mobile = TYPE_SCALE[scale]
    settings[key] = _px(desktop)
    settings[f"{key}_tablet"] = _px(tablet)
    settings[f"{key}_mobile"] = _px(mobile)


def _heading(text: str, color: str, ds: DesignSystem, *, level: str = "h2", size: int | None = None,
             scale: str | None = None, emphasize: bool = False, classes: str = "") -> dict[str, Any]:
    settings: dict[str, Any] = {
        "title": _emphasize(text) if emphasize else html.escape(text, quote=False),
        "header_size": level,
        "title_color": color,
        "typography_typography": "custom",
        "typography_font_family": ds.heading_font,
        "typography_font_weight": "600" if level in {"h1", "h2"} else "700",
        "typography_line_height": {"unit": "em", "size": 1.06 if level == "h1" else 1.12, "sizes": []},
    }
    if scale:
        _scaled(settings, "typography_font_size", scale)
    elif size:
        settings["typography_font_size"] = _px(size)
    if classes:
        settings["_css_classes"] = classes
    return _widget("heading", settings)


def _label(text: str, color: str, ds: DesignSystem, *, classes: str) -> dict[str, Any]:
    """Small non-heading text label (eyebrow, numeral) as a native Heading div."""
    return _widget("heading", {
        "title": html.escape(text, quote=False), "header_size": "div", "title_color": color,
        "typography_typography": "custom", "typography_font_family": ds.body_font,
        "typography_font_size": _px(13), "typography_font_weight": "700",
        "_css_classes": classes,
    })


def _text(text: str, color: str, ds: DesignSystem, *, size: int = 18, scale: str | None = None,
          classes: str = "") -> dict[str, Any]:
    settings: dict[str, Any] = {
        "editor": f"<p>{html.escape(text, quote=False)}</p>",
        "text_color": color,
        "typography_typography": "custom",
        "typography_font_family": ds.body_font,
        "typography_font_size": _px(size),
        "typography_line_height": {"unit": "em", "size": 1.65, "sizes": []},
    }
    if scale:
        _scaled(settings, "typography_font_size", scale)
    if classes:
        settings["_css_classes"] = classes
    return _widget("text-editor", settings)


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


def _button(label: str, url: str, ds: DesignSystem, *, accent: bool = False, ghost: bool = False,
            ink: str | None = None) -> dict[str, Any]:
    bg = ds.accent if accent else ds.primary
    settings: dict[str, Any] = {
        "text": html.escape(label, quote=False),
        "link": {"url": url, "is_external": "", "nofollow": ""},
        "size": "md",
        "background_color": bg,
        "button_text_color": _readable_ink(bg),
        "border_radius": _box(ds.radius, ds.radius, ds.radius, ds.radius),
        "typography_typography": "custom",
        "typography_font_family": ds.body_font,
        "typography_font_weight": "600",
        "_css_classes": "tai-btn tai-btn-primary" if not ghost else "tai-btn tai-btn-ghost",
    }
    if ghost:
        # Outline action: background/border are drawn by the scoped stylesheet;
        # Elementor still gets a valid readable fallback when CSS is absent.
        settings["background_color"] = ds.background
        settings["button_text_color"] = ink or ds.text
    return _widget("button", settings)


def _actions(section: SectionContentSpec, ds: DesignSystem, *, accent: bool = False,
             ink: str | None = None) -> list[dict[str, Any]]:
    if not section.cta_label:
        return []
    buttons = [_button(section.cta_label, section.cta_url or "#", ds, accent=accent)]
    if section.secondary_cta_label and section.secondary_cta_url:
        buttons.append(_button(section.secondary_cta_label, section.secondary_cta_url, ds, ghost=True, ink=ink))
    if len(buttons) == 1:
        return buttons
    return [_container(buttons, {
        "content_width": "full", "flex_direction": "row", "flex_wrap": "wrap",
        "align_items": "center", "gap": _px(14), "padding": _box(6, 0, 0, 0),
        "css_classes": "tai-actions",
    })]


def _split_items(items: list[str]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for item in items[:8]:
        if " — " in item:
            title, body = item.split(" — ", 1)
        elif " – " in item:
            title, body = item.split(" – ", 1)
        elif ": " in item:
            title, body = item.split(": ", 1)
        else:
            title, body = item, ""
        body = body.strip()
        # "Title — explanation" is rendered as two blocks; the explanation
        # becomes its own sentence, so it starts with a capital letter.
        if body[:1].islower():
            body = body[:1].upper() + body[1:]
        result.append((title.strip(), body))
    return result


def _surface_card(title: str, body: str, ds: DesignSystem, *, width: int = 31, variant: str = "services",
                  index: int = 0, presentation: str = "grid", icon: str | None = None,
                  ink: tuple[str, str] | None = None, surface: str | None = None) -> dict[str, Any]:
    title_ink, body_ink = ink or (ds.text, ds.muted)
    elements: list[dict[str, Any]] = []
    numbered = variant == "process" or presentation in {"list", "timeline"}
    if numbered:
        elements.append(_widget("heading", {
            "title": f"{index+1:02d}", "header_size": "div", "title_color": ds.accent,
            "typography_typography": "custom", "typography_font_family": ds.heading_font,
            "typography_font_size": _px(40), "typography_font_weight": "500",
            "_css_classes": "tai-card-index",
        }))
    elif icon and variant != "faq":
        elements.append(_icon(icon, ds.accent, classes="tai-icon tai-card-icon"))
    text_children = [_heading(title, title_ink, ds, level="h3", scale="h3", classes="tai-card-title")]
    if body:
        text_children.append(_text(body, body_ink, ds, size=16, classes="tai-card-text"))
    if presentation == "list" and variant not in {"faq"}:
        # Editorial row: numeral | title + text. Nested container keeps it editable.
        elements.append(_container(text_children, {
            "content_width": "full", "padding": _box(0, 0, 0, 0), "gap": _px(8),
            "css_classes": "tai-card-body",
        }))
    else:
        elements.extend(text_children)
    return _container(elements, {
        "content_width": "full",
        "width": _pct(width),
        "width_mobile": _pct(100),
        "background_background": "classic",
        "background_color": surface or ds.surface,
        "padding": _box(32, 30, 32, 30),
        "border_radius": _box(ds.radius, ds.radius, ds.radius, ds.radius),
        "gap": _px(14),
        "css_classes": f"tai-feature-card tai-feature-card-{variant} tai-card tai-card-{presentation}",
    })


def _editorial_product_card(title: str, body: str, ds: DesignSystem, index: int, *, width: int = 48, media: dict[str, Any] | None = None) -> dict[str, Any]:
    """Editable catalog teaser. No counterfeit photographic or numeric placeholder.

    Without verified attachment, render an editorial text card (decorated only
    by an abstract CSS pattern, never a fake product photo rectangle).
    """
    elements: list[dict[str, Any]] = []
    if media:
        elements.append(_container([_image_widget(media)], {
            "content_width": "full", "padding": _box(0, 0, 0, 0),
            "css_classes": "tai-product-art-photo",
        }))
    else:
        elements.append(_label(f"{index + 1:02d} / колекція", ds.accent, ds, classes="tai-product-index"))
    elements.append(_heading(title, ds.text, ds, level="h3", size=30, classes="tai-product-title"))
    if body:
        elements.append(_text(body, ds.muted, ds, size=16))
    return _container(elements, {
        "content_width": "full", "width": _pct(width), "width_mobile": _pct(100),
        "background_background": "classic", "background_color": ds.background,
        "padding": _box(16, 16, 24, 16) if media else _box(34, 30, 34, 30),
        "border_radius": _box(ds.radius, ds.radius, ds.radius, ds.radius),
        "gap": _px(13), "css_classes": "tai-product-card tai-card " + ("tai-product-card-with-photo" if media else "tai-product-card-text-only"),
    })


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


def _card_surface(section: SectionContentSpec, ds: DesignSystem) -> str:
    """Cards contrast with their section: soft sections get paper cards."""
    return ds.background if section.style_variant == "soft" else ds.surface


def _section_shell(section: SectionContentSpec, body: list[dict[str, Any]], ds: DesignSystem) -> dict[str, Any]:
    bg, _, _ = _colors(section, ds)
    return _container(body, {
        "content_width": "full",
        "width": _pct(100),
        "background_background": "classic",
        "background_color": bg,
        "css_classes": (f"thesis-ai-section thesis-ai-{section.section_type} thesis-ai-{section.component_key} "
                        f"tai-rich tai-tone-{section.style_variant} tai-kind-{section.section_type}"),
        "padding": _box(ds.section_spacing, 24, ds.section_spacing, 24),
        "gap": _px(30),
    })


def _intro(section: SectionContentSpec, ds: DesignSystem, *, h1: bool = False, display: bool = False,
           emphasis: str = "balanced") -> list[dict[str, Any]]:
    _, title_color, body_color = _colors(section, ds)
    on_color = section.style_variant in {"accent", "dark"}
    out: list[dict[str, Any]] = []
    if section.eyebrow:
        out.append(_label(section.eyebrow.upper(), title_color if on_color else ds.accent, ds,
                          classes="tai-eyebrow" + (" tai-eyebrow-pill" if h1 else "")))
    if h1:
        out.append(_heading(section.heading, title_color, ds, level="h1", scale=f"h1-{emphasis}",
                            emphasize=emphasis != "calm", classes="tai-display tai-h1"))
    else:
        out.append(_heading(section.heading, title_color, ds, level="h2",
                            scale="h2-display" if display else "h2",
                            emphasize=display or emphasis == "dramatic", classes="tai-display tai-h2"))
    if section.body:
        out.append(_text(section.body, body_color, ds, scale="lead", classes="tai-lead"))
    return out


def _section_header(section: SectionContentSpec, ds: DesignSystem, *, emphasis: str = "balanced",
                    centered: bool = False, h1: bool = False) -> dict[str, Any]:
    return _container(_intro(section, ds, h1=h1, emphasis=emphasis), {
        "content_width": "full", "padding": _box(0, 0, 0, 0), "gap": _px(16),
        "css_classes": "tai-section-head" + (" tai-section-head-center" if centered else ""),
    })


def _hero_highlights(section: SectionContentSpec, ds: DesignSystem) -> dict[str, Any] | None:
    from .content_quality import looks_like_filler, looks_like_planning
    # Legacy (non-creative) plans sometimes carry section *goals* in items;
    # those must never become visitor-facing highlights.
    pairs = [(t, b) for t, b in _split_items(section.items)
             if t and len(t) <= 60 and not looks_like_planning(f"{t} {b}") and not looks_like_filler(f"{t} {b}")][:4]
    if not pairs:
        return None
    _, title_ink, body_ink = _colors(section, ds)
    used: set[str] = set()
    cells = []
    for i, (title, body) in enumerate(pairs):
        children = [_icon(choose_icon(f"{title} {body}", i, used), ds.accent, classes="tai-icon tai-highlight-icon"),
                    _widget("heading", {
                        "title": html.escape(title, quote=False), "header_size": "div", "title_color": title_ink,
                        "typography_typography": "custom", "typography_font_family": ds.body_font,
                        "typography_font_size": _px(16), "typography_font_weight": "700",
                        "_css_classes": "tai-highlight-title"})]
        if body:
            children.append(_text(body, body_ink, ds, size=14, classes="tai-highlight-text"))
        cells.append(_container(children, {
            "content_width": "full", "padding": _box(0, 0, 0, 0), "gap": _px(6),
            "width": _pct(max(24, 100 // len(pairs) - 2)), "width_mobile": _pct(100),
            "css_classes": "tai-highlight",
        }))
    return _container(cells, {
        "content_width": "full", "flex_direction": "row", "flex_wrap": "wrap",
        "flex_direction_mobile": "column", "gap": _px(22), "padding": _box(26, 0, 0, 0),
        "css_classes": "tai-hero-highlights",
    })


def hero(section: SectionContentSpec, ds: DesignSystem, media: dict[str, Any] | None = None,
         secondary_media: dict[str, Any] | None = None, *, emphasis: str = "balanced") -> dict[str, Any]:
    left_elements = _intro(section, ds, h1=True, emphasis=emphasis)
    _, ink, _ = _colors(section, ds)
    left_elements.extend(_actions(section, ds, accent=section.style_variant == "dark", ink=ink))
    highlights = _hero_highlights(section, ds)
    if highlights is not None and not media:
        left_elements.append(highlights)
    left = _container(left_elements, {
        "content_width": "full",
        # Widths + gap must fit the grid: the visual CSS uses minmax(0,fr).
        "width": _pct(100),
        "width_mobile": _pct(100),
        "padding": _box(0, 0, 0, 0),
        "css_classes": "tai-hero-copy",
        "gap": _px(24),
    })

    if media:
        # Every visual is independently editable. No LLM-supplied image URLs.
        visual_children = [_image_widget(media)]
        if secondary_media and secondary_media.get("id") != media.get("id") and _validated_media_url(secondary_media):
            visual_children.append(_container([_image_widget(secondary_media)], {
                "content_width": "full", "padding": _box(0, 0, 0, 0),
                "css_classes": "tai-hero-photo-secondary",
            }))
        right = _container(visual_children, {
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
        "gap": _px(40), "padding": _box(0, 0, 0, 0),
    })
    # With a photo the copy column is narrow: the highlight strip spans the
    # full hero width underneath the composition instead of being squeezed.
    shell = _section_shell(section, [row] + ([highlights] if highlights is not None and media else []), ds)
    if media is None:
        shell["settings"]["css_classes"] += " tai-visual-typography"
    return shell


def cards(section: SectionContentSpec, ds: DesignSystem, media: dict[str, Any] | None = None, *, live_catalog: bool = False,
          product_names: list[str] | None = None, h1: bool = False, product_media: list[dict[str, Any]] | None = None,
          presentation: str = "grid", emphasis: str = "balanced") -> dict[str, Any]:
    header = _section_header(section, ds, emphasis=emphasis, h1=h1)
    body: list[dict[str, Any]] = [header]
    pairs = _split_items(section.items)
    if section.section_type == "process" and presentation in {"grid", "bento"}:
        presentation = "timeline"  # Steps read as a sequence, never as a bento.
    if section.section_type == "products":
        # Names typed by the Creative Director are NOT verified product entries.
        # Only explicit owner-provided items may become teaser cards. Otherwise
        # show the true WooCommerce catalog (if public products exist) or the
        # authored introductory copy/CTA without invented card inventory.
        pairs = [(name, "") for name in (product_names or [])[:4]]
        item_cards = [_editorial_product_card(title, text, ds, i, width=48 if len(pairs) <= 2 else 31,
                       media=choose_matching_media(title, product_media or []))
                      for i, (title, text) in enumerate(pairs)]
    else:
        _, title_ink, body_ink = _colors(section, ds)
        on_color = section.style_variant in {"accent", "dark"}
        used_icons: set[str] = set()
        item_cards = [_surface_card(
            title, text, ds, width=31 if len(pairs) >= 3 else 48, variant=section.section_type, index=i,
            presentation=presentation, icon=choose_icon(f"{title} {text}", i, used_icons),
            ink=None if not on_color else (title_ink, body_ink),
            surface=_card_surface(section, ds) if not on_color else None,
        ) for i, (title, text) in enumerate(pairs)]
        if on_color:
            for card in item_cards:
                card["settings"].pop("background_color", None)
                card["settings"]["background_background"] = ""
    if section.section_type == "products" and live_catalog:
        # Render actual WooCommerce products when present. The shortcode does not
        # create fictitious demo catalog entries.
        body.append(_container([_widget("shortcode", {"shortcode": '[products limit="6" columns="3" orderby="date" order="DESC"]'})], {
            "content_width": "boxed", "padding": _box(12, 0, 18, 0), "css_classes": "tai-live-catalog",
        }))
    elif item_cards:
        body.append(_container(item_cards, {
            "content_width": "full",
            "flex_direction": "row",
            "flex_wrap": "wrap",
            "flex_direction_mobile": "column",
            "css_classes": (f"tai-card-grid tai-card-grid-{section.section_type} tai-cards-{presentation} "
                            f"tai-count-{min(len(item_cards), 6)}"),
            "gap": _px(20),
            "padding": _box(12, 0, 10, 0),
        }))
    body.extend(_actions(section, ds, accent=section.style_variant in {"dark", "accent"}))
    return _section_shell(section, body, ds)


def statement(section: SectionContentSpec, ds: DesignSystem, *, emphasis: str = "dramatic") -> dict[str, Any]:
    """Manifesto / brand idea: one large typographic moment between dense sections."""
    _, title_color, body_color = _colors(section, ds)
    on_color = section.style_variant in {"accent", "dark"}
    inner: list[dict[str, Any]] = []
    if section.eyebrow:
        inner.append(_label(section.eyebrow.upper(), title_color if on_color else ds.accent, ds, classes="tai-eyebrow"))
    inner.append(_heading(section.heading, title_color, ds, level="h2", scale="h2-display",
                          emphasize=emphasis != "calm", classes="tai-display tai-h2 tai-statement-title"))
    if section.body:
        inner.append(_text(section.body, body_color, ds, scale="lead", classes="tai-lead tai-statement-text"))
    inner.extend(_actions(section, ds, accent=on_color))
    panel = _container(inner, {
        "content_width": "full", "align_items": "center", "padding": _box(0, 0, 0, 0), "gap": _px(20),
        "css_classes": "tai-statement",
    })
    return _section_shell(section, [panel], ds)


def faq(section: SectionContentSpec, ds: DesignSystem, *, emphasis: str = "balanced") -> dict[str, Any]:
    """Split FAQ: intro + native <details> disclosure items (keyboard accessible,
    no JavaScript, each answer is its own editable Text Editor widget)."""
    header = _section_header(section, ds, emphasis=emphasis)
    _, title_ink, body_ink = _colors(section, ds)
    header["settings"].update({"width": _pct(38), "width_mobile": _pct(100)})
    header["settings"]["css_classes"] += " tai-faq-intro"
    items = []
    for i, (question, answer) in enumerate(_split_items(section.items)):
        open_attr = " open" if i == 0 else ""
        answer_html = f"<p>{html.escape(answer, quote=False)}</p>" if answer else ""
        items.append(_widget("text-editor", {
            "editor": (f'<details class="tai-faq-item"{open_attr}><summary>{html.escape(question, quote=False)}</summary>'
                       f"{answer_html}</details>"),
            "text_color": title_ink,
            "typography_typography": "custom",
            "typography_font_family": ds.body_font,
            "typography_font_size": _px(17),
            "_css_classes": "tai-faq",
        }))
    if not items:
        return _section_shell(section, [header], ds)
    listing = _container(items, {
        "content_width": "full", "width": _pct(58), "width_mobile": _pct(100),
        "padding": _box(0, 0, 0, 0), "gap": _px(12), "css_classes": "tai-faq-list",
    })
    row = _container([header, listing], {
        "content_width": "full", "flex_direction": "row", "flex_direction_mobile": "column",
        "gap": _px(48), "padding": _box(0, 0, 0, 0), "css_classes": "tai-faq-grid",
    })
    return _section_shell(section, [row], ds)


def booking(section: SectionContentSpec, ds: DesignSystem, *, emphasis: str = "balanced") -> dict[str, Any]:
    left = _container(_intro(section, ds, emphasis=emphasis), {
        "content_width": "full", "width": _pct(42), "width_mobile": _pct(100),
        "padding": _box(12, 12, 12, 12), "gap": _px(16), "css_classes": "tai-booking-copy",
    })
    form = _container([
        _widget("shortcode", {"shortcode": '[contact-form-7 title="AI Contact"]'})
    ], {
        "content_width": "full", "width": _pct(56), "width_mobile": _pct(100),
        "background_background": "classic", "background_color": ds.background if section.style_variant == "soft" else ds.surface,
        "padding": _box(36, 36, 36, 36), "border_radius": _box(ds.radius, ds.radius, ds.radius, ds.radius),
        "css_classes": "tai-form-panel",
    })
    row = _container([left, form], {
        "content_width": "boxed", "flex_direction": "row", "flex_direction_mobile": "column",
        "gap": _px(48), "align_items": "center", "padding": _box(0, 0, 0, 0),
    })
    return _section_shell(section, [row], ds)


def contact(section: SectionContentSpec, ds: DesignSystem, *, emphasis: str = "balanced") -> dict[str, Any]:
    pairs = _split_items(section.items)
    left = _container(_intro(section, ds, emphasis=emphasis), {
        "content_width": "full", "width": _pct(54), "width_mobile": _pct(100),
        "padding": _box(12, 12, 12, 12), "gap": _px(16),
    })
    side_elements: list[dict[str, Any]] = [_heading("Як зв’язатися", ds.text, ds, level="h3", size=24)]
    used: set[str] = set()
    for i, (title, body) in enumerate(pairs[:4]):
        row_children = [_icon(choose_icon(f"{title} {body}", i, used), ds.accent, classes="tai-icon tai-contact-icon"),
                        _container([_heading(title, ds.primary, ds, level="h4", size=18)] +
                                   ([_text(body, ds.muted, ds, size=15)] if body else []),
                                   {"content_width": "full", "padding": _box(0, 0, 0, 0), "gap": _px(2)})]
        side_elements.append(_container(row_children, {
            "content_width": "full", "flex_direction": "row", "gap": _px(14), "padding": _box(0, 0, 0, 0),
            "css_classes": "tai-contact-row",
        }))
    side_elements.extend(_actions(section, ds))
    right = _container(side_elements, {
        "content_width": "full", "width": _pct(44), "width_mobile": _pct(100),
        "background_background": "classic", "background_color": _card_surface(section, ds),
        "padding": _box(34, 34, 34, 34), "border_radius": _box(ds.radius, ds.radius, ds.radius, ds.radius),
        "gap": _px(16), "css_classes": "tai-contact-panel",
    })
    row = _container([left, right], {
        "content_width": "boxed", "flex_direction": "row", "flex_direction_mobile": "column",
        "gap": _px(48), "align_items": "center", "padding": _box(0, 0, 0, 0),
    })
    return _section_shell(section, [row], ds)


def cta(section: SectionContentSpec, ds: DesignSystem, *, emphasis: str = "dramatic") -> dict[str, Any]:
    _, ink, _ = _colors(section, ds)
    body = _intro(section, ds, emphasis=emphasis)
    # Bigger closing statement; CTA bands are the page's final decision moment.
    for widget in body:
        if widget.get("widgetType") == "heading" and widget["settings"].get("header_size") == "h2":
            _scaled(widget["settings"], "typography_font_size", "h2-display")
            widget["settings"]["title"] = _emphasize(section.heading)
    body.extend(_actions(section, ds, accent=True, ink=ink))
    inner = _container(body, {
        "content_width": "boxed", "align_items": "center", "padding": _box(6, 6, 6, 6), "gap": _px(20),
        "css_classes": "tai-cta-panel",
    })
    # Honor Creative Director surface: do not force all CTA sections dark.
    return _section_shell(section, [inner], ds)


def simple_content(section: SectionContentSpec, ds: DesignSystem, *, emphasis: str = "balanced",
                   presentation: str = "grid") -> dict[str, Any]:
    body: list[dict[str, Any]] = [_section_header(section, ds, emphasis=emphasis)]
    if section.items:
        pairs = _split_items(section.items)
        used: set[str] = set()
        body.append(_container([_surface_card(t, b, ds, width=48 if len(pairs) <= 2 else 31, index=i,
                                              variant="content", presentation=presentation,
                                              icon=choose_icon(f"{t} {b}", i, used),
                                              surface=_card_surface(section, ds))
                                for i, (t, b) in enumerate(pairs)], {
            "content_width": "full", "flex_direction": "row", "flex_wrap": "wrap",
            "flex_direction_mobile": "column", "gap": _px(20), "padding": _box(8, 0, 8, 0),
            "css_classes": f"tai-card-grid tai-card-grid-content tai-cards-{presentation} tai-count-{min(len(pairs), 6)}",
        }))
    body.extend(_actions(section, ds, accent=section.style_variant == "dark"))
    return _section_shell(section, body, ds)


def balance_rhythm(specs: list[SectionContentSpec]) -> list[SectionContentSpec]:
    """Avoid three-plus identical background bands in a row (the 'flat
    document' look). Only light variants are alternated; an explicit dark or
    accent choice from the Creative Director is never changed."""
    out: list[SectionContentSpec] = []
    for index, spec in enumerate(specs):
        if (index >= 2 and spec.style_variant in {"default", "soft"}
                and out[-1].style_variant == spec.style_variant == out[-2].style_variant):
            spec = spec.model_copy(update={"style_variant": "soft" if spec.style_variant == "default" else "default"})
        out.append(spec)
    return out


DEFAULT_PRESENTATION = {"process": "timeline", "benefits": "bento", "trust": "list", "services": "grid",
                        "team": "grid", "stats": "grid", "content": "grid"}


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
    "statement": statement,
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
    secondary_image = choose_secondary_page_media(page, media or [], selected_image)
    # Defense in depth for direct compiler callers bypassing the planning gate.
    # Unique, valid Creative Director headings pass through unchanged.
    seen_headings: set[str] = set()
    used_concepts: set[str] = set()
    used_anchors: set[str] = set()
    specs = balance_rhythm(list(specs))
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
        planned = section_layout(layout, index)
        emphasis = planned.heading_emphasis if planned is not None else ("dramatic" if section_type in {"hero", "cta", "statement"} else "balanced")
        presentation = planned.card_presentation if planned is not None else DEFAULT_PRESENTATION.get(section_type, "grid")
        if section_type == "hero":
            # A typography-only scene must not render an unused photo layer.
            requested_layout = section_layout(layout, index)
            if (requested_layout is not None and selected_image is not None
                    and selected_image.get("ai_generated_role") == "hero"
                    and requested_layout.hero_scene == "typographic"):
                # Opt-in photography must not be discarded by a text-only scene.
                requested_layout = requested_layout.model_copy(update={"hero_scene": "editorial", "visual_treatment": "media"})
            if requested_layout is not None:
                resolved_scene = resolve_scene(requested_layout,
                    int(selected_image is not None) + int(secondary_image is not None))
                element = hero(section, ds,
                    selected_image if resolved_scene.media_count else None,
                    secondary_image if resolved_scene.media_count == 2 else None, emphasis=emphasis)
            else:
                element = hero(section, ds, selected_image, emphasis=emphasis)
        elif section_type in {"products", "services", "benefits", "trust", "team", "process", "stats"}:
            element = cards(section, ds, selected_image, live_catalog=live_catalog,
                            product_names=product_names, h1=(index == 0), product_media=media,
                            presentation=presentation, emphasis=emphasis)
        elif renderer is simple_content:
            element = simple_content(section, ds, emphasis=emphasis, presentation=presentation)
        else:
            element = renderer(section, ds, emphasis=emphasis)
        # Stable in-page anchors (#products, #process...) let a secondary CTA
        # scroll to a real section instead of inventing another page.
        if section_type not in used_anchors and re.fullmatch(r"[a-z]{2,20}", section_type):
            used_anchors.add(section_type)
            element["settings"]["_element_id"] = section_type
        # Put editorial AI concepts into distinct, native Elementor Image widgets.
        # These are not WooCommerce product images. Only the home page receives
        # the page-scoped editorial media created for its story/collection.
        editorial_role = ("collection" if section_type == "products" else
                          "story" if section_type in {"content", "benefits", "trust", "process"} else "")
        if page.page_slug == "home" and editorial_role and editorial_role not in used_concepts:
            candidate = next((m for m in (media or [])
                if m.get("ai_generated_role") == editorial_role and _validated_media_url(m)), None)
            if candidate:
                used_concepts.add(editorial_role)
                visual = _container([_image_widget(candidate)], {
                    "content_width": "full", "css_classes": f"tai-editorial-media tai-editorial-media-{editorial_role}",
                    "padding": _box(0, 0, 0, 0), "width": _pct(100),
                })
                # Editorial media comes before collection text/cards to establish
                # hierarchy; it is never put inside a verified product card.
                if editorial_role == "collection":
                    element["elements"].insert(0, visual)
                else:
                    element["elements"].append(visual)
        section_spec = section_layout(layout, index)
        if (section_spec is not None and section_type == "hero" and selected_image is not None
                and selected_image.get("ai_generated_role") == "hero"
                and section_spec.hero_scene == "typographic"):
            section_spec = section_spec.model_copy(update={"hero_scene": "editorial", "visual_treatment": "media"})
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
            if section_type == "hero":
                resolved_scene = resolve_scene(section_spec,
                    int(selected_image is not None) + int(secondary_image is not None))
                # The earlier typography trim is a legacy layout rule. Real
                # owner-selected media must not be pruned by an unrelated
                # visual_treatment text hint if the scene actually uses it.
                if resolved_scene.media_count and section_spec.visual_treatment == "typography":
                    section_spec = section_spec.model_copy(update={"visual_treatment": "media"})
            _apply_generative_layout(element, section_spec, page_slug=page.page_slug, index=index)
            if section_type == "hero":
                media_count = int(selected_image is not None) + int(secondary_image is not None)
                scene = resolve_scene(section_spec, media_count)
                element["settings"]["css_classes"] += " " + scene_classes(section_spec, scene)
                # Structural hygiene: don't render second image for single-media modes.
                if scene.media_count < 2:
                    for grid in element.get("elements", []):
                        if "tai-hero-grid" not in grid.get("settings", {}).get("css_classes", ""):
                            continue
                        for media_container in grid.get("elements", [])[1:]:
                            media_container["elements"] = [child for child in media_container.get("elements", [])
                                if "tai-hero-photo-secondary" not in child.get("settings", {}).get("css_classes", "")]
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
