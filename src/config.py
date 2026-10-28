"""
Configuration centralisée — chargée depuis les variables d'environnement.
Utilise pydantic-settings pour la validation et le typage.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Racine du projet = parent du répertoire src/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """Paramètres de l'application chargés depuis .env ou l'environnement."""

    model_config = SettingsConfigDict(
        # Chemin absolu vers .env à la racine du projet
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # === LLM & Embeddings ===
    google_api_key: str = Field(default="", description="Clé API Google Gemini")
    gemini_model: str = Field(default="gemini-1.5-flash", description="Modèle Gemini pour la génération")
    embedding_model: str = Field(
        default="models/text-embedding-004",
        description="Modèle d'embeddings Google",
    )

    # === Base de données ===
    database_url: str = Field(
        default="sqlite:///./data/bam_rag.db",
        description="URL de connexion SQLAlchemy",
    )

    # === Vectorstore ===
    chroma_persist_dir: str = Field(default="./data/chroma_db")
    chroma_collection_name: str = Field(default="bam_legal_chunks")
    # SQLite vectorstore (backend actif pour le MVP)
    vector_db_dir: str = Field(default="./data/vector_db")
    vector_collection_name: str = Field(default="bam_legal_chunks")

    # === Chemins ===
    data_raw_dir: str = Field(default="./data/raw")
    data_processed_dir: str = Field(default="./data/processed")

    # === API ===
    api_host: str = Field(default="127.0.0.1")
    api_port: int = Field(default=8000)
    api_debug: bool = Field(default=False)

    # === Limites ===
    max_pdf_size_mb: int = Field(default=50, ge=1, le=500)
    max_query_length: int = Field(default=500, ge=10, le=2000)
    max_context_chunks: int = Field(default=8, ge=1, le=20)
    retrieval_top_k: int = Field(default=10, ge=1, le=50)

    # === Logging ===
    log_level: str = Field(default="INFO")
    log_dir: str = Field(default="./logs")

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in allowed:
            raise ValueError(f"log_level doit être l'un de {allowed}")
        return v.upper()

    @property
    def raw_dir(self) -> Path:
        return Path(self.data_raw_dir)

    @property
    def processed_dir(self) -> Path:
        return Path(self.data_processed_dir)

    @property
    def chroma_dir(self) -> Path:
        return Path(self.chroma_persist_dir)

    @property
    def log_path(self) -> Path:
        return Path(self.log_dir)

    def ensure_dirs(self) -> None:
        """Crée les répertoires nécessaires s'ils n'existent pas."""
        for d in [self.raw_dir, self.processed_dir, self.chroma_dir, self.log_path]:
            d.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retourne l'instance singleton des paramètres (mise en cache)."""
    return Settings()
