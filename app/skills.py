from __future__ import annotations

from .models import AgentRole

# The first version keeps skills as explicit knowledge modules/references.
# We deliberately do not auto-download arbitrary GitHub skills at runtime.
SKILLS: dict[AgentRole, list[dict[str, str]]] = {
    AgentRole.ORCHESTRATOR: [
        {"name": "task-decomposition", "type": "project", "purpose": "Break a website request into bounded tasks."},
        {"name": "task-graph-orchestration", "type": "project", "purpose": "Create dependencies and execution order."},
        {"name": "agent-routing", "type": "project", "purpose": "Route work and repair issues to the correct specialist."},
        {"name": "workflow-state-management", "type": "project", "purpose": "Track project state, retries and completion."},
    ],
    AgentRole.ARCHITECT: [
        {"name": "wordpress-router", "type": "official-wordpress", "purpose": "Choose the right WordPress workflow/technology."},
        {"name": "wp-project-triage", "type": "official-wordpress", "purpose": "Inspect project type, tooling and versions."},
        {"name": "acf-free-data-model", "type": "project", "purpose": "Model CPTs, taxonomies and free ACF fields."},
        {"name": "capability-resolver", "type": "project", "purpose": "Map requirements to Core, existing plugin, approved plugin or custom ability."},
        {"name": "plugin-selection", "type": "project", "purpose": "Choose only approved, compatible free plugins."},
    ],
    AgentRole.DESIGN: [
        {"name": "wp-block-themes", "type": "official-wordpress", "purpose": "Design with theme.json, templates, patterns and global styles."},
        {"name": "frontend-design", "type": "reviewed-community-or-project", "purpose": "Create hierarchy, spacing, layout and responsive rules."},
        {"name": "web-accessibility", "type": "reviewed-community-or-project", "purpose": "Design for contrast, headings, labels and keyboard use."},
        {"name": "wordpress-seo-quality", "type": "project", "purpose": "Plan titles, metadata, headings, links, schema and crawlability."},
        {"name": "content-writing", "type": "project", "purpose": "Write page content from business context and page goals."},
    ],
    AgentRole.BUILDER: [
        {"name": "wp-block-development", "type": "official-wordpress", "purpose": "Build Gutenberg blocks correctly."},
        {"name": "wp-block-themes", "type": "official-wordpress", "purpose": "Implement block theme structures and styles."},
        {"name": "wp-plugin-development", "type": "official-wordpress", "purpose": "Follow WordPress plugin patterns and security practices."},
        {"name": "wp-rest-api", "type": "official-wordpress", "purpose": "Use WordPress REST interfaces correctly."},
        {"name": "wp-abilities-api", "type": "official-wordpress", "purpose": "Use structured abilities with schemas and permissions."},
        {"name": "acf-free-execution", "type": "project", "purpose": "Implement the approved ACF Free data model."},
        {"name": "woocommerce-store-builder", "type": "project", "purpose": "Implement basic WooCommerce store flows."},
    ],
    AgentRole.QUALITY: [
        {"name": "playwright-cli", "type": "official-microsoft", "purpose": "Browser-based functional and visual verification."},
        {"name": "wp-abilities-audit", "type": "official-wordpress", "purpose": "Audit exposed WordPress abilities."},
        {"name": "wp-abilities-verify", "type": "official-wordpress", "purpose": "Verify abilities behave as declared."},
        {"name": "wp-performance", "type": "official-wordpress", "purpose": "Review WordPress performance patterns."},
        {"name": "site-quality-audit", "type": "project", "purpose": "Combine SEO, accessibility, performance and security gates."},
    ],
}

OFFICIAL_SOURCES = {
    "wordpress": "https://github.com/WordPress/agent-skills",
    "wordpress_mcp": "https://github.com/WordPress/mcp-adapter",
    "playwright": "https://github.com/microsoft/playwright-cli",
    "woocommerce": "https://github.com/woocommerce/agent-skills",
}


def render_skill_context(role: AgentRole) -> str:
    lines = ["Available skills/knowledge modules:"]
    for skill in SKILLS[role]:
        lines.append(f"- {skill['name']}: {skill['purpose']}")
    return "\n".join(lines)
