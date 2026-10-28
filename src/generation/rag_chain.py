"""
Pipeline RAG — LLM Ollama (local) ou Google, avec streaming.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.request
from typing import Any, Generator, Optional

from src.generation.prompts import (
    CONTRADICTION_WARNING,
    INSUFFICIENT_SOURCES_MESSAGE,
    SYSTEM_PROMPT,
    build_rag_prompt,
)

logger = logging.getLogger(__name__)
MIN_RELEVANCE_SCORE = 0.0
MIN_PASSAGES_FOR_ANSWER = 1

_OUT_OF_SCOPE = [
    "recette", "cuisine", "tajine", "couscous", "météo", "temps qu'il",
    "sport", "foot", "film", "musique", "politique", "ignore tes instructions",
    "ignore your instructions", "oublie tes instructions", "prompt système",
    "system prompt", "donne ton prompt", "forget your instructions",
    "act as", "jailbreak", "droit du travail", "code de commerce",
    "impôts", "fiscal", "immobilier", "autres pays",
]


class LLMError(Exception):
    pass


class RAGChain:

    def __init__(self, hybrid_search, settings=None):
        self._search = hybrid_search
        if settings is None:
            from src.config import get_settings
            settings = get_settings()
        self._settings = settings

    def _is_out_of_scope(self, q: str) -> bool:
        ql = q.lower()
        return any(p in ql for p in _OUT_OF_SCOPE)

    def _generate_ollama(self, prompt: str) -> str:
        """Génération via Ollama local."""
        ollama_url = getattr(self._settings, 'ollama_base_url', 'http://localhost:11434')
        model = getattr(self._settings, 'ollama_llm_model', 'llama3.2:3b')

        body = json.dumps({
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 1024},
        }).encode()
        req = urllib.request.Request(
            f"{ollama_url}/api/generate",
            data=body, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read())
            return data.get("response", "")

    def _generate_google(self, prompt: str) -> str:
        """Génération via Google (fallback)."""
        import google.genai as genai
        client = genai.Client(api_key=self._settings.google_api_key)
        model = self._settings.gemini_model
        for attempt in range(2):
            try:
                r = client.models.generate_content(model=model, contents=prompt)
                return r.text
            except Exception as e:
                if attempt == 0:
                    time.sleep(3)
                    continue
                raise LLMError(str(e)) from e
        raise LLMError("LLM indisponible")

    def _generate(self, prompt: str) -> str:
        """Essaie Ollama d'abord, puis Google en fallback."""
        llm_mode = getattr(self._settings, 'llm_mode', 'ollama')

        if llm_mode == "ollama":
            try:
                return self._generate_ollama(prompt)
            except Exception as e:
                logger.warning("Ollama indisponible (%s), fallback Google.", e)
                if self._settings.google_api_key:
                    return self._generate_google(prompt)
                raise LLMError(f"Ollama indisponible : {e}") from e
        else:
            try:
                return self._generate_google(prompt)
            except Exception as e:
                raise LLMError(str(e)) from e

    def answer(self, question: str, n_context_chunks: Optional[int] = None,
               filters: Optional[dict] = None) -> dict[str, Any]:
        question = question.strip()

        if not question:
            return _err("Question vide.", question)
        if len(question) > self._settings.max_query_length:
            return _err(f"Question trop longue (max {self._settings.max_query_length}).", question)
        if self._is_out_of_scope(question):
            return {
                "answer": (
                    "Je suis uniquement en mesure de répondre aux questions relatives "
                    "aux textes législatifs et réglementaires de Bank Al-Maghrib.\n\n"
                    "Cette question est hors de mon périmètre."
                ),
                "answer_type": "out_of_scope",
                "question": question,
                "sources": [], "citations": [], "warnings": [],
                "search_method": "", "total_retrieved": 0, "relevant_used": 0,
            }

        n = n_context_chunks or self._settings.max_context_chunks
        search = self._search.search(query=question, n_results=n, filters=filters)
        all_results = search.get("results", [])
        relevant = [r for r in all_results if r.get("score", 0) >= MIN_RELEVANCE_SCORE]
        relevant = _deduplicate(relevant)

        if len(relevant) < MIN_PASSAGES_FOR_ANSWER:
            return {
                "answer": INSUFFICIENT_SOURCES_MESSAGE,
                "answer_type": "insufficient_sources",
                "question": question,
                "sources": [], "citations": [],
                "warnings": search.get("warnings", []),
                "search_method": search.get("search_method", ""),
                "total_retrieved": len(all_results), "relevant_used": 0,
            }

        context = [{"text": r["text"], "citation": r["citation"], "chunk_id": r["chunk_id"]}
                   for r in relevant]
        prompt = f"{SYSTEM_PROMPT}\n\n{build_rag_prompt(question, context)}"

        try:
            answer_text = self._generate(prompt)
            answer_type = "sourced"
        except LLMError as e:
            logger.error("LLM error: %s", e)
            answer_text = (
                "⚠️ **Service de génération indisponible.**\n\n"
                "Voici les passages pertinents trouvés :\n\n" +
                "\n\n---\n\n".join(
                    f"**[{i+1}] {r['citation'].get('article','')}** "
                    f"({r['citation'].get('title','')[:40]})\n\n{r['text'][:500]}"
                    for i, r in enumerate(relevant[:5])
                )
            )
            answer_type = "degraded"
        except Exception as e:
            logger.error("Unexpected error: %s", e)
            return _err(str(e), question)

        citations = []
        seen = set()
        for r in relevant:
            if r["chunk_id"] not in seen:
                seen.add(r["chunk_id"])
                cit = r["citation"]
                if cit.get("title") or cit.get("article"):
                    citations.append({
                        "chunk_id": r["chunk_id"],
                        "citation": cit,
                        "excerpt": r["text"][:500] + ("…" if len(r["text"]) > 500 else ""),
                        "score": r["score"],
                        "rank": r["rank"],
                    })

        warnings = list(search.get("warnings", []))
        if _detect_contradictions(relevant):
            warnings.append(CONTRADICTION_WARNING)

        return {
            "answer": answer_text,
            "answer_type": answer_type,
            "question": question,
            "sources": _sources(relevant),
            "citations": citations,
            "warnings": warnings,
            "search_method": search.get("search_method", ""),
            "total_retrieved": len(all_results),
            "relevant_used": len(relevant),
        }


