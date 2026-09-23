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
    plugins: list[dict[str, Any]] = Field(default_factory=list)
    capabilities: dict[str, Any] = Field(default_factory=dict)

    def plugin_state(self, slug: str) -> dict[str, Any] | None:
        for plugin in self.plugins:
            if str(plugin.get("slug", "")) == slug:
                return plugin
        approved = self.capabilities.get("approved_plugins", {})
        if isinstance(approved, dict) and isinstance(approved.get(slug), dict):
            return approved[slug]
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
    title_template: str
    meta_description_goal: str
    h1: str
    internal_link_targets: list[str] = Field(default_factory=list)
    schema_types: list[str] = Field(default_factory=list)


class SectionContentSpec(BaseModel):
    section_type: str
    heading: str
    body: str = ""
    items: list[str] = Field(default_factory=list)
    cta_label: str | None = None
    cta_url: str | None = None


class PageExperienceSpec(BaseModel):
    page_name: str
    sections: list[str]
    section_specs: list[SectionContentSpec] = Field(default_factory=list)
    content_guidance: list[str]
    responsive_notes: list[str]
    accessibility_notes: list[str]
    seo: SeoSpec


class ExperienceSpec(BaseModel):
    design_direction: str
    colors: list[str]
    typography: list[str]
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
    quality_reports: list[QualityReport] = Field(default_factory=list)
    status: Literal["created", "inspected", "planned", "specified", "built", "needs_approval", "failed", "passed"] = "created"
