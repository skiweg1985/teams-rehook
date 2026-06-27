from __future__ import annotations

import html
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.settings_overrides import get_effective_settings
from app.models import WebhookRoute
from app.services.graph_delegated_auth import GraphDelegatedAuthError, refresh_delegated_access_token
from app.services.webhook_payloads import NormalizedMessage


GRAPH_BACKEND = "graph"
GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"


class GraphDeliveryError(RuntimeError):
    def __init__(self, message: str, *, error_type: str = "graph_error", status_code: int | None = None, result: dict[str, Any] | None = None):
        super().__init__(message)
        self.error_type = error_type
        self.status_code = status_code
        self.result = result or {}


@dataclass(frozen=True)
class GraphDeliveryResult:
    mode: str
    status_code: int
    message_id: str
    target: dict[str, str]
    request: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": GRAPH_BACKEND,
            "mode": self.mode,
            "status_code": self.status_code,
            "message_id": self.message_id,
            "target": self.target,
            "request": self.request,
        }


def send_graph_message(
    db: Session,
    *,
    organization_id: str,
    route: WebhookRoute,
    message: NormalizedMessage,
    settings: Settings | None = None,
) -> GraphDeliveryResult:
    settings = settings or get_effective_settings()
    target = _target_for_route(route)
    payload = build_chat_message_payload(message)
    token = _delegated_token(db, organization_id=organization_id, settings=settings)

    endpoint = _endpoint_for_target(target)
    try:
        response = _graph_post_json(endpoint, token.access_token, payload)
    except GraphDeliveryError as exc:
        if not _should_retry_without_attachments(exc, payload):
            exc.result = _error_result(exc, target)
            raise
        fallback_payload = build_chat_message_payload(message, include_attachments=False)
        try:
            response = _graph_post_json(endpoint, token.access_token, fallback_payload)
        except GraphDeliveryError as retry_exc:
            retry_exc.result = _error_result(retry_exc, target)
            raise
        payload = fallback_payload

    return GraphDeliveryResult(
        mode="real",
        status_code=response["status_code"],
        message_id=response["body"].get("id", "") if isinstance(response["body"], dict) else "",
        target=target,
        request=_safe_request_summary(payload),
    )


def build_chat_message_payload(message: NormalizedMessage, *, include_attachments: bool = True) -> dict[str, Any]:
    html_body = _message_html(message)
    payload: dict[str, Any] = {
        "body": {
            "contentType": "html",
            "content": html_body,
        }
    }
    attachments = _adaptive_card_attachments(message) if include_attachments else []
    if attachments:
        payload["attachments"] = attachments
    return payload


def _delegated_token(db: Session, *, organization_id: str, settings: Settings):
    try:
        return refresh_delegated_access_token(db, organization_id=organization_id, settings=settings)
    except GraphDelegatedAuthError as exc:
        raise GraphDeliveryError(
            "Delegated Graph delivery is not ready. Reconnect the service user in Settings.",
            error_type="auth_error",
        ) from exc


def _target_for_route(route: WebhookRoute) -> dict[str, str]:
    kind = (route.graph_target_kind or "").strip()
    if kind == "channel":
        team_id = route.graph_team_id.strip()
        channel_id = route.graph_channel_id.strip()
        if not team_id or not channel_id:
            raise GraphDeliveryError(
                "Graph channel delivery requires a team ID and channel ID.",
                error_type="validation_error",
            )
        return {
            "kind": "channel",
            "team_id": team_id,
            "team_name": route.graph_team_name.strip(),
            "channel_id": channel_id,
            "target_name": route.target_name.strip(),
        }
    if kind == "chat":
        chat_id = route.graph_target_id.strip()
        if not chat_id:
            raise GraphDeliveryError(
                "Graph chat delivery requires an existing chat ID.",
                error_type="validation_error",
            )
        return {
            "kind": "chat",
            "chat_id": chat_id,
            "target_name": route.target_name.strip(),
        }
    if kind == "user":
        raise GraphDeliveryError(
            "Graph user and 1:1 delivery is not supported in V1. Select an existing chat or channel.",
            error_type="unsupported_target",
        )
    raise GraphDeliveryError(
        "Graph delivery supports channel and existing chat targets in V1.",
        error_type="unsupported_target",
    )


