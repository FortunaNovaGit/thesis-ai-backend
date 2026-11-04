"""Deterministic, policy-bounded interpretation of AI-produced layout instructions.

Elementor containers/widgets remain editable. No arbitrary CSS, remote image
URLs, HTML snippets, custom scripts or WordPress shell commands are accepted.
"""
from __future__ import annotations

from .models import ExperienceSpec, PageLayoutSpec, SectionLayoutSpec


def validate_creative_layout(experience: ExperienceSpec, *, required: bool = False) -> dict[str, PageLayoutSpec]:
    spec = experience.generative_design
    if spec is None:
        if required:
            raise ValueError("Creative Director did not return a GenerativeDesignSpec")
        return {}
    spec.selected()  # Verify the selected proposal actually exists.
    slugs = {page.page_slug: page for page in experience.pages}
    output: dict[str, PageLayoutSpec] = {}
    for page in spec.page_layouts:
        if page.page_slug not in slugs:
            raise ValueError(f"Layout references unknown page {page.page_slug!r}")
        if page.page_slug in output:
            raise ValueError(f"Duplicate layout for {page.page_slug!r}")
        seen = set()
        for section in page.sections:
            if section.section_index >= len(slugs[page.page_slug].section_specs):
                raise ValueError(f"Layout index {section.section_index} out of bounds on {page.page_slug}")
            if section.section_index in seen:
                raise ValueError(f"Duplicate layout index on {page.page_slug}")
            seen.add(section.section_index)
        output[page.page_slug] = page
    # A creative spec that leaves Home without a hero layout is misleading.
    if required and "home" in slugs and ("home" not in output or 0 not in {
        s.section_index for s in output["home"].sections
    }):
        raise ValueError("GenerativeDesignSpec is missing the Home hero layout")
    return output


def section_layout(page: PageLayoutSpec | None, index: int) -> SectionLayoutSpec | None:
    if page:
        return next((layout for layout in page.sections if layout.section_index == index), None)
    return None
