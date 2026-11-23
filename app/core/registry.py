"""MetricRegistry: a whitelist de métricas como objetos ``MetricSpec``.

Cada ``MetricSpec`` é montado a partir do catálogo (`app/data/catalog.yml`) e do
SQL versionado (`app/data/sql/<nome>/v<version>.sql`). Não existe outro caminho
para uma métrica entrar no sistema: o que não está aqui não é respondido.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from app.core.models import MetricInfo, MetricSpec
from app.data.catalog import load_catalog, read_sql


class MetricRegistry:
    """Coleção imutável de ``MetricSpec`` indexada por nome."""

    def __init__(self, specs: list[MetricSpec]) -> None:
        self._specs: dict[str, MetricSpec] = {}
        for spec in specs:
            if spec.name in self._specs:
                raise ValueError(f"Métrica duplicada: {spec.name}")
            self._specs[spec.name] = spec

    @classmethod
    def from_catalog(cls) -> MetricRegistry:
        """Constrói a registry a partir do catálogo versionado."""
        specs = []
        for name, entry in load_catalog()["metrics"].items():
            specs.append(
                MetricSpec(
                    name=name,
                    version=entry["version"],
                    title=entry["title"],
                    definition=" ".join(entry["definition"].split()),
                    sql=read_sql(name),
                    synonyms=tuple(entry["synonyms"]),
                    visualization=entry["visualization"],
                    value_column=entry["value_column"],
                    value_row=entry.get("value_row", "first"),
                    answer_template=" ".join(entry["answer_template"].split()),
                    default_params=entry.get("default_params") or {},
                    allowed_dimensions=tuple(entry.get("allowed_dimensions") or ()),
                )
            )
        return cls(specs)

    def get(self, name: str) -> MetricSpec:
        """Retorna a métrica ``name`` ou levanta ``KeyError`` (whitelist)."""
        try:
            return self._specs[name]
        except KeyError:
            raise KeyError(
                f"Métrica desconhecida: {name!r}. Disponíveis: {self.names()}"
            ) from None

    def names(self) -> list[str]:
        return list(self._specs)

    def __iter__(self) -> Iterator[MetricSpec]:
        return iter(self._specs.values())

    def __len__(self) -> int:
        return len(self._specs)

    def __contains__(self, name: object) -> bool:
        return name in self._specs

    def describe(self) -> list[MetricInfo]:
        """Resumo público das métricas (sem SQL), para ``GET /metrics``."""
        return [
            MetricInfo(
                name=s.name,
                title=s.title,
                definition=s.definition,
                synonyms=list(s.synonyms),
                visualization=s.visualization,
            )
            for s in self
        ]


@lru_cache(maxsize=1)
def default_registry() -> MetricRegistry:
    """Registry padrão (cacheada) construída a partir do catálogo."""
    return MetricRegistry.from_catalog()
