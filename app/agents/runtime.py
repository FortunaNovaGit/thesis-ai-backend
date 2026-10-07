from __future__ import annotations

import json
import secrets
from abc import ABC, abstractmethod
from typing import Any

from ..models import (
    AgentRole, AgentUsage, ApplicationSpec, BuildAction, BuildPlan, DesignSystem,
    ExperienceSpec, PageExperienceSpec, PageRequirement, PluginPlanItem,
    QualityIssue, QualityReport, Renderer, SectionContentSpec, SeoSpec,
    SiteSnapshot, TaskItem, TaskPlan,
)
from .prompts import architect_prompt, builder_prompt, design_prompt, orchestrator_prompt, quality_prompt


class AgentRuntime(ABC):
    def __init__(self) -> None:
        self.usage = AgentUsage()

    @abstractmethod
    async def plan(self, user_request: str) -> TaskPlan: ...
    @abstractmethod
    async def architect(self, user_request: str, task_plan: TaskPlan, site_snapshot: SiteSnapshot, renderer: Renderer) -> ApplicationSpec: ...
    @abstractmethod
    async def design(self, app_spec: ApplicationSpec, renderer: Renderer) -> ExperienceSpec: ...
    @abstractmethod
    async def build(self, app_spec: ApplicationSpec, experience_spec: ExperienceSpec, site_snapshot: SiteSnapshot, renderer: Renderer) -> BuildPlan: ...
    @abstractmethod
    async def quality(self, app_spec: ApplicationSpec, experience_spec: ExperienceSpec, executions_json: str, verification_snapshot: SiteSnapshot, renderer: Renderer) -> QualityReport: ...

    async def repair(self, app_spec: ApplicationSpec, experience_spec: ExperienceSpec, verification_snapshot: SiteSnapshot, quality_report: QualityReport, executions_json: str, renderer: Renderer) -> BuildPlan:
        return BuildPlan(actions=[])


def _plugin_active(snapshot: SiteSnapshot, slug: str) -> bool:
    state = snapshot.plugin_state(slug)
    return bool(state and state.get("active"))


def _guess_title(request: str) -> str:
    lower = request.lower()
    if "стомат" in lower:
        return "Стоматологічна клініка"
    if "ветерин" in lower:
        return "Ветеринарна клініка"
    if "магазин" in lower or "shop" in lower or "store" in lower:
        return "Онлайн-магазин"
    return "Новий сайт"


def _section_copy(page_name: str, purpose: str, section: str) -> SectionContentSpec:
    key = section.lower()
    if "hero" in key:
        return SectionContentSpec(section_type="hero", eyebrow="Професійний сервіс", heading=page_name, body=purpose, cta_label="Зв’язатися", cta_url="/contact/", style_variant="dark")
    if "service" in key or "послуг" in key:
        return SectionContentSpec(section_type="services", eyebrow="Послуги", heading="Як ми можемо допомогти", body="Основні напрямки роботи з чітким і зрозумілим процесом.", items=["Консультація та оцінка потреб", "Індивідуальне рішення", "Підтримка після звернення"], cta_label="Переглянути послуги", cta_url="/services/", style_variant="soft")
    if "team" in key or "doctor" in key or "лікар" in key:
        return SectionContentSpec(section_type="team", eyebrow="Команда", heading="Фахівці, які працюють для вашого результату", body="Знайомство з командою та її підходом до роботи.", items=["Професійна комунікація", "Увага до деталей", "Зрозумілі рекомендації"], style_variant="default")
    if "benefit" in key or "перева" in key or "value" in key:
        return SectionContentSpec(section_type="benefits", eyebrow="Переваги", heading="Чому нас обирають", body="Зосереджуємося на якості досвіду та передбачуваному результаті.", items=["Зрозумілий процес", "Сучасний підхід", "Зручна комунікація"], style_variant="soft")
    if "faq" in key:
        return SectionContentSpec(section_type="faq", eyebrow="FAQ", heading="Поширені запитання", body="Короткі відповіді на типові питання перед зверненням.", items=["Як почати? — Залиште заявку або зв’яжіться з нами.", "Що відбувається далі? — Ми уточнюємо потреби та погоджуємо наступний крок.", "Чи можна поставити додаткові питання? — Так, під час консультації."], style_variant="default")
    if "contact" in key or "контакт" in key:
        return SectionContentSpec(section_type="contact", eyebrow="Контакти", heading="Зв’яжіться з нами", body="Оберіть зручний спосіб зв’язку. Контактні дані можна додати у WordPress після генерації.", cta_label="Написати нам", cta_url="#contact", style_variant="soft")
    if "booking" in key or "запис" in key or "form" in key:
        return SectionContentSpec(section_type="booking", eyebrow="Запис", heading="Залиште заявку", body="Опишіть запит, і команда зможе зв’язатися з вами для уточнення деталей.", cta_label="Зв’язатися", cta_url="/contact/", style_variant="accent")
    if "cta" in key:
        return SectionContentSpec(section_type="cta", eyebrow="Наступний крок", heading="Готові обговорити ваш запит?", body="Зв’яжіться з нами — допоможемо визначити найкращий наступний крок.", cta_label="Зв’язатися", cta_url="/contact/", style_variant="accent")
    if "story" in key or "about" in key or "про" in key:
        return SectionContentSpec(section_type="content", eyebrow="Про нас", heading="Підхід, орієнтований на клієнта", body=purpose, style_variant="default")
    if "product" in key or "catalog" in key:
        return SectionContentSpec(section_type="products", eyebrow="Каталог", heading="Товари", body="Структура каталогу буде підключена до WooCommerce.", items=["Популярні товари", "Новинки", "Категорії"], style_variant="soft")
    return SectionContentSpec(section_type="content", heading=section.replace("-", " ").replace("_", " ").title(), body=purpose)


