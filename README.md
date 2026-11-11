# Thesis AI / AI Website Builder — backend v0.9.3

Five-agent FastAPI planning backend, PostgreSQL/SQLite job store, WordPress Pull local execution and a safe, editable Elementor V3 generative layout contract.

**Foundation from v0.9.1:** Creative Director (2–3 concept proposals), `GenerativeDesignSpec`, bounded responsive Elementor-native geometry, deterministic repair of duplicate page/site headings, retained Content Quality Gate. See [changelog](CHANGELOG_V0.9.1_UA.md) and [update guide](INSTALL_V0.9.1_UA.md) (Ukrainian).

## Offline tests — zero OpenAI API usage

```bash
python -m pip install -e '.[dev]'
AGENT_MODE=mock pytest -q
```

Optional synthetic visual smoke (requires Playwright + system Chromium at `/usr/bin/chromium`):

```bash
python qa/generative_layout_smoke.py
python qa/v091_primitives_smoke.py
```

This test is **not a live WordPress browser QA**. Actual deployment and real Elementor editability need a staging test.

## Run

```bash
export AGENT_MODE=mock
export BACKEND_TOKEN_SECRET="$(openssl rand -hex 32)"  # local-only example
uvicorn app.api:app --reload
```

Render requires an existing stable `BACKEND_TOKEN_SECRET`, PostgreSQL `DATABASE_URL`, and `OPENAI_API_KEY` for `AGENT_MODE=auto`. Do not regenerate an already configured token secret. Never commit API keys, database URLs or pairing secrets.

## v0.9.2 split creative contracts

The Creative Director role now makes a site-wide `CreativeFoundation` call, followed by one `CreativePage` call per page. `app/creative_pipeline.py` compiles these typed outputs into the unchanged downstream `ExperienceSpec`. This prevents one giant multi-page output from omitting required headings/SEO and lets one bounded JSON retry repair only the failed page. All rendering still uses WordPress Pull + native Elementor V3 containers/widgets; no executable LLM-generated CSS/HTML. Use `python qa/visual_audit.py --help` for optional non-OpenAI live preview checks. A successful offline fixture does not certify a deployed site.

## v0.9.3 guarded creative copy & optional site brief

- Only page-by-page `CreativePage` output carries `generation_contract=creative_page_v093`. This explicit marker avoids accidentally changing the older mock/compatibility reconciler.
- **Do not inject** fallback headings, repeated eyebrows, card filler, or forced product sections into this creative path; preserve every approved section in its generated order.
- The Creative Director's page payload rejects generic page-name headings, duplicate page paragraphs, planning copy, and unsafe links; a single bounded cross-page retry resolves copy collisions before plan deployment.
- Optional WordPress UI brief captures brand, audience, desired pages, product catalogue scale, available images, HEX palette and confirmed facts. Fields are sanitized locally and appended as explicit input constraints; they never become guessed commercial facts or products.
- Content Quality Gate stays fail-closed with precise section indices.
- **Important limitation:** Elementor Free cannot replace WooCommerce's system Shop archive via the standard Elementor Pro archive Theme Builder. The free pipeline styles the native WooCommerce archive separately, and drafts AI-owned pages as editable Elementor V3 containers.

An offline test is not a live OpenAI/Render/EasyWP acceptance run. Never expose secrets or use a live merchant's WooCommerce settings as a disposable staging test.

## v0.9.4 quality-first staging update

See `CHANGELOG_V0.9.4_UA.md` and `INSTALL_V0.9.4_UA.md`. This retains five agents, WordPress Pull, and the security/policy baseline. It adds media selection from the existing WordPress library, stricter real product identification, full-bleed layout regressions and offline browser QA. The rendering remains Elementor V3 native containers/widgets, not V4 MCP. Do not claim production readiness or visual-wow guarantees from offline tests alone.

## v0.10.0 Visual Composer preview

New `app/visual_composer.py`, constrained `hero_scene`/`hero_height`/`hero_motion` design controls and `plugin/thesis-ai-bridge/assets/visual-composer.css` add five different editable Elementor Hero layouts. Existing five-agent flow, WordPress Pull, Pydantic guards and draft-first behavior remain. The WordPress brief can supply one or two **real WordPress image attachments** for the Hero.

See `CHANGELOG_V0.10.0_UA.md` and `INSTALL_V0.10.0_UA.md`. Offline `qa/visual_composer_smoke.py` is *not* live Elementor or EasyWP proof. Do not infer real-world visual quality or production readiness from it.
