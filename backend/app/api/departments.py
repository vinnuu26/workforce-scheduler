from fastapi import Depends
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models, schemas
from ..services.crud import list_items
from .factory import data,crud_router
router=crud_router(models.Department,schemas.DepartmentCreate,"/departments")
@router.get("",name="list_departments")
def listing(skip:int=0,limit:int=100,db:Session=Depends(get_db)):
 return [data(x) for x in list_items(db,models.Department,skip,min(limit,500),{})]
