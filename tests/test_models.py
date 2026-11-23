"""Testes de validação dos contratos Pydantic."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.models import (
    MAX_QUESTION_LENGTH,
    AskRequest,
    AskResponse,
    EventType,
)


def test_event_type_is_closed_enum():
    assert {e.value for e in EventType} == {
        "signup",
        "onboarding_step_completed",
        "project_created",
        "feature_used",
        "activated",
        "login",
        "session_start",
        "subscription_started",
        "subscription_cancelled",
    }
    with pytest.raises(ValueError):
        EventType("churned")


def test_ask_request_strips_and_accepts_valid_question():
    req = AskRequest(question="  qual a taxa de ativação?  ")
    assert req.question == "qual a taxa de ativação?"


@pytest.mark.parametrize("question", ["", "   ", "x" * (MAX_QUESTION_LENGTH + 1)])
def test_ask_request_rejects_invalid_length(question):
    with pytest.raises(ValidationError):
        AskRequest(question=question)


def test_ask_request_forbids_extra_fields():
    # Nada além da pergunta entra pela API (ex.: SQL ou parâmetros livres).
    with pytest.raises(ValidationError):
        AskRequest(question="ativação", sql="DROP TABLE users")


def test_ask_response_contract_fields():
    assert list(AskResponse.model_fields) == [
        "metric",
        "answer",
        "value",
        "definition",
        "sql",
        "table",
        "chart",
        "confidence",
        "matched",
    ]


def test_ask_response_confidence_bounds():
    with pytest.raises(ValidationError):
        AskResponse(answer="x", confidence=1.5, matched=False)
