"""
Schémas Pydantic pour les requêtes et réponses de l'API — T703.
"""
from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator


# === Requêtes ===

class ChatRequest(BaseModel):
    """Requête de question-réponse."""
    question: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Question en langage naturel sur les textes BAM.",
        examples=["Quelles sont les conditions de capital minimum pour les banques ?"],
    )
    n_results: Optional[int] = Field(
        default=None,
        ge=1,
        le=20,
        description="Nombre de passages de contexte à utiliser (optionnel).",
    )
    filters: Optional[dict[str, str]] = Field(
        default=None,
        description="Filtres sur les métadonnées (ex: {\"doc_type\": \"circulaire\"}).",
    )

    @field_validator("question")
    @classmethod
    def sanitize_question(cls, v: str) -> str:
        return v.strip()


# === Réponses ===

class CitationResponse(BaseModel):
    """Citation vérifiable liée à un chunk source."""
    chunk_id: str
    citation: dict[str, Any] = Field(description="Référence : titre, type, numéro, article, page, URL.")
    excerpt: str = Field(description="Extrait du passage source (max 300 caractères).")
    score: float = Field(description="Score de pertinence.")
    rank: int = Field(description="Rang dans les résultats de recherche.")


class SourceResponse(BaseModel):
    """Document source utilisé pour la réponse."""
    document_id: str
    title: Optional[str] = None
    type: Optional[str] = None
    number: Optional[str] = None
    date: Optional[str] = None
    language: Optional[str] = None
    url: Optional[str] = None


class ChatResponse(BaseModel):
    """Réponse structurée à une question."""
    answer: str = Field(description="Réponse synthétique fondée sur les sources.")
    answer_type: str = Field(
        description="Type de réponse : 'sourced', 'insufficient_sources', 'error'.",
    )
    question: str
    sources: list[SourceResponse] = Field(
        default_factory=list,
        description="Liste des documents sources utilisés.",
    )
    citations: list[CitationResponse] = Field(
        default_factory=list,
        description="Citations vérifiables avec extraits.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Avertissements juridiques et techniques.",
    )
    search_method: str = Field(default="", description="Méthode de recherche utilisée.")
    total_retrieved: int = Field(default=0)
    relevant_used: int = Field(default=0)


class HealthResponse(BaseModel):
    """Réponse du endpoint de santé."""
    status: str
    version: str = "0.1.0"
    components: dict[str, str] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """Réponse d'erreur standardisée."""
    error: str
    detail: Optional[str] = None
    status_code: int
