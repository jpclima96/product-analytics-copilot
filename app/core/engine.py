"""QueryEngine: executa o SQL da registry contra o DuckDB, somente leitura.

Garantias:
- só executa ``MetricSpec.sql`` (templates da registry), nunca SQL arbitrário;
- parâmetros sempre por *binding* do DuckDB e restritos a ``ALLOWED_PARAMS``;
- em produção a conexão é aberta com ``read_only=True`` (``QueryEngine.open``);
- cada execução tem timeout (``con.interrupt``) e limite de linhas.

O SQL devolvido em ``QueryResult.sql`` é exatamente o texto executado: o
template da registry precedido de um comentário com os valores vinculados, para
auditoria. Os valores vêm do catálogo ou do próprio banco, nunca do usuário.
"""

from __future__ import annotations

import math
import threading
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
from pydantic import BaseModel

from app.core.models import MetricSpec

#: Parâmetros que podem ser vinculados às consultas (whitelist).
ALLOWED_PARAMS: tuple[str, ...] = ("start", "end", "window_days")

DEFAULT_TIMEOUT_S = 10.0
DEFAULT_MAX_ROWS = 1_000

_RANGE_SQL = (
    "SELECT (SELECT MIN(signup_ts) FROM users), (SELECT MAX(event_ts) FROM events)"
)


class QueryTimeoutError(RuntimeError):
    """A consulta excedeu o tempo máximo permitido."""


class QueryResult(BaseModel):
    """Resultado tabular de uma métrica, já em tipos JSON-serializáveis."""

    metric: str
    sql: str
    params: dict[str, Any]
    columns: list[str]
    rows: list[dict[str, Any]]
    truncated: bool = False

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows, columns=self.columns)


def _to_json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        value = float(value)
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


def _format_param(value: Any) -> str:
    if isinstance(value, datetime | date):
        return value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
    return str(value)


class QueryEngine:
    """Executor de métricas sobre uma conexão DuckDB."""

    def __init__(
        self,
        con: duckdb.DuckDBPyConnection,
        *,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        max_rows: int = DEFAULT_MAX_ROWS,
    ) -> None:
        self._con = con
        self.timeout_s = timeout_s
        self.max_rows = max_rows
        self._default_range: tuple[Any, Any] | None = None

    @classmethod
    def open(cls, path: str | Path, **kwargs: Any) -> QueryEngine:
        """Abre um arquivo DuckDB existente em modo **read-only**."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Banco DuckDB não encontrado: {path}")
        return cls(duckdb.connect(str(path), read_only=True), **kwargs)

    def close(self) -> None:
        self._con.close()

    # ------------------------------------------------------------------ #
    def default_range(self) -> tuple[Any, Any]:
        """Período padrão: do primeiro signup ao último evento (cacheado)."""
        if self._default_range is None:
            self._default_range = tuple(self._con.execute(_RANGE_SQL).fetchone())
        return self._default_range

    def resolve_params(
        self, spec: MetricSpec, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Mescla defaults + parâmetros e mantém só os usados pelo template."""
        params = dict(params or {})
        unknown = set(params) - set(ALLOWED_PARAMS)
        if unknown:
            raise ValueError(f"Parâmetros não permitidos: {sorted(unknown)}")

        merged: dict[str, Any] = {**spec.default_params, **params}
        start, end = self.default_range()
        if merged.get("start") is None:
            merged["start"] = start
        if merged.get("end") is None:
            merged["end"] = end
        if "window_days" in merged:
            merged["window_days"] = int(merged["window_days"])

        return {
            key: merged[key]
            for key in ALLOWED_PARAMS
            if key in merged and f"${key}" in spec.sql
        }

    @staticmethod
    def render_sql(spec: MetricSpec, bind: dict[str, Any]) -> str:
        """Texto executado: comentário de auditoria + template inalterado."""
        header = ", ".join(f"{k}={_format_param(v)}" for k, v in sorted(bind.items()))
        return f"-- bound params: {header}\n{spec.sql.strip()}"

    def run(self, spec: MetricSpec, params: dict[str, Any] | None = None) -> QueryResult:
        """Executa a métrica e devolve o resultado (com timeout e limite)."""
        bind = self.resolve_params(spec, params)
        sql = self.render_sql(spec, bind)

        cursor = self._con.cursor()
        timer = threading.Timer(self.timeout_s, cursor.interrupt)
        timer.start()
        try:
            cursor.execute(sql, bind)
            columns = [d[0] for d in cursor.description]
            raw = cursor.fetchmany(self.max_rows + 1)
        except duckdb.InterruptException as exc:
            raise QueryTimeoutError(
                f"Consulta excedeu {self.timeout_s:.0f}s"
            ) from exc
        finally:
            timer.cancel()
            cursor.close()

        truncated = len(raw) > self.max_rows
        rows = [
            {col: _to_json_value(val) for col, val in zip(columns, row, strict=True)}
            for row in raw[: self.max_rows]
        ]
        return QueryResult(
            metric=spec.name,
            sql=sql,
            params={k: _to_json_value(v) for k, v in bind.items()},
            columns=columns,
            rows=rows,
            truncated=truncated,
        )
