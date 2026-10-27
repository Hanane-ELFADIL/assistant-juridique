"""
Index BM25 pour la recherche lexicale — T501.
Construit sur le corpus complet des chunks en mémoire.
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> list[str]:
    """
    Tokenisation simple pour français et arabe.
    Conserve les chiffres pour les numéros d'articles.
    """
    text = text.lower()
    # Garde les lettres latines, arabes et les chiffres
    tokens = re.findall(r"[\w\u0600-\u06FF]+", text)
    # Supprime les stop-words français les plus fréquents
    FR_STOPWORDS = {
        "le", "la", "les", "de", "du", "des", "un", "une", "et", "en",
        "au", "aux", "à", "ce", "se", "sa", "son", "ses", "qui", "que",
        "qu", "il", "ils", "elle", "elles", "on", "nous", "vous", "est",
        "sont", "par", "pour", "sur", "dans", "avec", "ou", "mais", "ne",
        "pas", "plus", "tel", "tels", "telle", "telles", "tout", "tous",
    }
    return [t for t in tokens if len(t) > 1 and t not in FR_STOPWORDS]


class BM25Index:
    """
    Index BM25 sur le corpus des chunks (T501).
    
    Utilise rank-bm25 si disponible, sinon TF-IDF sklearn comme fallback.
    """

    def __init__(self):
        self._corpus_ids: list[str] = []
        self._corpus_texts: list[str] = []
        self._corpus_metas: list[dict] = []
        self._bm25 = None
        self._tokenized_corpus: list[list[str]] = []

    def build(
        self,
        chunk_ids: list[str],
        texts: list[str],
        metadatas: list[dict],
    ) -> None:
        """
        Construit l'index BM25 à partir du corpus.
        
        Args:
            chunk_ids: IDs des chunks.
            texts: Textes des chunks.
            metadatas: Métadonnées associées.
        """
        if not texts:
            logger.warning("Corpus vide — index BM25 non construit.")
            return

        self._corpus_ids = chunk_ids
        self._corpus_texts = texts
        self._corpus_metas = metadatas
        self._tokenized_corpus = [_tokenize(t) for t in texts]

        try:
            from rank_bm25 import BM25Okapi  # type: ignore
            self._bm25 = BM25Okapi(self._tokenized_corpus)
            logger.info("Index BM25 (rank-bm25) construit sur %d chunks.", len(texts))
        except ImportError:
            logger.warning(
                "rank-bm25 non disponible — fallback TF-IDF sklearn utilisé."
            )
            self._bm25 = None

    def search(self, query: str, n_results: int = 10) -> list[dict[str, Any]]:
        """
        Recherche lexicale BM25 (T501).
        
        Args:
            query: Requête textuelle.
            n_results: Nombre de résultats.
        
        Returns:
            Liste de dicts {chunk_id, text, metadata, score, rank}.
        """
        if not self._corpus_ids:
            return []

        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        if self._bm25 is not None:
            scores = self._bm25.get_scores(query_tokens)
        else:
            scores = self._tfidf_scores(query_tokens)

        # Tri par score décroissant
        ranked = sorted(
            enumerate(scores), key=lambda x: x[1], reverse=True
        )[:n_results]

        results = []
        for rank, (idx, score) in enumerate(ranked, start=1):
            if score <= 0:
                continue
            results.append({
                "chunk_id": self._corpus_ids[idx],
                "text": self._corpus_texts[idx],
                "metadata": self._corpus_metas[idx],
                "score": round(float(score), 4),
                "rank": rank,
            })

        return results

    def _tfidf_scores(self, query_tokens: list[str]) -> list[float]:
        """
        Fallback TF-IDF simple si rank-bm25 n'est pas disponible.
        """
        import math
        N = len(self._tokenized_corpus)
        scores = [0.0] * N

        for token in query_tokens:
            # IDF
            df = sum(1 for doc in self._tokenized_corpus if token in doc)
            if df == 0:
                continue
            idf = math.log((N - df + 0.5) / (df + 0.5) + 1)
            # TF
            for i, doc in enumerate(self._tokenized_corpus):
                tf = doc.count(token) / max(len(doc), 1)
                scores[i] += idf * tf

        return scores

    @property
    def size(self) -> int:
        return len(self._corpus_ids)
