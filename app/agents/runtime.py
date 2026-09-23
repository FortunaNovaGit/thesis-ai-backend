from __future__ import annotations

import json
import secrets
from abc import ABC, abstractmethod

from ..models import (
    AgentRole,
    ApplicationSpec,
    BuildAction,
    BuildPlan,
    ExperienceSpec,
    PageExperienceSpec,
    PageRequirement,
    PluginPlanItem,
    QualityIssue,
    QualityReport,
    Renderer,
    SectionContentSpec,
    SeoSpec,
    SiteSnapshot,
    TaskItem,
    TaskPlan,
)
from .prompts import architect_prompt, builder_prompt, design_prompt, orchestrator_prompt, quality_prompt


class AgentRuntime(ABC):
    @abstractmethod
    async def plan(self, user_request: str) -> TaskPlan: ...

    @abstractmethod
    async def architect(self, user_request: str, task_plan: TaskPlan, site_snapshot: SiteSnapshot, renderer: Renderer) -> ApplicationSpec: ...

    @abstractmethod
    async def design(self, app_spec: ApplicationSpec, renderer: Renderer) -> ExperienceSpec: ...

    @abstractmethod
    async def build(self, app_spec: ApplicationSpec, experience_spec: ExperienceSpec, site_snapshot: SiteSnapshot, renderer: Renderer) -> BuildPlan: ...

    @abstractmethod
    async def quality(self, app_spec: ApplicationSpec, experience_spec: ExperienceSpec, executions_json: str, renderer: Renderer) -> QualityReport: ...


def _plugin_active(snapshot: SiteSnapshot, slug: str) -> bool:
    state = snapshot.plugin_state(slug)
    return bool(state and state.get("active"))


def _section_copy(page_name: str, purpose: str, section: str) -> SectionContentSpec:
    key = section.lower()
    page = page_name.lower()
    if "hero" in key:
        return SectionContentSpec(section_type="hero", heading=page_name, body=purpose, cta_label="Дізнатися більше", cta_url="#main-content")
    if "service" in key or "послуг" in key:
        return SectionContentSpec(section_type="services", heading="Наші послуги", body="Основні напрямки, з якими ми допомагаємо клієнтам.", items=["Професійна консультація", "Індивідуальний підхід", "Сучасні рішення"])
    if "team" in key or "doctor" in key or "лікар" in key:
        return SectionContentSpec(section_type="team", heading="Наша команда", body="Фахівці, яким можна довірити важливі рішення.", items=["Досвідчені спеціалісти", "Зрозуміла комунікація", "Увага до деталей"])
    if "benefit" in key or "перева" in key or "value" in key:
        return SectionContentSpec(section_type="benefits", heading="Чому обирають нас", body="Ми поєднуємо якість, прозорість та комфорт.", items=["Якість", "Надійність", "Зручність"])
    if "faq" in key:
        return SectionContentSpec(section_type="faq", heading="Поширені запитання", body="Короткі відповіді на питання, які найчастіше виникають перед зверненням.", items=["Як записатися?", "Як проходить перша консультація?", "Які способи оплати доступні?"])
    if "contact" in key or "контакт" in key:
        return SectionContentSpec(section_type="contact", heading="Зв’яжіться з нами", body="Оберіть зручний спосіб зв’язку — ми відповімо та допоможемо з наступним кроком.", cta_label="Написати нам", cta_url="/contact/")
    if "booking" in key or "запис" in key or "form" in key:
        return SectionContentSpec(section_type="booking", heading="Записатися", body="Залиште заявку, і ми зв’яжемося з вами для уточнення деталей.", cta_label="Перейти до запису", cta_url="/booking/")
    if "cta" in key:
        return SectionContentSpec(section_type="cta", heading="Готові зробити наступний крок?", body="Зв’яжіться з нами — допоможемо підібрати оптимальне рішення.", cta_label="Зв’язатися", cta_url="/contact/")
    if "story" in key or "about" in key or "про" in key:
        return SectionContentSpec(section_type="content", heading="Про нас", body=purpose)
    if "product" in key or "catalog" in key:
        return SectionContentSpec(section_type="products", heading="Каталог", body="Добірка товарів і категорій магазину.", items=["Популярні товари", "Новинки", "Рекомендовані товари"])
    return SectionContentSpec(section_type="content", heading=section.replace("-", " ").replace("_", " ").title(), body=purpose)


