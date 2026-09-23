# WordPress Multi-Agent Thesis MVP — v0.3

Це третя версія прототипу магістерської системи: **5 спеціалізованих агентів + deterministic Policy Engine + WordPress Bridge**.

Головна зміна v0.3 — **one-click onboarding для WordPress-користувача**.

## Який UX ми будуємо

Кінцевий користувач не повинен бачити Python, `.env`, Application Password або CLI.

Його сценарій:

1. Встановити plugin `Thesis AI Bridge`.
2. Відкрити **AI Website Builder**.
3. Натиснути **Підключити AI Builder**.
4. Описати сайт природною мовою.
5. Натиснути **Створити сайт**.

У тестовій v0.3 адресу central backend треба один раз вказати у секції **Advanced**, тому що постійного production cloud endpoint ще немає. У фінальному продукті ця адреса буде вбудована в plugin.

---

## 5 агентів

1. **Orchestrator** — декомпозиція задач, залежності, routing, повторні цикли.
2. **Architect & Capability** — сторінки, функції, data model, capabilities, plugin plan.
3. **Design / Content / SEO** — layout, Gutenberg-first design, контент, SEO, accessibility requirements.
4. **WordPress Implementation** — формує BuildPlan і викликає контрольовані WordPress abilities.
5. **Quality & Security** — незалежно оцінює execution evidence і формує QualityReport.

Окремо працює **Policy Engine**. Це не LLM: він детерміновано дозволяє, блокує або вимагає approval для кожної ability.

---

## Архітектура v0.3

```text
WordPress Admin
   │
   │ Install → Connect → Describe → Build
   ▼
Thesis AI Bridge plugin
   │ HTTPS
   ▼
Central Python Backend
   ├─ Orchestrator
   ├─ Architect & Capability
   ├─ Design / Content / SEO
   ├─ WordPress Implementation
   ├─ Quality & Security
   └─ Policy Engine
   │
   │ authenticated REST / Abilities
   ▼
Thesis AI Bridge execution layer
   ▼
WordPress
```

---

## Що автоматизує кнопка Connect

Після явного натискання адміністратором plugin:

- створює окремого технічного WordPress user з роллю `AI Builder`;
- генерує випадковий primary password, який не показується і не передається backend;
- створює окремий WordPress Application Password для інтеграції;
- передає backend тільки site URL, service username та цей Application Password через HTTPS;
- backend одразу перевіряє доступ до Bridge;
- backend шифрує Application Password at rest;
- WordPress зберігає per-site backend token у зашифрованому вигляді;
- при Disconnect Application Password відкликається.

Основний пароль адміністратора WordPress не використовується.

---

## Безпека

Базові правила v0.3:

- dedicated low-privilege `AI Builder` role;
- no SSH;
- no WP-CLI requirement;
- no raw SQL;
- no arbitrary shell;
- no arbitrary filesystem writes;
- default-deny Policy Engine;
- Gutenberg pages створюються як `draft`;
- unknown abilities блокуються;
- plugin management вимкнений за замовчуванням;
- встановлювати можна лише plugins із hard-coded allowlist та WordPress.org;
- оновлення чужих/опублікованих сторінок вимкнене за замовчуванням;
- audit log у Bridge не зберігає page content.

### Risk model

- LOW → автоматичне виконання.
- MEDIUM → залежить від backend policy / налаштувань Bridge.
- HIGH → human approval.
- CRITICAL → block.

---

## WordPress abilities v0.3

```text
thesis-ai-bridge/get-site-info
thesis-ai-bridge/list-pages
thesis-ai-bridge/get-page
thesis-ai-bridge/create-draft-page
thesis-ai-bridge/ensure-draft-page
thesis-ai-bridge/update-page
thesis-ai-bridge/set-homepage
thesis-ai-bridge/list-plugins
thesis-ai-bridge/install-approved-plugin
thesis-ai-bridge/activate-approved-plugin
thesis-ai-bridge/deactivate-approved-plugin
```

Для WordPress 6.9+ plugin також реєструє native Abilities API. Для старішої підтримуваної версії залишається plugin-owned authenticated REST fallback.

---

## Local Demo Mode

Plugin можна встановити і перевірити **без backend**.

На сторінці **AI Website Builder** введи опис сайту і натисни **Спробувати локальне демо**.

Demo:

- створює/оновлює кілька Gutenberg draft pages;
- перевіряє execution layer, permissions та редагованість;
- нічого не публікує.

Важливо: **це не multi-agent run**. UI прямо це позначає. Реальні 5 агентів запускаються тільки після Connect.

---

## Central backend — один раз для всієї системи

Кінцеві WordPress-користувачі його не встановлюють. Backend розгортає власник системи один раз.

### Найпростіший developer start

```bash
cp .env.example .env
docker compose up -d --build
```

API слухає port `8000`.

Для реального WordPress backend повинен бути доступний по **HTTPS**. Розмісти контейнер за HTTPS reverse proxy / cloud endpoint і вкажи цю адресу один раз у Advanced налаштуванні plugin.

### Спочатку без LLM

У `.env`:

```env
AGENT_MODE=mock
```

Тоді WordPress execution буде реальним, а п'ять ролей працюватимуть через deterministic mock runtime. Це корисно для перевірки Bridge і безпеки без API cost.

### Потім із LLM

```env
AGENT_MODE=openai
OPENAI_API_KEY=...
OPENAI_MODEL=...
```

API key зберігається тільки на central backend, а не в WordPress кожного користувача.

---

## Backend API

```text
GET  /health
POST /v1/sites/connect
GET  /v1/sites/{site_id}/check
POST /v1/sites/{site_id}/build
POST /v1/sites/{site_id}/disconnect
```

Connected-site endpoints використовують окремий random bearer token.

Backend credentials store:

- Application Password encrypted with Fernet;
- site bearer token stored only as SHA-256 hash;
- connection endpoint blocks private/loopback/link-local WordPress targets by default to reduce SSRF risk;
- encryption key auto-created in `data/backend.key` for prototype deployment.

Для production ключ треба винести в managed secrets/KMS і використовувати нормальну DB.

---

## Швидка перевірка коду

```bash
python -m pytest -q
find wordpress-plugin/thesis-ai-bridge -name '*.php' -exec php -l {} \;
```

---

## Поточні обмеження v0.3

Це ще не universal AI website builder.

Поки що:

- основний renderer — прості Gutenberg blocks;
- Elementor adapter ще не реалізований;
- ACF execution adapter ще не реалізований;
- WooCommerce plugin install є, але повна store configuration ще попереду;
- browser QA / Playwright ще не підключений;
- visual QA ще не підключений;
- build endpoint поки synchronous;
- approval UX для MEDIUM/HIGH actions буде наступним етапом.

Ми навмисно не позначаємо ці перевірки як виконані без реального evidence.
