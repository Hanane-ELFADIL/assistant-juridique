"""
Modèle Document — T100
Métadonnées complètes pour chaque document juridique importé.
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class VerificationStatus(str, enum.Enum):
    """Statut de vérification de l'actualité du document."""
    UNVERIFIED = "unverified"      # Jamais vérifié
    VERIFIED = "verified"          # Vérifié comme en vigueur
    OUTDATED = "outdated"          # Version plus récente connue
    ABROGATED = "abrogated"        # Abrogé selon source officielle
    UNKNOWN = "unknown"            # Statut inconnu


class TextType(str, enum.Enum):
    """Types de textes législatifs et réglementaires BAM."""
    LOI = "loi"
    DAHIR = "dahir"
    DECRET = "decret"
    ARRETE = "arrete"
    CIRCULAIRE = "circulaire"
    INSTRUCTION = "instruction"
    NOTE = "note"
    DIRECTIVE = "directive"
    REGLEMENT = "reglement"
    AUTRE = "autre"
    INCONNU = "inconnu"


class Document(Base):
    """
    Représente un document juridique importé dans le système.
    
    Règle fondamentale : ce modèle ne contient que des données
    vérifiables extraites du document lui-même ou de sa source.
    Aucune information juridique n'est inférée.
    """
    __tablename__ = "documents"

    # Identifiant interne
    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    # Identification du texte
    title: Mapped[str] = mapped_column(Text, nullable=False)
    text_type: Mapped[str] = mapped_column(
        String(32),
        default=TextType.INCONNU.value,
        nullable=False,
    )
    text_number: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        comment="Numéro officiel du texte (ex: 34-03, n°2021-01)",
    )
    publication_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="Date de publication selon le document",
    )
    entry_into_force_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="Date d'entrée en vigueur si explicitement indiquée",
    )
    language: Mapped[str] = mapped_column(
        String(8),
        default="fr",
        nullable=False,
        comment="Code langue ISO 639-1 (fr, ar, fr-ar)",
    )

    # Provenance et fichier
    source_url: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="URL officielle de la source",
    )
    filename: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Nom du fichier tel que stocké dans data/raw/",
    )
    file_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        comment="Empreinte SHA-256 du fichier original",
    )
    file_size_bytes: Mapped[int] = mapped_column(nullable=False, default=0)

    # Dates de gestion
    collected_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        nullable=False,
        comment="Date de collecte/import dans le système",
    )
    last_verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="Dernière vérification de l'actualité du texte",
    )
    verification_status: Mapped[str] = mapped_column(
        String(32),
        default=VerificationStatus.UNVERIFIED.value,
        nullable=False,
    )

    # Qualité de l'extraction
    is_scanned: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="True si le PDF est un scan (OCR nécessaire)",
    )
    extraction_warnings: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Avertissements JSON de l'extraction",
    )
    total_pages: Mapped[int] = mapped_column(default=0, nullable=False)
    pages_with_text: Mapped[int] = mapped_column(default=0, nullable=False)
    pages_without_text: Mapped[int] = mapped_column(default=0, nullable=False)

    # Relations
    chunks: Mapped[list] = relationship(
        "Chunk",
        back_populates="document",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Document id={self.id!r} title={self.title!r} type={self.text_type!r}>"

    @property
    def is_verified_current(self) -> bool:
        """True uniquement si le statut est explicitement 'verified'."""
        return self.verification_status == VerificationStatus.VERIFIED.value

    @property
    def verification_warning(self) -> str | None:
        """Retourne un avertissement si le document n'est pas vérifié."""
        if self.verification_status == VerificationStatus.UNVERIFIED.value:
            return (
                "Ce document n'a pas été vérifié comme étant actuellement en vigueur. "
                "Consultez la source officielle pour confirmer son statut."
            )
        if self.verification_status == VerificationStatus.OUTDATED.value:
            return "Une version plus récente de ce document pourrait exister."
        if self.verification_status == VerificationStatus.ABROGATED.value:
            return "Ce texte a été signalé comme abrogé. Ne pas l'utiliser comme référence en vigueur."
        return None
