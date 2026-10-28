from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from ..budget import BudgetLimits, BudgetTracker
from ..capabilities import canonicalize_capability, plugin_plan_from_resolutions, resolve_capabilities
from ..component_library import compile_elementor_page, compile_gutenberg_page
from ..models import (
    AgentRole,
    AgentUsage,
    ApplicationSpec,
    ArchitectureBundle,
    BuildAction,
    BuildPlan,
    CapabilityRequirement,
    CapabilityResolution,
    ContentMatrixRow,
    DesignSystem,
    ExperienceSpec,
    PageExperienceSpec,
    PageIntent,
    PageRequirement,
    ProjectBrief,
    QualityIssue,
    QualityReport,
    Renderer,
    SectionContentSpec,
    SeoSpec,
    SiteSnapshot,
    TaskItem,
    TaskPlan,
)
from .prompts import (
    architect_prompt,
    builder_prompt,
    design_prompt,
    orchestrator_prompt,
    quality_prompt,
    repair_prompt,
)


class AgentRuntime(ABC):
    def __init__(self) -> None:
        self.usage = AgentUsage()

    @abstractmethod
    async def orchestrate(self, user_request: str, renderer: Renderer) -> ProjectBrief: ...

    @abstractmethod
    async def architect(self, brief: ProjectBrief, site_summary: dict[str, Any]) -> ArchitectureBundle: ...

    @abstractmethod
    async def design(self, brief: ProjectBrief, architecture: ArchitectureBundle) -> ExperienceSpec: ...

    @abstractmethod
    async def build(self, implementation_manifest: dict[str, Any]) -> BuildPlan: ...

    @abstractmethod
    async def quality(self, qa_evidence: dict[str, Any]) -> QualityReport: ...

    async def repair(self, repair_evidence: dict[str, Any]) -> BuildPlan:
        return BuildPlan(actions=[])

    def budget_state(self) -> dict[str, Any]:
        return {}


# ---------- deterministic artifact normalization ----------


def _guess_title(request: str) -> str:
    lower = request.lower()
    if "стомат" in lower:
        return "Стоматологічна клініка"
    if "ветерин" in lower:
        return "Ветеринарна клініка"
    if "магазин" in lower or "shop" in lower or "store" in lower:
        return "Онлайн-магазин"
    return "Новий сайт"


def _canonical_slug(value: str, name: str = "") -> str:
    source = (value or name or "page").strip().lower().strip("/")
    aliases = {
        "головна": "home", "homepage": "home", "main": "home", "index": "home",
        "про-нас": "about", "про нас": "about", "about-us": "about",
        "послуги": "services", "service": "services",
        "лікарі": "doctors", "команда": "doctors", "team": "doctors",
        "контакти": "contact", "contacts": "contact",
        "запис": "booking", "appointment": "booking", "appointments": "booking",
        "блог": "blog",
    }
    if source in aliases:
        return aliases[source]
    source = re.sub(r"[^a-z0-9_-]+", "-", source)
    source = re.sub(r"-+", "-", source).strip("-")
    return source or "page"


def _task_plan_from_brief(brief: ProjectBrief) -> TaskPlan:
    return TaskPlan(
        project_summary=f"{brief.site_type}: {brief.primary_goal}",
        tasks=[
            TaskItem(id="T1", title="Normalize project brief", agent=AgentRole.ORCHESTRATOR, expected_output="ProjectBrief"),
            TaskItem(id="T2", title="Design site architecture and resolve capabilities", agent=AgentRole.ARCHITECT, depends_on=["T1"], expected_output="ArchitectureBundle + CapabilityPlan"),
            TaskItem(id="T3", title="Create coherent design/content/SEO specification", agent=AgentRole.DESIGN, depends_on=["T2"], expected_output="ExperienceSpec"),
            TaskItem(id="T4", title="Compile safe WordPress implementation", agent=AgentRole.BUILDER, depends_on=["T3"], expected_output="BuildPlan"),
            TaskItem(id="T5", title="Verify facts, structure, content logic and policy", agent=AgentRole.QUALITY, depends_on=["T4"], expected_output="QualityReport"),
        ],
    )


def compact_site_summary(snapshot: SiteSnapshot) -> dict[str, Any]:
    """Only the facts an Architect needs. Never forward the entire raw snapshot."""
    plugins = [
        {"slug": str(p.get("slug", "")), "active": bool(p.get("active")), "version": str(p.get("version", ""))}
        for p in snapshot.plugins if p.get("slug")
    ]
    themes = [
        {"slug": str(t.get("slug", "")), "active": bool(t.get("active")), "version": str(t.get("version", ""))}
        for t in snapshot.themes if t.get("slug")
    ]
    pages = [
        {"slug": str(p.get("slug", "")), "title": str(p.get("title", "")), "status": str(p.get("status", ""))}
        for p in snapshot.pages[:50]
    ]
    recognized = snapshot.capabilities.get("recognized_capabilities", {}) if isinstance(snapshot.capabilities, dict) else {}
    return {
        "site_name": str(snapshot.site_info.get("name", snapshot.site_info.get("site_name", ""))),
        "active_theme": str(snapshot.structure.get("active_theme_slug", snapshot.site_info.get("theme_slug", ""))),
        "homepage_slug": str(snapshot.structure.get("homepage_slug", "")),
        "pages": pages,
        "plugins": plugins,
        "themes": themes,
        "recognized_capabilities": recognized if isinstance(recognized, dict) else {},
    }