def _endpoint_for_target(target: dict[str, str]) -> str:
    if target["kind"] == "channel":
        team_id = urllib.parse.quote(target["team_id"], safe="")
        channel_id = urllib.parse.quote(target["channel_id"], safe="")
        return f"/teams/{team_id}/channels/{channel_id}/messages"
    chat_id = urllib.parse.quote(target["chat_id"], safe="")
    return f"/chats/{chat_id}/messages"


def _graph_post_json(path: str, access_token: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{GRAPH_BASE_URL}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            response_body = response.read().decode("utf-8")
            body = json.loads(response_body) if response_body else {}
            return {"status_code": response.status, "body": body if isinstance(body, dict) else {}}
    except urllib.error.HTTPError as exc:
        safe_message = _safe_graph_error_message(exc)
        raise GraphDeliveryError(
            f"Microsoft Graph delivery failed with HTTP {exc.code}: {safe_message}",
            error_type="graph_http_error",
            status_code=exc.code,
        ) from exc
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise GraphDeliveryError("Microsoft Graph delivery failed.", error_type="graph_request_error") from exc


def _message_html(message: NormalizedMessage) -> str:
    lines: list[str] = []
    if message.title:
        lines.append(f"<strong>{html.escape(message.title)}</strong>")
    if message.text:
        lines.append(_plain_text_to_html(message.text))
    if message.status:
        lines.append(f"<strong>Status:</strong> {html.escape(message.status)}")
    if message.severity and message.severity != "info":
        lines.append(f"<strong>Severity:</strong> {html.escape(message.severity)}")
    return "<br><br>".join(lines) or "<strong>Webhook message</strong>"


def _plain_text_to_html(value: str) -> str:
    return "<br>".join(html.escape(line) for line in value.splitlines())


def _adaptive_card_attachments(message: NormalizedMessage) -> list[dict[str, str | None]]:
    if not message.activity:
        return []
    attachments: list[dict[str, str | None]] = []
    for index, attachment in enumerate(message.activity.get("attachments") or [], start=1):
        if not isinstance(attachment, dict):
            continue
        if attachment.get("contentType") != "application/vnd.microsoft.card.adaptive":
            continue
        content = attachment.get("content")
        if not isinstance(content, dict):
            continue
        attachments.append(
            {
                "id": str(index),
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": json.dumps(content, ensure_ascii=False),
                "name": "Adaptive Card",
            }
        )
    return attachments


def _should_retry_without_attachments(exc: GraphDeliveryError, payload: dict[str, Any]) -> bool:
    return exc.status_code == 400 and bool(payload.get("attachments"))


def _safe_graph_error_message(exc: urllib.error.HTTPError) -> str:
    try:
        body = json.loads(exc.read().decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return "The Graph response could not be parsed."
    if not isinstance(body, dict):
        return "Microsoft Graph returned an error."
    error = body.get("error")
    if isinstance(error, dict):
        message = str(error.get("message") or "Microsoft Graph returned an error.").strip()
        code = str(error.get("code") or "").strip()
        return f"{code}: {message}" if code else message
    return "Microsoft Graph returned an error."


def _error_result(exc: GraphDeliveryError, target: dict[str, str]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "backend": GRAPH_BACKEND,
        "target": target,
        "error_type": exc.error_type,
    }
    if exc.status_code is not None:
        result["status_code"] = exc.status_code
    return result


def _safe_request_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "content_type": payload.get("body", {}).get("contentType", ""),
        "has_attachments": bool(payload.get("attachments")),
        "attachment_count": len(payload.get("attachments") or []),
    }
