from __future__ import annotations

from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database import Base, engine
from app.models import DemoItem, Organization, User
from app.security import hash_secret


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_additive_schema()
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


def _ensure_additive_schema() -> None:
    with engine.begin() as connection:
        dialect = engine.dialect.name
        if dialect == "sqlite":
            columns = {row[1] for row in connection.execute(text("PRAGMA table_info(webhook_routes)")).all()}
            if "route_token" not in columns:
                connection.execute(text("ALTER TABLE webhook_routes ADD COLUMN route_token TEXT DEFAULT '' NOT NULL"))
            return

        exists = connection.execute(
            text(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'webhook_routes'
                  AND column_name = 'route_token'
                """
            )
        ).first()
        if not exists:
            connection.execute(text("ALTER TABLE webhook_routes ADD COLUMN route_token TEXT DEFAULT '' NOT NULL"))
