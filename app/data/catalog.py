"""Acesso ao catálogo de métricas (YAML) e ao SQL versionado por métrica."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

_HERE = Path(__file__).resolve().parent
CATALOG_PATH = _HERE / "catalog.yml"
SQL_DIR = _HERE / "sql"


@lru_cache(maxsize=1)
def load_catalog() -> dict:
    """Carrega e cacheia o catálogo de métricas."""
    with open(CATALOG_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def metric_names() -> list[str]:
    return list(load_catalog()["metrics"].keys())


def get_metric(name: str) -> dict:
    """Retorna a spec de uma métrica ou levanta KeyError (whitelist)."""
    metrics = load_catalog()["metrics"]
    if name not in metrics:
        raise KeyError(f"Métrica desconhecida: {name!r}. Disponíveis: {list(metrics)}")
    return metrics[name]


def read_sql(name: str) -> str:
    """Lê o SQL versionado (``sql/<metric>/v<version>.sql``) da métrica."""
    spec = get_metric(name)
    version = spec["version"]
    path = SQL_DIR / name / f"v{version}.sql"
    if not path.exists():
        raise FileNotFoundError(f"SQL não encontrado para {name} v{version}: {path}")
    return path.read_text(encoding="utf-8")
