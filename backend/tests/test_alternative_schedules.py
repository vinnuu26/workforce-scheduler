from datetime import date


def _employee(client, name, email, department_id, skills=(), max_hours=40, rate=20):
    result = client.post("/api/employees", json={"name": name, "email": email,
        "department_id": department_id, "max_hours_per_week": max_hours, "hourly_rate": rate}).json()
    for skill_id in skills:
        assert client.post(f"/api/employees/{result['id']}/skills", json={"skill_id": skill_id}).status_code == 201
    return result


def _availability(client, employee, day):
    response = client.post("/api/availability", json={"employee_id": employee["id"], "date": day,
        "start_time": "00:00", "end_time": "23:59", "available": True})
    assert response.status_code == 201


def test_alternatives_endpoint_returns_unique_hard_valid_schedules_and_metrics(client):
    department = client.post("/api/departments", json={"name": "Ops alternatives"}).json()
    other_department = client.post("/api/departments", json={"name": "Other alternatives"}).json()
    skill = client.post("/api/skills", json={"name": "Certified Python"}).json()
    employees = [
        _employee(client, f"Worker {i}", f"alternative{i}@example.test", department["id"], [skill["id"]])
        for i in (1, 2)
    ]
    low_skill = _employee(client, "Junior", "junior-alternative@example.test", department["id"])
    wrong_department = _employee(client, "Other dept", "other-alternative@example.test", other_department["id"], [skill["id"]])
    project = client.post("/api/projects", json={"name": "Alternatives project", "status": "active",
                                                   "deadline": "2026-10-02"}).json()
    requirement = client.post(f"/api/projects/{project['id']}/requirements", json={
        "skill_id": skill["id"], "quantity": 1, "required_hours": 8, "minimum_proficiency": 1,
    })
    assert requirement.status_code == 201
    shifts = []
    for day in ("2026-10-01", "2026-10-02"):
        shift = client.post("/api/shifts", json={"date": day, "start_time": "08:00", "end_time": "12:00",
            "department_id": department["id"], "project_id": project["id"], "required_staff": 1}).json()
        shifts.append(shift)
        for employee in (*employees, low_skill, wrong_department):
            _availability(client, employee, day)
        assert client.post(f"/api/shifts/{shift['id']}/skills", json={
            "skill_id": skill["id"], "minimum_proficiency": 1,
        }).status_code == 201
    # The second qualified employee cannot take the first shift due to approved leave.
    assert client.post("/api/leave", json={"employee_id": employees[1]["id"],
        "start_date": "2026-10-01", "end_date": "2026-10-01", "status": "approved"}).status_code == 201

    before_schedules = len(client.get("/api/schedules").json())
    response = client.post("/api/optimization/alternatives", json={
        "start_date": "2026-10-01", "end_date": "2026-10-02", "project_id": project["id"],
        "department_id": department["id"], "count": 3,
    })
    result = response.json()

    assert response.status_code == 200
    assert result["status"] in {"SUCCESS", "PARTIAL"}
    assert result["requested_count"] == 3
    assert 2 <= result["generated_count"] <= 3
    assert result["status"] == ("SUCCESS" if result["generated_count"] == 3 else "PARTIAL")
    signatures = [frozenset((a["employee_id"], a["shift_id"]) for a in alt["assignments"])
                  for alt in result["alternatives"]]
    assert len(set(signatures)) == len(signatures)
    assert all(alt["alternative_id"] == i for i, alt in enumerate(result["alternatives"], 1))
    for alternative in result["alternatives"]:
        assert alternative["status"] in {"OPTIMAL", "FEASIBLE"}
        assert alternative["total_excess_staff"] == alternative["total_assigned_staff"] - alternative["total_required_staff"]
        assert alternative["total_assigned_staff"] >= 2
        assert alternative["assignment_count"] == len(alternative["assignments"])
        assert alternative["total_cost"] == sum(a["cost"] for a in alternative["assignments"])
        assert "satisfaction_percentage" in alternative["preference"]
        assert "hour_balance_score" in alternative["fairness"]
        assert alternative["projects"][0]["completion_percentage"] == 100
        assert all(a["project_id"] == project["id"] for a in alternative["assignments"])
        assert all(a["employee_id"] in {e["id"] for e in (*employees, low_skill)}
                   for a in alternative["assignments"])
        assert all(a["shift_id"] in {s["id"] for s in shifts} for a in alternative["assignments"])
        assert all(sum(a["shift_id"] == shift["id"] for a in alternative["assignments"]) >= shift["required_staff"]
                   for shift in shifts)
        assert all(any(a["shift_id"] == shift["id"] and a["employee_id"] in {e["id"] for e in employees}
                       for a in alternative["assignments"]) for shift in shifts)
        assert all(a["department"] == "Ops alternatives" for a in alternative["assignments"])
        assert all(a["employee_id"] != employees[1]["id"] or a["shift_date"] != "2026-10-01"
                   for a in alternative["assignments"])
    two = client.post("/api/optimization/alternatives", json={
        "start_date": "2026-10-01", "end_date": "2026-10-02", "project_id": project["id"],
        "department_id": department["id"], "count": 2,
    }).json()
    assert two["status"] == "SUCCESS"
    assert two["generated_count"] == 2
    assert len(client.get("/api/schedules").json()) == before_schedules


