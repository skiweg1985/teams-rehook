from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import AppSetting, Organization, User
from app.security import hash_secret
from app.seed import INSTANCE_SESSION_SECRET_KEY, INSTANCE_SETTINGS_ENC_KEY, init_db
from app.seed import _ensure_additive_schema, _ensure_webhook_route_name_backend_uniqueness


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


def test_init_db_creates_default_org_and_instance_secret_without_bootstrap_admin(monkeypatch: pytest.MonkeyPatch):
    from app.core.config import get_settings

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    monkeypatch.setattr("app.seed.engine", engine)
    monkeypatch.setenv("SESSION_SECRET", "")
    monkeypatch.setenv("SETTINGS_ENC_KEY", "")
    get_settings.cache_clear()
    try:
        init_db()
        with Session(engine) as db:
            org = db.scalar(select(Organization).where(Organization.slug == "default"))
            users = db.scalars(select(User)).all()
            instance_secret = db.get(AppSetting, INSTANCE_SESSION_SECRET_KEY)
            settings_enc_key = db.get(AppSetting, INSTANCE_SETTINGS_ENC_KEY)
            assert org is not None
            assert users == []
            assert instance_secret is not None
            assert len(instance_secret.value) >= 40
            assert get_settings().session_secret == instance_secret.value
            assert settings_enc_key is not None
            assert len(settings_enc_key.value) >= 40
            assert get_settings().settings_enc_key == settings_enc_key.value
            assert get_settings().settings_enc_key_source == "generated"
    finally:
        get_settings.cache_clear()


def test_additive_schema_backfills_bot_activity_auth_metadata_columns(monkeypatch: pytest.MonkeyPatch):
    engine = create_engine("sqlite://", future=True)
    monkeypatch.setattr("app.seed.engine", engine)
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE bot_activity_events"))
        connection.execute(
            text(
                """
                CREATE TABLE bot_activity_events (
                    id VARCHAR(36) NOT NULL,
                    activity_type VARCHAR(80) NOT NULL,
                    service_url TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    team_id TEXT NOT NULL,
                    graph_team_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    conversation_type VARCHAR(40) NOT NULL,
                    team_name VARCHAR(200) NOT NULL,
                    channel_name VARCHAR(200) NOT NULL,
                    from_id TEXT NOT NULL,
                    user_name VARCHAR(200) NOT NULL,
                    graph_user_id TEXT NOT NULL,
                    recipient_id TEXT NOT NULL,
                    raw_activity_json TEXT NOT NULL,
                    created_at DATETIME NOT NULL,
                    PRIMARY KEY (id)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO bot_activity_events (
                    id,
                    activity_type,
                    service_url,
                    conversation_id,
                    tenant_id,
                    team_id,
                    graph_team_id,
                    channel_id,
                    conversation_type,
                    team_name,
                    channel_name,
                    from_id,
                    user_name,
                    graph_user_id,
                    recipient_id,
                    raw_activity_json,
                    created_at
                )
                VALUES (
                    'event-1',
                    'message',
                    'https://smba.trafficmanager.net/emea/',
                    'conversation-id',
                    'tenant-id',
                    'team-id',
                    '',
                    'channel-id',
                    'channel',
                    'Team',
                    'Alerts',
                    'user-id',
                    'Ada',
                    'aad-user-id',
                    'bot-id',
                    '{}',
                    CURRENT_TIMESTAMP
                )
                """
            )
        )

    _ensure_additive_schema()

    with engine.connect() as connection:
        columns = {row[1] for row in connection.execute(text("PRAGMA table_info(bot_activity_events)")).all()}
        assert {
            "auth_status",
            "auth_issuer",
            "auth_audience",
            "auth_service_url",
            "auth_service_url_matched",
            "auth_validated_at",
        } <= columns
        row = connection.execute(
            text(
                """
                SELECT auth_status, auth_issuer, auth_audience, auth_service_url,
                       auth_service_url_matched, auth_validated_at
                FROM bot_activity_events
                WHERE id = 'event-1'
                """
            )
        ).one()
        assert row[0] == "unknown"
        assert row[1] == ""
        assert row[2] == ""
        assert row[3] == ""
        assert row[4] == 0
        assert row[5] is None


def test_init_db_rejects_placeholder_session_secret(monkeypatch: pytest.MonkeyPatch):
    from app.core.config import get_settings

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    monkeypatch.setattr("app.seed.engine", engine)
    monkeypatch.setenv("SESSION_SECRET", "change-me-session-secret")
    monkeypatch.setenv("SETTINGS_ENC_KEY", "test-settings-encryption-key")
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="SESSION_SECRET"):
            init_db()
    finally:
        get_settings.cache_clear()


def test_init_db_rejects_placeholder_settings_enc_key(monkeypatch: pytest.MonkeyPatch):
    from app.core.config import get_settings

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    monkeypatch.setattr("app.seed.engine", engine)
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("SETTINGS_ENC_KEY", "change-me-settings-enc-key")
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="SETTINGS_ENC_KEY"):
            init_db()
    finally:
        get_settings.cache_clear()


def test_init_db_creates_webhook_url_reveal_token_table(monkeypatch: pytest.MonkeyPatch):
    from app.core.config import get_settings

    engine = create_engine("sqlite://", future=True)
    monkeypatch.setattr("app.seed.engine", engine)
    monkeypatch.setenv("SESSION_SECRET", "")
    monkeypatch.setenv("SETTINGS_ENC_KEY", "")
    get_settings.cache_clear()
    try:
        init_db()
        with engine.connect() as connection:
            tables = {
                row[0]
                for row in connection.execute(text("SELECT name FROM sqlite_master WHERE type = 'table'")).all()
            }
            assert "webhook_url_reveal_tokens" in tables
            columns = {
                row[1]
                for row in connection.execute(text("PRAGMA table_info(webhook_url_reveal_tokens)")).all()
            }
            assert {"organization_id", "route_id", "token_hash", "expires_at", "created_at"} <= columns
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
    monkeypatch.setenv("SESSION_SECRET", "")
    monkeypatch.setenv("SETTINGS_ENC_KEY", "")
    get_settings.cache_clear()
    try:
        init_db()
        with Session(engine) as db:
            users = db.scalars(select(User)).all()
            assert [user.email for user in users] == ["existing@example.com"]
    finally:
        get_settings.cache_clear()
