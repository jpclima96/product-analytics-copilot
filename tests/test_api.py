"""Testes da API FastAPI com TestClient: /ask, /metrics, /health."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.core.models import AskResponse


@pytest.fixture(scope="module")
def client(db_path):
    with TestClient(create_app(db_path)) as c:
        yield c


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_metrics_lists_whitelist_without_sql(client, registry):
    body = client.get("/metrics").json()
    assert {m["name"] for m in body} == set(registry.names())
    assert all("sql" not in m for m in body)
    assert all(m["definition"] for m in body)


def test_ask_matched_returns_full_contract(client):
    resp = client.post("/ask", json={"question": "Qual a taxa de ativação?"})
    assert resp.status_code == 200
    body = AskResponse.model_validate(resp.json())
    assert body.matched
    assert body.metric == "activation_rate"
    assert body.value == pytest.approx(0.5054)
    assert body.sql and body.definition and body.table and body.chart


def test_ask_unmatched_is_honest(client):
    body = client.post("/ask", json={"question": "qual a receita?"}).json()
    assert body["matched"] is False
    assert body["value"] is None
    assert body["sql"] is None


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"question": ""},
        {"question": "x" * 501},
        {"question": 123},
        {"question": "ativação", "sql": "SELECT 1"},
    ],
)
def test_ask_rejects_invalid_input(client, payload):
    assert client.post("/ask", json=payload).status_code == 422


def test_injection_in_question_is_never_executed(client):
    resp = client.post(
        "/ask", json={"question": "ativação'; DROP TABLE users; --"}
    ).json()
    # A pergunta só serve para roteamento: a métrica roda normalmente e o SQL
    # devolvido é o template da registry, sem o texto do usuário.
    assert resp["metric"] == "activation_rate"
    assert "DROP" not in resp["sql"]
    again = client.post("/ask", json={"question": "taxa de ativação"}).json()
    assert again["value"] == resp["value"]


def test_cors_allows_only_configured_origin(client):
    ok = client.options(
        "/ask",
        headers={
            "Origin": "http://localhost:8501",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:8501"
    denied = client.options(
        "/ask",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in denied.headers


def test_internal_errors_do_not_leak_details(db_path):
    app = create_app(db_path)
    with TestClient(app, raise_server_exceptions=False) as c:

        class Boom:
            def ask(self, question):
                raise RuntimeError("Catalog Error: Table events_secret does not exist")

        app.state.copilot = Boom()
        resp = c.post("/ask", json={"question": "ativação"})
    assert resp.status_code == 500
    assert resp.json() == {"detail": "Erro interno ao processar a pergunta."}
    assert "events_secret" not in resp.text


def test_query_timeout_returns_504(db_path):
    from app.core.engine import QueryTimeoutError

    app = create_app(db_path)
    with TestClient(app) as c:

        class Slow:
            def ask(self, question):
                raise QueryTimeoutError("Consulta excedeu 10s")

        app.state.copilot = Slow()
        resp = c.post("/ask", json={"question": "ativação"})
    assert resp.status_code == 504
