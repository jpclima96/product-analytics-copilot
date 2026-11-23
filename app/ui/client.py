"""Cliente HTTP mínimo da API, usado pela UI Streamlit."""

from __future__ import annotations

import os
from typing import Any

import requests

API_URL = os.environ.get("PAC_API_URL", "http://localhost:8000").rstrip("/")
TIMEOUT_S = 30


class ApiError(RuntimeError):
    """Falha ao falar com a API (mensagem segura para exibir ao usuário)."""


def _request(method: str, path: str, **kwargs: Any) -> Any:
    try:
        resp = requests.request(method, f"{API_URL}{path}", timeout=TIMEOUT_S, **kwargs)
    except requests.RequestException as exc:
        raise ApiError(f"Não foi possível conectar à API em {API_URL}.") from exc
    if resp.status_code == 422:
        raise ApiError("Pergunta inválida: use entre 1 e 500 caracteres.")
    if resp.status_code >= 400:
        detail = resp.json().get("detail", "Erro na API.")
        raise ApiError(str(detail))
    return resp.json()


def fetch_metrics() -> list[dict[str, Any]]:
    return _request("GET", "/metrics")


def ask(question: str) -> dict[str, Any]:
    return _request("POST", "/ask", json={"question": question})
