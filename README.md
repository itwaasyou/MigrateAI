# MigrateAI

MigrateAI scans a source repository and turns the findings into an ordered software migration plan. Each task explains what to do next, why it matters, how to tell it is complete, and which repository files to open when the scan found relevant evidence.

## Run locally

The default local setup uses SQLite and runs repository analysis in the API process. **Docker, PostgreSQL, and Redis are not needed to try the app.** MigrateAI reads source files for analysis; it does not execute the uploaded application or modify its repository.

### Requirements

- Windows PowerShell
- Python 3.11 or newer (the commands below use Python 3.12)
- Node.js 22 or newer and npm
- A Gemini API key only if you want repository chat and Gemini-tailored plans

The web app pins `pnpm@11.19.0` in `apps/web/package.json`. Install that version once with npm; these instructions do not require Corepack.

### 1. Configure the API

From the repository root, create a private `.env` file from the example:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and set `GEMINI_API_KEY` if you want Gemini features. Leave it blank to use scan-based plans; repository chat will be unavailable.

### 2. Start the API

Open a PowerShell window at the repository root:

```powershell
Set-Location apps/api
py -3 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -e ".[dev]"
& .\.venv\Scripts\python.exe -m alembic upgrade head
& .\.venv\Scripts\python.exe -m uvicorn migrateai.main:app --reload
```

Keep this window open. The API is at <http://localhost:8000>; its interactive API documentation is at <http://localhost:8000/docs>. The default database is `apps/api/migrateai.db`, and uploaded source is stored under `apps/api/data/`.

After pulling an update that changes the database, stop the API, run the Alembic upgrade command above from `apps/api`, and start the API again.

### 3. Start the web app

Open a second PowerShell window at the repository root and install the pinned pnpm version once:

```powershell
npm install --global pnpm@11.19.0
```

If PowerShell cannot find `pnpm` afterward, close and reopen the window. Then start the web app:

```powershell
Set-Location apps/web
pnpm --version
pnpm install --frozen-lockfile
pnpm dev
```

`pnpm --version` should print `11.19.0`. Open <http://localhost:3000>, create an account with a password of at least 12 characters, and upload a repository ZIP.

### 4. Try the demo

From a third PowerShell window at the repository root, create a ZIP of the included demo:

```powershell
Compress-Archive -Path .\demo\legacy-monolith\* -DestinationPath "$env:TEMP\legacy-monolith.zip" -Force
```

Upload the ZIP. After analysis finishes, review the detected current stack, choose a target stack, and select **Generate step-by-step plan**. Start with the highlighted action. Update task statuses as you work, then export the Markdown plan.

## Target stack suggestions

The target picker groups suggested options by runtime, framework, web framework, data store, and platform. Suggestions come from the selected current stack and are starting points, not automatic compatibility guarantees. You can select multiple technologies or add a custom target.

## Configuration

| Variable | Purpose | Default |
| --- | --- | --- |
| `GEMINI_API_KEY` | Enables Gemini-backed repository chat and tailored plans | Unset |
| `AI_MODEL` | Gemini model name | `gemini-3.8-flash` |
| `DATABASE_URL` | SQLAlchemy database connection | `sqlite:///./migrateai.db` |
| `WEB_ORIGIN` | Allowed browser origin for API requests | `http://localhost:3000` |
| `COOKIE_SECURE` | Marks the session cookie secure when using HTTPS | `false` |
| `MAX_UPLOAD_MB` | Maximum uploaded ZIP size | `50` |
| `DATA_ROOT` | Location for extracted repositories | `./data/repos` |

## Development checks

Run from `apps/api`:

```powershell
& .\.venv\Scripts\python.exe -m pytest tests -q
& .\.venv\Scripts\python.exe -m ruff check src tests migrations
& .\.venv\Scripts\python.exe -m ruff format --check src tests migrations
```

Run from `apps/web`:

```powershell
pnpm run typecheck
pnpm run build
```

## What is implemented

- Email/password accounts, workspace roles, and workspace-scoped API access.
- ZIP upload with archive path and size checks.
- Static repository inventory, language and technology signals, import edges, and API/database findings.
- Evidence-linked repository chat with bounded source retrieval when Gemini is configured.
- Impact estimates based on the files found by the scan.
- Ordered migration plans, an explicitly highlighted next task, task status updates, and Markdown export.
- SQLite and an in-process analysis runner for local development.

## Current limits

- The scanner uses deterministic manifest/text signals and Python AST support; it is not a complete parser for every language.
- Impact estimates cover detected signals and do not predict every downstream change.
- Plans provide recommendations; they do not transform the source repository.
- GitHub OAuth, branch selection, commit history, email verification and recovery, incremental analysis, full architecture/dependency visualizations, and end-to-end browser coverage are not implemented yet.

See [docs/roadmap.md](docs/roadmap.md) for remaining work.
