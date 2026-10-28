# v0.8.2 — Commerce Drafts + Compact Verification

Цей реліз розвиває v0.8.1 без зміни архітектури WordPress Pull та п'яти агентних ролей.

## Що реалізовано

1. **Компактний verify:** Bridge передає `plan_job_id`, компактні результати виконання і поточний snapshot. Backend дістає **повний, збережений** план із JobRepository за `(site_id, job_id)`. Не повторюємо великий Elementor JSON у тілі `/verify`. План чужого сайту відхиляється.
2. **Безпечні WooCommerce drafts:** лише явно названі у лапках товари з тексту завдання; максимум чотири. Дані не згенеровані LLM, ціни, stock, фотографії, алергени не вигадуються. Новий `ensure-woocommerce-product-draft` створює WC_Product_Simple зі статусом `draft`. Уже існуючі чужі продукти ніколи не змінюються, а існуючі AI-owned drafts повторно використовуються без перезапису ручних правок.
3. **Мінімальна адаптація каталогу Elementor:** verified назви можуть відображатися у декоративних editorial preview cards. Це **не** checkout і **не** продає unpublished продукти. Живий shortcode WooCommerce використовується лише за наявності published товарів.
4. **QA:** перевіряє присутність фактично створених WooCommerce draft products. Draft-first не вважається проблемою, відсутність товарів взагалі — проблема. Детерміноване QA виконується раніше за дорогий семантичний QA; якщо вже є блокувальна помилка, LLM QA пропускається.
5. **Пауза після активації залежностей:** WordPress background worker завершує поточний PHP request після install/activate plugin/theme. Новий запит запускається з уже завантаженими класами WooCommerce/Elementor.
6. **Керовані помилки:** невиправна 413 і п'ять поспіль помилок backend завершують build явним failed, а не нескінченним spinner. Після успішної дії лічильник помилок скидається.
7. **Сумісність:** ecommerce preflight перевіряє наявність нової ability *до* викликів LLM.

## Перевірки

- 49 Python tests passed, включно з HTTP integration test `/verify` із великим планом у durable DB і маленьким HTTP request, cross-site deny, policy/validation, mock-commerce plan.
- Усі PHP файли перевіряються `php -l`.
- ZIP integrity перевірено.

## Не реалізовано / обмеження

- Не генеруємо і не завантажуємо фотографії товарів та банери автоматично.
- Немає product variations, shipping, taxes, payment gateway, automated checkout QA чи browser screenshot QA.
- WooCommerce draft products **не з'являються у публічному каталозі**, доки власник не підтвердить дані та не опублікує їх вручну.
- Elementor працює з існуючими медіафайлами сайту лише якщо знайдено тематичний збіг.
- Реальний E2E на EasyWP/Render та мережеві 520 ще потребують перевірки; виправлення великих verify-запитів не гарантує усунення будь-якої 520.
- PostgreSQL потрібний для збереження планів між Render redeploy. Не змінюйте BACKEND_TOKEN_SECRET.
