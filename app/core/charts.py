"""Helpers Plotly: figura → JSON (dict) a partir das linhas do resultado SQL.

Os gráficos usam **apenas** ``rows`` devolvidas pelo ``QueryEngine`` — nenhum
número é calculado ou inventado aqui. Cada métrica é uma série única: uma cor
(slot 1 da paleta categórica), sem legenda; fundo transparente para herdar o
tema claro/escuro de quem renderiza (Streamlit).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import plotly.graph_objects as go

from app.core.models import MetricSpec

SERIES_COLOR = "#2a78d6"
MUTED = "rgba(128,128,128,0.25)"
FONT = dict(family="Inter, system-ui, sans-serif", size=13)

Rows = list[dict[str, Any]]


def _base_layout(title: str) -> dict[str, Any]:
    return dict(
        title=dict(text=title, x=0, xanchor="left"),
        font=FONT,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=16, r=16, t=56, b=16),
        showlegend=False,
        height=360,
    )


def kpi_chart(spec: MetricSpec, rows: Rows) -> go.Figure:
    """Número em destaque (hero number) para métricas de valor único."""
    value = rows[0].get(spec.value_column) if rows else None
    fig = go.Figure(
        go.Indicator(
            mode="number",
            value=value,
            number=dict(valueformat=".1%", font=dict(size=56)),
        )
    )
    fig.update_layout(**{**_base_layout(spec.title), "height": 180})
    return fig


def funnel_chart(spec: MetricSpec, rows: Rows) -> go.Figure:
    """Funil de usuários por passo, com % do topo."""
    fig = go.Figure(
        go.Funnel(
            y=[f"Passo {r['step']}" for r in rows],
            x=[r["users"] for r in rows],
            customdata=[[r["pct_of_top"], r["pct_of_prev"]] for r in rows],
            texttemplate="%{x:d}<br>%{percentInitial:.1%}",
            marker=dict(color=SERIES_COLOR),
            connector=dict(fillcolor=MUTED, line=dict(width=0)),
            hovertemplate=(
                "%{y}<br>Usuários: %{x}<br>% do topo: %{customdata[0]:.1%}"
                "<extra></extra>"
            ),
        )
    )
    fig.update_layout(**_base_layout(spec.title))
    return fig


def bar_chart(spec: MetricSpec, rows: Rows) -> go.Figure:
    """Ranking em barras horizontais (maior no topo)."""
    ordered = list(reversed(rows))  # Plotly desenha de baixo para cima
    fig = go.Figure(
        go.Bar(
            x=[r[spec.value_column] for r in ordered],
            y=[r["feature_name"] for r in ordered],
            orientation="h",
            marker=dict(color=SERIES_COLOR, line=dict(width=0)),
            text=[f"{r[spec.value_column]:.1%}" for r in ordered],
            textposition="outside",
            customdata=[[r["users"], r["active_users"]] for r in ordered],
            hovertemplate=(
                "%{y}: %{x:.1%}<br>%{customdata[0]} de %{customdata[1]} "
                "usuários ativos<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        **_base_layout(spec.title),
        bargap=0.35,
        xaxis=dict(tickformat=".0%", range=[0, 1.1], gridcolor=MUTED, zeroline=False),
        yaxis=dict(showgrid=False),
    )
    return fig


BUILDERS: dict[str, Callable[[MetricSpec, Rows], go.Figure]] = {
    "kpi": kpi_chart,
    "funnel": funnel_chart,
    "bar": bar_chart,
}


def figure_to_json(fig: go.Figure) -> dict[str, Any]:
    """Serializa a figura em JSON Plotly puro (sem tipos numpy)."""
    return json.loads(fig.to_json())


def build_chart(spec: MetricSpec, rows: Rows) -> dict[str, Any] | None:
    """Figura Plotly (JSON) para a métrica, ou ``None`` se não houver dados."""
    if not rows:
        return None
    return figure_to_json(BUILDERS[spec.visualization](spec, rows))
