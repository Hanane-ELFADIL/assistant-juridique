"""
Pipeline RAG — génération avec retry, timeout, prompt strict.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

from src.generation.prompts import (
    CONTRADICTION_WARNING,
    INSUFFICIENT_SOURCES_MESSAGE,
    SYSTEM_PROMPT,
    build_rag_prompt,
)

logger = logging.getLogger(__name__)

MIN_RELEVANCE_SCORE = 0.0
MIN_PASSAGES_FOR_ANSWER = 1

# Questions hors périmètre
_OUT_OF_SCOPE_PATTERNS = [
    "recette", "cuisine", "tajine", "météo", "temps qu'il", "quel temps",
    "foot", "sport", "film", "musique", "politique", "élection",
    "ignore tes instructions", "ignore your instructions", "prompt système",
    "system prompt", "donne moi ton prompt", "forget your",
]


class LLMNotConfiguredError(Exception):
    pass


class RAGChain:

    def __init__(self, hybrid_search, settings=None):
        self._search = hybrid_search
        if settings is None:
            from src.config import get_settings
            settings = get_settings()
        self._settings = settings
        self._llm = None

    def _get_llm(self):
        if self._llm is not None:
            return self._llm
        if not self._settings.google_api_key:
            raise LLMNotConfiguredError("GOOGLE_API_KEY non définie.")
        try:
            import google.genai as genai
        except ImportError:
            raise ImportError("google-genai requis : pip install google-genai")
        self._llm = genai.Client(api_key=self._settings.google_api_key)
        logger.info("LLM : %s", self._settings.gemini_model)
        return self._llm

    def _is_out_of_scope(self, question: str) -> bool:
        q_lower = question.lower()
        return any(p in q_lower for p in _OUT_OF_SCOPE_PATTERNS)

    def _generate(self, prompt: str) -> str:
        """Génération avec 2 tentatives et backoff."""
        client = self._get_llm()
        model = self._settings.gemini_model
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                )
                return response.text
            except Exception as e:
                err = str(e)
                if attempt == 0 and ("503" in err or "UNAVAILABLE" in err or "quota" in err.lower()):
                    logger.warning("LLM tentative 1 échouée (%s), retry dans 3s.", err[:60])
                    time.sleep(3)
                    continue
                raise
        raise RuntimeError("LLM indisponible après 2 tentatives.")

    def answer(self, question: str, n_context_chunks: Optional[int] = None,
               filters: Optional[dict] = None) -> dict[str, Any]:
        n = n_context_chunks or self._settings.max_context_chunks
        question = question.strip()

        if not question:
            return _error_response("Question vide.", question)

        if len(question) > self._settings.max_query_length:
            return _error_response(
                f"Question trop longue (max {self._settings.max_query_length} caractères).",
                question,
            )

        # Détection hors périmètre
        if self._is_out_of_scope(question):
            return {
                "answer": (
                    "Cette question est hors du périmètre de l'assistant juridique "
                    "Bank Al-Maghrib. Je suis uniquement en mesure de répondre "
                    "aux questions relatives aux textes législatifs et réglementaires bancaires marocains."
                ),
                "answer_type": "out_of_scope",
                "question": question,
                "sources": [], "citations": [], "warnings": [],
                "search_method": "", "total_retrieved": 0, "relevant_used": 0,
            }

        # Recherche hybride
        logger.info("Recherche : %r", question[:80])
        search_result = self._search.search(query=question, n_results=n, filters=filters)
        all_results = search_result.get("results", [])

        relevant = [r for r in all_results if r.get("score", 0) >= MIN_RELEVANCE_SCORE]

        if len(relevant) < MIN_PASSAGES_FOR_ANSWER:
            return {
                "answer": INSUFFICIENT_SOURCES_MESSAGE,
                "answer_type": "insufficient_sources",
                "question": question,
                "sources": [], "citations": [],
                "warnings": search_result.get("warnings", []),
                "search_method": search_result.get("search_method", ""),
                "total_retrieved": len(all_results),
                "relevant_used": 0,
            }

        # Déduplication : max 2 passages par article
        relevant = _deduplicate(relevant)

        context_for_prompt = [
            {"text": r["text"], "citation": r["citation"], "chunk_id": r["chunk_id"]}
            for r in relevant
        ]
        prompt = f"{SYSTEM_PROMPT}\n\n{build_rag_prompt(question, context_for_prompt)}"

        # Génération avec fallback dégradé
        try:
            answer_text = self._generate(prompt)
            answer_type = "sourced"
        except LLMNotConfiguredError as e:
            return _error_response(str(e), question)
        except Exception as e:
            logger.error("Échec génération LLM : %s", e)
            # Mode dégradé : afficher les passages sans synthèse
            answer_text = (
                "⚠️ **Service de génération indisponible.**\n\n"
                "Voici les passages les plus pertinents trouvés dans les documents :\n\n"
                + "\n\n---\n\n".join(
                    f"**[{i+1}]** {r['text'][:400]}"
                    for i, r in enumerate(relevant[:5])
                )
            )
            answer_type = "degraded"

        # Construction des citations — UNIQUEMENT avec de vrais métadonnées
        citations = []
        seen = set()
        for r in relevant:
            if r["chunk_id"] not in seen:
                seen.add(r["chunk_id"])
                cit = r["citation"]
                # Ne pas afficher de citation sans au moins un titre ou un article réel
                if cit.get("title") or cit.get("article"):
                    citations.append({
                        "chunk_id": r["chunk_id"],
                        "citation": cit,
                        "excerpt": r["text"][:400] + ("…" if len(r["text"]) > 400 else ""),
                        "score": r["score"],
                        "rank": r["rank"],
                    })

        warnings = list(search_result.get("warnings", []))
        if _detect_contradictions(relevant):
            warnings.append(CONTRADICTION_WARNING)

        return {
            "answer": answer_text,
            "answer_type": answer_type,
            "question": question,
            "sources": _build_sources_list(relevant),
            "citations": citations,
            "warnings": warnings,
            "search_method": search_result.get("search_method", ""),
            "total_retrieved": len(all_results),
            "relevant_used": len(relevant),
        }


def _deduplicate(results: list[dict], max_per_article: int = 2) -> list[dict]:
    """Max 2 passages par article, supprime les quasi-doublons."""
    seen_articles: dict[str, int] = {}
    out = []
    seen_texts: list[str] = []
    for r in results:
        art = r.get("metadata", {}).get("article_number", "")
        # Limite par article
        if art:
            if seen_articles.get(art, 0) >= max_per_article:
                continue
            seen_articles[art] = seen_articles.get(art, 0) + 1
        # Supprime quasi-doublons (chevauchement > 80%)
        text = r["text"][:200]
        if any(_overlap(text, t) > 0.8 for t in seen_texts):
            continue
        seen_texts.append(text)
        out.append(r)
    return out


def _overlap(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    tokens_a = set(a.lower().split())
    tokens_b = set(b.lower().split())
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / max(len(tokens_a), len(tokens_b))


def _error_response(message: str, question: str) -> dict[str, Any]:
    return {
        "answer": message, "answer_type": "error", "question": question,
        "sources": [], "citations": [], "warnings": [message],
        "search_method": "", "total_retrieved": 0, "relevant_used": 0,
    }


def _build_sources_list(results: list[dict]) -> list[dict]:
    seen = set()
    sources = []
    for r in results:
        meta = r.get("metadata", {})
        doc_id = meta.get("document_id", "")
        if doc_id and doc_id not in seen:
            seen.add(doc_id)
            source = {"document_id": doc_id}
            for field, label in [("doc_title","title"),("doc_type","type"),
                                   ("doc_number","number"),("doc_date","date"),
                                   ("doc_language","language"),("source_url","url")]:
                val = meta.get(field)
                if val:
                    source[label] = val
            sources.append(source)
    return sources


def _detect_contradictions(results: list[dict]) -> bool:
    return len({r.get("metadata", {}).get("document_id") for r in results
                if r.get("metadata", {}).get("document_id")}) > 1
