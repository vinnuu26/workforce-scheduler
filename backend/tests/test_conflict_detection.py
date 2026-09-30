from datetime import date, datetime, time

import pytest

from app.optimizer.model import (
    AvailabilityWindow,
    Employee,
    LeavePeriod,
    Project,
    ProjectRequirement,
    RequiredSkill,
    SchedulingInput,
    Shift,
    SkillProficiency,
)
from app.services.conflict_detection_service import detect_conflicts


DAY = date(2026, 10, 5)


def make_shift(**overrides):
    values = dict(id=1, date=DAY, start_time=time(8), end_time=time(16), required_staff=1)
    return Shift(**(values | overrides))


def make_employee(**overrides):
    values = dict(id=1, name="Worker", department="Operations")
    return Employee(**(values | overrides))


def available(employee, *shifts):
    return tuple(AvailabilityWindow(
        employee.id, shift.starts_at, shift.ends_at, True,
    ) for shift in shifts)


def conflicts_for(data, kind):
    return [item for item in detect_conflicts(data) if item["type"] == kind]


def test_staffing_shortage_reports_required_available_gap_and_shift():
    shift = make_shift(required_staff=2)
    data = SchedulingInput((make_employee(),), (shift,), available(make_employee(), shift))

    [conflict] = conflicts_for(data, "STAFFING_SHORTAGE")

    assert conflict["shift_id"] == 1
    assert (conflict["required"], conflict["available"], conflict["gap"]) == (2, 1, 1)


def test_skill_shortage_reports_only_workers_with_required_proficiency():
    shift = make_shift(required_skills=(RequiredSkill("Forklift", minimum_proficiency=2),))
    employee = make_employee(skills=(SkillProficiency("Forklift", 1),))
    data = SchedulingInput((employee,), (shift,), available(employee, shift))

    [conflict] = conflicts_for(data, "SKILL_SHORTAGE")

    assert conflict["skill"] == "Forklift"
    assert conflict["required"] == 1
    assert conflict["available"] == 0
    assert conflict["employee_ids"] == []


def test_availability_shortage_requires_full_shift_coverage():
    shift = make_shift()
    employee = make_employee()
    partial = AvailabilityWindow(employee.id, shift.starts_at, datetime(2026, 10, 5, 15), True)

    [conflict] = conflicts_for(SchedulingInput((employee,), (shift,), (partial,)), "AVAILABILITY_SHORTAGE")

    assert conflict["required"] == 1
    assert conflict["available"] == 0
    assert employee.id in conflict["blocked_employee_ids"]


def test_approved_leave_shortage_is_reported():
    shift = make_shift()
    employee = make_employee()
    data = SchedulingInput((employee,), (shift,), available(employee, shift),
                           (LeavePeriod(employee.id, DAY, DAY, "approved"),))

    [conflict] = conflicts_for(data, "LEAVE_CONFLICT")

    assert conflict["employee_ids"] == [employee.id]
    assert (conflict["required"], conflict["available"], conflict["gap"]) == (1, 0, 1)


def test_single_shift_over_weekly_maximum_is_reported():
    shift = make_shift()
    employee = make_employee(max_hours_per_week=4)
    data = SchedulingInput((employee,), (shift,), available(employee, shift))

    [conflict] = conflicts_for(data, "MAX_HOURS_CONFLICT")

    assert conflict["required"] == 1
    assert conflict["available"] == 0


def test_forced_rest_violation_is_reported_for_both_shifts():
    first = make_shift(id=1, start_time=time(8), end_time=time(12), minimum_rest_hours=8)
    second = make_shift(id=2, start_time=time(16), end_time=time(20))
    employee = make_employee()
    data = SchedulingInput((employee,), (first, second), available(employee, first, second))

    [conflict] = conflicts_for(data, "REST_CONFLICT")

    assert conflict["shift_ids"] == [1, 2]
    assert conflict["employee_ids"] == [employee.id]
    assert conflict["minimum_rest_hours"] == 8


def test_department_shortage_is_distinguished_from_staffing_shortage():
    shift = make_shift(department="Operations")
    employee = make_employee(department="Logistics")
    data = SchedulingInput((employee,), (shift,), available(employee, shift))

    [conflict] = conflicts_for(data, "DEPARTMENT_CONFLICT")

    assert conflict["required"] == 1
    assert conflict["available"] == 0


def test_project_requirement_shortage_uses_qualified_capacity_upper_bound():
    shift = make_shift(project_id=7)
    employee = make_employee(skills=(SkillProficiency("Safety"),))
    data = SchedulingInput(
        (employee,), (shift,), available(employee, shift),
        projects=(Project(7, "Warehouse setup", date(2026, 10, 10), "active"),),
        project_requirements=(ProjectRequirement(9, 7, "Safety", required_count=1,
                                                 required_hours=16, deadline=date(2026, 10, 10)),),
    )

    [conflict] = conflicts_for(data, "PROJECT_REQUIREMENT_SHORTAGE")

    assert conflict["project_id"] == 7
    assert conflict["requirement_id"] == 9
    assert conflict["required"] == 16
    assert conflict["available"] == 8
    assert conflict["gap"] == 8


def test_deadline_conflict_compares_before_deadline_and_all_associated_dates():
    before = make_shift(id=1, date=date(2026, 10, 5), project_id=7)
    after = make_shift(id=2, date=date(2026, 10, 6), project_id=7)
    employee = make_employee(skills=(SkillProficiency("Safety"),))
    data = SchedulingInput(
        (employee,), (before, after), available(employee, before, after),
        projects=(Project(7, "Warehouse setup", date(2026, 10, 5), "active"),),
        project_requirements=(ProjectRequirement(9, 7, "Safety", required_count=1,
                                                 required_hours=16, deadline=date(2026, 10, 5)),),
    )

    [conflict] = conflicts_for(data, "DEADLINE_CONFLICT")

    assert conflict["available_qualified_hours_before_deadline"] == 8
    assert conflict["available_qualified_hours_all_dates"] == 16


def test_diagnostics_have_stable_structured_fields_and_unique_ids():
    shift = make_shift(required_staff=2)
    employee = make_employee()
    data = SchedulingInput((employee,), (shift,), available(employee, shift))
    detected = conflicts_for(data, "STAFFING_SHORTAGE")
    assert detected
    conflict = detected[0]
    assert conflict["conflict_id"] and conflict["severity"] == "CRITICAL"
    assert conflict["message"] and conflict["constraints"]
    diagnostics = detect_conflicts(data)
    assert len({item["conflict_id"] for item in diagnostics}) == len(diagnostics)
