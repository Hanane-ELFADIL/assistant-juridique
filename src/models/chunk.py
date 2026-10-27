"""
Modèle Chunk — T300
Unité de texte indexable avec provenance complète.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class Chunk(Base):
    """
    Fragment de texte extrait d'un document juridique.
    
    Chaque chunk est lié à son document source et conserve
    la hiérarchie complète : document → chapitre → article → alinéa.
    """
    __tablename__ = "chunks"

    # Identifiant unique du chunk
    chunk_id: Mapped[str] = mapped_column(String(128), primary_key=True)

    # Lien vers le document source (T304)
    document_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Contenu
    text: Mapped[str] = mapped_column(Text, nullable=False)
    text_length: Mapped[int] = mapped_column(Integer, default=0)

    # Position dans le document (T201, T304)
    page_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    page_end: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    page_printed: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
        comment="Numéro de page imprimé dans le document (peut différer du PDF)",
    )

    # Hiérarchie juridique (T304)
    chapter: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    section: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    article_number: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="Numéro d'article (ex: '3', 'Article 3', 'Art. 3')",
    )
    paragraph_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Métadonnées héritées du document (dénormalisées pour les filtres)
    doc_title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    doc_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    doc_number: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    doc_date: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    doc_language: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Chunking (T302, T305)
    chunk_index: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Index du sous-chunk dans l'article parent (0 si article complet)",
    )
    parent_chunk_id: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        comment="ID du chunk parent pour les sous-chunks (T305)",
    )
    is_sub_chunk: Mapped[bool] = mapped_column(
        default=False,
        comment="True si ce chunk est un sous-découpage d'un article",
    )
    overlap_chars: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="Nombre de caractères de chevauchement avec le chunk précédent",
    )

    # Qualité
    extraction_method: Mapped[str] = mapped_column(
        String(32),
        default="legal",
        comment="Méthode utilisée : 'legal' ou 'fallback'",
    )
    has_warnings: Mapped[bool] = mapped_column(default=False)

    # Relation
    document: Mapped["Document"] = relationship(  # type: ignore[name-defined]
        "Document",
        back_populates="chunks",
    )

    def __repr__(self) -> str:
        return (
            f"<Chunk id={self.chunk_id!r} doc={self.document_id!r} "
            f"art={self.article_number!r} p={self.page_start}>"
        )

    def to_metadata_dict(self) -> dict:
        """
        Retourne les métadonnées sous forme de dict plat pour ChromaDB.
        ChromaDB n'accepte que str, int, float, bool — pas de None.
        """
        return {
            "document_id": self.document_id or "",
            "doc_title": self.doc_title or "",
            "doc_type": self.doc_type or "",
            "doc_number": self.doc_number or "",
            "doc_date": self.doc_date or "",
            "doc_language": self.doc_language or "fr",
            "source_url": self.source_url or "",
            "chapter": self.chapter or "",
            "section": self.section or "",
            "article_number": self.article_number or "",
            "paragraph_number": self.paragraph_number if self.paragraph_number is not None else 0,
            "page_start": self.page_start if self.page_start is not None else 0,
            "page_end": self.page_end if self.page_end is not None else 0,
            "page_printed": self.page_printed or "",
            "chunk_index": self.chunk_index,
            "parent_chunk_id": self.parent_chunk_id or "",
            "is_sub_chunk": self.is_sub_chunk,
            "extraction_method": self.extraction_method or "legal",
        }
