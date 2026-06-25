from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_admin, require_csrf
from app.models import AuditEvent, User
from app.schemas import AuditEventOut, UserOut
from app.security import loads_json

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=list[UserOut], dependencies=[Depends(require_csrf)])
def list_users(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return db.scalars(
        select(User)
        .where(User.organization_id == admin.organization_id)
        .order_by(User.created_at.desc())
    ).all()


@router.get("/logs", response_model=list[AuditEventOut], dependencies=[Depends(require_csrf)])
def list_logs(
    limit: int = Query(default=100, ge=1, le=250),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.organization_id == admin.organization_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
    ).all()
    return [
        AuditEventOut(
            id=row.id,
            actor_type=row.actor_type,
            actor_id=row.actor_id,
            action=row.action,
            metadata=loads_json(row.metadata_json, {}),
            created_at=row.created_at,
        )
        for row in rows
    ]
