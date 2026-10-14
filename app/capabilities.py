from __future__ import annotations

from collections.abc import Iterable

from .models import (
    ArchitectureBundle,
    CapabilityRequirement,
    CapabilityResolution,
    PluginPlanItem,
    Renderer,
    SiteSnapshot,
)


# The LLM asks for business capabilities. Only deterministic code maps those
# capabilities to concrete WordPress dependencies. This prevents hallucinated
# plugin slugs and makes the selection method explainable in the thesis.
CAPABILITY_PLUGIN_MAP: dict[str, str] = {
    "page_builder_elementor": "elementor",
    "forms": "contact-form-7",
    "ecommerce": "woocommerce",
    "structured_content": "advanced-custom-fields",
}

# SEO intentionally has a native bridge fallback: title/meta are written even
# without a third-party SEO plugin. Existing recognized SEO plugins are reused.
CORE_CAPABILITIES = {
    "pages",
    "navigation",
    "site_identity",
    "seo",
    "basic_seo",
    "blog",
    "media",
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
    return value if isinstance(value, dict) else {}


def _dedupe_requirements(requirements: Iterable[CapabilityRequirement]) -> list[CapabilityRequirement]:
    result: list[CapabilityRequirement] = []
    seen: set[str] = set()
    for item in requirements:
        key = item.capability.strip().lower().replace("-", "_")
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
    if renderer in {"elementor", "auto"} and not any(
        r.capability == "page_builder_elementor" for r in requirements
    ):
        requirements.insert(0, CapabilityRequirement(
            capability="page_builder_elementor",
            reason="Selected Elementor renderer requires Elementor Free",
            priority="required",
        ))

    requirements = _dedupe_requirements(requirements)
    active = _active_plugin_slugs(snapshot)
    installed = _installed_plugin_slugs(snapshot)
    recognized = _recognized(snapshot)
    resolutions: list[CapabilityResolution] = []

    for req in requirements:
        capability = req.capability
        # Bridge/Core can satisfy these directly without adding dependency weight.
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
            # SEO plugin is optional in v0.7 because native metadata fallback exists.
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
                reason=f"No approved deterministic implementation mapping exists for '{capability}'",
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
