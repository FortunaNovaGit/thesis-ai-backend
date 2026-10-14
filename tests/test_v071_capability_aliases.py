from app.agents.runtime import normalize_architecture
from app.capabilities import canonicalize_capability, resolve_capabilities
from app.models import (
    ArchitectureBundle,
    CapabilityRequirement,
    ContentMatrixRow,
    PageIntent,
    ProjectBrief,
    SiteSnapshot,
)


def _snapshot():
    return SiteSnapshot(
        site_info={"name": "Test"},
        pages=[],
        plugins=[{"slug": "elementor", "active": True}],
        themes=[{"slug": "hello-elementor", "active": True}],
        capabilities={"recognized_capabilities": {"page_builder_elementor": True}},
        structure={"homepage_slug": "", "active_theme_slug": "hello-elementor"},
    )


def _brief():
    return ProjectBrief(
        site_type="business_website",
        language="uk",
        primary_goal="Leads",
        renderer="elementor",
        requested_pages=["Головна", "Послуги", "Контакти"],
        requirements=["seo", "navigation"],
    )


def test_common_core_aliases_are_canonicalized():
    assert canonicalize_capability("core_pages") == "pages"
    assert canonicalize_capability("wordpress-pages") == "pages"
    assert canonicalize_capability("core_navigation") == "navigation"
    assert canonicalize_capability("contact_forms") == "forms"
    assert canonicalize_capability("elementor") == "page_builder_elementor"


def test_architecture_normalization_turns_core_pages_into_core_capability():
    arch = ArchitectureBundle(
        site_title="Test",
        pages=[
            PageIntent(name="Головна", slug="home", purpose="Convert"),
            PageIntent(name="Послуги", slug="services", purpose="Explain"),
            PageIntent(name="Контакти", slug="contact", purpose="Contact"),
        ],
        capabilities=[CapabilityRequirement(capability="core_pages", reason="Need pages")],
        content_matrix=[
            ContentMatrixRow(page_slug="home", page_goal="Convert"),
            ContentMatrixRow(page_slug="services", page_goal="Explain"),
            ContentMatrixRow(page_slug="contact", page_goal="Contact"),
        ],
    )
    normalized = normalize_architecture(_brief(), arch)
    caps = {x.capability for x in normalized.capabilities}
    assert "core_pages" not in caps
    assert "pages" in caps
    assert "navigation" in caps
    assert "site_identity" in caps
    assert "seo" in caps
    assert "page_builder_elementor" in caps

    resolutions = resolve_capabilities(normalized, _snapshot(), "elementor")
    pages = next(x for x in resolutions if x.capability == "pages")
    assert pages.source == "core"
    assert pages.action == "reuse"
    assert not [x for x in resolutions if x.source == "unavailable"]
