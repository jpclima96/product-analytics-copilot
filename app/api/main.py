"""API FastAPI do Product Analytics Copilot.

Endpoints:
- ``POST /ask``     — pergunta em linguagem natural → ``AskResponse``
- ``GET  /metrics`` — métricas disponíveis (whitelist)
- ``GET  /health``  — status

Configuração por variáveis de ambiente:
- ``PAC_DB_PATH``      — arquivo DuckDB (default ``app/data/warehouse.duckdb``);
  se não existir é gerado **na inicialização** (nunca no caminho de request).
- ``PAC_CORS_ORIGINS`` — origens permitidas, separadas por vírgula
  (default ``http://localhost:8501``, a UI Streamlit).

Uso: ``uvicorn app.api.main:app``
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.copilot import Copilot
from app.core.engine import QueryEngine, QueryTimeoutError
from app.core.models import AskRequest, AskResponse, MetricInfo
from app.core.registry import default_registry
from app.data.db import DEFAULT_DB_PATH, write_duckdb

logger = logging.getLogger("pac.api")

DEFAULT_CORS_ORIGINS = "http://localhost:8501,http://127.0.0.1:8501"


def _cors_origins() -> list[str]:
    raw = os.environ.get("PAC_CORS_ORIGINS", DEFAULT_CORS_ORIGINS)
    return [o.strip() for o in raw.split(",") if o.strip()]


def create_app(db_path: str | Path | None = None) -> FastAPI:
    """Fábrica da aplicação (``db_path`` explícito facilita os testes)."""
    path = Path(db_path or os.environ.get("PAC_DB_PATH") or DEFAULT_DB_PATH)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if not path.exists():
            logger.info("Gerando dataset sintético em %s", path)
            write_duckdb(path)
        engine = QueryEngine.open(path)  # read-only
        app.state.copilot = Copilot(default_registry(), engine)
        try:
            yield
        finally:
            engine.close()

    app = FastAPI(
        title="Product Analytics Copilot",
        version="0.1.0",
        description=(
            "Perguntas em linguagem natural sobre métricas de produto, "
            "respondidas a partir de SQL parametrizado e auditável."
        ),
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(QueryTimeoutError)
    async def _timeout(_: Request, exc: QueryTimeoutError) -> JSONResponse:
        logger.warning("Timeout: %s", exc)
        return JSONResponse(
            status_code=504,
            content={"detail": "A consulta demorou demais. Tente novamente."},
        )

    @app.exception_handler(Exception)
    async def _internal(_: Request, exc: Exception) -> JSONResponse:
        # Loga o detalhe no servidor; o cliente não vê schema nem stack trace.
        logger.exception("Erro ao processar requisição", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Erro interno ao processar a pergunta."},
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/metrics", response_model=list[MetricInfo])
    def metrics(request: Request) -> list[MetricInfo]:
        return request.app.state.copilot.registry.describe()

    @app.post("/ask", response_model=AskResponse)
    def ask(body: AskRequest, request: Request) -> AskResponse:
        return request.app.state.copilot.ask(body.question)

    return app


app = create_app()