def _normalize_architecture(brief: ProjectBrief, architecture: ArchitectureBundle) -> ArchitectureBundle:
    seen: set[str] = set()
    pages: list[PageIntent] = []
    for page in architecture.pages:
        slug = _canonical_slug(page.slug, page.name)
        if slug in seen:
            continue
        seen.add(slug)
        goals = list(dict.fromkeys([str(x).strip().lower() for x in page.section_goals if str(x).strip()]))
        # Guardrails for the common business-site path. The Architect still decides
        # the page set and intent; these defaults prevent a sparse plan from turning
        # into a page with one repeated heading.
        required_by_slug: dict[str, list[str]] = {
            "home": ["hero", "services", "benefits", "cta"],
            "services": ["hero", "services", "process", "cta"],
            "contact": ["hero", "contact"],
            "about": ["hero", "content", "benefits", "cta"],
            "doctors": ["hero", "team", "trust", "cta"],
            "booking": ["hero", "booking", "faq"],
        }
        for required in required_by_slug.get(slug, ["hero", "content", "cta"]):
            if required not in goals:
                goals.append(required)
        if slug == "contact" and any(x in {"forms", "booking"} or "форм" in x.lower() or "запис" in x.lower() for x in brief.requirements):
            if "booking" not in goals:
                goals.append("booking")
        pages.append(page.model_copy(update={"slug": slug, "section_goals": goals}))
    if "home" not in seen:
        pages.insert(0, PageIntent(
            name="Головна" if brief.language.startswith("uk") else "Home",
            slug="home",
            purpose="Основна посадкова сторінка, що пояснює цінність і веде до головної конверсії",
            search_intent=brief.site_type,
            primary_cta="Записатися" if "booking" in brief.requirements or "запис" in " ".join(brief.requirements).lower() else "Зв’язатися",
            primary_cta_url="/booking/" if any("booking" in x or "запис" in x for x in brief.requirements) else "/contact/",
            section_goals=["hero", "services", "benefits", "trust", "cta"],
        ))

    matrix_by_slug = {row.page_slug: row for row in architecture.content_matrix}
    matrix: list[ContentMatrixRow] = []
    valid_slugs = {p.slug for p in pages}
    for page in pages:
        row = matrix_by_slug.get(page.slug)
        links = [x for x in (row.internal_links if row else []) if x in valid_slugs and x != page.slug]
        if not links:
            links = ["home"] if page.slug != "home" else [x for x in ["services", "doctors", "contact", "booking"] if x in valid_slugs]
        matrix.append(ContentMatrixRow(
            page_slug=page.slug,
            page_goal=(row.page_goal if row else page.purpose),
            search_intent=(row.search_intent if row else page.search_intent),
            primary_cta=(row.primary_cta if row else page.primary_cta),
            secondary_cta=(row.secondary_cta if row else ""),
            key_messages=(row.key_messages if row else [page.purpose]),
            internal_links=links,
        ))

    capability_seen: set[str] = set()
    capabilities: list[CapabilityRequirement] = []
    baseline_capabilities = [
        CapabilityRequirement(capability="pages", reason="Architecture contains generated WordPress pages", priority="required"),
        CapabilityRequirement(capability="site_identity", reason="Generated site needs title/tagline identity", priority="required"),
        CapabilityRequirement(capability="seo", reason="Generated pages require basic SEO metadata", priority="required"),
    ]
    if len(pages) > 1:
        baseline_capabilities.append(CapabilityRequirement(
            capability="navigation", reason="Multiple pages require site navigation", priority="required"
        ))
    if brief.renderer in {"elementor", "auto"}:
        baseline_capabilities.append(CapabilityRequirement(
            capability="page_builder_elementor", reason="Selected renderer is Elementor", priority="required"
        ))
    if any("booking" in p.section_goals for p in pages):
        baseline_capabilities.append(CapabilityRequirement(
            capability="forms", reason="Architecture contains a booking/contact form section", priority="required"
        ))

    for item in [*baseline_capabilities, *architecture.capabilities]:
        key = canonicalize_capability(item.capability)
        if key and key not in capability_seen:
            capability_seen.add(key)
            capabilities.append(item.model_copy(update={"capability": key}))

    return architecture.model_copy(update={"pages": pages, "content_matrix": matrix, "capabilities": capabilities})

def architecture_to_application_spec(
    brief: ProjectBrief,
    architecture: ArchitectureBundle,
    resolutions: list[CapabilityResolution],
) -> ApplicationSpec:
    pages = [
        PageRequirement(
            name=p.name,
            slug=p.slug,
            purpose=p.purpose,
            required_sections=p.section_goals or ["hero", "content", "cta"],
        )
        for p in architecture.pages
    ]
    required_capabilities = [r.capability for r in architecture.capabilities if r.priority == "required"]
    return ApplicationSpec(
        site_type=brief.site_type,
        site_title=architecture.site_title,
        tagline=architecture.tagline,
        language=brief.language,
        theme_slug=architecture.theme_slug,
        goals=[brief.primary_goal, *brief.secondary_goals],
        pages=pages,
        features=list(dict.fromkeys(brief.requirements + required_capabilities)),
        content_types=architecture.content_types,
        required_capabilities=required_capabilities,
        plugin_plan=plugin_plan_from_resolutions(resolutions),
        security_requirements=architecture.security_requirements,
        performance_requirements=architecture.performance_requirements,
    )


