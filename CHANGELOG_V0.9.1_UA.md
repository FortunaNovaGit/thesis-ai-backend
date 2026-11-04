# Thesis AI v0.9.1 — Stabilization + compositional design grammar

**Стан:** локально перевірена збірка для staging. Не сертифікований production/wow реліз: live EasyWP, реальною Elementor-редакцією, зображеннями та реальними транзакціями її ще не перевірено.

## Усунуті помилки

1. `name 'candidates' is not defined`: `design_prompt()` містив неекрановані дужки JSON-контракту в Python f-string. Додано тест, який викликає **всі** генератори агентних промптів і створює OpenAI-runtime із підставним (offline) Agent SDK.
2. `reconcile_experience()` більше не замінює нормальні унікальні короткі речення на універсальні абзаци лише через їхню довжину; справжні повторення перевіряються і ремонтуються обмежено; невирішені проблеми блокуються Content Quality Gate.
3. Elementor-компілятор більше не підміняє нормальні заголовки готовими маркетинговими назвами. Страхувальний dedupe залишається для прямого виклику компілятора в обхід gate.
4. Контраст кольору тексту кнопки підбирається з урахуванням світлості AI-обраного фону, а не завжди білий.
5. Сайтова типографіка й навігаційні стилі у Bridge обмежені AI-owned сторінками й WooCommerce Shop, щоб не перефарбовувати сторонні сторінки.

## Нове у дизайн-специфікації

`SectionLayoutSpec` доповнено незалежними контрольованими полями:
`card_presentation=grid|bento|list`, `surface_treatment=canvas|tinted|bordered`,
`content_alignment=start|center`, `visual_treatment=abstract|typography|media`,
`accent_detail=none|rule|index`.

Creative Director обирає значення окремо для кожної секції за її змістом. WordPress отримує лише нативні Elementor `container` + `heading` / `text-editor` / `button` / `shortcode` / `image` widgets з дозволеними CSS-класами; сторонній код та URL картинок не передаються. Створено композиції типографічного Hero без імітації фото, bento-карток, інформативних списків, акцентів і різних фонів. Старі дизайни/плани читаються із безпечними значеннями за замовчуванням.

## Автоматичні перевірки (без OpenAI API)

- **81 Python tests** (`python -m pytest -q`), включно з новими regression tests.
- **22 offline Chromium geometry checks:** 12 старих комбінацій + 10 нових з ширинами від 320 до 1440 px; перевірено overflow, межі Hero/CTA, bento columns.
- PHP lint для `thesis-ai-bridge.php` та файлів `includes/*.php`.
- Backend `python -m compileall -q app`.
- Без секретного файлу `data/backend.key`, SQLite БД, `.env` і cache у новому ZIP.

## Відомі обмеження

- Це **не** повний Media Pipeline. Зображення беруться тільки з реальної медіатеки WordPress; за відсутності фото можна використовувати абстрактні композиції, але вони не замінюють професійну артдирекцію з реальними зображеннями.
- Це Elementor V3 adapter; MCP/V4 не інтегровано.
- Browser checks на синтетичному DOM, **не** live WP E2E. Потрібні staging тест і редагування в Elementor.
- Якість AI-копірайтингу залежить від фактичної моделі, вводу й результату генерації. Немає гарантії, що кожний сайт буде wow або не потребуватиме редактури.
- WooCommerce Shop є системним архівом; AI не змінює його в Elementor. Демонстраційні продукти — тільки чернетки без ціни й вигаданих фактів.
- Security backlog: HMAC всього плану, approvals, rollback та повна multiworker reliability залишаються окремими завданнями.
