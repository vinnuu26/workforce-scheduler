"""Prepare persisted workforce data for the database-independent CP-SAT optimizer."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import date, datetime, time, timedelta
from dataclasses import replace
import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app import models
from app.optimizer.model import (
    AvailabilityWindow, Employee as OptimizerEmployee, EmployeePreference as OptimizerPreference, LeavePeriod,
    Project as OptimizerProject, ProjectRequirement as OptimizerProjectRequirement,
    RequiredSkill, SchedulingInput, Shift as OptimizerShift, SkillProficiency,
    normalize_preference_weight, scheduling_input_from_mapping,
)
from app.optimizer.solver import solve_schedule
from app.optimizer.constraints import _availability_covers, _on_approved_leave
from app.services.conflict_detection_service import detect_conflicts
from app.conflicts.resolution import resolve_conflicts, apply_resolution_operations


class SchedulingDataError(ValueError):
    """Raised when persisted inputs are malformed before optimization starts."""


APPLYABLE_RESOLUTION_TYPES = {
    "REDUCE_STAFFING_REQUIREMENT", "ADJUST_PROJECT_REQUIRED_HOURS",
    "ADJUST_PROJECT_REQUIRED_COUNT", "EXTEND_PROJECT_DEADLINE",
}


def _verified_resolution_input(db: Session, start_date: date, end_date: date,
                               resolution_id: str, department_id: int | None,
                               project_id: int | None):
    original, employees, shifts = prepare_scheduling_input(db, start_date, end_date, department_id, project_id)
    analysis = resolve_conflicts(original)
    proposal = next((item for item in analysis.get("resolutions", [])
                     if item.get("resolution_id") == resolution_id), None)
    if not proposal or proposal.get("testable") is not True or proposal.get("feasible") is not True:
        raise SchedulingDataError("Resolution is missing, stale, untestable, or not optimizer-verified feasible")
    operations = proposal.get("operations") or []
    if not operations or any(item.get("type") not in APPLYABLE_RESOLUTION_TYPES for item in operations):
        raise SchedulingDataError("This verified resolution type cannot be applied automatically")
    normalized = []
    for operation in operations:
        item = dict(operation)
        if item["type"] == "EXTEND_PROJECT_DEADLINE":
            item["deadline"] = date.fromisoformat(item["deadline"])
        normalized.append(item)
    candidate = apply_resolution_operations(original, normalized)
    result = solve_schedule(candidate)
    if result.status != "FEASIBLE":
        raise SchedulingDataError("The selected repair no longer produces a feasible optimizer result")
    return proposal, normalized, candidate, result, employees, shifts


def preview_conflict_resolution_from_database(db: Session, start_date: date, end_date: date,
                                              resolution_id: str, department_id: int | None = None,
                                              project_id: int | None = None) -> dict[str, Any]:
    proposal, operations, _candidate, result, _employees, _shifts = _verified_resolution_input(
        db, start_date, end_date, resolution_id, department_id, project_id,
    )
    return {"status": result.status, "resolution_id": resolution_id, "resolution": proposal,
            "persisted": False, "start_date": start_date, "end_date": end_date,
            "assignments": result.assignments, "total_cost": result.total_cost,
            "total_required_staff": result.total_required_staff,
            "total_assigned_staff": result.total_assigned_staff,
            "operations": operations}


def apply_conflict_resolution_from_database(db: Session, start_date: date, end_date: date,
                                            resolution_id: str, confirmed: bool,
                                            department_id: int | None = None,
                                            project_id: int | None = None) -> dict[str, Any]:
    if not confirmed:
        raise SchedulingDataError("Explicit confirmation is required to apply a conflict resolution")
    try:
        proposal, operations, _candidate, _first_result, _employees, _shifts = _verified_resolution_input(
            db, start_date, end_date, resolution_id, department_id, project_id,
        )
        # Persist only reviewed changes to source staffing/project requirements. Hard optimizer
        # constraints are not disabled; the candidate is solved again after these values update.
        for operation in operations:
            kind = operation["type"]
            if kind == "REDUCE_STAFFING_REQUIREMENT":
                shift = db.get(models.Shift, operation["shift_id"])
                if shift is None or operation["value"] < 1 or operation["value"] >= shift.required_staff:
                    raise SchedulingDataError("Staffing requirement changed since analysis; analyze again")
                shift.required_staff = operation["value"]
            elif kind in {"ADJUST_PROJECT_REQUIRED_HOURS", "ADJUST_PROJECT_REQUIRED_COUNT"}:
                requirement = db.get(models.ProjectRequirement, operation["requirement_id"])
                if requirement is None:
                    raise SchedulingDataError("Project requirement no longer exists")
                column = "required_hours" if operation["field"] == "required_hours" else "quantity"
                current = getattr(requirement, column)
                if operation["value"] >= current or operation["value"] < 0:
                    raise SchedulingDataError("Project requirement changed since analysis; analyze again")
                setattr(requirement, column, operation["value"])
            elif kind == "EXTEND_PROJECT_DEADLINE":
                project = db.get(models.Project, operation["project_id"])
                if project is None or project.deadline is None:
                    raise SchedulingDataError("Project deadline changed since analysis; analyze again")
                expected = date.fromisoformat(operation["current_deadline"])
                if project.deadline != expected:
                    raise SchedulingDataError("Project deadline changed since analysis; analyze again")
                project.deadline = operation["deadline"]
                for requirement in db.scalars(select(models.ProjectRequirement).where(
                    models.ProjectRequirement.project_id == project.id,
                )).all():
                    if requirement.deadline is not None:
                        requirement.deadline = operation["deadline"]
        db.flush()
        data, employees_by_id, shifts_by_id = prepare_scheduling_input(
            db, start_date, end_date, department_id, project_id,
        )
        result = solve_schedule(data)
        if result.status != "FEASIBLE":
            raise SchedulingDataError("The selected repair failed server revalidation")
        schedule = models.Schedule(
            name=f"Resolved schedule {start_date.isoformat()} to {end_date.isoformat()}",
            start_date=start_date, end_date=end_date, status="generated", total_cost=result.total_cost,
            overtime_hours=result.total_overtime_hours, scope_department_id=department_id,
            scope_project_id=project_id,
        )
        db.add(schedule); db.flush()
        for assignment in result.assignments:
            db.add(models.ScheduleAssignment(schedule_id=schedule.id,
                employee_id=assignment["employee_id"], shift_id=assignment["shift_id"],
                regular_hours=assignment["regular_hours"], overtime_hours=assignment["overtime_hours"],
                cost=assignment["cost"]))
            db.add(models.ScheduleExplanation(schedule_id=schedule.id,
                message="Assignment included in the revalidated feasible conflict-resolution schedule.",
                details=json.dumps({"employee_id": assignment["employee_id"], "shift_id": assignment["shift_id"],
                                    "resolution_id": resolution_id}, sort_keys=True)))
        db.commit()
        return {"status": "FEASIBLE", "persisted": True, "schedule_id": schedule.id,
                "resolution_id": resolution_id, "resolution": proposal,
                "assignments": result.assignments, "total_cost": result.total_cost,
                "total_required_staff": result.total_required_staff,
                "total_assigned_staff": result.total_assigned_staff}
    except Exception:
        db.rollback()
        raise


def resolve_conflicts_from_database(
    db: Session, start_date: date, end_date: date, department_id: int | None = None,
    project_id: int | None = None,
) -> dict[str, Any]:
    """Analyze temporary candidate inputs only; this function never writes to the session."""
    data, _employees_by_id, _shifts_by_id = prepare_scheduling_input(
        db, start_date, end_date, department_id, project_id,
    )
    return resolve_conflicts(data)


def generate_schedule(input_data: SchedulingInput | Mapping[str, Any]) -> dict[str, Any]:
    """Preserve the original database-independent service API."""
    if isinstance(input_data, Mapping):
        input_data = scheduling_input_from_mapping(input_data)
    result = solve_schedule(input_data)
    conflicts = detect_conflicts(input_data) if result.status == "INFEASIBLE" else []
    return {
        "status": result.status, "solver_status": result.solver_status,
        "assignments": result.assignments, "unassigned_shifts": result.unassigned_shifts,
        "employee_hours": result.employee_hours,
        "total_required_staff": result.total_required_staff,
        "total_assigned_staff": result.total_assigned_staff,
        "total_excess_staff": result.total_excess_staff,
        "total_regular_hours": result.total_regular_hours,
        "total_overtime_hours": result.total_overtime_hours, "total_cost": result.total_cost,
        "objective": result.objective, "preference": result.preference,
        "fairness": result.fairness,
        "projects": result.projects,
        "conflicts": conflicts,
    }


def prepare_scheduling_input(
    db: Session, start_date: date, end_date: date, department_id: int | None = None,
    project_id: int | None = None,
) -> tuple[SchedulingInput, dict[int, models.Employee], dict[int, models.Shift]]:
    """Load and validate database rows, then convert them to optimizer value objects."""
    employees = list(db.scalars(
        select(models.Employee).options(joinedload(models.Employee.department), selectinload(models.Employee.skills))
        .order_by(models.Employee.id)
    ).unique())
    shifts_query = (
        select(models.Shift).options(
            joinedload(models.Shift.department), joinedload(models.Shift.template),
            selectinload(models.Shift.required_skills),
        ).where(models.Shift.date >= start_date, models.Shift.date <= end_date)
        .order_by(models.Shift.date, models.Shift.id)
    )
    if project_id is not None:
        if db.get(models.Project, project_id) is None:
            raise SchedulingDataError(f"project_id {project_id} does not reference an existing project")
        shifts_query = shifts_query.where(models.Shift.project_id == project_id)
    shifts = list(db.scalars(shifts_query).unique())
    if department_id is not None:
        if db.get(models.Department, department_id) is None:
            raise SchedulingDataError(f"department_id {department_id} does not reference an existing department")
        employees = [employee for employee in employees if employee.department_id == department_id]
        shifts = [shift for shift in shifts if shift.department_id == department_id]
    if project_id is not None:
        shifts = [shift for shift in shifts if shift.project_id == project_id]
    if not employees:
        raise SchedulingDataError("No employees are available for the requested scheduling period")
    if not shifts:
        raise SchedulingDataError("No shifts are available for the requested scheduling period")

    for employee in employees:
        if employee.department_id is not None and employee.department is None:
            raise SchedulingDataError(f"Employee {employee.id} references missing department {employee.department_id}")
        if employee.hourly_rate is None or employee.hourly_rate < 0:
            raise SchedulingDataError(f"Employee {employee.id} has an invalid hourly_rate")
        if employee.max_hours_per_week is None or employee.max_hours_per_week < 0:
            raise SchedulingDataError(f"Employee {employee.id} has an invalid max_hours_per_week")
    for shift in shifts:
        if shift.department_id is not None and shift.department is None:
            raise SchedulingDataError(f"Shift {shift.id} references missing department {shift.department_id}")
        start = shift.start_time or (shift.template.start_time if shift.template else None)
        end = shift.end_time or (shift.template.end_time if shift.template else None)
        if start is None or end is None:
            raise SchedulingDataError(f"Shift {shift.id} is missing a start or end time and has no complete template")
        if start == end:
            raise SchedulingDataError(f"Shift {shift.id} has an invalid time range: start and end are equal")
        if shift.required_staff < 1:
            raise SchedulingDataError(f"Shift {shift.id} required_staff must be at least 1")
        if any(skill is None or not skill.name.strip() for skill in shift.required_skills):
            raise SchedulingDataError(f"Shift {shift.id} has an invalid required skill reference")

    skill_ids = set(db.scalars(select(models.Skill.id)).all())
    selected_employee_ids = {employee.id for employee in employees}
    selected_shift_ids = {shift.id for shift in shifts}
    employee_skill_rows = db.execute(select(
        models.employee_skills.c.employee_id, models.employee_skills.c.skill_id,
    ).where(models.employee_skills.c.employee_id.in_(selected_employee_ids))).all()
    for employee_id, skill_id in employee_skill_rows:
        if skill_id not in skill_ids:
            raise SchedulingDataError(f"Employee {employee_id} references missing skill {skill_id}")
    shift_skill_rows = db.execute(select(
        models.shift_skills.c.shift_id, models.shift_skills.c.skill_id,
    ).where(models.shift_skills.c.shift_id.in_(selected_shift_ids))).all()
    for shift_id, skill_id in shift_skill_rows:
        if skill_id not in skill_ids:
            raise SchedulingDataError(f"Shift {shift_id} references missing required skill {skill_id}")

    employee_ids = [employee.id for employee in employees]
    availability_rows = list(db.scalars(select(models.Availability).where(
        models.Availability.employee_id.in_(employee_ids),
        models.Availability.date >= start_date, models.Availability.date <= end_date,
    )).all())
    availability: list[AvailabilityWindow] = []
    for item in availability_rows:
        if item.start_time is None or item.end_time is None or item.start_time == item.end_time:
            raise SchedulingDataError(f"Availability {item.id} must have a valid start_time and end_time")
        start_at = datetime.combine(item.date, item.start_time)
        end_at = datetime.combine(item.date, item.end_time)
        if end_at < start_at:
            end_at += timedelta(days=1)
        availability.append(AvailabilityWindow(item.employee_id, start_at, end_at, item.available))

    leave_rows = list(db.scalars(select(models.Leave).where(
        models.Leave.employee_id.in_(employee_ids),
        models.Leave.start_date <= end_date, models.Leave.end_date >= start_date,
    )).all())
    for item in leave_rows:
        if item.end_date < item.start_date:
            raise SchedulingDataError(f"Leave {item.id} has end_date before start_date")

    preference_rows = list(db.scalars(select(models.EmployeePreference).where(
        models.EmployeePreference.employee_id.in_(employee_ids),
    ).order_by(models.EmployeePreference.id)).all())

    optimizer_employees = tuple(OptimizerEmployee(
        id=item.id, name=item.name,
        department=item.department.name if item.department else None,
        active=item.active,
        hourly_rate=float(item.hourly_rate),
        max_hours_per_week=float(item.max_hours_per_week),
        skills=tuple(SkillProficiency(skill.name, int(db.execute(select(models.employee_skills.c.proficiency).where(models.employee_skills.c.employee_id == item.id, models.employee_skills.c.skill_id == skill.id)).scalar_one_or_none() or 1)) for skill in item.skills),
    ) for item in employees)
    optimizer_shifts = tuple(OptimizerShift(
        id=item.id, date=item.date,
        start_time=item.start_time or item.template.start_time,
        end_time=item.end_time or item.template.end_time,
        name=item.template.name if item.template else f"Shift {item.id}",
        department=item.department.name if item.department else None,
        required_staff=item.required_staff,
        required_skills=tuple(RequiredSkill(skill.name) for skill in item.required_skills),
        project_id=item.project_id,
    ) for item in shifts)
    optimizer_preferences = tuple(OptimizerPreference(
        employee_id=item.employee_id, key=item.key, value=item.value,
        weight=normalize_preference_weight(item.weight),
    ) for item in preference_rows)
    if project_id is not None:
        project_rows = list(db.scalars(
            select(models.Project).options(selectinload(models.Project.requirements).joinedload(models.ProjectRequirement.skill))
            .where(models.Project.id == project_id, func.lower(models.Project.status) == "active")
            .order_by(models.Project.id)
        ).unique())
    else:
        project_rows = list(db.scalars(
            select(models.Project).options(selectinload(models.Project.requirements).joinedload(models.ProjectRequirement.skill))
            .where(func.lower(models.Project.status) == "active")
            .order_by(models.Project.id)
        ).unique())
    optimizer_projects = tuple(OptimizerProject(
        id=item.id, name=item.name, deadline=item.deadline, status=item.status,
    ) for item in project_rows)
    optimizer_project_requirements = tuple(OptimizerProjectRequirement(
        id=requirement.id, project_id=requirement.project_id,
        skill_name=requirement.skill.name if requirement.skill else None, role=requirement.role,
        required_count=requirement.quantity, required_hours=float(requirement.required_hours or 0),
        deadline=item.deadline, minimum_proficiency=requirement.minimum_proficiency or 1,
    ) for item in project_rows for requirement in item.requirements)
    return SchedulingInput(optimizer_employees, optimizer_shifts, tuple(availability), tuple(
        LeavePeriod(item.employee_id, item.start_date, item.end_date, item.status) for item in leave_rows
    ), optimizer_preferences, optimizer_projects, optimizer_project_requirements), {item.id: item for item in employees}, {item.id: item for item in shifts}


def generate_schedule_from_database(
    db: Session, start_date: date, end_date: date, department_id: int | None = None,
    project_id: int | None = None,
) -> dict[str, Any]:
    """Run CP-SAT and persist a complete successful result in one transaction."""
    data, employees_by_id, shifts_by_id = prepare_scheduling_input(db, start_date, end_date, department_id, project_id)
    result = solve_schedule(data)
    conflicts = detect_conflicts(data) if result.status == "INFEASIBLE" else []
    total_required = sum(item.required_staff for item in data.shifts)
    response: dict[str, Any] = {
        "status": result.status, "solver_status": result.solver_status,
        "schedule_id": None, "start_date": start_date, "end_date": end_date,
        "total_required_staff": total_required,
        "total_assigned_staff": result.total_assigned_staff,
        "total_excess_staff": result.total_excess_staff,
        "total_cost": result.total_cost,
        "total_regular_hours": result.total_regular_hours,
        "total_overtime_hours": result.total_overtime_hours,
        "objective": result.objective,
        "preference": result.preference,
        "fairness": result.fairness,
        "projects": result.projects,
        "conflicts": conflicts,
        "assignments": [],
        "unassigned_shifts": result.unassigned_shifts,
        "employee_hours": result.employee_hours,
        "message": None,
    }
    if result.status != "FEASIBLE":
        response["message"] = "No feasible schedule exists for the requested period."
        return response

    try:
        optimizer_shifts_by_id = {item.id: item for item in data.shifts}
        schedule = models.Schedule(
            name=f"Generated schedule {start_date.isoformat()} to {end_date.isoformat()}",
            start_date=start_date, end_date=end_date, status="generated",
            objective_value=None, total_cost=result.total_cost,
            overtime_hours=result.total_overtime_hours, scope_department_id=department_id,
            scope_project_id=project_id,
        )
        db.add(schedule)
        db.flush()
        enriched = []
        for assignment in result.assignments:
            employee = employees_by_id[assignment["employee_id"]]
            shift = shifts_by_id[assignment["shift_id"]]
            hours = float(assignment["hours"])
            cost = round(hours * float(employee.hourly_rate), 2)
            db.add(models.ScheduleAssignment(
                schedule_id=schedule.id, employee_id=employee.id, shift_id=shift.id,
                regular_hours=hours, overtime_hours=0.0, cost=cost,
            ))
            explanation = {
                "employee_id": employee.id,
                "shift_id": shift.id,
                "project_id": shift.project_id,
                "department": shift.department.name if shift.department else None,
                "required_skills_matched": [skill.name for skill in shift.required_skills],
                "eligibility_checks": {
                    "employee_active": bool(employee.active),
                    "department_match": bool(shift.department_id is None or employee.department_id == shift.department_id),
                    "available_for_complete_shift": _availability_covers(employee.id, optimizer_shifts_by_id[shift.id], data.availability),
                    "approved_leave_applied": _on_approved_leave(employee.id, optimizer_shifts_by_id[shift.id], data.leave),
                },
                "preference_match": assignment.get("preference_match"),
                "preference_reasons": assignment.get("preference_reasons", []),
                "optimizer_objective": result.objective,
                "preference_metrics": result.preference,
                "fairness_metrics": result.fairness,
                "project_metrics": result.projects,
            }
            db.add(models.ScheduleExplanation(
                schedule_id=schedule.id,
                message="The optimizer included this assignment in a feasible schedule after applying its hard constraints and objective order.",
                details=json.dumps(explanation, sort_keys=True),
            ))
            enriched.append({
                **assignment,
                "department": shift.department.name if shift.department else None,
                "regular_hours": hours, "overtime_hours": 0.0, "cost": cost,
            })
        db.commit()
        response.update(schedule_id=schedule.id, assignments=enriched)
        return response
    except Exception:
        db.rollback()
        raise


def preview_reschedule_from_database(db: Session, schedule_id: int, assignment_id: int) -> dict[str, Any]:
    """Preview a full-day absence for an assigned employee without changing stored rows."""
    schedule = db.get(models.Schedule, schedule_id)
    if schedule is None:
        raise SchedulingDataError(f"schedule_id {schedule_id} does not reference an existing schedule")
    if schedule.start_date is None or schedule.end_date is None:
        raise SchedulingDataError("The selected schedule has no complete date range")
    assignment = db.get(models.ScheduleAssignment, assignment_id)
    if assignment is None or assignment.schedule_id != schedule_id:
        raise SchedulingDataError(f"assignment_id {assignment_id} is not part of schedule {schedule_id}")
    shift = db.get(models.Shift, assignment.shift_id)
    if shift is None or shift.date < schedule.start_date or shift.date > schedule.end_date:
        raise SchedulingDataError("The selected assignment shift is outside the saved schedule period")

    data, _employees, _shifts = prepare_scheduling_input(
        db, schedule.start_date, schedule.end_date, schedule.scope_department_id, schedule.scope_project_id,
    )
    candidate = replace(data, leave=(*data.leave, LeavePeriod(
        employee_id=assignment.employee_id, start_date=shift.date, end_date=shift.date, status="approved",
    )))
    result = solve_schedule(candidate)
    return {
        "status": result.status,
        "source_schedule_id": schedule_id,
        "source_assignment_id": assignment_id,
        "affected_employee_id": assignment.employee_id,
        "affected_shift_id": assignment.shift_id,
        "absence_date": shift.date,
        "persisted": False,
        "assignments": result.assignments,
        "total_required_staff": result.total_required_staff,
        "total_assigned_staff": result.total_assigned_staff,
        "total_cost": result.total_cost,
        "total_overtime_hours": result.total_overtime_hours,
        "objective": result.objective,
        "preference": result.preference,
        "fairness": result.fairness,
        "projects": result.projects,
        "conflicts": detect_conflicts(candidate) if result.status == "INFEASIBLE" else [],
    }


def apply_reschedule_from_database(db: Session, schedule_id: int, assignment_id: int, confirmed: bool) -> dict[str, Any]:
    """Revalidate a temporary absence candidate, then atomically replace schedule rows."""
    if not confirmed:
        raise SchedulingDataError("Explicit confirmation is required to apply a reschedule")
    try:
        preview = preview_reschedule_from_database(db, schedule_id, assignment_id)
        if preview["status"] != "FEASIBLE":
            raise SchedulingDataError("The reschedule candidate is not optimizer-verified feasible")
        schedule = db.get(models.Schedule, schedule_id)
        assignments = preview["assignments"]
        db.query(models.ScheduleAssignment).filter_by(schedule_id=schedule_id).delete(synchronize_session=False)
        db.query(models.ScheduleExplanation).filter_by(schedule_id=schedule_id).delete(synchronize_session=False)
        for item in assignments:
            db.add(models.ScheduleAssignment(
                schedule_id=schedule_id, employee_id=item["employee_id"], shift_id=item["shift_id"],
                regular_hours=float(item["regular_hours"]), overtime_hours=float(item["overtime_hours"]),
                cost=float(item["cost"]),
            ))
            db.add(models.ScheduleExplanation(
                schedule_id=schedule_id,
                message="Assignment included in the optimizer-verified reschedule.",
                details=json.dumps({"employee_id": item["employee_id"], "shift_id": item["shift_id"], "reschedule": True}),
            ))
        schedule.total_cost = float(preview["total_cost"])
        schedule.overtime_hours = float(preview["total_overtime_hours"])
        db.flush()
        result = {**preview, "persisted": True, "schedule_id": schedule_id, "assignments": assignments}
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