def _eid() -> str:
    return secrets.token_hex(4)


def _responsive_px(size: int) -> dict[str, Any]:
    return {"unit": "px", "size": size, "sizes": []}


def _box(top: int, right: int, bottom: int, left: int) -> dict[str, Any]:
    return {"unit": "px", "top": str(top), "right": str(right), "bottom": str(bottom), "left": str(left), "isLinked": False}


def _widget(widget_type: str, settings: dict[str, Any]) -> dict[str, Any]:
    return {"id": _eid(), "elType": "widget", "widgetType": widget_type, "isInner": False, "settings": settings, "elements": []}


def _container(elements: list[dict[str, Any]], settings: dict[str, Any] | None = None) -> dict[str, Any]:
    # Stability profile: these controls were proven to save correctly in the
    # earlier EasyWP/Elementor integration. Richer responsive/typography controls
    # can be layered back after transport/execution is stable.
    base: dict[str, Any] = {
        "content_width": "boxed",
        "flex_direction": "column",
        "gap": _responsive_px(20),
        "padding": _box(56, 24, 56, 24),
    }
    if settings:
        base.update(settings)
    return {"id": _eid(), "elType": "container", "isInner": False, "settings": base, "elements": elements}


def _heading(text: str, color: str, *, level: str = "h2", size: int = 42, font: str = "Manrope") -> dict[str, Any]:
    return _widget("heading", {
        "title": text,
        "header_size": level,
        "title_color": color,
    })


def _text(text: str, color: str, *, font: str = "Inter") -> dict[str, Any]:
    return _widget("text-editor", {
        "editor": f"<p>{text}</p>",
        "text_color": color,
    })


def _button(label: str, url: str, ds: DesignSystem, *, dark: bool = False) -> dict[str, Any]:
    return _widget("button", {
        "text": label,
        "link": {"url": url, "is_external": "", "nofollow": ""},
        "size": "md",
        "background_color": ds.accent if dark else ds.primary,
        "button_text_color": "#FFFFFF",
        "border_radius": _box(ds.radius, ds.radius, ds.radius, ds.radius),
    })


def _card(title: str, body: str, ds: DesignSystem) -> dict[str, Any]:
    return _container([
        _heading(title, ds.text, level="h3", size=24, font=ds.heading_font),
        _text(body, ds.muted, font=ds.body_font),
    ], {
        "background_background": "classic",
        "background_color": ds.background,
        "padding": _box(24, 24, 24, 24),
        "border_radius": _box(ds.radius, ds.radius, ds.radius, ds.radius),
    })


def _section_bg(variant: str, ds: DesignSystem) -> tuple[str, str, str]:
    if variant == "dark":
        return ds.primary, "#FFFFFF", "#E2E8F0"
    if variant == "accent":
        return ds.accent, "#FFFFFF", "#F8FAFC"
    if variant == "soft":
        return ds.surface, ds.text, ds.muted
    return ds.background, ds.text, ds.muted


