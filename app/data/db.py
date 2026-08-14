"""Camada de armazenamento em DuckDB.

- ``build_connection``: conexão in-memory populada (útil para testes/summary).
- ``write_duckdb``: materializa um arquivo ``.duckdb`` em disco.
- ``connect_readonly``: abre um arquivo existente em modo **read-only** (o modo
  usado no caminho de request, conforme os limites de segurança do projeto).
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from app.data.generate import DEFAULT_N_USERS, SEED, generate_frames

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "warehouse.duckdb"

_SCHEMA_SQL = """
CREATE TABLE users AS SELECT * FROM users_df;
CREATE TABLE events AS SELECT * FROM events_df;
CREATE INDEX idx_events_user ON events(user_id);
CREATE INDEX idx_events_type ON events(event_type);
"""


def _populate(con: duckdb.DuckDBPyConnection, n_users: int, seed: int) -> None:
    users_df, events_df = generate_frames(n_users, seed)
    con.register("users_df", users_df)
    con.register("events_df", events_df)
    con.execute(_SCHEMA_SQL)
    con.unregister("users_df")
    con.unregister("events_df")


def build_connection(
    n_users: int = DEFAULT_N_USERS, seed: int = SEED
) -> duckdb.DuckDBPyConnection:
    """Cria uma conexão in-memory já populada com os dados sintéticos."""
    con = duckdb.connect(":memory:")
    _populate(con, n_users, seed)
    return con


def write_duckdb(
    path: str | Path = DEFAULT_DB_PATH,
    n_users: int = DEFAULT_N_USERS,
    seed: int = SEED,
) -> Path:
    """Gera os dados e materializa um arquivo DuckDB em disco."""
    path = Path(path)
    if path.exists():
        path.unlink()
    con = duckdb.connect(str(path))
    try:
        _populate(con, n_users, seed)
    finally:
        con.close()
    return path


def connect_readonly(path: str | Path = DEFAULT_DB_PATH) -> duckdb.DuckDBPyConnection:
    """Abre um arquivo DuckDB existente em modo read-only."""
    return duckdb.connect(str(path), read_only=True)
