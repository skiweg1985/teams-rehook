from __future__ import annotations

import pytest

from app.services.webhook_payloads import WebhookPayloadError, normalize_webhook_payload


def test_normalizes_plain_text_payload():
    message = normalize_webhook_payload(b"Firewall link down", "text/plain")

    assert message.title == "Webhook message"
    assert message.text == "Firewall link down"
    assert message.raw_type == "text"


def test_normalizes_simple_json_payload():
    message = normalize_webhook_payload(
        b'{"title":"PRTG alert","text":"Sensor failed","severity":"warning","status":"down"}',
        "application/json",
    )

    assert message.title == "PRTG alert"
    assert message.text == "Sensor failed"
    assert message.severity == "warning"
    assert message.status == "down"


def test_normalizes_message_card_sections_and_facts():
    message = normalize_webhook_payload(
        b"""
        {
          "@type": "MessageCard",
          "summary": "macmon event",
          "sections": [
            {
              "activityTitle": "Device changed",
              "facts": [{"name": "Host", "value": "switch-01"}]
            }
          ]
        }
        """,
        "application/json",
    )

    assert message.title == "macmon event"
    assert "Device changed" in message.text
    assert "Host: switch-01" in message.text
    assert message.raw_type == "MessageCard"


def test_rejects_empty_payload():
    with pytest.raises(WebhookPayloadError):
        normalize_webhook_payload(b"   ", "text/plain")


def test_preserves_adaptive_card_activity():
    message = normalize_webhook_payload(
        b"""
        {
          "type": "message",
          "attachments": [
            {
              "contentType": "application/vnd.microsoft.card.adaptive",
              "content": {
                "type": "AdaptiveCard",
                "body": [
                  {"type": "TextBlock", "text": "%device: %shortname"},
                  {"type": "TextBlock", "text": "%message"},
                  {
                    "type": "FactSet",
                    "facts": [{"title": "Status", "value": "%status"}]
                  }
                ]
              }
            }
          ]
        }
        """,
        "application/json",
    )

    assert message.raw_type == "adaptive_card_activity"
    assert message.title == "%device: %shortname"
    assert "%message" in message.text
    assert "Status: %status" in message.text
    assert message.activity is not None
    assert message.activity["attachments"][0]["contentType"] == "application/vnd.microsoft.card.adaptive"
