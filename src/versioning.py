"""
Actualité et gestion des versions des documents — T1000–T1007.

Règle invariante : le système ne détermine JAMAIS automatiquement
qu'un texte est abrogé ou applicable sans source officielle vérifiée.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from src.models.document import Document, VerificationStatus

logger = logging.getLogger(__name__)


# ── T1000 : Dates de collecte et vérification ────────────────────────────────

def get_collection_date(doc: Document) -> Optional[datetime]:
    """Retourne la date de collecte du document (T1000)."""
    return doc.collected_at


def get_last_verified_date(doc: Document) -> Optional[datetime]:
    """Retourne la date de dernière vérification (T1000)."""
    return doc.last_verified_at


def mark_verified(doc: Document, db: Session) -> Document:
    """
    Marque un document comme vérifié à la date actuelle (T1000).
    La vérification doit être effectuée par un humain — cette fonction
    n'affirme pas que le texte est en vigueur, seulement qu'il a été
    vérifié à cette date.
    """
    doc.last_verified_at = datetime.now(timezone.utc)
    doc.verification_status = VerificationStatus.VERIFIED.value
    db.commit()
    db.refresh(doc)
    logger.info("Document %r marqué comme vérifié le %s.", doc.id, doc.last_verified_at)
    return doc


def mark_outdated(doc: Document, db: Session, reason: str = "") -> Document:
    """Marque un document comme potentiellement dépassé (T1000)."""
    doc.verification_status = VerificationStatus.OUTDATED.value
    if reason:
        logger.warning("Document %r marqué comme dépassé : %s", doc.id, reason)
    db.commit()
    db.refresh(doc)
    return doc


# ── T1001 : Détection de changements par empreinte ───────────────────────────

def check_file_changed(doc: Document, settings=None) -> bool:
    """
    Détecte si le fichier PDF a changé depuis l'import (T1001).
    Compare l'empreinte SHA-256 stockée avec celle du fichier actuel.

    Returns:
        True si le fichier a changé, False sinon.
    """
    if settings is None:
        from src.config import get_settings
        settings = get_settings()

    raw_path = settings.raw_dir / doc.filename
    if not raw_path.exists():
        logger.warning("Fichier manquant pour le document %r : %s", doc.id, raw_path)
        return True  # absent = changé

    from src.ingestion.fingerprint import sha256_file
    current_sha256 = sha256_file(raw_path)
    changed = current_sha256 != doc.file_sha256

    if changed:
        logger.warning(
            "Empreinte modifiée pour %r : stockée=%s, actuelle=%s",
            doc.id, doc.file_sha256[:16], current_sha256[:16],
        )
    return changed


# ── T1002 : Conservation des versions historiques ────────────────────────────

def archive_document_version(doc: Document, settings=None) -> Optional[Path]:
    """
    Archive le fichier actuel avant mise à jour (T1002).
    Crée une copie horodatée dans data/raw/archive/.
    Les versions historiques ne sont jamais écrasées silencieusement.

    Returns:
        Chemin du fichier archivé, ou None si le fichier n'existe pas.
    """
    if settings is None:
        from src.config import get_settings
        settings = get_settings()

    import shutil
    raw_path = settings.raw_dir / doc.filename
    if not raw_path.exists():
        return None

    archive_dir = settings.raw_dir / "archive"
    archive_dir.mkdir(exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    stem = raw_path.stem
    suffix = raw_path.suffix
    archive_path = archive_dir / f"{stem}_{ts}{suffix}"

    shutil.copy2(str(raw_path), str(archive_path))
    logger.info("Version archivée : %s → %s", raw_path.name, archive_path.name)
    return archive_path


# ── T1003 : Marquage des documents non vérifiés ──────────────────────────────

def get_unverified_documents(db: Session) -> list[Document]:
    """
    Retourne les documents dont le statut juridique n'a pas été vérifié (T1003).
    Ces documents ne doivent pas être présentés comme étant en vigueur.
    """
    return (
        db.query(Document)
        .filter(Document.verification_status == VerificationStatus.UNVERIFIED.value)
        .all()
    )


def get_verification_warning(doc: Document) -> Optional[str]:
    """
    Retourne l'avertissement approprié selon le statut de vérification (T1003).
    Délègue au modèle Document.
    """
    return doc.verification_warning


# ── T1004 : Dates multiples ───────────────────────────────────────────────────

def get_dates_summary(doc: Document) -> dict:
    """
    Retourne un résumé des dates disponibles pour un document (T1004).
    Distingue : publication, entrée en vigueur, collecte, vérification.
    Ne génère aucune date manquante.
    """
    summary: dict = {
        "publication_date": (
            doc.publication_date.isoformat() if doc.publication_date else None
        ),
        "entry_into_force_date": (
            doc.entry_into_force_date.isoformat()
            if doc.entry_into_force_date else None
        ),
        "collected_at": (
            doc.collected_at.isoformat() if doc.collected_at else None
        ),
        "last_verified_at": (
            doc.last_verified_at.isoformat() if doc.last_verified_at else None
        ),
        "verification_status": doc.verification_status,
    }
    # Signale les dates manquantes sans les inventer
    missing = [k for k, v in summary.items() if v is None and k != "verification_status"]
    if missing:
        summary["_missing_dates"] = missing
        logger.debug("Dates manquantes pour %r : %s", doc.id, missing)
    return summary


# ── T1005 : Rapport sur les documents à vérifier ────────────────────────────

def generate_staleness_report(db: Session, settings=None) -> dict:
    """
    Rapport sur les documents anciens, manquants ou à reverifier (T1005).
    N'affirme jamais qu'un texte est abrogé ou applicable (T1006).
    """
    if settings is None:
        from src.config import get_settings
        settings = get_settings()

    docs = db.query(Document).all()
    now = datetime.now(timezone.utc)

    report = {
        "generated_at": now.isoformat(),
        "total_documents": len(docs),
        "by_status": {},
        "missing_files": [],
        "never_verified": [],
        "file_changed": [],
        "legal_disclaimer": (
            "Ce rapport est informatif uniquement. "
            "Le statut juridique (en vigueur, abrogé, modifié) "
            "doit être vérifié manuellement sur les sources officielles."
        ),
    }

    for status in VerificationStatus:
        count = sum(1 for d in docs if d.verification_status == status.value)
        report["by_status"][status.value] = count

    for doc in docs:
        raw_path = settings.raw_dir / doc.filename
        if not raw_path.exists():
            report["missing_files"].append({
                "id": doc.id, "title": doc.title, "filename": doc.filename,
            })

        if doc.last_verified_at is None:
            report["never_verified"].append({
                "id": doc.id, "title": doc.title,
                "collected_at": doc.collected_at.isoformat() if doc.collected_at else None,
            })

        if raw_path.exists() and check_file_changed(doc, settings):
            report["file_changed"].append({
                "id": doc.id, "title": doc.title, "filename": doc.filename,
            })

    return report
