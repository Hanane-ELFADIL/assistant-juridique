"""
Vectorstore SQLite + numpy — rapide, sans serveur, sans ChromaDB.
Stocke les vecteurs en BLOB SQLite. Recherche cosinus numpy en mémoire.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Optional

import numpy as np

logger = logging.getLogger(__name__)
EMBEDDING_INTERFACE_VERSION = "1.0"


class SQLiteVectorStore:
    """Vectorstore léger : SQLite pour la persistance, numpy pour la recherche."""

    def __init__(self, provider, persist_dir: Optional[str] = None,
                 collection_name: Optional[str] = None):
        self._provider = provider
        if persist_dir is None:
            from src.config import get_settings
            s = get_settings()
            persist_dir = s.vector_db_dir
            collection_name = collection_name or s.vector_collection_name
        self._persist_dir = Path(persist_dir)
        self._collection_name = collection_name or "bam_legal_chunks"
        self._db_path = self._persist_dir / f"{self._collection_name}.db"
        self._conn: Optional[sqlite3.Connection] = None
        # Cache mémoire
        self._ids: list[str] = []
        self._matrix_norm: Optional[np.ndarray] = None  # pré-normalisé
        self._docs: list[str] = []
        self._metas: list[dict] = []
        self._cache_valid = False

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._persist_dir.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id TEXT PRIMARY KEY,
                    document TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    metadata TEXT NOT NULL,
                    model_name TEXT
                )
            """)
            self._conn.commit()
        return self._conn

    def _invalidate_cache(self):
        self._cache_valid = False
        self._ids = []
        self._matrix_norm = None
        self._docs = []
        self._metas = []

    def _load_cache(self):
        if self._cache_valid:
            return
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT chunk_id, document, embedding, metadata FROM chunks"
        ).fetchall()
        if not rows:
            self._ids = []
            self._matrix_norm = np.zeros((0, 1), dtype=np.float32)
            self._docs = []
            self._metas = []
            self._cache_valid = True
            return

        self._ids = [r[0] for r in rows]
        self._docs = [r[1] for r in rows]
        self._metas = [json.loads(r[3]) for r in rows]

        # Charger tous les vecteurs et pré-normaliser
        dim = len(np.frombuffer(rows[0][2], dtype=np.float32))
        matrix = np.empty((len(rows), dim), dtype=np.float32)
        for i, r in enumerate(rows):
            matrix[i] = np.frombuffer(r[2], dtype=np.float32)

        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self._matrix_norm = matrix / norms  # pré-normalisé une seule fois
        self._cache_valid = True
        logger.info("Cache vectoriel : %d vecteurs dim=%d", len(self._ids), dim)

    def upsert_chunks(self, chunk_ids: list[str], texts: list[str],
                      metadatas: list[dict], batch_size: int = 10000) -> int:
        if not chunk_ids:
            return 0
        total = len(chunk_ids)
        logger.info("Génération embeddings pour %d chunks...", total)
        all_embeddings = self._provider.embed_texts(texts)
        logger.info("Embeddings OK. Insertion SQLite...")

        conn = self._get_conn()
        inserted = 0
        for start in range(0, total, batch_size):
            end = min(start + batch_size, total)
            rows = []
            for i in range(start, end):
                vec_bytes = np.array(all_embeddings[i], dtype=np.float32).tobytes()
                rows.append((chunk_ids[i], texts[i], vec_bytes,
                              json.dumps(metadatas[i]), self._provider.model_name))
            conn.executemany(
                "INSERT OR REPLACE INTO chunks "
                "(chunk_id, document, embedding, metadata, model_name) "
                "VALUES (?,?,?,?,?)", rows
            )
            conn.commit()
            inserted += end - start
        self._invalidate_cache()
        return inserted

    def query(self, query_text: str, n_results: int = 10,
              where: Optional[dict] = None) -> list[dict[str, Any]]:
        self._load_cache()
        if len(self._ids) == 0:
            return []

        # Embedding de la requête, normalisé
        q_vec = np.array(self._provider.embed_query(query_text), dtype=np.float32)
        q_norm = np.linalg.norm(q_vec)
        if q_norm > 0:
            q_vec /= q_norm

        # Similarité cosinus sur matrice pré-normalisée (rapide)
        scores = self._matrix_norm.dot(q_vec)

        # Filtre métadonnées
        if where:
            for i, meta in enumerate(self._metas):
                for k, v in where.items():
                    if meta.get(k) != v:
                        scores[i] = -1.0
                        break

        # Top-k
        k = min(n_results, len(self._ids))
        top_idx = np.argpartition(scores, -k)[-k:]
        top_idx = top_idx[np.argsort(scores[top_idx])[::-1]]

        results = []
        for rank, idx in enumerate(top_idx, start=1):
            s = float(scores[idx])
            if s < 0:
                continue
            results.append({
                "chunk_id": self._ids[idx],
                "text": self._docs[idx],
                "metadata": self._metas[idx],
                "score": round(max(0.0, s), 4),
                "rank": rank,
            })
        return results

    def delete_document_chunks(self, document_id: str) -> int:
        conn = self._get_conn()
        cur = conn.execute(
            "DELETE FROM chunks WHERE json_extract(metadata,'$.document_id')=?",
            (document_id,)
        )
        conn.commit()
        self._invalidate_cache()
        return cur.rowcount

    def count(self) -> int:
        return self._get_conn().execute(
            "SELECT COUNT(*) FROM chunks"
        ).fetchone()[0]

    def get_index_info(self) -> dict:
        n = self.count()
        model = ""
        if n > 0:
            row = self._get_conn().execute(
                "SELECT model_name FROM chunks LIMIT 1"
            ).fetchone()
            model = row[0] if row else ""
        return {
            "collection_name": self._collection_name,
            "persist_dir": str(self._persist_dir),
            "total_chunks": n,
            "embedding_model": model,
            "embedding_interface_version": EMBEDDING_INTERFACE_VERSION,
            "backend": "sqlite+numpy",
        }
