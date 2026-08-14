"""Fixtures compartilhadas dos testes."""

from __future__ import annotations

import pytest

from app.data.db import build_connection
from app.data.generate import DEFAULT_N_USERS, SEED


@pytest.fixture(scope="session")
def con():
    """Conexão DuckDB in-memory com o dataset sintético padrão (construído 1x)."""
    connection = build_connection(n_users=DEFAULT_N_USERS, seed=SEED)
    yield connection
    connection.close()
