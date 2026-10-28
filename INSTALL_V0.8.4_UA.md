# Оновлення v0.8.4

1. Зробити backup тестового WordPress і зберегти commit робочої версії backend.
2. Замінити backend-файли з ZIP у GitHub. Commit, push, Render deploy. Не змінювати `BACKEND_TOKEN_SECRET`, `BACKEND_PAIRING_SECRET`, `DATABASE_URL`.
3. Перевірити `/health`: версія `0.8.4`.
4. WordPress → Plugins → Add New → Upload Plugin → ZIP → **Replace current with uploaded**. Не видаляти плагін вручну; це може змінити його settings.
5. Відкрити AI Website Builder → перевірити connection/preflight. Версія Bridge `0.8.4`.
6. **Без витрат API:** можна відкрити стару AI-сторінку й оцінити новий scoped CSS. Якщо старий документ створено з темплейтом Default, у Elementor Page Settings вибрати **Elementor Full Width**. Для нових AI-сторінок це виконається автоматично.
7. Elementor → Tools → Regenerate CSS & Data (за потреби). Очистити кеш/CDN, якщо показується старий стиль.
8. Запускати тест лише на draft-сайті. На першій перевірці особливо дивитися на H1, колонку Hero, мобільну версію, контент карток і редагованість у Elementor.

## MCP: окремий добровільний тест

- Перевірити WordPress >= 6.8, Elementor >= 4.3, ввімкнений Atomic Editor.
- Адміністратор: Elementor → Elementor MCP → Enable MCP access → Other / Codex / Cursor → Generate Prompt. Це створить WordPress Application Password.
- Авторизувати окремий MCP-клієнт **свідомо**, з правами, потрібними тільки для тестової сторінки. Не вставляти секрети у відкриту переписку або в backend repo.
- У v0.8.4 backend **не виконує** MCP-виклики. Для цього потрібен окремий opt-in MCP Adapter, тести tools discovery, permissions, dry-run і audit.

Поточні CSS-тести — синтетичні, вони не замінюють browser QA на реальному WordPress.