def test_alternative_count_validation_and_default(client):
    department = client.post("/api/departments", json={"name": "Count validation"}).json()
    employee = _employee(client, "Only", "count-only@example.test", department["id"])
    shift = client.post("/api/shifts", json={"date": "2026-10-01", "start_time": "08:00",
        "end_time": "12:00", "department_id": department["id"]}).json()
    _availability(client, employee, "2026-10-01")
    request = {"start_date": "2026-10-01", "end_date": "2026-10-01"}
    assert client.post("/api/optimization/alternatives", json={**request, "count": 0}).status_code == 422
    assert client.post("/api/optimization/alternatives", json={**request, "count": 6}).status_code == 422
    default = client.post("/api/optimization/alternatives", json=request).json()
    assert default["requested_count"] == 3


def test_only_one_solution_returns_partial_and_does_not_persist(client):
    department = client.post("/api/departments", json={"name": "Unique solution"}).json()
    employee = _employee(client, "Forced worker", "forced@example.test", department["id"])
    for day in ("2026-10-01", "2026-10-02"):
        client.post("/api/shifts", json={"date": day, "start_time": "08:00", "end_time": "12:00",
            "department_id": department["id"]})
        _availability(client, employee, day)
    before = len(client.get("/api/schedules").json())
    result = client.post("/api/optimization/alternatives", json={
        "start_date": "2026-10-01", "end_date": "2026-10-02", "count": 3,
    }).json()
    assert result["status"] == "PARTIAL"
    assert result["generated_count"] == 1
    assert len(result["alternatives"]) == 1
    assert len(client.get("/api/schedules").json()) == before


def test_infeasible_alternatives_return_zero_without_persistence(client):
    department = client.post("/api/departments", json={"name": "Impossible alternatives"}).json()
    employee = _employee(client, "Part time", "part-time-alternative@example.test", department["id"], max_hours=4)
    client.post("/api/shifts", json={"date": "2026-10-01", "start_time": "08:00", "end_time": "16:00",
        "department_id": department["id"]})
    _availability(client, employee, "2026-10-01")
    before = len(client.get("/api/schedules").json())
    result = client.post("/api/optimization/alternatives", json={
        "start_date": "2026-10-01", "end_date": "2026-10-01", "count": 3,
    }).json()
    assert result == {"status": "INFEASIBLE", "requested_count": 3,
                      "generated_count": 0, "alternatives": []}
    assert len(client.get("/api/schedules").json()) == before
