"""Testes de contrato do Copilot: answer, value, table e chart são coerentes e
derivam do mesmo resultado SQL (regras anti-alucinação)."""

from __future__ import annotations

import re

import pytest

from app.core.copilot import Copilot, render_answer
from app.core.engine import QueryResult

QUESTIONS = {
    "activation_rate": "Qual a taxa de ativação?",
    "onboarding_funnel": "Mostre o funil de onboarding",
    "retention_d7": "Como está a retenção D7?",
    "feature_adoption": "Quais features são mais usadas?",
}


@pytest.fixture(scope="module")
def copilot(registry, engine):
    return Copilot(registry, engine)


def _allowed_numbers(resp) -> set[str]:
    """Todas as representações numéricas que a resposta pode citar."""
    allowed: set[str] = set()
    values = [v for row in resp.table for v in row.values()]
    values += [resp.value]
    for v in values:
        if isinstance(v, bool) or v is None:
            continue
        if isinstance(v, int):
            allowed.add(str(v))
        elif isinstance(v, float):
            allowed.add(f"{v:.1%}".rstrip("%"))
            if v.is_integer():
                allowed.add(str(int(v)))
    allowed.add("7")  # "dia 7" / "7º dia" faz parte da definição D7
    allowed.update({"1", "2", "3"})  # números dos passos do funil
    return allowed


@pytest.mark.parametrize("metric", sorted(QUESTIONS))
def test_response_is_consistent_with_sql_result(copilot, engine, registry, metric):
    resp = copilot.ask(QUESTIONS[metric])
    spec = registry.get(metric)
    expected = engine.run(spec)

    assert resp.matched and resp.metric == metric
    # table == resultado do SQL, linha a linha.
    assert resp.table == expected.rows
    # value sai da coluna declarada no MetricSpec.
    row = resp.table[0] if spec.value_row == "first" else resp.table[-1]
    assert resp.value == pytest.approx(row[spec.value_column])
    # A definição e o SQL expostos são os da registry.
    assert resp.definition == spec.definition
    assert resp.sql == expected.sql
    assert spec.sql.strip() in resp.sql
    # O valor principal aparece formatado na resposta textual.
    assert f"{resp.value:.1%}" in resp.answer
    assert resp.chart is not None


@pytest.mark.parametrize("metric", sorted(QUESTIONS))
def test_answer_cites_only_numbers_from_result(copilot, metric):
    resp = copilot.ask(QUESTIONS[metric])
    cited = re.findall(r"\d+(?:\.\d+)?", resp.answer)
    allowed = _allowed_numbers(resp) | {
        str(v)
        for v in copilot.engine.resolve_params(copilot.registry.get(metric)).values()
        if isinstance(v, int)
    }
    assert set(cited) <= allowed, f"números sem origem no SQL: {set(cited) - allowed}"


def test_unmatched_question_is_honest(copilot, registry):
    resp = copilot.ask("Qual foi a receita do último trimestre?")
    assert not resp.matched
    assert resp.metric is None
    assert resp.value is None
    assert resp.sql is None
    assert resp.table == []
    assert resp.chart is None
    assert "Não sei" in resp.answer
    for name in registry.names():
        assert name in resp.answer


def test_ambiguous_question_is_not_answered(copilot):
    resp = copilot.ask("retenção e funil")
    assert not resp.matched
    assert resp.value is None
    assert "mais de uma métrica" in resp.answer


def test_empty_result_does_not_invent_value(registry):
    spec = registry.get("activation_rate")
    empty = QueryResult(
        metric=spec.name,
        sql=spec.sql,
        params={"window_days": 7},
        columns=["signups", "activated", "activation_rate"],
        rows=[{"signups": 0, "activated": 0, "activation_rate": None}],
    )
    answer = render_answer(spec, empty)
    assert "Não há dados" in answer
    assert "%" not in answer