def _eid() -> str:
    return secrets.token_hex(4)


def _widget(widget_type: str, settings: dict) -> dict:
    return {"id": _eid(), "elType": "widget", "widgetType": widget_type, "isInner": False, "settings": settings, "elements": []}


def _container(elements: list[dict], settings: dict | None = None) -> dict:
    base = {
        "content_width": "boxed",
        "flex_direction": "column",
        "gap": {"unit": "px", "size": 18, "sizes": []},
        "padding": {"unit": "px", "top": "56", "right": "24", "bottom": "56", "left": "24", "isLinked": False},
    }
    if settings:
        base.update(settings)
    return {"id": _eid(), "elType": "container", "isInner": False, "settings": base, "elements": elements}


def _elementor_page_elements(page: PageExperienceSpec) -> list[dict]:
    sections: list[dict] = []
    specs = page.section_specs or [SectionContentSpec(section_type=s, heading=s.title()) for s in page.sections]
    for index, section in enumerate(specs):
        widgets: list[dict] = []
        level = "h1" if index == 0 else "h2"
        widgets.append(_widget("heading", {"title": section.heading, "header_size": level}))
        if section.body:
            widgets.append(_widget("text-editor", {"editor": f"<p>{section.body}</p>"}))
        if section.items:
            inner_cards: list[dict] = []
            for item in section.items:
                inner_cards.append(_container([
                    _widget("heading", {"title": item, "header_size": "h3"}),
                    _widget("text-editor", {"editor": "<p>Детальніше про цю перевагу або напрямок.</p>"}),
                ], {"background_background": "classic", "background_color": "#F6F8FB", "border_radius": {"unit": "px", "top": "12", "right": "12", "bottom": "12", "left": "12", "isLinked": True}, "padding": {"unit": "px", "top": "24", "right": "24", "bottom": "24", "left": "24", "isLinked": True}}))
            widgets.append(_container(inner_cards, {"flex_direction": "row", "flex_wrap": "wrap", "gap": {"unit": "px", "size": 20, "sizes": []}, "padding": {"unit": "px", "top": "12", "right": "0", "bottom": "12", "left": "0", "isLinked": False}}))
        if section.cta_label:
            widgets.append(_widget("button", {"text": section.cta_label, "link": {"url": section.cta_url or "#", "is_external": "", "nofollow": ""}, "size": "md"}))
        section_settings = {}
        if section.section_type == "hero":
            section_settings = {"min_height": {"unit": "vh", "size": 60, "sizes": []}, "justify_content": "center", "background_background": "classic", "background_color": "#F4F7FB"}
        sections.append(_container(widgets, section_settings))
    return sections