def _visitor_defaults(
    brief: ProjectBrief,
    page: PageIntent,
    section_type: str,
    matrix: ContentMatrixRow | None,
    site_title: str,
) -> dict[str, Any]:
    dental = brief.site_type == "dental_clinic" or "стомат" in site_title.lower()
    cta = (matrix.primary_cta if matrix else page.primary_cta) or "Зв’язатися"
    cta_url = page.primary_cta_url or ("/contact/" if page.slug != "contact" else "#contact-form")
    # Domain pack: it provides safe, non-factual fallback language only when the
    # creative agent returns sparse/planning-style copy. It never invents people,
    # prices, years, addresses, reviews or clinical claims.
    if dental:
        by_slug: dict[str, dict[str, tuple[str, str, list[str]]]] = {
            "home": {
                "hero": ("Стоматологія, де зрозуміло кожен наступний крок", "Профілактика, лікування та консультації у зрозумілому форматі. Почніть із вашого запиту — команда допоможе визначити доречний наступний крок.", ["Зрозумілий маршрут — від першого звернення до плану дій", "Турбота про комфорт — спокійна комунікація без зайвого тиску", "Зручний контакт — короткий шлях до консультації"]),
                "services": ("Основні напрямки стоматологічної допомоги", "Оберіть напрямок, який найбільше відповідає вашій ситуації. Остаточний план визначається після індивідуальної консультації.", ["Профілактика та гігієна — регулярний догляд і підтримка здоров’я ротової порожнини", "Лікування зубів — поетапний підхід до поширених стоматологічних проблем", "Відновлення та естетика — рішення для функції та природного вигляду усмішки"]),
                "benefits": ("Турбота без зайвої невизначеності", "Хороший досвід починається з чіткої комунікації та зрозумілих наступних кроків.", ["Спочатку — ваш запит — з’ясовуємо, що саме турбує і який результат важливий", "Потім — зрозумілий план — пояснюємо можливі наступні кроки простою мовою", "Далі — зручний зв’язок — залишайте заявку, коли готові перейти до консультації"]),
                "trust": ("Прозорий підхід до взаємодії", "Без вигаданих обіцянок і гучних цифр: сайт фокусується на зрозумілому сервісі та підтверджених даних.", ["Чітка комунікація — запитання можна уточнити до візиту", "Послідовність — кожен етап має зрозумілий наступний крок", "Редагованість — фактичні дані клініки легко додати у WordPress"]),
                "team": ("Люди, які пояснюють і допомагають", "Знайомство з фахівцями має починатися з підтверджених імен, ролей та досвіду. Поки цих даних немає, сторінка не вигадує профілі — їх можна додати після уточнення інформації клініки.", ["Профілі без вигаданих фактів", "Зрозуміле пояснення ролі спеціаліста", "Можливість швидко перейти до консультації"]),
                "cta": ("Готові обговорити ваш запит?", "Залиште звернення — команда клініки зможе уточнити деталі та запропонувати наступний крок.", []),
            },
            "services": {
                "hero": ("Стоматологічні послуги для щоденного здоров’я усмішки", "Від профілактики до відновлення: перегляньте основні напрямки й оберіть, з чого почати консультацію.", ["Профілактика", "Лікування", "Відновлення"]),
                "services": ("З чим можна звернутися", "Нижче — базові напрямки, які допомагають зорієнтуватися перед консультацією.", ["Профілактика та професійна гігієна — підтримка здоров’я зубів і ясен та профілактичний контроль", "Терапевтичне лікування — робота з карієсом, чутливістю та іншими поширеними скаргами", "Відновлення зубів — рішення, спрямовані на функцію, комфорт і природний вигляд"]),
                "process": ("Як починається робота", "Не потрібно самостійно визначати потрібну процедуру — достатньо описати свій запит.", ["1. Звернення — коротко опишіть, що вас турбує", "2. Консультація — уточнюються потреби та можливі варіанти", "3. Наступний крок — формується зрозумілий план подальших дій"]),
                "faq": ("Поширені запитання перед зверненням", "Короткі відповіді допоможуть підготуватися до першого контакту.", ["Не знаю, яка послуга потрібна — опишіть симптом або бажаний результат, а напрямок можна уточнити під час консультації", "Чи можна спочатку поставити запитання? — так, використайте контактну форму на сайті", "Де подивитися точні ціни? — вартість варто додати лише після підтвердження клінікою"]),
                "cta": ("Потрібна допомога з вибором послуги?", "Залиште звернення, щоб уточнити ваш запит і домовитися про консультацію.", []),
            },
            "contact": {
                "hero": ("Зв’яжіться з клінікою зручним способом", "Поставте запитання або залиште заявку на консультацію. Контактні дані можна доповнити підтвердженою адресою, телефоном і графіком роботи.", ["Запитання перед візитом", "Заявка на консультацію", "Уточнення наступного кроку"]),
                "contact": ("Є запитання перед візитом?", "Напишіть, що саме вас цікавить. Якщо у вихідному запиті не було адреси чи телефону, ми не вигадуємо їх — підтверджені дані можна додати у WordPress.", ["Телефон — додайте підтверджений номер клініки", "Email — додайте робочу адресу для звернень", "Адреса і графік — заповніть фактичними даними клініки"]),
                "booking": ("Залиште заявку на консультацію", "Коротко опишіть ваш запит і залиште контакт для відповіді. Не надсилайте через форму зайві медичні або інші чутливі дані.", []),
                "cta": ("Готові зробити перший крок?", "Залиште звернення — команда клініки зв’яжеться з вами після отримання заявки.", []),
            },
        }
        page_pack = by_slug.get(page.slug, {})
        if section_type in page_pack:
            h, b, items = page_pack[section_type]
            return {"heading": h, "body": b, "items": items, "cta_label": cta, "cta_url": cta_url}

    generic_headings = {
        "hero": page.name,
        "services": "Що ми пропонуємо",
        "benefits": "Чому цей підхід зручний",
        "trust": "Що допомагає прийняти рішення",
        "team": "Команда і підхід",
        "process": "Як усе відбувається",
        "stats": "Коротко про головне",
        "faq": "Поширені запитання",
        "contact": "Як зв’язатися",
        "booking": "Залиште заявку",
        "cta": "Готові перейти до наступного кроку?",
        "content": "Детальніше",
    }
    messages = [m for m in (matrix.key_messages if matrix else []) if not _looks_internal_copy(str(m))]
    generic_bodies = {
        "hero": f"Дізнайтеся головне про {site_title} і оберіть зручний наступний крок.",
        "services": "Перегляньте основні напрямки та знайдіть варіант, який відповідає вашому запиту.",
        "benefits": "Ключові переваги подані просто й конкретно, щоб рішення було легше прийняти.",
        "trust": "Фокус на прозорій комунікації, підтверджених даних і зрозумілих наступних кроках.",
        "team": "Додайте підтверджені профілі фахівців, щоб відвідувачі могли познайомитися з командою без вигаданих фактів.",
        "process": "Короткий послідовний маршрут допомагає зрозуміти, що відбувається після першого звернення.",
        "stats": "Тут варто використовувати лише перевірені цифри та факти, які надав власник сайту.",
        "faq": "Відповіді на типові запитання допомагають відвідувачеві швидше зорієнтуватися перед зверненням.",
        "contact": "Оберіть зручний спосіб зв’язку або залиште коротке звернення через форму.",
        "booking": "Залиште контакт і коротко опишіть запит — команда зможе повернутися з відповіддю.",
        "cta": "Зробіть наступний крок у зручний для вас спосіб.",
        "content": "Коротка практична інформація, що допомагає відвідувачеві перейти до наступної дії.",
    }
    return {
        "heading": generic_headings.get(section_type, page.name),
        "body": messages[0] if messages else generic_bodies.get(section_type, generic_bodies["content"]),
        "items": messages[:4],
        "cta_label": cta,
        "cta_url": cta_url,
    }


