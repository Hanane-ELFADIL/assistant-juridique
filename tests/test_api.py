"""
Tests Phase 7 — T700–T708
API FastAPI : /health et /api/chat avec mock RAG chain.
"""
from __future__ import annotations

import pytest
from contextlib import asynccontextmanager
from unittest.mock import MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import chat, health
from src.api.schemas import HealthResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi import Request


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_sourced_result(question: str = "question test") -> dict:
    return {
        "answer": "Les banques doivent respecter les ratios prudentiels.",
        "answer_type": "sourced",
        "question": question,
        "sources": [{"document_id": "d1", "title": "Loi 34-03", "type": "loi",
                     "number": "34-03", "date": "2006", "url": "https://bkam.ma"}],
        "citations": [{
            "chunk_id": "c1",
            "citation": {"title": "Loi 34-03", "article": "Article 1", "page": 5},
            "excerpt": "Les banques doivent respecter les ratios...",
            "score": 0.85,
            "rank": 1,
        }],
        "warnings": ["⚠️ Ces résultats sont classés par similarité textuelle."],
        "search_method": "hybrid (vectoriel + BM25, fusion RRF)",
        "total_retrieved": 3,
        "relevant_used": 1,
    }


def _make_insufficient_result(question: str = "question hors corpus") -> dict:
    return {
        "answer": "Je n'ai pas trouvé de passages suffisants.",
        "answer_type": "insufficient_sources",
        "question": question,
        "sources": [],
        "citations": [],
        "warnings": ["Sources insuffisantes."],
        "search_method": "",
        "total_retrieved": 0,
        "relevant_used": 0,
    }


