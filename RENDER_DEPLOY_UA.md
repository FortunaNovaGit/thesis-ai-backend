# Render deployment — test backend

## GitHub
Create a new repository and upload the CONTENTS of this folder so that `Dockerfile`, `pyproject.toml`, `app/`, and `render.yaml` are at the repository root.

Do not upload `.env` or `data/`.

## Render
1. New → Web Service → Git Provider → GitHub.
2. Select the repository.
3. Runtime / Language: Docker.
4. Branch: main.
5. Root Directory: leave blank.
6. Dockerfile Path: `./Dockerfile`.
7. Instance type: Free.
8. Health Check Path: `/health`.
9. Environment variables for first test:
   - `AGENT_MODE=mock`
   - `AUTO_APPROVE_MEDIUM_RISK=true`
   - `ALLOW_INSECURE_WORDPRESS=false`
   - `ALLOW_PRIVATE_WORDPRESS=false`
10. Deploy.

After deploy open:
`https://YOUR-SERVICE.onrender.com/health`

Expected JSON:
`{"status":"ok","version":"0.4.0","agent_mode":"mock"}`

## Important limitation
This test build stores connected-site state on Render's local filesystem. Free Render web services do not provide a persistent disk. A redeploy/restart can therefore require reconnecting the WordPress plugin. This is acceptable for the first end-to-end test; the next version should move site state to PostgreSQL or another persistent store.


## v0.4.0
Backend HTTP client now follows safe canonical redirects (for example EasyWP adding a trailing slash to REST routes).
