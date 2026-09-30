from datetime import date, datetime, time

import pytest

from app.optimizer.model import AvailabilityWindow, Employee, EmployeePreference, LeavePeriod, RequiredSkill, SchedulingInput, Shift, SkillProficiency
from app.services.scheduling_service import generate_schedule


def window(employee_id, start="2026-10-05T00:00", end="2026-10-07T12:00"):
    return AvailabilityWindow(employee_id, datetime.fromisoformat(start), datetime.fromisoformat(end))

def sample_input():
    employees=(
        Employee("E1", "Rahul", "IT", (SkillProficiency("Python"), SkillProficiency("SQL")), 40, 30),
        Employee("E2", "Priya", "IT", (SkillProficiency("Python"),), 40, 25),
        Employee("E3", "Aman", "IT", (SkillProficiency("SQL"),), 40, 22),
        Employee("E4", "Ravi", "QA", (SkillProficiency("Testing"),), 32, 24),
        Employee("E5", "Kiran", "IT", (SkillProficiency("Python"), SkillProficiency("SQL")), 24, 18),
    )
    shifts=(
        Shift("MORNING", date(2026,10,5), time(8), time(12), 2, "Morning IT", "IT",
              (RequiredSkill("Python"), RequiredSkill("SQL")), minimum_rest_hours=8),
        Shift("EVENING", date(2026,10,5), time(17), time(21), 1, "Evening IT", "IT",
              (RequiredSkill("Python"),), minimum_rest_hours=8),
        Shift("NIGHT", date(2026,10,5), time(22), time(6), 1, "Night IT", "IT",
              (RequiredSkill("SQL"),), minimum_rest_hours=8),
        Shift("QA", date(2026,10,6), time(8), time(12), 1, "QA Testing", "QA",
              (RequiredSkill("Testing"),)),
    )
    availability=tuple(window(employee.id) for employee in employees)
    leave=(LeavePeriod("E5", date(2026,10,5), date(2026,10,6), "approved"),)
    return SchedulingInput(employees, shifts, availability, leave)

def run(data):
    return generate_schedule(data)

def test_sample_data_is_feasible_and_meets_staffing_hours_and_cost():
    data=sample_input()
    result=run(data)
    assert result["status"] == "FEASIBLE"
    assert result["solver_status"] in {"FEASIBLE", "OPTIMAL"}
    assert result["unassigned_shifts"] == []
    counts={shift.id:0 for shift in data.shifts}
    for assignment in result["assignments"]:
        counts[assignment["shift_id"]]+=1
        assert assignment["employee_id"] != "E5"
    for shift in data.shifts:
        assert counts[shift.id] >= shift.required_staff
        for requirement in shift.required_skills:
            qualified={employee.id for employee in data.employees
                        if any(skill.name==requirement.name and skill.proficiency>=requirement.minimum_proficiency
                               for skill in employee.skills)}
            assert sum(item["shift_id"]==shift.id and item["employee_id"] in qualified
                       for item in result["assignments"]) >= requirement.required_count
    assert result["total_overtime_hours"] == 0
    for employee in data.employees:
        assert result["employee_hours"][employee.id] <= employee.max_hours_per_week
        calculated=sum(item["hours"] for item in result["assignments"] if item["employee_id"]==employee.id)
        assert result["employee_hours"][employee.id] == pytest.approx(calculated)
    expected_cost=sum(item["hours"]*next(e.hourly_rate for e in data.employees if e.id==item["employee_id"])
                      for item in result["assignments"])
    assert result["total_cost"] == pytest.approx(expected_cost)
    assert result["total_regular_hours"] == pytest.approx(sum(result["employee_hours"].values()))

def test_approved_leave_prevents_assignment():
    employees=(Employee("leave", "On Leave", "IT"), Employee("free", "Available", "IT"))
    shift=Shift("s", date(2026,10,5), time(9), time(13), department="IT")
    data=SchedulingInput(employees,(shift,),tuple(window(e.id) for e in employees),
                         (LeavePeriod("leave", date(2026,10,5), date(2026,10,5)),))
    result=run(data)
    assert result["status"] == "FEASIBLE"
    assert [a["employee_id"] for a in result["assignments"]] == ["free"]

