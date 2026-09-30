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

# Project-aware scheduling

Project-aware scheduling adds hard constraints for requirements on projects
whose status is `active`. Shifts must have `project_id` set to be considered
project work. A requirement uses its existing `quantity` as the distinct
qualified employee count, plus `required_hours`; `skill_id` identifies the
required skill and `minimum_proficiency` sets its threshold. Qualified assigned
time across associated shifts must satisfy both values. Requirements without a
skill apply to any active employee assigned to that project's work.

The shift must be completed on or before the project's deadline: a shift counts
only when its end calendar date is no later than the deadline date. Thus an
overnight shift ending the following day does not count for the previous day's
deadline. Work after a deadline never satisfies a requirement. Explicit unmet
requirements make the model infeasible and no schedule or assignment rows are
persisted. Project completion metrics are returned under `projects` alongside
the existing optimizer fields.

The schema change is additive in
`migrations/0002_project_aware_scheduling.sql`. `Base.metadata.create_all`
creates the new columns for a fresh database but does not alter an existing
SQLite database; apply the migration to an existing database before using the
new fields. Existing employee skill rows have no proficiency column, so
database-loaded employee skills currently use proficiency level 1. Higher
employee proficiency levels are supported by the database-independent
optimizer input but need a later employee-skill schema/API extension for
persisted workforce data.
