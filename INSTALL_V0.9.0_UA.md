# Інструкція оновлення Thesis AI v0.8.5 → v0.9.0

## Передумови

- Робіть це **на staging/тестовому WordPress**; перед оновленням зробіть backup WordPress файлів і БД.
- Є два архіви: `thesis-ai-backend-v0.9.0.zip` і `thesis-ai-bridge-v0.9.0.zip`.
- Нічого не видаляйте з EasyWP / WooCommerce перед тестом. Системну published Shop сторінку не слід перейменовувати чи переводити в draft.
- `BACKEND_TOKEN_SECRET`, `BACKEND_PAIRING_SECRET`, `DATABASE_URL`, `OPENAI_API_KEY` залишити такими, як є. Не додавати їх у Git або архів.

## 1. Backend / GitHub / Render

1. Розпакуйте backend ZIP локально та скопіюйте вміст до **кореня існуючого** `FortunaNovaGit/thesis-ai-backend` (не створюйте вкладену папку `backend` у репозиторії). Збережіть існуючий `.git`, Render settings, секрети та локальні невідстежувані файли.
2. Перед публікацією перевірте локально: `python -m pip install -e '.[dev]'`, далі `AGENT_MODE=mock pytest -q`. Має бути **75 passed**.
3. Зробіть `git add` лише після перегляду diff і `git commit -m "Thesis AI v0.9.0 generative designer foundation"`, `git push origin main`.
4. Перевірте успішність Render deploy. Відкрийте **ваш власний** `https://<render-host>/health`: `version` має бути `0.9.0`, `editorial_quality_gate` → `v2_repair`, `generative_design` → `bounded_elementor_v3`, `execution_mode` → `wordpress_pull`, `durable_jobs` → `true` для PostgreSQL.
5. Для платного творчого запуску потрібен наявний працездатний OpenAI routing/`AGENT_MODE=auto`. Offline mock-тести не витрачають OpenAI API.

## 2. WordPress Bridge

1. У WP Admin відкрийте **Plugins → Add Plugin → Upload Plugin**.
2. Завантажте `thesis-ai-bridge-v0.9.0.zip`, оберіть **Replace current with uploaded**. **Не робіть Delete Plugin** — це може зачепити збережені налаштування.
3. Переконайтесь, що в AI Website Builder відображається **Bridge 0.9.0**, backend підключений та Preflight не показує несумісності.
4. Очистьте cache сторінки/CDN після оновлення CSS. Якщо installer повідомляє `Could not create directory ... wp-content/upgrade`, це проблема запису WordPress — перевірте файлову систему або оновіть код контрольовано через SFTP. Не використовуйте `chmod 777`.

## 3. Безпечний інтеграційний тест

У staging вкажіть короткий prompt:

> Створи сучасний преміальний інтернет-магазин шоколадних цукерок ручної роботи Fortuna Nova українською. Рівно три сторінки: Головна, Магазин (існуючий WooCommerce Shop), Контакти. На Головній — оригінальна композиція Hero, історія, колекції й CTA «Обрати цукерки». Створи draft products «Асорті 16 цукерок» і «Асорті 24 цукерки» без вигаданих цін, складу, алергенів та фото. Не публікуй сторінки чи товари. Elementor Free, адаптивність, меню та SEO. Не повторюй заголовки, не показуй службовий текст.

Перевірте: одна draft Home, редагованість окремих Elementor widgets/containers, Shop лишається WooCommerce-owned published, draft products у WooCommerce, `content_quality.repairs`, відсутність дублювань, фактичні mobile/tablet/desktop скриншоти. Якщо невідомі властивості товару або контакти — **не вигадувати**; їх заповнює власник.

**Критично:** у `AGENT_MODE=auto` **реальний build витрачатиме OpenAI API**. Спершу локальні mock-тести, потім один контрольований staging запуск. Збирайте token usage/time/error & screenshots; не вважайте безпомилковий planning доказом високого візуального рівня.

## 4. Відновлення (rollback)

Якщо staging-тест невдалий: поверніть backend до попереднього Git commit v0.8.5, зробіть Render deploy і завантажте Bridge v0.8.5 через **Replace current with uploaded**; очистіть cache. Секрети, site token і `DATABASE_URL` не змінюйте. Зміни сторінок/товарів відкочуйте тільки із перевіреного backup або AI-owned draft ownership, не видаляйте чужий контент.

## 5. Відомі межі

V4/MCP, Media Pipeline та справжній Playwright QA живих WP-сторінок **не входять у цей release**. 0.9.0 є першим перевіреним кодовим етапом Generative Website Designer, а не фінальним production-ready website generator.
