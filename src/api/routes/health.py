"""
Endpoint /health détaillé — T701.
"""
from __future__ import annotations
from fastapi import APIRouter, Request
from src.api.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check(request: Request) -> HealthResponse:
    """État détaillé de tous les composants."""
    components: dict[str, str] = {}

    # SQLite vectorstore
    try:
        from src.vectorstore.sqlite_store import SQLiteVectorStore
        components["vectorstore"] = "ok"
    except ImportError:
        components["vectorstore"] = "not_installed"

    # PyMuPDF
    try:
        import pymupdf
        components["pymupdf"] = "ok"
    except ImportError:
        components["pymupdf"] = "not_installed"

    # LangChain Google
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        components["langchain_google"] = "ok"
    except ImportError:
        components["langchain_google"] = "not_installed"

    # BM25
    try:
        from rank_bm25 import BM25Okapi
        components["bm25"] = "ok"
    except ImportError:
        components["bm25"] = "not_installed"

    # Chunks indexés (depuis app.state si disponible)
    rag = getattr(request.app.state, "rag_chain", None)
    if rag and hasattr(rag, "_search"):
        try:
            vs = rag._search._vector_store
            components["chunks_indexed"] = str(vs.count())
        except Exception:
            components["chunks_indexed"] = "unknown"

        try:
            bm25 = rag._search._bm25
            components["bm25_size"] = str(bm25.size)
        except Exception:
            components["bm25_size"] = "unknown"

    all_ok = all(v in ("ok",) or v.isdigit() for v in components.values())
    return HealthResponse(
        status="ok" if all_ok else "degraded",
        components=components,
    )
