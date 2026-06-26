from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any


class WebhookPayloadError(ValueError):
    pass


@dataclass(frozen=True)
class NormalizedMessage:
    title: str
    text: str
    severity: str = "info"
    status: str = ""
    raw_type: str = "unknown"
    activity: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def truncate_text(value: str, limit: int = 2000) -> str:
    if len(value) <= limit:
        return value
    return f"{value[: limit - 3]}..."


def payload_preview(payload: bytes, limit: int = 2000) -> str:
    text = payload.decode("utf-8", errors="replace")
    return truncate_text(text, limit)


def normalize_webhook_payload(payload: bytes, content_type: str | None) -> NormalizedMessage:
    if not payload or not payload.strip():
        raise WebhookPayloadError("Webhook payload must not be empty")

    text = payload.decode("utf-8", errors="replace").strip()
    content_type_normalized = (content_type or "").lower()
    looks_like_json = text.startswith("{") or text.startswith("[")
    if "json" in content_type_normalized or looks_like_json:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise WebhookPayloadError("Webhook payload is not valid JSON") from exc
        return _normalize_json(parsed)

    return NormalizedMessage(
        title="Webhook message",
        text=truncate_text(text),
        raw_type="text",
    )


def _normalize_json(value: Any) -> NormalizedMessage:
    if isinstance(value, list):
        if not value:
            raise WebhookPayloadError("Webhook JSON array must not be empty")
        return NormalizedMessage(
            title="Webhook message",
            text=truncate_text(json.dumps(value, ensure_ascii=False, sort_keys=True)),
            raw_type="json_array",
        )
    if not isinstance(value, dict):
        raise WebhookPayloadError("Webhook JSON payload must be an object or array")
    if not value:
        raise WebhookPayloadError("Webhook JSON object must not be empty")
    if _is_bot_activity_with_attachments(value):
        title, text = _activity_summary(value)
        return NormalizedMessage(
            title=truncate_text(title or "Adaptive card message", 255),
            text=truncate_text(text or "Adaptive card payload", 4000),
            severity="info",
            raw_type="adaptive_card_activity",
            activity=value,
        )

    raw_type = str(value.get("@type") or value.get("type") or "json_object")
    title = _first_text(value, "title", "summary", "subject", "event", "name") or "Webhook message"
    status = _first_text(value, "status", "state") or ""
    severity = (_first_text(value, "severity", "level", "priority") or status or "info").lower()
    body_text = _first_text(value, "text", "message", "description", "details", "summary") or ""
    section_text = _message_card_sections(value.get("sections"))
    facts_text = _facts_text(value.get("facts"))
    fallback_text = "" if body_text or section_text or facts_text else json.dumps(value, ensure_ascii=False, sort_keys=True)
    parts = [part for part in [body_text, section_text, facts_text, fallback_text] if part]

    return NormalizedMessage(
        title=truncate_text(title, 255),
        text=truncate_text("\n\n".join(parts), 4000),
        severity=truncate_text(severity, 40),
        status=truncate_text(status, 40),
        raw_type=truncate_text(raw_type, 80),
    )


def _is_bot_activity_with_attachments(value: dict[str, Any]) -> bool:
    attachments = value.get("attachments")
    if value.get("type") != "message" or not isinstance(attachments, list):
        return False
    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        content_type = str(attachment.get("contentType") or "")
        if content_type == "application/vnd.microsoft.card.adaptive":
            return True
    return False


def _activity_summary(activity: dict[str, Any]) -> tuple[str, str]:
    text_blocks: list[str] = []
    facts: list[str] = []
    for attachment in activity.get("attachments") or []:
        if not isinstance(attachment, dict):
            continue
        content = attachment.get("content")
        if isinstance(content, dict):
            _collect_adaptive_card_text(content, text_blocks, facts)
    title = next((text for text in text_blocks if text.strip()), "")
    body = "\n".join([line for line in [*text_blocks[1:], *facts] if line.strip()])
    return title, body


def _collect_adaptive_card_text(value: Any, text_blocks: list[str], facts: list[str]) -> None:
    if isinstance(value, dict):
        if value.get("type") == "TextBlock":
            text = value.get("text")
            if isinstance(text, str) and text.strip():
                text_blocks.append(text.strip())
        if value.get("type") == "FactSet":
            fact_text = _adaptive_facts_text(value.get("facts"))
            if fact_text:
                facts.append(fact_text)
        for child in value.values():
            _collect_adaptive_card_text(child, text_blocks, facts)
    elif isinstance(value, list):
        for child in value:
            _collect_adaptive_card_text(child, text_blocks, facts)


def _adaptive_facts_text(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    lines: list[str] = []
    for fact in value:
        if not isinstance(fact, dict):
            continue
        title = fact.get("title")
        fact_value = fact.get("value")
        if title is None or fact_value is None:
            continue
        lines.append(f"{title}: {fact_value}")
    return "\n".join(lines)


def _first_text(value: dict[str, Any], *keys: str) -> str:
    for key in keys:
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
        if isinstance(candidate, (int, float, bool)):
            return str(candidate)
    return ""


def _message_card_sections(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    lines: list[str] = []
    for section in value:
        if not isinstance(section, dict):
            continue
        title = _first_text(section, "activityTitle", "title")
        subtitle = _first_text(section, "activitySubtitle", "subtitle")
        text = _first_text(section, "text")
        facts = _facts_text(section.get("facts"))
        section_parts = [part for part in [title, subtitle, text, facts] if part]
        if section_parts:
            lines.append("\n".join(section_parts))
    return "\n\n".join(lines)


def _facts_text(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    lines: list[str] = []
    for fact in value:
        if not isinstance(fact, dict):
            continue
        name = fact.get("name")
        fact_value = fact.get("value")
        if name is None or fact_value is None:
            continue
        lines.append(f"{name}: {fact_value}")
    return "\n".join(lines)
