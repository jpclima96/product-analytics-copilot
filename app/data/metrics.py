"""Execução de métricas: lê o SQL versionado e o roda com parâmetros vinculados.

Segurança: apenas parâmetros da whitelist ``ALLOWED_PARAMS`` são vinculados, e
sempre por *binding* do DuckDB — nunca por concatenação de strings.
"""

from __future__ import annotations

import duckdb
import pandas as pd

from app.data.catalog import get_metric, read_sql

#: Parâmetros que podem ser vinculados às consultas (whitelist).
ALLOWED_PARAMS = ("start", "end", "window_days")


def _default_range(con: duckdb.DuckDBPyConnection) -> tuple:
    start = con.execute("SELECT MIN(signup_ts) FROM users").fetchone()[0]
    end = con.execute("SELECT MAX(event_ts) FROM events").fetchone()[0]
    return start, end


def run_metric(
    con: duckdb.DuckDBPyConnection,
    name: str,
    params: dict | None = None,
) -> pd.DataFrame:
    """Executa a métrica ``name`` e devolve o resultado como DataFrame."""
    spec = get_metric(name)
    sql = read_sql(name)

    merged: dict = dict(spec.get("default_params") or {})
    if params:
        merged.update(params)

    if merged.get("start") is None or merged.get("end") is None:
        start, end = _default_range(con)
        merged.setdefault("start", None)
        merged.setdefault("end", None)
        merged["start"] = merged["start"] or start
        merged["end"] = merged["end"] or end

    # Vincula somente parâmetros permitidos e realmente referenciados no SQL.
    bind = {
        key: merged[key]
        for key in ALLOWED_PARAMS
        if key in merged and f"${key}" in sql
    }
    return con.execute(sql, bind).df()
