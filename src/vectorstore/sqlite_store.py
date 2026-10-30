"""Vectorstore SQLite + numpy — rapide, sans ChromaDB."""
from __future__ import annotations
import json, logging, sqlite3
from pathlib import Path
from typing import Any, Optional
import numpy as np

logger = logging.getLogger(__name__)
EMBEDDING_INTERFACE_VERSION = "1.0"


class SQLiteVectorStore:
    def __init__(self, provider, persist_dir: Optional[str] = None,
                 collection_name: Optional[str] = None):
        self._provider = provider
        if persist_dir is None:
            from src.config import get_settings
            s = get_settings()
            persist_dir = getattr(s, 'vector_db_dir', './data/vector_db')
            collection_name = collection_name or getattr(s, 'vector_collection_name', 'bam_legal_chunks')
        self._persist_dir = Path(persist_dir)
        self._collection_name = collection_name or "bam_legal_chunks"
        self._db_path = self._persist_dir / f"{self._collection_name}.db"
        self._conn: Optional[sqlite3.Connection] = None
        self._ids: list[str] = []
        self._matrix_norm: Optional[np.ndarray] = None
        self._docs: list[str] = []
        self._metas: list[dict] = []
        self._cache_valid = False

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._persist_dir.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            self._conn.execute("""CREATE TABLE IF NOT EXISTS chunks (
                chunk_id TEXT PRIMARY KEY, document TEXT NOT NULL,
                embedding BLOB NOT NULL, metadata TEXT NOT NULL, model_name TEXT)""")
            self._conn.commit()
        return self._conn

    def _invalidate_cache(self):
        self._cache_valid = False
        self._ids = []; self._matrix_norm = None
        self._docs = []; self._metas = []

    def _load_cache(self):
        if self._cache_valid:
            return
        conn = self._get_conn()
        rows = conn.execute("SELECT chunk_id, document, embedding, metadata FROM chunks").fetchall()
        if not rows:
            self._ids = []; self._docs = []; self._metas = []
            self._matrix_norm = np.zeros((0, 1), dtype=np.float32)
            self._cache_valid = True; return
        self._ids = [r[0] for r in rows]
        self._docs = [r[1] for r in rows]
        self._metas = [json.loads(r[3]) for r in rows]
        dim = len(np.frombuffer(rows[0][2], dtype=np.float32))
        matrix = np.empty((len(rows), dim), dtype=np.float32)
        for i, r in enumerate(rows):
            matrix[i] = np.frombuffer(r[2], dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self._matrix_norm = matrix / norms
        self._cache_valid = True
        logger.info("Cache : %d vecteurs dim=%d", len(self._ids), dim)

    def upsert_chunks(self, chunk_ids, texts, metadatas, batch_size=10000):
        if not chunk_ids: return 0
        logger.info("Embeddings pour %d chunks...", len(chunk_ids))
        all_emb = self._provider.embed_texts(texts)
        conn = self._get_conn(); inserted = 0
        for s in range(0, len(chunk_ids), batch_size):
            rows = [(chunk_ids[i], texts[i], np.array(all_emb[i], dtype=np.float32).tobytes(),
                     json.dumps(metadatas[i]), self._provider.model_name)
                    for i in range(s, min(s+batch_size, len(chunk_ids)))]
            conn.executemany("INSERT OR REPLACE INTO chunks (chunk_id,document,embedding,metadata,model_name) VALUES(?,?,?,?,?)", rows)
            conn.commit(); inserted += len(rows)
        self._invalidate_cache(); return inserted

    def query(self, query_text, n_results=10, where=None):
        self._load_cache()
        if len(self._ids) == 0: return []
        q = np.array(self._provider.embed_query(query_text), dtype=np.float32)
        qn = np.linalg.norm(q); q = q / qn if qn > 0 else q
        scores = self._matrix_norm.dot(q)
        if where:
            for i, meta in enumerate(self._metas):
                if any(meta.get(k) != v for k, v in where.items()):
                    scores[i] = -1.0
        k = min(n_results, len(self._ids))
        top = np.argpartition(scores, -k)[-k:]
        top = top[np.argsort(scores[top])[::-1]]
        return [{"chunk_id": self._ids[i], "text": self._docs[i],
                 "metadata": self._metas[i], "score": round(max(0.0, float(scores[i])), 4),
                 "rank": r+1} for r, i in enumerate(top) if scores[i] >= 0]

    def delete_document_chunks(self, document_id):
        conn = self._get_conn()
        cur = conn.execute("DELETE FROM chunks WHERE json_extract(metadata,'$.document_id')=?", (document_id,))
        conn.commit(); self._invalidate_cache(); return cur.rowcount

    def count(self):
        return self._get_conn().execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

    def get_index_info(self):
        n = self.count(); model = ""
        if n > 0:
            row = self._get_conn().execute("SELECT model_name FROM chunks LIMIT 1").fetchone()
            model = row[0] if row else ""
        return {"collection_name": self._collection_name, "persist_dir": str(self._persist_dir),
                "total_chunks": n, "embedding_model": model,
                "embedding_interface_version": EMBEDDING_INTERFACE_VERSION, "backend": "sqlite+numpy"}
