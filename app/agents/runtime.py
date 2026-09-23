from __future__ import annotations

import json
from abc import ABC, abstractmethod

from ..models import (
    AgentRole,
    ApplicationSpec,
    BuildAction,
    BuildPlan,
    ExperienceSpec,
    PageExperienceSpec,
    PageRequirement,
    QualityReport,
    SeoSpec,
    TaskItem,
    TaskPlan,
)
from .prompts import architect_prompt, builder_prompt, design_prompt, orchestrator_prompt, quality_prompt


class AgentRuntime(ABC):
    @abstractmethod
    async def plan(self, user_request: str) -> TaskPlan: ...

    @abstractmethod
    async def architect(self, user_request: str, task_plan: TaskPlan) -> ApplicationSpec: ...

    @abstractmethod
    async def design(self, app_spec: ApplicationSpec) -> ExperienceSpec: ...

    @abstractmethod
    async def build(self, app_spec: ApplicationSpec, experience_spec: ExperienceSpec) -> BuildPlan: ...

    @abstractmethod
    async def quality(self, app_spec: ApplicationSpec, experience_spec: ExperienceSpec, executions_json: str) -> QualityReport: ...


class MockAgentRuntime(AgentRuntime):
    async def plan(self, user_request: str) -> TaskPlan:
        return TaskPlan(
            project_summary=user_request,
            tasks=[
                TaskItem(id="T1", title="Формалізувати вимоги та capability model", agent=AgentRole.ARCHITECT, expected_output="ApplicationSpec"),
                TaskItem(id="T2", title="Спроєктувати UX/UI, контент та SEO", agent=AgentRole.DESIGN, depends_on=["T1"], expected_output="ExperienceSpec"),
                TaskItem(id="T3", title="Сформувати та виконати план побудови WordPress", agent=AgentRole.BUILDER, depends_on=["T1", "T2"], expected_output="BuildPlan + executions"),
                TaskItem(id="T4", title="Перевірити якість і безпеку", agent=AgentRole.QUALITY, depends_on=["T3"], expected_output="QualityReport"),
            ],
        )

    async def architect(self, user_request: str, task_plan: TaskPlan) -> ApplicationSpec:
        lower = user_request.lower()
        is_shop = any(word in lower for word in ("магазин", "shop", "store", "woocommerce"))
        pages = [
            PageRequirement(name="Головна", slug="home", purpose="Основна презентація сайту", required_sections=["hero", "benefits", "cta"]),
            PageRequirement(name="Про нас", slug="about", purpose="Довіра та інформація про проєкт", required_sections=["story", "values"]),
            PageRequirement(name="Контакти", slug="contact", purpose="Контакт і конверсія", required_sections=["contacts", "form"]),
        ]
        if any(word in lower for word in ("послуг", "service", "services")):
            pages.insert(1, PageRequirement(name="Послуги", slug="services", purpose="Опис і навігація по послугах", required_sections=["services-grid", "faq", "cta"]))
        if any(word in lower for word in ("лікар", "doctor", "team", "команд")):
            pages.insert(2, PageRequirement(name="Лікарі", slug="doctors", purpose="Профілі спеціалістів і довіра", required_sections=["team-grid", "credentials", "cta"]))
        if any(word in lower for word in ("запис", "booking", "appointment")):
            pages.append(PageRequirement(name="Запис", slug="booking", purpose="Запис користувача", required_sections=["booking-form", "contact-options"]))
        features = ["responsive design", "SEO baseline", "accessible navigation"]
        caps = ["pages", "navigation", "seo"]
        plugins = []
        if is_shop:
            pages.extend([
                PageRequirement(name="Магазин", slug="shop", purpose="Каталог товарів", required_sections=["product-grid"]),
                PageRequirement(name="Кошик", slug="cart", purpose="Кошик", required_sections=["cart"]),
                PageRequirement(name="Оформлення", slug="checkout", purpose="Checkout", required_sections=["checkout"]),
            ])
            features.append("basic ecommerce")
            caps.append("ecommerce")
            from ..models import PluginPlanItem
            plugins.append(PluginPlanItem(capability="ecommerce", plugin_slug="woocommerce", reason="Базова e-commerce функціональність"))
        return ApplicationSpec(
            site_type="basic_ecommerce" if is_shop else "business_website",
            goals=["Створити редагований WordPress-сайт", "Пройти незалежну перевірку якості"],
            pages=pages,
            features=features,
            required_capabilities=caps,
            plugin_plan=plugins,
            security_requirements=["least privilege", "no raw SQL", "no direct shell", "policy gate for writes"],
            performance_requirements=["optimized images", "avoid unnecessary plugins", "Core Web Vitals-aware design"],
        )

    async def design(self, app_spec: ApplicationSpec) -> ExperienceSpec:
        pages = []
        for page in app_spec.pages:
            pages.append(PageExperienceSpec(
                page_name=page.name,
                sections=page.required_sections or ["content"],
                content_guidance=[f"Пояснити мету сторінки: {page.purpose}", "Додати чіткий CTA там, де доречно"],
                responsive_notes=["Mobile-first stacking", "No horizontal overflow"],
                accessibility_notes=["Один логічний H1", "Контрастний текст", "Змістовні link/button labels"],
                seo=SeoSpec(
                    slug=f"/{page.slug}/" if page.slug != "home" else "/",
                    title_template=f"{page.name} | Назва бренду",
                    meta_description_goal=f"Коротко пояснити зміст сторінки «{page.name}» і користь для відвідувача.",
                    h1=page.name,
                    internal_link_targets=["/"] if page.slug != "home" else [f"/{p.slug}/" for p in app_spec.pages if p.slug != "home"],
                    schema_types=["WebPage", "BreadcrumbList"],
                ),
            ))
        return ExperienceSpec(
            design_direction="Чистий сучасний Gutenberg-first дизайн з повторно використовуваними компонентами",
            colors=["brand-primary", "brand-secondary", "neutral-background", "high-contrast-text"],
            typography=["Readable sans-serif body", "Clear heading scale"],
            component_rules=["Consistent buttons", "Reusable section spacing", "Semantic headings"],
            pages=pages,
        )

    async def build(self, app_spec: ApplicationSpec, experience_spec: ExperienceSpec) -> BuildPlan:
        actions: list[BuildAction] = [
            BuildAction(ability="thesis-ai-bridge/get-site-info", rationale="Перевірити цільове WordPress-середовище"),
            BuildAction(ability="thesis-ai-bridge/list-pages", rationale="Отримати фактичну структуру сторінок"),
            BuildAction(ability="thesis-ai-bridge/list-plugins", rationale="Перевірити встановлені та активні plugins"),
        ]
        for plugin in app_spec.plugin_plan:
            actions.extend([
                BuildAction(ability="thesis-ai-bridge/install-approved-plugin", parameters={"plugin_slug": plugin.plugin_slug}, rationale=plugin.reason),
                BuildAction(ability="thesis-ai-bridge/activate-approved-plugin", parameters={"plugin_slug": plugin.plugin_slug}, rationale=f"Активувати {plugin.plugin_slug}"),
            ])
        exp_by_name = {p.page_name: p for p in experience_spec.pages}
        for page in app_spec.pages:
            exp = exp_by_name[page.name]
            content_parts = []
            for section in exp.sections:
                label = section.replace("-", " ").replace("_", " ").strip().title()
                content_parts.append(
                    '<!-- wp:group {"tagName":"section","layout":{"type":"constrained"}} -->'
                    '<section class="wp-block-group">'
                    f'<!-- wp:heading --><h2 class="wp-block-heading">{label}</h2><!-- /wp:heading -->'
                    f'<!-- wp:paragraph --><p>Контент секції «{label}» буде сформований відповідно до вимог сторінки.</p><!-- /wp:paragraph -->'
                    '</section><!-- /wp:group -->'
                )
            content = "\n\n".join(content_parts)
            actions.append(BuildAction(
                ability="thesis-ai-bridge/ensure-draft-page",
                parameters={"title": page.name, "slug": page.slug, "content": content},
                rationale=f"Створити редаговану Gutenberg draft-сторінку {page.name}",
            ))
        return BuildPlan(actions=actions)

    async def quality(self, app_spec: ApplicationSpec, experience_spec: ExperienceSpec, executions_json: str) -> QualityReport:
        executions = json.loads(executions_json)
        failures = [x for x in executions if not x.get("executed") and x.get("policy", {}).get("outcome") != "require_approval"]
        pending = [x for x in executions if x.get("policy", {}).get("outcome") == "require_approval"]
        checks = [
            "Структурна повнота сторінок",
            "Policy decisions для кожної build action",
            "Відсутність raw SQL/shell/filesystem/auth operations",
            "Наявність SEO та accessibility вимог у ExperienceSpec",
        ]
        if failures:
            from ..models import QualityIssue
            return QualityReport(
                passed=False,
                summary="Структурна перевірка виявила невиконані build actions.",
                checks_performed=checks,
                issues=[QualityIssue(
                    id="Q1", category="functional", severity="high",
                    description=f"{len(failures)} build actions failed or were blocked.",
                    responsible_agent=AgentRole.BUILDER,
                    suggested_fix="Переглянути BuildPlan/адаптери abilities і повторити виконання.",
                )],
            )
        if pending:
            from ..models import QualityIssue
            return QualityReport(
                passed=False,
                summary="Є операції, що очікують human approval.",
                checks_performed=checks,
                issues=[QualityIssue(
                    id="Q1", category="security", severity="high",
                    description="High-risk action requires approval before execution.",
                    responsible_agent=AgentRole.ORCHESTRATOR,
                    suggested_fix="Отримати explicit approval або замінити дію безпечнішою ability.",
                )],
            )
        return QualityReport(
            passed=True,
            summary="v0.3 structural/API QA passed. Browser/visual penetration-style tests are not yet wired and are NOT claimed as passed.",
            checks_performed=checks,
            issues=[],
        )


