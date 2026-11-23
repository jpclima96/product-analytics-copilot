"""Testes do QueryEngine: read-only, binding, limites e valores esperados."""

from __future__ import annotations

import duckdb
import pytest

from app.core.engine import QueryEngine, QueryTimeoutError
from app.core.models import MetricSpec

# Valores do dataset padrão (seed=42, 12.000 usuários). O gerador é
# determinístico, então estes números são estáveis — se mudarem, algo mudou
# no gerador ou na definição de uma métrica.
EXPECTED_VALUES = {
    "activation_rate": ("activation_rate", 0.5054),
    "retention_d7": ("retention_d7", 0.2551),
}


def test_open_is_read_only(engine):
    with pytest.raises(duckdb.Error):
        engine._con.execute("CREATE TABLE hack (a INTEGER)")
    with pytest.raises(duckdb.Error):
        engine._con.execute("DELETE FROM users")


def test_open_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        QueryEngine.open(tmp_path / "nao_existe.duckdb")


@pytest.mark.parametrize(
    "name", ["activation_rate", "onboarding_funnel", "retention_d7", "feature_adoption"]
)
def test_every_metric_runs(engine, registry, name):
    result = engine.run(registry.get(name))
    assert result.rows
    assert registry.get(name).value_column in result.columns
    assert result.sql.endswith(registry.get(name).sql.strip())
    assert not result.truncated


@pytest.mark.parametrize("name", sorted(EXPECTED_VALUES))
def test_known_values_are_deterministic(engine, registry, name):
    column, expected = EXPECTED_VALUES[name]
    result = engine.run(registry.get(name))
    assert result.rows[0][column] == pytest.approx(expected)


def test_result_sql_is_exactly_what_ran(engine, con, registry):
    result = engine.run(registry.get("activation_rate"))
    assert result.sql.startswith("-- bound params: ")
    assert "window_days=7" in result.sql.splitlines()[0]
    # Reexecutar o texto devolvido com os mesmos parâmetros dá o mesmo resultado.
    bind = engine.resolve_params(registry.get("activation_rate"))
    again = con.execute(result.sql, bind).fetchone()
    assert list(result.rows[0].values()) == pytest.approx([float(v) for v in again])


def test_only_referenced_params_are_bound(engine, registry):
    bind = engine.resolve_params(registry.get("feature_adoption"))
    assert set(bind) == {"start", "end"}
    bind = engine.resolve_params(registry.get("activation_rate"))
    assert set(bind) == {"start", "end", "window_days"}


def test_window_days_param_changes_result(engine, registry):
    spec = registry.get("activation_rate")
    r1 = engine.run(spec, {"window_days": 1}).rows[0]["activation_rate"]
    r7 = engine.run(spec, {"window_days": 7}).rows[0]["activation_rate"]
    assert r1 < r7


def test_unknown_param_rejected(engine, registry):
    with pytest.raises(ValueError):
        engine.run(registry.get("activation_rate"), {"table": "users"})


def test_injection_attempt_is_bound_not_executed(engine, con, registry):
    payload = "2025-01-01'; DROP TABLE users; --"
    with pytest.raises(duckdb.Error):
        engine.run(registry.get("activation_rate"), {"start": payload})
    assert con.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0


def test_max_rows_truncates(db_path, registry):
    eng = QueryEngine.open(db_path, max_rows=2)
    try:
        result = eng.run(registry.get("feature_adoption"))
    finally:
        eng.close()
    assert len(result.rows) == 2
    assert result.truncated


def test_timeout_interrupts_slow_query(db_path):
    slow = MetricSpec(
        name="slow_test_only",
        version=1,
        title="Consulta lenta (teste)",
        definition="Consulta propositalmente lenta para testar o timeout.",
        sql=(
            "SELECT COUNT(*) AS n FROM range(1000000) a, range(1000000) b "
            "WHERE (a.range * b.range) % 7 = 3"
        ),
        synonyms=("lenta",),
        visualization="kpi",
        value_column="n",
        answer_template="{value}",
    )
    eng = QueryEngine.open(db_path, timeout_s=0.3)
    try:
        with pytest.raises(QueryTimeoutError):
            eng.run(slow)
    finally:
        eng.close()


def test_rows_are_json_serializable(engine, registry):
    import json

    for spec in registry:
        json.dumps(engine.run(spec).rows)
