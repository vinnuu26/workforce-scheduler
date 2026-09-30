from contextlib import asynccontextmanager
from fastapi import FastAPI
from .database import Base, engine
from . import models  # register models
from .api import departments, skills, employees, shifts, shift_templates, availability, leave, preferences, projects, schedules, relations

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield

app=FastAPI(title="Workforce Scheduler API",version="1.0.0",lifespan=lifespan)
@app.get("/")
def root(): return {"message":"Workforce Scheduler API"}
@app.get("/health")
def health(): return {"status":"ok"}
for module in (departments,skills,employees,shifts,shift_templates,availability,leave,preferences,projects,schedules): app.include_router(module.router,prefix="/api")
app.include_router(relations.router,prefix="/api")
