# Workforce Scheduler Backend

Install dependencies with `pip install -r requirements.txt` (and `pip install -r requirements-dev.txt` to run tests).

From this directory, start the API with `uvicorn app.main:app --reload`. The SQLite database defaults to `./workforce_scheduler.db`; set `DATABASE_URL` to override it. API routes are under `/api`; interactive docs are at `/docs`.

Run tests with `pytest`.
# Fairness optimization

After excess staffing, labor cost, and weighted employee preferences have each
been optimized and locked, the optimizer minimizes fairness in three
lexicographic phases: working-hour deviation, night-shift imbalance, then
weekend-shift imbalance. The hour target is total assigned hours divided by
the number of active employees in the scheduling input. The objective minimizes
the sum of absolute differences from that target; it does not relax any hard
constraint.

A shift counts as a night shift when it starts at or after 20:00, ends at or
before 06:00, or crosses midnight. A weekend shift is one whose start date is
Saturday or Sunday. Night and weekend ranges are max count minus min count among
active employees individually eligible for at least one shift in that category;
people ineligible for the category do not lower its minimum. Eligibility
respects activity, availability, approved leave, skills, department, and the
single-shift maximum-hours limit. Each reported balance score is `1 / (1 + r)`,
where `r` is relative imbalance: total hour deviation divided by total assigned
hours, or the category's count range divided by its assigned shift count. A
zero-work denominator uses 1 so a schedule with no shifts has no measured
imbalance. A score of 1 means zero measured imbalance.
