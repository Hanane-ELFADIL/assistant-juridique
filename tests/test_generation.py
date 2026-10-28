"""
Tests Phase 6 — T600–T610
Pipeline RAG avec mock LLM (pas d'appel Google réel).
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock


# --- Mock providers ---

class MockEmbeddingProvider:
    def embed_texts(self, texts): return [self._v(t) for t in texts]
    def embed_query(self, q): return self._v(q)
    def _v(self, t):
        seed = sum(ord(c) for c in t[:20])
        return [(seed + i * 0.1) % 1.0 for i in range(8)]
    @property
    def model_name(self): return "mock-v1"
    @property
    def embedding_dimension(self): return 8


def _make_mock_llm(response_text: str):
    mock_response = MagicMock()
    mock_response.content = response_text
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = mock_response
    return mock_llm


# --- Fixtures ---

@pytest.fixture
def hybrid_search(tmp_path):
    from src.vectorstore.chroma_store import ChromaVectorStore
    from src.retrieval.bm25_index import BM25Index
    from src.retrieval.hybrid_search import HybridSearch

    store = ChromaVectorStore(
        MockEmbeddingProvider(),
        persist_dir=str(tmp_path / "chroma"),
        collection_name="rag_test",
    )
    bm25 = BM25Index()
    chunks = [
        ("c1", "Article 1 : Les banques doivent respecter les ratios prudentiels.",
         {"document_id": "d1", "article_number": "1", "doc_title": "Loi 34-03",
          "doc_type": "loi", "doc_number": "34-03", "doc_date": "2006",
          "source_url": "https://bkam.ma", "page_start": 5}),
        ("c2", "Article 2 : Le capital minimum est de 200 millions de dirhams.",
         {"document_id": "d1", "article_number": "2", "doc_title": "Loi 34-03",
          "doc_type": "loi", "doc_number": "34-03", "doc_date": "2006",
          "source_url": "https://bkam.ma", "page_start": 6}),
        ("c3", "Article 5 : Les établissements soumettent un rapport annuel.",
         {"document_id": "d1", "article_number": "5", "doc_title": "Loi 34-03",
          "doc_type": "loi", "doc_number": "34-03", "doc_date": "2006",
          "source_url": "https://bkam.ma", "page_start": 9}),
    ]
    ids, texts, metas = zip(*chunks)
    store.upsert_chunks(list(ids), list(texts), list(metas))
    bm25.build(list(ids), list(texts), list(metas))
    return HybridSearch(store, bm25, top_k=3)


@pytest.fixture
def mock_settings(tmp_path):
    from src.config import Settings
    return Settings(
        google_api_key="fake-key",
        gemini_model="gemini-1.5-flash",
        database_url="sqlite:///:memory:",
        data_raw_dir=str(tmp_path / "raw"),
        data_processed_dir=str(tmp_path / "proc"),
        chroma_persist_dir=str(tmp_path / "chroma"),
        max_context_chunks=3,
        max_query_length=500,
    )


def _chain_with_mock_llm(hybrid_search, mock_settings, response_text):
    """Crée une RAGChain avec un mock LLM injecté."""
    from src.generation.rag_chain import RAGChain
    chain = RAGChain(hybrid_search, mock_settings)
    mock_llm = _make_mock_llm(response_text)
    chain._llm = mock_llm
    chain._get_llm = lambda: mock_llm
    return chain


# --- T601/T602/T606/T607 : Prompts ---

class TestPrompts:

    def test_system_prompt_forbids_invention(self):
        """T601/T606 — le prompt système interdit l'invention."""
        from src.generation.prompts import SYSTEM_PROMPT
        prompt_lower = SYSTEM_PROMPT.lower()
        assert "jamais" in prompt_lower or "never" in prompt_lower
        assert "inventer" in prompt_lower or "fabrique" in prompt_lower

    def test_prompt_treats_docs_as_data(self):
        """T602 — les passages sont présentés comme DONNÉES."""
        from src.generation.prompts import build_rag_prompt
        prompt = build_rag_prompt("question ?", [{"text": "passage", "citation": {}, "chunk_id": "c1"}])
        assert "données" in prompt.lower() or "data" in prompt.lower()

    def test_prompt_no_context_signals_missing(self):
        """T607 — prompt sans contexte signale l'absence de sources."""
        from src.generation.prompts import build_rag_prompt
        prompt = build_rag_prompt("question ?", [])
        assert "insuffisant" in prompt.lower() or "aucun" in prompt.lower()

    def test_insufficient_sources_message_has_bkam_url(self):
        """T607 — message sources insuffisantes contient l'URL BAM."""
        from src.generation.prompts import INSUFFICIENT_SOURCES_MESSAGE
        assert "bkam.ma" in INSUFFICIENT_SOURCES_MESSAGE