def test_employee_must_be_available_for_the_complete_shift():
    employees=(Employee("partial", "Partial", "IT"), Employee("full", "Full", "IT"))
    shift=Shift("s", date(2026,10,5), time(8), time(12), department="IT")
    availability=(window("partial", "2026-10-05T08:00", "2026-10-05T10:00"), window("full"))
    result=run(SchedulingInput(employees,(shift,),availability))
    assert result["status"] == "FEASIBLE"
    assert [a["employee_id"] for a in result["assignments"]] == ["full"]

def test_required_skill_counts_only_employees_meeting_proficiency():
    employees=(
        Employee("junior", "Junior", "IT", (SkillProficiency("Python",1),)),
        Employee("senior", "Senior", "IT", (SkillProficiency("Python",3),)),
    )
    shift=Shift("s", date(2026,10,5), time(8), time(12), department="IT",
                required_skills=(RequiredSkill("Python",1,2),))
    result=run(SchedulingInput(employees,(shift,),tuple(window(e.id) for e in employees)))
    assert result["status"] == "FEASIBLE"
    assert [a["employee_id"] for a in result["assignments"]] == ["senior"]

def test_department_restriction_excludes_other_department():
    employees=(Employee("it", "IT", "IT"), Employee("qa", "QA", "QA"))
    shift=Shift("s", date(2026,10,5), time(8), time(12), department="IT")
    result=run(SchedulingInput(employees,(shift,),tuple(window(e.id) for e in employees)))
    assert result["status"] == "FEASIBLE"
    assert [a["employee_id"] for a in result["assignments"]] == ["it"]

def test_overlapping_shifts_are_not_assigned_to_the_same_employee():
    employees=(Employee("a", "A", "IT"), Employee("b", "B", "IT"))
    shifts=(Shift("s1", date(2026,10,5), time(8), time(12), department="IT"),
            Shift("s2", date(2026,10,5), time(11), time(15), department="IT"))
    result=run(SchedulingInput(employees,shifts,tuple(window(e.id) for e in employees)))
    assert result["status"] == "FEASIBLE"
    first={a["employee_id"] for a in result["assignments"] if a["shift_id"]=="s1"}
    second={a["employee_id"] for a in result["assignments"] if a["shift_id"]=="s2"}
    assert first.isdisjoint(second)

def test_minimum_rest_period_is_respected():
    employees=(Employee("a", "A", "IT"), Employee("b", "B", "IT"))
    shifts=(Shift("s1", date(2026,10,5), time(8), time(12), department="IT", minimum_rest_hours=8),
            Shift("s2", date(2026,10,5), time(16), time(20), department="IT"))
    result=run(SchedulingInput(employees,shifts,tuple(window(e.id) for e in employees)))
    assert result["status"] == "FEASIBLE"
    first=next(a["employee_id"] for a in result["assignments"] if a["shift_id"]=="s1")
    second=next(a["employee_id"] for a in result["assignments"] if a["shift_id"]=="s2")
    assert first != second

def test_maximum_weekly_hours_are_hard():
    employee=Employee("e", "E", "IT", max_hours_per_week=8)
    shifts=(Shift("s1", date(2026,10,5), time(8), time(16), department="IT"),
            Shift("s2", date(2026,10,6), time(8), time(16), department="IT"))
    result=run(SchedulingInput((employee,),shifts,(window("e"),)))
    assert result["status"] == "INFEASIBLE"
    assert result["assignments"] == []

def test_inactive_employee_cannot_be_assigned():
    employee=Employee("e", "E", "IT", active=False)
    shift=Shift("s", date(2026,10,5), time(8), time(12), department="IT")
    result=run(SchedulingInput((employee,),(shift,),(window("e"),)))
    assert result["status"] == "INFEASIBLE"
    assert result["assignments"] == []

def test_impossible_staffing_is_infeasible_without_fabricated_assignments():
    employees=(Employee("a", "A", "IT"), Employee("b", "B", "IT"))
    shift=Shift("s", date(2026,10,5), time(8), time(12), required_staff=5, department="IT")
    result=run(SchedulingInput(employees,(shift,),tuple(window(e.id) for e in employees)))
    assert result["status"] == "INFEASIBLE"
    assert result["solver_status"] == "INFEASIBLE"
    assert result["assignments"] == []
    assert result["unassigned_shifts"] == [{"shift_id":"s","shift_name":"Shift"}]
    assert result["total_required_staff"] == 5
    assert result["total_assigned_staff"] == 0
    assert result["total_excess_staff"] == 0

