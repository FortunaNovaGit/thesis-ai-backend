# Thesis AI / AI Website Builder — backend v0.9.0

Five-agent FastAPI planning backend, PostgreSQL/SQLite job store, WordPress Pull local execution and a safe, editable Elementor V3 generative layout contract.

**New in v0.9.0:** Creative Director (2–3 concept proposals), `GenerativeDesignSpec`, bounded responsive Elementor-native geometry, deterministic repair of duplicate page/site headings, retained Content Quality Gate. See [changelog](CHANGELOG_V0.9.0_UA.md) and [update guide](INSTALL_V0.9.0_UA.md) (Ukrainian).

## Offline tests — zero OpenAI API usage

```bash
python -m pip install -e '.[dev]'
AGENT_MODE=mock pytest -q
```

Optional synthetic visual smoke (requires Playwright + system Chromium at `/usr/bin/chromium`):

```bash
python qa/generative_layout_smoke.py
```

This test is **not a live WordPress browser QA**. Actual deployment and real Elementor editability need a staging test.

## Run

```bash
export AGENT_MODE=mock
export BACKEND_TOKEN_SECRET="$(openssl rand -hex 32)"  # local-only example
uvicorn app.api:app --reload
```

Render requires an existing stable `BACKEND_TOKEN_SECRET`, PostgreSQL `DATABASE_URL`, and `OPENAI_API_KEY` for `AGENT_MODE=auto`. Do not regenerate an already configured token secret. Never commit API keys, database URLs or pairing secrets.
