"""Strict top-level parameter contracts for planned mutating WordPress abilities.

Generated page JSON is deliberately not interpreted as a new PHP/JS capability:
Elementor nested elements are validated again by the Bridge allowlist.
"""
from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class StrictParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PluginParams(StrictParams):
    plugin_slug: Literal["elementor", "woocommerce", "advanced-custom-fields", "contact-form-7", "wordpress-seo", "seo-by-rank-math"]


class ThemeParams(StrictParams):
    theme_slug: Literal["hello-elementor"]


class PageParams(StrictParams):
    title: str = Field(min_length=1, max_length=180)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", min_length=1, max_length=120)
    elements: list[dict[str, Any]] = Field(default_factory=list, max_length=300)
    settings: dict[str, Any] = Field(default_factory=dict)
    content: str = Field(default="", max_length=250_000)


class SeoParams(StrictParams):
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=120)
    seo_title: str = Field(min_length=1, max_length=300)
    meta_description: str = Field(min_length=1, max_length=1000)


class DesignParams(StrictParams):
    primary: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    accent: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    background: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    surface: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    text: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    muted: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    heading_font: str = Field(min_length=1, max_length=90)
    body_font: str = Field(min_length=1, max_length=90)
    container_width: int = Field(ge=700, le=1800)
    radius: int = Field(ge=0, le=60)


class IdentityParams(StrictParams):
    site_title: str = Field(min_length=1, max_length=180)
    tagline: str = Field(max_length=280)


class MenuParams(StrictParams):
    menu_name: str = Field(min_length=1, max_length=100)
    page_slugs: list[str] = Field(min_length=1, max_length=30)
    assign_primary: bool = True


class HomeParams(StrictParams):
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=120)


class ContactFormParams(StrictParams):
    title: str = Field(min_length=1, max_length=120)


class CommerceParams(StrictParams):
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class ACFParams(StrictParams):
    content_types: list[dict[str, Any]] = Field(max_length=12)


SCHEMAS: dict[str, type[BaseModel]] = {
    **{f"thesis-ai-bridge/{name}": PluginParams for name in
       ["ensure-approved-plugin", "install-approved-plugin", "activate-approved-plugin", "deactivate-approved-plugin"]},
    "thesis-ai-bridge/ensure-approved-theme": ThemeParams,
    "thesis-ai-bridge/elementor-ensure-draft-page": PageParams,
    "thesis-ai-bridge/ensure-draft-page": PageParams,
    "thesis-ai-bridge/create-draft-page": PageParams,
    "thesis-ai-bridge/set-page-seo": SeoParams,
    "thesis-ai-bridge/apply-site-design": DesignParams,
    "thesis-ai-bridge/update-site-identity": IdentityParams,
    "thesis-ai-bridge/ensure-navigation-menu": MenuParams,
    "thesis-ai-bridge/set-homepage-by-slug": HomeParams,
    "thesis-ai-bridge/ensure-contact-form": ContactFormParams,
    "thesis-ai-bridge/configure-woocommerce": CommerceParams,
    "thesis-ai-bridge/apply-acf-model": ACFParams,
}


def validate_action(ability: str, params: dict[str, Any]) -> str | None:
    if not isinstance(params, dict):
        return "Parameters must be a JSON object"
    if len(json.dumps(params, ensure_ascii=False, default=str).encode("utf-8")) > 350_000:
        return "Action parameters exceed the 350 KB size limit"
    spec = SCHEMAS.get(ability)
    if spec is None:
        return None  # The Policy Engine separately default-denies unknown abilities.
    try:
        spec.model_validate(params)
    except ValidationError as exc:
        error = exc.errors()[0]
        return f"Invalid {ability} parameters ({'.'.join(map(str, error['loc']))}): {error['msg']}"
    if isinstance(params.get("page_slugs"), list):
        if not all(isinstance(s, str) and 0 < len(s) <= 120 and s.replace('-', '').isalnum() for s in params["page_slugs"]):
            return "Invalid menu page slug"
    return None
