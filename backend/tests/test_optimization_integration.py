from datetime import date

from app import models


def seeded_workforce(client):
    departments = [client.post("/api/departments", json={"name": name}).json()
                   for name in ("Operations", "Logistics")]
    skills = [client.post("/api/skills", json={"name": name}).json()
              for name in ("Forklift", "Safety", "Dispatch", "First Aid")]
    template = client.post("/api/shift-templates", json={
        "name": "Day coverage", "start_time": "09:00", "end_time": "13:00",
    }).json()
    employees = []
    for index, (name, department_index, skill_index) in enumerate([
        ("Ari Chen", 0, 0), ("Bo Singh", 0, 1), ("Cam Das", 1, 2),
        ("Dee Rao", 1, 3), ("Eli Shah", 0, 0),
    ]):
        employee = client.post("/api/employees", json={
            "name": name, "email": f"worker{index}@example.test",
            "department_id": departments[department_index]["id"],
            "hourly_rate": 20 + index, "max_hours_per_week": 40,
        }).json()
        client.post(f"/api/employees/{employee['id']}/skills", json={"skill_id": skills[skill_index]["id"]})
        employees.append(employee)
    shifts = []
    shift_specs = [("2026-10-05", 0, 0), ("2026-10-05", 1, 2),
                   ("2026-10-06", 0, 1), ("2026-10-06", 1, 3)]
    for day, department_index, skill_index in shift_specs:
        shift = client.post("/api/shifts", json={
            "date": day, "department_id": departments[department_index]["id"],
            "template_id": template["id"], "required_staff": 1,
        }).json()
        client.post(f"/api/shifts/{shift['id']}/skills", json={"skill_id": skills[skill_index]["id"]})
        shifts.append(shift)
    for employee in employees:
        for day in ("2026-10-05", "2026-10-06"):
            client.post("/api/availability", json={
                "employee_id": employee["id"], "date": day,
                "start_time": "00:00", "end_time": "23:59", "available": True,
            })
    client.post("/api/leave", json={
        "employee_id": employees[4]["id"], "start_date": "2026-10-05",
        "end_date": "2026-10-05", "status": "approved",
    })
    return departments, employees, shifts


def test_database_schedule_generation_persists_and_retrieves_assignments(client):
    departments, employees, shifts = seeded_workforce(client)
    response = client.post("/api/optimization/generate", json={
        "start_date": "2026-10-05", "end_date": "2026-10-06",
    })
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "FEASIBLE"
    assert result["solver_status"] in {"FEASIBLE", "OPTIMAL"}
    assert result["schedule_id"] is not None
    assert result["total_required_staff"] == result["total_assigned_staff"] == 4
    assert result["total_excess_staff"] == 0
    assert result["objective"]["excess_staff"] == 0
    assert len(result["assignments"]) == 4
    assert all(item["employee_id"] in {employee["id"] for employee in employees} for item in result["assignments"])
    assert all(item["shift_id"] in {shift["id"] for shift in shifts} for item in result["assignments"])
    assert all(item["regular_hours"] == 4 and item["overtime_hours"] == 0 for item in result["assignments"])
    assert all(item["cost"] == item["hours"] * item["hourly_rate"] for item in result["assignments"])
    assert all(item["department"] in {"Operations", "Logistics"} for item in result["assignments"])
    assert result["total_cost"] == sum(item["cost"] for item in result["assignments"])
    assert result["total_regular_hours"] == 16

    schedule = client.get(f"/api/schedules/{result['schedule_id']}")
    assert schedule.status_code == 200
    assert schedule.json()["total_cost"] == result["total_cost"]
    listed = client.get("/api/schedules").json()
    assert any(item["id"] == result["schedule_id"] for item in listed)
    saved = client.get(f"/api/schedules/{result['schedule_id']}/assignments").json()
    assert len(saved) == 4
    assert {item["employee_id"] for item in saved} == {item["employee_id"] for item in result["assignments"]}
    assert {item["shift_id"] for item in saved} == {item["shift_id"] for item in result["assignments"]}
    assert all(item["shift_name"] == "Day coverage" and item["hours"] == 4 for item in saved)


def test_infeasible_result_is_not_persisted(client):
    _departments, _employees, shifts = seeded_workforce(client)
    shift_id = shifts[0]["id"]
    updated = client.put(f"/api/shifts/{shift_id}", json={
        "date": "2026-10-05", "department_id": shifts[0]["department_id"],
        "template_id": shifts[0]["template_id"], "required_staff": 10,
    })
    assert updated.status_code == 200
    before = len(client.get("/api/schedules").json())
    response = client.post("/api/optimization/generate", json={
        "start_date": "2026-10-05", "end_date": "2026-10-06",
    })
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "INFEASIBLE"
    assert result["schedule_id"] is None
    assert result["assignments"] == []
    assert len(client.get("/api/schedules").json()) == before


def test_period_and_department_filtering(client):
    departments, _employees, shifts = seeded_workforce(client)
    result = client.post("/api/optimization/generate", json={
        "start_date": "2026-10-05", "end_date": "2026-10-05",
        "department_id": departments[0]["id"],
    })
    assert result.status_code == 200, result.text
    payload = result.json()
    assert payload["status"] == "FEASIBLE"
    assert payload["total_required_staff"] == 1
    assert len(payload["assignments"]) == 1
    assert payload["assignments"][0]["shift_id"] == shifts[0]["id"]


def test_invalid_request_and_malformed_availability_are_validation_errors(client):
    assert client.post("/api/optimization/generate", json={
        "start_date": "2026-10-07", "end_date": "2026-10-01",
    }).status_code == 422
    _departments, employees, _shifts = seeded_workforce(client)
    # Mutate one persisted availability row to represent legacy/malformed data.
    from app.database import get_db
    db = next(apply_override_db(client))
    try:
        row = db.query(models.Availability).filter_by(employee_id=employees[0]["id"]).first()
        row.end_time = None
        db.commit()
    finally:
        db.close()
    response = client.post("/api/optimization/generate", json={
        "start_date": "2026-10-05", "end_date": "2026-10-06",
    })
    assert response.status_code == 422
    assert "valid start_time and end_time" in response.json()["detail"]


def apply_override_db(client):
    """Access the test client's configured request-scoped test session factory."""
    from app.main import app
    override = app.dependency_overrides
    yield from override[next(dep for dep in override if dep.__name__ == "get_db")]()
