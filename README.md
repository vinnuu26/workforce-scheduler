# Workforce Scheduler

A workforce planning application that stores employee and shift data, generates schedules with Google OR-Tools CP-SAT, and exposes schedule coverage, conflicts, alternatives, and reschedule previews through a React dashboard.

## Features

- Manage employees, departments, skills, dated shifts, shift templates, availability, leave, weighted preferences, projects, and project requirements.
- Generate and persist a feasible schedule for a selected date range.
- Optimize in this order: minimize excess staffing, minimize labor cost, maximize weighted preference satisfaction, then balance working hours, night shifts, and weekend shifts.
- Generate unique alternative schedules without persisting them.
- Diagnose infeasible inputs with evidence-based conflict details and inspect bounded resolution candidates tested by the production optimizer. Conflict analysis is non-persistent; leave and unsupported changes are shown as informational only.
- Review saved assignments and the factual explanation/objective context recorded at generation time.
- Preview a full-day absence against a saved schedule using the same optimizer. The preview does not modify the original schedule or save the candidate.
- Apply an explicitly confirmed reschedule after the server reruns the optimizer; schedule assignments and totals are replaced in one database transaction.
- Persist employee skill proficiency from levels 1–5; legacy employee-skill rows migrate to level 1.
- View dashboard measures derived from current workforce, shifts, saved assignments, and saved conflicts.

## Architecture

- `frontend/`: React 18, Vite 6, React Router, Tailwind CSS, Recharts, Axios, and Lucide icons.
- `backend/`: FastAPI, SQLAlchemy, Pydantic, SQLite by default, and OR-Tools CP-SAT.
- `backend/app/optimizer/`: database-independent optimizer model, constraints, objective hierarchy, solver, and project metrics.
- `backend/app/services/`: database-to-optimizer mapping, persistence, alternatives, conflict diagnostics, and reschedule preview.
- API routes are under `/api`; FastAPI documentation is at `/docs`.
- CRUD is available for departments, skills, employees, shift templates, shifts, availability, leave, preferences, projects, requirements, and schedule metadata. Employee skill relationships support add, proficiency update, and remove. Schedule assignments are read-only outside optimizer generation and validated rescheduling.

## Local development

### Backend

From `backend/`, create/use the project virtual environment and install dependencies:

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Copy `.env.example` to a local `.env` only if you need to override the database or local CORS origins. `CORS_ORIGINS` is a comma-separated allowlist and defaults to the two local Vite origins. The default database is `backend/workforce_scheduler.db` (ignored by Git). Run the API from `backend/`:

```powershell
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

The API listens on `http://localhost:8000`. The frontend development origin is allowed by the local CORS configuration.

The API creates missing tables on startup and applies the additive employee-skill proficiency column migration when needed. When upgrading a pre-existing database that predates preference weights or project-aware scheduling, review and apply the earlier ordered SQL files in `backend/migrations/` before starting the upgraded application.

### Frontend

From `frontend/`:

```powershell
npm ci
Copy-Item .env.example .env.local
npm run dev
```

`VITE_API_BASE_URL` is the backend origin (for example `http://localhost:8000`); the API client adds `/api`. Vite uses the local backend default in development. Production builds use a same-origin `/api` path unless `VITE_API_BASE_URL` is explicitly set.

### Tests and build

From `backend/`:

```powershell
..\backend\venv\Scripts\python.exe -m pytest -q
..\backend\venv\Scripts\python.exe -c "from app.main import app; print('FastAPI import OK')"
```

From `frontend/`:

```powershell
npm run build
```

## Demo data

The development seeder adds rows only when their identifying demo values are missing; it does not clear or reset the database. From `backend/` run:

```powershell
.\venv\Scripts\python.exe scripts\seed_demo_data.py
```

It creates three departments, skills, employees, shift templates, a feasible seven-day staffing period, explicit availability differences, approved leave, weighted preferences, projects and project requirements. It assigns varied employee skill levels from 1–5. It also creates a separate next-day shift with demand of 999 to demonstrate an intentionally infeasible staffing case. Use the printed date range in **Schedule** to generate the feasible roster; select the following day in **Conflicts** to run diagnostics.

## Demo workflow

1. Seed data and start the API and frontend.
2. Review employees and skills, shifts, projects, and project requirements.
3. Add or review availability, approved leave, and weighted preferences under **Constraints**.
4. Generate a schedule for the seeder’s seven-day period; inspect coverage, cost, assignments, and per-assignment explanation details.
5. Generate one to three alternatives and inspect their returned metrics; alternatives are not saved.
6. Choose a saved assignment under **Reschedule** to preview a full-day absence and compare optimizer output. The preview never changes the source schedule.
7. Analyze the intentionally infeasible date under **Conflicts** and inspect tested resolution proposals. Feasible resolutions are verified by the production optimizer; informational suggestions cannot be applied automatically.
8. Select an assignment in **Reschedule**, preview a temporary full-day absence, review the before/after assignment differences, then explicitly confirm to apply the server-revalidated candidate.

## Rescheduling and data limitations

The preview models an employee as absent for the entire selected shift date. It uses temporary approved leave and the existing optimizer, then compares assignments by shift ID. Applying reruns this candidate on the server and atomically replaces assignments and totals while preserving schedule identity and date metadata. The candidate is rejected if no longer feasible. The dashboard omits preference and fairness scores because those values are not persisted with saved schedules. Arbitrary objective weights are intentionally not configurable: the solver uses proven lexicographic stages, and combining them into weighted sums would change the documented priority guarantees. Hard constraints remain mandatory. Conflict resolution currently analyzes infeasibility and returns verified changes for review; direct automatic application of conflict suggestions is not wired into the reschedule flow. Employee skill proficiency is persisted on a 1–5 scale and checked against project minimum proficiency.

## Environment variables

| Variable | Used by | Default | Purpose |
| --- | --- | --- | --- |
| `DATABASE_URL` | Backend | `sqlite:///./workforce_scheduler.db` | SQLAlchemy database connection. |
| `CORS_ORIGINS` | Backend | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated allowed browser origins for cross-origin API use. |
| `VITE_API_BASE_URL` | Frontend build | local dev: `http://localhost:8000`; production: same origin | Backend origin; frontend appends `/api`. |
| `WEB_PORT` | Docker Compose | `8080` | Host port for the web container. |

No credentials or production secrets are included. Keep `.env` files local; `.env.example` files contain placeholders/configuration only.

## Deployment

Docker Compose builds a static React frontend served by Nginx and a FastAPI backend. Nginx proxies `/api/` to the backend, and SQLite data is stored in a named volume:

```sh
docker compose up --build
```

Open `http://localhost:8080`. Set `WEB_PORT` to change the host port. For a deployment where the browser reaches the API at a separate public origin, build with `VITE_API_BASE_URL` set to that HTTPS backend origin and configure the backend CORS allowlist for the deployed frontend origin. Do not place secrets in Vite variables; they are embedded in the public frontend bundle.

This repository contains deployment configuration, not a deployed service. Hosting credentials, a production database decision, and the actual deployment action remain environment-specific.
