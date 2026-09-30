import sqlite3
from datetime import date, datetime, time
from pathlib import Path

from app.optimizer.model import (
    AvailabilityWindow, Employee, Project, ProjectRequirement, SchedulingInput,
    Shift, SkillProficiency,
)
from app.services.scheduling_service import generate_schedule


def _available(employee_id, start_day=4, end_day=7):
    return AvailabilityWindow(employee_id, datetime(2026, 10, start_day), datetime(2026, 10, end_day, 23, 59))


def _project_data(shifts, requirements, employees=None, project_deadline=date(2026, 10, 5), projects=None):
    employees = tuple(employees or (Employee("python", "Python worker", skills=(SkillProficiency("Python", 2),)),))
    projects = tuple(projects or (Project(1, "Project Alpha", project_deadline, "active"),))
    availability = tuple(_available(employee.id) for employee in employees)
    return SchedulingInput(tuple(employees), tuple(shifts), availability, projects=projects,
                           project_requirements=tuple(requirements))


def test_project_requirement_is_fulfilled_and_metrics_report_completion(client):
    skill = client.post("/api/skills", json={"name": "Python"}).json()
    employee = client.post("/api/employees", json={"name": "Ari", "email": "ari-project@example.test",
                                                    "max_hours_per_week": 40, "hourly_rate": 25}).json()
    assert client.post(f"/api/employees/{employee['id']}/skills", json={"skill_id": skill["id"]}).status_code == 201
    project = client.post("/api/projects", json={"name": "Project Alpha", "status": "active",
                                                   "deadline": "2026-10-05"}).json()
    requirement = client.post(f"/api/projects/{project['id']}/requirements", json={
        "skill_id": skill["id"], "role": "developer", "quantity": 1,
        "required_hours": 16, "minimum_proficiency": 1,
    })
    assert requirement.status_code == 201
    shifts = []
    for day in ("2026-10-04", "2026-10-05"):
        shift = client.post("/api/shifts", json={"date": day, "start_time": "08:00", "end_time": "16:00",
                                                   "required_staff": 1, "project_id": project["id"]}).json()
        shifts.append(shift)
        assert client.post("/api/availability", json={"employee_id": employee["id"], "date": day,
            "start_time": "00:00", "end_time": "23:59", "available": True}).status_code == 201

    result = client.post("/api/optimization/generate", json={
        "start_date": "2026-10-04", "end_date": "2026-10-05", "project_id": project["id"],
    }).json()
    assert result["status"] == "FEASIBLE"
    assert result["schedule_id"] is not None
    assert {item["shift_id"] for item in result["assignments"]} == {item["id"] for item in shifts}
    assert all(item["project_id"] == project["id"] for item in result["assignments"])
    project_result = result["projects"][0]
    assert project_result["project_name"] == "Project Alpha"
    assert project_result["deadline"] == "2026-10-05"
    assert project_result["completion_percentage"] == 100
    assert project_result["requirements"][0]["required_hours"] == 16
    assert project_result["requirements"][0]["scheduled_hours"] == 16
    assert project_result["requirements"][0]["remaining_hours"] == 0
    assert project_result["requirements"][0]["satisfied"] is True


def test_insufficient_work_before_deadline_is_infeasible_and_not_persisted(client):
    skill = client.post("/api/skills", json={"name": "Python"}).json()
    employee = client.post("/api/employees", json={"name": "Ari", "email": "ari-deadline@example.test",
                                                    "max_hours_per_week": 40}).json()
    client.post(f"/api/employees/{employee['id']}/skills", json={"skill_id": skill["id"]})
    project = client.post("/api/projects", json={"name": "Deadline project", "status": "active",
                                                   "deadline": "2026-10-05"}).json()
    client.post(f"/api/projects/{project['id']}/requirements", json={
        "skill_id": skill["id"], "quantity": 1, "required_hours": 24,
    })
    for day in ("2026-10-04", "2026-10-05", "2026-10-06"):
        client.post("/api/shifts", json={"date": day, "start_time": "08:00", "end_time": "16:00",
                                         "required_staff": 1, "project_id": project["id"]})
        client.post("/api/availability", json={"employee_id": employee["id"], "date": day,
            "start_time": "00:00", "end_time": "23:59", "available": True})
    before = len(client.get("/api/schedules").json())
    response = client.post("/api/optimization/generate", json={
        "start_date": "2026-10-04", "end_date": "2026-10-06", "project_id": project["id"],
    })
    result = response.json()

    assert response.status_code == 200
    assert result["status"] == result["solver_status"] == "INFEASIBLE"
    assert result["schedule_id"] is None
    assert result["assignments"] == []
    assert result["projects"][0]["requirements"][0]["scheduled_hours"] == 0
    assert len(client.get("/api/schedules").json()) == before


