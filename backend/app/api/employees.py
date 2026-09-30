from fastapi import Depends
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models, schemas
from ..services.crud import list_items
from .factory import data,crud_router
router=crud_router(models.Employee,schemas.EmployeeCreate,"/employees")
@router.get("",name="list_employees")
def listing(skip:int=0,limit:int=100, department_id: int|None=None, active: bool|None=None,db:Session=Depends(get_db)):
 return [data(x) for x in list_items(db,models.Employee,skip,min(limit,500),{'department_id':department_id, 'active':active})]
