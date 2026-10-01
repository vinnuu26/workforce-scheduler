import json

from test_optimization_integration import seeded_workforce


def test_generation_persists_assignment_explanations_and_reschedule_preview_is_non_persistent(client):
    _departments, _employees, _shifts = seeded_workforce(client)
    generated = client.post("/api/optimization/generate", json={
        "start_date": "2026-10-05", "end_date": "2026-10-06",
    })
    assert generated.status_code == 200, generated.text
    result = generated.json()
    schedule_id = result["schedule_id"]
    saved_explanations = client.get(f"/api/schedules/{schedule_id}/explanations")
    assert saved_explanations.status_code == 200
    assert len(saved_explanations.json()) == len(result["assignments"])
    details = json.loads(saved_explanations.json()[0]["details"])
    assert "employee_id" in details and "shift_id" in details
    assert "optimizer_objective" in details and "fairness_metrics" in details
    assert "preference_metrics" in details and "project_metrics" in details
    assert details["eligibility_checks"]["available_for_complete_shift"] is True

    original_assignments = client.get(f"/api/schedules/{schedule_id}/assignments").json()
    schedule_count = len(client.get("/api/schedules").json())
    preview = client.post("/api/optimization/reschedule-preview", json={
        "schedule_id": schedule_id, "assignment_id": original_assignments[0]["id"],
    })
    assert preview.status_code == 200, preview.text
    assert preview.json()["persisted"] is False
    assert preview.json()["source_schedule_id"] == schedule_id
    assert len(client.get("/api/schedules").json()) == schedule_count
    assert client.get(f"/api/schedules/{schedule_id}/assignments").json() == original_assignments
    assert len(client.get("/api/leave").json()) == 1


def test_reschedule_preview_rejects_assignment_from_another_schedule(client):
    _departments, _employees, _shifts = seeded_workforce(client)
    generated = client.post("/api/optimization/generate", json={
        "start_date": "2026-10-05", "end_date": "2026-10-06",
    }).json()
    assignment = client.get(f"/api/schedules/{generated['schedule_id']}/assignments").json()[0]
    response = client.post("/api/optimization/reschedule-preview", json={
        "schedule_id": generated["schedule_id"] + 99, "assignment_id": assignment["id"],
    })
    assert response.status_code == 422
