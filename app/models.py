from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentRole(str, Enum):
    ORCHESTRATOR = "orchestrator"
    ARCHITECT = "architect_capability"
    DESIGN = "design_content_seo"
    BUILDER = "wordpress_implementation"
    QUALITY = "quality_security"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PolicyOutcome(str, Enum):
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    BLOCK = "block"


Renderer = Literal["elementor", "gutenberg", "auto"]


class TaskItem(BaseModel):
    id: str
    title: str
    agent: AgentRole
    depends_on: list[str] = Field(default_factory=list)
    expected_output: str


class TaskPlan(BaseModel):
    project_summary: str
    tasks: list[TaskItem]


class SiteSnapshot(BaseModel):
    site_info: dict[str, Any] = Field(default_factory=dict)
    pages: list[dict[str, Any]] = Field(default_factory=list)
    plugins: list[dict[str, Any]] = Field(default_factory=list)
    themes: list[dict[str, Any]] = Field(default_factory=list)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    structure: dict[str, Any] = Field(default_factory=dict)

    def plugin_state(self, slug: str) -> dict[str, Any] | None:
        for plugin in self.plugins:
            if str(plugin.get("slug", "")) == slug:
                return plugin
        approved = self.capabilities.get("approved_plugins", {})
        if isinstance(approved, dict) and isinstance(approved.get(slug), dict):
            return approved[slug]
        return None

    def theme_state(self, slug: str) -> dict[str, Any] | None:
        for theme in self.themes:
            if str(theme.get("slug", "")) == slug:
                return theme
        return None


class PageRequirement(BaseModel):
    name: str
    slug: str
    purpose: str
    required_sections: list[str] = Field(default_factory=list)


class ContentTypeSpec(BaseModel):
    name: str
    implementation: Literal["page", "post", "cpt", "woocommerce_product"]
    fields: list[str] = Field(default_factory=list)


class PluginPlanItem(BaseModel):
    capability: str
    plugin_slug: str
    reason: str
    approved_catalogue_required: bool = True


class ApplicationSpec(BaseModel):
    site_type: str
    site_title: str
    tagline: str = ""
    language: str = "uk"
    theme_slug: str = "hello-elementor"
    goals: list[str]
    pages: list[PageRequirement]
    features: list[str]
    content_types: list[ContentTypeSpec] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    plugin_plan: list[PluginPlanItem] = Field(default_factory=list)
    security_requirements: list[str] = Field(default_factory=list)
    performance_requirements: list[str] = Field(default_factory=list)


class SeoSpec(BaseModel):
    slug: str
    title: str
    meta_description: str
    h1: str
    internal_link_targets: list[str] = Field(default_factory=list)
    schema_types: list[str] = Field(default_factory=list)


class SectionContentSpec(BaseModel):
    section_type: str
    eyebrow: str = ""
    heading: str
    body: str = ""
    items: list[str] = Field(default_factory=list)
    cta_label: str | None = None
    cta_url: str | None = None
    style_variant: Literal["default", "soft", "accent", "dark"] = "default"


class PageExperienceSpec(BaseModel):
    page_name: str
    sections: list[str]
    section_specs: list[SectionContentSpec] = Field(default_factory=list)
    content_guidance: list[str]
    responsive_notes: list[str]
    accessibility_notes: list[str]
    seo: SeoSpec


class DesignSystem(BaseModel):
    primary: str = "#1D4ED8"
    accent: str = "#0EA5E9"
    background: str = "#FFFFFF"
    surface: str = "#F8FAFC"
    text: str = "#0F172A"
    muted: str = "#475569"
    heading_font: str = "Manrope"
    body_font: str = "Inter"
    container_width: int = 1180
    section_spacing: int = 88
    radius: int = 18


class ExperienceSpec(BaseModel):
    design_direction: str
    design_system: DesignSystem = Field(default_factory=DesignSystem)
    component_rules: list[str]
    pages: list[PageExperienceSpec]


class BuildAction(BaseModel):
    ability: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    rationale: str


class BuildPlan(BaseModel):
    actions: list[BuildAction]


class PolicyDecision(BaseModel):
    ability: str
    risk: RiskLevel
    outcome: PolicyOutcome
    reason: str


class ActionExecution(BaseModel):
    action: BuildAction
    policy: PolicyDecision
    executed: bool
    result: Any | None = None
    error: str | None = None
    attempt: int = 1


class QualityIssue(BaseModel):
    id: str
    category: Literal["functional", "visual", "seo", "accessibility", "performance", "security"]
    severity: Literal["low", "medium", "high", "critical"]
    description: str
    responsible_agent: AgentRole
    suggested_fix: str


class QualityReport(BaseModel):
    passed: bool
    summary: str
    checks_performed: list[str]
    issues: list[QualityIssue] = Field(default_factory=list)


class AgentUsage(BaseModel):
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    def add(self, other: "AgentUsage") -> None:
        self.requests += other.requests
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.total_tokens += other.total_tokens


class ProjectRun(BaseModel):
    run_id: str
    user_request: str
    renderer: Renderer = "elementor"
    task_plan: TaskPlan | None = None
    site_snapshot: SiteSnapshot | None = None
    application_spec: ApplicationSpec | None = None
    experience_spec: ExperienceSpec | None = None
    build_plan: BuildPlan | None = None
    executions: list[ActionExecution] = Field(default_factory=list)
    verification_snapshot: SiteSnapshot | None = None
    quality_reports: list[QualityReport] = Field(default_factory=list)
    usage: AgentUsage = Field(default_factory=AgentUsage)
    repair_attempts: int = 0
    status: Literal["created", "inspected", "planned", "specified", "built", "needs_approval", "repairing", "failed", "passed"] = "created"
