"""
Index vectoriel ChromaDB — T403–T407.
Idempotent : pas de doublons à chaque relance (détection par chunk_id).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from src.config import get_settings
from src.embeddings.provider import EMBEDDING_INTERFACE_VERSION, EmbeddingProvider

logger = logging.getLogger(__name__)

# Métadonnée spéciale pour tracer la version du modèle d'embeddings (T407)
_META_KEY_MODEL = "_embedding_model"
_META_KEY_VERSION = "_embedding_interface_version"


class ChromaVectorStore:
    """
    Wrapper ChromaDB pour l'indexation et la recherche de chunks juridiques.
    
    Garanties :
    - Idempotence : upsert par chunk_id (T405, T406).
    - Traçabilité : version du modèle stockée dans les métadonnées (T407).
    - Sécurité : les textes juridiques sont traités comme données.
    """

    def __init__(
        self,
        provider: EmbeddingProvider,
        persist_dir: Optional[str] = None,
        collection_name: Optional[str] = None,
    ):
        self._provider = provider
        settings = get_settings()
        self._persist_dir = persist_dir or settings.chroma_persist_dir
        self._collection_name = collection_name or settings.chroma_collection_name
        self._client = None
        self._collection = None

    def _get_client(self):
        if self._client is None:
            try:
                import chromadb  # type: ignore
            except ImportError:
                raise ImportError(
                    "chromadb requis. Exécutez : pip install chromadb"
                )
            Path(self._persist_dir).mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=self._persist_dir)
        return self._client

    def _get_collection(self):
        if self._collection is None:
            client = self._get_client()
            self._collection = client.get_or_create_collection(
                name=self._collection_name,
                metadata={
                    _META_KEY_MODEL: self._provider.model_name,
                    _META_KEY_VERSION: EMBEDDING_INTERFACE_VERSION,
                },
            )
            logger.info(
                "Collection ChromaDB '%s' prête (%d documents existants).",
                self._collection_name,
                self._collection.count(),
            )
        return self._collection

    def upsert_chunks(
        self,
        chunk_ids: list[str],
        texts: list[str],
        metadatas: list[dict],
        batch_size: int = 50,
    ) -> int:
        """
        Indexe les chunks avec upsert (T405, T406).
        Un chunk déjà présent est mis à jour — pas de doublon.
        
        Args:
            chunk_ids: IDs uniques des chunks.
            texts: Textes à vectoriser.
            metadatas: Métadonnées associées.
            batch_size: Taille des lots pour l'API d'embeddings.
        
        Returns:
            Nombre de chunks indexés/mis à jour.
        """
        if not chunk_ids:
            return 0

        collection = self._get_collection()
        total = len(chunk_ids)
        indexed = 0

        for start in range(0, total, batch_size):
            batch_ids = chunk_ids[start:start + batch_size]
            batch_texts = texts[start:start + batch_size]
            batch_metas = metadatas[start:start + batch_size]

            # Nettoyage des métadonnées (ChromaDB n'accepte que str/int/float/bool)
            clean_metas = []
            for meta in batch_metas:
                clean = {}
                for k, v in meta.items():
                    if isinstance(v, (str, int, float, bool)):
                        clean[k] = v
                    elif v is None:
                        clean[k] = ""
                    else:
                        clean[k] = str(v)
                clean_metas.append(clean)

            try:
                embeddings = self._provider.embed_texts(batch_texts)
                collection.upsert(
                    ids=batch_ids,
                    embeddings=embeddings,
                    documents=batch_texts,
                    metadatas=clean_metas,
                )
                indexed += len(batch_ids)
                logger.info(
                    "Lot %d–%d indexé (%d/%d).",
                    start + 1,
                    start + len(batch_ids),
                    indexed,
                    total,
                )
            except Exception as e:
                logger.error("Erreur lors de l'indexation du lot %d : %s", start, e)
                raise

        return indexed

    def query(
        self,
        query_text: str,
        n_results: int = 10,
        where: Optional[dict] = None,
    ) -> list[dict[str, Any]]:
        """
        Recherche vectorielle sémantique (T500).
        
        Args:
            query_text: Question en langage naturel.
            n_results: Nombre de résultats à retourner.
            where: Filtres sur les métadonnées (T503).
        
        Returns:
            Liste de dicts {chunk_id, text, metadata, score, rank}.
        """
        collection = self._get_collection()
        query_embedding = self._provider.embed_query(query_text)

        kwargs: dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": min(n_results, max(1, collection.count())),
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        try:
            results = collection.query(**kwargs)
        except Exception as e:
            logger.error("Erreur de recherche vectorielle : %s", e)
            return []

        output = []
        ids = results.get("ids", [[]])[0]
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for rank, (cid, text, meta, dist) in enumerate(
            zip(ids, docs, metas, distances), start=1
        ):
            # Convertit la distance cosinus en score de similarité [0, 1]
            score = max(0.0, 1.0 - dist / 2.0)
            output.append({
                "chunk_id": cid,
                "text": text,
                "metadata": meta,
                "score": round(score, 4),
                "rank": rank,
            })

        return output

    def delete_document_chunks(self, document_id: str) -> int:
        """
        Supprime tous les chunks d'un document de l'index (T406).
        
        Returns:
            Nombre de chunks supprimés.
        """
        collection = self._get_collection()
        try:
            existing = collection.get(
                where={"document_id": document_id},
                include=["documents"],
            )
            ids_to_delete = existing.get("ids", [])
            if ids_to_delete:
                collection.delete(ids=ids_to_delete)
                logger.info(
                    "%d chunks supprimés pour document_id=%r.",
                    len(ids_to_delete),
                    document_id,
                )
            return len(ids_to_delete)
        except Exception as e:
            logger.error("Erreur suppression chunks de %r : %s", document_id, e)
            return 0

    def count(self) -> int:
        """Retourne le nombre total de chunks dans l'index."""
        return self._get_collection().count()

    def get_index_info(self) -> dict:
        """Retourne les informations de l'index (T407)."""
        collection = self._get_collection()
        meta = collection.metadata or {}
        return {
            "collection_name": self._collection_name,
            "persist_dir": self._persist_dir,
            "total_chunks": collection.count(),
            "embedding_model": meta.get(_META_KEY_MODEL, "unknown"),
            "embedding_interface_version": meta.get(_META_KEY_VERSION, "unknown"),
        }
