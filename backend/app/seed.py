from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database import Base, engine
from app.models import DemoItem, Organization, User
from app.security import hash_secret


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    settings = get_settings()
    with Session(engine) as db:
        org = db.scalar(select(Organization).where(Organization.slug == settings.default_org_slug))
        if not org:
            org = Organization(slug=settings.default_org_slug, name=settings.default_org_name)
            db.add(org)
            db.flush()

        bootstrap_email = str(settings.bootstrap_admin_email or "").strip().lower()
        admin = db.scalar(select(User).where(User.organization_id == org.id, User.email == bootstrap_email))
        if not admin:
            admin = User(
                organization_id=org.id,
                email=bootstrap_email,
                display_name=settings.bootstrap_admin_display_name,
                password_hash=hash_secret(settings.bootstrap_admin_password),
                is_admin=True,
                is_active=True,
            )
            db.add(admin)
            db.flush()

        existing_demo = db.scalar(select(DemoItem).where(DemoItem.organization_id == org.id).limit(1))
        if not existing_demo:
            db.add_all(
                [
                    DemoItem(
                        organization_id=org.id,
                        owner_id=admin.id,
                        title="Wire the first workflow",
                        status="in_progress",
                        summary="Replace this demo record with the first real object in your app.",
                    ),
                    DemoItem(
                        organization_id=org.id,
                        owner_id=admin.id,
                        title="Review settings",
                        status="todo",
                        summary="Use the settings page as the starting point for app-level configuration.",
                    ),
                    DemoItem(
                        organization_id=org.id,
                        owner_id=admin.id,
                        title="Ship the dashboard",
                        status="done",
                        summary="The dashboard is intentionally data-light so teams can adapt it quickly.",
                    ),
                ]
            )
        db.commit()
