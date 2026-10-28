"""
Endpoint de santé — T701.
"""
from __future__ import annotations

from fastapi import APIRouter

from src.api.schemas import HealthResponse

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Vérification de l'état du service",
    tags=["System"],
)
async def health_check() -> HealthResponse:
    """
    Vérifie que l'API est en ligne.
    Retourne l'état des composants principaux.
    """
    components: dict[str, str] = {}

    # Vérification SQLite vectorstore
    try:
        from src.vectorstore.sqlite_store import SQLiteVectorStore  # type: ignore
        components["vectorstore"] = "ok"
    except ImportError:
        components["vectorstore"] = "not_installed"

    # Vérification PyMuPDF
    try:
        import pymupdf  # type: ignore
        components["pymupdf"] = "ok"
    except ImportError:
        components["pymupdf"] = "not_installed"

    # Vérification LangChain Google
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI  # type: ignore
        components["langchain_google"] = "ok"
    except ImportError:
        components["langchain_google"] = "not_installed"

    # Vérification BM25
    try:
        from rank_bm25 import BM25Okapi  # type: ignore
        components["bm25"] = "ok"
    except ImportError:
        components["bm25"] = "not_installed"

    all_ok = all(v == "ok" for v in components.values())
    return HealthResponse(
        status="ok" if all_ok else "degraded",
        components=components,
    )
