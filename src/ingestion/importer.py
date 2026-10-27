"""
Import manuel de PDFs locaux — T101, T105.
Copie le PDF vers data/raw/, calcule l'empreinte, enregistre les métadonnées.
"""
from __future__ import annotations

import json
import logging
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from src.config import get_settings
from src.ingestion.fingerprint import safe_filename, sha256_file
from src.models.document import Document, TextType, VerificationStatus

logger = logging.getLogger(__name__)


class DuplicateDocumentError(Exception):
    """Levée quand un document avec la même empreinte existe déjà."""
    def __init__(self, existing_id: str, sha256: str):
        self.existing_id = existing_id
        self.sha256 = sha256
        super().__init__(
            f"Document avec SHA-256 {sha256!r} déjà présent (id={existing_id!r})."
        )


class InvalidPDFError(Exception):
    """Levée quand le fichier n'est pas un PDF valide."""
    pass


def _detect_scanned_pdf(path: Path) -> tuple[bool, list[str]]:
    """
    Détecte rapidement si un PDF est probablement scanné (T106).
    Retourne (is_scanned, warnings).
    Nécessite PyMuPDF — retourne (False, []) si non disponible.
    """
    try:
        import pymupdf  # type: ignore
    except ImportError:
        logger.warning("PyMuPDF non installé — détection scan ignorée.")
        return False, []

    warnings: list[str] = []
    is_scanned = False
    try:
        doc = pymupdf.open(str(path))
        total = len(doc)
        empty_pages = 0
        for page in doc:
            text = page.get_text("text").strip()
            if len(text) < 20:
                empty_pages += 1
        doc.close()
        if total > 0 and empty_pages / total > 0.5:
            is_scanned = True
            warnings.append(
                f"{empty_pages}/{total} pages sans texte exploitable — "
                "PDF probablement scanné. OCR recommandé."
            )
    except Exception as e:
        warnings.append(f"Impossible d'analyser le PDF pour détecter un scan : {e}")
    return is_scanned, warnings


def import_pdf(
    source_path: Path | str,
    db: Session,
    *,
    title: Optional[str] = None,
    text_type: str = TextType.INCONNU.value,
    text_number: Optional[str] = None,
    publication_date: Optional[datetime] = None,
    source_url: Optional[str] = None,
    language: str = "fr",
    overwrite: bool = False,
) -> Document:
    """
    Importe un PDF local dans le système.
    
    - Valide la taille et le type MIME.
    - Calcule l'empreinte SHA-256.
    - Détecte les doublons.
    - Copie le fichier vers data/raw/ sans modification.
    - Enregistre les métadonnées en base.
    
    Args:
        source_path: Chemin du fichier PDF à importer.
        db: Session SQLAlchemy.
        title: Titre du document (déduit du nom de fichier si absent).
        text_type: Type de texte (loi, dahir, circulaire…).
        text_number: Numéro officiel du texte.
        publication_date: Date de publication.
        source_url: URL officielle source.
        language: Code langue ISO 639-1.
        overwrite: Si True, réimporte même si un doublon existe.
    
    Returns:
        L'objet Document créé ou existant.
    
    Raises:
        FileNotFoundError: Fichier source introuvable.
        InvalidPDFError: Le fichier n'est pas un PDF.
        DuplicateDocumentError: Doublon détecté (sauf si overwrite=True).
    """
    settings = get_settings()
    settings.ensure_dirs()
    source_path = Path(source_path).resolve()

    # Vérification existence
    if not source_path.exists():
        raise FileNotFoundError(f"Fichier source introuvable : {source_path}")

    # Validation taille
    size_bytes = source_path.stat().st_size
    max_bytes = settings.max_pdf_size_mb * 1024 * 1024
    if size_bytes > max_bytes:
        raise InvalidPDFError(
            f"Fichier trop volumineux : {size_bytes / 1024 / 1024:.1f} Mo "
            f"(maximum : {settings.max_pdf_size_mb} Mo)"
        )

    # Validation type PDF (magic bytes)
    with source_path.open("rb") as f:
        header = f.read(5)
    if not header.startswith(b"%PDF-"):
        raise InvalidPDFError(
            f"Le fichier {source_path.name!r} n'est pas un PDF valide "
            f"(header : {header!r})."
        )

    # Calcul empreinte
    file_sha256 = sha256_file(source_path)
    logger.info("Empreinte SHA-256 : %s", file_sha256)

    # Détection doublon (T104)
    existing = db.query(Document).filter(Document.file_sha256 == file_sha256).first()
    if existing and not overwrite:
        raise DuplicateDocumentError(existing.id, file_sha256)

    # Nom de fichier sûr (T903)
    safe_name = safe_filename(source_path.name)
    dest_path = settings.raw_dir / safe_name

    # Si le fichier de destination existe déjà mais c'est un autre document
    if dest_path.exists() and (not existing or existing.filename != safe_name):
        # Renommer avec un suffixe unique
        stem = source_path.stem
        suffix = source_path.suffix
        safe_name = safe_filename(f"{stem}_{file_sha256[:8]}{suffix}")
        dest_path = settings.raw_dir / safe_name

    # Copie vers data/raw/ — fichier original inchangé (T105)
    if not dest_path.exists():
        shutil.copy2(str(source_path), str(dest_path))
        logger.info("PDF copié vers : %s", dest_path)
    else:
        logger.info("Fichier déjà présent dans data/raw/ : %s", dest_path)

    # Détection scan (T106)
    is_scanned, scan_warnings = _detect_scanned_pdf(dest_path)

    # Génération ID unique
    doc_id = str(uuid.uuid4())

    # Titre par défaut
    if not title:
        title = source_path.stem.replace("_", " ").replace("-", " ").strip()

    # Création du document
    if existing and overwrite:
        doc = existing
        doc.title = title
        doc.text_type = text_type
        doc.text_number = text_number
        doc.publication_date = publication_date
        doc.source_url = source_url
        doc.language = language
        doc.filename = safe_name
        doc.file_size_bytes = size_bytes
        doc.is_scanned = is_scanned
        doc.extraction_warnings = json.dumps(scan_warnings) if scan_warnings else None
        doc.collected_at = datetime.now(timezone.utc)
        doc.verification_status = VerificationStatus.UNVERIFIED.value
    else:
        doc = Document(
            id=doc_id,
            title=title,
            text_type=text_type,
            text_number=text_number,
            publication_date=publication_date,
            source_url=source_url,
            language=language,
            filename=safe_name,
            file_sha256=file_sha256,
            file_size_bytes=size_bytes,
            is_scanned=is_scanned,
            extraction_warnings=json.dumps(scan_warnings) if scan_warnings else None,
            collected_at=datetime.now(timezone.utc),
            verification_status=VerificationStatus.UNVERIFIED.value,
        )
        db.add(doc)

    db.commit()
    db.refresh(doc)

    if is_scanned:
        logger.warning(
            "Document %r signalé comme potentiellement scanné : %s",
            doc.id,
            scan_warnings,
        )
    else:
        logger.info(
            "Document importé avec succès : id=%r title=%r",
            doc.id,
            doc.title,
        )

    return doc
