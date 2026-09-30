"""Prepare persisted workforce data for the database-independent CP-SAT optimizer."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import date, datetime, time, timedelta
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


class SchedulingDataError(ValueError):
    """Raised when persisted inputs are malformed before optimization starts."""


def generate_schedule(input_data: SchedulingInput | Mapping[str, Any]) -> dict[str, Any]:
    """Preserve the original database-independent service API."""
    if isinstance(input_data, Mapping):
        input_data = scheduling_input_from_mapping(input_data)
    result = solve_schedule(input_data)
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
        skills=tuple(SkillProficiency(skill.name) for skill in item.skills),
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
        "assignments": [],
        "unassigned_shifts": result.unassigned_shifts,
        "employee_hours": result.employee_hours,
        "message": None,
    }
    if result.status != "FEASIBLE":
        response["message"] = "No feasible schedule exists for the requested period."
        return response

    try:
        schedule = models.Schedule(
            name=f"Generated schedule {start_date.isoformat()} to {end_date.isoformat()}",
            start_date=start_date, end_date=end_date, status="generated",
            objective_value=None, total_cost=result.total_cost,
            overtime_hours=result.total_overtime_hours,
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
