"""Modelos de domínio (Pydantic) e enum fechado de eventos.

Estes modelos são a fonte de verdade do formato de `users` e `events`.
O `EventType` é um enum **fechado** (whitelist): apenas eventos conhecidos
entram no sistema — parte da defesa anti-alucinação descrita em
`docs/architecture.md`.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


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


# --------------------------------------------------------------------------- #
# Contratos da camada de aplicação (E1/E3)
# --------------------------------------------------------------------------- #

#: Tamanho máximo aceito para a pergunta em linguagem natural.
MAX_QUESTION_LENGTH = 500

Visualization = Literal["kpi", "funnel", "bar"]


class MetricSpec(BaseModel):
    """Especificação imutável de uma métrica da whitelist.

    ``definition`` e ``sql`` vêm da mesma entrada do catálogo
    (`app/data/catalog.yml` + `app/data/sql/<name>/v<version>.sql`) e são a
    única fonte de verdade do que é mostrado e do que é executado.
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    version: int = Field(ge=1)
    title: str
    definition: str
    sql: str
    synonyms: tuple[str, ...] = Field(min_length=1)
    visualization: Visualization
    value_column: str
    value_row: Literal["first", "last"] = "first"
    answer_template: str
    default_params: dict[str, int | float | str] = Field(default_factory=dict)
    allowed_dimensions: tuple[str, ...] = ()


class AskRequest(BaseModel):
    """Entrada de ``POST /ask``. A pergunta só é usada para matching."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    question: str = Field(min_length=1, max_length=MAX_QUESTION_LENGTH)


class AskResponse(BaseModel):
    """Contrato de saída de ``POST /ask`` (ver `docs/architecture.md`)."""

    metric: str | None = None
    answer: str
    value: float | None = None
    definition: str | None = None
    sql: str | None = None
    table: list[dict[str, Any]] = Field(default_factory=list)
    chart: dict[str, Any] | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    matched: bool


class MetricInfo(BaseModel):
    """Resumo público de uma métrica (``GET /metrics``)."""

    name: str
    title: str
    definition: str
    synonyms: list[str]
    visualization: Visualization
