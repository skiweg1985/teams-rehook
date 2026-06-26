from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.config import Settings
from app.services.teams_bot import BotTokenManager, build_activity, send_bot_activity
from app.services.webhook_payloads import NormalizedMessage


def test_token_manager_reuses_valid_token():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    calls = 0

    def fetcher(settings: Settings):
        nonlocal calls
        calls += 1
        return f"token-{calls}", 3600

    manager = BotTokenManager(Settings(), fetcher=fetcher, now=lambda: now)

    assert manager.get_token() == "token-1"
    assert manager.get_token() == "token-1"
    assert calls == 1


def test_token_manager_refreshes_expiring_token():
    current = datetime(2026, 1, 1, tzinfo=timezone.utc)
    calls = 0

    def fetcher(settings: Settings):
        nonlocal calls
        calls += 1
        return f"token-{calls}", 120

    manager = BotTokenManager(Settings(), fetcher=fetcher, now=lambda: current, refresh_window_seconds=60)

    assert manager.get_token() == "token-1"
    current = current + timedelta(seconds=90)
    assert manager.get_token() == "token-2"
    assert calls == 2


def test_mock_delivery_does_not_require_credentials():
    settings = Settings(bot_delivery_mode="mock")
    message = NormalizedMessage(title="Test", text="Hello", severity="info", source="relay")

    result = send_bot_activity(
        service_url="https://smba.trafficmanager.net/emea/example",
        conversation_id="conversation-id",
        message=message,
        settings=settings,
    )

    assert result.mode == "mock"
    assert result.status_code == 202
    assert result.activity["type"] == "message"


def test_activity_contains_title_and_text_without_metadata_footer():
    message = NormalizedMessage(title="Alert", text="Sensor down", severity="critical", status="down", source="PRTG")

    activity = build_activity(message)

    assert activity["type"] == "message"
    assert "Alert" in activity["text"]
    assert "Sensor down" in activity["text"]
    assert "severity: critical" not in activity["text"]
    assert "status: down" not in activity["text"]
    assert "source: PRTG" not in activity["text"]


def test_build_activity_preserves_existing_adaptive_card_activity():
    card_activity = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {"type": "AdaptiveCard", "body": [{"type": "TextBlock", "text": "Hello"}]},
            }
        ],
    }
    message = NormalizedMessage(title="Card", text="Card payload", activity=card_activity)

    activity = build_activity(message)

    assert activity["attachments"] == card_activity["attachments"]
    assert "text" not in activity
