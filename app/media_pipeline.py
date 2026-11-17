"""Source-aware, bounded, non-product media planning for draft Elementor sites.

Generated visuals are editorial concepts, never evidence of actual products,
team members, property, certifications or production processes.
"""
from __future__ import annotations

from typing import Any
from .models import ExperienceSpec, ProjectBrief

ALLOWED_ROLES = {"hero", "collection", "story"}


def build_media_manifest(brief: ProjectBrief, experience: ExperienceSpec, user_request: str = "") -> list[dict[str, Any]]:
    pages = {page.page_slug: page for page in experience.pages}
    page = pages.get("home") or next(iter(experience.pages), None)
    if page is None:
        return []
    sections = page.section_specs
    hero = sections[0] if sections else None
    collection = next((s for s in sections if s.section_type == "products"), None)
    story = next((s for s in sections if s.section_type in {"content", "benefits", "trust", "process"}), None)
    direction = str(experience.design_direction or "editorial")[:200]
    palette = experience.design_system
    style = f"Website category: {brief.site_type[:80]}. Main goal: {brief.primary_goal[:180]}. Owner request theme: {user_request[:220].replace(chr(10), ' ')}. Art direction: {direction}. Brand palette: {palette.primary}, {palette.accent}, {palette.background}."
    shared = (
        "Create one visually rich, high-end editorial scene for a premium website. "
        "No text, typography, logos, brand names, watermarks, labels, readable product packaging, "
        "price tags or identifiable real people. Original cohesive photographic art direction. "
        "Concept illustration only: never suggest this is a genuine photo of a particular sold item. "
        + style
    )
    out = []
    requests = [
        ("hero", hero, "1536x1024", "Atmospheric full-bleed opening composition, strong visual focal point with negative space for separate heading and CTA."),
        ("collection", collection, "1024x1024", "Editorial composition expressing the category/collection, tactile materials and evocative lighting, without inventing exact real SKUs."),
        ("story", story, "1536x1024", "Intimate storytelling still life, subtle craft cues without depicting an actual factory, employee or claimed manufacturing process."),
    ]
    for role, section, size, instruction in requests:
        if section is None:
            continue
        title = str(section.heading or "")[:110]
        # Do not put unverifiable body copy into a literal visual factual claim.
        prompt = f"{shared} Section theme: {title}. {instruction}"
        out.append({
            "key": role,
            "role": role,
            "page_slug": page.page_slug,
            "size": size,
            "prompt": prompt[:1300],
            "alt": f"AI-концепт для секції «{title}» (ілюстративне зображення)",
            "provenance": "ai_generated_concept_not_product_photo",
        })
    return out[:3]
