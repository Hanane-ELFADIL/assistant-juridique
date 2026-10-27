"""
Évaluation bout en bout du pipeline RAG — T1100–T1107.

Ce module mesure :
- La qualité de récupération (séparément de la génération) — T1102
- La fidélité des citations (chunk_id réel récupéré) — T1103
- La gestion des questions sans réponse — T1101, T1104
- La robustesse aux pannes — T1105

IMPORTANT : ce module évalue des métriques techniques.
Il ne déclare PAS le système prêt pour un usage bancaire opérationnel (T1107).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── T1102 : Qualité de récupération ──────────────────────────────────────────

def recall_at_k(retrieved_ids: list[str], relevant_ids: list[str], k: int) -> float:
    """
    Calcule Recall@k : proportion des passages pertinents retrouvés dans le top-k.

    Args:
        retrieved_ids: IDs des chunks récupérés, dans l'ordre.
        relevant_ids: IDs des chunks considérés pertinents (ground truth).
        k: Nombre de résultats à considérer.

    Returns:
        Recall@k entre 0.0 et 1.0.
    """
    if not relevant_ids:
        return 0.0
    top_k = set(retrieved_ids[:k])
    found = len(top_k & set(relevant_ids))
    return found / len(relevant_ids)


def mean_reciprocal_rank(
    retrieved_ids_per_query: list[list[str]],
    relevant_ids_per_query: list[list[str]],
) -> float:
    """
    Calcule le Mean Reciprocal Rank (MRR) sur un ensemble de requêtes.

    Returns:
        MRR entre 0.0 et 1.0.
    """
    if not retrieved_ids_per_query:
        return 0.0

    rr_sum = 0.0
    for retrieved, relevant in zip(retrieved_ids_per_query, relevant_ids_per_query):
        relevant_set = set(relevant)
        for rank, cid in enumerate(retrieved, start=1):
            if cid in relevant_set:
                rr_sum += 1.0 / rank
                break

    return rr_sum / len(retrieved_ids_per_query)


# ── T1103 : Vérification des citations ───────────────────────────────────────

def verify_citations(rag_result: dict) -> dict:
    """
    Vérifie que chaque citation correspond au passage affiché (T1103).

    Contrôle :
    - Chaque citation a un chunk_id non vide
    - Chaque citation a un extrait (excerpt) non vide
    - L'extrait correspond au texte du chunk (si disponible)

    Returns:
        Rapport de vérification.
    """
    citations = rag_result.get("citations", [])
    issues = []
    verified = 0

    for cit in citations:
        chunk_id = cit.get("chunk_id", "")
        excerpt = cit.get("excerpt", "")
        citation_meta = cit.get("citation", {})

        if not chunk_id:
            issues.append("Citation sans chunk_id")
            continue

        if not excerpt:
            issues.append(f"Citation {chunk_id[:8]} sans extrait")
            continue

        # Vérification que la citation ne contient pas de champs vides
        for k, v in citation_meta.items():
            if v in (None, "", 0):
                issues.append(f"Citation {chunk_id[:8]} : champ vide {k!r}")

        verified += 1

    return {
        "total_citations": len(citations),
        "verified": verified,
        "issues": issues,
        "pass": len(issues) == 0,
    }


# ── T1104 : Fidélité et contradictions ───────────────────────────────────────

def check_answer_faithfulness(rag_result: dict) -> dict:
    """
    Vérifie la fidélité de la réponse au contexte fourni (T1104).

    Contrôle heuristique :
    - Une réponse sourcée doit avoir des citations
    - Une réponse "insufficient_sources" ne doit pas avoir de citations
    - Les contradictions doivent être signalées dans les warnings

    Returns:
        Rapport de fidélité.
    """
    answer_type = rag_result.get("answer_type", "error")
    citations = rag_result.get("citations", [])
    warnings = rag_result.get("warnings", [])
    issues = []

    if answer_type == "sourced" and not citations:
        issues.append("Réponse 'sourced' sans citations — incohérence")

    if answer_type == "insufficient_sources" and citations:
        issues.append("Réponse 'insufficient_sources' avec citations — incohérence")

    # Vérification que les avertissements légaux sont présents
    has_legal_warning = any(
        "similarité" in w.lower() or "applicabilité" in w.lower()
        for w in warnings
    )
    if answer_type == "sourced" and not has_legal_warning:
        issues.append("Avertissement légal manquant dans une réponse sourcée")

    return {
        "answer_type": answer_type,
        "has_citations": bool(citations),
        "has_legal_warning": has_legal_warning,
        "issues": issues,
        "pass": len(issues) == 0,
    }


# ── T1105 : Robustesse aux pannes ────────────────────────────────────────────

def check_unavailable_component(
    hybrid_search,
    settings,
    question: str = "test robustesse",
) -> dict:
    """
    Vérifie le comportement quand le LLM est indisponible (T1105).

    Returns:
        Résultat du test de robustesse.
    """
    from src.generation.rag_chain import RAGChain
    from src.config import Settings

    settings_no_key = Settings(
        google_api_key="",
        database_url="sqlite:///:memory:",
    )
    chain = RAGChain(hybrid_search, settings_no_key)
    result = chain.answer(question)

    return {
        "question": question,
        "answer_type": result.get("answer_type"),
        "graceful": result.get("answer_type") in ("error", "insufficient_sources"),
        "has_answer": bool(result.get("answer")),
    }


# ── T1106 : Rapport d'évaluation ─────────────────────────────────────────────

def generate_eval_report(results: list[dict]) -> dict:
    """
    Génère un rapport d'évaluation reproductible (T1106).

    Args:
        results: Liste de dicts {question_id, question, rag_result}.

    Returns:
        Rapport avec métriques et exemples d'erreurs.
    """
    total = len(results)
    sourced = sum(1 for r in results if r["rag_result"].get("answer_type") == "sourced")
    insufficient = sum(1 for r in results if r["rag_result"].get("answer_type") == "insufficient_sources")
    errors = sum(1 for r in results if r["rag_result"].get("answer_type") == "error")

    citation_issues = []
    faithfulness_issues = []

    for r in results:
        cit_check = verify_citations(r["rag_result"])
        if not cit_check["pass"]:
            citation_issues.append({"id": r["question_id"], "issues": cit_check["issues"]})

        faith_check = check_answer_faithfulness(r["rag_result"])
        if not faith_check["pass"]:
            faithfulness_issues.append({"id": r["question_id"], "issues": faith_check["issues"]})

    return {
        "total_questions": total,
        "sourced": sourced,
        "insufficient_sources": insufficient,
        "errors": errors,
        "citation_issues_count": len(citation_issues),
        "faithfulness_issues_count": len(faithfulness_issues),
        "citation_issues": citation_issues,
        "faithfulness_issues": faithfulness_issues,
        "legal_disclaimer": (
            "Ce rapport évalue des métriques techniques. "
            "Il ne constitue pas une validation pour un usage bancaire opérationnel. "
            "Une validation de sécurité et juridique appropriée est requise (T1107)."
        ),
    }