def test_mapping_input_and_cross_department_opt_in():
    data={
        "employees":[{"id":"it","name":"IT worker","department":"IT","skills":{"Python":2}}],
        "shifts":[{"id":"s","date":"2026-10-05","start_time":"08:00","end_time":"12:00",
                    "department":"QA","required_skills":[{"name":"Python","required_count":1,"min_proficiency":2}],
                    "allow_cross_department":True}],
        "availability":[{"employee_id":"it","start":"2026-10-05T00:00","end":"2026-10-06T00:00"}],
    }
    result=run(data)
    assert result["status"] == "FEASIBLE"
    assert result["assignments"][0]["employee_id"] == "it"


def test_excess_staff_is_minimized_and_hard_minimum_is_preserved():
    employees = tuple(Employee(f"e{i}", f"Employee {i}", "IT", hourly_rate=25) for i in range(4))
    shift = Shift("s", date(2026, 10, 5), time(9), time(13), required_staff=2, department="IT")
    data = SchedulingInput(employees, (shift,), tuple(window(employee.id) for employee in employees))

    result = run(data)

    assert result["status"] == "FEASIBLE"
    assert result["total_required_staff"] == 2
    assert result["total_assigned_staff"] == 2
    assert result["total_excess_staff"] == 0
    assert result["objective"]["excess_staff"] == 0


def test_lower_cost_pair_is_selected_when_staffing_is_equal():
    employees = (
        Employee("a", "A", "IT", hourly_rate=100),
        Employee("b", "B", "IT", hourly_rate=100),
        Employee("c", "C", "IT", hourly_rate=50),
        Employee("d", "D", "IT", hourly_rate=50),
    )
    shift = Shift("s", date(2026, 10, 5), time(9), time(13), required_staff=2, department="IT")
    result = run(SchedulingInput(employees, (shift,), tuple(window(item.id) for item in employees)))

    assert result["total_excess_staff"] == 0
    assert result["total_assigned_staff"] == 2
    assert {item["employee_id"] for item in result["assignments"]} == {"c", "d"}
    assert result["total_cost"] == 400


def test_staffing_priority_beats_a_cheaper_overstaffed_alternative():
    employees = (
        Employee("expensive_a", "Expensive A", "IT", (SkillProficiency("A"),), hourly_rate=250),
        Employee("expensive_bc", "Expensive BC", "IT", (SkillProficiency("B"), SkillProficiency("C")), hourly_rate=225),
        Employee("cheap_a", "Cheap A", "IT", (SkillProficiency("A"),), hourly_rate=25),
        Employee("cheap_b", "Cheap B", "IT", (SkillProficiency("B"),), hourly_rate=25),
        Employee("cheap_c", "Cheap C", "IT", (SkillProficiency("C"),), hourly_rate=25),
    )
    shift = Shift(
        "s", date(2026, 10, 5), time(9), time(13), required_staff=2, department="IT",
        required_skills=(RequiredSkill("A"), RequiredSkill("B"), RequiredSkill("C")),
    )
    result = run(SchedulingInput(employees, (shift,), tuple(window(item.id) for item in employees)))

    # Three specialists cost 300 but have one excess assignment. The best
    # exact-staffing pair costs 1000, and the primary staffing objective wins.
    assert result["status"] == "FEASIBLE"
    assert result["total_required_staff"] == 2
    assert result["total_assigned_staff"] == 2
    assert result["total_excess_staff"] == 0
    assert result["total_cost"] == 1000
    assert result["objective"]["excess_staff"] == 0
    assert result["objective"]["labor_cost"] == 1000


def test_result_cost_fields_and_overtime_are_consistent():
    employees = (
        Employee("a", "A", "IT", hourly_rate=50),
        Employee("b", "B", "IT", hourly_rate=75),
    )
    shift = Shift("s", date(2026, 10, 5), time(9), time(13), required_staff=1, department="IT")
    result = run(SchedulingInput(employees, (shift,), tuple(window(item.id) for item in employees)))

    assert result["total_required_staff"] == 1
    assert result["total_assigned_staff"] == 1
    assert result["total_excess_staff"] == 0
    assert result["total_cost"] == 200
    assert result["objective"]["labor_cost"] == result["total_cost"]
    assert result["total_overtime_hours"] == 0
    for assignment in result["assignments"]:
        assert assignment["cost"] == pytest.approx(assignment["hours"] * assignment["hourly_rate"])
        assert assignment["regular_hours"] == assignment["hours"]
        assert assignment["overtime_hours"] == 0


