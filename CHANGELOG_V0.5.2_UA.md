# v0.5.2 — root-cause diagnostics + safe reruns

Ця версія виправляє проблеми, які проявились після асинхронного v0.5.1 build.

## Виправлено

- Quality Agent більше не рахує кожну стару невдалу спробу як окрему актуальну проблему. Оцінюється останній результат кожної логічної action.
- Repair loop більше не створює оманливе число на кшталт `30 failed actions`, якщо насправді декілька дій просто повторювались.
- WordPress admin тепер показує точну помилку кожної невиконаної ability: ability, slug/plugin, error, policy reason та attempt.
- AI-owned сторінка у Trash з потрібним slug автоматично відновлюється у Draft і повторно використовується. Це робить development reruns ідемпотентними.
- Published/чужі сторінки все ще не перезаписуються автоматично. Для них повертається явний conflict із status/author.

## Чому це важливо

Під час тестів сторінки часто видаляються перед повторним build. WordPress може залишати trashed post із тим самим slug, а попередній Bridge трактував його як небезпечний conflict. У результаті Elementor page action не доходила навіть до створення post.

## Безпека

Safe rerun стосується лише trashed page, автором якої є dedicated Thesis AI Builder user. Чужий або published content не відновлюється і не переписується.
