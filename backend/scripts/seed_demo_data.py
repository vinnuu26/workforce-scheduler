"""Seed a small, repeatable workforce demo without deleting existing data.

Run from ``backend`` with the project Python environment:
    .\\venv\\Scripts\\python.exe scripts\\seed_demo_data.py

The script adds missing demo rows only; it never resets the database.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path
import sys

from sqlalchemy import select, update

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import models
from app.database import Base, SessionLocal, engine


def main() -> None:
    Base.metadata.create_all(bind=engine)
    today = date.today()
    start = today + timedelta(days=(7 - today.weekday()) % 7)
    end = start + timedelta(days=6)
    db = SessionLocal()
    try:
        department_names = ("Operations", "Logistics", "Customer Care")
        departments = {}
        for name in department_names:
            row = db.scalar(select(models.Department).where(models.Department.name == name))
            if row is None:
                row = models.Department(name=name, description=f"Demo {name.lower()} team")
                db.add(row); db.flush()
            departments[name] = row

        skill_names = ("Operations", "Forklift", "Safety", "Dispatch", "Customer Support", "Inventory")
        skills = {}
        for name in skill_names:
            row = db.scalar(select(models.Skill).where(models.Skill.name == name))
            if row is None:
                row = models.Skill(name=name, description=f"Demo qualification: {name}")
                db.add(row); db.flush()
            skills[name] = row

        templates = {}
        for name, start_time, end_time in (("Early", time(6), time(14)), ("Day", time(9), time(17)), ("Late", time(14), time(22))):
            row = db.scalar(select(models.ShiftTemplate).where(models.ShiftTemplate.name == name))
            if row is None:
                row = models.ShiftTemplate(name=name, start_time=start_time, end_time=end_time, description="Demo eight-hour coverage")
                db.add(row); db.flush()
            templates[name] = row

        team_skills = {
            "Operations": ("Operations", "Forklift", "Safety", "Inventory"),
            "Logistics": ("Operations", "Dispatch", "Safety", "Inventory"),
            "Customer Care": ("Operations", "Customer Support", "Safety"),
        }
        employees = {}
        for department, qualifications in team_skills.items():
            for index in range(1, 5):
                email = f"demo.{department.lower().replace(' ', '.')}\u002e{index}@example.test"
                row = db.scalar(select(models.Employee).where(models.Employee.email == email))
                if row is None:
                    row = models.Employee(name=f"{department} Teammate {index}", email=email,
                        department_id=departments[department].id, active=True,
                        hourly_rate=22 + index * 2, max_hours_per_week=40)
                    qualification_index = 1 + ((index - 1) % (len(qualifications) - 1))
                    row.skills = [skills[qualifications[0]], skills[qualifications[qualification_index]]]
                    db.add(row); db.flush()
                employees[(department, index)] = row
                # Update levels every run so seeded proficiency data stays demonstrative and idempotent.
                for skill in row.skills:
                    level = 1 + ((index + skill.id) % 5)
                    db.execute(update(models.employee_skills).where(
                        models.employee_skills.c.employee_id == row.id,
                        models.employee_skills.c.skill_id == skill.id,
                    ).values(proficiency=level))

        project_specs = (("Regional Fulfilment Demo", "active"), ("Dispatch Coverage Demo", "planned"), ("Service Desk Demo", "active"))
        projects = {}
        for name, status in project_specs:
            row = db.scalar(select(models.Project).where(models.Project.name == name))
            if row is None:
                row = models.Project(name=name, status=status, description="Seeded demonstration project", deadline=end + timedelta(days=7))
                db.add(row); db.flush()
            projects[name] = row
        requirement_specs = ((projects[project_specs[0][0]], skills["Forklift"], "forklift coverage"),
                             (projects[project_specs[2][0]], skills["Customer Support"], "service coverage"))
        for project, skill, role in requirement_specs:
            exists = db.scalar(select(models.ProjectRequirement.id).where(
                models.ProjectRequirement.project_id == project.id,
                models.ProjectRequirement.skill_id == skill.id,
                models.ProjectRequirement.role == role,
            ))
            if exists is None:
                db.add(models.ProjectRequirement(project_id=project.id, skill_id=skill.id, role=role,
                    quantity=1, required_hours=8, minimum_proficiency=1))

        department_project = {"Operations": projects[project_specs[0][0]], "Logistics": projects[project_specs[1][0]],
                              "Customer Care": projects[project_specs[2][0]]}
        for offset in range(7):
            day = start + timedelta(days=offset)
            for index, department in enumerate(department_names):
                shift_name = ("Early", "Day", "Late")[index]
                exists = db.scalar(select(models.Shift.id).where(
                    models.Shift.date == day, models.Shift.department_id == departments[department].id,
                    models.Shift.template_id == templates[shift_name].id,
                ))
                if exists is None:
                    shift = models.Shift(date=day, department_id=departments[department].id,
                        template_id=templates[shift_name].id,
                        project_id=department_project[department].id if offset < 3 else None,
                        required_staff=2)
                    shift.required_skills = [skills[team_skills[department][0]]]
                    db.add(shift)

        # One intentionally impossible demand is isolated to the day after the feasible demo week.
        impossible_day = end + timedelta(days=1)
        impossible_exists = db.scalar(select(models.Shift.id).where(
            models.Shift.date == impossible_day, models.Shift.required_staff == 999,
        ))
        if impossible_exists is None:
            db.add(models.Shift(date=impossible_day, department_id=departments["Operations"].id,
                template_id=templates["Early"].id, required_staff=999))

        for (department, index), employee in employees.items():
            for offset in range(7):
                day = start + timedelta(days=offset)
                exists = db.scalar(select(models.Availability.id).where(
                    models.Availability.employee_id == employee.id,
                    models.Availability.date == day,
                    models.Availability.available.is_(True),
                ))
                if exists is None:
                    db.add(models.Availability(employee_id=employee.id, date=day,
                        start_time=time(0), end_time=time(23, 59), available=True))
            # An explicit unavailable interval demonstrates availability exclusions.
            unavailable_day = start + timedelta(days=(index + 1) % 7)
            exists = db.scalar(select(models.Availability.id).where(
                models.Availability.employee_id == employee.id,
                models.Availability.date == unavailable_day,
                models.Availability.available.is_(False),
            ))
            if exists is None:
                db.add(models.Availability(employee_id=employee.id, date=unavailable_day,
                    start_time=time(0), end_time=time(23, 59), available=False,
                    notes="Seeded demo unavailable day"))
            if index == 3:
                leave_exists = db.scalar(select(models.Leave.id).where(
                    models.Leave.employee_id == employee.id,
                    models.Leave.start_date == start + timedelta(days=4),
                    models.Leave.reason == "Seeded demo approved leave",
                ))
                if leave_exists is None:
                    day = start + timedelta(days=4)
                    db.add(models.Leave(employee_id=employee.id, start_date=day, end_date=day,
                        status="approved", reason="Seeded demo approved leave"))
            preference_exists = db.scalar(select(models.EmployeePreference.id).where(
                models.EmployeePreference.employee_id == employee.id,
                models.EmployeePreference.key == "preferred_shift",
            ))
            if preference_exists is None:
                preferred_shifts = ("Early", "Day", "Late")
                db.add(models.EmployeePreference(employee_id=employee.id, key="preferred_shift",
                    value=preferred_shifts[(index - 1) % len(preferred_shifts)], weight=float(index),
                    notes="Seeded demo preference"))
        db.commit()
        print(f"Demo data ready: feasible period {start.isoformat()} through {end.isoformat()}; "
              f"intentional infeasible demand on {impossible_day.isoformat()}.")
        print("Run the schedule generator for the seven-day period, then analyze the next day for a staffing conflict.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
