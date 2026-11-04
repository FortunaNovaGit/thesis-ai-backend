# Thesis AI v0.9.3 — Creatively Authored Content Guard + Brief UX

Дата: 04.11.2026. **Статус: кандидат для staging-перевірки, не production-ready / не гарантований «wow»-результат.** База — v0.9.2, без переписування WordPress Pull, Policy Engine, PostgreSQL чи п'яти агентів.

## Причина інциденту v0.9.2

Відповідь `CreativePage` перетворювалася в `ExperienceSpec`, а `reconcile_experience` після цього повторно упорядковував секції за `PageIntent.section_goals`. Коли тип відсутній або повторювався, використовувалися generic fallback-секції, зокрема `generic_headings["hero"] = page.name`, звідки й повтори «Головна», «Магазин», «Контакти». Обробка повторних параграфів іноді підставляла ще один boilerplate. `Content Quality Gate` правильно блокував небажану публікацію. Без сирого payload інциденту не можна стверджувати, що всі дублікати походили саме із reconciler; модель теж могла повторювати текст.

## Що змінено

1. **Explicit generation contract** `creative_page_v093`: новий творчий pipeline зберігає послідовність авторських секцій, заголовки, параграфи, eyebrow і стилі. Старі mock/compatibility path залишили попередню поведінку.
2. **No fallback content on AI pages**: не дописуємо «Головна», беззмістовні картки або фіксовану секцію «Обрані колекції» після роботи Creative Director; повна оригінальна структура має надходити з CreativePage.
3. **Editorial validation BEFORE deployment**: Pydantic перевіряє повторені локальні заголовки/тіла, порожні CTA-посилання, службові інструкції й навігаційні слова замість H1/H2. При schema error — точковий контрактний retry, без довільного шаблона.
4. **Site-wide cross-page review**: при повторенні заголовка або майже однакового body сторінка отримує **один** scoped rewrite у межах наявного LLM budget; після невдалої спроби build блокується, а WordPress залишається незмінним.
5. **Precise diagnostics**: `repeated_body` і `planning_copy` тепер показують справжній `section_index` та першу секцію, з якою виник повтор.
6. **Optional structured brief UI**: зручні поля для бренду, типу сайту, аудиторії, сторінок, очікуваної кількості товарів, дизайнерської підказки, HEX-кольорів, стану медіа та підтверджених фактів; збереження між оновленнями сторінки. Поля не є ліцензією вигадувати товари.
7. **Honest output UI**: показує checklist людської перевірки перед публікацією, не змішує backend QA з реальним Playwright/visual approval.
8. **No fake-photo fallback**: при `visual_treatment=media` без підтвердженого attachment Hero стає типографічним, не вдає реальний товарний знімок.
9. **Regression coverage**: відтворення повторних заголовків «Головна», «Магазин», «Контакти», повторів між сторінками, збереження авторських sections та коректних індексів; без OpenAI API витрат.

## Що не готове

- Перевірений живий OpenAI → Render → EasyWP → Elementor e2e; тест архіву в окремому staging WordPress.
- Full Media Pipeline із ліцензуванням, upload, provenance, alt/crops, товарними фото.
- Керовані AI Elementor Pro/WooCommerce Archive/Product Templates; **Elementor Free стандартно не замінює системний Woo Shop Archive через Theme Builder**.
- Автоматичний Visual Critic після скриншотів живого Elementor, його bounded visual-repair цикл; Lighthouse, axe, ZAP, production hardening.
- Доказова гарантія «wow» або того, що достатньо одного промпту для повністю запущеного магазину.

## Принцип продукту

Генератор вибирає не один із готових сайтів, а створює свою артдирекцію й параметри композиції з безпечних Elementor-примітивів. Потрібні реальні фото/копірайтинг/факти й оцінка результату у браузері, щоб продемонструвати якість, а не лише «JSON валідний».
