"""Atalho para executar uma métrica por nome e obter um DataFrame.

A execução de fato (binding, read-only, timeout) vive em ``app.core.engine``;
este módulo apenas compõe registry + engine para scripts e testes.
"""

from __future__ import annotations

import duckdb
import pandas as pd

from app.core.engine import ALLOWED_PARAMS, QueryEngine
from app.core.registry import default_registry

__all__ = ["ALLOWED_PARAMS", "run_metric"]


def run_metric(
    con: duckdb.DuckDBPyConnection,
    name: str,
    params: dict | None = None,
) -> pd.DataFrame:
    """Executa a métrica ``name`` e devolve o resultado como DataFrame."""
    spec = default_registry().get(name)
    return QueryEngine(con).run(spec, params).to_frame()
