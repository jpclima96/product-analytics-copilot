"""Modelos de domínio (Pydantic) e enum fechado de eventos.

Estes modelos são a fonte de verdade do formato de `users` e `events`.
O `EventType` é um enum **fechado** (whitelist): apenas eventos conhecidos
entram no sistema — parte da defesa anti-alucinação descrita em
`docs/architecture.md`.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Tipos de evento permitidos no produto SaaS de exemplo."""

    signup = "signup"
    onboarding_step_completed = "onboarding_step_completed"
    project_created = "project_created"
    feature_used = "feature_used"
    activated = "activated"
    login = "login"
    session_start = "session_start"
    subscription_started = "subscription_started"
    subscription_cancelled = "subscription_cancelled"


#: Eventos que caracterizam "atividade" do usuário (usados em retenção/adoção).
ACTIVITY_EVENTS: tuple[EventType, ...] = (
    EventType.login,
    EventType.feature_used,
    EventType.session_start,
)


class User(BaseModel):
    """Dimensão de usuário."""

    user_id: str
    signup_ts: datetime
    plan: str
    country: str


class Event(BaseModel):
    """Um evento (grão = 1 evento por linha)."""

    event_id: str
    user_id: str
    event_type: EventType
    event_ts: datetime
    properties: dict = Field(default_factory=dict)
    session_id: str | None = None
