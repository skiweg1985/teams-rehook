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
