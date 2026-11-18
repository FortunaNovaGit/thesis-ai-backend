# Thesis AI v0.12.0 — інструкція оновлення та тестування

## 0. Передумови
- Встановлена збірка **backend/Bridge v0.11.0**.
- Staging WordPress, Elementor Free, Render backend + PostgreSQL.
- Резервна копія WordPress. Нічого не видаляти (WooCommerce, сторінки, поточний Bridge).

## 1. Оновлення backend
1. Розпакуй `thesis-ai-backend-v0.12.0.zip` поверх вихідних файлів репозиторію `thesis-ai-backend`, переглянь `git diff`, commit/push.
2. Дочекайся Render deploy, відкрий `https://<your-backend>/health`. Має бути `version=0.12.0` і `features.rich_sections=rich_visual_system_v1`.
3. **Не змінюй** `BACKEND_TOKEN_SECRET`, `DATABASE_URL`, `BACKEND_PAIRING_SECRET`, `OPENAI_API_KEY`. Нових змінних середовища немає.

## 2. Оновлення WordPress Bridge
1. WordPress → Plugins → Add Plugin → Upload Plugin → `thesis-ai-bridge-v0.12.0.zip` → **Replace current with uploaded**.
2. Не роби Delete / Uninstall.
3. Очисть кеш WordPress/CDN. Перевір версію плагіна 0.12.0 і зроби Preflight.

> Оновлюй **обидва** компоненти. Bridge 0.11 відкидає нові налаштування мовчки — сайт збудується, але без нового вигляду.

## 3. Перший тест (без платних зображень)
1. Бриф: «Лише власні / наявні фотографії».
2. Промпт (3 сторінки Fortuna Nova з handoff-документа) — один build.
3. Відкрий **Preview** чернетки Головної та перевір:
   - Hero: великий заголовок з акцентним курсивом, дві кнопки (якщо AI запропонував другу дію), рядок пунктів з іконками;
   - різні типи секцій: bento / нумерований список / timeline / FAQ, що розкривається / темна фінальна CTA;
   - чергування світлих фонів, без трьох однакових смуг поспіль;
   - шрифти з кирилицею (жодного «системного» шрифту в заголовках);
   - mobile (≈390 px): немає горизонтального скролу, кнопки на всю ширину.
4. Відкрий сторінку в **Elementor**: кожен заголовок, текст, кнопка, іконка редагуються окремо; зміни кольору/тексту застосовуються.
5. Перевір: FAQ у редакторі — Text Editor з `<details>`; клік по питанню розкриває відповідь на сайті.

## 4. Живий візуальний аудит (опційно)
```bash
python qa/visual_audit.py --url 'https://<staging-preview-url>/' --output qa/evidence
```
Скриншоти знімаються з `reduced_motion=reduce`, щоб scroll-анімації не ховали нижні блоки.

## 5. Локальний синтетичний прев'ю (без WordPress/API)
```bash
python qa/rich_preview.py qa/rich-evidence --plugin plugin/thesis-ai-bridge --direction warm
python qa/rich_preview.py qa/rich-evidence --plugin plugin/thesis-ai-bridge --direction minimal --tag minimal
```
Потрібні `playwright` і Chromium. Це синтетичний рендер, не заміна живого Elementor.

## 6. Діагностика
- Іконки не видно: у Elementor → Settings → Advanced переконайся, що Font Awesome 5 не вимкнено (Load Font Awesome 4 Support / Inline Font Icons можуть змінювати розмітку — перевір на staging).
- FAQ без розкриття: перевір, що `<details>` збережено в Text Editor (WordPress KSES). Якщо вирізано — повідом, перейдемо на нативний Elementor Accordion.
- Анімації не потрібні: системне налаштування «Зменшити рух» вимикає їх автоматично.
- Старі сторінки (збудовані 0.11 і раніше) зберігають попередній вигляд — для нового треба перебудувати сторінку.
