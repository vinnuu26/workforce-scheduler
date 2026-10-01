from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import OptimizationRequest, ReschedulePreviewRequest, RescheduleApplyRequest, ConflictResolutionRequest
from ..schemas import AlternativeOptimizationRequest
from ..services.alternative_schedule_service import generate_alternative_schedules
from ..services.scheduling_service import (
    SchedulingDataError, generate_schedule_from_database, preview_reschedule_from_database,
    resolve_conflicts_from_database, apply_reschedule_from_database,
    preview_conflict_resolution_from_database, apply_conflict_resolution_from_database,
)

router = APIRouter(prefix="/optimization", tags=["optimization"])


@router.post("/generate")
def generate(payload: OptimizationRequest, db: Session = Depends(get_db)):
    try:
        return generate_schedule_from_database(
            db, payload.start_date, payload.end_date, payload.department_id, payload.project_id,
        )
    except SchedulingDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/resolve-conflict")
def resolve_conflict(payload: OptimizationRequest, db: Session = Depends(get_db)):
    try:
        return resolve_conflicts_from_database(
            db, payload.start_date, payload.end_date, payload.department_id, payload.project_id,
        )
    except SchedulingDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/reschedule-preview")
def reschedule_preview(payload: ReschedulePreviewRequest, db: Session = Depends(get_db)):
    try:
        return preview_reschedule_from_database(db, payload.schedule_id, payload.assignment_id)
    except SchedulingDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/apply-reschedule")
def apply_reschedule(payload: RescheduleApplyRequest, db: Session = Depends(get_db)):
    try:
        return apply_reschedule_from_database(db, payload.schedule_id, payload.assignment_id, payload.confirmed)
    except SchedulingDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/resolution-preview")
def resolution_preview(payload: ConflictResolutionRequest, db: Session = Depends(get_db)):
    try:
        return preview_conflict_resolution_from_database(db, payload.start_date, payload.end_date,
            payload.resolution_id, payload.department_id, payload.project_id)
    except SchedulingDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/apply-resolution")
def apply_resolution(payload: ConflictResolutionRequest, db: Session = Depends(get_db)):
    try:
        return apply_conflict_resolution_from_database(db, payload.start_date, payload.end_date,
            payload.resolution_id, payload.confirmed, payload.department_id, payload.project_id)
    except SchedulingDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/alternatives")
def alternatives(payload: AlternativeOptimizationRequest, db: Session = Depends(get_db)):
    try:
        return generate_alternative_schedules(
            db, payload.start_date, payload.end_date, payload.count,
            payload.department_id, payload.project_id,
        )
    except SchedulingDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
