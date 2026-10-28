"""
Application FastAPI principale — T700, T708.
"""
from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.routes import chat, health
from src.config import get_settings

# === Logging ===
def setup_logging(settings) -> None:
    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    handlers = [logging.StreamHandler(sys.stdout)]
    try:
        handlers.append(
            logging.FileHandler(log_dir / "app.log", encoding="utf-8")
        )
    except Exception:
        pass
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )


logger = logging.getLogger(__name__)


# === Lifecycle ===
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialisation et nettoyage des ressources au démarrage/arrêt."""
    settings = get_settings()
    setup_logging(settings)
    settings.ensure_dirs()
    logger.info("Démarrage de l'assistant juridique BAM RAG...")

    # Initialisation de la base de données
    try:
        from src.database import init_db
        init_db()
        logger.info("Base de données initialisée.")
    except Exception as e:
        logger.error("Erreur initialisation BDD : %s", e)

    # Initialisation du pipeline RAG (si possible)
    try:
        from src.embeddings.provider import get_embedding_provider
        from src.vectorstore.sqlite_store import SQLiteVectorStore
        from src.retrieval.bm25_index import BM25Index
        from src.retrieval.hybrid_search import HybridSearch
        from src.generation.rag_chain import RAGChain

        provider = get_embedding_provider(settings)
        vector_store = SQLiteVectorStore(provider)
        # Précharger le cache vectoriel au démarrage (évite le délai à la première requête)
        try:
            vector_store._load_cache()
            logger.info("Cache vectoriel chargé : %d chunks.", vector_store.count())
        except Exception as e:
            logger.warning("Cache vectoriel non chargé au démarrage : %s", e)
        bm25_index = BM25Index()
        hybrid = HybridSearch(vector_store, bm25_index, top_k=settings.retrieval_top_k)
        rag_chain = RAGChain(hybrid, settings)

        app.state.rag_chain = rag_chain
        app.state.vector_store = vector_store
        app.state.bm25_index = bm25_index
        logger.info("Pipeline RAG initialisé.")
    except Exception as e:
        logger.warning("Pipeline RAG non disponible au démarrage : %s", e)
        app.state.rag_chain = None

    yield

    logger.info("Arrêt de l'application.")


# === Application ===
def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Assistant Juridique RAG — Bank Al-Maghrib",
        description=(
            "API de recherche documentaire sur les textes législatifs et réglementaires "
            "de Bank Al-Maghrib. Les réponses sont fondées uniquement sur les documents indexés."
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # CORS — restreint à localhost pour le MVP
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    # Gestion globale des erreurs (T705)
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error("Erreur non gérée : %s", exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": "Erreur interne du serveur.", "status_code": 500},
        )

    # Routes
    app.include_router(health.router)
    app.include_router(chat.router, prefix="/api")

    return app


app = create_app()
