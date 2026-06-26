from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class HealthOut(BaseModel):
    ok: bool = True
    service: str
    version: str


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=200)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    email: str
    display_name: str
    is_admin: bool
    is_active: bool
    created_at: datetime


class SessionResponse(BaseModel):
    ok: bool = True
    user: UserOut
    csrf_token: str


DemoItemStatus = Literal["todo", "in_progress", "done"]


class DemoItemCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    status: DemoItemStatus = "todo"
    summary: str = Field(default="", max_length=2000)


class DemoItemUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    status: DemoItemStatus | None = None
    summary: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def require_change(self):
        if self.title is None and self.status is None and self.summary is None:
            raise ValueError("At least one field must be provided")
        return self


class DemoItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    owner_id: str | None = None
    title: str
    status: str
    summary: str
    created_at: datetime
    updated_at: datetime


class AuditEventOut(BaseModel):
    id: str
    actor_type: str
    actor_id: str | None = None
    action: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


WebhookTargetType = Literal["bot_conversation"]
WebhookRouteStatus = Literal["delivered", "failed", "rejected"]


class WebhookRouteBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    source_system: str = Field(default="", max_length=120)
    is_active: bool = True
    target_type: WebhookTargetType = "bot_conversation"
    target_name: str = Field(min_length=1, max_length=200)
    bot_service_url: str = Field(min_length=1, max_length=2000)
    bot_conversation_id: str = Field(min_length=1, max_length=2000)


class WebhookRouteCreate(WebhookRouteBase):
    pass


class WebhookRouteUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    source_system: str | None = Field(default=None, max_length=120)
    is_active: bool | None = None
    target_type: WebhookTargetType | None = None
    target_name: str | None = Field(default=None, min_length=1, max_length=200)
    bot_service_url: str | None = Field(default=None, min_length=1, max_length=2000)
    bot_conversation_id: str | None = Field(default=None, min_length=1, max_length=2000)

    @model_validator(mode="after")
    def require_change(self):
        if (
            self.name is None
            and self.source_system is None
            and self.is_active is None
            and self.target_type is None
            and self.target_name is None
            and self.bot_service_url is None
            and self.bot_conversation_id is None
        ):
            raise ValueError("At least one field must be provided")
        return self


class WebhookRouteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    name: str
    source_system: str
    is_active: bool
    target_type: str
    target_name: str
    bot_service_url: str
    bot_conversation_id: str
    webhook_url: str | None = None
    webhook_url_available: bool = False
    last_delivery_status: str | None = None
    last_delivery_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class WebhookRouteCreatedOut(WebhookRouteOut):
    webhook_url: str
    webhook_url_available: bool = True


class WebhookRouteTestRequest(BaseModel):
    title: str = Field(default="Teams Webhook Relay test", min_length=1, max_length=255)
    text: str = Field(default="This is a test message from the relay service.", min_length=1, max_length=2000)
    severity: str = Field(default="info", max_length=40)


class WebhookDeliveryOut(BaseModel):
    ok: bool
    status: WebhookRouteStatus
    route_id: str
    delivery_event_id: str
    message: str


class WebhookRouteDefaultsOut(BaseModel):
    bot_default_service_url: str = ""


class WebhookDeliveryEventOut(BaseModel):
    id: str
    route_id: str | None = None
    status: str
    request_metadata: dict[str, Any] = Field(default_factory=dict)
    normalized_message: dict[str, Any] = Field(default_factory=dict)
    delivery_result: dict[str, Any] = Field(default_factory=dict)
    error: str = ""
    created_at: datetime
