from datetime import date, datetime, time

from app.optimizer.model import (
    AvailabilityWindow, Employee, LeavePeriod, Project, ProjectRequirement,
    SchedulingInput, Shift, SkillProficiency,
)
from app.conflicts.resolution import resolve_conflicts


def shift(identifier=1, day=date(2026, 10, 5), start=time(9), end=time(17), **kwargs):
    return Shift(identifier, day, start, end, **kwargs)


def window(employee_id, shift_item, start=None, end=None):
    return AvailabilityWindow(employee_id, start or shift_item.starts_at,
                              end or shift_item.ends_at, True)


def workers(count, *, dept="Ops", hours=40, skills=()):
    return tuple(Employee(i + 1, f"Worker {i+1}", department=dept,
                          max_hours_per_week=hours, skills=skills) for i in range(count))


def test_staffing_reduction_is_minimal_and_optimizer_verified():
    item = shift(required_staff=6)
    people = workers(4)
    result = resolve_conflicts(SchedulingInput(people, (item,),
        tuple(window(person.id, item) for person in people)))

    [proposal] = [item for item in result["resolutions"] if item["type"] == "REDUCE_STAFFING_REQUIREMENT"]
    assert result["status"] == "INFEASIBLE"
    assert proposal["feasible"] is proposal["testable"] is True
    assert proposal["details"]["suggested_value"] == 4
    assert proposal["change_size"] == 2


def test_project_hours_reduce_to_first_feasible_value():
    item = shift(project_id=7)
    person = workers(1, skills=(SkillProficiency("Safety"),))[0]
    shifts = tuple(shift(i, day=date(2026, 10, 4+i), project_id=7) for i in range(2))
    result = resolve_conflicts(SchedulingInput(
        (person,), shifts, tuple(window(person.id, current) for current in shifts),
        projects=(Project(7, "Setup", date(2026, 10, 10), "active"),),
        project_requirements=(ProjectRequirement(70, 7, "Safety", required_hours=24),),
    ))

    proposals = [item for item in result["resolutions"] if item["type"] == "ADJUST_PROJECT_REQUIRED_HOURS"]
    assert proposals
    assert proposals[0]["details"]["suggested_value"] == 16
    assert proposals[0]["change_size"] == 8


def test_project_count_can_be_reduced_without_dropping_below_one():
    shifts = (shift(1, project_id=7), shift(2, day=date(2026, 10, 6), project_id=7))
    people = workers(2, skills=(SkillProficiency("Safety"),))
    result = resolve_conflicts(SchedulingInput(
        people, shifts, tuple(window(person.id, current) for person in people for current in shifts),
        projects=(Project(7, "Setup", date(2026, 10, 10), "active"),),
        project_requirements=(ProjectRequirement(70, 7, "Safety", required_count=3),),
    ))

    [proposal] = [item for item in result["resolutions"] if item["type"] == "ADJUST_PROJECT_REQUIRED_COUNT"]
    assert proposal["details"]["suggested_value"] == 2
    assert proposal["change_size"] == 1


def test_deadline_extension_finds_first_feasible_day():
    first = shift(1, day=date(2026, 10, 5), project_id=7)
    second = shift(2, day=date(2026, 10, 7), project_id=7)
    person = workers(1, skills=(SkillProficiency("Safety"),))[0]
    result = resolve_conflicts(SchedulingInput(
        (person,), (first, second), (window(person.id, first), window(person.id, second)),
        projects=(Project(7, "Setup", date(2026, 10, 5), "active"),),
        project_requirements=(ProjectRequirement(70, 7, "Safety", required_hours=16),),
    ))

    [proposal] = [item for item in result["resolutions"] if item["type"] == "EXTEND_PROJECT_DEADLINE"]
    assert proposal["change_size"] == 2
    assert proposal["details"]["suggested_deadline"] == "2026-10-07"


def test_availability_extension_is_minimal_and_verified():
    item = shift()
    person = workers(1)[0]
    result = resolve_conflicts(SchedulingInput((person,), (item,),
        (window(person.id, item, end=datetime(2026, 10, 5, 13)),)))

    [proposal] = [item for item in result["resolutions"] if item["type"] == "EXTEND_AVAILABILITY"]
    assert proposal["change_size"] == 4
    assert proposal["details"]["old_end_time"] == "13:00"
    assert proposal["details"]["new_end_time"] == "17:00"


def test_department_exception_names_and_tests_specific_employee():
    item = shift(department="Ops")
    person = workers(1, dept="Logistics")[0]
    result = resolve_conflicts(SchedulingInput((person,), (item,), (window(person.id, item),)))

    [proposal] = [item for item in result["resolutions"] if item["type"] == "RELAX_DEPARTMENT_RESTRICTION"]
    assert proposal["affected_employee_ids"] == [person.id]
    assert proposal["details"]["verified_department_assignments"] == [(person.id, item.id)]


