"""
Interface embeddings — supporte Ollama (local) et Google API.
Ollama recommandé : nomic-embed-text (vraie sémantique, 768 dims).
"""
from __future__ import annotations

import hashlib
import logging
import math
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)
EMBEDDING_INTERFACE_VERSION = "2.0"


class EmbeddingProvider(ABC):
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


class OllamaEmbeddingProvider(EmbeddingProvider):
    """
    Embeddings via Ollama local — nomic-embed-text (768 dims).
    Vraie sémantique, aucune clé API, fonctionne hors-ligne.
    Requires: ollama pull nomic-embed-text
    """
    def __init__(self, model: str = "nomic-embed-text",
                 base_url: str = "http://localhost:11434"):
        self._model = model
        self._base_url = base_url

    def _embed(self, texts: list[str]) -> list[list[float]]:
        import urllib.request, json
        results = []
        for text in texts:
            body = json.dumps({"model": self._model, "prompt": text}).encode()
            req = urllib.request.Request(
                f"{self._base_url}/api/embeddings",
                data=body, headers={"Content-Type": "application/json"}
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = json.loads(r.read())
                    results.append(data["embedding"])
            except Exception as e:
                logger.error("Ollama embedding error: %s", e)
                raise RuntimeError(
                    f"Ollama non disponible ({e}). "
                    "Vérifiez que Ollama tourne : ollama serve"
                ) from e
        return results

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        # Traitement par batch de 10 pour éviter les timeouts
        results = []
        for i in range(0, len(texts), 10):
            batch = texts[i:i+10]
            results.extend(self._embed(batch))
            if i % 500 == 0 and i > 0:
                logger.info("Embeddings Ollama : %d/%d", i, len(texts))
        return results

    def embed_query(self, query: str) -> list[float]:
        return self._embed([query])[0]

    @property
    def model_name(self) -> str:
        return f"ollama/{self._model}"

    @property
    def embedding_dimension(self) -> int:
        return 768  # nomic-embed-text


class LocalHashEmbeddingProvider(EmbeddingProvider):
    """
    Fallback local — hash MD5, dim 64. Aucune installation.
    Qualité faible. Utiliser uniquement si Ollama non disponible.
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
        return "hash-local-64"

    @property
    def embedding_dimension(self) -> int:
        return self.DIM


# Alias
TFIDFEmbeddingProvider = LocalHashEmbeddingProvider


class GoogleEmbeddingProvider(EmbeddingProvider):
    """Embeddings Google (gemini-embedding-001, 3072 dims)."""
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
            model=self._model_name, contents=texts,
            config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
        )
        return [e.values for e in result.embeddings]

    def embed_query(self, query: str) -> list[float]:
        import google.genai.types as types
        client = self._get_client()
        result = client.models.embed_content(
            model=self._model_name, contents=[query],
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
    Factory selon EMBEDDING_MODEL dans .env :
      ollama          → OllamaEmbeddingProvider (recommandé)
      local           → LocalHashEmbeddingProvider (fallback)
      models/gemini-* → GoogleEmbeddingProvider
    """
    if settings is None:
        from src.config import get_settings
        settings = get_settings()

    model = settings.embedding_model

    if model == "ollama":
        ollama_url = getattr(settings, 'ollama_base_url', 'http://localhost:11434')
        ollama_model = getattr(settings, 'ollama_embed_model', 'nomic-embed-text')
        logger.info("Provider : Ollama (%s @ %s)", ollama_model, ollama_url)
        return OllamaEmbeddingProvider(model=ollama_model, base_url=ollama_url)

    if model == "local" or not settings.google_api_key:
        logger.info("Provider : hash local (fallback)")
        return LocalHashEmbeddingProvider()

    logger.info("Provider : Google (%s)", model)
    return GoogleEmbeddingProvider(model_name=model, api_key=settings.google_api_key)
