"""Fixtures compartilhadas dos testes.

O dataset sintético padrão é materializado **uma vez** num arquivo DuckDB
temporário e aberto em modo read-only — o mesmo caminho usado pela API.
"""

from __future__ import annotations

import pytest

from app.core.engine import QueryEngine
from app.core.registry import default_registry
from app.data.db import connect_readonly, write_duckdb
from app.data.generate import DEFAULT_N_USERS, SEED


@pytest.fixture(scope="session")
def db_path(tmp_path_factory):
    path = tmp_path_factory.mktemp("warehouse") / "warehouse.duckdb"
    return write_duckdb(path, n_users=DEFAULT_N_USERS, seed=SEED)


@pytest.fixture(scope="session")
def con(db_path):
    """Conexão DuckDB read-only com o dataset sintético padrão."""
    connection = connect_readonly(db_path)
    yield connection
    connection.close()


@pytest.fixture(scope="session")
def registry():
    return default_registry()


@pytest.fixture(scope="session")
def engine(db_path):
    eng = QueryEngine.open(db_path)
    yield eng
    eng.close()
