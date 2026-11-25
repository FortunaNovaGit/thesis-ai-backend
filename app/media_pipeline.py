"""Source-aware, bounded, non-product media planning for draft Elementor sites.

Generated visuals are editorial concepts, never evidence of actual products,
team members, property, certifications or production processes.

v0.13 "auto imagery": every image-friendly section of every planned page gets
a deterministic *media slot*. The same slot function is used by the media
manifest (what to generate) and by the Elementor compiler (where to place it),
so a generated attachment can only land in the section it was made for.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

from .models import ExperienceSpec, ProjectBrief

# Kept for backwards compatibility (v0.11 attachments use these roles).
LEGACY_ROLES = {"hero", "collection", "story"}
SLOT_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,31}$")
DEFAULT_MAX_IMAGES = 10
HARD_MAX_IMAGES = 12

# People-centred sections (team) and number-only sections (stats) never get
# generated imagery: it would imply real staff or real metrics.
IMAGE_SECTION_TYPES = {"products", "benefits", "services", "content", "process", "trust",
                       "statement", "cta", "faq", "contact", "booking"}
STORY_TYPES = {"content", "benefits", "trust", "process"}

SIZES = {
    "hero": "1536x1024", "detail": "1024x1536", "products": "1536x1024",
    "statement": "1536x1024", "cta": "1536x1024",
}
INSTRUCTIONS = {
    "hero": "Atmospheric opening composition, strong focal point, generous calm negative space on one side for a separate heading and buttons.",
    "detail": "Close-up macro detail of materials and textures from the same art direction, vertical framing, shallow depth of field.",
    "products": "Editorial still life expressing the category and collection mood: tactile materials, evocative light. Do not depict exact real SKUs or readable packaging.",
    "benefits": "Calm lifestyle-free still life that evokes quality and care; objects, materials and light only.",
    "services": "Editorial still life evoking the service experience through objects, materials and light; no people.",
    "content": "Intimate storytelling still life, subtle craft cues without depicting an actual factory, employee or claimed manufacturing process.",
    "process": "Hands-free arrangement of tools and raw materials that hints at craft and sequence; no factory, no employees, no claimed process.",
    "trust": "Quiet, elegant still life suggesting reliability and care; no documents, certificates, logos or awards.",
    "statement": "Wide cinematic mood image with soft low-contrast areas so a large overlaid headline stays readable; abstract and atmospheric.",
    "cta": "Wide atmospheric background with soft gradients and low detail so overlaid text and buttons stay readable.",
    "faq": "Minimal, soft still life with a single object and plenty of empty space; calm and reassuring.",
    "contact": "Inviting minimal still life of a gift or a table setting in warm light; no maps, addresses, storefronts or people.",
    "booking": "Inviting minimal still life suggesting preparation for an occasion; no people, no calendars with readable text.",
}


def slot_prefix(page_slug: str) -> str:
    """Home keeps v0.11 role names; other pages are namespaced by their slug."""
    if page_slug == "home":
        return ""
    clean = re.sub(r"[^a-z0-9-]+", "-", page_slug.casefold()).strip("-")[:18] or "page"
    return clean + "-"


def page_media_slots(page_slug: str, section_types: Iterable[str]) -> list[dict[str, Any]]:
    """Deterministic, unique slots for one page, in visual order.

    Returns dicts: {index, key, kind}. ``kind`` selects size/instructions and
    the compiler placement. Home: hero, hero-detail, collection, story, ...
    Other pages: <slug>-hero, <slug>-<type>.
    """
    prefix = slot_prefix(page_slug)
    slots: list[dict[str, Any]] = []
    used: set[str] = set()
    story_taken = False
    for index, raw_type in enumerate(section_types):
        section_type = (raw_type or "content").lower().strip()
        if index == 0:
            slots.append({"index": 0, "key": f"{prefix}hero", "kind": "hero"})
            used.add(f"{prefix}hero")
            if page_slug == "home":
                slots.append({"index": 0, "key": "hero-detail", "kind": "detail"})
                used.add("hero-detail")
            continue
        if section_type not in IMAGE_SECTION_TYPES:
            continue
        if page_slug == "home" and section_type == "products" and "collection" not in used:
            key = "collection"
        elif page_slug == "home" and section_type in STORY_TYPES and not story_taken:
            key, story_taken = "story", True
        else:
            key = f"{prefix}{section_type}"
        if key in used or not SLOT_RE.fullmatch(key):
            continue
        used.add(key)
        slots.append({"index": index, "key": key, "kind": section_type})
    return slots


def _priority(page_slug: str, slot: dict[str, Any]) -> tuple[int, int]:
    """Visitors see the home page and every page opening first.

    0: home hero / story / collection, 1: other pages' heroes, 2: rest of home,
    3: rest of other pages, 4: the optional home hero detail (collage).
    """
    if page_slug == "home":
        if slot["kind"] == "detail":
            return (4, 0)
        rank = {"hero": 0, "story": 1, "collection": 2}.get(slot["key"])
        return (0, rank) if rank is not None else (2, slot["index"])
    return (1 if slot["kind"] == "hero" else 3, slot["index"])


def build_media_manifest(brief: ProjectBrief, experience: ExperienceSpec, user_request: str = "",
                         max_images: int = DEFAULT_MAX_IMAGES) -> list[dict[str, Any]]:
    limit = max(1, min(HARD_MAX_IMAGES, int(max_images or DEFAULT_MAX_IMAGES)))
    direction = str(experience.design_direction or "editorial")[:200]
    palette = experience.design_system
    style = (f"Website category: {brief.site_type[:80]}. Main goal: {brief.primary_goal[:180]}. "
             f"Owner request theme: {user_request[:220].replace(chr(10), ' ')}. Art direction: {direction}. "
             f"Brand palette: {palette.primary}, {palette.accent}, {palette.background}.")
    shared = (
        "Create one visually rich, high-end editorial image for a premium website. "
        "No text, typography, logos, brand names, watermarks, labels, readable product packaging, "
        "price tags or identifiable real people. Original cohesive photographic art direction, "
        "consistent colour grading across the whole website. "
        "Concept illustration only: never suggest this is a genuine photo of a particular sold item. "
        + style
    )
    candidates: list[tuple[tuple[int, int], dict[str, Any]]] = []
    for page_order, page in enumerate(experience.pages):
        sections = page.section_specs
        if not sections:
            continue
        for slot in page_media_slots(page.page_slug, [s.section_type for s in sections]):
            section = sections[slot["index"]]
            title = str(section.heading or page.page_name or "")[:110]
            kind = slot["kind"]
            # Do not put unverifiable body copy into a literal visual factual claim.
            prompt = f"{shared} Page: {page.page_name[:60]}. Section theme: {title}. {INSTRUCTIONS.get(kind, INSTRUCTIONS['content'])}"
            group, rank = _priority(page.page_slug, slot)
            candidates.append(((group, page_order * 1000 + rank), {
                "key": slot["key"],
                "role": slot["key"],
                "kind": kind,
                "page_slug": page.page_slug,
                "section_index": slot["index"],
                "size": SIZES.get(kind, "1024x1024"),
                "prompt": prompt[:1300],
                "alt": f"AI-концепт для секції «{title}» (ілюстративне зображення)",
                "provenance": "ai_generated_concept_not_product_photo",
            }))
    candidates.sort(key=lambda pair: pair[0])
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _, item in candidates:
        if item["key"] in seen:
            continue
        seen.add(item["key"])
        out.append(item)
        if len(out) >= limit:
            break
    return out


def manifest_roles(bundle: dict[str, Any]) -> set[str]:
    return {str(item.get("role")) for item in bundle.get("media_manifest", []) if isinstance(item, dict)}
