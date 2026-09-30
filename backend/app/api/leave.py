from fastapi import Depends
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models, schemas
from ..services.crud import list_items
from .factory import data,crud_router
router=crud_router(models.Leave,schemas.LeaveCreate,"/leave")
@router.get("",name="list_leave")
def listing(skip:int=0,limit:int=100, employee_id: int|None=None,db:Session=Depends(get_db)):
 return [data(x) for x in list_items(db,models.Leave,skip,min(limit,500),{'employee_id':employee_id})]
