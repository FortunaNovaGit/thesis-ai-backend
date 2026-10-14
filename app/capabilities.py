from __future__ import annotations

import re
from collections.abc import Iterable

from .models import (
    ArchitectureBundle,
    CapabilityRequirement,
    CapabilityResolution,
    PluginPlanItem,
    Renderer,
    SiteSnapshot,
)


# The LLM describes *semantic* capabilities. Deterministic code owns the mapping
# to WordPress Core/Bridge or to an approved dependency. This boundary prevents
# hallucinated plugin slugs from reaching the execution layer.
CAPABILITY_PLUGIN_MAP: dict[str, str] = {
    "page_builder_elementor": "elementor",
    "forms": "contact-form-7",
    "ecommerce": "woocommerce",
    "structured_content": "advanced-custom-fields",
}

# Capabilities implemented directly by WordPress Core and/or Thesis AI Bridge.
CORE_CAPABILITIES = {
    "pages",
    "navigation",
    "site_identity",
    "seo",
    "blog",
    "media",
}

# The Architect is deliberately allowed to speak in natural semantic names, but
# the resolver must be forgiving about common aliases. The previous v0.7.0 bug
# happened because the model returned `core_pages`, which is semantically valid
# but was treated as an unknown capability and aborted the whole build.
CAPABILITY_ALIASES: dict[str, str] = {
    # Core page/site primitives.
    "page": "pages",
    "core_page": "pages",
    "core_pages": "pages",
    "wordpress_page": "pages",
    "wordpress_pages": "pages",
    "page_creation": "pages",
    "core_navigation": "navigation",
    "menus": "navigation",
    "menu": "navigation",
    "navigation_menu": "navigation",
    "navigation_menus": "navigation",
    "site_settings": "site_identity",
    "core_site_identity": "site_identity",
    "site_branding": "site_identity",
    "basic_seo": "seo",
    "seo_metadata": "seo",
    "on_page_seo": "seo",
    "meta_seo": "seo",
    "posts": "blog",
    "blog_posts": "blog",
    "images": "media",
    "media_library": "media",

    # Approved plugin-backed capabilities.
    "form": "forms",
    "contact_form": "forms",
    "contact_forms": "forms",
    "booking_form": "forms",
    "elementor": "page_builder_elementor",
    "elementor_free": "page_builder_elementor",
    "page_builder": "page_builder_elementor",
    "woocommerce": "ecommerce",
    "shop": "ecommerce",
    "store": "ecommerce",
    "online_store": "ecommerce",
    "acf": "structured_content",
    "custom_fields": "structured_content",
    "custom_field": "structured_content",
    "data_model": "structured_content",
    "seo_plugin_support": "seo_plugin",
}

APPROVED_PLUGIN_SLUGS = {
    "elementor",
    "woocommerce",
    "advanced-custom-fields",
    "contact-form-7",
    "wordpress-seo",
    "seo-by-rank-math",
}

SEO_PLUGINS = ("wordpress-seo", "seo-by-rank-math")
SUPPORTED_CAPABILITIES = CORE_CAPABILITIES | set(CAPABILITY_PLUGIN_MAP) | {"seo_plugin"}


def canonicalize_capability(value: str) -> str:
    """Normalize an agent-produced semantic capability into our fixed vocabulary."""
    key = re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower()).strip("_")
    if not key:
        return ""
    key = CAPABILITY_ALIASES.get(key, key)
    # Future-proof common `core_*` wording without opening arbitrary mappings.
    if key.startswith("core_"):
        candidate = key[5:]
        if candidate in CORE_CAPABILITIES:
            key = candidate
    return CAPABILITY_ALIASES.get(key, key)


def _active_plugin_slugs(snapshot: SiteSnapshot) -> set[str]:
    return {
        str(p.get("slug", ""))
        for p in snapshot.plugins
        if bool(p.get("active")) and p.get("slug")
    }


def _installed_plugin_slugs(snapshot: SiteSnapshot) -> set[str]:
    return {str(p.get("slug", "")) for p in snapshot.plugins if p.get("slug")}


def _recognized(snapshot: SiteSnapshot) -> dict[str, object]:
    value = snapshot.capabilities.get("recognized_capabilities", {})
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, object] = {}
    for key, state in value.items():
        canonical = canonicalize_capability(str(key))
        if canonical:
            normalized[canonical] = state
    return normalized


def _dedupe_requirements(requirements: Iterable[CapabilityRequirement]) -> list[CapabilityRequirement]:
    result: list[CapabilityRequirement] = []
    seen: set[str] = set()
    for item in requirements:
        key = canonicalize_capability(item.capability)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item.model_copy(update={"capability": key}))
    return result