# --- T603/T604/T605 : Réponse structurée ---

class TestRAGChain:

    def test_sourced_response_structure(self, hybrid_search, mock_settings):
        """T603 — réponse sourcée a les clés attendues."""
        chain = _chain_with_mock_llm(
            hybrid_search, mock_settings,
            "Les banques doivent respecter les ratios (Article 1)."
        )
        result = chain.answer("obligations des banques ratios")
        assert result["answer_type"] == "sourced"
        assert result["answer"]
        for key in ["citations", "sources", "warnings", "search_method"]:
            assert key in result

    def test_citations_linked_to_real_chunks(self, hybrid_search, mock_settings):
        """T604 — chaque citation a un chunk_id réel."""
        chain = _chain_with_mock_llm(hybrid_search, mock_settings, "Réponse.")
        result = chain.answer("capital minimum banques")
        assert result["citations"]
        for cit in result["citations"]:
            assert "chunk_id" in cit
            assert cit["chunk_id"] in ("c1", "c2", "c3")

    def test_citations_no_empty_fields(self, hybrid_search, mock_settings):
        """T605/T606 — citation ne contient que des champs non vides."""
        chain = _chain_with_mock_llm(hybrid_search, mock_settings, "Réponse.")
        result = chain.answer("ratios prudentiels")
        for cit in result["citations"]:
            for k, v in cit["citation"].items():
                assert v not in (None, ""), f"Champ vide {k}={v!r}"

    def test_sources_are_real_documents(self, hybrid_search, mock_settings):
        """T606 — sources correspondent à de vrais documents."""
        chain = _chain_with_mock_llm(hybrid_search, mock_settings, "Réponse.")
        result = chain.answer("banques capital")
        for src in result["sources"]:
            assert src["document_id"] == "d1"

    def test_insufficient_sources_mode(self, hybrid_search, mock_settings):
        """T607 — question hors périmètre ou hors corpus → réponse appropriée."""
        chain = _chain_with_mock_llm(hybrid_search, mock_settings, "Réponse.")
        result = chain.answer("cuisine tajine marocain poulet citron")
        # out_of_scope, sourced ou insufficient_sources sont tous valides
        assert result["answer_type"] in ("sourced", "insufficient_sources", "out_of_scope")
        assert result["answer"]

    def test_warnings_present(self, hybrid_search, mock_settings):
        """T505 — warnings toujours présents."""
        chain = _chain_with_mock_llm(hybrid_search, mock_settings, "Réponse.")
        result = chain.answer("obligations banques")
        assert isinstance(result["warnings"], list)

    def test_empty_question_is_error(self, hybrid_search, mock_settings):
        """T705 — question vide → error."""
        from src.generation.rag_chain import RAGChain
        chain = RAGChain(hybrid_search, mock_settings)
        result = chain.answer("   ")
        assert result["answer_type"] == "error"

    def test_too_long_question_is_error(self, hybrid_search, mock_settings):
        """T705 — question trop longue → error."""
        from src.generation.rag_chain import RAGChain
        chain = RAGChain(hybrid_search, mock_settings)
        result = chain.answer("x" * 600)
        assert result["answer_type"] == "error"

    def test_no_api_key_gives_error(self, hybrid_search):
        """T600 — sans clé API → error ou insufficient_sources."""
        from src.generation.rag_chain import RAGChain
        from src.config import Settings
        settings = Settings(google_api_key="", database_url="sqlite:///:memory:")
        chain = RAGChain(hybrid_search, settings)
        result = chain.answer("capital banque")
        assert result["answer_type"] in ("error", "insufficient_sources")

    def test_excerpt_in_citations(self, hybrid_search, mock_settings):
        """T609 — extrait présent dans les citations (distingue citation vs résumé)."""
        chain = _chain_with_mock_llm(hybrid_search, mock_settings, "Réponse.")
        result = chain.answer("ratios banques")
        if result["citations"]:
            assert "excerpt" in result["citations"][0]
            assert result["citations"][0]["excerpt"]
