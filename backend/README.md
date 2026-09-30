# Workforce Scheduler Backend

Install dependencies with `pip install -r requirements.txt` (and `pip install -r requirements-dev.txt` to run tests).

From this directory, start the API with `uvicorn app.main:app --reload`. The SQLite database defaults to `./workforce_scheduler.db`; set `DATABASE_URL` to override it. API routes are under `/api`; interactive docs are at `/docs`.

Run tests with `pytest`.
