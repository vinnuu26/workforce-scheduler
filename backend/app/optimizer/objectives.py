"""Objective expressions for lexicographic schedule optimization."""
from __future__ import annotations

import math

from ortools.sat.python import cp_model

from .model import SchedulingInput


def excess_staff_expression(assignments: dict, data: SchedulingInput) -> cp_model.LinearExpr:
    """Total assigned staff above each shift's hard minimum staffing level."""
    return sum(
        sum(assignments[employee.id, shift.id] for employee in data.employees)
        - shift.required_staff
        for shift in data.shifts
    )


def labor_cost_expression(assignments: dict, data: SchedulingInput):
    """Total assignment cost in currency units, represented as a float objective."""
    terms = []
    for employee in data.employees:
        rate = float(employee.hourly_rate)
        if not math.isfinite(rate) or rate < 0:
            raise ValueError(f"Employee {employee.id!r} has an invalid hourly_rate")
        for shift in data.shifts:
            terms.append(assignments[employee.id, shift.id] * (shift.duration_minutes / 60) * rate)
    return sum(terms)
