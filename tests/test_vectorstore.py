"""
Tests Phase 4 — T400–T408
Embeddings (mock) + ChromaDB + BM25.
Pas d'appel à l'API Google : mock EmbeddingProvider utilisé.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

# --- Mock EmbeddingProvider (T400) ---

class MockEmbeddingProvider:
    """Fournisseur d'embeddings déterministe pour les tests (sans API)."""

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        # Embedding fictif : hash des premiers chars → vecteur de dim 8
        return [self._vec(t) for t in texts]

    def embed_query(self, query: str) -> list[float]:
        return self._vec(query)

    def _vec(self, text: str) -> list[float]:
        """Produit un vecteur de 8 floats déterministe depuis un texte."""
        seed = sum(ord(c) for c in text[:20])
        return [(seed + i * 0.1) % 1.0 for i in range(8)]

    @property
    def model_name(self) -> str:
        return "mock-embedding-v1"

    @property
    def embedding_dimension(self) -> int:
        return 8


# --- Fixtures ---

@pytest.fixture
def chroma_dir(tmp_path):
    return str(tmp_path / "chroma_test")


@pytest.fixture
def store(chroma_dir):
    from src.vectorstore.chroma_store import ChromaVectorStore
    provider = MockEmbeddingProvider()
    return ChromaVectorStore(
        provider=provider,
        persist_dir=chroma_dir,
        collection_name="test_collection",
    )


SAMPLE_CHUNKS = [
    ("chunk-1", "Article 1 : Les banques respectent les ratios.", {"document_id": "doc-1", "article_number": "1", "doc_title": "Loi Test"}),
    ("chunk-2", "Article 2 : Le capital minimum est fixé.", {"document_id": "doc-1", "article_number": "2", "doc_title": "Loi Test"}),
    ("chunk-3", "Article 3 : Bank Al-Maghrib contrôle.", {"document_id": "doc-2", "article_number": "3", "doc_title": "Circulaire"}),
]


# --- T400/T401 : Interface ---

class TestEmbeddingInterface:

    def test_embed_texts_returns_list(self):
        """T400 — embed_texts retourne une liste de vecteurs."""
        p = MockEmbeddingProvider()
        result = p.embed_texts(["texte 1", "texte 2"])
        assert len(result) == 2
        assert all(isinstance(v, list) for v in result)
        assert all(len(v) == 8 for v in result)

    def test_embed_query_returns_vector(self):
        """T400 — embed_query retourne un vecteur."""
        p = MockEmbeddingProvider()
        v = p.embed_query("question de test")
        assert isinstance(v, list)
        assert len(v) == 8

    def test_google_provider_interface(self):
        """T401 — GoogleEmbeddingProvider implémente l'interface."""
        from src.embeddings.provider import GoogleEmbeddingProvider, EmbeddingProvider
        p = GoogleEmbeddingProvider("models/text-embedding-004", "fake-key")
        assert isinstance(p, EmbeddingProvider)
        assert p.model_name == "models/text-embedding-004"
        assert p.embedding_dimension == 768


# --- T403/T404 : ChromaDB ---

