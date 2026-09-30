from fastapi import Depends
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models, schemas
from ..services.crud import list_items
from .factory import data,crud_router
router=crud_router(models.EmployeePreference,schemas.PreferenceCreate,"/preferences")
@router.get("",name="list_preferences")
def listing(skip:int=0,limit:int=100, employee_id: int|None=None,db:Session=Depends(get_db)):
 return [data(x) for x in list_items(db,models.EmployeePreference,skip,min(limit,500),{'employee_id':employee_id})]
