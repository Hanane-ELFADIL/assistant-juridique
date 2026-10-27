"""
Tests Phase 11 — T1100–T1107
Évaluation bout en bout du pipeline RAG.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.evaluation import (
    recall_at_k,
    mean_reciprocal_rank,
    verify_citations,
    check_answer_faithfulness,
    check_unavailable_component,
    generate_eval_report,
)


# ── T1100 : Jeu d'évaluation ──────────────────────────────────────────────────

class TestEvalDataset:

    def test_eval_questions_file_exists(self):
        """T1100 — fichier de questions d'évaluation présent."""
        path = Path("tests/fixtures/eval_questions.json")
        assert path.exists(), "tests/fixtures/eval_questions.json manquant"

    def test_eval_questions_valid_format(self):
        """T1100 — questions d'évaluation ont le bon format."""
        path = Path("tests/fixtures/eval_questions.json")
        if not path.exists():
            pytest.skip("Fichier absent")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) >= 5, "Au moins 5 questions requises"
        for q in data:
            assert "id" in q
            assert "question" in q
            assert "expected_answer_type" in q

    def test_eval_has_insufficient_sources_cases(self):
        """T1101 — jeu inclut des questions sans réponse dans le corpus."""
        path = Path("tests/fixtures/eval_questions.json")
        if not path.exists():
            pytest.skip("Fichier absent")
        data = json.loads(path.read_text(encoding="utf-8"))
        insufficient = [q for q in data if q["expected_answer_type"] == "insufficient_sources"]
        assert len(insufficient) >= 1, "Au moins 1 question hors corpus requise"

    def test_eval_has_complex_questions(self):
        """T1101 — jeu inclut des questions complexes."""
        path = Path("tests/fixtures/eval_questions.json")
        if not path.exists():
            pytest.skip("Fichier absent")
        data = json.loads(path.read_text(encoding="utf-8"))
        sourced = [q for q in data if q["expected_answer_type"] == "sourced"]
        assert len(sourced) >= 5


# ── T1102 : Métriques de récupération ────────────────────────────────────────

class TestRetrievalMetrics:

    def test_recall_at_k_perfect(self):
        """T1102 — Recall@k = 1.0 quand tout est retrouvé."""
        retrieved = ["c1", "c2", "c3"]
        relevant = ["c1", "c2"]
        assert recall_at_k(retrieved, relevant, k=3) == 1.0

    def test_recall_at_k_partial(self):
        """T1102 — Recall@k partiel."""
        retrieved = ["c1", "c5", "c3"]
        relevant = ["c1", "c2", "c3"]
        # c1 et c3 retrouvés sur 3 → 2/3
        assert abs(recall_at_k(retrieved, relevant, k=3) - 2/3) < 1e-9

    def test_recall_at_k_zero(self):
        """T1102 — Recall@k = 0 si rien de pertinent trouvé."""
        assert recall_at_k(["c5", "c6"], ["c1", "c2"], k=2) == 0.0

    def test_recall_at_k_empty_relevant(self):
        """T1102 — Recall@k = 0 si pas de passages pertinents définis."""
        assert recall_at_k(["c1"], [], k=5) == 0.0

    def test_mrr_first_position(self):
        """T1102 — MRR = 1.0 si le pertinent est premier."""
        assert mean_reciprocal_rank([["c1", "c2"]], [["c1"]]) == 1.0

    def test_mrr_second_position(self):
        """T1102 — MRR = 0.5 si le pertinent est en position 2."""
        assert mean_reciprocal_rank([["c2", "c1"]], [["c1"]]) == 0.5

    def test_mrr_not_found(self):
        """T1102 — MRR = 0 si pertinent absent."""
        assert mean_reciprocal_rank([["c2", "c3"]], [["c1"]]) == 0.0

    def test_mrr_multiple_queries(self):
        """T1102 — MRR moyenné sur plusieurs requêtes."""
        # Q1 : pertinent en position 1 → RR=1.0
        # Q2 : pertinent en position 2 → RR=0.5
        # MRR = (1.0 + 0.5) / 2 = 0.75
        result = mean_reciprocal_rank(
            [["c1", "c2"], ["c2", "c1"]],
            [["c1"], ["c1"]],
        )
        assert abs(result - 0.75) < 1e-9


# ── T1103 : Vérification des citations ───────────────────────────────────────

class TestCitationVerification:

    def test_valid_citations_pass(self):
        """T1103 — citations valides passent la vérification."""
        result = {
            "citations": [{
                "chunk_id": "c1",
                "citation": {"title": "Loi 34-03", "article": "Article 1"},
                "excerpt": "Les banques doivent respecter...",
                "score": 0.9,
                "rank": 1,
            }]
        }
        report = verify_citations(result)
        assert report["pass"] is True
        assert report["verified"] == 1

    def test_missing_chunk_id_fails(self):
        """T1103 — citation sans chunk_id → échec."""
        result = {
            "citations": [{"chunk_id": "", "citation": {}, "excerpt": "texte", "score": 0.5, "rank": 1}]
        }
        report = verify_citations(result)
        assert report["pass"] is False

    def test_missing_excerpt_fails(self):
        """T1103 — citation sans extrait → signalée."""
        result = {
            "citations": [{"chunk_id": "c1", "citation": {"title": "T"}, "excerpt": "", "score": 0.5, "rank": 1}]
        }
        report = verify_citations(result)
        assert report["pass"] is False

    def test_no_citations_is_ok(self):
        """T1103 — pas de citations → rapport vide valide."""
        report = verify_citations({"citations": []})
        assert report["pass"] is True
        assert report["total_citations"] == 0


