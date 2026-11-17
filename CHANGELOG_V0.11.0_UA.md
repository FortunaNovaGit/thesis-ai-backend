# Thesis AI v0.11.0 — Media Pipeline (staging release)

**Дата:** 11 листопада 2026 року. **База:** Backend + Bridge v0.10.0.
**Статус:** локально перевірена збірка; не підтверджена реальним EasyWP/Elementor E2E.

## Що реалізовано

### 1. MediaManifest у backend
- Новий `app/media_pipeline.py` формує до **трьох** окремих зображень для головної сторінки: `hero`, `collection`, `story`.
- Джерело ідеї — ProjectBrief, Creative Direction, палітра й зміст конкретних секцій. Усі зображення мають спільний художній напрям.
- Промпти забороняють написи, логотипи, справжніх працівників і видавання концепту за фотографію реального SKU.
- Для простих сайтів генерується лише набір ролей, які мають відповідні секції. Немає вигаданих товарів, цін, складу чи адрес.

### 2. Backend image jobs і захист від подвійних витрат
- Нові модулі: `app/media_store.py`, `app/image_provider.py`.
- Зовнішня генерація через офіційний OpenAI Images API; за замовчуванням модель `gpt-image-2.5-flare`, WebP, `quality=medium`.
- Виклики асинхронні; WordPress не тримає довгий PHP-запит до завершення генерації.
- PostgreSQL зберігає job та тимчасові байти зображень; вони **не вставляються в план JSON**. Після завантаження WordPress є основним сховищем медіафайлів.
- Кожний media job належить конкретному `site_id` і успішному `plan_job_id`. Повторний запуск того самого plan не створює другу платну job. Є добовий ліміт кількості jobs на site (2 за замовчуванням).
- API обмежує три ролі й розмір файлу до 5 MB. Неправильні формати блокуються. За збою Render generation не повторюється автоматично, щоб уникнути повторних списань.
- Нові API: `POST /v2/sites/{site_id}/media-jobs`, `GET /v2/sites/{site_id}/media-jobs/{job_id}`, `GET /v2/sites/{site_id}/media-jobs/{job_id}/assets/{key}`, `POST /v2/sites/{site_id}/plans/{plan_id}/recompile-media`.

### 3. WordPress Bridge
- У брифі додано явний вибір: **лише наявні зображення (default)** або **дозволити платне створення AI-концептів**.
- Перед генерацією перевіряється `/health` backend; якщо image generation не налаштована, build не запускається й текстові API-токени не витрачаються.
- Лише **після успішного Content Quality Gate** план переходить в окремий стан `media_generation`.
- WordPress опитує медіа job, завантажує **по одному** зображенню за короткий WP-Cron-крок, перевіряє MIME/WebP/розміри, виконує `media_handle_sideload()` і записує metadata/alt/caption.
- Не потрібно передавати API-ключ WordPress або дозволяти Render викликати REST WordPress — WordPress сам робить Pull.
- Ілюстративні матеріали маркуються `ai_generated_concept_not_product_photo`; незворотних змін/автопублікації немає.
- Після завантаження бекенд **повторно компілює існуючий перевірений план**, використовуючи зображення зі свіжого WP snapshot — без повторного виклику п'яти текстових агентів.

### 4. Відображення в Elementor
- Нове зображення Hero підставляється у **нативний Elementor Image widget** зі справжнім WP attachment ID.
- Секції каталогу/колекції та історії бренду отримують окремі редакційні image-widgets з CSS-класами `tai-editorial-media-collection`/`tai-editorial-media-story`.
- Згенеровані концепти **не прикріплюються як реальні фото WooCommerce-товарів**.
- Власне Hero-фото користувача має пріоритет. Якщо AI обрав текстовий Hero, але користувач свідомо активував фотогенерацію, адаптер перемикає його на редакційний макет з фото.
- Адаптивні стилі ізольовані `body.thesis-ai-generated`.

## Залишається обмеженням
- Фото реальних товарів/упаковок **не генеруються як достовірні product photos**. Їх потрібно завантажити власнику.
- Виконання image jobs в async tasks підтримує одноворкерне розгортання Render. Для production multiworker потрібна окрема distributed job queue/lease.
- Немає гарантованої відповідності або професійності всіх зображень; немає автоматичного AI Vision Critic або ліцензійного аудиту сторонніх медіа.
- Не перевірено фактичний EasyWP filesystem, WordPress WebP image editor, Elementor UI та з'єднання із платною Images API.
- Витрати на Images API **окремі** від `MAX_BUILD_COST_USD` / текстового бюджету, тому не існує перевіреної жорсткої доларової межі в цьому релізі.
- Потрібна явна перевірка прав використання фінальних ілюстрацій і довірчих продуктних фото перед публікацією.

## Перевірки
- Повний локальний `pytest` (тести без платних OpenAI-запитів).
- PHP syntax lint, WordPress brief smoke, JS syntax.
- Контроль site isolation, idempotency, ролей, WebP транспорт, media recompile без LLM, Elementor media placement, перевага реальних фото, fallback й default-off.
- Живий WordPress E2E **не виконувався**.
