"""
Tests Phase 5 — T500–T508
Recherche hybride : vectorielle + BM25 + RRF.
"""
from __future__ import annotations

import pytest


class MockEmbeddingProvider:
    def embed_texts(self, texts):
        return [self._v(t) for t in texts]
    def embed_query(self, q):
        return self._v(q)
    def _v(self, t):
        seed = sum(ord(c) for c in t[:20])
        return [(seed + i * 0.1) % 1.0 for i in range(8)]
    @property
    def model_name(self): return "mock-v1"
    @property
    def embedding_dimension(self): return 8


@pytest.fixture
def populated_store(tmp_path):
    from src.vectorstore.chroma_store import ChromaVectorStore
    from src.retrieval.bm25_index import BM25Index

    provider = MockEmbeddingProvider()
    store = ChromaVectorStore(provider, persist_dir=str(tmp_path / "chroma"), collection_name="test")
    bm25 = BM25Index()

    chunks = [
        ("c1", "Article 1 : Les banques respectent les ratios prudentiels.", {"document_id": "d1", "article_number": "1", "doc_title": "Loi 34-03", "doc_type": "loi", "doc_number": "34-03", "doc_date": "2006", "source_url": "https://bkam.ma", "page_start": 5}),
        ("c2", "Article 2 : Le capital minimum est de 200 millions.", {"document_id": "d1", "article_number": "2", "doc_title": "Loi 34-03", "doc_type": "loi", "doc_number": "34-03", "doc_date": "2006", "source_url": "https://bkam.ma", "page_start": 6}),
        ("c3", "Article 3 : Bank Al-Maghrib délivre les agréments.", {"document_id": "d1", "article_number": "3", "doc_title": "Loi 34-03", "doc_type": "loi", "doc_number": "34-03", "doc_date": "2006", "source_url": "https://bkam.ma", "page_start": 7}),
        ("c4", "Article 1 : Les établissements financiers sont soumis.", {"document_id": "d2", "article_number": "1", "doc_title": "Circulaire 1/W/2014", "doc_type": "circulaire", "doc_number": "1/W/2014", "doc_date": "2014", "source_url": "https://bkam.ma/2", "page_start": 1}),
    ]
    ids = [c[0] for c in chunks]
    texts = [c[1] for c in chunks]
    metas = [c[2] for c in chunks]
    store.upsert_chunks(ids, texts, metas)
    bm25.build(ids, texts, metas)
    return store, bm25


class TestHybridSearch:

    def test_search_returns_results(self, populated_store):
        """T500+T501+T502 — recherche hybride retourne des résultats."""
        from src.retrieval.hybrid_search import HybridSearch
        store, bm25 = populated_store
        hs = HybridSearch(store, bm25, top_k=3)
        result = hs.search("capital minimum banque")
        assert result["results"]
        assert result["total_found"] >= 1

    def test_results_have_required_fields(self, populated_store):
        """T507 — chaque résultat contient chunk_id, text, score, rank, citation."""
        from src.retrieval.hybrid_search import HybridSearch
        store, bm25 = populated_store
        hs = HybridSearch(store, bm25, top_k=3)
        result = hs.search("ratios prudentiels")
        for r in result["results"]:
            assert "chunk_id" in r
            assert "text" in r
            assert "score" in r
            assert "rank" in r
            assert "citation" in r

    def test_legal_warning_present(self, populated_store):
        """T505 — avertissement légal toujours présent."""
        from src.retrieval.hybrid_search import HybridSearch
        store, bm25 = populated_store
        hs = HybridSearch(store, bm25, top_k=3)
        result = hs.search("capital")
        assert any("similarité" in w.lower() or "applicabilité" in w.lower()
                   for w in result["warnings"])

    def test_empty_query(self, populated_store):
        """T500 — requête vide retourne liste vide avec warning."""
        from src.retrieval.hybrid_search import HybridSearch
        store, bm25 = populated_store
        hs = HybridSearch(store, bm25)
        result = hs.search("   ")
        assert result["results"] == []
        assert result["warnings"]

    def test_article_reference_filter(self, populated_store):
        """T504 — 'article 2' détecte et filtre sur article_number=2."""
        from src.retrieval.hybrid_search import HybridSearch
        store, bm25 = populated_store
        hs = HybridSearch(store, bm25, top_k=4)
        result = hs.search("article 2 capital")
        # Les résultats doivent contenir article 2
        if result["results"]:
            arts = [r["metadata"].get("article_number") for r in result["results"]]
            assert "2" in arts, f"Article 2 non trouvé dans {arts}"

    def test_citation_built_from_metadata(self, populated_store):
        """T507 — citation construite depuis les métadonnées réelles."""
        from src.retrieval.hybrid_search import HybridSearch
        store, bm25 = populated_store
        hs = HybridSearch(store, bm25, top_k=2)
        result = hs.search("agrément bank")
        for r in result["results"]:
            cit = r["citation"]
            # Citation ne contient que des champs non vides
            for v in cit.values():
                assert v not in (None, ""), f"Valeur vide dans citation: {cit}"


class TestRRF:

    def test_rrf_merges_lists(self):
        """T502 — RRF fusionne deux listes et trie par score."""
        from src.retrieval.hybrid_search import reciprocal_rank_fusion
        list_a = [
            {"chunk_id": "c1", "text": "t1", "rank": 1, "score": 0.9},
            {"chunk_id": "c2", "text": "t2", "rank": 2, "score": 0.7},
        ]
        list_b = [
            {"chunk_id": "c2", "text": "t2", "rank": 1, "score": 0.8},
            {"chunk_id": "c3", "text": "t3", "rank": 2, "score": 0.5},
        ]
        fused = reciprocal_rank_fusion(list_a, list_b)
        assert len(fused) == 3
        # c2 apparaît dans les deux listes → score RRF plus élevé
        assert fused[0]["chunk_id"] == "c2"
        # Scores décroissants
        scores = [r["rrf_score"] for r in fused]
        assert scores == sorted(scores, reverse=True)

    def test_rrf_no_duplicates(self):
        """T502 — pas de doublons dans la liste fusionnée."""
        from src.retrieval.hybrid_search import reciprocal_rank_fusion
        same = [{"chunk_id": "x", "text": "t", "rank": 1, "score": 0.9}]
        fused = reciprocal_rank_fusion(same, same)
        ids = [r["chunk_id"] for r in fused]
        assert len(ids) == len(set(ids))