class TestChromaStore:

    def test_upsert_and_count(self, store):
        """T403 — upsert indexe les chunks, count les compte."""
        ids = [c[0] for c in SAMPLE_CHUNKS]
        texts = [c[1] for c in SAMPLE_CHUNKS]
        metas = [c[2] for c in SAMPLE_CHUNKS]
        n = store.upsert_chunks(ids, texts, metas)
        assert n == 3
        assert store.count() == 3

    def test_metadata_stored(self, store):
        """T404 — métadonnées accessibles après upsert."""
        ids = [c[0] for c in SAMPLE_CHUNKS]
        texts = [c[1] for c in SAMPLE_CHUNKS]
        metas = [c[2] for c in SAMPLE_CHUNKS]
        store.upsert_chunks(ids, texts, metas)
        results = store.query("ratios prudentiels", n_results=3)
        assert results
        assert "document_id" in results[0]["metadata"]
        assert results[0]["metadata"]["document_id"] in ("doc-1", "doc-2")

    def test_query_returns_results(self, store):
        """T500 — query retourne chunk_id, text, score, rank."""
        ids = [c[0] for c in SAMPLE_CHUNKS]
        texts = [c[1] for c in SAMPLE_CHUNKS]
        metas = [c[2] for c in SAMPLE_CHUNKS]
        store.upsert_chunks(ids, texts, metas)
        results = store.query("capital minimum banques", n_results=2)
        assert len(results) == 2
        for r in results:
            assert "chunk_id" in r
            assert "text" in r
            assert "score" in r
            assert "rank" in r
            assert 0.0 <= r["score"] <= 1.0

    def test_idempotent_upsert(self, store):
        """T405 — deux upserts du même chunk → count inchangé."""
        ids = ["chunk-1"]
        texts = ["Article 1 : contenu."]
        metas = [{"document_id": "doc-1", "article_number": "1"}]
        store.upsert_chunks(ids, texts, metas)
        store.upsert_chunks(ids, texts, metas)  # deuxième fois
        assert store.count() == 1  # pas de doublon

    def test_delete_document_chunks(self, store):
        """T406 — delete_document_chunks supprime les chunks d'un document."""
        ids = [c[0] for c in SAMPLE_CHUNKS]
        texts = [c[1] for c in SAMPLE_CHUNKS]
        metas = [c[2] for c in SAMPLE_CHUNKS]
        store.upsert_chunks(ids, texts, metas)
        assert store.count() == 3
        deleted = store.delete_document_chunks("doc-1")
        assert deleted == 2
        assert store.count() == 1

    def test_reindex_no_duplicate(self, store):
        """T406 — réindexation complète : delete + upsert → count correct."""
        ids = [c[0] for c in SAMPLE_CHUNKS]
        texts = [c[1] for c in SAMPLE_CHUNKS]
        metas = [c[2] for c in SAMPLE_CHUNKS]
        store.upsert_chunks(ids, texts, metas)
        # Réindexation : supprime d'abord, puis réinsère
        store.delete_document_chunks("doc-1")
        store.upsert_chunks(ids[:2], texts[:2], metas[:2])  # doc-1 seulement
        assert store.count() == 3  # 1 (doc-2) + 2 (doc-1 réindexé)

    def test_index_info(self, store):
        """T407 — get_index_info retourne modèle et version."""
        store.upsert_chunks(["id1"], ["texte test"], [{"document_id": "d1"}])
        info = store.get_index_info()
        assert "embedding_model" in info
        assert "embedding_interface_version" in info
        assert info["embedding_model"] == "mock-embedding-v1"
        assert info["total_chunks"] >= 1

    def test_filter_by_metadata(self, store):
        """T503 — filtre where réduit les résultats."""
        ids = [c[0] for c in SAMPLE_CHUNKS]
        texts = [c[1] for c in SAMPLE_CHUNKS]
        metas = [c[2] for c in SAMPLE_CHUNKS]
        store.upsert_chunks(ids, texts, metas)
        # Filtre sur document_id
        results = store.query("article", n_results=3, where={"document_id": "doc-2"})
        assert all(r["metadata"]["document_id"] == "doc-2" for r in results)

    def test_empty_upsert(self, store):
        """T403 — upsert vide retourne 0."""
        n = store.upsert_chunks([], [], [])
        assert n == 0


# --- T408 : intégrité BDD ↔ Chroma ---

class TestIntegrity:

    def test_chunk_ids_match(self, store):
        """T408 — chunk_ids dans Chroma correspondent à ceux insérés."""
        ids = ["a1", "b2", "c3"]
        texts = ["Texte alpha.", "Texte beta.", "Texte gamma."]
        metas = [{"document_id": "d"} for _ in ids]
        store.upsert_chunks(ids, texts, metas)
        results = store.query("texte", n_results=3)
        returned_ids = {r["chunk_id"] for r in results}
        assert returned_ids.issubset(set(ids))


# --- T501 : BM25 ---

class TestBM25:

    def test_bm25_search(self):
        """T501 — BM25Index.search() retourne résultats triés."""
        from src.retrieval.bm25_index import BM25Index
        idx = BM25Index()
        idx.build(
            chunk_ids=["c1", "c2", "c3"],
            texts=[
                "Les banques doivent respecter les ratios prudentiels.",
                "Le capital minimum est fixé par Bank Al-Maghrib.",
                "Les conditions de licence bancaire sont strictes.",
            ],
            metadatas=[{"doc": "d1"}, {"doc": "d1"}, {"doc": "d2"}],
        )
        results = idx.search("capital banque", n_results=3)
        assert results
        assert results[0]["score"] > 0
        assert "chunk_id" in results[0]
        assert "text" in results[0]

    def test_bm25_empty_query(self):
        """T501 — requête vide retourne liste vide."""
        from src.retrieval.bm25_index import BM25Index
        idx = BM25Index()
        idx.build(["c1"], ["texte"], [{}])
        results = idx.search("", n_results=3)
        assert results == []

    def test_bm25_empty_corpus(self):
        """T501 — corpus vide retourne liste vide."""
        from src.retrieval.bm25_index import BM25Index
        idx = BM25Index()
        results = idx.search("banque", n_results=3)
        assert results == []
