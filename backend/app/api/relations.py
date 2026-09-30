from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models,schemas
from ..services.crud import get_item,list_items
from .factory import data
router=APIRouter(tags=["relationships"])
@router.post("/employees/{employee_id}/skills",status_code=201)
def add_employee_skill(employee_id:int, payload:dict, db:Session=Depends(get_db)):
 e=get_item(db,models.Employee,employee_id); s=get_item(db,models.Skill,int(payload.get("skill_id",0)))
 if s in e.skills: raise HTTPException(409,"Employee already has this skill")
 e.skills.append(s); db.commit(); return data(e)
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
@router.get("/schedules/{schedule_id}/assignments")
def assignments(schedule_id:int,db:Session=Depends(get_db)):
 get_item(db,models.Schedule,schedule_id); return [data(x) for x in list_items(db,models.ScheduleAssignment,0,500,{"schedule_id":schedule_id})]
@router.post("/schedules/{schedule_id}/assignments",status_code=201)
def add_assignment(schedule_id:int,payload:schemas.AssignmentCreate,db:Session=Depends(get_db)):
 get_item(db,models.Schedule,schedule_id); get_item(db,models.Employee,payload.employee_id); get_item(db,models.Shift,payload.shift_id)
 obj=models.ScheduleAssignment(schedule_id=schedule_id,**payload.model_dump()); db.add(obj); db.commit(); db.refresh(obj); return data(obj)
@router.delete("/schedules/{schedule_id}/assignments/{assignment_id}",status_code=204)
def remove_assignment(schedule_id:int,assignment_id:int,db:Session=Depends(get_db)):
 obj=get_item(db,models.ScheduleAssignment,assignment_id)
 if obj.schedule_id!=schedule_id: raise HTTPException(404,"Schedule assignment not found")
 db.delete(obj); db.commit()
@router.get("/schedules/{schedule_id}/conflicts")
def conflicts(schedule_id:int,db:Session=Depends(get_db)):
 get_item(db,models.Schedule,schedule_id); return [data(x) for x in list_items(db,models.ScheduleConflict,0,500,{"schedule_id":schedule_id})]
@router.get("/schedules/{schedule_id}/explanations")
def explanations(schedule_id:int,db:Session=Depends(get_db)):
 get_item(db,models.Schedule,schedule_id); return [data(x) for x in list_items(db,models.ScheduleExplanation,0,500,{"schedule_id":schedule_id})]
