"""Copilot: orquestra IntentRouter → QueryEngine → AskResponse.

Regras anti-alucinação aplicadas aqui:
- ``value``, ``table`` e ``chart`` vêm exclusivamente do resultado do SQL;
- ``answer`` é o ``answer_template`` do ``MetricSpec`` formatado com esse
  resultado (e com os parâmetros vinculados) — nenhum texto livre;
- sem match (ou match ambíguo) → resposta honesta listando as métricas.
"""

from __future__ import annotations

from typing import Any

from app.core.charts import build_chart
from app.core.engine import QueryEngine, QueryResult
from app.core.models import AskResponse, MetricSpec
from app.core.registry import MetricRegistry
from app.core.router import IntentRouter, RouteResult

NO_DATA_TEMPLATE = "Não há dados suficientes para calcular {title} no período."
NO_MATCH_TEMPLATE = (
    "Não sei responder a essa pergunta: ela não corresponde a nenhuma métrica "
    "disponível. Métricas disponíveis: {available}."
)
AMBIGUOUS_TEMPLATE = (
    "A pergunta parece envolver mais de uma métrica ({candidates}). "
    "Pergunte sobre uma métrica por vez. Métricas disponíveis: {available}."
)


def answer_context(spec: MetricSpec, result: QueryResult) -> dict[str, Any]:
    """Valores disponíveis para o template — todos vindos do resultado/binding."""
    rows = result.rows
    context: dict[str, Any] = dict(result.params)
    if rows:
        context.update(rows[0])
        context.update({f"last_{k}": v for k, v in rows[-1].items()})
    context["n_rows"] = len(rows)
    context["value"] = extract_value(spec, rows)
    return context


def extract_value(spec: MetricSpec, rows: list[dict[str, Any]]) -> float | None:
    """Valor principal: ``value_column`` da primeira ou da última linha."""
    if not rows:
        return None
    row = rows[0] if spec.value_row == "first" else rows[-1]
    value = row.get(spec.value_column)
    return None if value is None else float(value)


def render_answer(spec: MetricSpec, result: QueryResult) -> str:
    context = answer_context(spec, result)
    if context["value"] is None:
        return NO_DATA_TEMPLATE.format(title=spec.title.lower())
    return spec.answer_template.format(**context)


class Copilot:
    """Ponto de entrada único da aplicação: pergunta → ``AskResponse``."""

    def __init__(
        self,
        registry: MetricRegistry,
        engine: QueryEngine,
        router: IntentRouter | None = None,
    ) -> None:
        self.registry = registry
        self.engine = engine
        self.router = router or IntentRouter(registry)

    def _available(self) -> str:
        return ", ".join(f"{s.title} ({s.name})" for s in self.registry)

    def _unmatched(self, route: RouteResult) -> AskResponse:
        if route.ambiguous:
            top = [c for c in route.candidates if c.score == route.confidence]
            answer = AMBIGUOUS_TEMPLATE.format(
                candidates=", ".join(c.name for c in top),
                available=self._available(),
            )
        else:
            answer = NO_MATCH_TEMPLATE.format(available=self._available())
        return AskResponse(
            answer=answer, confidence=route.confidence, matched=False
        )

    def ask(self, question: str) -> AskResponse:
        route = self.router.route(question)
        if not route.matched:
            return self._unmatched(route)

        spec = route.spec
        result = self.engine.run(spec)
        return AskResponse(
            metric=spec.name,
            answer=render_answer(spec, result),
            value=extract_value(spec, result.rows),
            definition=spec.definition,
            sql=result.sql,
            table=result.rows,
            chart=build_chart(spec, result.rows),
            confidence=route.confidence,
            matched=True,
        )