def _elementor_page_elements(page: PageExperienceSpec, ds: DesignSystem) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    specs = page.section_specs or [SectionContentSpec(section_type=s, heading=s.title()) for s in page.sections]
    for idx, section in enumerate(specs):
        bg, title_color, body_color = _section_bg(section.style_variant, ds)
        content: list[dict[str, Any]] = []
        if section.eyebrow:
            content.append(_widget("heading", {"title": section.eyebrow.upper(), "header_size": "div", "title_color": ds.accent if section.style_variant != "accent" else "#FFFFFF"}))
        content.append(_heading(section.heading, title_color, level="h1" if idx == 0 else "h2", size=58 if idx == 0 else 42, font=ds.heading_font))
        if section.body:
            content.append(_text(section.body, body_color, font=ds.body_font))
        if section.items:
            cards: list[dict[str, Any]] = []
            for item in section.items[:6]:
                if " — " in item:
                    t, b = item.split(" — ", 1)
                else:
                    t, b = item, "Деталі можна відредагувати в Elementor після генерації."
                cards.append(_card(t, b, ds))
            content.append(_container(cards, {
                "flex_direction": "row", "flex_wrap": "wrap", "justify_content": "space-between",
                "padding": _box(12, 0, 12, 0), "background_color": bg,
                "flex_direction_mobile": "column",
            }))
        if section.section_type == "booking":
            content.append(_widget("shortcode", {"shortcode": '[contact-form-7 title="AI Contact"]'}))
        if section.cta_label and section.cta_url:
            content.append(_button(section.cta_label, section.cta_url, ds, dark=section.style_variant in {"dark", "accent"}))
        result.append(_container(content, {
            "background_background": "classic", "background_color": bg,
            "css_classes": f"thesis-ai-section thesis-ai-{section.section_type}",
        }))
    return result


def _gutenberg_page_content(page: PageExperienceSpec) -> str:
    parts: list[str] = []
    for i, section in enumerate(page.section_specs):
        tag = "h1" if i == 0 else "h2"
        parts.append(f'<!-- wp:group {{"layout":{{"type":"constrained"}}}} --><div class="wp-block-group"><!-- wp:heading {{"level":{1 if i == 0 else 2}}} --><{tag} class="wp-block-heading">{section.heading}</{tag}><!-- /wp:heading -->')
        if section.body:
            parts.append(f'<!-- wp:paragraph --><p>{section.body}</p><!-- /wp:paragraph -->')
        if section.items:
            lis = "".join(f"<li>{x}</li>" for x in section.items)
            parts.append(f'<!-- wp:list --><ul>{lis}</ul><!-- /wp:list -->')
        parts.append('</div><!-- /wp:group -->')
    return "\n".join(parts)




def _normalize_application_spec(spec: ApplicationSpec, renderer: Renderer) -> ApplicationSpec:
    """Apply deterministic invariants after LLM planning without changing user intent."""
    seen: set[str] = set()
    normalized_pages: list[PageRequirement] = []
    for page in spec.pages:
        slug = (page.slug or "").strip().strip("/") or "page"
        if slug in seen:
            continue
        seen.add(slug)
        normalized_pages.append(page.model_copy(update={"slug": slug}))
    if "home" not in seen:
        normalized_pages.insert(0, PageRequirement(
            name="Головна" if spec.language.startswith("uk") else "Home",
            slug="home",
            purpose="Основна посадкова сторінка сайту",
            required_sections=["hero", "benefits", "cta"],
        ))
    approved_plugins = {"elementor", "woocommerce", "advanced-custom-fields", "contact-form-7", "wordpress-seo", "seo-by-rank-math"}
    plugin_plan: list[PluginPlanItem] = []
    plugin_seen: set[str] = set()
    for item in spec.plugin_plan:
        if item.plugin_slug not in approved_plugins or item.plugin_slug in plugin_seen:
            continue
        plugin_seen.add(item.plugin_slug)
        plugin_plan.append(item)

    # Deterministic capability invariants. Agents decide intent, but the runtime
    # guarantees that required implementation dependencies are never forgotten.
    required = set(spec.required_capabilities)
    if renderer in {"elementor", "auto"} and "elementor" not in plugin_seen:
        plugin_plan.insert(0, PluginPlanItem(capability="page_builder_elementor", plugin_slug="elementor", reason="Required Elementor Free renderer"))
        plugin_seen.add("elementor")
    if ("ecommerce" in required or "commerce" in spec.site_type.lower() or "shop" in spec.site_type.lower()) and "woocommerce" not in plugin_seen:
        plugin_plan.append(PluginPlanItem(capability="ecommerce", plugin_slug="woocommerce", reason="Required e-commerce capability"))
        plugin_seen.add("woocommerce")
    if any(ct.implementation == "cpt" for ct in spec.content_types) and "advanced-custom-fields" not in plugin_seen:
        plugin_plan.append(PluginPlanItem(capability="structured_content", plugin_slug="advanced-custom-fields", reason="Structured content/data model capability"))
        plugin_seen.add("advanced-custom-fields")
    if "forms" in required and "contact-form-7" not in plugin_seen:
        plugin_plan.append(PluginPlanItem(capability="forms", plugin_slug="contact-form-7", reason="Approved contact/booking form capability"))
        plugin_seen.add("contact-form-7")

    if renderer in {"elementor", "auto"}:
        theme_slug = "hello-elementor" if spec.theme_slug != "hello-elementor" else spec.theme_slug
    else:
        theme_slug = spec.theme_slug
    return spec.model_copy(update={"pages": normalized_pages, "plugin_plan": plugin_plan, "theme_slug": theme_slug})


