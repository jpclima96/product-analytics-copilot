"""Testes dos helpers Plotly: JSON válido por tipo de gráfico."""

from __future__ import annotations

import json

import plotly.graph_objects as go
import plotly.io as pio
import pytest

from app.core.charts import BUILDERS, build_chart

EXPECTED_TRACE = {"kpi": "indicator", "funnel": "funnel", "bar": "bar"}


@pytest.mark.parametrize(
    "name", ["activation_rate", "onboarding_funnel", "retention_d7", "feature_adoption"]
)
def test_chart_is_valid_plotly_json(engine, registry, name):
    spec = registry.get(name)
    rows = engine.run(spec).rows
    chart = build_chart(spec, rows)

    json.dumps(chart)  # serializável
    fig = pio.from_json(json.dumps(chart))  # Plotly reconstrói a figura
    assert isinstance(fig, go.Figure)
    assert chart["data"][0]["type"] == EXPECTED_TRACE[spec.visualization]


def test_chart_numbers_come_from_rows(engine, registry):
    spec = registry.get("onboarding_funnel")
    rows = engine.run(spec).rows
    chart = build_chart(spec, rows)
    assert chart["data"][0]["x"] == [r["users"] for r in rows]

    spec = registry.get("activation_rate")
    rows = engine.run(spec).rows
    chart = build_chart(spec, rows)
    assert chart["data"][0]["value"] == rows[0]["activation_rate"]


def test_bar_chart_shows_top_feature_on_top(engine, registry):
    spec = registry.get("feature_adoption")
    rows = engine.run(spec).rows
    chart = build_chart(spec, rows)
    # Plotly desenha a última categoria no topo.
    assert chart["data"][0]["y"][-1] == rows[0]["feature_name"]


def test_empty_rows_yield_no_chart(registry):
    assert build_chart(registry.get("feature_adoption"), []) is None


def test_every_visualization_has_a_builder(registry):
    assert {s.visualization for s in registry} <= set(BUILDERS)