def resolve_capabilities(
    architecture: ArchitectureBundle,
    snapshot: SiteSnapshot,
    renderer: Renderer,
) -> list[CapabilityResolution]:
    requirements = list(architecture.capabilities)

    # Baseline website capabilities are deterministic. We do not require the LLM
    # to remember that creating pages/navigation/site identity are Core features.
    baseline = [
        CapabilityRequirement(capability="pages", reason="The architecture contains WordPress pages", priority="required"),
        CapabilityRequirement(capability="site_identity", reason="The generated site needs a title/tagline", priority="required"),
        CapabilityRequirement(capability="seo", reason="Every generated page receives basic SEO metadata", priority="required"),
    ]
    if len(architecture.pages) > 1:
        baseline.append(CapabilityRequirement(
            capability="navigation",
            reason="Multiple generated pages require navigation",
            priority="required",
        ))
    if renderer in {"elementor", "auto"}:
        baseline.append(CapabilityRequirement(
            capability="page_builder_elementor",
            reason="Selected Elementor renderer requires Elementor Free",
            priority="required",
        ))

    requirements = _dedupe_requirements([*baseline, *requirements])
    active = _active_plugin_slugs(snapshot)
    installed = _installed_plugin_slugs(snapshot)
    recognized = _recognized(snapshot)
    resolutions: list[CapabilityResolution] = []

    for req in requirements:
        capability = req.capability

        if capability in CORE_CAPABILITIES:
            resolutions.append(CapabilityResolution(
                capability=capability,
                source="core",
                action="reuse",
                reason=f"WordPress Core/Bridge satisfies capability: {req.reason}",
            ))
            continue

        if capability == "seo_plugin":
            existing = next((slug for slug in SEO_PLUGINS if slug in active), None)
            if existing:
                resolutions.append(CapabilityResolution(
                    capability=capability,
                    source="existing_plugin",
                    action="reuse",
                    plugin_slug=existing,
                    reason="Existing active SEO plugin already satisfies the capability",
                ))
                continue
            installed_existing = next((slug for slug in SEO_PLUGINS if slug in installed), None)
            if installed_existing:
                resolutions.append(CapabilityResolution(
                    capability=capability,
                    source="existing_plugin",
                    action="activate",
                    plugin_slug=installed_existing,
                    reason="Existing installed SEO plugin can be reused",
                ))
                continue
            resolutions.append(CapabilityResolution(
                capability=capability,
                source="core",
                action="reuse",
                reason="Native Bridge SEO metadata fallback avoids an unnecessary plugin",
            ))
            continue

        recognized_value = recognized.get(capability)
        if recognized_value:
            resolutions.append(CapabilityResolution(
                capability=capability,
                source="existing_plugin",
                action="reuse",
                reason="Site preflight reports this capability as already available",
            ))
            continue

        slug = CAPABILITY_PLUGIN_MAP.get(capability)
        if not slug:
            resolutions.append(CapabilityResolution(
                capability=capability,
                source="unavailable",
                action="none",
                reason=(
                    f"No approved deterministic implementation mapping exists for '{capability}'. "
                    f"Supported semantic capabilities: {', '.join(sorted(SUPPORTED_CAPABILITIES))}"
                ),
            ))
            continue

        if slug in active:
            source = "existing_plugin"
            action = "reuse"
            reason = f"Approved plugin '{slug}' is already active"
        elif slug in installed:
            source = "existing_plugin"
            action = "activate"
            reason = f"Approved plugin '{slug}' is installed and can be activated"
        else:
            source = "approved_plugin"
            action = "install"
            reason = f"Approved plugin '{slug}' is required for capability '{capability}'"
        resolutions.append(CapabilityResolution(
            capability=capability,
            source=source,
            action=action,
            plugin_slug=slug,
            reason=reason,
        ))
    return resolutions


def plugin_plan_from_resolutions(resolutions: list[CapabilityResolution]) -> list[PluginPlanItem]:
    result: list[PluginPlanItem] = []
    seen: set[str] = set()
    for item in resolutions:
        slug = item.plugin_slug
        if not slug or slug in seen or slug not in APPROVED_PLUGIN_SLUGS:
            continue
        if item.action not in {"install", "activate"}:
            continue
        seen.add(slug)
        result.append(PluginPlanItem(
            capability=item.capability,
            plugin_slug=slug,
            reason=item.reason,
            approved_catalogue_required=True,
        ))
    return result
