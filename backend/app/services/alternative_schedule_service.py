"""Generate distinct, lexicographically optimized schedules without persistence."""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.optimizer.solver import solve_schedule
from app.services.scheduling_service import prepare_scheduling_input


def generate_alternative_schedules(
    db: Session,
    start_date: date,
    end_date: date,
    count: int = 3,
    department_id: int | None = None,
    project_id: int | None = None,
) -> dict[str, Any]:
    """Return up to ``count`` unique alternatives, leaving persistence to selection."""
    data, _employees, _shifts = prepare_scheduling_input(
        db, start_date, end_date, department_id, project_id,
    )
    excluded: list[frozenset[tuple[int | str, int | str]]] = []
    alternatives = []
    for alternative_id in range(1, count + 1):
        result = solve_schedule(data, excluded_signatures=excluded)
        if result.status != "FEASIBLE":
            break
        signature = frozenset((item["employee_id"], item["shift_id"]) for item in result.assignments)
        # The no-good constraints guarantee uniqueness; this guard also prevents
        # accidental duplicate emission if future solver code changes its scope.
        if signature in excluded:
            break
        excluded.append(signature)
        alternatives.append({
            "alternative_id": alternative_id,
            "status": result.solver_status,
            "solver_status": result.solver_status,
            "total_required_staff": result.total_required_staff,
            "total_assigned_staff": result.total_assigned_staff,
            "total_excess_staff": result.total_excess_staff,
            "total_regular_hours": result.total_regular_hours,
            "total_overtime_hours": result.total_overtime_hours,
            "total_cost": result.total_cost,
            "preference": result.preference,
            "fairness": result.fairness,
            "projects": result.projects,
            "assignments": result.assignments,
            "assignment_count": len(result.assignments),
            "objective": result.objective,
        })

    generated = len(alternatives)
    status = "INFEASIBLE" if generated == 0 else "SUCCESS" if generated == count else "PARTIAL"
    return {
        "status": status,
        "requested_count": count,
        "generated_count": generated,
        "alternatives": alternatives,
    }
