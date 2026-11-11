"""Deterministic and safe Visual Composer for native Elementor V3 page scenes.

The AI chooses constrained semantic layout parameters, not arbitrary HTML,
JavaScript, URLs, selectors or CSS. Actual media is always pre-existing WP media.
"""
from __future__ import annotations
from dataclasses import dataclass

from .models import SectionLayoutSpec

SCENES = ("editorial", "cinematic", "collage", "poster", "typographic")

@dataclass(frozen=True)
class HeroScene:
    name: str
    media_count: int
    uses_overlay: bool
    downgrade_reason: str | None = None


def resolve_scene(spec: SectionLayoutSpec, image_count: int) -> HeroScene:
    """Resolve unavailable assets into an honest, editable alternative."""
    if image_count < 0:
        raise ValueError("image_count must be non-negative")
    requested = spec.hero_scene
    if requested == "auto":
        requested = ("typographic" if image_count == 0 else
                     "poster" if spec.composition == "centered" else
                     "editorial" if spec.composition == "offset" else "cinematic")
    if image_count == 0 and requested != "typographic":
        return HeroScene("typographic", 0, False, "missing_real_image")
    if requested == "collage" and image_count < 2:
        return HeroScene("editorial", 1, True, "missing_second_real_image")
    if requested == "typographic":
        return HeroScene("typographic", 0, False)
    return HeroScene(requested, 2 if requested == "collage" else 1,
                     requested in {"editorial", "cinematic", "collage", "poster"})


def scene_classes(spec: SectionLayoutSpec, scene: HeroScene) -> str:
    """Only allowlisted class names derived from Pydantic Literal values."""
    return " ".join(("tai-vc", f"tai-scene-{scene.name}",
                     f"tai-scene-height-{spec.hero_height}",
                     f"tai-scene-motion-{spec.hero_motion}",
                     "tai-scene-with-media" if scene.media_count else "tai-scene-no-media"))
