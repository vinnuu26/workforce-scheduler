"""Hard CP-SAT constraints for employee-to-shift assignments."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Iterable

from ortools.sat.python import cp_model

from .model import AvailabilityWindow, Employee, LeavePeriod, SchedulingInput, Shift

def _availability_covers(employee_id: int | str, shift: Shift, windows: tuple[AvailabilityWindow, ...]) -> bool:
    employee_windows=[window for window in windows if window.employee_id == employee_id]
    if any(not window.available and window.start < shift.ends_at and shift.starts_at < window.end for window in employee_windows):
        return False
    allowed=sorted((window.start, window.end) for window in employee_windows if window.available)
    cursor=shift.starts_at
    for start, end in allowed:
        if end <= cursor:
            continue
        if start > cursor:
            break
        cursor=max(cursor, end)
        if cursor >= shift.ends_at:
            return True
    return False

def _on_approved_leave(employee_id: int | str, shift: Shift, leave: tuple[LeavePeriod, ...]) -> bool:
    final_day=(shift.ends_at - timedelta(microseconds=1)).date()
    return any(item.employee_id == employee_id and item.status.casefold() == "approved"
               and item.start_date <= final_day and shift.date <= item.end_date for item in leave)

def employee_can_work_shift(employee: Employee, shift: Shift, data: SchedulingInput) -> bool:
    """Return whether an employee is individually eligible for a shift."""
    if not employee.active or not _availability_covers(employee.id, shift, data.availability):
        return False
    if _on_approved_leave(employee.id, shift, data.leave):
        return False
    if round(employee.max_hours_per_week * 60) < shift.duration_minutes:
        return False
    if (not shift.allow_cross_department and shift.department is not None
            and employee.department != shift.department
            and (employee.id, shift.id) not in data.department_exceptions):
        return False
    proficiency = {skill.name: skill.proficiency for skill in employee.skills}
    return all(
        proficiency.get(requirement.name, 0) >= requirement.minimum_proficiency
        for requirement in shift.required_skills
    )

def _weekly_key(shift: Shift) -> tuple[int, int]:
    week=shift.date.isocalendar()
    return week.year, week.week

def add_active_employee_constraints(model: cp_model.CpModel, variables: dict, data: SchedulingInput) -> None:
    for employee in data.employees:
        if not employee.active:
            for shift in data.shifts:
                model.add(variables[employee.id, shift.id] == 0)

def add_availability_constraints(model: cp_model.CpModel, variables: dict, data: SchedulingInput) -> None:
    for employee in data.employees:
        for shift in data.shifts:
            if not _availability_covers(employee.id, shift, data.availability):
                model.add(variables[employee.id, shift.id] == 0)

def add_leave_constraints(model: cp_model.CpModel, variables: dict, data: SchedulingInput) -> None:
    for employee in data.employees:
        for shift in data.shifts:
            if _on_approved_leave(employee.id, shift, data.leave):
                model.add(variables[employee.id, shift.id] == 0)

def add_overlap_and_rest_constraints(model: cp_model.CpModel, variables: dict, data: SchedulingInput) -> None:
    ordered=sorted(data.shifts, key=lambda shift: (shift.starts_at, shift.ends_at, str(shift.id)))
    for employee in data.employees:
        for index, first in enumerate(ordered):
            for second in ordered[index + 1:]:
                first_end, second_start=first.ends_at, second.starts_at
                rest=timedelta(hours=first.minimum_rest_hours)
                if first_end + rest > second_start:
                    model.add(variables[employee.id, first.id] + variables[employee.id, second.id] <= 1)

def add_maximum_hours_constraints(model: cp_model.CpModel, variables: dict, data: SchedulingInput) -> None:
    week_shifts: dict[tuple[int | str, tuple[int, int]], list[Shift]]=defaultdict(list)
    for employee in data.employees:
        for shift in data.shifts:
            week_shifts[employee.id, _weekly_key(shift)].append(shift)
        max_minutes=round(employee.max_hours_per_week * 60)
        for (employee_id, _week), shifts in week_shifts.items():
            if employee_id == employee.id:
                model.add(sum(shift.duration_minutes * variables[employee.id, shift.id] for shift in shifts) <= max_minutes)

def add_staffing_constraints(model: cp_model.CpModel, variables: dict, data: SchedulingInput) -> None:
    for shift in data.shifts:
        model.add(sum(variables[employee.id, shift.id] for employee in data.employees) >= shift.required_staff)

def add_required_skill_constraints(model: cp_model.CpModel, variables: dict, data: SchedulingInput) -> None:
    proficiency={(employee.id, skill.name): skill.proficiency for employee in data.employees for skill in employee.skills}
    for shift in data.shifts:
        for requirement in shift.required_skills:
            qualified=[employee for employee in data.employees
                       if proficiency.get((employee.id, requirement.name), 0) >= requirement.minimum_proficiency
                       and (shift.allow_cross_department or shift.department is None or employee.department == shift.department
                            or (employee.id, shift.id) in data.department_exceptions)]
            model.add(sum(variables[employee.id, shift.id] for employee in qualified) >= requirement.required_count)

def add_department_constraints(model: cp_model.CpModel, variables: dict, data: SchedulingInput) -> None:
    for employee in data.employees:
        for shift in data.shifts:
            if (not shift.allow_cross_department and shift.department is not None
                    and employee.department != shift.department
                    and (employee.id, shift.id) not in data.department_exceptions):
                model.add(variables[employee.id, shift.id] == 0)

def add_no_duplicate_constraints(model: cp_model.CpModel, variables: dict, data: SchedulingInput) -> None:
    # A single BoolVar exists per pair, so duplicate assignment rows cannot be represented.
    expected=len(data.employees) * len(data.shifts)
    if len(variables) != expected:
        raise ValueError("Assignment variables must contain one variable per employee/shift pair")

def add_hard_constraints(model: cp_model.CpModel, variables: dict, data: SchedulingInput) -> None:
    """Add all hard constraints; no soft constraints or objective are introduced."""
    add_active_employee_constraints(model, variables, data)
    add_availability_constraints(model, variables, data)
    add_leave_constraints(model, variables, data)
    add_overlap_and_rest_constraints(model, variables, data)
    add_maximum_hours_constraints(model, variables, data)
    add_staffing_constraints(model, variables, data)
    add_required_skill_constraints(model, variables, data)
    add_department_constraints(model, variables, data)
    add_no_duplicate_constraints(model, variables, data)
