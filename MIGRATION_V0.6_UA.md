# Міграція з v0.5.5 на v0.6.0

1. **Не видаляй Elementor, Hello Elementor, створені сторінки або старий Bridge.**
2. Розпакуй backend v0.6.0 і заміни файли у GitHub repo. Commit → Push.
3. У Render **не змінюй `BACKEND_TOKEN_SECRET`**.
4. Додай/перевір:
   - `AGENT_MODE=auto`
   - `OPENAI_MODEL=gpt-5.6-sol`
   - `OPENAI_API_KEY=<secret>`
   - `AUTO_APPROVE_MEDIUM_RISK=true`
   - `MAX_REPAIR_LOOPS=2`
5. Дочекайся deploy і перевір `/health` → `version: 0.6.0`, `execution_mode: wordpress_pull`.
6. WordPress → Plugins → Add New → Upload Plugin → `thesis-ai-bridge-v0.6.0.zip` → **Replace current with uploaded**.
7. Відкрий AI Website Builder → **Перевірити з’єднання**.
8. Якщо бачиш `agent_mode: mock`, OpenAI API key у Render ще не підхопився.
9. Запусти той самий тестовий prompt.

## Що принципово змінилося

Backend більше не робить жодного build-time REST виклику до EasyWP. Тому старі `WORDPRESS_RATE_LIMIT_*`, `WORDPRESS_BATCH_SIZE` та інші transport variables можна видалити — v0.6 їх не використовує в основному flow.

WordPress сам виконує approved actions локально, по одній на короткий AJAX request. Якщо закрити сторінку — state зберігається; після повернення polling продовжить build.