def _reconcile_experience_spec(app_spec: ApplicationSpec, experience: ExperienceSpec) -> ExperienceSpec:
    """Guarantee one editable page experience per architectural page."""
    by_name = {p.page_name: p for p in experience.pages}
    pages: list[PageExperienceSpec] = []
    for page in app_spec.pages:
        existing = by_name.get(page.name)
        if existing is None:
            sections = page.required_sections or ["content"]
            existing = PageExperienceSpec(
                page_name=page.name,
                sections=sections,
                section_specs=[_section_copy(page.name, page.purpose, section) for section in sections],
                content_guidance=[page.purpose, "Не вигадувати непідтверджені бізнес-факти"],
                responsive_notes=["Mobile-first stacking", "No horizontal overflow"],
                accessibility_notes=["One H1", "Readable contrast", "Meaningful controls"],
                seo=SeoSpec(
                    slug="/" if page.slug == "home" else f"/{page.slug}/",
                    title=f"{page.name} | {app_spec.site_title}",
                    meta_description=page.purpose,
                    h1=page.name,
                    internal_link_targets=["/"],
                    schema_types=["WebPage"],
                ),
            )
        else:
            seo = existing.seo.model_copy(update={"slug": "/" if page.slug == "home" else f"/{page.slug}/"})
            existing = existing.model_copy(update={"seo": seo})
        pages.append(existing)
    return experience.model_copy(update={"pages": pages})


def _compile_required_build_plan(
    app_spec: ApplicationSpec,
    experience_spec: ExperienceSpec,
    site_snapshot: SiteSnapshot,
    renderer: Renderer,
) -> BuildPlan:
    """Compile the LLM-produced specs into safe, deterministic WordPress actions.

    The agents decide *what* the site should contain. This compiler decides the exact
    low-level Elementor/Gutenberg payload, so an LLM never has to invent internal
    renderer JSON or bypass the controlled ability catalogue.
    """
    actions: list[BuildAction] = []
    if renderer in {"elementor", "auto"}:
        active_theme = str(site_snapshot.site_info.get("theme_slug", ""))
        if active_theme != app_spec.theme_slug:
            actions.append(BuildAction(
                ability="thesis-ai-bridge/ensure-approved-theme",
                parameters={"theme_slug": app_spec.theme_slug},
                rationale="Ensure the approved Elementor-compatible theme selected by architecture",
            ))

    for plugin in app_spec.plugin_plan:
        actions.append(BuildAction(
            ability="thesis-ai-bridge/ensure-approved-plugin",
            parameters={"plugin_slug": plugin.plugin_slug},
            rationale=plugin.reason,
        ))

    if any(p.plugin_slug == "woocommerce" for p in app_spec.plugin_plan) or _plugin_active(site_snapshot, "woocommerce"):
        actions.append(BuildAction(
            ability="thesis-ai-bridge/configure-woocommerce",
            parameters={"currency": "UAH" if app_spec.language.startswith("uk") else "USD"},
            rationale="Configure the basic WooCommerce store and required core pages",
        ))

    cpt_models = [ct.model_dump(mode="json") for ct in app_spec.content_types if ct.implementation == "cpt"]
    if cpt_models:
        actions.append(BuildAction(
            ability="thesis-ai-bridge/apply-acf-model",
            parameters={"content_types": cpt_models},
            rationale="Persist the Architect agent's structured content model using ACF Free + WordPress CPTs",
        ))

    needs_booking_form = any(
        section.section_type == "booking"
        for page in experience_spec.pages
        for section in page.section_specs
    )
    cf7_available_or_planned = _plugin_active(site_snapshot, "contact-form-7") or any(
        p.plugin_slug == "contact-form-7" for p in app_spec.plugin_plan
    )
    if needs_booking_form and cf7_available_or_planned:
        actions.append(BuildAction(
            ability="thesis-ai-bridge/ensure-contact-form",
            parameters={"title": "AI Contact"},
            rationale="Ensure the reusable booking/contact form before rendering pages",
        ))

    exp_by_name = {p.page_name: p for p in experience_spec.pages}
    for page in app_spec.pages:
        exp = exp_by_name.get(page.name)
        if exp is None:
            continue
        if renderer in {"elementor", "auto"}:
            actions.append(BuildAction(
                ability="thesis-ai-bridge/elementor-ensure-draft-page",
                parameters={
                    "title": page.name,
                    "slug": page.slug,
                    "elements": _elementor_page_elements(exp, experience_spec.design_system),
                    "settings": {"hide_title": "yes", "page_layout": "elementor_full_width"},
                },
                rationale=f"Compile ExperienceSpec into an editable Elementor draft page: {page.name}",
            ))
        else:
            actions.append(BuildAction(
                ability="thesis-ai-bridge/ensure-draft-page",
                parameters={"title": page.name, "slug": page.slug, "content": _gutenberg_page_content(exp)},
                rationale=f"Compile ExperienceSpec into an editable Gutenberg draft page: {page.name}",
            ))
        actions.append(BuildAction(
            ability="thesis-ai-bridge/set-page-seo",
            parameters={"slug": page.slug, "seo_title": exp.seo.title, "meta_description": exp.seo.meta_description},
            rationale=f"Apply controlled SEO metadata for {page.name}",
        ))

    actions.extend([
        BuildAction(
            ability="thesis-ai-bridge/update-site-identity",
            parameters={"site_title": app_spec.site_title, "tagline": app_spec.tagline},
            rationale="Apply site identity from ApplicationSpec",
        ),
        BuildAction(
            ability="thesis-ai-bridge/ensure-navigation-menu",
            parameters={"menu_name": "AI Primary", "page_slugs": [p.slug for p in app_spec.pages], "assign_primary": True},
            rationale="Build primary navigation from required pages",
        ),
        BuildAction(
            ability="thesis-ai-bridge/set-homepage-by-slug",
            parameters={"slug": "home"},
            rationale="Set the generated Home page as static homepage",
        ),
    ])
    return BuildPlan(actions=actions)


