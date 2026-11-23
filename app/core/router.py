"""IntentRouter: mapeia a pergunta em linguagem natural para um ``MetricSpec``.

Determinístico, sem LLM. Para cada sinônimo de cada métrica calcula a fração de
tokens do sinônimo presentes na pergunta (normalizada: minúsculas, sem acentos,
sem stopwords). Frase contígua conta como cobertura total; token com o mesmo
radical (prefixo comum >= ``STEM_LEN``) conta parcialmente. O score da métrica é
o melhor score entre seus sinônimos.

- score < ``threshold`` → sem match (resposta honesta, nunca um chute);
- empate entre métricas diferentes → ambíguo, também sem match.

A pergunta é usada **apenas** aqui; ela nunca chega ao SQL.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from app.core.models import MetricSpec
from app.core.registry import MetricRegistry

DEFAULT_THRESHOLD = 0.6
STEM_LEN = 5
STEM_WEIGHT = 0.8
TIE_EPSILON = 1e-9

STOPWORDS = frozenset(
    """
    a o as os um uma uns umas de da do das dos em no na nos nas e ou
    para por pra pro com sem que qual quais quanto quantos quanta quantas
    como foi eh esta sao ser ter tem temos tivemos nosso nossa meu minha
    me mostre mostra mostrar ver veja quero saber sobre ao aos
    the of in on and or what is are was how show my our to for
    """.split()
)


def normalize(text: str) -> str:
    """Minúsculas, sem acentos, só ``[a-z0-9]`` separados por espaço."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def tokenize(text: str) -> list[str]:
    return [t for t in normalize(text).split() if t not in STOPWORDS]


def _token_score(token: str, question_tokens: set[str]) -> float:
    if token in question_tokens:
        return 1.0
    if len(token) >= STEM_LEN:
        stem = token[:STEM_LEN]
        if any(len(q) >= STEM_LEN and q.startswith(stem) for q in question_tokens):
            return STEM_WEIGHT
    return 0.0


def synonym_score(synonym: str, question: str) -> float:
    """Cobertura do sinônimo pela pergunta, em [0, 1]."""
    syn_tokens = tokenize(synonym)
    if not syn_tokens:
        return 0.0
    q_tokens = tokenize(question)
    padded = f" {' '.join(q_tokens)} "
    if f" {' '.join(syn_tokens)} " in padded:
        return 1.0
    q_set = set(q_tokens)
    return sum(_token_score(t, q_set) for t in syn_tokens) / len(syn_tokens)


@dataclass(frozen=True)
class Candidate:
    name: str
    score: float
    specificity: int  # nº de tokens do sinônimo vencedor (desempate)
    synonym: str


@dataclass(frozen=True)
class RouteResult:
    spec: MetricSpec | None
    confidence: float
    candidates: list[Candidate] = field(default_factory=list)
    ambiguous: bool = False

    @property
    def matched(self) -> bool:
        return self.spec is not None


class IntentRouter:
    """Roteador por keywords/sinônimos com score e limiar."""

    def __init__(
        self, registry: MetricRegistry, threshold: float = DEFAULT_THRESHOLD
    ) -> None:
        if not 0 < threshold <= 1:
            raise ValueError("threshold deve estar em (0, 1]")
        self.registry = registry
        self.threshold = threshold

    def score(self, question: str) -> list[Candidate]:
        """Score de cada métrica, do melhor para o pior."""
        candidates = []
        for spec in self.registry:
            best = max(
                (
                    (synonym_score(s, question), len(tokenize(s)), s)
                    for s in spec.synonyms
                ),
                key=lambda t: (t[0], t[1]),
            )
            candidates.append(Candidate(spec.name, round(best[0], 4), best[1], best[2]))
        return sorted(candidates, key=lambda c: (c.score, c.specificity), reverse=True)

    def route(self, question: str) -> RouteResult:
        candidates = self.score(question)
        top = candidates[0] if candidates else None
        if top is None or top.score < self.threshold:
            return RouteResult(None, top.score if top else 0.0, candidates)

        runner_up = candidates[1] if len(candidates) > 1 else None
        if (
            runner_up is not None
            and abs(runner_up.score - top.score) <= TIE_EPSILON
            and runner_up.specificity == top.specificity
        ):
            return RouteResult(None, top.score, candidates, ambiguous=True)

        return RouteResult(self.registry.get(top.name), top.score, candidates)
