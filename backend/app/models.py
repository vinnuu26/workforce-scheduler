from datetime import UTC, date, time, datetime
from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Time, Table, Column, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

employee_skills=Table("employee_skills", Base.metadata, Column("employee_id", ForeignKey("employees.id", ondelete="CASCADE"), primary_key=True), Column("skill_id", ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True))
shift_skills=Table("shift_required_skills", Base.metadata, Column("shift_id", ForeignKey("shifts.id", ondelete="CASCADE"), primary_key=True), Column("skill_id", ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True))
class Department(Base):
    __tablename__="departments"
    id: Mapped[int]=mapped_column(primary_key=True); name: Mapped[str]=mapped_column(String(120), unique=True, index=True); description: Mapped[str|None]=mapped_column(Text, default=None)
class Skill(Base):
    __tablename__="skills"
    id: Mapped[int]=mapped_column(primary_key=True); name: Mapped[str]=mapped_column(String(120), unique=True, index=True); description: Mapped[str|None]=mapped_column(Text, default=None)
class Employee(Base):
    __tablename__="employees"
    id: Mapped[int]=mapped_column(primary_key=True); name: Mapped[str]=mapped_column(String(160)); email: Mapped[str]=mapped_column(String(255), unique=True, index=True); department_id: Mapped[int|None]=mapped_column(ForeignKey("departments.id"), default=None); active: Mapped[bool]=mapped_column(Boolean, default=True); hourly_rate: Mapped[float]=mapped_column(default=0.0); max_hours_per_week: Mapped[float]=mapped_column(default=40.0)
    department=relationship(Department); skills=relationship(Skill, secondary=employee_skills)
class ShiftTemplate(Base):
    __tablename__="shift_templates"
    id: Mapped[int]=mapped_column(primary_key=True); name: Mapped[str]=mapped_column(String(120)); start_time: Mapped[time]=mapped_column(Time); end_time: Mapped[time]=mapped_column(Time); description: Mapped[str|None]=mapped_column(Text, default=None)
class Shift(Base):
    __tablename__="shifts"
    id: Mapped[int]=mapped_column(primary_key=True); date: Mapped[date]=mapped_column(Date, index=True); department_id: Mapped[int|None]=mapped_column(ForeignKey("departments.id"), default=None); template_id: Mapped[int|None]=mapped_column(ForeignKey("shift_templates.id"), default=None); start_time: Mapped[time|None]=mapped_column(Time, default=None); end_time: Mapped[time|None]=mapped_column(Time, default=None); required_staff: Mapped[int]=mapped_column(Integer, default=1)
    department=relationship(Department); template=relationship(ShiftTemplate); required_skills=relationship(Skill, secondary=shift_skills)
class Availability(Base):
    __tablename__="availability"
    id: Mapped[int]=mapped_column(primary_key=True); employee_id: Mapped[int]=mapped_column(ForeignKey("employees.id")); date: Mapped[date]=mapped_column(Date, index=True); start_time: Mapped[time|None]=mapped_column(Time, default=None); end_time: Mapped[time|None]=mapped_column(Time, default=None); available: Mapped[bool]=mapped_column(Boolean, default=True); notes: Mapped[str|None]=mapped_column(Text, default=None)
class Leave(Base):
    __tablename__="leave_requests"
    id: Mapped[int]=mapped_column(primary_key=True); employee_id: Mapped[int]=mapped_column(ForeignKey("employees.id")); start_date: Mapped[date]=mapped_column(Date); end_date: Mapped[date]=mapped_column(Date); status: Mapped[str]=mapped_column(String(40), default="pending"); reason: Mapped[str|None]=mapped_column(Text, default=None)
class EmployeePreference(Base):
    __tablename__="employee_preferences"
    id: Mapped[int]=mapped_column(primary_key=True); employee_id: Mapped[int]=mapped_column(ForeignKey("employees.id")); key: Mapped[str]=mapped_column(String(100)); value: Mapped[str]=mapped_column(String(255)); weight: Mapped[float|None]=mapped_column(Float, nullable=True, default=1.0, server_default="1.0"); notes: Mapped[str|None]=mapped_column(Text, default=None)
class Project(Base):
    __tablename__="projects"
    id: Mapped[int]=mapped_column(primary_key=True); name: Mapped[str]=mapped_column(String(160)); status: Mapped[str]=mapped_column(String(40), default="planned"); description: Mapped[str|None]=mapped_column(Text, default=None)
class ProjectRequirement(Base):
    __tablename__="project_requirements"
    id: Mapped[int]=mapped_column(primary_key=True); project_id: Mapped[int]=mapped_column(ForeignKey("projects.id", ondelete="CASCADE")); skill_id: Mapped[int|None]=mapped_column(ForeignKey("skills.id"), default=None); role: Mapped[str]=mapped_column(String(120), default="staff"); quantity: Mapped[int]=mapped_column(Integer, default=1)
class Schedule(Base):
    __tablename__="schedules"
    id: Mapped[int]=mapped_column(primary_key=True); name: Mapped[str]=mapped_column(String(160)); start_date: Mapped[date|None]=mapped_column(Date, default=None); end_date: Mapped[date|None]=mapped_column(Date, default=None); status: Mapped[str]=mapped_column(String(40), default="draft"); objective_value: Mapped[float|None]=mapped_column(default=None); total_cost: Mapped[float]=mapped_column(default=0.0); overtime_hours: Mapped[float]=mapped_column(default=0.0); created_at: Mapped[datetime]=mapped_column(DateTime, default=lambda: datetime.now(UTC))
class ScheduleAssignment(Base):
    __tablename__="schedule_assignments"
    id: Mapped[int]=mapped_column(primary_key=True); schedule_id: Mapped[int]=mapped_column(ForeignKey("schedules.id", ondelete="CASCADE")); employee_id: Mapped[int]=mapped_column(ForeignKey("employees.id")); shift_id: Mapped[int]=mapped_column(ForeignKey("shifts.id")); regular_hours: Mapped[float]=mapped_column(default=0.0); overtime_hours: Mapped[float]=mapped_column(default=0.0); cost: Mapped[float]=mapped_column(default=0.0); notes: Mapped[str|None]=mapped_column(Text, default=None)
class ScheduleConflict(Base):
    __tablename__="schedule_conflicts"
    id: Mapped[int]=mapped_column(primary_key=True); schedule_id: Mapped[int]=mapped_column(ForeignKey("schedules.id", ondelete="CASCADE")); message: Mapped[str]=mapped_column(Text); details: Mapped[str|None]=mapped_column(Text, default=None)
class ScheduleExplanation(Base):
    __tablename__="schedule_explanations"
    id: Mapped[int]=mapped_column(primary_key=True); schedule_id: Mapped[int]=mapped_column(ForeignKey("schedules.id", ondelete="CASCADE")); message: Mapped[str]=mapped_column(Text); details: Mapped[str|None]=mapped_column(Text, default=None)