def _preference_window(employee):
    return window(employee.id, "2026-10-05T00:00", "2026-10-12T23:59")


def _preference_result(employees, shift, preferences, availability=None, leave=()):
    if availability is None:
        availability = tuple(_preference_window(employee) for employee in employees)
    data = SchedulingInput(tuple(employees), (shift,), tuple(availability), tuple(leave), tuple(preferences))
    return run(data)


def test_preferred_shift_is_satisfied_and_weighted():
    employees = (Employee("a", "A", "Ops", hourly_rate=20), Employee("b", "B", "Ops", hourly_rate=20))
    shift = Shift("s", date(2026, 10, 5), time(8), time(12), name="Morning", department="Ops")
    result = _preference_result(employees, shift, (EmployeePreference("a", "preferred_shift", "Morning", 10),))

    assert [item["employee_id"] for item in result["assignments"]] == ["a"]
    assert result["preference"] == {
        "total_weight": 10.0, "satisfied_weight": 10.0,
        "satisfaction_percentage": 100.0, "violated_preferences": [],
    }
    assert result["assignments"][0]["preference_match"] is True


def test_avoid_shift_preference_selects_employee_without_conflicting_preference():
    employees = (Employee("a", "A", "Ops", hourly_rate=20), Employee("b", "B", "Ops", hourly_rate=20))
    shift = Shift("s", date(2026, 10, 5), time(22), time(6), name="Night", department="Ops")
    result = _preference_result(employees, shift, (EmployeePreference("a", "avoid_shift", "Night", 10),))

    assert [item["employee_id"] for item in result["assignments"]] == ["b"]
    assert result["total_cost"] == 160
    assert result["preference"]["violated_preferences"] == []


def test_preferred_day_is_satisfied():
    employees = (Employee("a", "A", "Ops"), Employee("b", "B", "Ops"))
    shift = Shift("s", date(2026, 10, 5), time(9), time(13), name="Day", department="Ops")
    result = _preference_result(employees, shift, (EmployeePreference("a", "preferred_day", "Monday", 7),))

    assert result["assignments"][0]["employee_id"] == "a"
    assert result["preference"]["satisfied_weight"] == 7
    assert result["preference"]["satisfaction_percentage"] == 100


def test_avoid_weekend_selects_employee_without_weekend_preference():
    employees = (Employee("a", "A", "Ops"), Employee("b", "B", "Ops"))
    shift = Shift("s", date(2026, 10, 10), time(9), time(13), name="Day", department="Ops")
    result = _preference_result(employees, shift, (EmployeePreference("a", "avoid_weekend", "true", 10),))

    assert result["assignments"][0]["employee_id"] == "b"


def test_preference_weight_changes_choice_and_invalid_weight_defaults_to_one():
    employees = (Employee("a", "A", "Ops"), Employee("b", "B", "Ops"))
    shift = Shift("s", date(2026, 10, 5), time(9), time(13), name="Morning", department="Ops")
    preferences = (
        EmployeePreference("a", "preferred_shift", "Morning", 10),
        EmployeePreference("b", "preferred_shift", "Morning", -4),
    )
    result = _preference_result(employees, shift, preferences)

    assert result["assignments"][0]["employee_id"] == "a"
    assert result["preference"]["total_weight"] == 10
    assert result["preference"]["satisfied_weight"] == 10


def test_preference_violations_and_satisfaction_percentage_are_reported():
    employee = Employee("a", "A", "Ops")
    shift = Shift("s", date(2026, 10, 5), time(22), time(6), name="Night", department="Ops")
    result = _preference_result((employee,), shift, (EmployeePreference("a", "preferred_shift", "Morning", 10),))

    preference = result["preference"]
    assert preference["total_weight"] == 10
    assert preference["satisfied_weight"] == 0
    assert preference["satisfaction_percentage"] == 0
    assert len(preference["violated_preferences"]) == 1
    assert preference["violated_preferences"][0]["weight"] == 10
    assert result["assignments"][0]["preference_match"] is False