def test_two_change_search_finds_pair_when_neither_single_change_is_enough():
    first = shift(1, day=date(2026, 10, 5))
    second = shift(2, day=date(2026, 10, 6))
    person = workers(1)[0]
    availability = (
        window(person.id, first, end=datetime(2026, 10, 5, 13)),
        window(person.id, second, end=datetime(2026, 10, 6, 13)),
    )
    result = resolve_conflicts(SchedulingInput((person,), (first, second), availability))

    [proposal] = [item for item in result["resolutions"] if item["type"] == "MULTI_CHANGE_REPAIR"]
    assert proposal["feasible"] is True
    assert len(proposal["details"]) == 2
    assert proposal["affected_shift_ids"] == [1, 2]


def test_already_feasible_returns_no_conflicts_or_resolutions():
    item = shift()
    person = workers(1)[0]
    assert resolve_conflicts(SchedulingInput((person,), (item,), (window(person.id, item),))) == {
        "status": "ALREADY_FEASIBLE", "conflicts": [], "resolutions": [],
    }


def test_leave_is_informational_and_is_never_changed_or_marked_feasible():
    item = shift()
    person = workers(1)[0]
    result = resolve_conflicts(SchedulingInput(
        (person,), (item,), (window(person.id, item),),
        leave=(LeavePeriod(person.id, item.date, item.date, "approved"),),
    ))

    [proposal] = [item for item in result["resolutions"] if item["type"] == "LEAVE_CHANGE_REQUIRED"]
    assert proposal["testable"] is False
    assert proposal["feasible"] is False


def test_overtime_remains_informational_until_optimizer_supports_it():
    item = shift()
    person = workers(1, hours=4)[0]
    result = resolve_conflicts(SchedulingInput((person,), (item,), (window(person.id, item),)))

    [proposal] = [item for item in result["resolutions"] if item["type"] == "OVERTIME_UNAVAILABLE"]
    assert proposal["testable"] is False
    assert proposal["feasible"] is False


def test_no_testable_repair_preserves_diagnostics_with_no_feasible_proposals():
    item = shift(required_staff=1)
    result = resolve_conflicts(SchedulingInput((), (item,), ()))

    assert result["status"] == "INFEASIBLE"
    assert result["conflicts"]
    assert result["resolutions"] == []


def test_resolution_endpoint_does_not_write_schedule_or_change_input_rows(client):
    department = client.post("/api/departments", json={"name": "Operations"}).json()
    person = client.post("/api/employees", json={"name": "Worker", "email": "resolve@example.test",
        "department_id": department["id"], "max_hours_per_week": 40}).json()
    shift_row = client.post("/api/shifts", json={"date": "2026-10-05", "start_time": "09:00",
        "end_time": "17:00", "department_id": department["id"], "required_staff": 2}).json()
    client.post("/api/availability", json={"employee_id": person["id"], "date": "2026-10-05",
        "start_time": "09:00", "end_time": "17:00", "available": True})
    from app.database import get_db
    from app import models
    from app.main import app
    db = next(app.dependency_overrides[get_db]())
    try:
        before = {
            "employees": db.query(models.Employee).count(),
            "shifts": db.query(models.Shift).count(),
            "availability": db.query(models.Availability).count(),
            "required_staff": db.get(models.Shift, shift_row["id"]).required_staff,
            "schedules": db.query(models.Schedule).count(),
            "assignments": db.query(models.ScheduleAssignment).count(),
        }
    finally:
        db.close()

    response = client.post("/api/optimization/resolve-conflict", json={
        "start_date": "2026-10-05", "end_date": "2026-10-05",
    })

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "INFEASIBLE"
    assert payload["conflicts"]
    assert any(item["type"] == "REDUCE_STAFFING_REQUIREMENT" and item["feasible"]
               for item in payload["resolutions"])
    db = next(app.dependency_overrides[get_db]())
    try:
        after = {
            "employees": db.query(models.Employee).count(),
            "shifts": db.query(models.Shift).count(),
            "availability": db.query(models.Availability).count(),
            "required_staff": db.get(models.Shift, shift_row["id"]).required_staff,
            "schedules": db.query(models.Schedule).count(),
            "assignments": db.query(models.ScheduleAssignment).count(),
        }
    finally:
        db.close()
    assert after == before


def test_resolution_endpoint_returns_already_feasible_shape(client):
    department = client.post("/api/departments", json={"name": "Operations"}).json()
    person = client.post("/api/employees", json={"name": "Worker", "email": "ready@example.test",
        "department_id": department["id"], "max_hours_per_week": 40}).json()
    client.post("/api/shifts", json={"date": "2026-10-05", "start_time": "09:00",
        "end_time": "17:00", "department_id": department["id"], "required_staff": 1})
    client.post("/api/availability", json={"employee_id": person["id"], "date": "2026-10-05",
        "start_time": "09:00", "end_time": "17:00", "available": True})

    response = client.post("/api/optimization/resolve-conflict", json={
        "start_date": "2026-10-05", "end_date": "2026-10-05",
    })

    assert response.status_code == 200
    assert response.json() == {"status": "ALREADY_FEASIBLE", "conflicts": [], "resolutions": []}
