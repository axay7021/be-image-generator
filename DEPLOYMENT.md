# Deployment status and remaining setup

Target: Render workspace My Workspace (`tea-cspv77ggph6c73d04elg`), account 190020107022ait@gmail.com. Only axay7021 copies are modified.

- Docker runtime includes OpenCV runtime libraries and binds to Render PORT, using one worker by default.
- Startup runs Alembic migrations only when DATABASE_URL is configured; migration failure stops startup. Expected head: b8c5e2f1d3a7.
- `/health` remains available with no AI key; `/api/v1/modify-image/...` returns 503 AI_NOT_CONFIGURED until Gemini is configured.
- Free Render Postgres `ai-image-generator-db` was created on 29 October 2026 and expires 28 November 2026. Public network access is disabled. This is temporary evaluation storage, not permanent production storage.
- Render plugin does not expose database connection credentials or Blueprint apply. Copy the database Internal Database URL directly into this service's DATABASE_URL via Render Environment; do not paste it in chat or GitHub. Then redeploy to apply migrations.
- Set FRONTEND_URL to the actual frontend origin. Frontend NEXT_PUBLIC_BASE_URL must be the backend origin plus `/api/v1` (actions append `/modify-image/...`).
- Configure Clerk public and secret keys through Vercel Environment Variables and the backend Clerk secret/JWKS URL through Render Environment. JWKS must belong to the intended Clerk instance; token-supplied issuers are never trusted.
- Generated signing secrets must remain in hosting environment variables. Never seed the default super-admin account or run reset_password.py with its defaults.

## TODO — owner adds provider keys later

- [ ] Add GEMINI_API_KEY in Render Environment (left empty intentionally).
- [ ] Save, rebuild and redeploy after credential configuration.
- [ ] Verify Clerk signup/login, migrated database state, real image upload, Gemini generation and the frontend response end to end.
- [ ] Replace expiring free Postgres with durable storage before 28 November; approve any recurring cost first.
- [ ] Add the real live frontend URL to the portfolio only after deployment and verification.

No live AI functionality is claimed by a local build or a healthy `/health` endpoint.