# ── T1104 : Fidélité ─────────────────────────────────────────────────────────

class TestFaithfulness:

    def test_sourced_with_citations_passes(self):
        """T1104 — réponse sourcée avec citations et avertissement → OK."""
        result = {
            "answer_type": "sourced",
            "citations": [{"chunk_id": "c1", "citation": {}, "excerpt": "x", "score": 0.9, "rank": 1}],
            "warnings": ["⚠️ Ces résultats sont classés par similarité textuelle, non par applicabilité juridique."],
        }
        report = check_answer_faithfulness(result)
        assert report["pass"] is True

    def test_sourced_without_citations_fails(self):
        """T1104 — sourced sans citations → incohérence."""
        result = {
            "answer_type": "sourced",
            "citations": [],
            "warnings": ["⚠️ similarité"],
        }
        report = check_answer_faithfulness(result)
        assert report["pass"] is False

    def test_insufficient_with_citations_fails(self):
        """T1104 — insufficient_sources avec citations → incohérence."""
        result = {
            "answer_type": "insufficient_sources",
            "citations": [{"chunk_id": "c1"}],
            "warnings": [],
        }
        report = check_answer_faithfulness(result)
        assert report["pass"] is False

    def test_insufficient_without_citations_passes(self):
        """T1104 — insufficient_sources sans citations → cohérent."""
        result = {
            "answer_type": "insufficient_sources",
            "citations": [],
            "warnings": ["Sources insuffisantes."],
        }
        report = check_answer_faithfulness(result)
        # Pas d'incohérence structurelle (pas de warning légal requis pour insufficient)
        assert "Réponse 'insufficient_sources' avec citations" not in str(report["issues"])


# ── T1105 : Robustesse aux pannes ────────────────────────────────────────────

class TestRobustness:

    def test_unavailable_llm_graceful(self, tmp_path):
        """T1105 — LLM indisponible → réponse gracieuse (pas de crash)."""
        from src.vectorstore.chroma_store import ChromaVectorStore
        from src.retrieval.bm25_index import BM25Index
        from src.retrieval.hybrid_search import HybridSearch

        class MockProvider:
            def embed_texts(self, t): return [[0.1] * 8 for _ in t]
            def embed_query(self, q): return [0.1] * 8
            @property
            def model_name(self): return "mock"
            @property
            def embedding_dimension(self): return 8

        store = ChromaVectorStore(MockProvider(), persist_dir=str(tmp_path / "c"), collection_name="t")
        bm25 = BM25Index()
        hs = HybridSearch(store, bm25, top_k=3)

        result = check_unavailable_component(hs, None, "test question robustesse")
        assert result["graceful"] is True
        assert result["has_answer"] is True

    def test_empty_index_handled(self, tmp_path):
        """T1105 — index vide → réponse gracieuse."""
        from src.vectorstore.chroma_store import ChromaVectorStore
        from src.retrieval.bm25_index import BM25Index
        from src.retrieval.hybrid_search import HybridSearch
        from src.generation.rag_chain import RAGChain
        from src.config import Settings

        class MockProvider:
            def embed_texts(self, t): return [[0.1] * 8 for _ in t]
            def embed_query(self, q): return [0.1] * 8
            @property
            def model_name(self): return "mock"
            @property
            def embedding_dimension(self): return 8

        store = ChromaVectorStore(MockProvider(), persist_dir=str(tmp_path / "c"), collection_name="t")
        bm25 = BM25Index()
        hs = HybridSearch(store, bm25, top_k=3)
        settings = Settings(google_api_key="", database_url="sqlite:///:memory:")
        chain = RAGChain(hs, settings)

        result = chain.answer("question sur un index vide")
        assert result["answer_type"] in ("error", "insufficient_sources")
        assert result["answer"]  # toujours un message


# ── T1106 : Rapport d'évaluation ─────────────────────────────────────────────

class TestEvalReport:

    def test_report_structure(self):
        """T1106 — generate_eval_report() retourne la structure attendue."""
        mock_results = [
            {
                "question_id": "Q001",
                "question": "Quelles sont les obligations des banques ?",
                "rag_result": {
                    "answer_type": "sourced",
                    "citations": [{"chunk_id": "c1", "citation": {"title": "T"}, "excerpt": "x", "score": 0.9, "rank": 1}],
                    "warnings": ["⚠️ similarité textuelle non applicabilité"],
                },
            },
            {
                "question_id": "Q002",
                "question": "Recette de cuisine ?",
                "rag_result": {
                    "answer_type": "insufficient_sources",
                    "citations": [],
                    "warnings": ["Sources insuffisantes."],
                },
            },
        ]
        report = generate_eval_report(mock_results)
        assert report["total_questions"] == 2
        assert report["sourced"] == 1
        assert report["insufficient_sources"] == 1
        assert "legal_disclaimer" in report

    def test_report_legal_disclaimer(self):
        """T1107 — rapport contient avertissement usage opérationnel."""
        report = generate_eval_report([])
        assert "T1107" in report["legal_disclaimer"] or "bancaire" in report["legal_disclaimer"]
