# nara

Staffing workflow system for hospital wards. When a staffing event happens (unplanned leave, no-show, patient surge), the system finds the gap, proposes candidates, checks safety rules, and routes the result for approval.

The stack has four parts:

- **Backend:** FastAPI, SQLAlchemy 2 and PostgreSQL
- **Frontend:** Next.js 15 and Tailwind CSS v4
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
| Redis 7 | `nara-staffing-redis` | 6379 | `REDIS_PORT` |
| Backend (FastAPI) | `nara-staffing-backend` | 8000 | `BACKEND_PORT` |
| Frontend (Next.js) | `nara-staffing-frontend` | 3000 | `FRONTEND_PORT` |

If a port is already in use on your machine, change its value in `.env`. If you change `BACKEND_PORT`, also update `NEXT_PUBLIC_API_BASE_URL`, because the browser calls the backend directly.

## Using make

The [Makefile](Makefile) wraps the common Docker Compose commands. Run `make` to list them.

| Command | What it does |
|---|---|
| `make up` | Start all services in the background (creates `.env` if it's missing) |
| `make down` | Stop all services. Data is kept |
| `make reset` | Stop, **delete** the database, Redis and node_modules volumes, then start fresh |
| `make test` | Run backend tests with pytest inside the backend container. Run `make up` first |
| `make logs` | Follow logs. For one service: `make logs s=backend` |
| `make ps` | Show service status and health |

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

If you add an npm dependency, run `docker compose down -v` or remove the `frontend_node_modules` volume so that `npm install` runs from a clean state.

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
uvicorn app.main:app --reload --port 8000
```

On Windows PowerShell, use `$env:DATABASE_URL = "..."` instead of `export`. You can also create `backend/.env`, which the settings read automatically.

**Frontend** (Node 20+):

```bash
cd frontend
npm install
npm run dev
```

## Repository layout

```text
.
├── docker-compose.yml      # local stack: postgres, redis, backend, frontend
├── .env.example            # copy to .env
├── docs/
│   ├── workflow.md         # workflow contract (states, transitions, decisions)
│   └── database-schema.md  # planned DB schema and enums
├── backend/
│   ├── pyproject.toml
│   └── app/
│       ├── main.py         # FastAPI app and /health
│       ├── core/config.py  # settings (from env / .env)
│       ├── db/session.py   # SQLAlchemy engine and session
│       └── domain/enums.py # shared StrEnums (source of truth together with docs)
└── frontend/
    ├── package.json
    └── src/app/            # Next.js App Router (layout.tsx, page.tsx)
```

New modules follow the team's target structure: `api/`, `services/`, `repositories/`, `workflow/`, `optimization/` and the rest.

## Troubleshooting

- **The backend stays `unhealthy` or the frontend never starts.** The frontend waits for a healthy backend, and the backend waits for a healthy Postgres. Check `docker compose logs backend`. Common causes are a failed `pip install` or a wrong `DATABASE_URL`.
- **The page says "Cannot reach the API".** Check that http://localhost:8000/health opens in your browser, and that `NEXT_PUBLIC_API_BASE_URL` matches the backend port.
- **`database: unreachable`.** Postgres isn't up yet, or its credentials don't match `DATABASE_URL`. If you changed `POSTGRES_*` after the first run, the old volume still has the old credentials. Run `docker compose down -v` to recreate it.
- **Hot reload doesn't work on Windows.** File-watching polling is already turned on (`WATCHPACK_POLLING`). Keep the repo on a local drive rather than a network share.
