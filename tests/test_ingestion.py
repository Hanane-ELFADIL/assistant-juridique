"""
Tests Phase 1 — T101, T104, T105, T106
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

# --- helpers ---

def _make_real_pdf(path: Path, text: str = "Texte de test BAM.") -> None:
    """Crée un vrai PDF numérique avec PyMuPDF."""
    import pymupdf
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 100), text)
    doc.save(str(path))
    doc.close()


def _make_fake_file(path: Path) -> None:
    """Crée un fichier qui n'est pas un PDF."""
    path.write_bytes(b"This is not a PDF")


def _make_db():
    """Crée une session SQLite in-memory isolée."""
    import os; os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker
    from src.database import Base
    from src.models import document, chunk  # noqa

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def fk(conn, _):
        conn.cursor().execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


# --- tests ---

class TestImportPDF:

    def test_import_valid_pdf(self, tmp_path):
        """T101 — import d'un PDF valide."""
        pdf = tmp_path / "loi_test.pdf"
        _make_real_pdf(pdf, "Loi sur les établissements de crédit.")
        db = _make_db()

        from src.ingestion.importer import import_pdf
        doc = import_pdf(pdf, db, title="Loi test", text_type="loi")

        assert doc.id
        assert doc.title == "Loi test"
        assert doc.text_type == "loi"
        assert len(doc.file_sha256) == 64
        assert doc.file_size_bytes > 0
        assert doc.verification_status == "unverified"
        db.close()

    def test_import_nonexistent(self, tmp_path):
        """T101 — FileNotFoundError si fichier absent."""
        db = _make_db()
        from src.ingestion.importer import import_pdf
        with pytest.raises(FileNotFoundError):
            import_pdf(tmp_path / "ghost.pdf", db)
        db.close()

    def test_import_not_a_pdf(self, tmp_path):
        """T101 — InvalidPDFError si pas un PDF."""
        fake = tmp_path / "fake.pdf"
        _make_fake_file(fake)
        db = _make_db()
        from src.ingestion.importer import import_pdf, InvalidPDFError
        with pytest.raises(InvalidPDFError):
            import_pdf(fake, db)
        db.close()

    def test_duplicate_detection(self, tmp_path):
        """T104 — même fichier importé deux fois → DuplicateDocumentError."""
        pdf = tmp_path / "doc.pdf"
        _make_real_pdf(pdf)
        db = _make_db()
        from src.ingestion.importer import import_pdf, DuplicateDocumentError
        import_pdf(pdf, db, title="Original")
        with pytest.raises(DuplicateDocumentError):
            import_pdf(pdf, db, title="Copie")
        db.close()

    def test_overwrite_allowed(self, tmp_path):
        """T104 — overwrite=True accepté même si doublon."""
        pdf = tmp_path / "doc.pdf"
        _make_real_pdf(pdf)
        db = _make_db()
        from src.ingestion.importer import import_pdf
        doc1 = import_pdf(pdf, db, title="V1")
        doc2 = import_pdf(pdf, db, title="V2", overwrite=True)
        assert doc1.id == doc2.id
        assert doc2.title == "V2"
        db.close()

    def test_provenance_stored(self, tmp_path):
        """T105 — source_url et SHA-256 enregistrés."""
        pdf = tmp_path / "doc.pdf"
        _make_real_pdf(pdf)
        db = _make_db()
        from src.ingestion.importer import import_pdf
        doc = import_pdf(pdf, db, source_url="https://www.bkam.ma/test.pdf")
        assert doc.source_url == "https://www.bkam.ma/test.pdf"
        assert doc.file_sha256
        assert doc.collected_at is not None
        db.close()

    def test_file_copied_to_raw(self, tmp_path):
        """T105 — fichier copié dans data/raw/ sans modification."""
        pdf = tmp_path / "original.pdf"
        _make_real_pdf(pdf, "Contenu original")
        db = _make_db()
        from src.ingestion.importer import import_pdf
        from src.config import get_settings
        from src.ingestion.fingerprint import sha256_file
        doc = import_pdf(pdf, db)
        raw_path = get_settings().raw_dir / doc.filename
        assert raw_path.exists(), f"Fichier absent de data/raw/ : {raw_path}"
        assert sha256_file(raw_path) == doc.file_sha256
        db.close()

    def test_scanned_pdf_detection(self, tmp_path):
        """T106 — PDF avec pages vides signalé comme potentiellement scanné."""
        import pymupdf
        pdf = tmp_path / "scan.pdf"
        doc = pymupdf.open()
        # 3 pages vides (aucun texte)
        doc.new_page(); doc.new_page(); doc.new_page()
        doc.save(str(pdf))
        doc.close()

        db = _make_db()
        from src.ingestion.importer import import_pdf
        imported = import_pdf(pdf, db)
        assert imported.is_scanned is True
        db.close()

    def test_verification_warning(self, tmp_path):
        """T100 — avertissement présent si statut non vérifié."""
        pdf = tmp_path / "doc.pdf"
        _make_real_pdf(pdf)
        db = _make_db()
        from src.ingestion.importer import import_pdf
        doc = import_pdf(pdf, db)
        assert doc.verification_warning is not None
        assert "vigueur" in doc.verification_warning.lower()
        db.close()
