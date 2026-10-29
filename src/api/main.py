"""Application FastAPI — RAG juridique BAM avec Auth, Historique, Favoris."""
from __future__ import annotations
import logging, sys
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from src.api.routes import chat, health
from src.config import get_settings

def setup_logging(settings):
    Path(settings.log_dir).mkdir(parents=True, exist_ok=True)
    handlers = [logging.StreamHandler(sys.stdout)]
    try:
        handlers.append(logging.FileHandler(Path(settings.log_dir)/"app.log", encoding="utf-8"))
    except Exception:
        pass
    logging.basicConfig(level=getattr(logging, settings.log_level, logging.INFO),
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                        handlers=handlers)

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings)
    settings.ensure_dirs()
    logger.info("Démarrage BAM RAG...")

    # Base de données (inclut les nouveaux modèles User/Conversation/Favorite)
    try:
        from src.database import init_db
        init_db()
        logger.info("BDD initialisée.")
    except Exception as e:
        logger.error("Erreur BDD : %s", e)

    # Pipeline RAG
    try:
        from src.embeddings.provider import get_embedding_provider
        from src.vectorstore.sqlite_store import SQLiteVectorStore
        from src.retrieval.bm25_index import BM25Index
        from src.retrieval.hybrid_search import HybridSearch
        from src.generation.rag_chain import RAGChain

        provider = get_embedding_provider(settings)
        vector_store = SQLiteVectorStore(provider)

        # Préchargement cache vectoriel
        try:
            vector_store._load_cache()
            logger.info("Cache vectoriel : %d chunks.", vector_store.count())
        except Exception as e:
            logger.warning("Cache vectoriel : %s", e)

        # BM25 depuis la BDD
        bm25_index = BM25Index()
        try:
            from src.database import get_session_factory, init_db
            from src.models.chunk import Chunk as ChunkModel
            db_s = get_session_factory()()
            chunks_db = db_s.query(ChunkModel).all()
            if chunks_db:
                bm25_index.build([c.chunk_id for c in chunks_db],
                                  [c.text for c in chunks_db],
                                  [c.to_metadata_dict() for c in chunks_db])
                logger.info("BM25 : %d chunks.", bm25_index.size)
            db_s.close()
        except Exception as e:
            logger.warning("BM25 : %s", e)

        hybrid = HybridSearch(vector_store, bm25_index, top_k=settings.retrieval_top_k)
        rag_chain = RAGChain(hybrid, settings)
        app.state.rag_chain = rag_chain
        app.state.vector_store = vector_store
        app.state.bm25_index = bm25_index
        logger.info("Pipeline RAG prêt.")
    except Exception as e:
        logger.warning("Pipeline RAG non disponible : %s", e)
        app.state.rag_chain = None

    yield
    logger.info("Arrêt.")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Assistant Juridique BAM", version="2.0.0",
                  docs_url="/docs", redoc_url="/redoc",
                  openapi_url="/openapi.json", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:3001",
                       "http://127.0.0.1:3000", "http://127.0.0.1:3001"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def global_exc(request: Request, exc: Exception):
        logger.error("Erreur non gérée : %s", exc, exc_info=True)
        return JSONResponse(status_code=500, content={"error": "Erreur interne."})

    # Routes
    app.include_router(health.router)
    app.include_router(chat.router, prefix="/api")

    # Auth + Historique + Favoris
    from src.api.routes.auth_routes import router as auth_router
    from src.api.routes.history_routes import router as hist_router
    app.include_router(auth_router)
    app.include_router(hist_router)

    return app

app = create_app()