def test_project_requirements_count_only_skilled_employees_and_enforce_distinct_count():
    shifts = (Shift("one", date(2026, 10, 4), time(8), time(16), project_id=1),)
    unskilled = Employee("plain", "No skill")
    data = _project_data(shifts, (ProjectRequirement("r", 1, "Python", required_hours=1),), (unskilled,))
    assert generate_schedule(data)["status"] == "INFEASIBLE"

    skilled = Employee("qualified", "Qualified", skills=(SkillProficiency("Python", 2),))
    count_requirement = ProjectRequirement("r", 1, "Python", required_count=2)
    result = generate_schedule(_project_data(shifts, (count_requirement,), (skilled,)))
    assert result["status"] == "INFEASIBLE"


def test_project_requirement_rejects_insufficient_skill_proficiency_and_late_work():
    late_shift = Shift("late", date(2026, 10, 6), time(8), time(16), project_id=1)
    low_proficiency = Employee("junior", "Junior", skills=(SkillProficiency("Python", 1),))
    requirement = ProjectRequirement("r", 1, "Python", required_hours=8, minimum_proficiency=2)
    assert generate_schedule(_project_data((late_shift,), (requirement,), (low_proficiency,)))["status"] == "INFEASIBLE"

    skilled = Employee("senior", "Senior", skills=(SkillProficiency("Python", 2),))
    assert generate_schedule(_project_data((late_shift,), (requirement,), (skilled,)))["status"] == "INFEASIBLE"


def test_multiple_project_requirements_are_all_enforced_and_projects_are_independent():
    employees = (Employee("py", "Python", skills=(SkillProficiency("Python", 1),)),
                 Employee("sql", "SQL", skills=(SkillProficiency("SQL", 1),)))
    shifts = (Shift("py-shift", date(2026, 10, 4), time(8), time(16), project_id=1),
              Shift("sql-shift", date(2026, 10, 5), time(8), time(16), project_id=2))
    projects = (Project(1, "Alpha", date(2026, 10, 5), "active"),
                Project(2, "Beta", date(2026, 10, 5), "active"))
    requirements = (ProjectRequirement("py-req", 1, "Python", required_hours=8),
                    ProjectRequirement("sql-req", 2, "SQL", required_hours=8))
    result = generate_schedule(_project_data(shifts, requirements, employees, projects=projects))

    assert result["status"] == "FEASIBLE"
    assert len(result["projects"]) == 2
    assert all(item["completion_percentage"] == 100 for item in result["projects"])
    assert {item["project_id"] for item in result["projects"]} == {1, 2}


def test_multiple_requirements_on_one_project_and_wrong_project_work():
    employees = (Employee("py", "Python", skills=(SkillProficiency("Python", 1),)),
                 Employee("sql", "SQL", skills=(SkillProficiency("SQL", 1),)))
    requirements = (ProjectRequirement("py", 1, "Python", required_hours=8),
                    ProjectRequirement("sql", 1, "SQL", required_hours=8))
    shifts = (Shift("python-work", date(2026, 10, 4), time(8), time(16), project_id=1),
              Shift("sql-work", date(2026, 10, 5), time(8), time(16), project_id=1))
    complete = generate_schedule(_project_data(shifts, requirements, employees))
    assert complete["status"] == "FEASIBLE"
    assert all(item["satisfied"] for item in complete["projects"][0]["requirements"])

    wrong_project_shift = (Shift("unrelated", date(2026, 10, 4), time(8), time(16), project_id=2),)
    wrong_project = generate_schedule(_project_data(wrong_project_shift, requirements, employees))
    assert wrong_project["status"] == "INFEASIBLE"


def test_additive_project_migration_preserves_legacy_rows():
    connection = sqlite3.connect(":memory:")
    connection.executescript("""
        CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT, status TEXT, description TEXT);
        CREATE TABLE shifts (id INTEGER PRIMARY KEY, date DATE);
        CREATE TABLE project_requirements (id INTEGER PRIMARY KEY, project_id INTEGER, skill_id INTEGER, role TEXT, quantity INTEGER);
        INSERT INTO projects VALUES (1, 'Legacy', 'active', NULL);
        INSERT INTO shifts VALUES (1, '2026-10-05');
        INSERT INTO project_requirements VALUES (1, 1, NULL, 'staff', 2);
    """)
    migration = Path(__file__).parents[1] / "migrations" / "0002_project_aware_scheduling.sql"
    connection.executescript(migration.read_text(encoding="utf-8"))

    assert connection.execute("SELECT id, name, deadline FROM projects").fetchone() == (1, "Legacy", None)
    assert connection.execute("SELECT id, project_id FROM shifts").fetchone() == (1, None)
    assert connection.execute("SELECT id, quantity, required_hours, minimum_proficiency FROM project_requirements").fetchone() == (1, 2, 0.0, 1)
    connection.close()
