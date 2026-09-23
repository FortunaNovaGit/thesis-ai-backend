# AI Website Builder v0.3 — простий старт

## Варіант А — перевірити plugin прямо зараз без backend

1. WordPress → **Plugins → Add New Plugin → Upload Plugin**.
2. Завантаж `thesis-ai-bridge-v0.3.zip`.
3. Activate.
4. Відкрий **AI Website Builder** у лівому меню.
5. Опиши сайт.
6. Натисни **Спробувати локальне демо**.

Plugin створить тільки draft Gutenberg-сторінки. Нічого автоматично не публікується.

> Local Demo перевіряє Bridge/execution layer, але не запускає 5 AI-агентів.

---

## Варіант Б — реальний multi-agent flow

Backend розгортається **один раз нами**, а не кожним WordPress-користувачем.

### 1. Розгорнути backend

На VPS / cloud host:

```bash
cp .env.example .env
docker compose up -d --build
```

Спочатку лишаємо:

```env
AGENT_MODE=mock
```

Так ми тестуємо реальний WordPress execution без витрат на LLM.

Backend має бути доступний через HTTPS, наприклад:

```text
https://ai-builder.example.com
```

### 2. WordPress

В **AI Website Builder**:

1. Розкрий **Advanced: адреса backend для prototype**.
2. Один раз встав backend URL.
3. Натисни **Підключити AI Builder**.

Все інше plugin зробить сам:

- створить service user;
- створить Application Password;
- перевірить backend;
- збереже connection.

### 3. Створити сайт

Введи, наприклад:

```text
Створи сучасний сайт стоматології українською мовою.
Потрібні Головна, Послуги, Лікарі, Про нас, Контакти та запис.
Сайт має бути редагованим через Gutenberg, responsive, SEO-friendly і доступним.
```

Натисни **Створити сайт**.

Після завершення plugin покаже draft-сторінки та Quality summary.

---

## Чого більше НЕ треба робити WordPress-користувачу

Не потрібно вручну:

- створювати AI user;
- створювати Application Password;
- копіювати credentials;
- ставити Python;
- створювати `.env`;
- запускати CLI;
- мати SSH;
- мати WP-CLI.

Це головна зміна v0.3.
