import json
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models,schemas
from ..services.crud import get_item,list_items
from .factory import data
router=APIRouter(tags=["relationships"])
@router.post("/employees/{employee_id}/skills",status_code=201)
def add_employee_skill(employee_id:int, payload:schemas.EmployeeSkillRequest, db:Session=Depends(get_db)):
 e=get_item(db,models.Employee,employee_id); s=get_item(db,models.Skill,payload.skill_id)
 if s in e.skills: raise HTTPException(409,"Employee already has this skill")
 db.execute(models.employee_skills.insert().values(employee_id=employee_id,skill_id=s.id,proficiency=payload.proficiency)); db.expire(e,["skills"]); db.commit(); return data(e)
@router.put("/employees/{employee_id}/skills/{skill_id}")
def update_employee_skill(employee_id:int,skill_id:int,payload:dict,db:Session=Depends(get_db)):
 e=get_item(db,models.Employee,employee_id); get_item(db,models.Skill,skill_id)
 level=payload.get("proficiency")
 if not isinstance(level,int) or not 1 <= level <= 5: raise HTTPException(422,"proficiency must be an integer from 1 to 5")
 result=db.execute(models.employee_skills.update().where(models.employee_skills.c.employee_id==employee_id,models.employee_skills.c.skill_id==skill_id).values(proficiency=level))
 if not result.rowcount: raise HTTPException(404,"Employee skill not found")
 db.commit(); return data(e)
@router.delete("/employees/{employee_id}/skills/{skill_id}",status_code=204)
def remove_employee_skill(employee_id:int,skill_id:int,db:Session=Depends(get_db)):
 e=get_item(db,models.Employee,employee_id); s=get_item(db,models.Skill,skill_id)
 if s not in e.skills: raise HTTPException(404,"Employee skill not found")
 e.skills.remove(s); db.commit()
@router.post("/shifts/{shift_id}/skills",status_code=201)
def add_shift_skill(shift_id:int,payload:dict,db:Session=Depends(get_db)):
 sh=get_item(db,models.Shift,shift_id); sk=get_item(db,models.Skill,int(payload.get("skill_id",0)))
 if sk in sh.required_skills: raise HTTPException(409,"Shift already requires this skill")
 sh.required_skills.append(sk); db.commit(); return data(sh)
@router.delete("/shifts/{shift_id}/skills/{skill_id}",status_code=204)
def remove_shift_skill(shift_id:int,skill_id:int,db:Session=Depends(get_db)):
 sh=get_item(db,models.Shift,shift_id); sk=get_item(db,models.Skill,skill_id)
 if sk not in sh.required_skills: raise HTTPException(404,"Required skill not found")
 sh.required_skills.remove(sk); db.commit()
@router.post("/projects/{project_id}/requirements",status_code=201)
def add_requirement(project_id:int,payload:schemas.RequirementCreate,db:Session=Depends(get_db)):
 get_item(db,models.Project,project_id)
 if payload.skill_id is not None: get_item(db,models.Skill,payload.skill_id)
 q=db.query(models.ProjectRequirement).filter_by(project_id=project_id,skill_id=payload.skill_id,role=payload.role).first()
 if q: raise HTTPException(409,"Project requirement already exists")
 obj=models.ProjectRequirement(project_id=project_id,**payload.model_dump()); db.add(obj); db.commit(); db.refresh(obj); return data(obj)
@router.delete("/projects/{project_id}/requirements/{requirement_id}",status_code=204)
def remove_requirement(project_id:int,requirement_id:int,db:Session=Depends(get_db)):
 obj=get_item(db,models.ProjectRequirement,requirement_id)
 if obj.project_id!=project_id: raise HTTPException(404,"Project requirement not found")
 db.delete(obj); db.commit()
@router.put("/projects/{project_id}/requirements/{requirement_id}")
def update_requirement(project_id:int,requirement_id:int,payload:schemas.RequirementUpdate,db:Session=Depends(get_db)):
 obj=get_item(db,models.ProjectRequirement,requirement_id)
 if obj.project_id != project_id: raise HTTPException(404,"Project requirement not found")
 values=payload.model_dump(exclude_unset=True)
 if values.get("skill_id") is not None: get_item(db,models.Skill,values["skill_id"])
 for key,value in values.items(): setattr(obj,key,value)
 db.commit(); db.refresh(obj); return data(obj)
@router.get("/schedules/{schedule_id}/assignments")
def assignments(schedule_id:int,db:Session=Depends(get_db)):
 get_item(db,models.Schedule,schedule_id)
 rows=list_items(db,models.ScheduleAssignment,0,500,{"schedule_id":schedule_id})
 explanation_rows=list_items(db,models.ScheduleExplanation,0,500,{"schedule_id":schedule_id})
 explanation_by_pair={}
 for explanation in explanation_rows:
  try:
   details=json.loads(explanation.details or "{}")
   explanation_by_pair[(details.get("employee_id"),details.get("shift_id"))]={"message":explanation.message,"details":details}
  except (TypeError,ValueError):
   continue
 result=[]
 for item in rows:
  employee=get_item(db,models.Employee,item.employee_id); shift=get_item(db,models.Shift,item.shift_id)
  department=db.get(models.Department,shift.department_id) if shift.department_id is not None else None
  template=db.get(models.ShiftTemplate,shift.template_id) if shift.template_id is not None else None
  start=shift.start_time or (template.start_time if template else None)
  end=shift.end_time or (template.end_time if template else None)
  result.append({"id":item.id,"schedule_id":item.schedule_id,"employee_id":item.employee_id,
   "employee_name":employee.name,"shift_id":item.shift_id,
   "shift_name":template.name if template else f"Shift {shift.id}","shift_date":shift.date,
   "start_time":start,"end_time":end,"department":department.name if department else None,
   "hours":item.regular_hours+item.overtime_hours,"regular_hours":item.regular_hours,
   "overtime_hours":item.overtime_hours,"cost":item.cost,"notes":item.notes,
   "project_id":shift.project_id,
   "explanation":explanation_by_pair.get((item.employee_id,item.shift_id))})
 return result
@router.get("/schedules/{schedule_id}/conflicts")
def conflicts(schedule_id:int,db:Session=Depends(get_db)):
 get_item(db,models.Schedule,schedule_id); return [data(x) for x in list_items(db,models.ScheduleConflict,0,500,{"schedule_id":schedule_id})]
@router.get("/schedules/{schedule_id}/explanations")
def explanations(schedule_id:int,db:Session=Depends(get_db)):
 get_item(db,models.Schedule,schedule_id); return [data(x) for x in list_items(db,models.ScheduleExplanation,0,500,{"schedule_id":schedule_id})]
