from contextlib import asynccontextmanager
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import Base, engine
from sqlalchemy import inspect, text
from . import models  # register models
from .api import departments, skills, employees, shifts, shift_templates, availability, leave, preferences, projects, schedules, relations, optimization

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    migrations = (
        ("employee_skills", "proficiency", "ALTER TABLE employee_skills ADD COLUMN proficiency INTEGER NOT NULL DEFAULT 1"),
        ("schedules", "scope_department_id", "ALTER TABLE schedules ADD COLUMN scope_department_id INTEGER"),
        ("schedules", "scope_project_id", "ALTER TABLE schedules ADD COLUMN scope_project_id INTEGER"),
    )
    for table, column, statement in migrations:
        if inspect(engine).has_table(table) and column not in {item["name"] for item in inspect(engine).get_columns(table)}:
            with engine.begin() as connection:
                connection.execute(text(statement))
    yield

app=FastAPI(title="Workforce Scheduler API",version="1.0.0",lifespan=lifespan)
cors_origins = [origin.strip() for origin in os.getenv(
    "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173",
).split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)
@app.get("/")
def root(): return {"message":"Workforce Scheduler API"}
@app.get("/health")
def health(): return {"status":"ok"}
for module in (departments,skills,employees,shifts,shift_templates,availability,leave,preferences,projects,schedules): app.include_router(module.router,prefix="/api")
app.include_router(relations.router,prefix="/api")
app.include_router(optimization.router,prefix="/api")
