from fastapi import Depends
from sqlalchemy.orm import Session
from ..database import get_db
from .. import models, schemas
from ..services.crud import list_items
from .factory import data,crud_router
router=crud_router(models.Project,schemas.ProjectCreate,"/projects")
@router.get("",name="list_projects")
def listing(skip:int=0,limit:int=100, status: str|None=None,db:Session=Depends(get_db)):
 return [data(x) for x in list_items(db,models.Project,skip,min(limit,500),{'status':status})]
