from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database import get_db
from app.schemas import HealthOut

router = APIRouter(tags=["public"])


@router.get("/health", response_model=HealthOut)
def health():
    settings = get_settings()
    return HealthOut(service=settings.app_name, version=settings.app_version)


@router.get("/readyz", response_model=HealthOut)
def readyz(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    settings = get_settings()
    return HealthOut(service=settings.app_name, version=settings.app_version)
