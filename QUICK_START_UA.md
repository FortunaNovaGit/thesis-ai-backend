# Quick Start v0.6.0

## 1. Backend

Замінити файли у GitHub repo backend на v0.6.0 і зробити Commit → Push.

У Render Environment:

```text
AGENT_MODE=auto
OPENAI_MODEL=gpt-5.6-sol
OPENAI_API_KEY=<твій ключ>
BACKEND_TOKEN_SECRET=<залишити існуючий стабільний secret>
AUTO_APPROVE_MEDIUM_RISK=true
MAX_REPAIR_LOOPS=2
```

Старі `WORDPRESS_*RATE_LIMIT*` variables більше не потрібні.

Перевірити:

```text
https://<service>.onrender.com/health
```

Очікується `version: 0.6.0`, `execution_mode: wordpress_pull`.

## 2. WordPress

Upload Plugin → завантажити `thesis-ai-bridge-v0.6.0.zip` → Replace current with uploaded.

Після оновлення зайти в **AI Website Builder** і натиснути **Перевірити з’єднання**.

Якщо статус агентів `mock`, додати OpenAI API key в Render і знову натиснути Check connection.

## 3. Build

Приклад:

> Створи сучасний сайт стоматологічної клініки українською мовою. Потрібні Головна, Послуги, Лікарі, Про нас, Контакти та Запис. Використай Elementor. Потрібна форма запису, сучасний світлий дизайн, синій акцент, SEO та адаптивність.

Flow:

1. WordPress локально робить snapshot.
2. Render запускає 4 planning agents.
3. Policy Engine повертає тільки дозволені actions.
4. WordPress виконує actions локально по одній.
5. WordPress робить новий snapshot.
6. Quality/Security agent перевіряє результат.
7. Якщо потрібно — repair actions повертаються у WordPress і виконуються локально.
8. Після `passed` можна вручну опублікувати drafts.