def _looks_internal_copy(text: str) -> bool:
    value = (text or "").strip().lower()
    if not value:
        return True
    markers = [
        "ця сторінка", "сторінка має", "додайте", "після генерації", "контент секції",
        "мета сторінки", "надати канал", "допомогти зрозуміти", "розкрити принципи",
        "сформувати довіру", "зменшити friction", "користувач повинен", "пояснити роль сторінки",
    ]
    return any(m in value for m in markers)


def _default_section(brief: ProjectBrief, page: PageIntent, section_type: str, matrix: ContentMatrixRow | None, site_title: str) -> SectionContentSpec:
    defaults = _visitor_defaults(brief, page, section_type, matrix, site_title)
    variant = "dark" if section_type in {"hero", "cta"} else ("soft" if section_type in {"services", "benefits", "trust", "booking", "contact", "faq"} else "default")
    component = {
        "hero": "hero_split_v2", "services": "services_grid_v2", "benefits": "benefits_grid_v2",
        "trust": "trust_grid_v2", "team": "team_grid_v2", "process": "process_steps_v2",
        "faq": "faq_cards_v2", "booking": "booking_form_v2", "contact": "contact_split_v2",
        "cta": "cta_band_v2",
    }.get(section_type, f"{section_type}_v2")
    return SectionContentSpec(
        section_type=section_type,
        component_key=component,
        section_goal=page.purpose,
        eyebrow=site_title if section_type == "hero" else (page.name if section_type not in {"cta", "booking"} else ""),
        heading=str(defaults["heading"]),
        body=str(defaults["body"]),
        items=list(defaults.get("items", [])),
        cta_label=str(defaults.get("cta_label") or "") or None if section_type in {"hero", "cta", "contact"} else None,
        cta_url=str(defaults.get("cta_url") or "") or None if section_type in {"hero", "cta", "contact"} else None,
        style_variant=variant,
    )


def reconcile_experience(
    brief: ProjectBrief,
    architecture: ArchitectureBundle,
    experience: ExperienceSpec,
) -> ExperienceSpec:
    matrix_by_slug = {m.page_slug: m for m in architecture.content_matrix}
    exp_by_slug = {p.page_slug: p for p in experience.pages if p.page_slug}
    exp_by_name = {p.page_name: p for p in experience.pages}
    output: list[PageExperienceSpec] = []
    global_h1s: set[str] = set()

    for page in architecture.pages:
        existing = exp_by_slug.get(page.slug) or exp_by_name.get(page.name)
        matrix = matrix_by_slug.get(page.slug)
        required_types = list(dict.fromkeys(page.section_goals or ["hero", "content", "cta"]))
        incoming_by_type: dict[str, list[SectionContentSpec]] = {}
        if existing is not None:
            for sec in existing.section_specs:
                incoming_by_type.setdefault(sec.section_type.strip().lower() or "content", []).append(sec)

        specs: list[SectionContentSpec] = []
        used_headings: set[str] = set()
        for index, section_type in enumerate(required_types):
            fallback = _default_section(brief, page, section_type, matrix, architecture.site_title)
            candidates = incoming_by_type.get(section_type, [])
            sec = candidates.pop(0) if candidates else fallback

            heading = (sec.heading or "").strip()
            body = (sec.body or "").strip()
            if not heading or (index > 0 and heading.casefold() == page.name.casefold()) or heading.casefold() in used_headings or _looks_internal_copy(heading):
                heading = fallback.heading
            if not body or len(body) < 45 or _looks_internal_copy(body):
                body = fallback.body

            items = [x.strip() for x in sec.items if str(x).strip()]
            if section_type in {"services", "benefits", "trust", "team", "process", "stats", "faq"} and len(items) < 3:
                items = list(dict.fromkeys([*items, *fallback.items]))[:6]
            if section_type in {"hero", "contact"} and not items and fallback.items:
                items = fallback.items[:3]

            cta_label = sec.cta_label
            cta_url = sec.cta_url
            if section_type in {"hero", "cta"} and not cta_label:
                cta_label = fallback.cta_label
                cta_url = fallback.cta_url
            if cta_label and not cta_url:
                cta_url = fallback.cta_url

            component_key = sec.component_key or fallback.component_key
            style_variant = sec.style_variant or fallback.style_variant
            sec = sec.model_copy(update={
                "section_type": section_type,
                "component_key": component_key,
                "section_goal": sec.section_goal or fallback.section_goal,
                "eyebrow": sec.eyebrow or fallback.eyebrow,
                "heading": heading,
                "body": body,
                "items": items,
                "cta_label": cta_label,
                "cta_url": cta_url,
                "style_variant": style_variant,
            })
            used_headings.add(heading.casefold())
            specs.append(sec)

        fallback_seo = SeoSpec(
            slug="/" if page.slug == "home" else f"/{page.slug}/",
            title=f"{page.name} | {architecture.site_title}",
            meta_description=(_visitor_defaults(brief, page, "hero", matrix, architecture.site_title)["body"] or page.purpose)[:155],
            h1=specs[0].heading if specs else page.name,
            internal_link_targets=["/" if x == "home" else f"/{x}/" for x in (matrix.internal_links if matrix else [])],
            schema_types=["WebPage"],
        )
        if existing is None:
            seo = fallback_seo
            content_guidance = ["Visitor-facing copy only", "Do not fabricate missing facts", *(matrix.key_messages if matrix else [])]
            responsive_notes = ["Mobile-first stacking", "No horizontal overflow"]
            accessibility_notes = ["Exactly one H1", "Readable contrast", "Descriptive links"]
        else:
            seo = existing.seo.model_copy(update={
                "slug": fallback_seo.slug,
                "h1": existing.seo.h1 if existing.seo.h1 and not _looks_internal_copy(existing.seo.h1) else fallback_seo.h1,
                "title": existing.seo.title or fallback_seo.title,
                "meta_description": existing.seo.meta_description if len(existing.seo.meta_description.strip()) >= 60 and not _looks_internal_copy(existing.seo.meta_description) else fallback_seo.meta_description,
                "internal_link_targets": fallback_seo.internal_link_targets,
            })
            content_guidance = existing.content_guidance
            responsive_notes = existing.responsive_notes
            accessibility_notes = existing.accessibility_notes

        # One unique H1 per generated page. The hero heading is the rendered H1.
        h1 = specs[0].heading if specs else seo.h1
        if h1.casefold() in global_h1s:
            h1 = f"{page.name}: {architecture.site_title}"
            if specs:
                specs[0] = specs[0].model_copy(update={"heading": h1})
        global_h1s.add(h1.casefold())
        seo = seo.model_copy(update={"h1": h1})

        output.append(PageExperienceSpec(
            page_name=page.name,
            page_slug=page.slug,
            page_goal=page.purpose,
            sections=required_types,
            section_specs=specs,
            content_guidance=content_guidance,
            responsive_notes=responsive_notes,
            accessibility_notes=accessibility_notes,
            seo=seo,
        ))

    return experience.model_copy(update={"pages": output})

