from datetime import date, datetime, time

import pytest

from app.optimizer.model import AvailabilityWindow, Employee, LeavePeriod, RequiredSkill, SchedulingInput, Shift, SkillProficiency
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
