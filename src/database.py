"""
Connexion SQLAlchemy et initialisation de la base de données SQLite.
"""
from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.config import get_settings


class Base(DeclarativeBase):
    """Classe de base pour tous les modèles SQLAlchemy."""
    pass


def _get_engine():
    settings = get_settings()
    settings.ensure_dirs()
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},  # SQLite uniquement
        echo=settings.api_debug,
    )
    # Activer les foreign keys pour SQLite
    if "sqlite" in settings.database_url:
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_conn, _connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return engine


_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = _get_engine()
    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=get_engine(),
        )
    return _SessionLocal


def init_db() -> None:
    """Crée toutes les tables si elles n'existent pas."""
    # Import des modèles pour que SQLAlchemy les connaisse
    from src.models import document, chunk  # noqa: F401
    Base.metadata.create_all(bind=get_engine())


def get_db() -> Session:
    """Générateur de session pour FastAPI Depends."""
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
