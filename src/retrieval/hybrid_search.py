"""
Recherche hybride — fusion vectorielle + BM25 via RRF — T500–T505, T507.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

from src.retrieval.bm25_index import BM25Index
from src.vectorstore.chroma_store import ChromaVectorStore

logger = logging.getLogger(__name__)

# Constante RRF (Reciprocal Rank Fusion) — T502
RRF_K = 60


def reciprocal_rank_fusion(
    results_a: list[dict],
    results_b: list[dict],
    weight_a: float = 0.6,
    weight_b: float = 0.4,
) -> list[dict]:
    """
    Fusionne deux listes de résultats via RRF (T502).
    
    RRF score = sum(weight / (k + rank))
    
    Args:
        results_a: Résultats vectoriels (poids plus élevé).
        results_b: Résultats BM25.
        weight_a: Poids de la liste A (vectoriel).
        weight_b: Poids de la liste B (BM25).
    
    Returns:
        Liste fusionnée et triée par score RRF décroissant.
    """
    scores: dict[str, float] = {}
    data: dict[str, dict] = {}

    for result in results_a:
        cid = result["chunk_id"]
        rank = result.get("rank", 1)
        scores[cid] = scores.get(cid, 0.0) + weight_a / (RRF_K + rank)
        data[cid] = result

    for result in results_b:
        cid = result["chunk_id"]
        rank = result.get("rank", 1)
        scores[cid] = scores.get(cid, 0.0) + weight_b / (RRF_K + rank)
        if cid not in data:
            data[cid] = result

    fused = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    output = []
    for rank, (cid, rrf_score) in enumerate(fused, start=1):
        item = dict(data[cid])
        item["rrf_score"] = round(rrf_score, 6)
        item["rank"] = rank
        output.append(item)

    return output


class HybridSearch:
    """
    Moteur de recherche hybride combinant vectoriel (ChromaDB) et lexical (BM25).
    
    Avertissement important (T505) : la similarité sémantique indique une
    pertinence textuelle probable, PAS une applicabilité juridique.
    """

    # Avertissement systématique affiché avec chaque résultat (T505)
    LEGAL_WARNING = (
        "⚠️ Ces résultats sont classés par similarité textuelle, "
        "non par applicabilité juridique. Vérifiez toujours les sources officielles."
    )

    def __init__(
        self,
        vector_store: ChromaVectorStore,
        bm25_index: BM25Index,
        top_k: int = 10,
    ):
        self._vector_store = vector_store
        self._bm25 = bm25_index
        self._top_k = top_k

    def search(
        self,
        query: str,
        n_results: Optional[int] = None,
        filters: Optional[dict] = None,
    ) -> dict[str, Any]:
        """
        Effectue une recherche hybride (T500–T504).
        
        Args:
            query: Question en langage naturel ou référence exacte.
            n_results: Nombre de résultats (défaut: top_k de la config).
            filters: Filtres sur les métadonnées (T503).
                     Ex: {"doc_type": "circulaire"} ou {"article_number": "3"}
        
        Returns:
            Dict avec résultats, scores, métadonnées et avertissements.
        """
        if not query or not query.strip():
            return {"results": [], "warnings": ["Requête vide."], "query": query}

        n = n_results or self._top_k
        query = query.strip()

        # Détection de recherche par référence exacte (T504)
        article_ref = _extract_article_reference(query)
        if article_ref:
            filters = filters or {}
            filters["article_number"] = article_ref
            logger.info("Référence d'article détectée : %r", article_ref)

        # Recherche vectorielle (T500)
        vector_results = []
        try:
            vector_results = self._vector_store.query(
                query_text=query,
                n_results=n,
                where=filters,
            )
        except Exception as e:
            logger.error("Erreur recherche vectorielle : %s", e)

        # Recherche BM25 (T501)
        bm25_results = []
        if self._bm25.size > 0:
            try:
                bm25_results = self._bm25.search(query, n_results=n)
            except Exception as e:
                logger.error("Erreur recherche BM25 : %s", e)

        # Fusion RRF (T502)
        if vector_results and bm25_results:
            fused = reciprocal_rank_fusion(vector_results, bm25_results)
        elif vector_results:
            fused = vector_results
        else:
            fused = bm25_results

        fused = fused[:n]

        # Enrichissement des résultats (T507)
        enriched = []
        for item in fused:
            meta = item.get("metadata", {})
            enriched.append({
                "chunk_id": item["chunk_id"],
                "text": item["text"],
                "score": item.get("rrf_score", item.get("score", 0.0)),
                "rank": item["rank"],
                # Citation vérifiable (T605)
                "citation": _build_citation(meta),
                "metadata": meta,
            })

        warnings = [self.LEGAL_WARNING]
        if not vector_results and not bm25_results:
            warnings.append("Aucun résultat trouvé pour cette requête.")
        elif not bm25_results:
            warnings.append("Recherche BM25 indisponible — résultats vectoriels uniquement.")

        return {
            "query": query,
            "results": enriched,
            "total_found": len(enriched),
            "search_method": _describe_method(bool(vector_results), bool(bm25_results)),
            "warnings": warnings,
        }


def _extract_article_reference(query: str) -> Optional[str]:
    """
    Détecte si la requête contient une référence à un article spécifique (T504).
    Ex: "article 3", "art. 12", "المادة 5"
    """
    patterns = [
        re.compile(r"\barticle\s+(\d+)\b", re.IGNORECASE),
        re.compile(r"\bart\.?\s*(\d+)\b", re.IGNORECASE),
        re.compile(r"\bالمادة\s+(\d+)\b"),
    ]
    for p in patterns:
        m = p.search(query)
        if m:
            return m.group(1)
    return None


def _build_citation(meta: dict) -> dict:
    """
    Construit une citation vérifiable depuis les métadonnées (T605).
    N'inclut que les champs non vides — ne fabrique rien.
    """
    citation = {}
    if meta.get("doc_title"):
        citation["title"] = meta["doc_title"]
    if meta.get("doc_type"):
        citation["type"] = meta["doc_type"]
    if meta.get("doc_number"):
        citation["number"] = meta["doc_number"]
    if meta.get("doc_date"):
        citation["date"] = meta["doc_date"]
    if meta.get("article_number"):
        citation["article"] = f"Article {meta['article_number']}"
    if meta.get("chapter"):
        citation["chapter"] = meta["chapter"]
    if meta.get("page_start"):
        citation["page"] = meta["page_start"]
    if meta.get("source_url"):
        citation["url"] = meta["source_url"]
    return citation


def _describe_method(has_vector: bool, has_bm25: bool) -> str:
    if has_vector and has_bm25:
        return "hybrid (vectoriel + BM25, fusion RRF)"
    if has_vector:
        return "vectoriel uniquement"
    if has_bm25:
        return "BM25 uniquement"
    return "aucune"
