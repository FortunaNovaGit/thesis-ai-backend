# Quick Start — v0.7.2

1. Замініть backend у GitHub вмістом цього архіву, Commit → Push → Render redeploy.
2. Не змінюйте `BACKEND_TOKEN_SECRET`.
3. Для дешевого 3-page тесту рекомендовано:
   - `MAX_BUILD_COST_USD=0.30`
   - `MAX_TOTAL_LLM_TOKENS=20000`
   - `MAX_LLM_CALLS=8`
   - `MAX_REPAIR_LOOPS=1`
   - `ENABLE_BUILDER_LLM_REVIEW=false`
4. Перевірте `/health`: version `0.7.2`, architecture `artifact_pipeline_v2`, agent mode `openai`.
5. Оновіть Thesis AI Bridge до `0.7.2` через Upload Plugin → Replace current with uploaded.
6. Старі AI-owned draft pages видаляти не обов'язково: builder оновлює canonical slugs і може використати їх повторно.
7. Запустіть той самий 3-page prompt і порівняйте: duration, calls/tokens/cost, headings, CTA, form, design, QA issues.

Build має продовжуватися у фоні навіть якщо вкладка WordPress не активна. Якщо WP-Cron затримується, відкрита builder page має безпечно підштовхнути один stale step.
