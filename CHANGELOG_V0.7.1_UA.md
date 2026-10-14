# v0.7.1 — Capability Resolver hotfix

## Виправлено

- `core_pages` та інші природні aliases (`wordpress_pages`, `core_navigation`, `contact_forms`, `elementor`, `custom_fields` тощо) тепер детерміновано нормалізуються у фіксований capability vocabulary.
- Базові WordPress capabilities (`pages`, `navigation`, `site_identity`, `seo`) більше не залежать від того, чи згадає їх Architect точним словом.
- Elementor capability автоматично додається для Elementor renderer.
- Architect prompt тепер містить точний whitelist semantic capability IDs і забороняє вигадувати synonyms/plugin slugs.
- Якщо planning впав після LLM-викликів, backend повертає фактичні token/cost usage замість оманливих `0 tokens / $0.000`.
- WordPress UI під час нового planning більше не показує сторінки зі старого build. До завершення Architect етапу показується нейтральний placeholder.

## Причина regression у v0.7.0

Architect повернув required capability `core_pages`. Це логічний опис можливості, але resolver знав тільки canonical `pages`, тому класифікував `core_pages` як `unavailable` і навмисно зупинив build до будь-яких WordPress mutations.

v0.7.1 нормалізує цю межу між вільним LLM vocabulary і deterministic execution vocabulary.
