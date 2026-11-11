"""v0.9.2 Creative Director output contract.

The Design/Content/SEO agent uses small, independently validated artifacts:
(1) a shared art direction, (2) one editable content/layout document per page.
No generic fallback copy is injected into a successful creative page response.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import (
    ArchitectureBundle, CreativeDirection, DesignSystem, ExperienceSpec,
    GenerativeDesignSpec, PageExperienceSpec, PageLayoutSpec,
    SectionContentSpec, SectionLayoutSpec, SeoSpec,
)


SECTION_KINDS = Literal[
    "hero", "services", "benefits", "trust", "team", "process", "stats",
    "faq", "content", "booking", "contact", "cta", "products",
]


class CreativeFoundation(BaseModel):
    """Compact, site-wide Creative Director artifact. No page copy here."""
    model_config = ConfigDict(extra="forbid")
    design_direction: str = Field(min_length=10, max_length=220)
    design_system: DesignSystem
    candidates: list[CreativeDirection] = Field(min_length=2, max_length=3)
    selected_direction_id: str
    selection_reason: str = Field(min_length=12, max_length=500)

    @model_validator(mode="after")
    def verify_choice(self) -> "CreativeFoundation":
        ids = [c.id for c in self.candidates]
        if len(ids) != len(set(ids)) or self.selected_direction_id not in ids:
            raise ValueError("selected_direction_id must reference one unique candidate")
        from .design_safety import accessible_design_palette
        self.design_system = accessible_design_palette(self.design_system)
        return self


class CreativeSection(BaseModel):
    """Small semantically grounded creative building block with AI-authored geometry."""
    model_config = ConfigDict(extra="forbid")
    kind: SECTION_KINDS
    headline: str = Field(min_length=7, max_length=180)
    body: str = Field(min_length=30, max_length=1400)
    eyebrow: str = Field(default="", max_length=95)
    items: list[str] = Field(default_factory=list, max_length=8)
    cta_label: str | None = Field(default=None, max_length=100)
    cta_url: str | None = Field(default=None, max_length=256)
    style_variant: Literal["default", "soft", "accent", "dark"] = "default"
    # Elementor V3-native controls, not arbitrary CSS. Index is assigned by compiler.
    composition: Literal["split", "stacked", "centered", "offset"]
    visual_treatment: Literal["abstract", "typography", "media"]
    surface_treatment: Literal["canvas", "tinted", "bordered"]
    card_presentation: Literal["grid", "bento", "list"]
    heading_emphasis: Literal["calm", "balanced", "dramatic"] = "balanced"
    motif: Literal["none", "halo", "lines", "frame", "gradient"] = "none"
    content_alignment: Literal["start", "center"] = "start"
    media_position: Literal["start", "end"] = "end"
    art_ratio: Literal["square", "portrait", "landscape", "wide"] = "portrait"
    max_width: int = Field(default=1200, ge=720, le=1440)
    text_width_pct: int = Field(default=55, ge=35, le=70)
    card_columns: int = Field(default=3, ge=1, le=4)
    vertical_space: int = Field(default=88, ge=36, le=168)
    accent_detail: Literal["none", "rule", "index"] = "none"
    hero_scene: Literal["auto", "editorial", "cinematic", "collage", "poster", "typographic"] = "auto"
    hero_motion: Literal["none", "subtle"] = "none"
    hero_height: Literal["standard", "tall", "fullscreen"] = "standard"


class CreativePage(BaseModel):
    """ONE page, not all pages + site design in one overloaded model output."""
    model_config = ConfigDict(extra="forbid")
    page_slug: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9_-]+$")
    sections: list[CreativeSection] = Field(min_length=2, max_length=12)
    seo_title: str = Field(min_length=12, max_length=160)
    meta_description: str = Field(min_length=40, max_length=320)

    @model_validator(mode="after")
    def ensure_primary_heading(self) -> "CreativePage":
        if self.sections[0].kind != "hero":
            raise ValueError("first section must have kind=hero and its headline is the page H1")
        from .content_quality import canonical, too_similar, looks_like_planning, looks_like_filler, safe_cta_url
        headlines: set[str] = set()
        bodies: list[str] = []
        page_labels = {"головна", "магазин", "контакти", "home", "shop", "contact", "about", "про нас"}
        for index, section in enumerate(self.sections):
            key = canonical(section.headline)
            if key in headlines:
                raise ValueError(f"duplicate headline in section {index}: {section.headline!r}; write a specific different headline")
            if key in page_labels:
                raise ValueError(f"section {index} uses a generic navigation label as headline: {section.headline!r}")
            if section.cta_label and not safe_cta_url(section.cta_url):
                raise ValueError(f"section {index} has an unsafe or missing CTA destination")
            if looks_like_planning(section.headline) or looks_like_planning(section.body):
                raise ValueError(f"section {index} includes editor/planning copy")
            if looks_like_filler(section.headline) or looks_like_filler(section.body):
                raise ValueError(f"section {index} contains generic filler; write useful customer-facing copy")
            if any(too_similar(section.body, previous) for previous in bodies):
                raise ValueError(f"section {index} repeats body text; give it a distinct visitor purpose")
            headlines.add(key)
            bodies.append(section.body)
        return self


def page_copy_conflicts(page: CreativePage, earlier: list[CreativePage]) -> list[str]:
    """Actionable cross-page editorial conflicts; no generic replacement copy."""
    from .content_quality import canonical, too_similar
    previous = [(other.page_slug, section)
                for other in earlier for section in other.sections]
    conflicts: list[str] = []
    for index, section in enumerate(page.sections):
        heading = canonical(section.headline)
        for slug, old in previous:
            if heading and heading == canonical(old.headline):
                conflicts.append(f"section[{index}] repeats headline {section.headline!r} from {slug}")
            if too_similar(section.body, old.body):
                conflicts.append(f"section[{index}] repeats body from {slug}; write a page-specific paragraph")
    return conflicts


def compose_experience(
    architecture: ArchitectureBundle,
    foundation: CreativeFoundation,
    generated_pages: list[CreativePage],
) -> ExperienceSpec:
    """Deterministic compilation: preserve authored copy, validate coverage first.

    Fail rather than silently turning a malformed creative page into marketing
    boilerplate. Existing `reconcile_experience` and editorial gate still follow.
    """
    expected = [page.slug for page in architecture.pages]
    got = [page.page_slug for page in generated_pages]
    if got != expected or len(set(got)) != len(got):
        raise ValueError(f"Creative page coverage mismatch: expected {expected}, received {got}")

    for index, source in enumerate(generated_pages):
        conflicts = page_copy_conflicts(source, generated_pages[:index])
        if conflicts:
            raise ValueError(f"Creative page {source.page_slug} has repeated site copy: " + "; ".join(conflicts[:6]))

    pages: list[PageExperienceSpec] = []
    layouts: list[PageLayoutSpec] = []
    for intent, source in zip(architecture.pages, generated_pages):
        required_kinds = [str(x).strip().lower() for x in intent.section_goals]
        available = [section.kind for section in source.sections]
        # Don't accept a page with four styled empty sections and no actual
        # semantic fulfillment. The reconciler must not hide such failures.
        missing = sorted({x for x in required_kinds if x in {
            "hero", "services", "benefits", "trust", "team", "process",
            "stats", "faq", "content", "booking", "contact", "cta", "products",
        } and x not in available})
        if missing:
            raise ValueError(f"Creative page {intent.slug} missing requested section types: {missing}")
        result_sections: list[SectionContentSpec] = []
        layout_sections: list[SectionLayoutSpec] = []
        for index, section in enumerate(source.sections):
            result_sections.append(SectionContentSpec(
                section_type=section.kind,
                component_key=section.kind,
                eyebrow=section.eyebrow,
                heading=section.headline.strip(),
                body=section.body.strip(),
                items=section.items,
                cta_label=section.cta_label,
                cta_url=section.cta_url,
                style_variant=section.style_variant,
            ))
            layout_sections.append(SectionLayoutSpec(
                section_index=index,
                composition=section.composition,
                visual_treatment=section.visual_treatment,
                surface_treatment=("canvas" if section.style_variant in {"dark", "accent"} and
                                   section.surface_treatment == "tinted" else section.surface_treatment),
                card_presentation=section.card_presentation,
                heading_emphasis=section.heading_emphasis,
                motif=section.motif,
                content_alignment=section.content_alignment,
                media_position=section.media_position,
                art_ratio=section.art_ratio,
                text_width_pct=section.text_width_pct,
                card_columns=section.card_columns,
                vertical_space=section.vertical_space,
                accent_detail=section.accent_detail,
                hero_scene=section.hero_scene,
                hero_motion=section.hero_motion,
                hero_height=section.hero_height,
                max_width=section.max_width,
            ))
        seo = SeoSpec(
            slug="/" if intent.slug == "home" else f"/{intent.slug}/",
            title=source.seo_title,
            meta_description=source.meta_description,
            h1=result_sections[0].heading,
            internal_link_targets=[],
            schema_types=["WebPage"],
        )
        pages.append(PageExperienceSpec(
            page_name=intent.name,
            page_slug=intent.slug,
            page_goal=intent.purpose,
            sections=[s.section_type for s in result_sections],
            section_specs=result_sections,
            seo=seo,
        ))
        layouts.append(PageLayoutSpec(page_slug=intent.slug, sections=layout_sections))

    return ExperienceSpec(
        generation_contract="creative_page_v093",
        design_direction=foundation.design_direction,
        design_system=foundation.design_system,
        pages=pages,
        generative_design=GenerativeDesignSpec(
            candidates=foundation.candidates,
            selected_direction_id=foundation.selected_direction_id,
            selection_reason=foundation.selection_reason,
            page_layouts=layouts,
        ),
    )
