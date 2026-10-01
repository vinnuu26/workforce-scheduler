"""Tested, non-persistent repair proposals for infeasible scheduling inputs.

Candidate inputs are immutable dataclass copies and every feasible proposal is
verified with the production CP-SAT optimizer. Two-change search is bounded and
exists only to find small combinations where neither individual change works.
Result ordering is deterministic presentation order, not a business ranking.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from itertools import combinations
from typing import Any

from app.optimizer.constraints import _availability_covers, _on_approved_leave
from app.optimizer.model import AvailabilityWindow, ProjectRequirement, SchedulingInput
from app.optimizer.solver import solve_schedule
from app.services.conflict_detection_service import _skill_level, detect_conflicts

MAX_PROJECT_HOUR_STEPS = 24
MAX_DEADLINE_EXTENSION_DAYS = 7
MAX_SINGLE_TESTS = 80
MAX_TWO_CHANGE_TESTS = 100
MAX_CANDIDATE_SOLVER_SECONDS = 0.2
MAX_RESOLUTIONS = 50


def _candidate(kind: str, target: tuple[Any, ...], change_size: float, **values: Any) -> dict[str, Any]:
    return {"type": kind, "target": target, "change_size": change_size, **values}


def _clone_with(data: SchedulingInput, operation: dict[str, Any]) -> SchedulingInput:
    """Apply one operation to a fresh immutable SchedulingInput value."""
    kind = operation["type"]
    if kind == "REDUCE_STAFFING_REQUIREMENT":
        shifts = tuple(replace(item, required_staff=operation["value"])
                       if item.id == operation["shift_id"] else item for item in data.shifts)
        return replace(data, shifts=shifts)
    if kind in {"ADJUST_PROJECT_REQUIRED_HOURS", "ADJUST_PROJECT_REQUIRED_COUNT"}:
        requirements = tuple(replace(item, **{operation["field"]: operation["value"]})
                             if item.id == operation["requirement_id"] else item
                             for item in data.project_requirements)
        return replace(data, project_requirements=requirements)
    if kind == "EXTEND_PROJECT_DEADLINE":
        projects = tuple(replace(item, deadline=operation["deadline"])
                         if item.id == operation["project_id"] else item for item in data.projects)
        requirements = tuple(replace(item, deadline=operation["deadline"])
                             if item.project_id == operation["project_id"] and item.deadline is not None
                             else item for item in data.project_requirements)
        return replace(data, projects=projects, project_requirements=requirements)
    if kind == "EXTEND_AVAILABILITY":
        index = operation["availability_index"]
        windows = list(data.availability)
        original = windows[index]
        windows[index] = replace(original,
            start=min(original.start, operation["start"]),
            end=max(original.end, operation["end"]))
        return replace(data, availability=tuple(windows))
    if kind == "RELAX_DEPARTMENT_RESTRICTION":
        exception = (operation["employee_id"], operation["shift_id"])
        return replace(data, department_exceptions=tuple(sorted(
            set(data.department_exceptions) | {exception}, key=lambda item: (str(item[1]), str(item[0])))))
    raise ValueError(f"Unsupported resolution operation: {kind}")


def _eligible_except_availability(data: SchedulingInput, employee, shift, *, ignore_department=False) -> bool:
    if (not employee.active or (not ignore_department and employee.department != shift.department
                                and shift.department is not None)):
        return False
    if round(employee.max_hours_per_week * 60) < shift.duration_minutes:
        return False
    if _on_approved_leave(employee.id, shift, data.leave):
        return False
    return all(_skill_level(employee, req.name) >= req.minimum_proficiency
               for req in shift.required_skills)


def _availability_candidates(data: SchedulingInput, conflict: dict[str, Any]) -> list[dict[str, Any]]:
    shift = next((item for item in data.shifts if item.id == conflict.get("shift_id")), None)
    if shift is None:
        return []
    candidates = []
    for employee in data.employees:
        if employee.id not in conflict.get("employee_ids", ()) or not _eligible_except_availability(data, employee, shift):
            continue
        for index, window in enumerate(data.availability):
            if window.employee_id != employee.id or not window.available:
                continue
            if window.start > shift.starts_at or window.end < shift.ends_at:
                if window.end <= shift.starts_at or window.start >= shift.ends_at:
                    continue
                old_covered = max(0, (min(window.end, shift.ends_at) - max(window.start, shift.starts_at)).total_seconds())
                required = (shift.ends_at - shift.starts_at).total_seconds()
                extra_hours = round((required - old_covered) / 3600, 4)
                candidates.append(_candidate(
                    "EXTEND_AVAILABILITY", (shift.id, employee.id, index), extra_hours,
                    employee_id=employee.id, shift_id=shift.id, availability_index=index,
                    start=min(window.start, shift.starts_at), end=max(window.end, shift.ends_at),
                    old_start=window.start, old_end=window.end,
                    change_size_hours=extra_hours,
                ))
    return candidates


def _department_candidates(data: SchedulingInput, conflict: dict[str, Any]) -> list[dict[str, Any]]:
    shift = next((item for item in data.shifts if item.id == conflict.get("shift_id")), None)
    if shift is None or shift.allow_cross_department or shift.department is None:
        return []
    results = []
    for employee in data.employees:
        if employee.department == shift.department or not _eligible_except_availability(
                data, employee, shift, ignore_department=True):
            continue
        if not _availability_covers(employee.id, shift, data.availability):
            continue
        results.append(_candidate("RELAX_DEPARTMENT_RESTRICTION", (shift.id, employee.id), 1,
                                   employee_id=employee.id, shift_id=shift.id))
    return results


def _build_candidates(data: SchedulingInput, conflicts: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    informational: list[dict[str, Any]] = []
    by_shift = {item.id: item for item in data.shifts}
    by_requirement = {item.id: item for item in data.project_requirements}
    by_project = {item.id: item for item in data.projects}

    for conflict in conflicts:
        kind = conflict["type"]
        shift = by_shift.get(conflict.get("shift_id"))
        if kind in {"STAFFING_SHORTAGE", "SKILL_SHORTAGE", "AVAILABILITY_SHORTAGE", "DEPARTMENT_CONFLICT"} and shift:
            if kind == "STAFFING_SHORTAGE":
                candidates.extend(_candidate("REDUCE_STAFFING_REQUIREMENT", (shift.id, value),
                                             shift.required_staff-value, shift_id=shift.id, value=value)
                                  for value in range(shift.required_staff-1, 0, -1))
            elif kind == "AVAILABILITY_SHORTAGE":
                candidates.extend(_availability_candidates(data, conflict))
            elif kind == "DEPARTMENT_CONFLICT":
                candidates.extend(_department_candidates(data, conflict))

        requirement = by_requirement.get(conflict.get("requirement_id"))
        if requirement and kind == "PROJECT_REQUIREMENT_SHORTAGE":
            if conflict.get("missing_hours", 0) > 0 or requirement.required_hours > 0:
                steps = min(MAX_PROJECT_HOUR_STEPS, int(requirement.required_hours + 0.999999))
                candidates.extend(_candidate("ADJUST_PROJECT_REQUIRED_HOURS", (requirement.id, value),
                                             round(requirement.required_hours-value, 4),
                                             requirement_id=requirement.id, field="required_hours", value=value)
                                  for value in (round(max(0.0, requirement.required_hours-step), 4)
                                                for step in range(1, steps+1)))
            if requirement.required_count > 1:
                candidates.extend(_candidate("ADJUST_PROJECT_REQUIRED_COUNT", (requirement.id, value),
                                             requirement.required_count-value,
                                             requirement_id=requirement.id, field="required_count", value=value)
                                  for value in range(requirement.required_count-1, 0, -1))

        if kind == "DEADLINE_CONFLICT":
            project = by_project.get(conflict.get("project_id"))
            requirement_deadline = requirement.deadline if requirement else None
            current = requirement_deadline or (project.deadline if project else None)
            if project and current:
                candidates.extend(_candidate("EXTEND_PROJECT_DEADLINE", (project.id, days), days,
                                             project_id=project.id, days=days,
                                             deadline=current + timedelta(days=days),
                                             current_deadline=current)
                                  for days in range(1, MAX_DEADLINE_EXTENSION_DAYS + 1))

        if kind == "LEAVE_CONFLICT":
            informational.append({"type": "LEAVE_CHANGE_REQUIRED", "testable": False,
                "description": "A qualified employee would need an approved leave change for this shift.",
                "conflict_id": conflict["conflict_id"], "employee_ids": conflict.get("employee_ids", []),
                "shift_id": conflict.get("shift_id")})
        if kind == "MAX_HOURS_CONFLICT":
            informational.append({"type": "OVERTIME_UNAVAILABLE", "testable": False,
                "description": "Additional overtime support is not currently enabled in the optimizer.",
                "conflict_id": conflict["conflict_id"], "employee_ids": conflict.get("employee_ids", []),
                "shift_id": conflict.get("shift_id")})

    candidates.sort(key=lambda item: (item["change_size"], item["type"],
                                     tuple(map(str, item["target"]))))
    return candidates[:MAX_SINGLE_TESTS], informational


def _proposal(operation: dict[str, Any], data: SchedulingInput, *, operations=None,
              assignments=None) -> dict[str, Any]:
    ops = operations or [operation]
    types = [item["type"] for item in ops]
    kind = types[0] if len(ops) == 1 else "MULTI_CHANGE_REPAIR"
    shift_ids = sorted({item["shift_id"] for item in ops if "shift_id" in item}, key=str)
    project_ids = sorted({item["project_id"] for item in ops if "project_id" in item}, key=str)
    employee_ids = sorted({item["employee_id"] for item in ops if "employee_id" in item}, key=str)
    total_size = round(sum(item["change_size"] for item in ops), 4)
    details = []
    for item in ops:
        item_details = {key: value for key, value in item.items()
                        if key not in {"target", "field", "availability_index", "start", "end", "old_start", "old_end"}}
        if item["type"] == "REDUCE_STAFFING_REQUIREMENT":
            shift = next(item2 for item2 in data.shifts if item2.id == item["shift_id"])
            item_details.update(current_value=shift.required_staff, suggested_value=item["value"],
                                required_staff_before=shift.required_staff, required_staff_after=item["value"])
        elif item["type"] in {"ADJUST_PROJECT_REQUIRED_HOURS", "ADJUST_PROJECT_REQUIRED_COUNT"}:
            req = next(item2 for item2 in data.project_requirements if item2.id == item["requirement_id"])
            field = item["field"]
            item_details.update(current_value=getattr(req, field), suggested_value=item["value"])
        elif item["type"] == "EXTEND_AVAILABILITY":
            item_details.update(old_start_time=item["old_start"].strftime("%H:%M"),
                                new_start_time=item["start"].strftime("%H:%M"),
                                old_end_time=item["old_end"].strftime("%H:%M"),
                                new_end_time=item["end"].strftime("%H:%M"))
        elif item["type"] == "EXTEND_PROJECT_DEADLINE":
            item_details.update(current_deadline=item["current_deadline"].isoformat(),
                                suggested_deadline=item["deadline"].isoformat(),
                                change_size_days=item["days"])
        details.append(item_details)
    if len(ops) == 1:
        details = details[0]
    if assignments:
        exception_pairs = {(item["employee_id"], item["shift_id"]) for item in ops
                           if item["type"] == "RELAX_DEPARTMENT_RESTRICTION"}
        department_pairs = [(item["employee_id"], item["shift_id"]) for item in assignments
                            if (item["employee_id"], item["shift_id"]) in exception_pairs]
        if any(item["type"] == "RELAX_DEPARTMENT_RESTRICTION" for item in ops):
            details = {"changes": details if isinstance(details, list) else [details],
                       "verified_department_assignments": department_pairs}
    description = "; ".join(_description(item, data) for item in ops)
    public_operations = []
    for item in ops:
        public_operations.append({key: value.isoformat() if hasattr(value, "isoformat") else value
                                 for key, value in item.items() if key != "target"})
    return {"resolution_id": "", "type": kind, "description": description,
            "testable": True, "feasible": True, "change_size": total_size,
            "affected_shift_ids": shift_ids, "affected_employee_ids": employee_ids,
            "affected_project_ids": project_ids, "details": details, "operations": public_operations}


def apply_resolution_operations(data: SchedulingInput, operations: list[dict[str, Any]]) -> SchedulingInput:
    """Apply only immutable optimizer input operations; caller must validate feasibility."""
    candidate = data
    for operation in operations:
        candidate = _clone_with(candidate, operation)
    return candidate


def _description(operation: dict[str, Any], data: SchedulingInput) -> str:
    kind = operation["type"]
    if kind == "REDUCE_STAFFING_REQUIREMENT":
        shift = next(item for item in data.shifts if item.id == operation["shift_id"])
        return f"Reduce {shift.name} staffing from {shift.required_staff} to {operation['value']}."
    if kind == "ADJUST_PROJECT_REQUIRED_HOURS":
        req = next(item for item in data.project_requirements if item.id == operation["requirement_id"])
        return f"Reduce project requirement {req.id} from {req.required_hours:g} to {operation['value']:g} hours."
    if kind == "ADJUST_PROJECT_REQUIRED_COUNT":
        req = next(item for item in data.project_requirements if item.id == operation["requirement_id"])
        return f"Reduce project requirement {req.id} participant count from {req.required_count} to {operation['value']}."
    if kind == "EXTEND_PROJECT_DEADLINE":
        return f"Extend project {operation['project_id']} deadline by {operation['days']} days."
    if kind == "EXTEND_AVAILABILITY":
        return f"Extend employee {operation['employee_id']} availability to cover shift {operation['shift_id']}."
    if kind == "RELAX_DEPARTMENT_RESTRICTION":
        return f"Allow employee {operation['employee_id']} to cover shift {operation['shift_id']} across departments."
    return kind.replace("_", " ").capitalize()


def _run_candidate(data: SchedulingInput, operations: list[dict[str, Any]]):
    candidate = data
    for operation in operations:
        candidate = _clone_with(candidate, operation)
    result = solve_schedule(candidate, max_time_seconds=MAX_CANDIDATE_SOLVER_SECONDS)
    return candidate, result


def resolve_conflicts(data: SchedulingInput) -> dict[str, Any]:
    """Diagnose, search bounded candidate changes, and verify feasible repairs."""
    baseline = solve_schedule(data)
    if baseline.status == "FEASIBLE":
        return {"status": "ALREADY_FEASIBLE", "conflicts": [], "resolutions": []}
    if baseline.status != "INFEASIBLE":
        return {"status": baseline.status, "conflicts": [], "resolutions": []}

    conflicts = detect_conflicts(data)
    candidates, informational = _build_candidates(data, conflicts)
    tested = 0
    successful: list[tuple[dict[str, Any], list[dict[str, Any]], Any]] = []
    failed: list[dict[str, Any]] = []
    resolved_targets: set[tuple[Any, ...]] = set()
    for operation in candidates:
        target_key = (operation["type"], operation["target"][0])
        if target_key in resolved_targets:
            continue
        if tested >= MAX_SINGLE_TESTS:
            break
        tested += 1
        _, result = _run_candidate(data, [operation])
        if result.status == "FEASIBLE":
            successful.append((operation, [operation], result))
            resolved_targets.add(target_key)
            # For the same target, candidates are ordered from smallest change.
            # Skip all remaining single-operation variants after verified repair.
        else:
            failed.append(operation)

    pair_tests = 0
    if not successful:
        for first, second in combinations(failed, 2):
            if pair_tests >= MAX_TWO_CHANGE_TESTS:
                break
            if first["type"] == second["type"] and first["target"][0] == second["target"][0]:
                continue
            # Do not combine two alternative values for the same logical field.
            if first["target"][:1] == second["target"][:1] and first["type"] == second["type"]:
                continue
            pair_tests += 1
            _, result = _run_candidate(data, [first, second])
            if result.status == "FEASIBLE":
                successful.append((first, [first, second], result))

    proposals = []
    for _key, operations, result in successful:
        proposals.append(_proposal(operations[0], data, operations=operations,
                                   assignments=result.assignments))
    proposals.extend({"resolution_id": "", "type": item["type"],
                      "description": item["description"], "testable": False,
                      "feasible": False, "change_size": 0,
                      "affected_shift_ids": [item["shift_id"]] if item.get("shift_id") is not None else [],
                      "affected_employee_ids": item.get("employee_ids", []),
                      "affected_project_ids": [], "details": {"conflict_id": item["conflict_id"]}}
                     for item in informational)
    proposals.sort(key=lambda item: (not item["testable"], item["change_size"], item["type"],
                                     tuple(map(str, item["affected_shift_ids"])),
                                     tuple(map(str, item["affected_employee_ids"])),
                                     tuple(map(str, item["affected_project_ids"]))))
    proposals = proposals[:MAX_RESOLUTIONS]
    for index, proposal in enumerate(proposals, start=1):
        proposal["resolution_id"] = f"R{index}"
    return {"status": "INFEASIBLE", "conflicts": conflicts, "resolutions": proposals}