def explicitly_named_demo_products(user_request: str, *, max_products: int = 4) -> list[str]:
    """Extract only product names explicitly quoted by the user.

    AI-generated suggestions are deliberately not trusted as product facts.
    Anything unquoted/ambiguous is omitted; products never receive inferred prices.
    """
    quoted = re.findall(r"[«\"]([^»\"]{3,100})[»\"]", user_request or "")
    result: list[str] = []
    for raw in quoted:
        title = " ".join(raw.strip().split())
        lower = title.casefold()
        if not any(term in lower for term in ("цукер", "шоколад", "асорті", "пралін", "набір")):
            continue
        if title not in result and len(title) <= 100:
            result.append(title)
        if len(result) >= max_products:
            break
    return result


def compile_build_plan(
    app_spec: ApplicationSpec,
    experience_spec: ExperienceSpec,
    snapshot: SiteSnapshot,
    renderer: Renderer,
    user_request: str = "",
) -> BuildPlan:
    actions: list[BuildAction] = []
    active_theme = str(snapshot.structure.get("active_theme_slug", snapshot.site_info.get("theme_slug", "")))
    if renderer in {"elementor", "auto"} and active_theme != app_spec.theme_slug:
        actions.append(BuildAction(
            ability="thesis-ai-bridge/ensure-approved-theme",
            parameters={"theme_slug": app_spec.theme_slug},
            rationale="Ensure the approved Elementor-compatible theme",
        ))

    for plugin in app_spec.plugin_plan:
        state = snapshot.plugin_state(plugin.plugin_slug)
        if state and state.get("active"):
            continue
        actions.append(BuildAction(
            ability="thesis-ai-bridge/ensure-approved-plugin",
            parameters={"plugin_slug": plugin.plugin_slug},
            rationale=plugin.reason,
        ))

    if any(p.plugin_slug == "woocommerce" for p in app_spec.plugin_plan) or bool(snapshot.plugin_state("woocommerce") and snapshot.plugin_state("woocommerce").get("active")):
        actions.append(BuildAction(
            ability="thesis-ai-bridge/configure-woocommerce",
            parameters={"currency": "UAH" if app_spec.language.startswith("uk") else "USD"},
            rationale="Configure the basic WooCommerce store",
        ))

    ecommerce_requested = any(p.plugin_slug == "woocommerce" for p in app_spec.plugin_plan) or "ecommerce" in app_spec.required_capabilities
    if ecommerce_requested:
        for product_name in explicitly_named_demo_products(user_request):
            actions.append(BuildAction(
                ability="thesis-ai-bridge/ensure-woocommerce-product-draft",
                parameters={
                    "name": product_name,
                    "description": "Демонстраційний товар. Склад, ціна, вага, наявність і фотографії потребують підтвердження перед публікацією.",
                },
                rationale="Create only the explicitly requested WooCommerce product draft without inventing commercial facts",
            ))

    cpt_models = [ct.model_dump(mode="json") for ct in app_spec.content_types if ct.implementation == "cpt"]
    if cpt_models:
        actions.append(BuildAction(
            ability="thesis-ai-bridge/apply-acf-model",
            parameters={"content_types": cpt_models},
            rationale="Apply the Architect's structured content model",
        ))

    needs_form = any(s.section_type == "booking" for p in experience_spec.pages for s in p.section_specs)
    cf7_planned_or_active = any(p.plugin_slug == "contact-form-7" for p in app_spec.plugin_plan) or bool(snapshot.plugin_state("contact-form-7") and snapshot.plugin_state("contact-form-7").get("active"))
    if needs_form and cf7_planned_or_active:
        actions.append(BuildAction(
            ability="thesis-ai-bridge/ensure-contact-form",
            parameters={"title": "AI Contact"},
            rationale="Create the reusable booking/contact form",
        ))

    exp_by_slug = {p.page_slug: p for p in experience_spec.pages}
    for page in app_spec.pages:
        exp = exp_by_slug.get(page.slug)
        if exp is None:
            continue
        if renderer in {"elementor", "auto"}:
            actions.append(BuildAction(
                ability="thesis-ai-bridge/elementor-ensure-draft-page",
                parameters={
                    "title": page.name,
                    "slug": page.slug,
                    "elements": compile_elementor_page(exp, experience_spec.design_system, snapshot.media, live_catalog=bool(snapshot.commerce.get("published_products", 0)), product_names=explicitly_named_demo_products(user_request)),
                    "settings": {"hide_title": "yes", "page_layout": "elementor_full_width"},
                },
                rationale=f"Render {page.name} from the shared component library",
            ))
        else:
            actions.append(BuildAction(
                ability="thesis-ai-bridge/ensure-draft-page",
                parameters={"title": page.name, "slug": page.slug, "content": compile_gutenberg_page(exp)},
                rationale=f"Render {page.name} as editable Gutenberg blocks",
            ))
        actions.append(BuildAction(
            ability="thesis-ai-bridge/set-page-seo",
            parameters={"slug": page.slug, "seo_title": exp.seo.title, "meta_description": exp.seo.meta_description},
            rationale=f"Apply SEO metadata for {page.name}",
        ))

    actions.extend([
        BuildAction(
            ability="thesis-ai-bridge/apply-site-design",
            parameters={
                "primary": experience_spec.design_system.primary,
                "accent": experience_spec.design_system.accent,
                "background": experience_spec.design_system.background,
                "surface": experience_spec.design_system.surface,
                "text": experience_spec.design_system.text,
                "muted": experience_spec.design_system.muted,
                "heading_font": experience_spec.design_system.heading_font,
                "body_font": experience_spec.design_system.body_font,
                "container_width": experience_spec.design_system.container_width,
                "radius": experience_spec.design_system.radius,
            },
            rationale="Apply the shared DesignSystem consistently to the WordPress front end",
        ),
        BuildAction(
            ability="thesis-ai-bridge/update-site-identity",
            parameters={"site_title": app_spec.site_title, "tagline": app_spec.tagline},
            rationale="Apply site identity from the architecture",
        ),
        BuildAction(
            ability="thesis-ai-bridge/ensure-navigation-menu",
            parameters={"menu_name": "AI Primary", "page_slugs": [p.slug for p in app_spec.pages], "assign_primary": True},
            rationale="Create a coherent primary navigation",
        ),
        BuildAction(
            ability="thesis-ai-bridge/set-homepage-by-slug",
            parameters={"slug": "home"},
            rationale="Set the generated Home page as static homepage",
        ),
    ])
    return BuildPlan(actions=actions)


