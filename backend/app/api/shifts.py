from fastapi import Depends
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models, schemas
from ..services.crud import list_items
from .factory import data,crud_router
router=crud_router(models.Shift,schemas.ShiftCreate,"/shifts")
@router.get("",name="list_shifts")
def listing(skip:int=0,limit:int=100, date: str|None=None, department_id: int|None=None,db:Session=Depends(get_db)):
 return [data(x) for x in list_items(db,models.Shift,skip,min(limit,500),{'date':date, 'department_id':department_id})]
