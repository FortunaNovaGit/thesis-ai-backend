"""Bounded, zero-token repairs before the unchanged fail-closed quality gate.

Only headings supported by existing section content or semantically safe navigation
labels are rewritten. Never fabricate testimonials, offers, prices or business facts.
"""
from __future__ import annotations

from dataclasses import dataclass

from .content_quality import canonical, looks_like_planning
from .models import ExperienceSpec, SectionContentSpec

# These are heading *vocabulary*, not complete copy or website templates.
PURPOSE_LABELS: dict[str, tuple[str, ...]] = {
    "hero": ("Знайомство", "З чого почати"),
    "products": ("Перегляньте асортимент", "Як обрати набір", "Колекції та формати"),
    "services": ("Напрямки та можливості", "Оберіть потрібний напрямок"),
    "benefits": ("Що варто врахувати", "Варіанти для ваших потреб"),
    "trust": ("Відповіді перед вибором", "Про важливі деталі"),
    "process": ("Послідовність кроків", "Як перейти до наступного кроку"),
    "contact": ("Напишіть нам", "Запитання та звернення"),
    "booking": ("Залиште звернення", "Поставте запитання"),
    "faq": ("Запитання та відповіді", "Що ще варто знати"),
    "cta": ("Оберіть наступний крок", "Готові продовжити?"),
    "content": ("Детальніше про вибір", "Корисні деталі"),
    "team": ("Про команду", "Поставте запитання спеціалістам"),
    "stats": ("Важливе перед вибором", "Коротко про деталі"),
}


@dataclass(frozen=True)
class Repair:
    page: str
    section_index: int
    before: str
    after: str
    reason: str = "duplicate_heading"

    def as_dict(self) -> dict[str, str | int]:
        return self.__dict__.copy()


def _item_title(section: SectionContentSpec) -> str | None:
    for item in section.items:
        value = item.split(" — ", 1)[0].split(": ", 1)[0].strip(" ·.-")
        if 12 <= len(value) <= 62 and not looks_like_planning(value):
            return value
    return None


def repair_duplicate_headings(experience: ExperienceSpec) -> tuple[ExperienceSpec, list[Repair]]:
    """At most one substitution per section; unresolved issues remain gate failures."""
    updated_pages = []
    repairs: list[Repair] = []
    global_seen: set[str] = set()
    for page in experience.pages:
        seen: set[str] = set()
        sections = []
        for idx, section in enumerate(page.section_specs):
            original = section.heading.strip()
            key = canonical(original)
            if not key or (key not in seen and key not in global_seen and not looks_like_planning(original)):
                if key:
                    seen.add(key)
                    global_seen.add(key)
                sections.append(section)
                continue
            candidates = []
            item = _item_title(section)
            if item:
                candidates.append(item)
            candidates.extend(PURPOSE_LABELS.get(section.section_type, ()))
            # Grounded page label differentiates two semantically identical blocks.
            if page.page_name.strip() and not looks_like_planning(page.page_name):
                candidates.extend(f"{label} — {page.page_name}" for label in PURPOSE_LABELS.get(section.section_type, ()))
            replacement = next((x for x in candidates if canonical(x) and canonical(x) not in seen and canonical(x) not in global_seen
                                and not looks_like_planning(x)), None)
            if replacement:
                repairs.append(Repair(page.page_slug, idx, original, replacement,
                                      "duplicate_heading" if key in seen else "repeated_site_heading"))
                section = section.model_copy(update={"heading": replacement})
                key = canonical(replacement)
            if key:
                seen.add(key)
                global_seen.add(key)
            sections.append(section)
        updated_pages.append(page.model_copy(update={"section_specs": sections,
                                              "seo": page.seo.model_copy(update={"h1": sections[0].heading}) if sections else page.seo}))
    return experience.model_copy(update={"pages": updated_pages}), repairs
