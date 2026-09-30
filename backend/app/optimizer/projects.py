"""Hard project requirement constraints and factual completion metrics."""
from __future__ import annotations

import math
from typing import Any

from ortools.sat.python import cp_model

from .model import Employee, Project, ProjectRequirement, SchedulingInput, Shift


def _requirement_shifts(requirement: ProjectRequirement, project: Project, data: SchedulingInput) -> list[Shift]:
    """Return associated shifts fully completed by the effective deadline."""
    deadline = requirement.deadline or project.deadline
    return [shift for shift in data.shifts
            if shift.project_id == project.id and (deadline is None or shift.ends_at.date() <= deadline)]


def _qualified(employee: Employee, requirement: ProjectRequirement) -> bool:
    if requirement.skill_name is None:
        return True
    return any(skill.name == requirement.skill_name
               and skill.proficiency >= requirement.minimum_proficiency for skill in employee.skills)


def add_project_requirement_constraints(
    model: cp_model.CpModel, assignments: dict, data: SchedulingInput,
) -> None:
    """Require each explicit requirement for an active project as hard constraints."""
    projects = {project.id: project for project in data.projects if project.status.casefold() == "active"}
    for requirement_index, requirement in enumerate(data.project_requirements):
        project = projects.get(requirement.project_id)
        if project is None:
            continue
        if requirement.required_count < 0 or requirement.required_hours < 0 or requirement.minimum_proficiency < 1:
            raise ValueError(f"Project requirement {requirement.id!r} has invalid count, hours, or proficiency")
        shifts = _requirement_shifts(requirement, project, data)
        qualified_employees = [employee for employee in data.employees if employee.active and _qualified(employee, requirement)]
        # Count distinct qualified employees who receive at least one matching project shift.
        if requirement.required_count:
            participating = []
            for employee_index, employee in enumerate(qualified_employees):
                employee_assignments = [assignments[employee.id, shift.id] for shift in shifts]
                if not employee_assignments:
                    continue
                participant = model.new_bool_var(f"project_{requirement_index}_employee_{employee_index}")
                for assignment in employee_assignments:
                    model.add(assignment <= participant)
                model.add(participant <= sum(employee_assignments))
                participating.append(participant)
            model.add(sum(participating) >= requirement.required_count)

        if requirement.required_hours:
            required_minutes = math.ceil(requirement.required_hours * 60 - 1e-9)
            model.add(sum(assignments[employee.id, shift.id] * shift.duration_minutes
                          for employee in qualified_employees for shift in shifts) >= required_minutes)


def project_metrics(assignments: list[dict[str, Any]], data: SchedulingInput) -> list[dict[str, Any]]:
    """Return requirement completion using only qualifying, on-project work."""
    projects = {project.id: project for project in data.projects if project.status.casefold() == "active"}
    employees = {employee.id: employee for employee in data.employees}
    results = []
    for project in projects.values():
        project_requirements = []
        completion_values = []
        for requirement in (item for item in data.project_requirements if item.project_id == project.id):
            eligible_shifts = {shift.id: shift for shift in _requirement_shifts(requirement, project, data)}
            eligible_assignments = [item for item in assignments
                                    if item["shift_id"] in eligible_shifts
                                    and _qualified(employees[item["employee_id"]], requirement)]
            scheduled_hours = round(sum(eligible_shifts[item["shift_id"]].duration_minutes
                                        for item in eligible_assignments) / 60, 2)
            assigned_employee_count = len({item["employee_id"] for item in eligible_assignments})
            hour_completion = min(1.0, scheduled_hours / requirement.required_hours) if requirement.required_hours else 1.0
            count_completion = min(1.0, assigned_employee_count / requirement.required_count) if requirement.required_count else 1.0
            completion = min(hour_completion, count_completion)
            completion_values.append(completion)
            project_requirements.append({
                "requirement_id": requirement.id,
                "skill": requirement.skill_name,
                "role": requirement.role,
                "required_count": requirement.required_count,
                "assigned_employee_count": assigned_employee_count,
                "required_hours": requirement.required_hours,
                "scheduled_hours": scheduled_hours,
                "remaining_hours": round(max(0.0, requirement.required_hours - scheduled_hours), 2),
                "deadline": (requirement.deadline or project.deadline).isoformat() if requirement.deadline or project.deadline else None,
                "satisfied": scheduled_hours + 1e-9 >= requirement.required_hours
                            and assigned_employee_count >= requirement.required_count,
            })
        results.append({
            "project_id": project.id, "project_name": project.name,
            "deadline": project.deadline.isoformat() if project.deadline else None,
            "requirements": project_requirements,
            "completion_percentage": round(100 * (sum(completion_values) / len(completion_values)), 2)
                                    if completion_values else 100.0,
        })
    return results
