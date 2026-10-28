"""
Interface interchangeable pour les embeddings — T400, T401.
Supporte Google Embeddings API et un provider local rapide.
"""
from __future__ import annotations

import hashlib
import logging
import math
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)
EMBEDDING_INTERFACE_VERSION = "1.0"


class EmbeddingProvider(ABC):
    """Interface abstraite pour les fournisseurs d'embeddings (T400)."""

    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...

    @abstractmethod
    def embed_query(self, query: str) -> list[float]: ...

    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @property
    @abstractmethod
    def embedding_dimension(self) -> int: ...


class LocalHashEmbeddingProvider(EmbeddingProvider):
    """
    Embeddings locaux ultra-rapides — aucune clé API, aucun téléchargement.
    Bag-of-words + hashing MD5 pur Python. Dim=64.
    <1ms par texte. Qualité moindre mais fonctionnel immédiatement.
    """
    DIM = 64

    def _hash_text(self, text: str) -> list[float]:
        vec = [0.0] * self.DIM
        tokens = text.lower().split()
        if not tokens:
            return vec
        for token in tokens:
            h = int(hashlib.md5(token.encode()).hexdigest(), 16)
            idx = h % self.DIM
            sign = 1.0 if (h >> 64) % 2 == 0 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._hash_text(t) for t in texts]

    def embed_query(self, query: str) -> list[float]:
        return self._hash_text(query)

    @property
    def model_name(self) -> str:
        return "hash-bow-local-64"

    @property
    def embedding_dimension(self) -> int:
        return self.DIM


# Alias pour rétrocompatibilité
TFIDFEmbeddingProvider = LocalHashEmbeddingProvider


class GoogleEmbeddingProvider(EmbeddingProvider):
    """
    Embeddings Google via SDK natif google-genai.
    Modèle : gemini-embedding-001 (multilingue FR/AR). Dim=3072.
    Nécessite GOOGLE_API_KEY valide et quota API suffisant.
    """
    def __init__(self, model_name: str = "models/gemini-embedding-001", api_key: str = ""):
        self._model_name = model_name
        self._api_key = api_key
        self._client = None

    def _get_client(self):
        if self._client is None:
            import google.genai as genai
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        import google.genai.types as types
        client = self._get_client()
        result = client.models.embed_content(
            model=self._model_name,
            contents=texts,
            config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
        )
        return [e.values for e in result.embeddings]

    def embed_query(self, query: str) -> list[float]:
        import google.genai.types as types
        client = self._get_client()
        result = client.models.embed_content(
            model=self._model_name,
            contents=[query],
            config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
        )
        return result.embeddings[0].values

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def embedding_dimension(self) -> int:
        return 3072


def get_embedding_provider(settings=None) -> EmbeddingProvider:
    """
    Factory : retourne le bon provider selon la config.
    EMBEDDING_MODEL=local  → LocalHashEmbeddingProvider (rapide, sans API)
    EMBEDDING_MODEL=...    → GoogleEmbeddingProvider (requiert clé valide)
    Pas de clé             → LocalHashEmbeddingProvider automatiquement
    """
    if settings is None:
        from src.config import get_settings
        settings = get_settings()

    model = settings.embedding_model
    api_key = settings.google_api_key

    if model == "local" or not api_key:
        if not api_key:
            logger.warning(
                "GOOGLE_API_KEY absente — provider local utilisé. "
                "Configurer une vraie clé pour de meilleurs résultats."
            )
        else:
            logger.info("Provider local demandé explicitement.")
        return LocalHashEmbeddingProvider()

    logger.info("Provider Google : %s", model)
    return GoogleEmbeddingProvider(model_name=model, api_key=api_key)
