# Оновлення Thesis AI до v0.10.0 (staging preview)

## Перед установленням

- Створи резервну копію тестового WordPress і окремо зафіксуй commit поточного backend. **Не застосовуй відразу до робочого магазину.**
- Не змінюй `DATABASE_URL`, `BACKEND_TOKEN_SECRET`, `BACKEND_PAIRING_SECRET`, `OPENAI_API_KEY` або пароль адміністратора. Жодних секретів у Git.
- Новий Visual Composer працює із WordPress Bridge v0.10.0; оновлюємо **спочатку backend, потім плагін**.

## Backend / Render

1. Розпакуй `thesis-ai-backend-v0.10.0.zip` локально. Вміст архіву — **корінь Python-репозиторію**, не додаткова папка `backend`.
2. Наклади його файли поверх існуючого GitHub-репозиторію (збережи власні несекретні зміни; порівняй diff). Не перенось `.env` чи secrets у репозиторій.
3. Локально: `python -m pip install -e '.[dev]'` та `python -m pytest -q`; за потреби перевір PHP/JS плагіна.
4. Зроби commit, push; після Render deployment відкрий `/health`: перевір `version: 0.10.0` та `visual_composer: bounded_hero_scenes_v1`.
5. Якщо Render падає — відкотись до попереднього commit без заміни секретів.

## WordPress Bridge

1. WordPress Admin → Plugins → Add New → Upload Plugin → обери **`thesis-ai-bridge-v0.10.0.zip`**.
2. Натисни **Replace current with uploaded**. Не роби Delete/Uninstall чинного плагіна: можна втратити налаштування.
3. Очисть кеш (у тому числі CDN, якщо застосовується), перевір підключення й Preflight.
4. Заповни основний промпт. У необов'язковому брифі обери **Головне фото для Hero** з WP Media Library. Для колажу можеш обрати **Друге фото для Hero-колажу**. Не завантажуй випадкові фото товарів, які не належать бренду.
5. Тестуй три сторінки: Головна, Магазин, Контакти, без автоматичної публікації. Відкрий кожну в Elementor; перевір, що текст, CTA та обидва зображення редагуються як окремі елементи.

## Як працює вибір сцени

Creative Director тепер може вибрати `editorial`, `cinematic`, `collage`, `poster` або `typographic` Hero. Якщо необхідних фото немає, система безпечно переходить до композиції з одним зображенням чи типографікою. AI не отримує доступ до виконання довільного CSS, JS, HTML або довільних URL.

## Офлайн-перевірка дизайну (за бажанням розробника)

```bash
python -m pytest -q
python -m pip install playwright
python -m playwright install chromium
python qa/visual_composer_smoke.py /tmp/thesis-hero-qa
```

У середовищах з уже встановленим Chromium можна встановити `CHROMIUM_PATH=/usr/bin/chromium` (або вказати фактичний шлях). Скрипт використовує **синтетичний** HTML, а не підключається до WordPress.

## Обмеження

Нова версія — перший реалізований Hero Visual Composer, а не завершена автономна система професійного дизайну. Media Pipeline, Elementor V4/MCP, live visual repair і повноцінні WooCommerce archives не інтегровані. Не називай build успішним лише тому, що JSON пройшов Pydantic; потрібен фактичний перегляд сторінки.
