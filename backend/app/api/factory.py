from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..database import get_db
from ..services.crud import get_item,create_item,update_item,delete_item
def data(obj):
    result={c.name:getattr(obj,c.name) for c in obj.__table__.columns}
    for rel in obj.__mapper__.relationships:
        value=getattr(obj,rel.key)
        result[rel.key]=[data(x) for x in value] if rel.uselist else (data(value) if value is not None else None)
    return result
def crud_router(model, create_schema, path):
    router=APIRouter(prefix=path,tags=[path.strip('/')])
    @router.get("/{item_id}")
    def get_one(item_id:int,db:Session=Depends(get_db)): return data(get_item(db,model,item_id))
    @router.post("",status_code=201)
    def create(payload:create_schema,db:Session=Depends(get_db)): return data(create_item(db,model,payload.model_dump(exclude_unset=True)))
    @router.put("/{item_id}")
    def update(item_id:int,payload:create_schema,db:Session=Depends(get_db)): return data(update_item(db,model,item_id,payload.model_dump(exclude_unset=True)))
    @router.delete("/{item_id}",status_code=204)
    def delete(item_id:int,db:Session=Depends(get_db)): delete_item(db,model,item_id)
    return router
