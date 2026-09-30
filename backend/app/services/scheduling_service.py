"""Application service entry point for the database-independent optimizer."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.optimizer.model import SchedulingInput, scheduling_input_from_mapping
from app.optimizer.solver import solve_schedule

def generate_schedule(input_data: SchedulingInput | Mapping[str, Any]) -> dict[str, Any]:
    """Generate a schedule from typed input data or a JSON-like mapping.

    Availability must include declared available windows that cover the full shift.
    A shift's complete hours are charged to the ISO week containing its start date.
    """
    if isinstance(input_data, Mapping):
        input_data=scheduling_input_from_mapping(input_data)
    result=solve_schedule(input_data)
    return {
        "status": result.status, "solver_status": result.solver_status,
        "assignments": result.assignments, "unassigned_shifts": result.unassigned_shifts,
        "employee_hours": result.employee_hours, "total_regular_hours": result.total_regular_hours,
        "total_overtime_hours": result.total_overtime_hours, "total_cost": result.total_cost,
    }
