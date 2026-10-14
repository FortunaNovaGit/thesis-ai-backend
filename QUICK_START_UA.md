# Quick Start v0.7

1. Замінити backend files у GitHub на v0.7.0 і зробити Push.
2. У Render зберегти існуючий `BACKEND_TOKEN_SECRET`; не генерувати його заново.
3. Додати model-router та budget env variables з `CHANGELOG_V0.7.0_UA.md`.
4. Після deploy відкрити `/health`.
5. Очікувані поля: `version=0.7.0`, `architecture_version=artifact_pipeline_v1`, `model=multi-model`.
6. Оновити WordPress Bridge до v0.7.0 через Upload Plugin → Replace current with uploaded.
7. Натиснути «Перевірити з’єднання», щоб UI підтягнув новий model router.
8. Запустити той самий стоматологічний prompt для коректного A/B порівняння з v0.6.

Під час першого тесту не збільшувати budget. Якщо build зупиниться через budget, спочатку дивитися breakdown по агентах, а не просто піднімати ліміт.
