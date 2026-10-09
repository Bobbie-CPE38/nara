# nara

Staffing workflow system for hospital wards. When a staffing event happens (unplanned leave, no-show, patient surge), the system finds the gap, proposes candidates, checks safety rules, and routes the result for approval.

The stack has four parts:

- **Backend:** FastAPI, SQLAlchemy 2 and PostgreSQL
- **Frontend:** Next.js 16 and Tailwind CSS v4
- **Queue/cache:** Redis
- **Local orchestration:** Docker Compose

> Status: walking skeleton. The backend currently exposes `GET /health`, and the frontend shows a system check page. See [docs/workflow.md](docs/workflow.md) and [docs/database-schema.md](docs/database-schema.md) for the planned design.

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker Engine) with Compose v2 (`docker compose version`)
- Git

You don't need to install Python or Node locally, because the containers handle both.

## Quick start

```bash
# 1. Clone, then create your local env file
cp .env.example .env

# 2. Start everything in the background (the first run installs pip and npm dependencies, so it takes a few minutes)
make up            # or: docker compose up -d
```

`make up` also creates `.env` from `.env.example` if you skipped step 1.

When all services report healthy, open these:

| URL | What |
|---|---|
| http://localhost:3000 | Frontend "System check" page. API and Database should both be `ok` |
| http://localhost:8000/health | Backend health check (`{"status":"ok","database":"ok"}`) |
| http://localhost:8000/docs | Interactive API docs (Swagger UI) |

Code changes reload automatically. The backend runs `uvicorn --reload`, and the frontend runs `next dev`. Both have their source mounted as volumes.

## Services and ports

| Service | Container | Default port | `.env` variable |
|---|---|---|---|
| PostgreSQL 17 | `nara-staffing-postgres` | 5432 | `POSTGRES_PORT` |
| Redis 8 | `nara-staffing-redis` | 6379 | `REDIS_PORT` |
| Backend (FastAPI) | `nara-staffing-backend` | 8000 | `BACKEND_PORT` |
| Frontend (Next.js) | `nara-staffing-frontend` | 3000 | `FRONTEND_PORT` |

If a port is already in use on your machine, change its value in `.env`. If you change `BACKEND_PORT`, also update `NEXT_PUBLIC_API_BASE_URL`, because the browser calls the backend directly. If you change `FRONTEND_PORT`, also update `CORS_ORIGINS`. Otherwise the backend blocks the browser and the page says "Cannot reach the API".

## Using make

The [Makefile](Makefile) wraps the common Docker Compose commands. Run `make` to list them.

| Command | What it does |
|---|---|
| `make up` | Start all services in the background (creates `.env` if it's missing) |
| `make down` | Stop all services. Data is kept |
| `make reset` | Stop, **delete** the database, Redis and node_modules volumes, then start fresh |
| `make test` | Run backend (pytest) and frontend (vitest) tests inside the containers. Run `make up` first |
| `make test-backend` | Run backend tests only |
| `make test-frontend` | Run frontend tests only |
| `make lint` | Run ruff and mypy on the backend, and `tsc` on the frontend. Run `make up` first |
| `make lint-backend` | Run ruff and mypy only |
| `make lint-frontend` | Type-check the frontend only |
| `make logs` | Follow logs. For one service: `make logs s=backend` |
| `make ps` | Show service status and health |
| `make seed` | Placeholder. Loading demo data arrives in walking-skeleton Step 2.3 |

macOS and Linux already have `make`. On Windows, install it once and then open a new terminal:

```powershell
winget install ezwinports.make
```

If you'd rather not install it, the raw `docker compose` commands below do the same job.

## Common commands

```bash
docker compose up -d                 # start in the background
docker compose logs -f backend       # follow the logs for one service
docker compose ps                    # show status and health
docker compose down                  # stop (data is kept)
docker compose down -v               # stop and DELETE the database, Redis and node_modules volumes
docker compose restart backend       # restart one service (for example, after editing pyproject.toml)
```

If you add an npm dependency, run `docker compose restart frontend`. The container runs `npm ci` on every start, so it reinstalls from `package-lock.json`.

## Local development without Docker (optional)

Keep PostgreSQL running in Docker (`docker compose up -d postgres redis`) and run the apps on your host.

**Backend** (Python 3.11+):

```bash
cd backend
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e .
# Point at localhost instead of the "postgres" container hostname
export DATABASE_URL=postgresql+psycopg://staffing:staffing_dev@localhost:5432/staffing
export CORS_ORIGINS='["http://localhost:3000"]'
uvicorn app.main:app --reload --port 8000
```

Both variables are required. The backend refuses to start if either is missing. On Windows PowerShell, use `$env:DATABASE_URL = "..."` and `$env:CORS_ORIGINS = '["http://localhost:3000"]'` instead of `export`. You can also put them in `backend/.env`, which the settings read automatically.

**Frontend** (Node 22.12+, 24 recommended, the same as Docker and CI):

```bash
cd frontend
npm install
npm run dev
```

## Repository layout

```text
.
├── docker-compose.yml        # local stack: postgres, redis, backend, frontend
├── Makefile                  # shortcuts for the stack (run `make`)
├── .env.example              # copy to .env
├── .github/workflows/ci.yml  # lint + tests on every PR
├── docs/
│   ├── workflow.md           # workflow contract (states, transitions, decisions)
│   ├── database-schema.md    # planned DB schema and enums
│   ├── walking-skeleton.md   # step-by-step build plan
│   └── repo-structure.md     # target folder structure
├── backend/
│   ├── pyproject.toml        # dependencies, ruff, mypy, pytest
│   ├── alembic.ini
│   ├── alembic/              # migrations (versions/ is empty until Step 2)
│   ├── app/
│   │   ├── main.py           # FastAPI app and /health
│   │   ├── core/config.py    # settings (from env / .env)
│   │   ├── core/clock.py     # settable system clock, use instead of datetime.now()
│   │   ├── db/base.py        # declarative Base with constraint naming
│   │   ├── db/session.py     # SQLAlchemy engine and session
│   │   ├── db/models/        # ORM models (Step 2)
│   │   └── domain/enums.py   # shared StrEnums (source of truth together with docs)
│   └── tests/                # unit/ and integration/, conftest.py creates the test DB
└── frontend/
    ├── package.json
    ├── src/app/              # Next.js App Router (layout.tsx, page.tsx)
    ├── src/lib/api.ts        # API client, adds X-Demo-User
    ├── src/hooks/            # usePolling
    └── tests/unit/           # vitest tests
```

New modules follow the team's target structure: `api/`, `services/`, `repositories/`, `workflow/`, `optimization/` and the rest.

## Troubleshooting

- **The backend stays `unhealthy` or the frontend never starts.** The frontend waits for a healthy backend, and the backend waits for a healthy Postgres. Check `docker compose logs backend`. Common causes are a failed `pip install` or a wrong `DATABASE_URL`.
- **The page says "Cannot reach the API".** Check that http://localhost:8000/health opens in your browser, and that `NEXT_PUBLIC_API_BASE_URL` matches the backend port.
- **`database: unreachable`.** Postgres isn't up yet, or its credentials don't match `DATABASE_URL`. If you changed `POSTGRES_*` after the first run, the old volume still has the old credentials. Run `docker compose down -v` to recreate it.
- **Hot reload doesn't work on Windows.** File-watching polling is already turned on (`WATCHPACK_POLLING`). Keep the repo on a local drive rather than a network share.
