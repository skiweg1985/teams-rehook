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
from app.services.event_log import emit_event
from app.services.webhook_payloads import NormalizedMessage


GRAPH_BACKEND = "graph"
GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"


class GraphDeliveryError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        error_type: str = "graph_error",
        status_code: int | None = None,
        graph_error_code: str = "",
        graph_error_message: str = "",
        result: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.error_type = error_type
        self.status_code = status_code
        self.graph_error_code = graph_error_code
        self.graph_error_message = graph_error_message
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
            _apply_operator_guidance(exc, target, token.diagnostics)
            exc.result = _error_result(exc, target)
            _emit_graph_delivery_error(db, route=route, target=target, exc=exc)
            raise
        fallback_payload = build_chat_message_payload(message, include_attachments=False)
        try:
            response = _graph_post_json(endpoint, token.access_token, fallback_payload)
        except GraphDeliveryError as retry_exc:
            _apply_operator_guidance(retry_exc, target, token.diagnostics)
            retry_exc.result = _error_result(retry_exc, target)
            _emit_graph_delivery_error(db, route=route, target=target, exc=retry_exc)
            raise
        payload = fallback_payload

    emit_event(
        db,
        level="info",
        category="integration",
        event_type="graph.delivery.sent",
        message=f"Microsoft Graph delivery completed with HTTP {response['status_code']}.",
        target={
            "type": target.get("kind", "message"),
            "id": target.get("channel_id") or target.get("chat_id") or "",
            "route_id": getattr(route, "id", "") or "",
        },
        http={"method": "POST", "path": endpoint, "status_code": response["status_code"]},
        raw={"message_id": response["body"].get("id", "") if isinstance(response["body"], dict) else ""},
        domain="integration",
    )
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
        emit_event(
            db,
            level="error",
            category="integration",
            event_type="graph.delivery.auth_error",
            message="Delegated Graph delivery token refresh failed.",
            target={"type": "app", "organization_id": organization_id},
            security={"severity": "high", "reason": "graph_delegated_auth_error"},
            raw={"exception_type": exc.__class__.__name__, "exception": str(exc)},
            domain="integration",
        )
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
        graph_error_code, safe_message = _safe_graph_error_details(exc)
        raise GraphDeliveryError(
            f"Microsoft Graph delivery failed with HTTP {exc.code}: {safe_message}",
            error_type="graph_http_error",
            status_code=exc.code,
            graph_error_code=graph_error_code,
            graph_error_message=safe_message,
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


def _safe_graph_error_details(exc: urllib.error.HTTPError) -> tuple[str, str]:
    try:
        body = json.loads(exc.read().decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return "", "The Graph response could not be parsed."
    if not isinstance(body, dict):
        return "", "Microsoft Graph returned an error."
    error = body.get("error")
    if isinstance(error, dict):
        message = str(error.get("message") or "Microsoft Graph returned an error.").strip()
        code = str(error.get("code") or "").strip()
        return code, f"{code}: {message}" if code else message
    return "", "Microsoft Graph returned an error."


def _emit_graph_delivery_error(db: Session, *, route: WebhookRoute, target: dict[str, str], exc: GraphDeliveryError) -> None:
    emit_event(
        db,
        level="error",
        category="integration",
        event_type=f"graph.delivery.{exc.error_type}",
        message=str(exc),
        target={
            "type": target.get("kind", "message"),
            "id": target.get("channel_id") or target.get("chat_id") or "",
            "route_id": getattr(route, "id", "") or "",
        },
        http={"method": "POST", "status_code": exc.status_code},
        security={"severity": "medium", "reason": exc.error_type},
        raw={
            "graph_error_code": exc.graph_error_code,
            "graph_error_message": exc.graph_error_message,
            "result": exc.result,
        },
        domain="integration",
    )


def _apply_operator_guidance(exc: GraphDeliveryError, target: dict[str, str], diagnostics: Any) -> None:
    operator_message = _operator_message_for_error(exc, target, diagnostics)
    if not operator_message:
        return
    exc.error_type = "graph_channel_access_denied"
    exc.args = (operator_message,)


def _operator_message_for_error(exc: GraphDeliveryError, target: dict[str, str], diagnostics: Any) -> str:
    if exc.status_code != 403 or target.get("kind") != "channel":
        return ""
    service_user = _service_user_label(diagnostics)
    target_label = _target_label(target)
    return (
        f"Microsoft Graph denied channel delivery to {target_label} with HTTP 403. "
        f"Add the connected Graph service user {service_user} to the target Team/channel and verify delegated "
        "ChannelMessage.Send consent, then run Send test again."
    )


def _service_user_label(diagnostics: Any) -> str:
    principal = str(getattr(diagnostics, "service_user_principal_name", "") or "").strip()
    display_name = str(getattr(diagnostics, "service_user_display_name", "") or "").strip()
    if principal and display_name:
        return f"{display_name} ({principal})"
    if principal:
        return principal
    if display_name:
        return display_name
    return "configured in Settings"


def _target_label(target: dict[str, str]) -> str:
    team_name = target.get("team_name", "").strip()
    channel_name = target.get("target_name", "").strip()
    if team_name and channel_name.lower().startswith(f"{team_name.lower()} /"):
        return channel_name
    if team_name and channel_name:
        return f"{team_name} / {channel_name}"
    return channel_name or team_name or "the selected channel"


def _error_result(exc: GraphDeliveryError, target: dict[str, str]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "backend": GRAPH_BACKEND,
        "target": target,
        "error_type": exc.error_type,
    }
    if exc.status_code is not None:
        result["status_code"] = exc.status_code
    if exc.graph_error_code:
        result["graph_error_code"] = exc.graph_error_code
    if exc.graph_error_message:
        result["graph_error_message"] = exc.graph_error_message
    if str(exc):
        result["operator_message"] = str(exc)
    return result


def _safe_request_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "content_type": payload.get("body", {}).get("contentType", ""),
        "has_attachments": bool(payload.get("attachments")),
        "attachment_count": len(payload.get("attachments") or []),
    }
