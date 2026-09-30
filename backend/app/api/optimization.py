from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import OptimizationRequest
from ..services.scheduling_service import SchedulingDataError, generate_schedule_from_database

router = APIRouter(prefix="/optimization", tags=["optimization"])


@router.post("/generate")
def generate(payload: OptimizationRequest, db: Session = Depends(get_db)):
    try:
        return generate_schedule_from_database(
            db, payload.start_date, payload.end_date, payload.department_id, payload.project_id,
        )
    except SchedulingDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
