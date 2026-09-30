from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import HTTPException
def _validate_refs(db,model,data):
    for key,value in data.items():
        column=model.__table__.columns.get(key)
        if value is None or column is None: continue
        for fk in column.foreign_keys:
            target=fk.column.table
            if db.execute(select(target.c.id).where(target.c.id==value)).first() is None:
                raise HTTPException(404,f"Referenced {target.name} {value} not found")
def list_items(db:Session,model,skip=0,limit=100,filters=None):
    stmt=select(model)
    for key,value in (filters or {}).items():
        if value is not None and hasattr(model,key): stmt=stmt.where(getattr(model,key)==value)
    return list(db.scalars(stmt.offset(max(skip,0)).limit(max(1,min(limit,500)))).all())
def get_item(db,model,item_id):
    obj=db.get(model,item_id)
    if obj is None: raise HTTPException(404,f"{model.__name__} {item_id} not found")
    return obj
def create_item(db,model,data):
    _validate_refs(db,model,data); obj=model(**data); db.add(obj)
    try: db.commit()
    except Exception as exc: db.rollback(); raise HTTPException(409,"Could not create resource; check unique values and references") from exc
    db.refresh(obj); return obj
def update_item(db,model,item_id,data):
    obj=get_item(db,model,item_id); _validate_refs(db,model,data)
    for key,value in data.items(): setattr(obj,key,value)
    try: db.commit()
    except Exception as exc: db.rollback(); raise HTTPException(409,"Could not update resource; check unique values and references") from exc
    db.refresh(obj); return obj
def delete_item(db,model,item_id):
    obj=get_item(db,model,item_id); db.delete(obj); db.commit()