class OpenAIAgentRuntime(AgentRuntime):
    def __init__(self, model: str) -> None:
        try:
            from agents import Agent
        except ImportError as exc:
            raise RuntimeError("Install dependencies with: pip install -e .") from exc

        self.model = model
        self._Agent = Agent
        self.orchestrator = Agent(name="Orchestrator", instructions=orchestrator_prompt(), model=model, output_type=TaskPlan)
        self.architect_agent = Agent(name="Architect & Capability", instructions=architect_prompt(), model=model, output_type=ApplicationSpec)
        self.design_agent = Agent(name="Design, Content & SEO", instructions=design_prompt(), model=model, output_type=ExperienceSpec)
        self.builder_agent = Agent(name="WordPress Implementation", instructions=builder_prompt(), model=model, output_type=BuildPlan)
        self.quality_agent = Agent(name="Quality & Security", instructions=quality_prompt(), model=model, output_type=QualityReport)

    async def _run(self, agent, payload: str):
        from agents import Runner
        result = await Runner.run(agent, payload, max_turns=8)
        return result.final_output

    async def plan(self, user_request: str) -> TaskPlan:
        return await self._run(self.orchestrator, user_request)

    async def architect(self, user_request: str, task_plan: TaskPlan) -> ApplicationSpec:
        return await self._run(self.architect_agent, json.dumps({"user_request": user_request, "task_plan": task_plan.model_dump()}, ensure_ascii=False))

    async def design(self, app_spec: ApplicationSpec) -> ExperienceSpec:
        return await self._run(self.design_agent, app_spec.model_dump_json())

    async def build(self, app_spec: ApplicationSpec, experience_spec: ExperienceSpec) -> BuildPlan:
        return await self._run(self.builder_agent, json.dumps({"application_spec": app_spec.model_dump(), "experience_spec": experience_spec.model_dump()}, ensure_ascii=False))

    async def quality(self, app_spec: ApplicationSpec, experience_spec: ExperienceSpec, executions_json: str) -> QualityReport:
        return await self._run(self.quality_agent, json.dumps({
            "application_spec": app_spec.model_dump(),
            "experience_spec": experience_spec.model_dump(),
            "executions": json.loads(executions_json),
            "evidence_limit": "No Playwright/browser evidence is supplied in v0.3; do not claim those checks passed.",
        }, ensure_ascii=False))


def make_agent_runtime(mode: str, model: str) -> AgentRuntime:
    if mode == "openai":
        return OpenAIAgentRuntime(model)
    return MockAgentRuntime()
