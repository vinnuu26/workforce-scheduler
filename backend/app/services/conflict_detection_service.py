"""Deterministic evidence-based diagnostics for infeasible scheduling inputs."""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from typing import Any

from app.optimizer.constraints import _availability_covers, _on_approved_leave, _weekly_key
from app.optimizer.model import Employee, Project, ProjectRequirement, SchedulingInput, Shift
from app.optimizer.projects import _qualified, _requirement_shifts


def _conflict(
    conflict_type: str,
    message: str,
    *,
    shift: Shift | None = None,
    shifts: list[Shift] | None = None,
    employee_ids: list[int | str] | None = None,
    project_id: int | str | None = None,
    requirement_id: int | str | None = None,
    skill: str | None = None,
    required: int | float | None = None,
    available: int | float | None = None,
    gap: int | float | None = None,
    constraints: list[str] | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    shift_ids = [item.id for item in (shifts or ([shift] if shift else []))]
    key = f"{conflict_type.lower()}-shift-{','.join(map(str, shift_ids)) or 'none'}-project-{project_id or 'none'}-requirement-{requirement_id or 'none'}-skill-{skill or 'none'}"
    result: dict[str, Any] = {
        "conflict_id": key,
        "type": conflict_type,
        "severity": "CRITICAL",
        "shift_id": shift.id if shift else (shift_ids[-1] if shift_ids else None),
        "shift_ids": shift_ids,
        "employee_ids": sorted(set(employee_ids or []), key=str),
        "project_id": project_id,
        "requirement_id": requirement_id,
        "skill": skill,
        "message": message,
        "required": required,
        "available": available,
        "gap": gap,
        "constraints": constraints or [],
    }
    if details:
        result.update(details)
    return result


def _skill_level(employee: Employee, skill_name: str) -> int:
    return max((skill.proficiency for skill in employee.skills if skill.name == skill_name), default=0)


def _shift_profile(employee: Employee, shift: Shift, data: SchedulingInput) -> dict[str, Any]:
    dept_ok = shift.allow_cross_department or shift.department is None or employee.department == shift.department
    skill_qualified = all(_skill_level(employee, req.name) >= req.minimum_proficiency
                          for req in shift.required_skills)
    hours_ok = round(employee.max_hours_per_week * 60) >= shift.duration_minutes
    available = _availability_covers(employee.id, shift, data.availability)
    on_leave = _on_approved_leave(employee.id, shift, data.leave)
    return {
        "active": employee.active,
        "department": dept_ok,
        "skill": skill_qualified,
        "single_shift_hours": hours_ok,
        "availability": available,
        "leave": on_leave,
    }


def _forced_employee_shifts(data: SchedulingInput, profiles: dict[Any, dict[Any, dict[str, Any]]]):
    """Return assignments forced by a demand pool with no spare eligible worker."""
    forced: dict[Any, set[Any]] = defaultdict(set)
    for shift in data.shifts:
        eligible = [employee for employee in data.employees
                    if all(profiles[shift.id][employee.id][key]
                           for key in ("active", "department", "single_shift_hours", "availability"))
                    and not profiles[shift.id][employee.id]["leave"]]
        if len(eligible) == shift.required_staff:
            for employee in eligible:
                forced[employee.id].add(shift.id)
        for requirement in shift.required_skills:
            qualified = [employee for employee in eligible
                         if _skill_level(employee, requirement.name) >= requirement.minimum_proficiency]
            if len(qualified) == requirement.required_count:
                for employee in qualified:
                    forced[employee.id].add(shift.id)
    return forced


def detect_conflicts(data: SchedulingInput) -> list[dict[str, Any]]:
    """Report concrete shortages and forced hard-constraint conflicts.

    This is a targeted static analysis, not an interpretation of a CP-SAT
    infeasibility proof. Staffing/skill counts use staged candidate pools;
    rest and cumulative-hour conflicts are emitted only when the involved
    assignment is forced by the available candidate count.
    """
    conflicts: list[dict[str, Any]] = []
    seen: set[str] = set()
    employees_by_id = {employee.id: employee for employee in data.employees}
    shifts_by_id = {shift.id: shift for shift in data.shifts}
    profiles = {shift.id: {employee.id: _shift_profile(employee, shift, data)
                           for employee in data.employees} for shift in data.shifts}

    def add(item):
        if item["conflict_id"] not in seen:
            seen.add(item["conflict_id"])
            conflicts.append(item)

    # Per-shift general staffing shortages, attributed to the earliest binding
    # candidate filter so availability/leave/department are not reported twice.
    for shift in data.shifts:
        profile = profiles[shift.id]
        active = [e for e in data.employees if profile[e.id]["active"]]
        department = [e for e in active if profile[e.id]["department"]]
        single_shift = [e for e in department if profile[e.id]["single_shift_hours"]]
        available = [e for e in single_shift if profile[e.id]["availability"]]
        eligible = [e for e in available if not profile[e.id]["leave"]]
        if len(eligible) >= shift.required_staff:
            pass
        elif len(department) < shift.required_staff:
            if len(active) >= shift.required_staff:
                add(_conflict("DEPARTMENT_CONFLICT",
                    f"Shift {shift.id} requires {shift.required_staff} staff, but only {len(department)} active employees match its department.",
                    shift=shift, employee_ids=[e.id for e in department], required=shift.required_staff,
                    available=len(department), gap=shift.required_staff-len(department),
                    constraints=["department_restriction"]))
            else:
                add(_conflict("STAFFING_SHORTAGE",
                    f"Shift {shift.id} requires {shift.required_staff} staff, but only {len(active)} active employees exist in the scheduling input.",
                    shift=shift, employee_ids=[e.id for e in active], required=shift.required_staff,
                    available=len(active), gap=shift.required_staff-len(active), constraints=["minimum_staffing"]))
        elif len(single_shift) < shift.required_staff:
            add(_conflict("MAX_HOURS_CONFLICT",
                f"Shift {shift.id} requires {shift.required_staff} staff, but only {len(single_shift)} department-qualified employees can fit the shift within their weekly maximum.",
                shift=shift, employee_ids=[e.id for e in department if not profile[e.id]["single_shift_hours"]],
                required=shift.required_staff, available=len(single_shift), gap=shift.required_staff-len(single_shift),
                constraints=["maximum_weekly_hours"], details={"blocked_employee_ids": [e.id for e in department if not profile[e.id]["single_shift_hours"]]}))
        elif len(available) < shift.required_staff:
            add(_conflict("AVAILABILITY_SHORTAGE",
                f"Shift {shift.id} requires {shift.required_staff} staff, but only {len(available)} department-qualified employees can cover the complete shift.",
                shift=shift, employee_ids=[e.id for e in single_shift if not profile[e.id]["availability"]],
                required=shift.required_staff, available=len(available), gap=shift.required_staff-len(available),
                constraints=["availability_window"], details={"blocked_employee_ids": [e.id for e in single_shift if not profile[e.id]["availability"]]}))
        elif len(eligible) < shift.required_staff:
            add(_conflict("LEAVE_CONFLICT",
                f"Shift {shift.id} requires {shift.required_staff} staff; approved leave reduces otherwise available employees from {len(available)} to {len(eligible)}.",
                shift=shift, employee_ids=[e.id for e in available if profile[e.id]["leave"]],
                required=shift.required_staff, available=len(eligible), gap=shift.required_staff-len(eligible),
                constraints=["approved_leave"], details={"blocked_employee_ids": [e.id for e in available if profile[e.id]["leave"]]}))

        # Each skill has an independent qualified-headcount constraint.
        for skill_req in shift.required_skills:
            skilled = [e for e in active if _skill_level(e, skill_req.name) >= skill_req.minimum_proficiency]
            dept_skilled = [e for e in skilled if profile[e.id]["department"]]
            max_skilled = [e for e in dept_skilled if profile[e.id]["single_shift_hours"]]
            available_skilled = [e for e in max_skilled if profile[e.id]["availability"]]
            eligible_skilled = [e for e in available_skilled if not profile[e.id]["leave"]]
            n = skill_req.required_count
            common = {"shift": shift, "skill": skill_req.name, "required": n,
                      "constraints": ["required_skill", "minimum_proficiency"]}
            if len(skilled) < n:
                add(_conflict("SKILL_SHORTAGE",
                    f"Shift {shift.id} requires {n} employees with {skill_req.name} proficiency {skill_req.minimum_proficiency}, but only {len(skilled)} active employees have that skill level.",
                    employee_ids=[e.id for e in skilled], available=len(skilled), gap=n-len(skilled),
                    details={"minimum_proficiency": skill_req.minimum_proficiency}, **common))
            elif len(dept_skilled) < n:
                add(_conflict("DEPARTMENT_CONFLICT",
                    f"Shift {shift.id} requires {n} qualified {skill_req.name} employees, but department restrictions leave only {len(dept_skilled)}.",
                    employee_ids=[e.id for e in dept_skilled], available=len(dept_skilled), gap=n-len(dept_skilled),
                    details={"minimum_proficiency": skill_req.minimum_proficiency}, **common))
            elif len(max_skilled) < n:
                add(_conflict("MAX_HOURS_CONFLICT",
                    f"Shift {shift.id} requires {n} qualified {skill_req.name} employees, but weekly maximum hours leave only {len(max_skilled)} able to take the full shift.",
                    employee_ids=[e.id for e in dept_skilled if not profile[e.id]["single_shift_hours"]],
                    available=len(max_skilled), gap=n-len(max_skilled),
                    details={"minimum_proficiency": skill_req.minimum_proficiency}, **common))
            elif len(available_skilled) < n:
                add(_conflict("AVAILABILITY_SHORTAGE",
                    f"Shift {shift.id} requires {n} qualified {skill_req.name} employees, but only {len(available_skilled)} can cover the complete shift.",
                    employee_ids=[e.id for e in max_skilled if not profile[e.id]["availability"]],
                    available=len(available_skilled), gap=n-len(available_skilled),
                    details={"minimum_proficiency": skill_req.minimum_proficiency}, **common))
            elif len(eligible_skilled) < n:
                add(_conflict("LEAVE_CONFLICT",
                    f"Approved leave reduces qualified {skill_req.name} employees for shift {shift.id} from {len(available_skilled)} to {len(eligible_skilled)}; {n} are required.",
                    employee_ids=[e.id for e in available_skilled if profile[e.id]["leave"]],
                    available=len(eligible_skilled), gap=n-len(eligible_skilled),
                    details={"minimum_proficiency": skill_req.minimum_proficiency}, **common))

    # Detect rest/overlap and cumulative max-hour conflicts only for assignments
    # forced by a tight staffing or skill-qualified candidate pool.
    forced = _forced_employee_shifts(data, profiles)
    for employee_id, forced_ids in forced.items():
        ordered = sorted((shifts_by_id[sid] for sid in forced_ids), key=lambda s: (s.starts_at, s.ends_at, str(s.id)))
        for index, first in enumerate(ordered):
            for second in ordered[index + 1:]:
                if first.ends_at + timedelta(hours=first.minimum_rest_hours) > second.starts_at:
                    add(_conflict("REST_CONFLICT",
                        f"Employee {employee_id} is forced onto shifts {first.id} and {second.id}, but the required rest period after shift {first.id} extends past shift {second.id}.",
                        shift=second, shifts=[first, second], employee_ids=[employee_id], required=1,
                        available=0, gap=1, constraints=["shift_overlap", "minimum_rest_hours"],
                        details={"minimum_rest_hours": first.minimum_rest_hours}))

        by_week: dict[tuple[int, int], list[Shift]] = defaultdict(list)
        for shift in ordered:
            by_week[_weekly_key(shift)].append(shift)
        employee = employees_by_id[employee_id]
        for week, week_shifts in by_week.items():
            forced_hours = sum(shift.duration_minutes for shift in week_shifts) / 60
            if forced_hours > employee.max_hours_per_week:
                add(_conflict("MAX_HOURS_CONFLICT",
                    f"Employee {employee_id} is required for {forced_hours:g} hours in week {week[0]}-W{week[1]:02d}, above the weekly maximum of {employee.max_hours_per_week:g} hours.",
                    shift=week_shifts[-1], shifts=week_shifts, employee_ids=[employee_id],
                    required=round(forced_hours, 2), available=employee.max_hours_per_week,
                    gap=round(forced_hours-employee.max_hours_per_week, 2),
                    constraints=["minimum_staffing_or_skill_requirement", "maximum_weekly_hours"]))

    _project_conflicts(data, add)
    return conflicts


def _project_conflicts(data: SchedulingInput, add) -> None:
    active_projects = {project.id: project for project in data.projects if project.status.casefold() == "active"}
    for requirement in data.project_requirements:
        project = active_projects.get(requirement.project_id)
        if project is None:
            continue
        associated = [shift for shift in data.shifts if shift.project_id == project.id]
        before_deadline = _requirement_shifts(requirement, project, data)
        employees = [employee for employee in data.employees if employee.active and _qualified(employee, requirement)]
        available_shifts = []
        all_date_shifts = []
        for shift in associated:
            possible = [employee for employee in employees
                        if (shift.allow_cross_department or shift.department is None or employee.department == shift.department)
                        and round(employee.max_hours_per_week * 60) >= shift.duration_minutes
                        and _availability_covers(employee.id, shift, data.availability)
                        and not _on_approved_leave(employee.id, shift, data.leave)]
            if possible:
                all_date_shifts.append((shift, possible))
            if shift in before_deadline and possible:
                available_shifts.append((shift, possible))

        qualified_before = {employee.id for _shift, people in available_shifts for employee in people}
        # This is a capacity upper bound: overlapping/rest interactions can only
        # reduce realizable hours, so a reported deficit remains evidence-based.
        def hours_upper_bound(entries):
            by_employee_week: dict[tuple[Any, tuple[int, int]], int] = defaultdict(int)
            for shift, people in entries:
                for employee in people:
                    by_employee_week[employee.id, _weekly_key(shift)] += shift.duration_minutes
            capacity = {employee.id: round(employee.max_hours_per_week * 60) for employee in employees}
            return round(sum(min(minutes, capacity[employee_id])
                             for (employee_id, _week), minutes in by_employee_week.items()) / 60, 2)

        hours_before = hours_upper_bound(available_shifts)
        hours_overall = hours_upper_bound(all_date_shifts)
        missing_count = max(0, requirement.required_count - len(qualified_before))
        missing_hours = round(max(0.0, requirement.required_hours - hours_before), 2)
        if not missing_count and not missing_hours:
            continue
        if missing_hours and hours_overall >= requirement.required_hours:
            conflict_type = "DEADLINE_CONFLICT"
            message = (f"Project {project.name} requires {requirement.required_hours:g} qualified hours by "
                       f"{(requirement.deadline or project.deadline).isoformat() if requirement.deadline or project.deadline else 'its deadline'}, "
                       f"but only {hours_before:g} hours of qualified associated shift capacity end by then; "
                       f"{hours_overall:g} hours are available across all associated dates.")
        else:
            conflict_type = "PROJECT_REQUIREMENT_SHORTAGE"
            message = f"Project {project.name} requirement {requirement.id} has insufficient qualified project work before its deadline."
        required_value = requirement.required_hours if missing_hours else requirement.required_count
        available_value = hours_before if missing_hours else len(qualified_before)
        gap_value = missing_hours if missing_hours else missing_count
        add(_conflict(conflict_type, message,
            shift=before_deadline[0] if before_deadline else (associated[0] if associated else None),
            shifts=before_deadline or associated,
            employee_ids=list(qualified_before), project_id=project.id,
            requirement_id=requirement.id, skill=requirement.skill_name,
            required=required_value, available=available_value, gap=gap_value,
            constraints=["project_assignment", "required_skill", "minimum_proficiency", "project_deadline"],
            details={"project_name": project.name, "required_count": requirement.required_count,
                     "qualified_count": len(qualified_before), "missing_count": missing_count,
                     "required_hours": requirement.required_hours,
                     "available_qualified_hours_before_deadline": hours_before,
                     "available_qualified_hours_all_dates": hours_overall,
                     "missing_hours": missing_hours,
                     "deadline": (requirement.deadline or project.deadline).isoformat()
                                 if requirement.deadline or project.deadline else None}))