def merge_advisory_actions(baseline: BuildPlan, proposed: BuildPlan) -> BuildPlan:
    allowed = {
        "thesis-ai-bridge/configure-woocommerce",
        "thesis-ai-bridge/apply-acf-model",
        "thesis-ai-bridge/ensure-contact-form",
    }
    actions = list(baseline.actions)
    seen = {(a.ability, json.dumps(a.parameters, sort_keys=True, ensure_ascii=False)) for a in actions}
    for action in proposed.actions:
        key = (action.ability, json.dumps(action.parameters, sort_keys=True, ensure_ascii=False))
        if action.ability in allowed and key not in seen:
            actions.append(action)
            seen.add(key)
    return BuildPlan(actions=actions)


# ---------- deterministic mock specialist system ----------


class MockAgentRuntime(AgentRuntime):
    async def orchestrate(self, user_request: str, renderer: Renderer) -> ProjectBrief:
        lower = user_request.lower()
        pages = ["Головна", "Про нас", "Контакти"]
        if "послуг" in lower or "стомат" in lower or "service" in lower:
            pages.insert(1, "Послуги")
        if "лікар" in lower or "команд" in lower or "team" in lower:
            pages.insert(-1, "Лікарі")
        if "запис" in lower or "booking" in lower:
            pages.append("Запис")
        requirements = ["seo", "navigation"]
        if renderer in {"elementor", "auto"}:
            requirements.append("page_builder_elementor")
        if "запис" in lower or "форма" in lower:
            requirements.append("forms")
        if any(x in lower for x in ["магазин", "woocommerce", "shop", "store"]):
            requirements.append("ecommerce")
        return ProjectBrief(
            site_type="dental_clinic" if "стомат" in lower else ("ecommerce" if "ecommerce" in requirements else "business_website"),
            language="uk",
            primary_goal="Отримувати цільові звернення з сайту",
            secondary_goals=["Пояснити послуги", "Побудувати довіру"],
            audiences=["Потенційні клієнти"],
            tone="professional, clear, trustworthy",
            renderer=renderer,
            requested_pages=pages,
            requirements=requirements,
            known_facts={},
            missing_facts=["Адреса", "Телефон", "Імена фахівців", "Ціни"],
            constraints=["Не вигадувати бізнес-факти", "Усі сторінки залишаються draft"],
        )

    async def architect(self, brief: ProjectBrief, site_summary: dict[str, Any]) -> ArchitectureBundle:
        slug_map = {
            "Головна": "home", "Послуги": "services", "Лікарі": "doctors", "Про нас": "about",
            "Про клініку": "about", "Магазин": "shop", "Контакти": "contact", "Запис": "booking", "Блог": "blog",
        }
        pages: list[PageIntent] = []
        for name in brief.requested_pages:
            slug = slug_map.get(name, _canonical_slug(name))
            purpose = {
                "home": "Пояснити цінність клініки, сформувати довіру та привести до запису",
                "services": "Допомогти зрозуміти напрямки допомоги та перейти до запису",
                "doctors": "Пояснити підхід команди без вигадування персональних даних",
                "about": "Розкрити принципи роботи, досвід взаємодії та цінності",
                "contact": "Дати простий шлях до контакту й наступної дії",
                "booking": "Зменшити friction до звернення через форму",
            }.get(slug, f"Пояснити роль сторінки {name} у шляху користувача")
            cta = "Записатися на прийом" if "booking" in brief.requirements or "forms" in brief.requirements else "Зв’язатися"
            cta_url = "/booking/" if "Запис" in brief.requested_pages else "/contact/"
            sections = {
                "home": ["hero", "services", "benefits", "trust", "team", "cta"],
                "services": ["hero", "services", "process", "faq", "cta"],
                "doctors": ["hero", "team", "trust", "cta"],
                "about": ["hero", "content", "benefits", "process", "cta"],
                "contact": ["hero", "contact", "booking"],
                "booking": ["hero", "booking", "faq"],
            }.get(slug, ["hero", "content", "cta"])
            pages.append(PageIntent(name=name, slug=slug, purpose=purpose, search_intent="informational / commercial", primary_cta=cta, primary_cta_url=cta_url, section_goals=sections))
        capabilities = [CapabilityRequirement(capability=x, reason=f"Requested/derived requirement: {x}") for x in brief.requirements]
        matrix = [ContentMatrixRow(
            page_slug=p.slug,
            page_goal=p.purpose,
            search_intent=p.search_intent,
            primary_cta=p.primary_cta,
            key_messages=[p.purpose, "Чіткий наступний крок", "Не вигадувати непідтверджені факти"],
            internal_links=[x.slug for x in pages if x.slug != p.slug][:3],
        ) for p in pages]
        return ArchitectureBundle(
            site_title="Стоматологічна клініка" if brief.site_type == "dental_clinic" else _guess_title(" ".join(brief.requested_pages) + " " + brief.site_type),
            tagline="Турбота, зрозумілий підхід і зручний запис" if brief.site_type == "dental_clinic" else "Сучасний підхід і зрозумілий сервіс",
            theme_slug="hello-elementor",
            pages=pages,
            capabilities=capabilities,
            content_matrix=matrix,
            security_requirements=["least privilege", "approved dependencies only", "draft-first"],
            performance_requirements=["avoid unnecessary plugins", "responsive component library"],
        )

    async def design(self, brief: ProjectBrief, architecture: ArchitectureBundle) -> ExperienceSpec:
        matrix = {m.page_slug: m for m in architecture.content_matrix}
        pages: list[PageExperienceSpec] = []
        for page in architecture.pages:
            row = matrix.get(page.slug)
            sections: list[SectionContentSpec] = []
            for section_type in page.section_goals:
                sec = _default_section(brief, page, section_type, row, architecture.site_title)
                if section_type == "services":
                    sec = sec.model_copy(update={"heading": "Допомога відповідно до ваших потреб", "body": "Почніть із напрямку, який найбільше відповідає вашому запиту.", "items": ["Профілактика — регулярна турбота та раннє виявлення проблем", "Лікування — зрозумілий план і поетапний підхід", "Естетика — рішення з фокусом на природний результат"]})
                elif section_type == "benefits":
                    sec = sec.model_copy(update={"heading": "Комфортний шлях від першого звернення", "items": ["Зрозуміла комунікація — пояснюємо наступні кроки простою мовою", "Сучасний підхід — фокус на точності та комфорті", "Зручний запис — швидкий спосіб залишити заявку онлайн"]})
                elif section_type == "trust":
                    sec = sec.model_copy(update={"heading": "Довіра починається з прозорості", "body": "На сайті немає вигаданих цифр чи обіцянок — конкретні факти можна додати після генерації.", "items": ["Чіткі рекомендації", "Послідовний процес", "Увага до досвіду пацієнта"]})
                elif section_type == "team":
                    sec = sec.model_copy(update={"heading": "Команда клініки", "body": "Додайте реальні профілі лікарів у Elementor після генерації або через структуровані поля.", "items": ["Профіль лікаря — спеціалізація та підхід", "Профіль лікаря — досвід, який ви підтвердите", "Профіль лікаря — напрямки консультацій"]})
                elif section_type == "faq":
                    sec = sec.model_copy(update={"heading": "Перед візитом", "items": ["Як записатися? — Залиште заявку через форму або скористайтеся контактами клініки.", "Що підготувати? — Опишіть основний запит, щоб команда могла зорієнтувати вас щодо наступного кроку.", "Чи можна уточнити деталі? — Так, контактний блок призначений саме для цього."]})
                sections.append(sec)
            pages.append(PageExperienceSpec(
                page_name=page.name,
                page_slug=page.slug,
                page_goal=page.purpose,
                sections=page.section_goals,
                section_specs=sections,
                content_guidance=[page.purpose, "Не вигадувати непідтверджені факти"],
                responsive_notes=["Mobile-first stacking", "Cards stack to one column"],
                accessibility_notes=["Exactly one H1", "Meaningful CTA labels"],
                seo=SeoSpec(
                    slug="/" if page.slug == "home" else f"/{page.slug}/",
                    title=f"{page.name} | {architecture.site_title}",
                    meta_description=page.purpose[:150],
                    h1=page.name,
                    internal_link_targets=["/" if x == "home" else f"/{x}/" for x in (row.internal_links if row else [])],
                    schema_types=["WebPage"],
                ),
            ))
        return ExperienceSpec(
            design_direction="Modern clinical: spacious, trustworthy, minimal, conversion-oriented",
            design_system=DesignSystem(primary="#174E72", accent="#3AA6C9", background="#FFFFFF", surface="#F4F8FB", text="#102235", muted="#5A6B7C", radius=18),
            component_rules=["One shared design system", "Use deterministic component library", "One main CTA hierarchy"],
            pages=pages,
        )

    async def build(self, implementation_manifest: dict[str, Any]) -> BuildPlan:
        return BuildPlan(actions=[])

    async def quality(self, qa_evidence: dict[str, Any]) -> QualityReport:
        issues: list[QualityIssue] = []
        for item in qa_evidence.get("deterministic_issues", []):
            try:
                issues.append(QualityIssue.model_validate(item))
            except Exception:
                continue
        return QualityReport(
            passed=not issues,
            summary="Deterministic + semantic QA passed." if not issues else "QA found issues that require bounded repair.",
            checks_performed=["requirements", "page inventory", "capabilities", "CTA/internal link coherence", "policy"],
            issues=issues,
        )