def _merge_safe_advisory_actions(baseline: BuildPlan, proposed: BuildPlan) -> BuildPlan:
    """Keep deterministic required actions and append only non-duplicate known advisory actions."""
    allowed = {
        "thesis-ai-bridge/ensure-approved-theme",
        "thesis-ai-bridge/ensure-approved-plugin",
        "thesis-ai-bridge/ensure-contact-form",
        "thesis-ai-bridge/elementor-ensure-draft-page",
        "thesis-ai-bridge/ensure-draft-page",
        "thesis-ai-bridge/set-page-seo",
        "thesis-ai-bridge/update-site-identity",
        "thesis-ai-bridge/ensure-navigation-menu",
        "thesis-ai-bridge/set-homepage-by-slug",
        "thesis-ai-bridge/configure-woocommerce",
        "thesis-ai-bridge/apply-acf-model",
    }
    actions = list(baseline.actions)
    seen = {
        (a.ability, json.dumps(a.parameters, sort_keys=True, ensure_ascii=False))
        for a in actions
    }
    for action in proposed.actions:
        if action.ability not in allowed:
            continue
        # Page payloads and site assembly are compiled deterministically from specs.
        if action.ability in {
            "thesis-ai-bridge/elementor-ensure-draft-page",
            "thesis-ai-bridge/ensure-draft-page",
            "thesis-ai-bridge/set-page-seo",
            "thesis-ai-bridge/update-site-identity",
            "thesis-ai-bridge/ensure-navigation-menu",
            "thesis-ai-bridge/set-homepage-by-slug",
        }:
            continue
        key = (action.ability, json.dumps(action.parameters, sort_keys=True, ensure_ascii=False))
        if key not in seen:
            actions.append(action)
            seen.add(key)
    return BuildPlan(actions=actions)


