"""Testes do IntentRouter: frases → métrica, incluindo o caso "não casa"."""

from __future__ import annotations

import pytest

from app.core.router import IntentRouter, normalize, synonym_score, tokenize


@pytest.fixture(scope="module")
def router(registry):
    return IntentRouter(registry)


@pytest.mark.parametrize(
    ("question", "metric"),
    [
        ("Qual a taxa de ativação?", "activation_rate"),
        ("quantos usuários ativaram em 7 dias?", "activation_rate"),
        ("activation rate", "activation_rate"),
        ("ATIVAÇÃO", "activation_rate"),
        ("mostre o funil de onboarding", "onboarding_funnel"),
        ("qual a conversão do onboarding?", "onboarding_funnel"),
        ("Como está a retenção D7?", "retention_d7"),
        ("retenção no dia 7", "retention_d7"),
        ("retention", "retention_d7"),
        ("quais features são mais usadas?", "feature_adoption"),
        ("adoção de funcionalidades", "feature_adoption"),
        ("feature adoption", "feature_adoption"),
    ],
)
def test_routes_known_questions(router, question, metric):
    result = router.route(question)
    assert result.matched
    assert result.spec.name == metric
    assert result.confidence >= router.threshold


@pytest.mark.parametrize(
    "question",
    [
        "qual a receita mensal?",
        "taxa de churn",
        "quantos usuários temos?",
        "qual o cancelamento de assinaturas?",
        "previsão do tempo amanhã",
        "DROP TABLE users; --",
        "'; SELECT * FROM users; --",
        "???",
    ],
)
def test_unknown_questions_do_not_match(router, question):
    result = router.route(question)
    assert not result.matched
    assert result.spec is None
    assert result.confidence < router.threshold


def test_ambiguous_question_does_not_guess(router):
    result = router.route("retenção e funil")
    assert not result.matched
    assert result.ambiguous
    assert {c.name for c in result.candidates[:2]} == {
        "retention_d7",
        "onboarding_funnel",
    }


def test_more_specific_synonym_wins_tie(router):
    # "taxa de ativação" (2 tokens) é mais específico que "onboarding" (1 token).
    result = router.route("taxa de ativação do onboarding")
    assert result.spec.name == "activation_rate"


def test_candidates_are_sorted_and_cover_all_metrics(router, registry):
    candidates = router.score("retenção")
    assert {c.name for c in candidates} == set(registry.names())
    scores = [c.score for c in candidates]
    assert scores == sorted(scores, reverse=True)


def test_routing_is_deterministic(router):
    results = {router.route("taxa de ativação").confidence for _ in range(5)}
    assert len(results) == 1


def test_normalize_strips_accents_and_punctuation():
    assert normalize("Retenção D7?!") == "retencao d7"
    assert tokenize("Qual é a taxa de ativação?") == ["taxa", "ativacao"]


def test_synonym_score_bounds():
    assert synonym_score("taxa de ativação", "taxa de ativação") == 1.0
    assert synonym_score("taxa de ativação", "taxa") == 0.5
    assert synonym_score("taxa de ativação", "nada a ver") == 0.0
    assert synonym_score("de", "de") == 0.0  # só stopwords


def test_invalid_threshold(registry):
    with pytest.raises(ValueError):
        IntentRouter(registry, threshold=0)
