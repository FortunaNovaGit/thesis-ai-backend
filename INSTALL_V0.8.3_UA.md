# Установлення v0.8.3

1. Зробіть резервну копію сайту і тестуйте на staging. Залиште активний WooCommerce та Elementor.
2. У GitHub repo backend замініть код вмістом backend архіву. Commit → Push → Render deploy. `BACKEND_TOKEN_SECRET` і `DATABASE_URL` не змінюйте.
3. Перевірте `/health`: version = `0.8.3`. Перевірте Render Logs без розкриття API keys.
4. WordPress → Plugins → Add New → Upload Plugin → виберіть `thesis-ai-bridge-v0.8.3.zip` → Replace current with uploaded. Не видаляйте поточний плагін вручну.
5. WordPress → AI Website Builder → Перевірити з'єднання → Preflight.
6. Повторіть 3-сторінковий prompt Fortuna Nova, але прямо попросіть демо-товари, якщо потрібні заготівки.
7. WordPress → WooCommerce → Products: переконайтеся, що статус товарів **Draft** і немає жодної вигаданої ціни.
8. Відкрийте /shop/ увійшовши адміністратором. За відсутності опублікованих товарів побачите **редакторський** preview AI-чернеток. Публічному відвідувачу чернетки НЕ видно.
9. Перевірте Home (desktop/mobile): новий дизайн, відсутність внутрішніх формулювань, товарний showcase і робочі CTA. Завантаження реальних медіа рекомендується для повноцінного вигляду.

Якщо WordPress знову повідомить `Could not create directory ... wp-content/upgrade`, це серверна помилка запису; повторне перейменування ZIP її не вилікує. Перевірте права/диск або встановіть оновлення через SFTP.
