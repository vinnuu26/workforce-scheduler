from test_optimization_integration import seeded_workforce


def test_employee_skill_proficiency_is_persisted_and_enforced_for_project(client):
    _departments, employees, shifts = seeded_workforce(client)
    employee = employees[0]
    skill = client.get('/api/skills').json()[0]
    response = client.get(f"/api/employees/{employee['id']}").json()
    assert response['skills'][0]['proficiency'] == 1
    project = client.post('/api/projects', json={'name': 'Proficiency project', 'status': 'active'}).json()
    shift_id = shifts[0]['id']
    client.put(f"/api/shifts/{shift_id}", json={'date': '2026-10-05', 'department_id': employee['department_id'], 'template_id': 1, 'project_id': project['id'], 'required_staff': 1})
    client.post(f"/api/projects/{project['id']}/requirements", json={'skill_id': skill['id'], 'role': 'qualified', 'quantity': 1, 'required_hours': 0, 'minimum_proficiency': 2})
    for other in employees[1:]:
        client.put(f"/api/employees/{other['id']}", json={'name': other['name'], 'email': other['email'], 'department_id': other['department_id'], 'active': False, 'hourly_rate': other['hourly_rate'], 'max_hours_per_week': other['max_hours_per_week']})
    low = client.post('/api/optimization/generate', json={'start_date': '2026-10-05', 'end_date': '2026-10-05', 'project_id': project['id']}).json()
    assert low['status'] == 'INFEASIBLE'
    updated = client.put(f"/api/employees/{employee['id']}/skills/{skill['id']}", json={'proficiency': 2})
    assert updated.status_code == 200
    assert next(row for row in updated.json()['skills'] if row['id'] == skill['id'])['proficiency'] == 2
    high = client.post('/api/optimization/generate', json={'start_date': '2026-10-05', 'end_date': '2026-10-05', 'project_id': project['id']}).json()
    assert high['status'] == 'FEASIBLE'
    assert high['assignments'][0]['employee_id'] == employee['id']
    above = client.put(f"/api/employees/{employee['id']}/skills/{skill['id']}", json={'proficiency': 3})
    assert above.status_code == 200
    assert client.post('/api/optimization/generate', json={'start_date': '2026-10-05', 'end_date': '2026-10-05', 'project_id': project['id']}).json()['status'] == 'FEASIBLE'


def test_apply_reschedule_requires_confirmation_and_persists_verified_candidate(client):
    department = client.post('/api/departments', json={'name': 'Ops'}).json()
    employees = [client.post('/api/employees', json={'name': f'Worker {i}', 'email': f'w{i}@example.test', 'department_id': department['id']}).json() for i in range(2)]
    shift = client.post('/api/shifts', json={'date': '2026-10-05', 'department_id': department['id'], 'start_time': '09:00', 'end_time': '13:00'}).json()
    for employee in employees:
        client.post('/api/availability', json={'employee_id': employee['id'], 'date': '2026-10-05', 'start_time': '00:00', 'end_time': '23:59', 'available': True})
    generated = client.post('/api/optimization/generate', json={'start_date': '2026-10-05', 'end_date': '2026-10-05'}).json()
    schedule_id = generated['schedule_id']
    original = client.get(f'/api/schedules/{schedule_id}/assignments').json()
    assignment = original[0]
    denied = client.post('/api/optimization/apply-reschedule', json={'schedule_id': schedule_id, 'assignment_id': assignment['id'], 'confirmed': False})
    assert denied.status_code == 422
    assert client.get(f'/api/schedules/{schedule_id}/assignments').json() == original
    response = client.post('/api/optimization/apply-reschedule', json={'schedule_id': schedule_id, 'assignment_id': assignment['id'], 'confirmed': True})
    assert response.status_code == 200, response.text
    assert response.json()['persisted'] is True
    updated = client.get(f'/api/schedules/{schedule_id}/assignments').json()
    assert len(updated) == len(original) == 1
    assert updated[0]['employee_id'] != assignment['employee_id']
    stored = client.get(f'/api/schedules/{schedule_id}').json()
    assert stored['total_cost'] == response.json()['total_cost']
import os
import sqlite3
import subprocess


def test_demo_seed_is_idempotent_and_creates_multiple_skill_levels(tmp_path):
    db_path = tmp_path / 'seed.sqlite'
    env = {**os.environ, 'DATABASE_URL': f'sqlite:///{db_path.as_posix()}'}
    script = 'scripts/seed_demo_data.py'
    executable = './venv/Scripts/python.exe'
    for _ in range(2):
        run = subprocess.run([executable, script], cwd=__import__('pathlib').Path(__file__).parents[1], env=env, capture_output=True, text=True)
        assert run.returncode == 0, run.stderr
    with sqlite3.connect(db_path) as connection:
        levels = {row[0] for row in connection.execute('SELECT DISTINCT proficiency FROM employee_skills')}
        employees = connection.execute('SELECT COUNT(*) FROM employees').fetchone()[0]
        shifts = connection.execute('SELECT COUNT(*) FROM shifts').fetchone()[0]
    assert levels == {1, 2, 3, 4, 5}
    assert employees == 12
    assert shifts == 22
import sqlite3
from pathlib import Path


def test_employee_proficiency_migration_keeps_rows_and_defaults_level_one():
    connection = sqlite3.connect(':memory:')
    connection.executescript('CREATE TABLE employee_skills(employee_id INTEGER, skill_id INTEGER, PRIMARY KEY(employee_id, skill_id)); INSERT INTO employee_skills VALUES (4, 9);')
    migration = Path(__file__).parents[1] / 'migrations' / '0003_employee_skill_proficiency.sql'
    connection.executescript(migration.read_text(encoding='utf-8'))
    assert connection.execute('SELECT employee_id, skill_id, proficiency FROM employee_skills').fetchone() == (4, 9, 1)
    connection.close()
import pytest
from app import models


def test_apply_reschedule_rolls_back_if_replacement_fails(client, monkeypatch):
    department = client.post('/api/departments', json={'name': 'Rollback Ops'}).json()
    employees = [client.post('/api/employees', json={'name': f'Person {i}', 'email': f'rb{i}@example.test', 'department_id': department['id']}).json() for i in range(2)]
    shift = client.post('/api/shifts', json={'date': '2026-10-05', 'department_id': department['id'], 'start_time': '09:00', 'end_time': '13:00'}).json()
    for employee in employees:
        client.post('/api/availability', json={'employee_id': employee['id'], 'date': '2026-10-05', 'start_time': '00:00', 'end_time': '23:59', 'available': True})
    schedule = client.post('/api/optimization/generate', json={'start_date': '2026-10-05', 'end_date': '2026-10-05'}).json()
    before = client.get(f"/api/schedules/{schedule['schedule_id']}/assignments").json()
    with monkeypatch.context() as patcher:
        patcher.setattr(models, 'ScheduleExplanation', lambda: None)
        with pytest.raises(Exception):
            client.post('/api/optimization/apply-reschedule', json={'schedule_id': schedule['schedule_id'], 'assignment_id': before[0]['id'], 'confirmed': True})
    after = client.get(f"/api/schedules/{schedule['schedule_id']}/assignments").json()
    assert after == before