class MockAgentRuntime(AgentRuntime):
    def __init__(self) -> None:
        super().__init__()

    async def plan(self, user_request: str) -> TaskPlan:
        return TaskPlan(project_summary=user_request, tasks=[
            TaskItem(id="T1", title="Inspect current site and capabilities", agent=AgentRole.ARCHITECT, expected_output="SiteSnapshot"),
            TaskItem(id="T2", title="Create application/capability specification", agent=AgentRole.ARCHITECT, depends_on=["T1"], expected_output="ApplicationSpec"),
            TaskItem(id="T3", title="Create design, content and SEO specification", agent=AgentRole.DESIGN, depends_on=["T2"], expected_output="ExperienceSpec"),
            TaskItem(id="T4", title="Build Elementor/WordPress site and setup", agent=AgentRole.BUILDER, depends_on=["T3"], expected_output="BuildPlan"),
            TaskItem(id="T5", title="Verify actual WordPress result", agent=AgentRole.QUALITY, depends_on=["T4"], expected_output="QualityReport"),
        ])

    async def architect(self, user_request: str, task_plan: TaskPlan, site_snapshot: SiteSnapshot, renderer: Renderer) -> ApplicationSpec:
        lower = user_request.lower()
        is_shop = any(x in lower for x in ["магазин", "shop", "store", "woocommerce"])
        pages = [
            PageRequirement(name="Головна", slug="home", purpose="Представити цінність, ключові напрямки та наступний крок", required_sections=["hero", "services", "benefits", "cta"]),
            PageRequirement(name="Про нас", slug="about", purpose="Пояснити підхід, цінності та довіру", required_sections=["hero", "about", "benefits", "cta"]),
            PageRequirement(name="Контакти", slug="contact", purpose="Дати простий спосіб зв’язку", required_sections=["hero", "contact", "cta"]),
        ]
        if "послуг" in lower or "service" in lower or "стомат" in lower:
            pages.insert(1, PageRequirement(name="Послуги", slug="services", purpose="Показати основні послуги та допомогти обрати напрямок", required_sections=["hero", "services", "faq", "cta"]))
        if "лікар" in lower or "team" in lower or "команд" in lower:
            pages.insert(2, PageRequirement(name="Лікарі", slug="doctors", purpose="Представити команду без вигадування персональних даних", required_sections=["hero", "team", "benefits", "cta"]))
        if "запис" in lower or "booking" in lower:
            pages.append(PageRequirement(name="Запис", slug="booking", purpose="Спрямувати користувача до контакту/форми", required_sections=["hero", "booking", "faq"]))
        plugins: list[PluginPlanItem] = []
        if renderer in {"elementor", "auto"} and not _plugin_active(site_snapshot, "elementor"):
            plugins.append(PluginPlanItem(capability="page_builder_elementor", plugin_slug="elementor", reason="Основний Elementor Free renderer"))
        if is_shop and not _plugin_active(site_snapshot, "woocommerce"):
            plugins.append(PluginPlanItem(capability="ecommerce", plugin_slug="woocommerce", reason="Базова e-commerce функціональність"))
        if any(x in lower for x in ["форма", "запис", "booking"]) and not site_snapshot.capabilities.get("recognized_capabilities", {}).get("forms"):
            plugins.append(PluginPlanItem(capability="forms", plugin_slug="contact-form-7", reason="Approved free form capability"))
        if is_shop:
            pages.insert(1, PageRequirement(name="Магазин", slug="shop", purpose="Каталог WooCommerce", required_sections=["hero", "products", "benefits", "cta"]))
        return ApplicationSpec(
            site_type="basic_ecommerce" if is_shop else "business_website",
            site_title=_guess_title(user_request), tagline="Сучасний підхід і зрозумілий сервіс", language="uk", theme_slug="hello-elementor",
            goals=["Створити редагований WordPress-сайт", "Повторно використати наявні capabilities", "Налаштувати основну структуру сайту", "Пройти незалежну перевірку"],
            pages=pages, features=["Elementor editable pages", "site identity", "navigation", "homepage", "SEO metadata"],
            required_capabilities=["page_builder_elementor"] + (["ecommerce"] if is_shop else []), plugin_plan=plugins,
            security_requirements=["least privilege", "no raw SQL", "no shell", "policy gate", "approved dependencies only"],
            performance_requirements=["avoid unnecessary plugins", "responsive containers", "Core Web Vitals-aware design"],
        )

    async def design(self, app_spec: ApplicationSpec, renderer: Renderer) -> ExperienceSpec:
        pages: list[PageExperienceSpec] = []
        for page in app_spec.pages:
            specs = [_section_copy(page.name, page.purpose, s) for s in (page.required_sections or ["content"])]
            pages.append(PageExperienceSpec(
                page_name=page.name, sections=page.required_sections or ["content"], section_specs=specs,
                content_guidance=[page.purpose, "Не вигадувати непідтверджені бізнес-факти"],
                responsive_notes=["Mobile-first stacking", "Cards 3/2/1 columns", "No horizontal overflow"],
                accessibility_notes=["One H1", "Readable contrast", "Meaningful button labels"],
                seo=SeoSpec(slug="/" if page.slug == "home" else f"/{page.slug}/", title=f"{page.name} | {app_spec.site_title}", meta_description=f"{page.purpose}. Дізнайтеся більше на сайті {app_spec.site_title}.", h1=page.name, internal_link_targets=["/"], schema_types=["WebPage", "BreadcrumbList"]),
            ))
        return ExperienceSpec(
            design_direction="Сучасний чистий Elementor-сайт із сильним hero, картковою сіткою, виразними CTA та достатнім whitespace",
            design_system=DesignSystem(),
            component_rules=["Consistent sections", "Reusable cards", "One primary CTA style", "Responsive flex containers", "Semantic heading hierarchy"],
            pages=pages,
        )

    async def build(self, app_spec: ApplicationSpec, experience_spec: ExperienceSpec, site_snapshot: SiteSnapshot, renderer: Renderer) -> BuildPlan:
        return _compile_required_build_plan(app_spec, experience_spec, site_snapshot, renderer)

    async def quality(self, app_spec: ApplicationSpec, experience_spec: ExperienceSpec, executions_json: str, verification_snapshot: SiteSnapshot, renderer: Renderer) -> QualityReport:
        executions = json.loads(executions_json)
        # Evaluate the latest outcome for each logical action instead of counting every
        # historical attempt. Otherwise one transient failure remains a permanent QA
        # failure even after a successful repair, and repair loops inflate the count.
        latest: dict[str, dict] = {}
        for item in executions:
            action = item.get("action") or {}
            key = str(action.get("ability", "")) + "|" + json.dumps(action.get("parameters", {}), sort_keys=True, ensure_ascii=False)
            latest[key] = item
        latest_items = list(latest.values())
        failures = [x for x in latest_items if not x.get("executed") and x.get("policy", {}).get("outcome") != "require_approval"]
        pending = [x for x in latest_items if x.get("policy", {}).get("outcome") == "require_approval"]
        issues: list[QualityIssue] = []
        required_slugs = {p.slug for p in app_spec.pages}
        actual_slugs = {str(p.get("slug", "")) for p in verification_snapshot.pages}
        missing = sorted(required_slugs - actual_slugs)
        if failures:
            issues.append(QualityIssue(id="Q-actions", category="functional", severity="high", description=f"{len(failures)} build actions failed or were blocked.", responsible_agent=AgentRole.BUILDER, suggested_fix="Repair failed idempotent abilities and re-verify."))
        if missing:
            issues.append(QualityIssue(id="Q-pages", category="functional", severity="high", description=f"Missing required pages: {', '.join(missing)}", responsible_agent=AgentRole.BUILDER, suggested_fix="Create the missing AI-owned draft pages."))
        if pending:
            issues.append(QualityIssue(id="Q-approval", category="security", severity="high", description="One or more actions require human approval.", responsible_agent=AgentRole.ORCHESTRATOR, suggested_fix="Approve explicitly or choose a safer implementation."))
        structure = verification_snapshot.structure
        if structure and structure.get("homepage_slug") not in {"home", ""}:
            issues.append(QualityIssue(id="Q-home", category="functional", severity="medium", description="Generated Home page is not configured as the static homepage.", responsible_agent=AgentRole.BUILDER, suggested_fix="Run set-homepage-by-slug for home."))
        checks = ["post-build page inventory", "plugin/theme capability verification", "policy outcomes", "site identity/homepage/navigation structure", "SEO metadata write actions", "Elementor renderer structure"]
        return QualityReport(passed=not issues, summary="v0.5 post-build structural verification passed." if not issues else "Post-build verification found issues that can enter the repair loop.", checks_performed=checks, issues=issues)

    async def repair(self, app_spec: ApplicationSpec, experience_spec: ExperienceSpec, verification_snapshot: SiteSnapshot, quality_report: QualityReport, executions_json: str, renderer: Renderer) -> BuildPlan:
        # Deterministic mock only retries failed safe/idempotent actions once.
        executions = json.loads(executions_json)
        actions: list[BuildAction] = []
        safe_retry = {"thesis-ai-bridge/elementor-ensure-draft-page", "thesis-ai-bridge/ensure-draft-page", "thesis-ai-bridge/set-page-seo", "thesis-ai-bridge/update-site-identity", "thesis-ai-bridge/ensure-navigation-menu", "thesis-ai-bridge/set-homepage-by-slug", "thesis-ai-bridge/ensure-approved-plugin", "thesis-ai-bridge/ensure-approved-theme"}
        latest: dict[str, dict] = {}
        for item in executions:
            action = item.get("action") or {}
            ability = str(action.get("ability", ""))
            key = ability + json.dumps(action.get("parameters", {}), sort_keys=True, ensure_ascii=False)
            latest[key] = item
        for key, item in latest.items():
            if item.get("executed"):
                continue
            action = item.get("action") or {}
            ability = str(action.get("ability", ""))
            if ability in safe_retry:
                actions.append(BuildAction(ability=ability, parameters=action.get("parameters", {}), rationale="Repair retry after verification failure"))
        return BuildPlan(actions=actions)


