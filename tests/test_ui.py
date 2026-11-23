"""Smoke tests da UI Streamlit (AppTest), com a API real via TestClient."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from app.api.main import create_app
from app.ui import client as ui_client

APP_FILE = str(Path(__file__).resolve().parents[1] / "app" / "ui" / "streamlit_app.py")


@pytest.fixture(scope="module")
def api(db_path):
    with TestClient(create_app(db_path)) as c:
        yield c


@pytest.fixture
def wired(api, monkeypatch):
    """Faz o cliente da UI falar com a API em processo."""

    def _request(method, path, **kwargs):
        resp = api.request(method, path, **kwargs)
        if resp.status_code >= 400:
            raise ui_client.ApiError(resp.json().get("detail", "Erro"))
        return resp.json()

    monkeypatch.setattr(ui_client, "_request", _request)


def _run_question(question: str) -> AppTest:
    at = AppTest.from_file(APP_FILE, default_timeout=30).run()
    at.text_input(key="question").input(question)
    at.button[-1].click().run()  # botão "Perguntar" do formulário
    return at


def test_app_renders_without_errors(wired):
    at = AppTest.from_file(APP_FILE, default_timeout=30).run()
    assert not at.exception
    assert "Product Analytics Copilot" in at.title[0].value
    assert len(at.sidebar.expander) == 4


def test_matched_question_shows_answer_sql_and_definition(wired):
    at = _run_question("Qual a taxa de ativação?")
    assert not at.exception
    assert "taxa de ativação" in at.success[0].value
    assert any("SELECT" in c.value for c in at.code)
    assert at.get("plotly_chart")  # KPI renderizado como gráfico indicador


def test_unmatched_question_shows_honest_warning(wired):
    at = _run_question("qual a receita?")
    assert not at.exception
    assert "Não sei" in at.warning[0].value
    assert not at.code


def test_api_down_shows_error(monkeypatch):
    def _down(method, path, **kwargs):
        raise ui_client.ApiError("Não foi possível conectar à API.")

    monkeypatch.setattr(ui_client, "_request", _down)
    at = _run_question("Qual a taxa de ativação?")
    assert not at.exception
    assert at.error
