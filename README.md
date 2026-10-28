> **v0.8.2:** see `INSTALL_V0.8.2_UA.md` and `CHANGELOG_V0.8.2_UA.md` for compact QA verification, idempotent WooCommerce draft products and limitations.

# WordPress Multi-Agent Thesis Backend — v0.8.1

Five-agent artifact-driven WordPress/Elementor builder prototype. See `CHANGELOG_V0.8.1_UA.md` and `INSTALL_V0.8.1_UA.md` for the release.

## Run locally

```bash
python -m pip install -e '.[dev]'
export AGENT_MODE=mock
export BACKEND_TOKEN_SECRET="$(openssl rand -hex 32)"
export DATABASE_URL="sqlite:///./data/jobs-v081.sqlite3"
uvicorn app.api:app --reload
```

Run tests: `pytest -q`.

## Render

Provide `DATABASE_URL` pointing to **persistent PostgreSQL** and a stable `BACKEND_TOKEN_SECRET` under Environment. Do not put credentials into Git. `/health` reports `durable_jobs` and `stable_connection_tokens`.

WordPress bridge must be v0.8.1. Execution remains local to WordPress to avoid host WAF burst limits.