def test_preference_never_overrides_availability():
    employees = (Employee("a", "A", "Ops"), Employee("b", "B", "Ops"))
    shift = Shift("s", date(2026, 10, 5), time(9), time(13), name="Morning", department="Ops")
    availability = (window("b", "2026-10-05T00:00", "2026-10-05T23:59"),)
    result = _preference_result(
        employees, shift, (EmployeePreference("a", "preferred_shift", "Morning", 100),), availability,
    )

    assert [item["employee_id"] for item in result["assignments"]] == ["b"]


def test_preference_never_overrides_approved_leave():
    employees = (Employee("a", "A", "Ops"), Employee("b", "B", "Ops"))
    shift = Shift("s", date(2026, 10, 5), time(9), time(13), name="Morning", department="Ops")
    leave = (LeavePeriod("a", date(2026, 10, 5), date(2026, 10, 5), "approved"),)
    result = _preference_result(
        employees, shift, (EmployeePreference("a", "preferred_shift", "Morning", 100),), leave=leave,
    )

    assert [item["employee_id"] for item in result["assignments"]] == ["b"]


def test_preference_never_overrides_maximum_hours():
    employees = (Employee("a", "A", "Ops", max_hours_per_week=0), Employee("b", "B", "Ops"))
    shift = Shift("s", date(2026, 10, 5), time(9), time(13), name="Morning", department="Ops")
    result = _preference_result(employees, shift, (EmployeePreference("a", "preferred_shift", "Morning", 100),))

    assert [item["employee_id"] for item in result["assignments"]] == ["b"]


def test_preference_never_overrides_skill_or_department_constraints():
    skilled_same_department = Employee("b", "B", "Ops", (SkillProficiency("Certified"),))
    unskilled_same_department = Employee("a", "A", "Ops")
    other_department = Employee("c", "C", "Other", (SkillProficiency("Certified"),))
    shift = Shift("s", date(2026, 10, 5), time(9), time(13), name="Morning", department="Ops",
                  required_skills=(RequiredSkill("Certified"),))
    result = _preference_result(
        (unskilled_same_department, other_department, skilled_same_department), shift,
        (EmployeePreference("a", "preferred_shift", "Morning", 1000),),
    )

    assert [item["employee_id"] for item in result["assignments"]] == ["b"]


def test_preference_is_tertiary_after_staffing_and_labor_cost():
    employees = (
        Employee("cheap", "Cheap", "Ops", hourly_rate=10),
        Employee("preferred", "Preferred", "Ops", hourly_rate=100),
    )
    shift = Shift("s", date(2026, 10, 5), time(9), time(13), required_staff=1,
                  name="Morning", department="Ops")
    result = _preference_result(
        employees, shift, (EmployeePreference("preferred", "preferred_shift", "Morning", 1000),),
    )

    assert result["total_excess_staff"] == 0
    assert result["total_cost"] == 40
    assert result["assignments"][0]["employee_id"] == "cheap"


def test_preference_objective_cannot_add_excess_staff():
    employees = (Employee("a", "A", "Ops"), Employee("b", "B", "Ops"), Employee("c", "C", "Ops"))
    shift = Shift("s", date(2026, 10, 5), time(9), time(13), required_staff=1,
                  name="Morning", department="Ops")
    preferences = tuple(EmployeePreference(item.id, "preferred_shift", "Morning", 10) for item in employees)
    result = _preference_result(employees, shift, preferences)

    assert result["total_required_staff"] == 1
    assert result["total_assigned_staff"] == 1
    assert result["total_excess_staff"] == 0


def test_mapping_input_accepts_preferences_and_defaults_missing_weight():
    raw = {
        "employees": [{"id": "a", "name": "A", "department": "Ops"}],
        "shifts": [{"id": "s", "date": "2026-10-05", "start_time": "09:00", "end_time": "13:00",
                    "name": "Morning", "department": "Ops"}],
        "availability": [{"employee_id": "a", "start": "2026-10-05T00:00", "end": "2026-10-05T23:59"}],
        "preferences": [{"employee_id": "a", "key": "preferred_shift", "value": "Morning"}],
    }
    result = run(raw)

    assert result["preference"]["total_weight"] == 1
    assert result["preference"]["satisfied_weight"] == 1