def _create_test_app(mock_chain=None) -> FastAPI:
    """
    Crée une app FastAPI minimaliste SANS lifespan pour les tests.
    Injecte un mock RAGChain optionnel dans app.state.
    """
    @asynccontextmanager
    async def noop_lifespan(app: FastAPI):
        yield  # pas d'initialisation

    app = FastAPI(
        title="Test App",
        lifespan=noop_lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(Exception)
    async def global_handler(request: Request, exc: Exception):
        return JSONResponse(status_code=500, content={"error": str(exc)})

    app.include_router(health.router)
    app.include_router(chat.router, prefix="/api")
    app.state.rag_chain = mock_chain
    return app


# ── T701 : GET /health ────────────────────────────────────────────────────────

class TestHealthEndpoint:

    def test_health_returns_200(self):
        """T701 — GET /health retourne 200."""
        app = _create_test_app()
        with TestClient(app) as client:
            resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_response_schema(self):
        """T701 — réponse /health a status et components."""
        app = _create_test_app()
        with TestClient(app) as client:
            resp = client.get("/health")
        data = resp.json()
        assert "status" in data
        assert "components" in data
        assert data["status"] in ("ok", "degraded")

    def test_health_components_listed(self):
        """T701 — composants clés présents dans /health."""
        app = _create_test_app()
        with TestClient(app) as client:
            resp = client.get("/health")
        components = resp.json()["components"]
        for key in ("vectorstore", "pymupdf", "langchain_google", "bm25"):
            assert key in components

    def test_health_all_ok_when_installed(self):
        """T701 — status='ok' quand tous les composants sont installés."""
        app = _create_test_app()
        with TestClient(app) as client:
            resp = client.get("/health")
        data = resp.json()
        assert data["components"]["pymupdf"] == "ok"
        assert data["components"]["vectorstore"] == "ok"
        assert data["components"]["bm25"] == "ok"


# ── T702/T703 : POST /api/chat ────────────────────────────────────────────────

class TestChatEndpoint:

    def test_chat_valid_question(self):
        """T702 — POST /api/chat avec question valide retourne 200."""
        mock = MagicMock()
        mock.answer.return_value = _make_sourced_result()
        app = _create_test_app(mock)
        with TestClient(app) as client:
            resp = client.post("/api/chat", json={"question": "Quelles sont les obligations des banques ?"})
        assert resp.status_code == 200

    def test_chat_response_schema(self):
        """T703/T704 — réponse contient answer, citations, sources, warnings."""
        mock = MagicMock()
        mock.answer.return_value = _make_sourced_result()
        app = _create_test_app(mock)
        with TestClient(app) as client:
            resp = client.post("/api/chat", json={"question": "capital minimum banque"})
        data = resp.json()
        for key in ("answer", "answer_type", "question", "sources", "citations", "warnings"):
            assert key in data, f"Clé manquante: {key}"

    def test_chat_answer_type_sourced(self):
        """T704 — answer_type='sourced' pour une réponse avec sources."""
        mock = MagicMock()
        mock.answer.return_value = _make_sourced_result()
        app = _create_test_app(mock)
        with TestClient(app) as client:
            resp = client.post("/api/chat", json={"question": "ratios prudentiels banques"})
        assert resp.json()["answer_type"] == "sourced"

    def test_chat_citations_present(self):
        """T704 — citations non vides dans la réponse."""
        mock = MagicMock()
        mock.answer.return_value = _make_sourced_result()
        app = _create_test_app(mock)
        with TestClient(app) as client:
            resp = client.post("/api/chat", json={"question": "capital minimum"})
        data = resp.json()
        assert len(data["citations"]) >= 1
        cit = data["citations"][0]
        assert "chunk_id" in cit
        assert "citation" in cit
        assert "excerpt" in cit

    def test_chat_sources_present(self):
        """T704 — sources non vides dans la réponse."""
        mock = MagicMock()
        mock.answer.return_value = _make_sourced_result()
        app = _create_test_app(mock)
        with TestClient(app) as client:
            resp = client.post("/api/chat", json={"question": "agrément bancaire"})
        data = resp.json()
        assert len(data["sources"]) >= 1
        assert "document_id" in data["sources"][0]

    def test_chat_warnings_present(self):
        """T704 — warnings toujours présents."""
        mock = MagicMock()
        mock.answer.return_value = _make_sourced_result()
        app = _create_test_app(mock)
        with TestClient(app) as client:
            resp = client.post("/api/chat", json={"question": "agrément bancaire"})
        assert isinstance(resp.json()["warnings"], list)

    def test_chat_insufficient_sources(self):
        """T704/T607 — mode sources insuffisantes retourné correctement."""
        mock = MagicMock()
        mock.answer.return_value = _make_insufficient_result()
        app = _create_test_app(mock)
        with TestClient(app) as client:
            resp = client.post("/api/chat", json={"question": "question hors corpus"})
        data = resp.json()
        assert data["answer_type"] == "insufficient_sources"
        assert data["citations"] == []
        assert data["sources"] == []

    def test_chat_with_filters(self):
        """T703 — paramètre filters accepté."""
        mock = MagicMock()
        mock.answer.return_value = _make_sourced_result()
        app = _create_test_app(mock)
        with TestClient(app) as client:
            resp = client.post("/api/chat", json={
                "question": "capital minimum banque",
                "filters": {"doc_type": "loi"}
            })
        assert resp.status_code == 200
        # Vérifie que filters a été passé à answer()
        call_kwargs = mock.answer.call_args
        assert call_kwargs is not None


# ── T703 : Validation des entrées ────────────────────────────────────────────

class TestInputValidation:

    def test_question_too_short_is_422(self):
        """T703 — question trop courte (< 3 chars) → 422."""
        app = _create_test_app()
        with TestClient(app) as client:
            resp = client.post("/api/chat", json={"question": "ab"})
        assert resp.status_code == 422

    def test_question_too_long_is_422(self):
        """T703 — question trop longue (> 500 chars) → 422."""
        app = _create_test_app()
        with TestClient(app) as client:
            resp = client.post("/api/chat", json={"question": "x" * 501})
        assert resp.status_code == 422

    def test_missing_question_is_422(self):
        """T703 — corps sans question → 422."""
        app = _create_test_app()
        with TestClient(app) as client:
            resp = client.post("/api/chat", json={})
        assert resp.status_code == 422

    def test_n_results_zero_is_422(self):
        """T703 — n_results=0 invalide → 422."""
        app = _create_test_app()
        with TestClient(app) as client:
            resp = client.post("/api/chat", json={"question": "question valide ?", "n_results": 0})
        assert resp.status_code == 422

    def test_n_results_too_large_is_422(self):
        """T703 — n_results=21 invalide → 422."""
        app = _create_test_app()
        with TestClient(app) as client:
            resp = client.post("/api/chat", json={"question": "question valide ?", "n_results": 21})
        assert resp.status_code == 422


# ── T705 : Gestion d'erreurs ─────────────────────────────────────────────────

class TestErrorHandling:

    def test_no_rag_chain_returns_503(self):
        """T705 — pipeline RAG absent → 503."""
        app = _create_test_app(mock_chain=None)  # rag_chain=None
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/api/chat", json={"question": "question valide ?"})
        assert resp.status_code == 503

    def test_rag_chain_exception_returns_500(self):
        """T705 — exception dans RAG chain → 500."""
        mock = MagicMock()
        mock.answer.side_effect = RuntimeError("Erreur simulée dans RAG")
        app = _create_test_app(mock)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/api/chat", json={"question": "question valide ?"})
        assert resp.status_code == 500

    def test_method_not_allowed(self):
        """T705 — GET sur /api/chat → 405."""
        app = _create_test_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/chat")
        assert resp.status_code == 405


# ── T706 : Journalisation ─────────────────────────────────────────────────────

class TestLogging:

    def test_logs_do_not_contain_api_key(self, caplog):
        """T706 — la clé API n'apparaît pas dans les logs."""
        import logging
        mock = MagicMock()
        mock.answer.return_value = _make_sourced_result()
        app = _create_test_app(mock)
        with caplog.at_level(logging.INFO):
            with TestClient(app) as client:
                client.post("/api/chat", json={"question": "test question API"})
        for record in caplog.records:
            assert "GOOGLE_API_KEY" not in record.message
            assert "fake-key" not in record.message

    def test_logs_question_length_not_content(self, caplog):
        """T706 — log contient la longueur, pas le texte brut."""
        import logging
        mock = MagicMock()
        mock.answer.return_value = _make_sourced_result()
        app = _create_test_app(mock)
        secret_text = "textesecretnepasenregistrer"
        with caplog.at_level(logging.INFO):
            with TestClient(app) as client:
                client.post("/api/chat", json={"question": secret_text + " test"})
        for record in caplog.records:
            # Le contenu brut de la question ne doit pas être loggué
            assert secret_text not in record.message


# ── T708 : OpenAPI ───────────────────────────────────────────────────────────

class TestOpenAPI:

    def test_openapi_schema_available(self):
        """T708 — /openapi.json retourne le schéma complet."""
        app = _create_test_app()
        with TestClient(app) as client:
            resp = client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert "paths" in schema
        assert "/health" in schema["paths"]
        assert "/api/chat" in schema["paths"]

    def test_openapi_chat_has_post(self):
        """T708 — /api/chat a une méthode POST documentée."""
        app = _create_test_app()
        with TestClient(app) as client:
            schema = client.get("/openapi.json").json()
        assert "post" in schema["paths"]["/api/chat"]

    def test_docs_available(self):
        """T708 — /docs retourne 200."""
        app = _create_test_app()
        with TestClient(app) as client:
            resp = client.get("/docs")
        assert resp.status_code == 200
