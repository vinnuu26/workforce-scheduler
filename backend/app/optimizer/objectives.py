"""Objective expressions and assignment-level preference evaluation.

The preference score is weighted satisfaction minus weighted violations.
Preference metrics count each supported employee preference once per assigned
shift for that employee; this makes every reported violation traceable to an
actual assignment. Unsupported or malformed preference keys/values are ignored.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from .model import Employee, EmployeePreference, SchedulingInput, Shift, normalize_preference_weight


def excess_staff_expression(assignments: dict, data: SchedulingInput):
    """Total assigned staff above each shift's hard minimum staffing level."""
    return sum(
        sum(assignments[employee.id, shift.id] for employee in data.employees)
        - shift.required_staff
        for shift in data.shifts
    )


def labor_cost_expression(assignments: dict, data: SchedulingInput):
    """Exact integer-proportional labor cost expression for safe lexicographic locking.

    Every hourly rate is converted from its decimal string to common integer
    units. Multiplying by shift minutes gives a common positive scale factor
    (rate scale × 60) for every assignment, so minimizing this integer sum is
    exactly equivalent to minimizing currency cost without float lock errors.
    """
    rates: dict[Any, Decimal] = {}
    precision = 0
    for employee in data.employees:
        try:
            rate = Decimal(str(employee.hourly_rate))
        except (InvalidOperation, ValueError):
            raise ValueError(f"Employee {employee.id!r} has an invalid hourly_rate")
        if not rate.is_finite() or rate < 0:
            raise ValueError(f"Employee {employee.id!r} has an invalid hourly_rate")
        rates[employee.id] = rate
        precision = max(precision, max(0, -rate.as_tuple().exponent))
    scale = 10 ** precision
    terms = []
    upper_bound = 0
    for employee in data.employees:
        rate_units = int(rates[employee.id] * scale)
        for shift in data.shifts:
            coefficient = rate_units * shift.duration_minutes
            upper_bound += coefficient
            terms.append(assignments[employee.id, shift.id] * coefficient)
    if upper_bound >= 2**62:
        raise ValueError("Combined labor-cost objective exceeds the supported integer range")
    return sum(terms)


def _normal(value: str) -> str:
    return " ".join(str(value).casefold().replace("_", " ").replace("-", " ").split())


def _shift_matches(value: str, shift_name: str) -> bool:
    target, actual = _normal(value), _normal(shift_name)
    if target.endswith(" shift"):
        target = target[:-6].strip()
    if actual.endswith(" shift"):
        actual = actual[:-6].strip()
    return bool(target) and target == actual


def preference_evaluation(preference: EmployeePreference, shift: Shift) -> tuple[bool, str] | None:
    """Return (satisfied, human-readable reason), or None if unsupported/invalid."""
    key = _normal(preference.key).replace(" ", "_")
    value = _normal(preference.value)
    day_name = shift.date.strftime("%A").casefold()
    if key == "preferred_shift" and value:
        matched = _shift_matches(value, shift.name)
        return matched, f"Preferred shift: {preference.value}"
    if key == "avoid_shift" and value:
        avoided = _shift_matches(value, shift.name)
        return not avoided, f"Avoided shift: {preference.value}"
    if key == "preferred_day" and value:
        matched = value == day_name
        return matched, f"Preferred day: {preference.value}"
    if key == "avoid_weekend":
        if value not in {"true", "1", "yes", "y"}:
            return None
        is_weekend = shift.date.weekday() >= 5
        return not is_weekend, "Avoid weekend"
    return None


def preference_score_expression(assignments: dict, data: SchedulingInput):
    """Weighted satisfied assignments minus weighted preference violations."""
    preferences_by_employee: dict[Any, list[EmployeePreference]] = {}
    for preference in data.preferences:
        preferences_by_employee.setdefault(preference.employee_id, []).append(preference)
    terms = []
    for employee in data.employees:
        for shift in data.shifts:
            for preference in preferences_by_employee.get(employee.id, ()):
                evaluation = preference_evaluation(preference, shift)
                if evaluation is None:
                    continue
                satisfied, _reason = evaluation
                weight = normalize_preference_weight(preference.weight)
                if weight:
                    terms.append(assignments[employee.id, shift.id] * (weight if satisfied else -weight))
    return sum(terms)


def preference_metrics(assignments: list[dict[str, Any]], data: SchedulingInput) -> dict[str, Any]:
    """Calculate preference weight and traceable assignment-level violations."""
    employees = {employee.id: employee for employee in data.employees}
    shifts = {shift.id: shift for shift in data.shifts}
    preferences_by_employee: dict[Any, list[EmployeePreference]] = {}
    for preference in data.preferences:
        preferences_by_employee.setdefault(preference.employee_id, []).append(preference)

    total_weight = 0.0
    satisfied_weight = 0.0
    violated_preferences = []
    for assignment in assignments:
        employee = employees[assignment["employee_id"]]
        shift = shifts[assignment["shift_id"]]
        reasons = []
        assignment_violations = []
        for preference in preferences_by_employee.get(employee.id, ()):
            evaluation = preference_evaluation(preference, shift)
            if evaluation is None:
                continue
            satisfied, reason = evaluation
            weight = normalize_preference_weight(preference.weight)
            total_weight += weight
            if satisfied:
                satisfied_weight += weight
                reasons.append(reason)
            else:
                violation = {
                    "employee_id": employee.id, "employee_name": employee.name,
                    "shift_id": shift.id, "shift_name": shift.name,
                    "key": preference.key, "value": preference.value, "weight": weight,
                    "reason": reason,
                }
                assignment_violations.append(violation)
                violated_preferences.append(violation)
        assignment["preference_match"] = not assignment_violations
        assignment["preference_reasons"] = reasons

    total_weight = round(total_weight, 2)
    satisfied_weight = round(satisfied_weight, 2)
    percentage = round(100 * satisfied_weight / total_weight, 2) if total_weight else 0.0
    return {
        "total_weight": total_weight,
        "satisfied_weight": satisfied_weight,
        "satisfaction_percentage": percentage,
        "violated_preferences": violated_preferences,
    }
