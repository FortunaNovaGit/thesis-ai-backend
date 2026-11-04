# Thesis AI / AI Website Builder — backend v0.9.1

Five-agent FastAPI planning backend, PostgreSQL/SQLite job store, WordPress Pull local execution and a safe, editable Elementor V3 generative layout contract.

**New in v0.9.1:** Creative Director (2–3 concept proposals), `GenerativeDesignSpec`, bounded responsive Elementor-native geometry, deterministic repair of duplicate page/site headings, retained Content Quality Gate. See [changelog](CHANGELOG_V0.9.1_UA.md) and [update guide](INSTALL_V0.9.1_UA.md) (Ukrainian).

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