# ---------- OpenAI runtime with per-agent routing and hard budgets ----------


TModel = TypeVar("TModel", bound=BaseModel)


def _extract_json_value(text: str) -> Any:
    candidate = (text or "").strip()
    if not candidate:
        raise ValueError("Agent returned an empty response")
    if candidate.startswith("```"):
        lines = candidate.splitlines()[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        candidate = "\n".join(lines).strip()
        if candidate.lower().startswith("json\n"):
            candidate = candidate[5:].lstrip()
    decoder = json.JSONDecoder()
    try:
        value, idx = decoder.raw_decode(candidate)
        if not candidate[idx:].strip():
            return value
    except json.JSONDecodeError:
        pass
    for i, ch in enumerate(candidate):
        if ch not in "{[":
            continue
        try:
            value, _ = decoder.raw_decode(candidate[i:])
            return value
        except json.JSONDecodeError:
            continue
    raise ValueError("Agent did not return valid JSON")


def _validate_agent_json(text: str, output_model: type[TModel]) -> TModel:
    return output_model.model_validate(_extract_json_value(text))


def _compact_schema(model: type[BaseModel]) -> str:
    schema = model.model_json_schema()

    def clean(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: clean(v) for k, v in value.items() if k not in {"title", "description", "default", "examples"}}
        if isinstance(value, list):
            return [clean(v) for v in value]
        return value

    return json.dumps(clean(schema), ensure_ascii=False, separators=(",", ":"))


HINTS: dict[str, str] = {
    "ProjectBrief": "Keys: site_type, language, primary_goal, secondary_goals[], audiences[], tone, renderer, requested_pages[], requirements[], known_facts{}, missing_facts[], constraints[].",
    "ArchitectureBundle": "Keys: site_title, tagline, theme_slug, pages[{name,slug,purpose,search_intent,primary_cta,primary_cta_url,section_goals[]}], capabilities[{capability,reason,priority}], content_types[], content_matrix[{page_slug,page_goal,search_intent,primary_cta,secondary_cta,key_messages[],internal_links[]}], security_requirements[], performance_requirements[].",
    "ExperienceSpec": "Keys: design_direction, design_system{primary,accent,background,surface,text,muted,heading_font,body_font,container_width,section_spacing,radius}, component_rules[], pages[{page_name,page_slug,page_goal,sections[],section_specs[{section_type,component_key,section_goal,eyebrow,heading,body,items[],cta_label,cta_url,style_variant}],content_guidance[],responsive_notes[],accessibility_notes[],seo{slug,title,meta_description,h1,internal_link_targets[],schema_types[]}}].",
    "BuildPlan": "Keys: actions[{ability,parameters{},rationale}]. Keep actions minimal.",
    "QualityReport": "Keys: passed, summary, checks_performed[], issues[{id,category,severity,description,responsible_agent,suggested_fix}].",
}


class OpenAIAgentRuntime(AgentRuntime):
    def __init__(self, model_router: dict[str, str], budget_limits: BudgetLimits) -> None:
        super().__init__()
        try:
            from agents import Agent
        except ImportError as exc:
            raise RuntimeError("Install dependencies with: pip install -e .") from exc
        self.model_router = model_router
        self.budget = BudgetTracker(budget_limits)
        self.agents = {
            "orchestrator": Agent(name="Orchestrator", instructions=orchestrator_prompt(), model=model_router["orchestrator"]),
            "architect": Agent(name="Architect & Capability", instructions=architect_prompt(), model=model_router["architect"]),
            "design": Agent(name="Design, Content & SEO", instructions=design_prompt(), model=model_router["design"]),
            "builder": Agent(name="WordPress Implementation", instructions=builder_prompt(), model=model_router["builder"]),
            "quality": Agent(name="Quality & Security", instructions=quality_prompt(), model=model_router["quality"]),
            "repair": Agent(name="WordPress Repair Escalation", instructions=repair_prompt(), model=model_router["repair"]),
        }

    def budget_state(self) -> dict[str, Any]:
        return self.budget.state().model_dump(mode="json")

    async def _run_raw(self, key: str, payload: str) -> str:
        from agents import Runner

        self.budget.assert_can_call()
        agent = self.agents[key]
        model = self.model_router[key]
        # Specialists have no tools in v0.7 planning, therefore max_turns=2 is a
        # strict safety limit rather than an invitation to long autonomous loops.
        result = await Runner.run(agent, payload, max_turns=2)
        usage = result.context_wrapper.usage
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        requests = int(getattr(usage, "requests", 1) or 1)
        self.budget.record(agent.name, model, requests, input_tokens, output_tokens)
        self.usage = self.budget.usage.model_copy(deep=True)
        output = result.final_output
        return output if isinstance(output, str) else json.dumps(output, ensure_ascii=False, default=str)

    async def _run_typed(self, key: str, payload: dict[str, Any] | str, output_model: type[TModel]) -> TModel:
        payload_text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        hint = HINTS.get(output_model.__name__, f"Return JSON matching {output_model.__name__}.")
        first_prompt = payload_text + "\n\nOUTPUT: one JSON object only. " + hint
        first = await self._run_raw(key, first_prompt)
        try:
            return _validate_agent_json(first, output_model)
        except (ValueError, ValidationError) as exc:
            # One bounded formatter retry; full schema is used only on failure so
            # successful runs do not pay the schema-token tax on every agent.
            correction = {
                "instruction": "Fix only JSON/schema validity. Preserve intended content. Return JSON only.",
                "validation_error": str(exc)[:2500],
                "previous_response": first[:12000],
                "json_schema": _compact_schema(output_model),
            }
            second = await self._run_raw(key, json.dumps(correction, ensure_ascii=False, separators=(",", ":")))
            try:
                return _validate_agent_json(second, output_model)
            except (ValueError, ValidationError) as second_exc:
                raise RuntimeError(f"{self.agents[key].name} returned invalid JSON twice: {second_exc}") from second_exc

    async def orchestrate(self, user_request: str, renderer: Renderer) -> ProjectBrief:
        return await self._run_typed("orchestrator", {"request": user_request, "renderer": renderer}, ProjectBrief)

    async def architect(self, brief: ProjectBrief, site_summary: dict[str, Any]) -> ArchitectureBundle:
        return await self._run_typed("architect", {"project_brief": brief.model_dump(mode="json"), "site_preflight": site_summary}, ArchitectureBundle)

    async def design(self, brief: ProjectBrief, architecture: ArchitectureBundle) -> ExperienceSpec:
        return await self._run_typed("design", {
            "project_brief": brief.model_dump(mode="json"),
            "architecture": architecture.model_dump(mode="json"),
            "instruction": "Create coherent site-wide content and design. Do not repeat upstream JSON in prose.",
        }, ExperienceSpec)

    async def build(self, implementation_manifest: dict[str, Any]) -> BuildPlan:
        return await self._run_typed("builder", implementation_manifest, BuildPlan)

    async def quality(self, qa_evidence: dict[str, Any]) -> QualityReport:
        return await self._run_typed("quality", qa_evidence, QualityReport)

    async def repair(self, repair_evidence: dict[str, Any]) -> BuildPlan:
        return await self._run_typed("repair", repair_evidence, BuildPlan)


def make_agent_runtime(
    mode: str,
    model: str = "gpt-5.6-terra",
    *,
    model_router: dict[str, str] | None = None,
    budget_limits: BudgetLimits | None = None,
) -> AgentRuntime:
    if mode == "openai":
        router = model_router or {
            "orchestrator": model,
            "architect": model,
            "design": model,
            "builder": model,
            "quality": model,
            "repair": model,
        }
        limits = budget_limits or BudgetLimits(max_cost_usd=0.50, max_total_tokens=30_000, max_llm_calls=10)
        return OpenAIAgentRuntime(router, limits)
    return MockAgentRuntime()


# Public helpers used by workflows/tests.
normalize_architecture = _normalize_architecture
make_task_plan = _task_plan_from_brief
