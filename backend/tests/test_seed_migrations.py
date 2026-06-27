from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Organization, User
from app.security import hash_secret, verify_secret
from app.seed import DEFAULT_BOOTSTRAP_ADMIN_EMAIL, DEFAULT_BOOTSTRAP_ADMIN_PASSWORD, init_db
from app.seed import _ensure_webhook_route_name_backend_uniqueness


def test_sqlite_route_name_migration_replaces_old_name_unique_constraint(monkeypatch: pytest.MonkeyPatch):
    engine = create_engine("sqlite://", future=True)
    monkeypatch.setattr("app.seed.engine", engine)

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE webhook_routes (
                    id VARCHAR(36) NOT NULL,
                    organization_id VARCHAR NOT NULL,
                    created_by_id VARCHAR,
                    name VARCHAR(200) NOT NULL,
                    is_active BOOLEAN NOT NULL,
                    route_token_hash VARCHAR(64) NOT NULL,
                    route_token TEXT NOT NULL,
                    delivery_backend VARCHAR(32) NOT NULL,
                    target_type VARCHAR(32) NOT NULL,
                    target_name VARCHAR(200) NOT NULL,
                    bot_service_url TEXT NOT NULL,
                    bot_conversation_id TEXT NOT NULL,
                    graph_target_kind VARCHAR(32) NOT NULL,
                    graph_target_id TEXT NOT NULL,
                    graph_team_id TEXT NOT NULL,
                    graph_team_name VARCHAR(200) NOT NULL,
                    graph_channel_id TEXT NOT NULL,
                    graph_user_id TEXT NOT NULL,
                    graph_user_display_name VARCHAR(255) NOT NULL,
                    graph_user_principal_name VARCHAR(255) NOT NULL,
                    bot_target_source VARCHAR(40) NOT NULL,
                    bot_registered_by_id TEXT NOT NULL,
                    bot_registered_at DATETIME,
                    last_delivery_status VARCHAR(32),
                    last_delivery_at DATETIME,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    PRIMARY KEY (id),
                    CONSTRAINT uq_webhook_routes_org_name UNIQUE (organization_id, name)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO webhook_routes (
                    id,
                    organization_id,
                    name,
                    is_active,
                    route_token_hash,
                    route_token,
                    delivery_backend,
                    target_type,
                    target_name,
                    bot_service_url,
                    bot_conversation_id,
                    graph_target_kind,
                    graph_target_id,
                    graph_team_id,
                    graph_team_name,
                    graph_channel_id,
                    graph_user_id,
                    graph_user_display_name,
                    graph_user_principal_name,
                    bot_target_source,
                    bot_registered_by_id,
                    created_at,
                    updated_at
                )
                VALUES (
                    'route-1',
                    'org-1',
                    'Shared alerts',
                    1,
                    'hash-1',
                    'plain-token',
                    'bot_framework',
                    'bot_conversation',
                    'Ops',
                    'https://smba.example',
                    'conversation-id',
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    '2026-01-01 00:00:00',
                    '2026-01-01 00:00:00'
                )
                """
            )
        )

    _ensure_webhook_route_name_backend_uniqueness()

    with engine.begin() as connection:
        old_unique_indexes = [
            row[1]
            for row in connection.execute(text("PRAGMA index_list(webhook_routes)")).all()
            if bool(row[2])
            and [
                column_row[2]
                for column_row in connection.execute(text(f"PRAGMA index_info('{row[1]}')")).all()
            ]
            == ["organization_id", "name"]
        ]
        assert old_unique_indexes == []

        connection.execute(
            text(
                """
                INSERT INTO webhook_routes (
                    id,
                    organization_id,
                    name,
                    is_active,
                    route_token_hash,
                    route_token,
                    delivery_backend,
                    target_type,
                    target_name,
                    bot_service_url,
                    bot_conversation_id,
                    graph_target_kind,
                    graph_target_id,
                    graph_team_id,
                    graph_team_name,
                    graph_channel_id,
                    graph_user_id,
                    graph_user_display_name,
                    graph_user_principal_name,
                    bot_target_source,
                    bot_registered_by_id,
                    created_at,
                    updated_at
                )
                VALUES (
                    'route-2',
                    'org-1',
                    'Shared alerts',
                    1,
                    'hash-2',
                    'plain-token-2',
                    'graph',
                    'bot_conversation',
                    'Ops',
                    '',
                    '',
                    'chat',
                    'chat-id',
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    '2026-01-01 00:00:00',
                    '2026-01-01 00:00:00'
                )
                """
            )
        )

        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    """
                    INSERT INTO webhook_routes (
                        id,
                        organization_id,
                        name,
                        is_active,
                        route_token_hash,
                        route_token,
                        delivery_backend,
                        target_type,
                        target_name,
                        bot_service_url,
                        bot_conversation_id,
                        graph_target_kind,
                        graph_target_id,
                        graph_team_id,
                        graph_team_name,
                        graph_channel_id,
                        graph_user_id,
                        graph_user_display_name,
                        graph_user_principal_name,
                        bot_target_source,
                        bot_registered_by_id,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        'route-3',
                        'org-1',
                        'Shared alerts',
                        1,
                        'hash-3',
                        'plain-token-3',
                        'graph',
                        'bot_conversation',
                        'Ops',
                        '',
                        '',
                        'chat',
                        'chat-id-2',
                        '',
                        '',
                        '',
                        '',
                        '',
                        '',
                        '',
                        '',
                        '2026-01-01 00:00:00',
                        '2026-01-01 00:00:00'
                    )
                    """
                )
            )


def test_init_db_bootstraps_default_admin_for_empty_org(monkeypatch: pytest.MonkeyPatch):
    from app.core.config import get_settings

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    monkeypatch.setattr("app.seed.engine", engine)
    get_settings.cache_clear()
    try:
        init_db()
        with Session(engine) as db:
            user = db.scalar(select(User).where(User.email == DEFAULT_BOOTSTRAP_ADMIN_EMAIL))
            assert user is not None
            assert user.is_admin is True
            assert user.is_active is True
            assert verify_secret(DEFAULT_BOOTSTRAP_ADMIN_PASSWORD, user.password_hash)
    finally:
        get_settings.cache_clear()


def test_init_db_does_not_bootstrap_default_admin_when_org_has_user(monkeypatch: pytest.MonkeyPatch):
    from app.core.config import get_settings

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    with Session(engine) as db:
        org = Organization(slug="default", name="Default")
        db.add(org)
        db.flush()
        db.add(
            User(
                organization_id=org.id,
                email="existing@example.com",
                display_name="Existing",
                password_hash=hash_secret("existing-password"),
                is_admin=True,
                is_active=True,
            )
        )
        db.commit()

    monkeypatch.setattr("app.seed.engine", engine)
    get_settings.cache_clear()
    try:
        init_db()
        with Session(engine) as db:
            users = db.scalars(select(User)).all()
            assert [user.email for user in users] == ["existing@example.com"]
    finally:
        get_settings.cache_clear()
