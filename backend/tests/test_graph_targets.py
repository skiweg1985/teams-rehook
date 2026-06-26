from __future__ import annotations

from app.core.config import Settings
from app.services.graph_targets import _graph_credentials


def test_graph_credentials_fall_back_to_bot_credentials():
    settings = Settings(
        bot_tenant_id="bot-tenant",
        bot_client_id="bot-client",
        bot_client_secret="bot-secret",
    )

    assert _graph_credentials(settings) == ("bot-tenant", "bot-client", "bot-secret")


def test_graph_credentials_override_bot_credentials():
    settings = Settings(
        bot_tenant_id="bot-tenant",
        bot_client_id="bot-client",
        bot_client_secret="bot-secret",
        graph_tenant_id="graph-tenant",
        graph_client_id="graph-client",
        graph_client_secret="graph-secret",
    )

    assert _graph_credentials(settings) == ("graph-tenant", "graph-client", "graph-secret")
