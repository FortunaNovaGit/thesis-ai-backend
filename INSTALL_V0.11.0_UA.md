# Thesis AI v0.11.0 — інструкція оновлення та тестування

## 0. Передумови
- Остання встановлена збірка **backend/Bridge v0.10.0**; якщо інша — спочатку звірити сумісність.
- **Staging WordPress**, Elementor Free, стабільний Render backend (один web worker) + PostgreSQL.
- Резервна копія WordPress і медіабібліотеки. Ніякого видалення WooCommerce, сторінок або поточного Bridge.
- Доступ до Render Environment, GitHub і адмінки WordPress.

## 1. Оновлення backend
1. Завантаж `thesis-ai-backend-v0.11.0.zip`.
2. Розпакуй його поверх **вихідних файлів** бекенд-репозиторію `FortunaNovaGit/thesis-ai-backend`, переглянь git diff, зроби commit/push.
3. Дочекайся успішного Render deployment та перевір `https://<your-backend>/health`. Має бути `version=0.11.0`, `media_pipeline=opt_in_ai_concepts_3_assets_v1`.
4. **Не змінюй** `BACKEND_TOKEN_SECRET`, `DATABASE_URL` та `BACKEND_PAIRING_SECRET`. Новий ZIP не містить ключів і файлів `data/backend.key`/`data/jobs-*.sqlite3`.
5. Для **першого безплатного smoke-тесту** залиш `ENABLE_IMAGE_GENERATION=false`.
6. Коли готовий дозволити платну генерацію, у Render Environment встанови:

```env
ENABLE_IMAGE_GENERATION=true
OPENAI_IMAGE_MODEL=gpt-image-2.5-flare
MAX_MEDIA_JOBS_PER_SITE_DAY=2
OPENAI_API_KEY=<your existing private API key>
DATABASE_URL=<your existing Render PostgreSQL Internal URL>
BACKEND_TOKEN_SECRET=<your unchanged stable secret>
```

Перевір `/health`: `image_generation_ready=true`, `job_store=postgresql`. Якщо model недоступна для акаунта — Images API поверне помилку; не потрібно повторювати багаторазово. **API-ключ не вводь у WordPress і не надсилай у чат**.

## 2. Оновлення WordPress Bridge
1. Завантаж `thesis-ai-bridge-v0.11.0.zip`.
2. WordPress → Plugins → Add Plugin → Upload Plugin → ZIP → **Replace current with uploaded**.
3. Не використовуй Delete / Uninstall (налаштування можуть бути очищені).
4. Очисть кеш WordPress/CDN, перевір що plugin і `/health` мають v0.11.0; зроби Preflight.
5. У брифі відкрий новий блок **«AI-зображення для сайту»**.

## 3. Перший тест без витрат на зображення
- Обери «Лише власні / наявні фотографії». Запусти невеликий 3-page Fortuna Nova build.
- Перевір, що старі сценарії працюють як v0.10.0, а немає повторних заголовків та JSON error.

## 4. Тест із платними AI-концептами (тільки staging)
1. Переконайся, що `image_generation_ready=true`, PostgreSQL працює, WordPress може записувати `wp-content/uploads` і обробляти WebP.
2. Обери «Дозволяю платну AI-генерацію ілюстративних зображень». За бажанням вибери власне Hero-фото (тоді воно матиме пріоритет).
3. Використай короткий промпт: «Створи преміальний український магазин шоколадних цукерок Fortuna Nova: Головна, Магазин і Контакти. Продуманий editorial дизайн, WooCommerce, без вигаданих цін, товарних фото та адрес. Сторінки — чернетки.»
4. Build: `planning` → `media_generation` → локальне завантаження WebP → recompile-media → `local_execution` → `verification`.
5. WordPress Media Library: перевір наявність завантажених AI-концептів і підпису «Ілюстративне AI-зображення».
6. Відкрий Elementor Home: Hero має бути справжнім Image widget, а зображення Story/Collection — окремими image widgets. Спробуй змінити фото й перевір мобільну версію.
7. Відкрий WooCommerce Draft products — **фото з Media Pipeline не повинні бути прив'язані як справжні product photos**.
8. Зніми реальні desktop/mobile скриншоти, перевір тексти, макети, контраст, CTA, розміри/кроп і фактичну кількість платних image jobs.

## 5. Діагностика
- `Image generation is not enabled`: увімкни `ENABLE_IMAGE_GENERATION=true`, не запускай Build до `/health image_generation_ready=true`.
- `Daily image generation quota reached`: два media jobs на сайт за UTC-добу за замовчуванням; наступний build роби без генерації або після скидання ліміту.
- `Unsupported ... model` / HTTP 400: перевір `OPENAI_IMAGE_MODEL` і доступ до потрібної моделі у своєму API-акаунті.
- `image invalid` / `dimensions`: WordPress відхилив пошкоджений/неправильний WebP; перевір WP PHP/WebP image support.
- `filesystem`: перевір права на uploads/temp і діагностику WP; **не встановлюй chmod 777**.
- `Render worker restarted during generation`: job не буде повторено автоматично, щоб не списати кошти двічі; перевір лог і за потреби запусти нову контрольовану збірку.
- `recompile-media` 409: WP не підтвердив attachment для кожної згенерованої ролі; перевір медіатеку, meta і лог Bridge.
- Якщо Elementor показує порожню секцію, перевір draft preview / cache та реальну структуру image widget у Elementor editor.

## 6. Чесні межі
- Не існує гарантії wow-дизайну без реального візуального QA. Це **перша інтегрована media-версія**, а не production-ready реліз.
- Ціна image API залежить від обраної моделі, якості, формату та розміру; 1–3 картинки коштуватимуть додатково. **MAX_BUILD_COST_USD не контролює цю частину**. Рекомендуємо тестувати не більше одного платного build на початку.
- WebP-concepts — це editorial visuals, **не точні фото реальних товарів**. Додай реальні товарні фото окремо перед публікацією.
- Не запускай у production без резервної копії та перевірки Elementor/WordPress E2E.

## 7. Локальні команди для розробника
```bash
python -m pytest -q
python -m compileall -q app
node --check plugin/thesis-ai-bridge/assets/admin.js
php -d zend.assertions=1 -d assert.exception=1 plugin/thesis-ai-bridge/tests/brief_smoke.php
```

Після розпакування ZIP Bridge встановлюється **тільки** до WordPress, вкладена в backend папка `plugin/` залишається зручним джерелом для offline integration tests.
