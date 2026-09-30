"""Typed, database-independent input and decision-variable construction."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
import math
from typing import Any, Mapping

from ortools.sat.python import cp_model

Identifier = int | str

@dataclass(frozen=True, slots=True)
class SkillProficiency:
    name: str
    proficiency: int = 1

@dataclass(frozen=True, slots=True)
class RequiredSkill:
    name: str
    required_count: int = 1
    minimum_proficiency: int = 1

@dataclass(frozen=True, slots=True)
class AvailabilityWindow:
    employee_id: Identifier
    start: datetime
    end: datetime
    available: bool = True

@dataclass(frozen=True, slots=True)
class LeavePeriod:
    employee_id: Identifier
    start_date: date
    end_date: date
    status: str = "approved"

@dataclass(frozen=True, slots=True)
class EmployeePreference:
    employee_id: Identifier
    key: str
    value: str
    weight: float = 1.0

@dataclass(frozen=True, slots=True)
class Project:
    id: Identifier
    name: str
    deadline: date | None = None
    status: str = "planned"
    priority: int | None = None

@dataclass(frozen=True, slots=True)
class ProjectRequirement:
    id: Identifier
    project_id: Identifier
    skill_name: str | None = None
    role: str = "staff"
    required_count: int = 1
    required_hours: float = 0.0
    deadline: date | None = None
    minimum_proficiency: int = 1

@dataclass(frozen=True, slots=True)
class Employee:
    id: Identifier
    name: str
    department: str | None = None
    skills: tuple[SkillProficiency, ...] = ()
    max_hours_per_week: float = 40.0
    hourly_rate: float = 0.0
    active: bool = True

@dataclass(frozen=True, slots=True)
class Shift:
    id: Identifier
    date: date
    start_time: time
    end_time: time
    required_staff: int = 1
    name: str = "Shift"
    department: str | None = None
    required_skills: tuple[RequiredSkill, ...] = ()
    allow_cross_department: bool = False
    minimum_rest_hours: float = 0.0
    project_id: Identifier | None = None

    @property
    def starts_at(self) -> datetime:
        return datetime.combine(self.date, self.start_time)

    @property
    def ends_at(self) -> datetime:
        end = datetime.combine(self.date, self.end_time)
        return end + timedelta(days=1) if end <= self.starts_at else end

    @property
    def duration_minutes(self) -> int:
        seconds = (self.ends_at - self.starts_at).total_seconds()
        minutes = round(seconds / 60)
        if minutes <= 0 or abs(seconds - minutes * 60) > 1e-6:
            raise ValueError(f"Shift {self.id!r} must have a positive whole-minute duration")
        return minutes

@dataclass(frozen=True, slots=True)
class SchedulingInput:
    employees: tuple[Employee, ...]
    shifts: tuple[Shift, ...]
    availability: tuple[AvailabilityWindow, ...] = ()
    leave: tuple[LeavePeriod, ...] = ()
    preferences: tuple[EmployeePreference, ...] = ()
    projects: tuple[Project, ...] = ()
    project_requirements: tuple[ProjectRequirement, ...] = ()
    department_exceptions: tuple[tuple[Identifier, Identifier], ...] = ()

@dataclass(frozen=True, slots=True)
class DecisionVariables:
    model: cp_model.CpModel
    assignments: dict[tuple[Identifier, Identifier], cp_model.IntVar]


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    return value if isinstance(value, date) else date.fromisoformat(str(value))

def _as_time(value: Any) -> time:
    return value if isinstance(value, time) else time.fromisoformat(str(value))

def _as_datetime(value: Any, day: Any = None, clock: Any = None) -> datetime:
    if value is None:
        if day is None or clock is None:
            raise ValueError("Availability windows require start/end datetimes or date and time fields")
        value = datetime.combine(_as_date(day), _as_time(clock))
    elif not isinstance(value, datetime):
        value = datetime.fromisoformat(str(value))
    if value.tzinfo is not None:
        value = value.astimezone(UTC).replace(tzinfo=None)
    return value

def _skill_levels(raw: Any) -> tuple[SkillProficiency, ...]:
    if raw is None:
        return ()
    if isinstance(raw, Mapping):
        return tuple(SkillProficiency(str(name), int(level)) for name, level in raw.items())
    result=[]
    for skill in raw:
        if isinstance(skill, str):
            result.append(SkillProficiency(skill))
        elif isinstance(skill, Mapping):
            result.append(SkillProficiency(str(skill.get("name", skill.get("skill"))), int(skill.get("proficiency", 1))))
        else:
            result.append(SkillProficiency(str(skill.name), int(getattr(skill, "proficiency", 1))))
    return tuple(result)

def _required_skills(raw: Any) -> tuple[RequiredSkill, ...]:
    if raw is None:
        return ()
    if isinstance(raw, Mapping):
        raw=[{"name": name, **(dict(value) if isinstance(value, Mapping) else {"required_count": value})} for name, value in raw.items()]
    result=[]
    for item in raw:
        if isinstance(item, str):
            result.append(RequiredSkill(item))
        elif isinstance(item, Mapping):
            result.append(RequiredSkill(str(item.get("name", item.get("skill"))), int(item.get("required_count", item.get("count", 1))), int(item.get("minimum_proficiency", item.get("min_proficiency", 1)))))
        else:
            result.append(RequiredSkill(str(item.name), int(getattr(item, "required_count", 1)), int(getattr(item, "minimum_proficiency", 1))))
    return tuple(result)

def normalize_preference_weight(value: Any) -> float:
    """Return a finite non-negative preference weight, defaulting to 1."""
    try:
        weight = float(value)
    except (TypeError, ValueError):
        return 1.0
    return weight if math.isfinite(weight) and weight >= 0 else 1.0

def scheduling_input_from_mapping(raw: Mapping[str, Any]) -> SchedulingInput:
    """Convert basic dictionaries/JSON data to the optimizer's typed input."""
    employees=tuple(Employee(
        id=item.get("id", item.get("employee_id")), name=str(item.get("name", item.get("employee_name", ""))),
        department=item.get("department", item.get("department_id")), skills=_skill_levels(item.get("skills")),
        max_hours_per_week=float(item.get("max_hours_per_week", 40)), hourly_rate=float(item.get("hourly_rate", 0)),
        active=bool(item.get("active", True)),
    ) for item in raw.get("employees", ()))
    shifts=tuple(Shift(
        id=item.get("id", item.get("shift_id")), date=_as_date(item["date"]),
        start_time=_as_time(item["start_time"]), end_time=_as_time(item["end_time"]),
        required_staff=int(item.get("required_staff", 1)), name=str(item.get("name", item.get("shift_name", "Shift"))),
        department=item.get("department", item.get("department_id")), required_skills=_required_skills(item.get("required_skills")),
        allow_cross_department=bool(item.get("allow_cross_department", item.get("cross_department_allowed", False))),
        minimum_rest_hours=float(item.get("minimum_rest_hours", item.get("min_rest_hours", 0))),
        project_id=item.get("project_id"),
    ) for item in raw.get("shifts", ()))
    availability=tuple(AvailabilityWindow(
        employee_id=item.get("employee_id"),
        start=_as_datetime(item.get("start", item.get("start_datetime")), item.get("date"), item.get("start_time")),
        end=_as_datetime(item.get("end", item.get("end_datetime")), item.get("date"), item.get("end_time")),
        available=bool(item.get("available", True)),
    ) for item in raw.get("availability", ()))
    leave=tuple(LeavePeriod(
        employee_id=item.get("employee_id"), start_date=_as_date(item["start_date"]),
        end_date=_as_date(item["end_date"]), status=str(item.get("status", "approved")),
    ) for item in raw.get("leave", ()))
    preferences=tuple(EmployeePreference(
        employee_id=item["employee_id"], key=str(item.get("key", "")),
        value=str(item.get("value", "")), weight=normalize_preference_weight(item.get("weight", 1.0)),
    ) for item in raw.get("preferences", ()))
    projects=tuple(Project(
        id=item.get("id", item.get("project_id")), name=str(item.get("name", "")),
        deadline=_as_date(item["deadline"]) if item.get("deadline") else None,
        status=str(item.get("status", "planned")), priority=item.get("priority"),
    ) for item in raw.get("projects", ()))
    project_requirements=tuple(ProjectRequirement(
        id=item.get("id", index), project_id=item.get("project_id"),
        skill_name=item.get("skill_name", item.get("skill")), role=str(item.get("role", "staff")),
        required_count=int(item.get("required_count", item.get("quantity", 1))),
        required_hours=float(item.get("required_hours", 0)),
        deadline=_as_date(item["deadline"]) if item.get("deadline") else None,
        minimum_proficiency=int(item.get("minimum_proficiency", 1)),
    ) for index, item in enumerate(raw.get("project_requirements", ())))
    return SchedulingInput(employees=employees, shifts=shifts, availability=availability,
                           leave=leave, preferences=preferences, projects=projects,
                           project_requirements=project_requirements)

def create_decision_variables(data: SchedulingInput) -> DecisionVariables:
    """Create exactly one BoolVar for each unique employee/shift pair."""
    employee_ids=[employee.id for employee in data.employees]
    shift_ids=[shift.id for shift in data.shifts]
    if len(set(employee_ids)) != len(employee_ids):
        raise ValueError("Employee IDs must be unique")
    if len(set(shift_ids)) != len(shift_ids):
        raise ValueError("Shift IDs must be unique")
    model=cp_model.CpModel()
    variables={(employee.id, shift.id): model.new_bool_var(f"assign_e{ei}_s{si}")
               for ei, employee in enumerate(data.employees) for si, shift in enumerate(data.shifts)}
    return DecisionVariables(model=model, assignments=variables)
