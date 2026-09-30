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
    """Integer-scaled weighted satisfaction minus violations for exact locking."""
    preferences_by_employee: dict[Any, list[EmployeePreference]] = {}
    for preference in data.preferences:
        preferences_by_employee.setdefault(preference.employee_id, []).append(preference)
    precision = 0
    for preference in data.preferences:
        weight = Decimal(str(normalize_preference_weight(preference.weight)))
        precision = max(precision, max(0, -weight.as_tuple().exponent))
    scale = 10 ** precision
    known_employee_ids = {employee.id for employee in data.employees}
    objective_bound = sum(
        int(Decimal(str(normalize_preference_weight(preference.weight))) * scale) * len(data.shifts)
        for preference in data.preferences if preference.employee_id in known_employee_ids
    )
    if objective_bound >= 2**62:
        raise ValueError("Combined weighted-preference objective exceeds the supported integer range")
    terms = []
    for employee in data.employees:
        for shift in data.shifts:
            for preference in preferences_by_employee.get(employee.id, ()):
                evaluation = preference_evaluation(preference, shift)
                if evaluation is None:
                    continue
                satisfied, _reason = evaluation
                weight = int(Decimal(str(normalize_preference_weight(preference.weight))) * scale)
                if weight:
                    terms.append(assignments[employee.id, shift.id] * (weight if satisfied else -weight))
    return sum(terms)


def fairness_expressions(model, assignments: dict, data: SchedulingInput):
    """Build lexicographic fairness expressions for hours, nights, then weekends.

    Hours are represented in minutes. For a fixed assigned-work total, minimizing
    sum(abs(employee_minutes * employee_count - total_minutes)) is equivalent to
    minimizing absolute deviation from the mean target without fractional CP-SAT
    coefficients. Night/weekend balance is measured over employees eligible for
    those shifts so employees who cannot work them do not count as unfairly low.
    """
    active = [employee for employee in data.employees if employee.active]
    employee_count = len(active)
    total_minutes = sum(
        assignments[employee.id, shift.id] * shift.duration_minutes
        for employee in active for shift in data.shifts
    )
    hour_deviation_terms = []
    for index, employee in enumerate(data.employees):
        if not employee.active or not employee_count:
            continue
        minutes = sum(
            assignments[employee.id, shift.id] * shift.duration_minutes
            for shift in data.shifts
        )
        upper = max(1, employee_count * sum(shift.duration_minutes for shift in data.shifts))
        deviation = model.new_int_var(0, upper, f"hour_deviation_{index}")
        model.add_abs_equality(deviation, employee_count * minutes - total_minutes)
        hour_deviation_terms.append(deviation)

    def shift_count_expr(eligible_employees, selected_shifts, label):
        count = len(eligible_employees)
        if count == 0:
            return 0
        total = sum(assignments[employee.id, shift.id]
                    for employee in eligible_employees for shift in selected_shifts)
        terms = []
        for index, employee in enumerate(eligible_employees):
            employee_count_expr = sum(assignments[employee.id, shift.id] for shift in selected_shifts)
            deviation = model.new_int_var(0, max(1, count * len(selected_shifts)), f"{label}_deviation_{index}")
            model.add_abs_equality(deviation, count * employee_count_expr - total)
            terms.append(deviation)
        return sum(terms)

    hour_expr = sum(hour_deviation_terms)
    night_shifts = [shift for shift in data.shifts if shift.starts_at.hour >= 20 or shift.ends_at.hour <= 6 or shift.ends_at.date() > shift.starts_at.date()]
    weekend_shifts = [shift for shift in data.shifts if shift.date.weekday() >= 5]
    # Count employees with at least one hard-feasible target shift. Static eligibility
    # checks skill/department/capacity/availability/leave, matching the assignment rules.
    from .constraints import employee_can_work_shift
    eligible_nights = [employee for employee in active if any(employee_can_work_shift(employee, shift, data) for shift in night_shifts)]
    eligible_weekends = [employee for employee in active if any(employee_can_work_shift(employee, shift, data) for shift in weekend_shifts)]
    night_expr = shift_count_expr(eligible_nights, night_shifts, "night")
    weekend_expr = shift_count_expr(eligible_weekends, weekend_shifts, "weekend")
    return hour_expr, night_expr, weekend_expr


def fairness_metrics(assignments: list[dict[str, Any]], data: SchedulingInput) -> dict[str, Any]:
    """Calculate interpretable workload, night, and weekend balance metrics.

    Hour target is total assigned hours divided by active employees. Night and
    weekend ranges use employees eligible for at least one shift in that category.
    Balance scores are 1 / (1 + relative range/deviation), hence 1 is perfect.
    """
    active = [employee for employee in data.employees if employee.active]
    total_minutes = {employee.id: 0 for employee in data.employees}
    nights = {employee.id: 0 for employee in data.employees}
    weekends = {employee.id: 0 for employee in data.employees}
    shifts = {shift.id: shift for shift in data.shifts}
    for assignment in assignments:
        shift = shifts[assignment["shift_id"]]
        employee_id = assignment["employee_id"]
        total_minutes[employee_id] += shift.duration_minutes
        if shift.starts_at.hour >= 20 or shift.ends_at.hour <= 6 or shift.ends_at.date() > shift.starts_at.date():
            nights[employee_id] += 1
        if shift.date.weekday() >= 5:
            weekends[employee_id] += 1
    target_minutes = sum(total_minutes[item.id] for item in active) / len(active) if active else 0
    deviations = {item.id: round(abs(total_minutes[item.id] - target_minutes) / 60, 2) for item in active}
    total_deviation = round(sum(deviations.values()), 2)
    from .constraints import employee_can_work_shift
    night_shifts = [shift for shift in data.shifts if shift.starts_at.hour >= 20 or shift.ends_at.hour <= 6 or shift.ends_at.date() > shift.starts_at.date()]
    weekend_shifts = [shift for shift in data.shifts if shift.date.weekday() >= 5]
    eligible_nights = [item.id for item in active if any(employee_can_work_shift(item, shift, data) for shift in night_shifts)]
    eligible_weekends = [item.id for item in active if any(employee_can_work_shift(item, shift, data) for shift in weekend_shifts)]
    night_range = max((nights[item] for item in eligible_nights), default=0) - min((nights[item] for item in eligible_nights), default=0)
    weekend_range = max((weekends[item] for item in eligible_weekends), default=0) - min((weekends[item] for item in eligible_weekends), default=0)
    target_hours = round(target_minutes / 60, 2)
    total_active_hours = sum(total_minutes[item.id] for item in active) / 60
    night_total = sum(nights[item] for item in eligible_nights)
    weekend_total = sum(weekends[item] for item in eligible_weekends)
    return {
        "target_hours": target_hours,
        "hour_deviations": deviations,
        "total_hour_deviation": total_deviation,
        "night_shift_counts": nights,
        "night_shift_range": night_range,
        "weekend_shift_counts": weekends,
        "weekend_shift_range": weekend_range,
        "hour_balance_score": round(1 / (1 + total_deviation / max(total_active_hours, 1)), 4),
        "night_shift_balance_score": round(1 / (1 + night_range / max(night_total, 1)), 4),
        "weekend_balance_score": round(1 / (1 + weekend_range / max(weekend_total, 1)), 4),
    }


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
