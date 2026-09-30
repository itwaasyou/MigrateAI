# Deploy MigrateAI with Vercel

This guide deploys the **Next.js web app** to Vercel and runs the existing FastAPI API on a Python host that provides persistent storage. The repository contains two apps; Vercel's project should point at `apps/web`.

## What runs where

| Part | Where it runs | Why |
| --- | --- | --- |
| Web app (`apps/web`) | Vercel | It is a Next.js 15 app and Vercel can build it directly from this monorepo. |
| API (`apps/api`) | A persistent Python service | The API accepts ZIPs up to 50 MB, stores extracted repositories on disk, and runs scans as in-process background tasks. |
| Database | Managed PostgreSQL | User accounts, workspaces, scan results, and plans must survive API restarts. |
| Rate limits | Managed Redis | The API requires Redis when `APP_ENV=production`. |
| Repository files | Persistent disk mounted at `DATA_ROOT` | Chat and reports read the uploaded source files after the upload request has finished. |

Vercel can run FastAPI functions, but that does not fit this API as currently written: Vercel Function request bodies are limited to 4.5 MB, and the function filesystem is read-only apart from temporary `/tmp` storage. This app allows 50 MB uploads and needs repository files to persist across requests. See Vercel's [Function limits](https://vercel.com/docs/functions/limitations), [filesystem documentation](https://vercel.com/docs/functions/runtimes), and [FastAPI guide](https://vercel.com/docs/frameworks/backend/fastapi).

## 1. Prepare the API services

Before configuring Vercel, provision:

1. A Python 3.11+ service that can run continuously and mount a persistent disk.
2. A PostgreSQL database.
3. A Redis instance reachable from the Python service.
4. Two HTTPS hostnames under the same domain, for example `app.example.com` for Vercel and `api.example.com` for the API.

The matching domain is needed because the current session cookie uses `SameSite=Lax`. The app and API can be different subdomains, but must be same-site for the browser to send that cookie on API requests. Vercel's generated `*.vercel.app` preview host and an API on another provider do not meet this requirement.

Configure these variables on the **API host**, using its secret/environment-variable settings:

| Variable | Value |
| --- | --- |
| `DATABASE_URL` | PostgreSQL SQLAlchemy URL using the installed psycopg v3 driver, for example `postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME`. Add the SSL options required by your database provider. |
| `REDIS_URL` | The managed Redis connection URL. Required when `APP_ENV=production`. |
| `DATA_ROOT` | The mount path of the persistent disk, for example `/var/lib/migrateai/repos`. |
| `APP_ENV` | `production` |
| `COOKIE_SECURE` | `true` |
| `WEB_ORIGIN` | The exact Vercel app origin, for example `https://app.example.com` (no trailing slash). |
| `GEMINI_API_KEY` | Your Gemini key, if you want Gemini-backed chat and tailored plans. Keep it on the API only. |
| `AI_MODEL` | Optional; defaults to `gemini-3.8-flash`. |
| `MAX_UPLOAD_MB` | Optional; defaults to `50`. |

Do not put `DATABASE_URL`, `REDIS_URL`, or `GEMINI_API_KEY` in Vercel or in any `NEXT_PUBLIC_` variable. Keep the database and Redis private to the API host.

## 2. Deploy the FastAPI API

Set the API service's working directory to `apps/api`, or use equivalent paths from the repository root. Configure its build/install command:

```sh
python -m pip install .
```

Run database migrations as a release/pre-deploy command before starting the service:

```sh
python -m alembic upgrade head
```

Set the start command to:

```sh
python -m uvicorn migrateai.main:app --host 0.0.0.0 --port $PORT
```

Mount the persistent disk at the path configured by `DATA_ROOT`. Start with one API instance: repository scans run in the API process, and each database record points to a file on that disk. The disk must remain available to that API instance after restarts. The platform must provide a `PORT` environment variable; if it does not, use the port setting required by that platform.

Once it is running, open `https://api.example.com/health`. A healthy API returns:

```json
{"status":"ok"}
```

## 3. Add the web app to Vercel

1. Push this repository to GitHub, GitLab, or Bitbucket and import it from the Vercel dashboard.
2. In the import/build settings, set **Root Directory** to `apps/web`. Vercel documents this setting for projects in a monorepo in [Using Monorepos](https://vercel.com/docs/monorepos).
3. Keep the detected **Next.js** framework settings and set the project Node.js version to **22.x**. The app expects Node.js 22 or newer and pins `pnpm@11.19.0` in `apps/web/package.json`. If Vercel asks for commands, use:

   - Install: `pnpm install --frozen-lockfile`
   - Build: `pnpm run build`
   - Output directory: leave the Next.js default

4. In Vercel project settings, add this environment variable for **Production**:

   | Name | Value |
   | --- | --- |
   | `NEXT_PUBLIC_API_URL` | `https://api.example.com` |

   `NEXT_PUBLIC_API_URL` is compiled into the browser bundle during the build, so redeploy after changing it. Vercel explains the `NEXT_PUBLIC_` behavior in its [framework environment variable documentation](https://vercel.com/docs/environment-variables/framework-environment-variables).

5. Add `app.example.com` under **Settings → Domains** in Vercel and follow Vercel's DNS instructions. Set the API host's custom domain to `api.example.com`.
6. Deploy the production branch.

### If Vercel says “No FastAPI entrypoint found”

This means the Vercel project is building from the repository root and detecting `apps/api`. Open **Project Settings → Build & Development Settings → Root Directory**, set it to `apps/web`, save, and redeploy. Keep the framework set to **Next.js**. Do not add the suggested `[tool.vercel] entrypoint` to `pyproject.toml` for this deployment; that would try to deploy the API as a Vercel Function instead of deploying the web app described here.

If the Vercel log still runs `python -m pip install .` or `alembic`, the project is still pointed at the API or has custom Python build-command overrides. Set the root to `apps/web` and reset the Install Command to Vercel's default (or `pnpm install --frozen-lockfile`) and Build Command to `pnpm run build`. Do not combine commands with commas. Run API dependency installation and database migrations on the separate Python host; Vercel's web project should not run them.

## 4. Verify the deployed app

Open `https://app.example.com` and check the full flow:

1. Create an account using a password of at least 12 characters, then sign in.
2. Create or open a workspace and upload a repository ZIP smaller than 50 MB.
3. Wait for the scan to finish. Confirm the detected current stack, choose a target stack, and generate the step-by-step plan.
4. Update a task status and export the plan as Markdown.

If sign-in does not persist, check that the browser is using the custom app and API subdomains under the same parent domain, that both use HTTPS, and that `WEB_ORIGIN` exactly matches the app origin. If the browser blocks the request, check the API's CORS setting and browser console; the current API allows one exact `WEB_ORIGIN` value.

## Preview deployments

Vercel preview URLs change and use a `vercel.app` hostname, while the API currently allows one exact CORS origin and its session cookie is `SameSite=Lax`. Use the production custom domain for authenticated checks. To support authenticated previews, configure stable same-site preview app/API domains and update the API's allowed-origin handling; simply adding a changing preview URL to `WEB_ORIGIN` is not a durable setup.

## Current deployment limits

- Keep the API at one instance while scans run as FastAPI in-process background tasks and repository files live on its mounted disk. API restarts can interrupt scans that are still running.
- Do not point multiple API instances at separate local disks. A future multi-instance deployment needs shared object storage and a durable job queue.
- Vercel hosts the web app in this guide. The API, database, Redis, and repository files remain separate services.
