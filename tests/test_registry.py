"""Testes da MetricRegistry: whitelist completa e coerente."""

from __future__ import annotations

import re

import pytest

from app.core.engine import ALLOWED_PARAMS
from app.core.models import EventType
from app.core.registry import MetricRegistry

EXPECTED = {"activation_rate", "onboarding_funnel", "retention_d7", "feature_adoption"}
FORBIDDEN_SQL = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|ATTACH|COPY|PRAGMA|INSTALL|LOAD)\b",
    re.IGNORECASE,
)


def test_registry_has_exactly_the_four_metrics(registry):
    assert set(registry.names()) == EXPECTED


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_each_spec_is_complete(registry, name):
    spec = registry.get(name)
    assert spec.title
    assert len(spec.definition) > 30
    assert spec.sql.strip()
    assert spec.synonyms
    assert spec.visualization in {"kpi", "funnel", "bar"}
    assert spec.value_column in spec.sql
    assert spec.answer_template


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_sql_is_read_only_template(registry, name):
    sql = registry.get(name).sql
    # Comentários podem citar palavras-chave; analisa só o código.
    code = "\n".join(line.split("--")[0] for line in sql.splitlines())
    assert not FORBIDDEN_SQL.search(code)
    assert ";" not in code.rstrip().rstrip(";")  # uma única instrução
    assert "{" not in code  # sem placeholders de formatação de string
    params = set(re.findall(r"\$([a-z_]+)\b", code))
    assert params <= set(ALLOWED_PARAMS)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_sql_only_references_whitelisted_events(registry, name):
    code = "\n".join(
        line.split("--")[0] for line in registry.get(name).sql.splitlines()
    )
    literals = {
        lit for lit in re.findall(r"'([^']*)'", code) if not lit.startswith("$")
    }
    assert literals <= {e.value for e in EventType}


def test_retention_d7_definition_and_sql_agree_on_exact_day_7(registry):
    spec = registry.get("retention_d7")
    assert "dia 7 exato" in spec.definition
    assert "[D+7, D+8)" in spec.definition
    assert "INTERVAL 7 DAY" in spec.sql
    assert "INTERVAL 8 DAY" in spec.sql


def test_activation_default_window_matches_definition(registry):
    spec = registry.get("activation_rate")
    assert spec.default_params["window_days"] == 7
    assert "7d" in spec.definition
    assert "$window_days" in spec.sql


def test_unknown_metric_raises(registry):
    with pytest.raises(KeyError):
        registry.get("receita")


def test_duplicate_metric_rejected(registry):
    spec = registry.get("activation_rate")
    with pytest.raises(ValueError):
        MetricRegistry([spec, spec])


def test_describe_hides_sql(registry):
    infos = registry.describe()
    assert {i.name for i in infos} == EXPECTED
    assert all("sql" not in i.model_dump() for i in infos)
