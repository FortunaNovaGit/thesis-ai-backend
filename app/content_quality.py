"""Deterministic pre-build editorial checks.

No AI calls are needed to catch duplicate page copy, planning notes,
unsafe links, and weak section content. This is an artifact check, NOT
browser/visual QA or a factual verification service.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .models import ExperienceSpec

INTERNAL_COPY = (
    "ця сторінка", "сторінка має", "додайте підтвердж", "додайте інформац",
    "після генерації", "контент секції", "мета сторінки", "план сторінки",
    "надати канал", "сформувати довіру", "зменшити friction", "посадкова сторінка",
    "основна конверсія", "використайте віджет", "заповніть у редакторі",
    "додайте у wordpress", "підставте сюди", "lorem ipsum", "placeholder text",
    "wireframe", "section purpose", "content goes here", "згенеруйте контент",
    "додайте товар", "призначення сторінки", "ключове повідомлення", "текст для секції",
)


def canonical(text: str) -> str:
    return " ".join(re.findall(r"[^\W_]+", (text or "").casefold(), flags=re.UNICODE))


def too_similar(a: str, b: str) -> bool:
    a_norm, b_norm = canonical(a), canonical(b)
    if len(a_norm) < 65 or len(b_norm) < 65:
        return False
    if a_norm == b_norm:
        return True
    # Token overlap can match general business language; high threshold only.
    aset, bset = set(a_norm.split()), set(b_norm.split())
    return len(aset & bset) / max(1, len(aset | bset)) >= 0.88


def looks_like_planning(text: str) -> bool:
    value = (text or "").casefold()
    return any(marker in value for marker in INTERNAL_COPY)


def safe_cta_url(url: str | None) -> bool:
    if not url:
        return False
    if url.startswith("#"):
        return bool(re.fullmatch(r"#[a-zA-Z][\w-]{0,79}", url))
    if url.startswith("/") and not url.startswith("//"):
        return not any(x in url for x in ("\\", "\r", "\n", "<", ">"))
    # External CTA destinations are not automatically trusted; require user approval.
    return False


@dataclass(frozen=True)
class EditorialIssue:
    code: str
    page: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "page": self.page, "detail": self.detail}


def audit_experience(experience: ExperienceSpec) -> list[EditorialIssue]:
    issues: list[EditorialIssue] = []
    body_history: list[tuple[str, str]] = []
    for page in experience.pages:
        headings: set[str] = set()
        for section in page.section_specs:
            if section.section_type == "hero" and len(canonical(section.body)) < 20:
                issues.append(EditorialIssue("empty_hero", page.page_slug, "Hero lacks useful introduction"))
            if not section.body.strip() and not section.items and section.section_type not in {"products", "stats"}:
                issues.append(EditorialIssue("empty_section", page.page_slug, section.section_type))
            if looks_like_planning(section.heading) or looks_like_planning(section.body):
                issues.append(EditorialIssue("planning_copy", page.page_slug, section.section_type))
            heading = canonical(section.heading)
            if heading and heading in headings:
                issues.append(EditorialIssue("duplicate_heading", page.page_slug, section.heading))
            headings.add(heading)
            if any(looks_like_planning(item) for item in section.items):
                issues.append(EditorialIssue("planning_item", page.page_slug, section.section_type))
            items_seen: set[str] = set()
            for item in section.items:
                key = canonical(item)
                if key and key in items_seen:
                    issues.append(EditorialIssue("duplicate_item", page.page_slug, section.section_type))
                items_seen.add(key)
            body = section.body.strip()
            for other_page, other_body in body_history:
                if too_similar(body, other_body):
                    issues.append(EditorialIssue("repeated_body", page.page_slug, f"Repeated with {other_page}"))
                    break
            if body:
                body_history.append((page.page_slug, body))
            if section.cta_label and not safe_cta_url(section.cta_url):
                issues.append(EditorialIssue("unsafe_cta", page.page_slug, section.section_type))
        if page.seo.h1 and looks_like_planning(page.seo.h1):
            issues.append(EditorialIssue("planning_h1", page.page_slug, "SEO H1"))
        if looks_like_planning(page.seo.meta_description):
            issues.append(EditorialIssue("planning_meta", page.page_slug, "SEO description"))
    return issues
