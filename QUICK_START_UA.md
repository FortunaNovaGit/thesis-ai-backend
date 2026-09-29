# Quick Start — v0.5.2

## 1. Оновити backend у GitHub

Замініть файли репозиторію `thesis-ai-backend` файлами з backend v0.5, Commit і Push. Render зробить auto-deploy.

## 2. Додати Render Environment Variables

Обов'язково:

```text
AGENT_MODE=auto
OPENAI_MODEL=gpt-5.6-terra
BACKEND_TOKEN_SECRET=<натиснути Generate у Render або вставити довгий випадковий secret>
```

Щоб запустити **реальні LLM-агенти**, додайте також:

```text
OPENAI_API_KEY=<ваш API key>
```

Залишити:

```text
AUTO_APPROVE_MEDIUM_RISK=true
ALLOW_INSECURE_WORDPRESS=false
ALLOW_PRIVATE_WORDPRESS=false
```

Після deploy перевірте `/health`. Очікувано:

```json
{
  "status": "ok",
  "version": "0.5.2",
  "agent_mode": "openai",
  "stable_connection_tokens": true
}
```

Без OpenAI key `agent_mode` буде `mock` — це нормально для infrastructure test.

## 3. Оновити WordPress plugin

Upload `thesis-ai-bridge-v0.5.2.zip` поверх поточної версії.

Після першого переходу на stable `BACKEND_TOKEN_SECRET` зробіть один раз:

```text
AI Website Builder -> Відключити -> Підключити AI Builder
```

## 4. Перший real-agent test

Prompt:

```text
Створи сучасний сайт стоматологічної клініки українською мовою.
Потрібні Головна, Послуги, Лікарі, Про нас, Контакти та Запис.
Стиль чистий, сучасний, світлий, з виразним синім акцентом.
Потрібна форма запису. Не вигадуй імена лікарів, адресу, телефон чи інші
факти, яких я не надав.
```

Увімкнено:
- Elementor Free
- auto approved plugins
- auto site setup

Система повинна зробити preflight, повторно використати наявний Elementor, за потреби встановити Contact Form 7 / Hello Elementor, створити Elementor draft pages, SEO metadata, menu/homepage/site identity та виконати structural QA.

## 5. Перевірити і опублікувати

Сторінки лишаються draft. Відкрийте їх через `Elementor`, перевірте результат. Якщо останній build має `passed`, у AI Website Builder з'явиться кнопка:

**Перевірив — опублікувати AI-сторінки**

Це human-in-the-loop publish: агенти самі сторінки не публікують.
