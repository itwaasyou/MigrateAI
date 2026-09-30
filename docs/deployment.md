# Deployment notes

The local planner runs with SQLite and an in-process background task, so no extra backend services are needed locally. For a shared deployment, use a managed database, persistent repository storage, HTTPS, and a production secret/session-cookie policy.

## Environment

- `DATABASE_URL`: SQLAlchemy URL. Use a managed PostgreSQL URL for production.
- `REDIS_URL`: private Redis URL for shared production rate limiting. It is not needed for local development.
- `DATA_ROOT`: private persistent volume for uploaded repository files.
- `COOKIE_SECURE=true`: set session cookies only over HTTPS.
- `APP_ENV=production`: enables Redis-backed rate limits.
- `WEB_ORIGIN`: exact frontend origin allowed by CORS.
- `GEMINI_API_KEY`: Gemini API key for repository chat.
- `AI_MODEL`: optional Gemini model name; defaults to `gemini-2.5-flash`.
- `AI_MODEL`: optional Gemini model name; defaults to `gemini-3.8-flash`.

Apply the schema with `alembic upgrade head` before starting the API. Repository scans run as in-process background tasks, so begin with one API instance. Do not expose the database, Redis, uploaded repository storage, or Gemini key to the browser. Put TLS termination and request-size limits at the ingress. Back up the relational database and repository volume together.

## Deployment steps

- **API:** install `apps/api` with `python -m pip install .`, apply migrations, then run `uvicorn migrateai.main:app --host 0.0.0.0 --port 8000` behind HTTPS.
- **Frontend:** deploy `apps/web` to a Node 22 host and set `NEXT_PUBLIC_API_URL` to the public API origin at build time.
- **Data:** use managed PostgreSQL if needed, managed Redis only for multi-instance production rate limiting, and encrypted persistent storage mounted at `DATA_ROOT`.

Set database credentials, the Gemini key, secure cookies, firewall rules, and backups in the selected cloud secret manager. Do not commit `.env` files.
