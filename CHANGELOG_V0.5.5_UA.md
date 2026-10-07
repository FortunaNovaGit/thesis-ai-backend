# v0.5.5 — stability rollback + staged WordPress execution

Ця версія виправляє регресію v0.5.4, де plugin/theme activation і Elementor page creation могли виконуватись в одному PHP/REST batch. На EasyWP це могло завершувати весь batch generic `500 internal_server_error / There has been a critical error on this website`.

## Основні зміни

- Dependency barrier: plugin/theme install/activate виконуються окремим request і ніколи не змішуються з Elementor document creation.
- Preflight-aware pruning: вже активні Elementor/approved plugins та вже активна Hello Elementor theme не викликають зайвих remote actions.
- Guarded batch execution: кожна action у WordPress batch загорнута в `try/catch (Throwable)`, тому одна помилка Elementor/plugin не повинна валити весь batch.
- Snapshot guard: помилка post-build snapshot повертається як structured `snapshot_error`, а не generic WordPress critical error.
- Content/site setup розділені на фази: dependencies → dependent setup → page/SEO batch → final site assembly + snapshot.
- Elementor stability profile: повернено набір Elementor controls, які вже проходили реальний EasyWP тест у ранній версії; складні typography/responsive controls тимчасово прибрані до стабілізації execution layer.
- Збережено async build, Policy Engine, batching, 429 backoff, preflight/capability resolver і repair loop.

## Чому це важливо

v0.5.4 оптимізувала кількість HTTP requests занадто агресивно. v0.5.5 залишає низьку кількість запитів, але поважає WordPress bootstrap boundaries: код щойно активованого plugin/theme повинен використовуватись вже в наступному PHP request.
