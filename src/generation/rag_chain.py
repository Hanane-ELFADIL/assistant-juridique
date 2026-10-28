"""
Pipeline RAG complet — T600–T609.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from src.generation.prompts import (
    CONTRADICTION_WARNING,
    INSUFFICIENT_SOURCES_MESSAGE,
    SYSTEM_PROMPT,
    build_rag_prompt,
)

logger = logging.getLogger(__name__)

# Seuil de score minimal pour considérer un passage pertinent
# RRF scores sont typiquement entre 0.01 et 0.02 — on accepte tout passage trouvé
MIN_RELEVANCE_SCORE = 0.0
# Nombre minimal de passages pour éviter le mode "sources insuffisantes"
MIN_PASSAGES_FOR_ANSWER = 1


class LLMNotConfiguredError(Exception):
    """Levée si GOOGLE_API_KEY n'est pas configurée."""
    pass


class RAGChain:
    """
    Pipeline RAG : recherche → construction du prompt → génération → citation.
    
    Interface configurable pour le LLM (T600).
    """

    def __init__(
        self,
        hybrid_search,
        settings=None,
    ):
        self._search = hybrid_search
        if settings is None:
            from src.config import get_settings
            settings = get_settings()
        self._settings = settings
        self._llm = None

    def _get_llm(self):
        """Initialise le LLM via le SDK google-genai natif (T600)."""
        if self._llm is not None:
            return self._llm

        if not self._settings.google_api_key:
            raise LLMNotConfiguredError(
                "GOOGLE_API_KEY non définie. "
                "Ajoutez-la dans votre fichier .env."
            )

        try:
            import google.genai as genai
        except ImportError:
            raise ImportError(
                "google-genai requis. "
                "Exécutez : pip install google-genai"
            )

        self._llm = genai.Client(api_key=self._settings.google_api_key)
        logger.info("LLM initialisé (google-genai) : %s", self._settings.gemini_model)
        return self._llm

    def answer(
        self,
        question: str,
        n_context_chunks: Optional[int] = None,
        filters: Optional[dict] = None,
    ) -> dict[str, Any]:
        """
        Répond à une question via RAG.
        
        Args:
            question: Question en langage naturel.
            n_context_chunks: Nombre de chunks de contexte (défaut: config).
            filters: Filtres de recherche.
        
        Returns:
            Dict structuré : answer, sources, citations, warnings, metadata.
        """
        n = n_context_chunks or self._settings.max_context_chunks
        question = question.strip()

        if not question:
            return _error_response("Question vide.", question)

        # Vérification longueur
        if len(question) > self._settings.max_query_length:
            return _error_response(
                f"Question trop longue (max {self._settings.max_query_length} caractères).",
                question,
            )

        # 1. Recherche hybride
        logger.info("Recherche pour : %r", question[:80])
        search_result = self._search.search(
            query=question,
            n_results=n,
            filters=filters,
        )
        all_results = search_result.get("results", [])

        # 2. Filtrage par score minimal
        relevant = [
            r for r in all_results
            if r.get("score", 0) >= MIN_RELEVANCE_SCORE
        ]

        # 3. Mode sources insuffisantes (T607)
        if len(relevant) < MIN_PASSAGES_FOR_ANSWER:
            logger.info("Sources insuffisantes pour : %r", question[:80])
            return {
                "answer": INSUFFICIENT_SOURCES_MESSAGE,
                "answer_type": "insufficient_sources",
                "question": question,
                "sources": [],
                "citations": [],
                "warnings": search_result.get("warnings", []),
                "search_method": search_result.get("search_method", ""),
                "total_retrieved": len(all_results),
            }

        # 4. Construction du prompt (T601, T602)
        context_for_prompt = [
            {"text": r["text"], "citation": r["citation"], "chunk_id": r["chunk_id"]}
            for r in relevant
        ]
        prompt = build_rag_prompt(question, context_for_prompt)

        # 5. Génération LLM via SDK google-genai natif
        try:
            client = self._get_llm()
            full_prompt = f"{SYSTEM_PROMPT}\n\n{prompt}"
            response = client.models.generate_content(
                model=self._settings.gemini_model,
                contents=full_prompt,
            )
            answer_text = response.text
        except LLMNotConfiguredError as e:
            return _error_response(str(e), question)
        except Exception as e:
            logger.error("Erreur LLM : %s", e)
            # Si le LLM échoue mais la recherche a trouvé des résultats,
            # retourner les passages avec un message explicatif
            err_str = str(e)
            if "503" in err_str or "UNAVAILABLE" in err_str:
                answer_text = (
                    "⚠️ Le service de génération est temporairement indisponible. "
                    "Voici les passages les plus pertinents trouvés dans les documents :"
                )
            else:
                return _error_response(f"Erreur lors de la génération : {e}", question)

        # 6. Construction des citations vérifiables (T604, T605)
        citations = []
        seen_chunks = set()
        for r in relevant:
            if r["chunk_id"] not in seen_chunks:
                seen_chunks.add(r["chunk_id"])
                citations.append({
                    "chunk_id": r["chunk_id"],
                    "citation": r["citation"],
                    "excerpt": r["text"][:300] + ("…" if len(r["text"]) > 300 else ""),
                    "score": r["score"],
                    "rank": r["rank"],
                })

        # 7. Détection de contradictions (T608)
        warnings = list(search_result.get("warnings", []))
        if _detect_contradictions(relevant):
            warnings.append(CONTRADICTION_WARNING)

        logger.info(
            "Réponse générée : %d sources, %d warnings.",
            len(citations),
            len(warnings),
        )

        return {
            "answer": answer_text,
            "answer_type": "sourced",
            "question": question,
            "sources": _build_sources_list(relevant),
            "citations": citations,
            "warnings": warnings,
            "search_method": search_result.get("search_method", ""),
            "total_retrieved": len(all_results),
            "relevant_used": len(relevant),
        }


def _error_response(message: str, question: str) -> dict[str, Any]:
    return {
        "answer": message,
        "answer_type": "error",
        "question": question,
        "sources": [],
        "citations": [],
        "warnings": [message],
        "search_method": "",
        "total_retrieved": 0,
    }


def _build_sources_list(results: list[dict]) -> list[dict]:
    """
    Déduplique et structure la liste des sources (T605, T606).
    N'inclut que les champs réellement disponibles — rien n'est inventé.
    """
    seen_docs = set()
    sources = []
    for r in results:
        meta = r.get("metadata", {})
        doc_id = meta.get("document_id", "")
        if doc_id and doc_id not in seen_docs:
            seen_docs.add(doc_id)
            source = {"document_id": doc_id}
            # N'ajoute que les champs non vides
            for field, label in [
                ("doc_title", "title"),
                ("doc_type", "type"),
                ("doc_number", "number"),
                ("doc_date", "date"),
                ("doc_language", "language"),
                ("source_url", "url"),
            ]:
                val = meta.get(field)
                if val:
                    source[label] = val
            sources.append(source)
    return sources


def _detect_contradictions(results: list[dict]) -> bool:
    """
    Détection heuristique simple de contradictions entre documents (T608).
    Si plusieurs documents différents sont cités, il peut y avoir divergence.
    """
    doc_ids = set()
    for r in results:
        meta = r.get("metadata", {})
        doc_id = meta.get("document_id")
        if doc_id:
            doc_ids.add(doc_id)
    # Heuristique : si plus d'un document source, avertir
    return len(doc_ids) > 1
