"""
Endpoint de question-réponse RAG — T702–T706.
"""
from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request, status

from src.api.schemas import ChatRequest, ChatResponse, CitationResponse, SourceResponse

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_rag_chain(request: Request):
    """Récupère le RAGChain depuis le state de l'application."""
    chain = getattr(request.app.state, "rag_chain", None)
    if chain is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Le pipeline RAG n'est pas initialisé. Veuillez d'abord indexer des documents.",
        )
    return chain


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Poser une question sur les textes juridiques BAM",
    tags=["RAG"],
    responses={
        503: {"description": "Pipeline RAG non initialisé"},
        422: {"description": "Requête invalide"},
        500: {"description": "Erreur interne"},
    },
)
async def chat(
    request: Request,
    body: ChatRequest,
) -> ChatResponse:
    """
    Répond à une question en langage naturel en utilisant les textes indexés.
    
    - La réponse est fondée **uniquement** sur les passages récupérés.
    - Chaque citation est vérifiable : titre, type, numéro, article, page, URL.
    - Un avertissement est affiché si les sources sont insuffisantes.
    - Les textes juridiques sont traités comme données, pas comme instructions.
    """
    start_time = time.monotonic()
    rag_chain = _get_rag_chain(request)

    # Journalisation sans contenu sensible (T706)
    logger.info(
        "Requête /api/chat — question_length=%d n_results=%s",
        len(body.question),
        body.n_results,
    )

    try:
        result = rag_chain.answer(
            question=body.question,
            n_context_chunks=body.n_results,
            filters=body.filters,
        )
    except Exception as e:
        logger.error("Erreur RAG chain : %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Une erreur interne est survenue lors du traitement de la requête.",
        )

    elapsed = round(time.monotonic() - start_time, 3)
    logger.info(
        "Réponse générée en %.3fs — type=%s sources=%d",
        elapsed,
        result.get("answer_type"),
        len(result.get("sources", [])),
    )

    # Construction de la réponse typée
    citations = [
        CitationResponse(**c) for c in result.get("citations", [])
    ]
    sources = [
        SourceResponse(**s) for s in result.get("sources", [])
    ]

    return ChatResponse(
        answer=result["answer"],
        answer_type=result.get("answer_type", "error"),
        question=result["question"],
        sources=sources,
        citations=citations,
        warnings=result.get("warnings", []),
        search_method=result.get("search_method", ""),
        total_retrieved=result.get("total_retrieved", 0),
        relevant_used=result.get("relevant_used", 0),
    )
