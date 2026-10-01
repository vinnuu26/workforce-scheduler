from datetime import date, time
from pydantic import BaseModel, ConfigDict, Field, model_validator
class APIModel(BaseModel):
    model_config=ConfigDict(from_attributes=True, extra="ignore")
class DepartmentCreate(APIModel): name:str; description:str|None=None
class SkillCreate(APIModel): name:str; description:str|None=None
class EmployeeCreate(APIModel): name:str; email:str; department_id:int|None=None; active:bool=True; hourly_rate:float=0.0; max_hours_per_week:float=40.0
class ShiftTemplateCreate(APIModel): name:str; start_time:time; end_time:time; description:str|None=None
class ShiftCreate(APIModel): date:date; department_id:int|None=None; template_id:int|None=None; project_id:int|None=None; start_time:time|None=None; end_time:time|None=None; required_staff:int=1
class AvailabilityCreate(APIModel): employee_id:int; date:date; start_time:time|None=None; end_time:time|None=None; available:bool=True; notes:str|None=None
class LeaveCreate(APIModel): employee_id:int; start_date:date; end_date:date; status:str="pending"; reason:str|None=None
class PreferenceCreate(APIModel): employee_id:int; key:str; value:str; weight:float|None=1.0; notes:str|None=None
class ProjectCreate(APIModel): name:str; status:str="planned"; description:str|None=None; deadline:date|None=None
class RequirementCreate(APIModel): skill_id:int|None=None; role:str="staff"; quantity:int=Field(default=1,ge=1); required_hours:float=Field(default=0.0,ge=0); minimum_proficiency:int=Field(default=1,ge=1,le=5)
class ScheduleCreate(APIModel): name:str; start_date:date|None=None; end_date:date|None=None; status:str="draft"
class AssignmentCreate(APIModel): employee_id:int; shift_id:int; notes:str|None=None
class OptimizationRequest(APIModel):
    start_date:date
    end_date:date
    department_id:int|None=None
    project_id:int|None=None

    @model_validator(mode="after")
    def validate_date_range(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self

class AlternativeOptimizationRequest(OptimizationRequest):
    count:int=Field(default=3,ge=1,le=5)

class ReschedulePreviewRequest(APIModel):
    schedule_id: int = Field(ge=1)
    assignment_id: int = Field(ge=1)

class RescheduleApplyRequest(ReschedulePreviewRequest):
    confirmed: bool

class ConflictResolutionRequest(APIModel):
    start_date: date
    end_date: date
    resolution_id: str = Field(min_length=1, max_length=16)
    department_id: int|None=None
    project_id: int|None=None
    confirmed: bool = False

    @model_validator(mode="after")
    def validate_resolution_range(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self

class EmployeeSkillRequest(APIModel):
    skill_id: int = Field(ge=1)
    proficiency: int = Field(default=1, ge=1, le=5)

class RequirementUpdate(APIModel):
    skill_id:int|None=None; role:str|None=None; quantity:int|None=Field(default=None,ge=1); required_hours:float|None=Field(default=None,ge=0); minimum_proficiency:int|None=Field(default=None,ge=1,le=5)
