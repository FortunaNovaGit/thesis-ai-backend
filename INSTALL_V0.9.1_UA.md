# Як оновити Thesis AI до v0.9.1

## До початку

Оновлюй **тестовий / staging WordPress**, або зроби резервну копію. Встановлені Elementor, WooCommerce, форми, сторінки та товари **не видаляй**. Перевір, що маєш доступ до існуючого GitHub backend, Render та WordPress Dashboard. Нова версія не змінює секрети й не створює платних OpenAI-запитів під час локальних тестів.

## 1. Backend (Render)

1. Завантаж `thesis-ai-backend-v0.9.1.zip` і розпакуй у локальний каталог свого **існуючого** backend GitHub-репозиторію. Це **оновлення поверх існуючого**, а не новий проєкт.
2. Не копіюй зі старого ZIP `data/backend.key`, SQLite БД, `.env`, `__pycache__`; ZIP v0.9.1 їх не містить. Залиш поточні `BACKEND_TOKEN_SECRET`, `BACKEND_PAIRING_SECRET`, `DATABASE_URL`, `OPENAI_API_KEY` у Render Environment без змін.
3. До push запусти:

   ```bash
   python -m pip install -e '.[dev]'
   python -m compileall -q app
   python -m pytest -q
   ```

4. Переглянь git diff, commit/push у `main` і дочекайся успішного Render deployment.
5. Відкрий поточний Backend `/health`. Очікувана версія **`0.9.1`**, `execution_mode=wordpress_pull`, `editorial_quality_gate=v2_repair`, `generative_design=bounded_elementor_v3`.

Backend ZIP містить папку `plugin/thesis-ai-bridge` **тільки як вихідний код для Git/CI та інтеграційних тестів**. До WordPress встановлюється окремий WordPress Bridge ZIP.

## 2. WordPress Bridge

1. WordPress → Plugins → Add Plugin → Upload Plugin.
2. Вибери `thesis-ai-bridge-v0.9.1.zip` → Install Now → **Replace current with uploaded**.
3. Переконайся, що Plugin Version — **0.9.1**. Не натискай Delete/Uninstall існуючої версії: це може вплинути на конфігурацію pairing.
4. Очисть кеш EasyWP/WordPress, онови WP Dashboard і перевір підключення backend. Якщо є проблема з тимчасовим каталогом `/wp-content/upgrade/`, це окрема проблема дозволів WordPress filesystem, а не API; не встановлюй chmod 777.
5. Пройди Preflight. Не продовжуй при відсутній необхідній ability чи залежності.

## 3. Контрольний запуск

Запусти **одну** 3-сторінкову генерацію на staging: Головна, Магазин, Контакти. Вкажи бренд Fortuna Nova і відомі факти; бажано назви демонстраційних товарів точно в `«...»`. Elementor Free + WooCommerce, українська, draft-first. Вказуй, що **не можна вигадувати** склад, ціни, фото, телефони, доставку та відгуки.

Після завершення перевір:
- `plan` не падає з `name 'candidates' is not defined`;
- немає duplicate_heading / planning_copy або небезпечних CTA;
- наявні Elementor `Edit with Elementor`, індивідуальні редаговані заголовки/кнопки/контейнери;
- сторінки не перезаписують чужий published `shop`;
- мобільні/десктопні прев'ю не мають overflow/overlap; перевір також розмірені відступи та контраст;
- невідомі факти не вставляються в публічний контент; товари, коли запитані, — **WooCommerce draft**;
- без реальних фото дизайн може бути абстрактним: це не еквівалент повного Media Pipeline.

У разі збою збережи лише **санітизовані** error log, job id, назву помилки і скріншот. Не передавай токен або DATABASE_URL.

## 4. Окремі синтетичні Visual QA

За наявності встановленого `playwright` та Chromium за `/usr/bin/chromium`:

```bash
python qa/generative_layout_smoke.py
python qa/v091_primitives_smoke.py
```

Ці перевірки **не здійснюють мережевих запитів** і **не запускають OpenAI API**. Це не заміна E2E на живому WordPress.
