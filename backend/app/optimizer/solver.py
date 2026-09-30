"""Build, lexicographically optimize, and extract a hard-constraint schedule."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ortools.sat.python import cp_model

from .constraints import add_hard_constraints
from .model import SchedulingInput, create_decision_variables
from .objectives import (
    excess_staff_expression, labor_cost_expression, preference_metrics,
    preference_score_expression,
)


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    status: str
    solver_status: str
    assignments: list[dict[str, Any]]
    unassigned_shifts: list[dict[str, Any]]
    employee_hours: dict[int | str, float]
    total_required_staff: int
    total_assigned_staff: int
    total_excess_staff: int
    total_regular_hours: float
    total_overtime_hours: float
    total_cost: float
    objective: dict[str, int | float]
    preference: dict[str, Any]


def _time_text(value: datetime) -> str:
    return value.isoformat(timespec="minutes")


def _new_solver(max_time_seconds: float) -> cp_model.CpSolver:
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max_time_seconds
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 0
    solver.parameters.search_branching = cp_model.FIXED_SEARCH
    return solver


def _empty_infeasible_result(data: SchedulingInput, solver_status: str) -> OptimizationResult:
    return OptimizationResult(
        status="INFEASIBLE" if solver_status == "INFEASIBLE" else solver_status,
        solver_status=solver_status, assignments=[],
        unassigned_shifts=[{"shift_id": shift.id, "shift_name": shift.name} for shift in data.shifts],
        employee_hours={employee.id: 0.0 for employee in data.employees},
        total_required_staff=sum(shift.required_staff for shift in data.shifts),
        total_assigned_staff=0, total_excess_staff=0,
        total_regular_hours=0.0, total_overtime_hours=0.0, total_cost=0.0,
        objective={"excess_staff": 0, "labor_cost": 0.0, "preference_score": 0.0},
        preference={"total_weight": 0.0, "satisfied_weight": 0.0,
                    "satisfaction_percentage": 0.0, "violated_preferences": []},
    )


def solve_schedule(data: SchedulingInput, max_time_seconds: float = 30.0) -> OptimizationResult:
    decisions = create_decision_variables(data)
    add_hard_constraints(decisions.model, decisions.assignments, data)
    excess_expr = excess_staff_expression(decisions.assignments, data)
    cost_expr = labor_cost_expression(decisions.assignments, data)
    preference_expr = preference_score_expression(decisions.assignments, data)

    # Lexicographic optimization locks each proven optimum before proceeding:
    # staffing can never be traded for cost, and cost can never be traded for preferences.
    decisions.model.minimize(excess_expr)
    staffing_solver = _new_solver(max_time_seconds)
    staffing_status = staffing_solver.solve(decisions.model)
    staffing_status_name = staffing_solver.status_name(staffing_status)
    if staffing_status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return _empty_infeasible_result(data, staffing_status_name)

    best_excess = int(staffing_solver.value(excess_expr))
    # If phase one reached only a feasible incumbent (for example at the time
    # limit), preserve it rather than claim a lexicographic optimum we cannot prove.
    if staffing_status != cp_model.OPTIMAL:
        return _extract_result(data, decisions.assignments, staffing_solver, "FEASIBLE")

    decisions.model.add(excess_expr == best_excess)
    decisions.model.clear_objective()
    decisions.model.minimize(cost_expr)
    cost_solver = _new_solver(max_time_seconds)
    cost_status = cost_solver.solve(decisions.model)
    if cost_status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        # The primary-optimal staffing solution remains a valid fallback.
        return _extract_result(data, decisions.assignments, staffing_solver, "FEASIBLE")
    if cost_status != cp_model.OPTIMAL:
        return _extract_result(data, decisions.assignments, cost_solver, "FEASIBLE")

    best_cost = int(cost_solver.value(cost_expr))
    decisions.model.add(cost_expr == best_cost)
    decisions.model.clear_objective()
    decisions.model.maximize(preference_expr)
    preference_solver = _new_solver(max_time_seconds)
    preference_status = preference_solver.solve(decisions.model)
    preference_status_name = preference_solver.status_name(preference_status)
    if preference_status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return _extract_result(data, decisions.assignments, cost_solver, "FEASIBLE")
    return _extract_result(data, decisions.assignments, preference_solver, preference_status_name)


def _extract_result(data: SchedulingInput, assignments_by_pair: dict, solver: cp_model.CpSolver,
                    solver_status: str) -> OptimizationResult:
    assignments = []
    employee_minutes = {employee.id: 0 for employee in data.employees}
    employee_by_id = {employee.id: employee for employee in data.employees}
    shift_by_id = {shift.id: shift for shift in data.shifts}
    for (employee_id, shift_id), variable in assignments_by_pair.items():
        if not solver.boolean_value(variable):
            continue
        employee = employee_by_id[employee_id]
        shift = shift_by_id[shift_id]
        minutes = shift.duration_minutes
        hours = round(minutes / 60, 2)
        rate = float(employee.hourly_rate)
        cost = round(hours * rate, 2)
        employee_minutes[employee_id] += minutes
        assignments.append({
            "employee_id": employee_id, "employee_name": employee.name,
            "shift_id": shift_id, "shift_date": shift.date.isoformat(), "shift_name": shift.name,
            "start_time": _time_text(shift.starts_at), "end_time": _time_text(shift.ends_at),
            "department": shift.department, "hours": hours, "regular_hours": hours,
            "overtime_hours": 0.0, "hourly_rate": rate, "cost": cost,
        })

    employee_hours = {employee_id: round(minutes / 60, 2) for employee_id, minutes in employee_minutes.items()}
    total_required = sum(shift.required_staff for shift in data.shifts)
    total_assigned = len(assignments)
    total_excess = sum(
        sum(1 for assignment in assignments if assignment["shift_id"] == shift.id) - shift.required_staff
        for shift in data.shifts
    )
    total_regular_hours = round(sum(employee_minutes.values()) / 60, 2)
    total_cost = round(sum(assignment["cost"] for assignment in assignments), 2)
    preference = preference_metrics(assignments, data)
    preference_score = round(
        preference["satisfied_weight"]
        - sum(item["weight"] for item in preference["violated_preferences"]), 2,
    )
    return OptimizationResult(
        status="FEASIBLE", solver_status=solver_status, assignments=assignments, unassigned_shifts=[],
        employee_hours=employee_hours, total_required_staff=total_required,
        total_assigned_staff=total_assigned, total_excess_staff=total_excess,
        total_regular_hours=total_regular_hours, total_overtime_hours=0.0,
        total_cost=total_cost,
        objective={"excess_staff": total_excess, "labor_cost": total_cost,
                   "preference_score": preference_score},
        preference=preference,
    )