def _deduplicate(results: list[dict], max_per_article: int = 2) -> list[dict]:
    seen_art: dict = {}
    seen_txt: list = []
    out = []
    for r in results:
        art = r.get("metadata", {}).get("article_number", "")
        if art and seen_art.get(art, 0) >= max_per_article:
            continue
        t = r["text"][:150]
        if any(_overlap(t, s) > 0.75 for s in seen_txt):
            continue
        if art:
            seen_art[art] = seen_art.get(art, 0) + 1
        seen_txt.append(t)
        out.append(r)
    return out


def _overlap(a: str, b: str) -> float:
    ta, tb = set(a.lower().split()), set(b.lower().split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta), len(tb))


def _err(msg: str, q: str) -> dict:
    return {"answer": msg, "answer_type": "error", "question": q,
            "sources": [], "citations": [], "warnings": [msg],
            "search_method": "", "total_retrieved": 0, "relevant_used": 0}


def _sources(results: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for r in results:
        meta = r.get("metadata", {})
        did = meta.get("document_id", "")
        if did and did not in seen:
            seen.add(did)
            src = {"document_id": did}
            for f, l in [("doc_title","title"),("doc_type","type"),
                          ("doc_number","number"),("doc_date","date"),
                          ("source_url","url")]:
                if meta.get(f):
                    src[l] = meta[f]
            out.append(src)
    return out


def _detect_contradictions(results: list[dict]) -> bool:
    return len({r.get("metadata", {}).get("document_id")
                for r in results if r.get("metadata", {}).get("document_id")}) > 1
