"""Build, solve, and extract a hard-constraints-only CP-SAT schedule."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ortools.sat.python import cp_model

from .constraints import add_hard_constraints
from .model import SchedulingInput, create_decision_variables

@dataclass(frozen=True, slots=True)
class OptimizationResult:
    status: str
    solver_status: str
    assignments: list[dict[str, Any]]
    unassigned_shifts: list[dict[str, Any]]
    employee_hours: dict[int | str, float]
    total_regular_hours: float
    total_overtime_hours: float
    total_cost: float

def _time_text(value: datetime) -> str:
    return value.isoformat(timespec="minutes")

def solve_schedule(data: SchedulingInput, max_time_seconds: float = 30.0) -> OptimizationResult:
    decisions=create_decision_variables(data)
    add_hard_constraints(decisions.model, decisions.assignments, data)
    solver=cp_model.CpSolver()
    solver.parameters.max_time_in_seconds=max_time_seconds
    solver.parameters.num_search_workers=1
    solver.parameters.random_seed=0
    solver.parameters.search_branching=cp_model.FIXED_SEARCH
    if decisions.assignments:
        decisions.model.add_decision_strategy(list(decisions.assignments.values()), cp_model.CHOOSE_FIRST, cp_model.SELECT_MIN_VALUE)
    raw_status=solver.solve(decisions.model)
    solver_status=solver.status_name(raw_status)
    if raw_status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return OptimizationResult(
            status="INFEASIBLE" if raw_status == cp_model.INFEASIBLE else solver_status,
            solver_status=solver_status, assignments=[],
            unassigned_shifts=[{"shift_id": shift.id, "shift_name": shift.name} for shift in data.shifts],
            employee_hours={employee.id: 0.0 for employee in data.employees},
            total_regular_hours=0.0, total_overtime_hours=0.0, total_cost=0.0,
        )
    assignments=[]
    employee_minutes={employee.id: 0 for employee in data.employees}
    employee_by_id={employee.id: employee for employee in data.employees}
    shift_by_id={shift.id: shift for shift in data.shifts}
    for (employee_id, shift_id), variable in decisions.assignments.items():
        if not solver.boolean_value(variable):
            continue
        employee=employee_by_id[employee_id]
        shift=shift_by_id[shift_id]
        minutes=shift.duration_minutes
        employee_minutes[employee_id] += minutes
        assignments.append({
            "employee_id": employee_id, "employee_name": employee.name,
            "shift_id": shift_id, "shift_date": shift.date.isoformat(), "shift_name": shift.name,
            "start_time": _time_text(shift.starts_at), "end_time": _time_text(shift.ends_at),
            "hours": round(minutes / 60, 2), "department": shift.department,
        })
    hours={employee_id: round(minutes / 60, 2) for employee_id, minutes in employee_minutes.items()}
    regular_hours=sum(employee_minutes.values()) / 60
    total_cost=sum(employee_minutes[employee.id] / 60 * employee.hourly_rate for employee in data.employees)
    return OptimizationResult(
        status="FEASIBLE", solver_status=solver_status, assignments=assignments, unassigned_shifts=[],
        employee_hours=hours, total_regular_hours=round(regular_hours, 2),
        total_overtime_hours=0.0, total_cost=round(total_cost, 2),
    )
