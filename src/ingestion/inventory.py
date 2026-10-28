"""
Inventaire CLI des documents collectés — T107.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from src.config import get_settings
from src.models.document import Document, VerificationStatus
from src.models.chunk import Chunk

logger = logging.getLogger(__name__)


def generate_inventory_report(db: Session) -> dict[str, Any]:
    """
    Génère un rapport d'inventaire de tous les documents importés.
    
    Returns:
        Dictionnaire structuré avec statistiques et liste des documents.
    """
    settings = get_settings()
    documents = db.query(Document).all()

    total = len(documents)
    scanned = sum(1 for d in documents if d.is_scanned)
    unverified = sum(
        1 for d in documents
        if d.verification_status == VerificationStatus.UNVERIFIED.value
    )
    verified = sum(
        1 for d in documents
        if d.verification_status == VerificationStatus.VERIFIED.value
    )

    # Vérification des fichiers physiques
    missing_files = []
    for doc in documents:
        raw_path = settings.raw_dir / doc.filename
        if not raw_path.exists():
            missing_files.append(doc.filename)

    doc_list = []
    for doc in documents:
        raw_path = settings.raw_dir / doc.filename
        warnings = []
        if doc.extraction_warnings:
            try:
                warnings = json.loads(doc.extraction_warnings)
            except Exception:
                warnings = [doc.extraction_warnings]

        doc_list.append({
            "id": doc.id,
            "title": doc.title,
            "type": doc.text_type,
            "number": doc.text_number,
            "date": doc.publication_date.isoformat() if doc.publication_date else None,
            "language": doc.language,
            "filename": doc.filename,
            "file_exists": raw_path.exists(),
            "file_sha256": doc.file_sha256,
            "size_bytes": doc.file_size_bytes,
            "is_scanned": doc.is_scanned,
            "total_pages": doc.total_pages,
            "pages_with_text": doc.pages_with_text,
            "pages_without_text": doc.pages_without_text,
            "verification_status": doc.verification_status,
            "collected_at": doc.collected_at.isoformat() if doc.collected_at else None,
            "last_verified_at": doc.last_verified_at.isoformat() if doc.last_verified_at else None,
            "source_url": doc.source_url,
            "warnings": warnings,
            "chunks_count": db.query(Chunk).filter(Chunk.document_id == doc.id).count(),
        })

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_documents": total,
            "scanned_pdfs": scanned,
            "unverified_documents": unverified,
            "verified_documents": verified,
            "missing_files": len(missing_files),
        },
        "warnings": {
            "missing_files": missing_files,
            "unverified": [
                d["title"] for d in doc_list
                if d["verification_status"] == VerificationStatus.UNVERIFIED.value
            ],
        },
        "documents": doc_list,
    }


def print_inventory(db: Session) -> None:
    """Affiche le rapport d'inventaire dans la console."""
    report = generate_inventory_report(db)
    summary = report["summary"]

    print("\n" + "=" * 60)
    print("INVENTAIRE DES DOCUMENTS — Assistant Juridique BAM")
    print("=" * 60)
    print(f"Généré le : {report['generated_at']}")
    print(f"\nRésumé :")
    print(f"  Total documents   : {summary['total_documents']}")
    print(f"  PDFs scannés      : {summary['scanned_pdfs']}")
    print(f"  Non vérifiés      : {summary['unverified_documents']}")
    print(f"  Vérifiés          : {summary['verified_documents']}")
    print(f"  Fichiers manquants: {summary['missing_files']}")

    if report["warnings"]["missing_files"]:
        print("\n⚠️  FICHIERS MANQUANTS :")
        for f in report["warnings"]["missing_files"]:
            print(f"  - {f}")

    if report["warnings"]["unverified"]:
        print("\n⚠️  DOCUMENTS NON VÉRIFIÉS (statut juridique inconnu) :")
        for t in report["warnings"]["unverified"]:
            print(f"  - {t}")

    print("\nDocuments :")
    for doc in report["documents"]:
        status = "✓" if doc["verification_status"] == "verified" else "?"
        scan = " [SCANNÉ]" if doc["is_scanned"] else ""
        file_ok = "✓" if doc["file_exists"] else "✗ MANQUANT"
        print(
            f"  [{status}] {doc['title']!r} ({doc['type']}) "
            f"| fichier: {file_ok}{scan} | chunks: {doc['chunks_count']}"
        )
        if doc["warnings"]:
            for w in doc["warnings"]:
                print(f"      ⚠ {w}")
    print("=" * 60 + "\n")


def save_inventory_json(db: Session, output_path: Path | None = None) -> Path:
    """
    Sauvegarde le rapport d'inventaire en JSON.
    
    Returns:
        Chemin du fichier JSON créé.
    """
    settings = get_settings()
    if output_path is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        output_path = settings.processed_dir / f"inventory_{ts}.json"

    report = generate_inventory_report(db)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    logger.info("Inventaire sauvegardé : %s", output_path)
    return output_path
