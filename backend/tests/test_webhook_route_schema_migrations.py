from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from app.seed import _ensure_obsolete_webhook_route_columns_removed


def test_sqlite_obsolete_source_system_column_removed(monkeypatch: pytest.MonkeyPatch):
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
                    source_system VARCHAR(120) NOT NULL,
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
                    PRIMARY KEY (id)
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
                    source_system,
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
                    'Legacy route',
                    'legacy',
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

    _ensure_obsolete_webhook_route_columns_removed()

    with engine.begin() as connection:
        columns = {row[1] for row in connection.execute(text("PRAGMA table_info(webhook_routes)")).all()}
        assert "source_system" not in columns
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
                    'New route',
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
