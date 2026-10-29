"""
Pipeline d'indexation complet — CLI pour importer, extraire, chunker et indexer.

Usage :
    python -m src.pipeline import-pdf <chemin_pdf> [options]
    python -m src.pipeline index-all
    python -m src.pipeline inventory
    python -m src.pipeline status
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def cmd_import_pdf(args) -> int:
    """Importe un PDF local dans le système."""
    from src.config import get_settings
    from src.database import get_session_factory, init_db
    from src.ingestion.importer import import_pdf, DuplicateDocumentError, InvalidPDFError

    settings = get_settings()
    settings.ensure_dirs()
    init_db()

    SessionLocal = get_session_factory()
    db = SessionLocal()

    try:
        doc = import_pdf(
            source_path=Path(args.pdf_path),
            db=db,
            title=args.title,
            text_type=args.text_type or "inconnu",
            text_number=args.number,
            source_url=args.url,
            language=args.language or "fr",
        )
        print(f"✓ Document importé : id={doc.id!r} titre={doc.title!r}")
        if doc.is_scanned:
            print("  ⚠ PDF potentiellement scanné — OCR peut être nécessaire.")
        return 0
    except DuplicateDocumentError as e:
        print(f"⚠ Doublon détecté : {e}")
        return 1
    except (InvalidPDFError, FileNotFoundError) as e:
        print(f"✗ Erreur : {e}")
        return 1
    finally:
        db.close()


def cmd_index_document(document_id: str, db, settings) -> int:
    """Extrait, chunke et indexe un document par son ID."""
    from src.models.document import Document
    from src.extraction.pdf_extractor import extract_pdf, extraction_quality_report
    from src.chunking.legal_chunker import chunk_document
    from src.embeddings.provider import get_embedding_provider
    from src.vectorstore.chroma_store import ChromaVectorStore
    from src.retrieval.bm25_index import BM25Index
    from src.models.chunk import Chunk

    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        print(f"✗ Document {document_id!r} introuvable.")
        return 1

    pdf_path = settings.raw_dir / doc.filename
    if not pdf_path.exists():
        print(f"✗ Fichier PDF manquant : {pdf_path}")
        return 1

    print(f"  Extraction : {doc.title!r}...")
    extraction = extract_pdf(pdf_path, doc.id)

    # Mise à jour des stats du document
    doc.total_pages = extraction.total_pages
    doc.pages_with_text = extraction.pages_with_text
    doc.pages_without_text = extraction.pages_without_text
    if extraction.warnings:
        import json as _json
        doc.extraction_warnings = _json.dumps(extraction.warnings)
    db.commit()

    quality = extraction_quality_report(extraction)
    print(f"    Pages: {quality['pages_with_text']}/{quality['total_pages']}, "
          f"articles: {quality['articles_detected']}, "
          f"chapitres: {quality['chapters_detected']}")

    if quality["coverage_pct"] < 50:
        print(f"    ⚠ Faible couverture texte ({quality['coverage_pct']}%) — PDF peut être scanné.")

    # Chunking
    print("  Chunking...")
    doc_metadata = {
        "title": doc.title,
        "text_type": doc.text_type,
        "text_number": doc.text_number,
        "publication_date": doc.publication_date.isoformat() if doc.publication_date else "",
        "language": doc.language,
        "source_url": doc.source_url,
    }
    chunks_data, chunk_report = chunk_document(extraction, doc_metadata)
    print(f"    Chunks: {chunk_report['chunks_count']} "
          f"(méthode: {chunk_report['status']})")

    if not chunks_data:
        print("  ✗ Aucun chunk produit.")
        return 1

    # Persistance des chunks en base
    # Supprime les chunks existants pour ce document
    db.query(Chunk).filter(Chunk.document_id == doc.id).delete()
    db.commit()

    chunk_objects = []
    for cd in chunks_data:
        chunk = Chunk(
            chunk_id=cd.chunk_id,
            document_id=cd.document_id,
            text=cd.text,
            text_length=len(cd.text),
            page_start=cd.page_start,
            page_end=cd.page_end,
            page_printed=cd.page_printed or "",
            chapter=cd.chapter or "",
            section=cd.section or "",
            article_number=cd.article_number or "",
            paragraph_number=cd.paragraph_number,
            chunk_index=cd.chunk_index,
            parent_chunk_id=cd.parent_chunk_id,
            is_sub_chunk=cd.is_sub_chunk,
            overlap_chars=cd.overlap_chars,
            extraction_method=cd.extraction_method,
            has_warnings=cd.has_warnings,
            doc_title=cd.doc_title,
            doc_type=cd.doc_type,
            doc_number=cd.doc_number,
            doc_date=cd.doc_date,
            doc_language=cd.doc_language,
            source_url=cd.source_url,
        )
        chunk_objects.append(chunk)
        db.add(chunk)
    db.commit()

    # Indexation vectorielle
    print("  Indexation vectorielle...")
    provider = get_embedding_provider(settings)
    vector_store = ChromaVectorStore(provider)

    # Supprime les chunks existants de l'index
    vector_store.delete_document_chunks(doc.id)

    chunk_ids = [c.chunk_id for c in chunk_objects]
    texts = [c.text for c in chunk_objects]
    metadatas = [
        {
            "document_id": c.document_id,
            "doc_title": c.doc_title or "",
            "doc_type": c.doc_type or "",
            "doc_number": c.doc_number or "",
            "doc_date": c.doc_date or "",
            "doc_language": c.doc_language or "fr",
            "source_url": c.source_url or "",
            "chapter": c.chapter or "",
            "section": c.section or "",
            "article_number": c.article_number or "",
            "paragraph_number": c.paragraph_number or 0,
            "page_start": c.page_start or 0,
            "page_end": c.page_end or 0,
            "page_printed": c.page_printed or "",
            "chunk_index": c.chunk_index,
            "is_sub_chunk": c.is_sub_chunk,
            "extraction_method": c.extraction_method or "legal",
        }
        for c in chunk_objects
    ]

    indexed = vector_store.upsert_chunks(chunk_ids, texts, metadatas)
    print(f"    {indexed} chunks indexés dans ChromaDB.")

    print(f"  ✓ Document {doc.title!r} indexé avec succès.")
    return 0


def cmd_index_all(args) -> int:
    """Indexe tous les documents importés."""
    from src.config import get_settings
    from src.database import get_session_factory, init_db
    from src.models.document import Document

    settings = get_settings()
    settings.ensure_dirs()
    init_db()

    SessionLocal = get_session_factory()
    db = SessionLocal()

    try:
        docs = db.query(Document).all()
        if not docs:
            print("Aucun document à indexer. Importez d'abord des PDFs.")
            return 0

        print(f"Indexation de {len(docs)} document(s)...")
        errors = 0
        for doc in docs:
            result = cmd_index_document(doc.id, db, settings)
            if result != 0:
                errors += 1

        print(f"\n✓ Terminé : {len(docs) - errors}/{len(docs)} documents indexés.")
        return 0 if errors == 0 else 1
    finally:
        db.close()


def cmd_inventory(args) -> int:
    """Affiche l'inventaire des documents."""
    from src.config import get_settings
    from src.database import get_session_factory, init_db
    from src.ingestion.inventory import print_inventory, save_inventory_json

    settings = get_settings()
    settings.ensure_dirs()
    init_db()

    SessionLocal = get_session_factory()
    db = SessionLocal()

    try:
        print_inventory(db)
        if args.json:
            path = save_inventory_json(db)
            print(f"Inventaire sauvegardé : {path}")
        return 0
    finally:
        db.close()


