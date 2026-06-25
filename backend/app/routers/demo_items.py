from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, record_audit, require_csrf
from app.models import DemoItem, User
from app.schemas import DemoItemCreate, DemoItemOut, DemoItemUpdate

router = APIRouter(prefix="/demo-items", tags=["demo-items"])


@router.get("", response_model=list[DemoItemOut])
def list_demo_items(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(
        select(DemoItem)
        .where(DemoItem.organization_id == current_user.organization_id)
        .order_by(DemoItem.updated_at.desc())
    ).all()


@router.post("", response_model=DemoItemOut, dependencies=[Depends(require_csrf)])
def create_demo_item(
    payload: DemoItemCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = DemoItem(
        organization_id=current_user.organization_id,
        owner_id=current_user.id,
        title=payload.title.strip(),
        status=payload.status,
        summary=payload.summary.strip(),
    )
    db.add(item)
    db.flush()
    record_audit(
        db,
        action="demo_item.created",
        actor_type="user",
        actor_id=current_user.id,
        organization_id=current_user.organization_id,
        metadata={"demo_item_id": item.id, "title": item.title},
    )
    db.commit()
    db.refresh(item)
    return item


@router.patch("/{item_id}", response_model=DemoItemOut, dependencies=[Depends(require_csrf)])
def update_demo_item(
    item_id: str,
    payload: DemoItemUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = db.scalar(
        select(DemoItem).where(
            DemoItem.id == item_id,
            DemoItem.organization_id == current_user.organization_id,
        )
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Demo item not found")
    if payload.title is not None:
        item.title = payload.title.strip()
    if payload.status is not None:
        item.status = payload.status
    if payload.summary is not None:
        item.summary = payload.summary.strip()
    record_audit(
        db,
        action="demo_item.updated",
        actor_type="user",
        actor_id=current_user.id,
        organization_id=current_user.organization_id,
        metadata={"demo_item_id": item.id},
    )
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_csrf)])
def delete_demo_item(
    item_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = db.scalar(
        select(DemoItem).where(
            DemoItem.id == item_id,
            DemoItem.organization_id == current_user.organization_id,
        )
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Demo item not found")
    record_audit(
        db,
        action="demo_item.deleted",
        actor_type="user",
        actor_id=current_user.id,
        organization_id=current_user.organization_id,
        metadata={"demo_item_id": item.id, "title": item.title},
    )
    db.delete(item)
    db.commit()
    return None
