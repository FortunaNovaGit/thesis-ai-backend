# Render — оновлення до v0.5.3

Для вже створеного Web Service нічого нового створювати не треба.

1. Push backend v0.5.3 у `main`.
2. Render -> Environment.
3. Встановіть:
   - `AGENT_MODE=auto`
   - `OPENAI_MODEL=gpt-5.6-terra`
   - `BACKEND_TOKEN_SECRET` — один раз натиснути **Generate**; надалі не змінювати.
   - `OPENAI_API_KEY` — додати як secret, коли готові тестувати real LLM agents.
   - `AUTO_APPROVE_MEDIUM_RISK=true`
   - `ALLOW_INSECURE_WORDPRESS=false`
   - `ALLOW_PRIVATE_WORDPRESS=false`
4. Deploy latest commit.
5. Відкрити `/health`.

### Важливо про connection token

v0.4 зберігав connection state на ephemeral Render filesystem. v0.5 використовує self-contained encrypted token. Backend більше не потребує локального `sites.json` для WordPress connection.

Після першого переходу на v0.5 та встановлення `BACKEND_TOKEN_SECRET` старий token не декодується. У WordPress один раз натисніть `Відключити`, потім `Підключити AI Builder`. Наступні redeploy при незмінному secret connection не повинні скидати.

### Free Render limitation

Файли `runs/*.json` усе ще є локальною debug-телеметрією і можуть зникати після redeploy. Це не впливає на connection. Persistent research history буде винесено в PostgreSQL у наступній data-layer ітерації.