def cmd_status(args) -> int:
    """Affiche l'état de l'index vectoriel."""
    from src.config import get_settings
    from src.embeddings.provider import get_embedding_provider
    from src.vectorstore.chroma_store import ChromaVectorStore

    settings = get_settings()
    provider = get_embedding_provider(settings)
    store = ChromaVectorStore(provider)

    try:
        info = store.get_index_info()
        print("\n=== État de l'index vectoriel ===")
        for k, v in info.items():
            print(f"  {k}: {v}")
        print("=================================\n")
        return 0
    except Exception as e:
        print(f"✗ Index non disponible : {e}")
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="Assistant Juridique RAG — Bank Al-Maghrib — Pipeline CLI"
    )
    subparsers = parser.add_subparsers(dest="command")

    # import-pdf
    p_import = subparsers.add_parser("import-pdf", help="Importer un PDF local")
    p_import.add_argument("pdf_path", help="Chemin vers le fichier PDF")
    p_import.add_argument("--title", help="Titre du document")
    p_import.add_argument("--text-type", help="Type (loi, dahir, circulaire...)")
    p_import.add_argument("--number", help="Numéro officiel du texte")
    p_import.add_argument("--url", help="URL officielle source")
    p_import.add_argument("--language", default="fr", help="Langue (fr, ar)")
    p_import.set_defaults(func=cmd_import_pdf)

    # index-all
    p_index = subparsers.add_parser("index-all", help="Indexer tous les documents importés")
    p_index.set_defaults(func=cmd_index_all)

    # inventory
    p_inv = subparsers.add_parser("inventory", help="Afficher l'inventaire des documents")
    p_inv.add_argument("--json", action="store_true", help="Sauvegarder en JSON")
    p_inv.set_defaults(func=cmd_inventory)

    # status
    p_status = subparsers.add_parser("status", help="État de l'index vectoriel")
    p_status.set_defaults(func=cmd_status)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Logging basique pour CLI
    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s: %(message)s",
    )

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
