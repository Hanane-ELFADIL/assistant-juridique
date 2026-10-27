"""
Configuration pytest — fixtures partagées.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

# Force SQLite en mémoire pour les tests
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("GOOGLE_API_KEY", "test_key_not_real")
os.environ.setdefault("CHROMA_PERSIST_DIR", "./tests/fixtures/chroma_test")
os.environ.setdefault("DATA_RAW_DIR", "./tests/fixtures/raw")
os.environ.setdefault("DATA_PROCESSED_DIR", "./tests/fixtures/processed")


@pytest.fixture(scope="session")
def tmp_dir():
    """Répertoire temporaire partagé pour la session."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture(scope="function")
def db_session():
    """Session SQLAlchemy sur base in-memory pour tests isolés."""
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker
    from src.database import Base
    from src.models import document, chunk  # noqa: F401

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def set_fk(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="session")
def sample_pdf_path():
    """Retourne le chemin vers le PDF BAM disponible."""
    candidates = [
        Path("Recueil des textes législatifs et réglementaires de BAM _ VF.pdf"),
        Path("data/raw/Recueil_des_textes_l_gislatifs_et_r_glementaires_de_BAM___VF.pdf"),
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


@pytest.fixture
def minimal_pdf(tmp_dir):
    """Crée un PDF minimal synthétique pour les tests."""
    pdf_path = tmp_dir / "test_minimal.pdf"
    _create_minimal_pdf(pdf_path)
    return pdf_path


@pytest.fixture
def legal_pdf(tmp_dir):
    """Crée un PDF synthétique avec structure juridique."""
    pdf_path = tmp_dir / "test_legal.pdf"
    _create_legal_pdf(pdf_path)
    return pdf_path


@pytest.fixture
def empty_pdf(tmp_dir):
    """Crée un PDF avec des pages sans texte (simulant un scan)."""
    pdf_path = tmp_dir / "test_empty.pdf"
    _create_empty_pdf(pdf_path)
    return pdf_path


def _create_minimal_pdf(path: Path) -> None:
    """Crée un PDF minimal valide avec PyMuPDF."""
    try:
        import pymupdf
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((50, 50), "Document de test Bank Al-Maghrib.\nContenu minimal.")
        doc.save(str(path))
        doc.close()
    except ImportError:
        # Fallback : PDF synthétique minimal valide
        path.write_bytes(
            b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
            b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n"
            b"xref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n"
            b"0000000058 00000 n\n0000000115 00000 n\n"
            b"trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n190\n%%EOF\n"
        )


def _create_legal_pdf(path: Path) -> None:
    """Crée un PDF avec une structure juridique simulée."""
    try:
        import pymupdf
        doc = pymupdf.open()
        page = doc.new_page()
        content = (
            "RECUEIL DES TEXTES LÉGISLATIFS\n\n"
            "TITRE I — DISPOSITIONS GÉNÉRALES\n\n"
            "Chapitre Premier — Champ d'application\n\n"
            "Article 1\n"
            "La présente loi s'applique aux établissements de crédit.\n\n"
            "Article 2\n"
            "Les établissements doivent respecter les ratios prudentiels.\n\n"
            "Article 3\n"
            "Bank Al-Maghrib est chargée du contrôle prudentiel.\n\n"
            "TITRE II — DISPOSITIONS SPÉCIALES\n\n"
            "Article 4\n"
            "Le capital minimum est fixé par circulaire de Bank Al-Maghrib.\n"
        )
        page.insert_text((50, 50), content)
        doc.save(str(path))
        doc.close()
    except ImportError:
        _create_minimal_pdf(path)


def _create_empty_pdf(path: Path) -> None:
    """Crée un PDF avec des pages vides (simulation scan)."""
    try:
        import pymupdf
        doc = pymupdf.open()
        # Page vide (simulant un scan sans couche texte)
        doc.new_page()
        doc.new_page()
        doc.save(str(path))
        doc.close()
    except ImportError:
        _create_minimal_pdf(path)
