"""
Interface interchangeable pour les embeddings — T400, T401.
Supporte Google Embeddings API (par défaut) et peut être étendu.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Protocol

logger = logging.getLogger(__name__)

# Version de l'interface — à incrémenter si le schéma de l'index change (T407)
EMBEDDING_INTERFACE_VERSION = "1.0"


class EmbeddingProvider(ABC):
    """Interface abstraite pour les fournisseurs d'embeddings (T400)."""

    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        Génère les embeddings pour une liste de textes.
        
        Args:
            texts: Liste de textes à vectoriser.
        
        Returns:
            Liste de vecteurs (liste de floats).
        """
        ...

    @abstractmethod
    def embed_query(self, query: str) -> list[float]:
        """
        Génère l'embedding pour une requête utilisateur.
        (Certains modèles distinguent document et requête.)
        """
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Nom du modèle d'embeddings utilisé."""
        ...

    @property
    @abstractmethod
    def embedding_dimension(self) -> int:
        """Dimension des vecteurs produits."""
        ...


class GoogleEmbeddingProvider(EmbeddingProvider):
    """
    Fournisseur d'embeddings Google via LangChain (T401).
    Modèle : text-embedding-004 (multilingue FR/AR).
    """

    def __init__(self, model_name: str = "models/text-embedding-004", api_key: str = ""):
        self._model_name = model_name
        self._api_key = api_key
        self._embeddings = None

    def _get_embeddings(self):
        if self._embeddings is None:
            try:
                from langchain_google_genai import GoogleGenerativeAIEmbeddings
            except ImportError:
                raise ImportError(
                    "langchain-google-genai requis. "
                    "Exécutez : pip install langchain-google-genai"
                )
            self._embeddings = GoogleGenerativeAIEmbeddings(
                model=self._model_name,
                google_api_key=self._api_key or None,
                task_type="retrieval_document",
            )
        return self._embeddings

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Génère les embeddings pour un corpus de documents."""
        if not texts:
            return []
        embeddings_obj = self._get_embeddings()
        # Utilise task_type retrieval_document pour l'indexation
        embeddings_obj.task_type = "retrieval_document"
        return embeddings_obj.embed_documents(texts)

    def embed_query(self, query: str) -> list[float]:
        """Génère l'embedding pour une requête (task_type différent)."""
        embeddings_obj = self._get_embeddings()
        embeddings_obj.task_type = "retrieval_query"
        return embeddings_obj.embed_query(query)

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def embedding_dimension(self) -> int:
        return 768  # text-embedding-004 dimension


def get_embedding_provider(settings=None) -> EmbeddingProvider:
    """
    Factory : retourne le fournisseur d'embeddings configuré.
    Configurable via EMBEDDING_MODEL dans .env.
    """
    if settings is None:
        from src.config import get_settings
        settings = get_settings()

    model = settings.embedding_model
    api_key = settings.google_api_key

    if not api_key:
        logger.warning(
            "GOOGLE_API_KEY non définie — les embeddings échoueront. "
            "Définissez GOOGLE_API_KEY dans votre fichier .env."
        )

    logger.info("Fournisseur d'embeddings : Google (%s)", model)
    return GoogleEmbeddingProvider(model_name=model, api_key=api_key)