def _gutenberg_page_content(page: PageExperienceSpec) -> str:
    parts: list[str] = []
    specs = page.section_specs or [SectionContentSpec(section_type=s, heading=s.title()) for s in page.sections]
    for i, section in enumerate(specs):
        level = 1 if i == 0 else 2
        heading = section.heading
        body = section.body or ""
        parts.append('<!-- wp:group {"tagName":"section","layout":{"type":"constrained"}} --><section class="wp-block-group">')
        parts.append(f'<!-- wp:heading {{"level":{level}}} --><h{level} class="wp-block-heading">{heading}</h{level}><!-- /wp:heading -->')
        if body:
            parts.append(f'<!-- wp:paragraph --><p>{body}</p><!-- /wp:paragraph -->')
        if section.items:
            lis = "".join(f"<li>{item}</li>" for item in section.items)
            parts.append(f'<!-- wp:list --><ul>{lis}</ul><!-- /wp:list -->')
        if section.cta_label:
            parts.append(f'<!-- wp:buttons --><div class="wp-block-buttons"><!-- wp:button --><div class="wp-block-button"><a class="wp-block-button__link wp-element-button" href="{section.cta_url or '#'}">{section.cta_label}</a></div><!-- /wp:button --></div><!-- /wp:buttons -->')
        parts.append('</section><!-- /wp:group -->')
    return "\n".join(parts)


class MockAgentRuntime(AgentRuntime):
    async def plan(self, user_request: str) -> TaskPlan:
        return TaskPlan(
            project_summary=user_request,
            tasks=[
                TaskItem(id="T1", title="Проінспектувати WordPress і plugins", agent=AgentRole.ARCHITECT, expected_output="SiteSnapshot"),
                TaskItem(id="T2", title="Формалізувати вимоги та capability model", agent=AgentRole.ARCHITECT, depends_on=["T1"], expected_output="ApplicationSpec"),
                TaskItem(id="T3", title="Спроєктувати UX/UI, контент та SEO", agent=AgentRole.DESIGN, depends_on=["T2"], expected_output="ExperienceSpec"),
                TaskItem(id="T4", title="Встановити відсутні approved plugins і побудувати WordPress", agent=AgentRole.BUILDER, depends_on=["T2", "T3"], expected_output="BuildPlan + executions"),
                TaskItem(id="T5", title="Перевірити якість і безпеку", agent=AgentRole.QUALITY, depends_on=["T4"], expected_output="QualityReport"),
            ],
        )

    async def architect(self, user_request: str, task_plan: TaskPlan, site_snapshot: SiteSnapshot, renderer: Renderer) -> ApplicationSpec:
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
        plugins: list[PluginPlanItem] = []

        selected_renderer = "elementor" if renderer in {"elementor", "auto"} else "gutenberg"
        if selected_renderer == "elementor":
            caps.append("page_builder_elementor")
            if not _plugin_active(site_snapshot, "elementor"):
                plugins.append(PluginPlanItem(capability="page_builder_elementor", plugin_slug="elementor", reason="Elementor Free потрібен як renderer сторінок"))

        if is_shop:
            pages.extend([
                PageRequirement(name="Магазин", slug="shop", purpose="Каталог товарів", required_sections=["product-grid"]),
                PageRequirement(name="Кошик", slug="cart", purpose="Кошик", required_sections=["cart"]),
                PageRequirement(name="Оформлення", slug="checkout", purpose="Checkout", required_sections=["checkout"]),
            ])
            features.append("basic ecommerce")
            caps.append("ecommerce")
            if not _plugin_active(site_snapshot, "woocommerce"):
                plugins.append(PluginPlanItem(capability="ecommerce", plugin_slug="woocommerce", reason="Базова e-commerce функціональність"))

        if any(word in lower for word in ("форма", "contact form", "запис", "booking")) and not _plugin_active(site_snapshot, "contact-form-7"):
            plugins.append(PluginPlanItem(capability="forms", plugin_slug="contact-form-7", reason="Безкоштовний approved plugin для форм"))

        return ApplicationSpec(
            site_type="basic_ecommerce" if is_shop else "business_website",
            goals=["Створити редагований WordPress-сайт", "Повторно використати наявні capabilities", "Пройти незалежну перевірку якості"],
            pages=pages,
            features=features,
            required_capabilities=caps,
            plugin_plan=plugins,
            security_requirements=["least privilege", "no raw SQL", "no direct shell", "policy gate for writes", "approved plugin allowlist"],
            performance_requirements=["optimized images", "avoid unnecessary plugins", "Core Web Vitals-aware design"],
        )

    async def design(self, app_spec: ApplicationSpec, renderer: Renderer) -> ExperienceSpec:
        pages: list[PageExperienceSpec] = []
        for page in app_spec.pages:
            specs = [_section_copy(page.name, page.purpose, section) for section in (page.required_sections or ["content"])]
            pages.append(PageExperienceSpec(
                page_name=page.name,
                sections=page.required_sections or ["content"],
                section_specs=specs,
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
        builder_name = "Elementor Free" if renderer in {"elementor", "auto"} else "Gutenberg"
        return ExperienceSpec(
            design_direction=f"Чистий сучасний {builder_name} дизайн з повторно використовуваними компонентами",
            colors=["#1D4ED8", "#0EA5E9", "#F8FAFC", "#0F172A"],
            typography=["Readable sans-serif body", "Clear heading scale"],
            component_rules=["Consistent buttons", "Reusable section spacing", "Semantic headings", "Responsive containers"],
            pages=pages,
        )

    async def build(self, app_spec: ApplicationSpec, experience_spec: ExperienceSpec, site_snapshot: SiteSnapshot, renderer: Renderer) -> BuildPlan:
        actions: list[BuildAction] = []
        for plugin in app_spec.plugin_plan:
            actions.append(BuildAction(
                ability="thesis-ai-bridge/ensure-approved-plugin",
                parameters={"plugin_slug": plugin.plugin_slug},
                rationale=plugin.reason,
            ))

        selected_renderer = "elementor" if renderer in {"elementor", "auto"} else "gutenberg"
        exp_by_name = {p.page_name: p for p in experience_spec.pages}
        for page in app_spec.pages:
            exp = exp_by_name[page.name]
            if selected_renderer == "elementor":
                actions.append(BuildAction(
                    ability="thesis-ai-bridge/elementor-ensure-draft-page",
                    parameters={
                        "title": page.name,
                        "slug": page.slug,
                        "elements": _elementor_page_elements(exp),
                        "settings": {"hide_title": "yes"},
                    },
                    rationale=f"Створити редаговану Elementor draft-сторінку {page.name}",
                ))
            else:
                actions.append(BuildAction(
                    ability="thesis-ai-bridge/ensure-draft-page",
                    parameters={"title": page.name, "slug": page.slug, "content": _gutenberg_page_content(exp)},
                    rationale=f"Створити редаговану Gutenberg draft-сторінку {page.name}",
                ))
        return BuildPlan(actions=actions)

    async def quality(self, app_spec: ApplicationSpec, experience_spec: ExperienceSpec, executions_json: str, renderer: Renderer) -> QualityReport:
        executions = json.loads(executions_json)
        failures = [x for x in executions if not x.get("executed") and x.get("policy", {}).get("outcome") != "require_approval"]
        pending = [x for x in executions if x.get("policy", {}).get("outcome") == "require_approval"]
        checks = [
            "Фактичний site/plugin preflight перед planning",
            "Структурна повнота сторінок",
            "Policy decisions для кожної build action",
            "Approved-only plugin installation",
            f"Renderer: {renderer}",
            "Відсутність raw SQL/shell/filesystem/auth operations",
            "Наявність SEO та accessibility вимог у ExperienceSpec",
        ]
        if failures:
            return QualityReport(
                passed=False,
                summary="Структурна перевірка виявила невиконані build actions.",
                checks_performed=checks,
                issues=[QualityIssue(id="Q1", category="functional", severity="high", description=f"{len(failures)} build actions failed or were blocked.", responsible_agent=AgentRole.BUILDER, suggested_fix="Переглянути capability resolution/permissions і повторити виконання.")],
            )
        if pending:
            return QualityReport(
                passed=False,
                summary="Є операції, що очікують human approval.",
                checks_performed=checks,
                issues=[QualityIssue(id="Q1", category="security", severity="high", description="High-risk action requires approval before execution.", responsible_agent=AgentRole.ORCHESTRATOR, suggested_fix="Отримати explicit approval або замінити дію безпечнішою ability.")],
            )
        return QualityReport(
            passed=True,
            summary="v0.4 structural/API QA passed. Plugin inventory, capability resolution and renderer execution completed; browser/visual security testing is not yet claimed as passed.",
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

    async def architect(self, user_request: str, task_plan: TaskPlan, site_snapshot: SiteSnapshot, renderer: Renderer) -> ApplicationSpec:
        return await self._run(self.architect_agent, json.dumps({"user_request": user_request, "task_plan": task_plan.model_dump(), "site_snapshot": site_snapshot.model_dump(), "renderer": renderer}, ensure_ascii=False))

    async def design(self, app_spec: ApplicationSpec, renderer: Renderer) -> ExperienceSpec:
        return await self._run(self.design_agent, json.dumps({"application_spec": app_spec.model_dump(), "renderer": renderer}, ensure_ascii=False))

    async def build(self, app_spec: ApplicationSpec, experience_spec: ExperienceSpec, site_snapshot: SiteSnapshot, renderer: Renderer) -> BuildPlan:
        return await self._run(self.builder_agent, json.dumps({"application_spec": app_spec.model_dump(), "experience_spec": experience_spec.model_dump(), "site_snapshot": site_snapshot.model_dump(), "renderer": renderer}, ensure_ascii=False))

    async def quality(self, app_spec: ApplicationSpec, experience_spec: ExperienceSpec, executions_json: str, renderer: Renderer) -> QualityReport:
        return await self._run(self.quality_agent, json.dumps({
            "application_spec": app_spec.model_dump(),
            "experience_spec": experience_spec.model_dump(),
            "renderer": renderer,
            "executions": json.loads(executions_json),
            "evidence_limit": "No Playwright/browser evidence is supplied in v0.4; do not claim those checks passed.",
        }, ensure_ascii=False))


def make_agent_runtime(mode: str, model: str) -> AgentRuntime:
    if mode == "openai":
        return OpenAIAgentRuntime(model)
    return MockAgentRuntime()