class OpenAIAgentRuntime(AgentRuntime):
    def __init__(self, model: str) -> None:
        super().__init__()
        try:
            from agents import Agent
        except ImportError as exc:
            raise RuntimeError("Install dependencies with: pip install -e .") from exc
        self.model = model
        self.orchestrator = Agent(name="Orchestrator", instructions=orchestrator_prompt(), model=model, output_type=TaskPlan)
        self.architect_agent = Agent(name="Architect & Capability", instructions=architect_prompt(), model=model, output_type=ApplicationSpec)
        self.design_agent = Agent(name="Design, Content & SEO", instructions=design_prompt(), model=model, output_type=ExperienceSpec)
        self.builder_agent = Agent(name="WordPress Implementation", instructions=builder_prompt(), model=model, output_type=BuildPlan)
        self.quality_agent = Agent(name="Quality & Security", instructions=quality_prompt(), model=model, output_type=QualityReport)

    async def _run(self, agent, payload: str):
        from agents import Runner
        result = await Runner.run(agent, payload, max_turns=8)
        usage = result.context_wrapper.usage
        self.usage.add(AgentUsage(requests=int(usage.requests), input_tokens=int(usage.input_tokens), output_tokens=int(usage.output_tokens), total_tokens=int(usage.total_tokens)))
        return result.final_output

    async def plan(self, user_request: str) -> TaskPlan:
        return await self._run(self.orchestrator, user_request)

    async def architect(self, user_request: str, task_plan: TaskPlan, site_snapshot: SiteSnapshot, renderer: Renderer) -> ApplicationSpec:
        result = await self._run(self.architect_agent, json.dumps({"user_request": user_request, "task_plan": task_plan.model_dump(), "site_snapshot": site_snapshot.model_dump(), "renderer": renderer}, ensure_ascii=False))
        return _normalize_application_spec(result, renderer)

    async def design(self, app_spec: ApplicationSpec, renderer: Renderer) -> ExperienceSpec:
        result = await self._run(self.design_agent, json.dumps({"application_spec": app_spec.model_dump(), "renderer": renderer}, ensure_ascii=False))
        return _reconcile_experience_spec(app_spec, result)

    async def build(self, app_spec: ApplicationSpec, experience_spec: ExperienceSpec, site_snapshot: SiteSnapshot, renderer: Renderer) -> BuildPlan:
        proposed = await self._run(
            self.builder_agent,
            json.dumps({
                "application_spec": app_spec.model_dump(),
                "experience_spec": experience_spec.model_dump(),
                "site_snapshot": site_snapshot.model_dump(),
                "renderer": renderer,
                "instruction": "Plan only controlled high-level abilities. Exact Elementor/Gutenberg renderer payloads are compiled deterministically by the runtime.",
            }, ensure_ascii=False),
        )
        baseline = _compile_required_build_plan(app_spec, experience_spec, site_snapshot, renderer)
        return _merge_safe_advisory_actions(baseline, proposed)

    async def quality(self, app_spec: ApplicationSpec, experience_spec: ExperienceSpec, executions_json: str, verification_snapshot: SiteSnapshot, renderer: Renderer) -> QualityReport:
        return await self._run(self.quality_agent, json.dumps({"application_spec": app_spec.model_dump(), "experience_spec": experience_spec.model_dump(), "renderer": renderer, "executions": json.loads(executions_json), "verification_snapshot": verification_snapshot.model_dump(), "evidence_limit": "No browser/visual test evidence is supplied; do not claim it passed."}, ensure_ascii=False))

    async def repair(self, app_spec: ApplicationSpec, experience_spec: ExperienceSpec, verification_snapshot: SiteSnapshot, quality_report: QualityReport, executions_json: str, renderer: Renderer) -> BuildPlan:
        return await self._run(self.builder_agent, json.dumps({"mode": "repair", "application_spec": app_spec.model_dump(), "experience_spec": experience_spec.model_dump(), "renderer": renderer, "verification_snapshot": verification_snapshot.model_dump(), "quality_report": quality_report.model_dump(), "executions": json.loads(executions_json), "instruction": "Return the smallest safe idempotent BuildPlan that fixes the listed issues. Do not repeat successful actions unless necessary."}, ensure_ascii=False))


def make_agent_runtime(mode: str, model: str) -> AgentRuntime:
    if mode == "openai":
        return OpenAIAgentRuntime(model)
    return MockAgentRuntime()
