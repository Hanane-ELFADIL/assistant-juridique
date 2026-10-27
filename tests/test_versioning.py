"""
Tests Phase 10 — T1000–T1007
Actualité, versioning et traçabilité des documents.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pymupdf
import pytest


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_db():
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
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


def _make_doc(db, tmp_path, title="Loi test") -> tuple:
    """Importe un vrai PDF et retourne (doc, db)."""
    pdf = tmp_path / f"doc_{uuid.uuid4().hex[:6]}.pdf"
    d = pymupdf.open()
    p = d.new_page()
    p.insert_text((50, 100), f"Article 1 : {title}.")
    d.save(str(pdf))
    d.close()

    from src.ingestion.importer import import_pdf
    doc = import_pdf(pdf, db, title=title)
    return doc, db


# ── T1000 : Dates de collecte et vérification ────────────────────────────────

class TestCollectionDates:

    def test_collected_at_set_on_import(self, tmp_path):
        """T1000 — collected_at renseigné à l'import."""
        db = _make_db()
        doc, _ = _make_doc(db, tmp_path)
        assert doc.collected_at is not None

    def test_last_verified_initially_none(self, tmp_path):
        """T1000 — last_verified_at absent à l'import."""
        db = _make_db()
        doc, _ = _make_doc(db, tmp_path)
        from src.versioning import get_last_verified_date
        assert get_last_verified_date(doc) is None

    def test_mark_verified_sets_date(self, tmp_path):
        """T1000 — mark_verified() renseigne last_verified_at."""
        db = _make_db()
        doc, _ = _make_doc(db, tmp_path)
        from src.versioning import mark_verified
        doc = mark_verified(doc, db)
        assert doc.last_verified_at is not None
        assert doc.verification_status == "verified"

    def test_mark_outdated(self, tmp_path):
        """T1000 — mark_outdated() change le statut."""
        db = _make_db()
        doc, _ = _make_doc(db, tmp_path)
        from src.versioning import mark_outdated
        doc = mark_outdated(doc, db, reason="Version plus récente sur bkam.ma")
        assert doc.verification_status == "outdated"


# ── T1001 : Détection de changements ─────────────────────────────────────────

class TestFileChangeDetection:

    def test_unchanged_file_not_detected(self, tmp_path):
        """T1001 — fichier non modifié → check_file_changed retourne False."""
        db = _make_db()
        doc, _ = _make_doc(db, tmp_path)
        from src.versioning import check_file_changed
        from src.config import get_settings
        # Le fichier est copié dans data/raw/, doit correspondre à l'empreinte
        assert check_file_changed(doc) is False

    def test_missing_file_detected(self, tmp_path):
        """T1001 — fichier manquant → check_file_changed retourne True."""
        db = _make_db()
        doc, _ = _make_doc(db, tmp_path)
        from src.versioning import check_file_changed
        from src.config import get_settings
        settings = get_settings()
        # Simuler un fichier manquant
        raw_path = settings.raw_dir / doc.filename
        if raw_path.exists():
            raw_path.rename(raw_path.with_suffix(".bak"))
        try:
            assert check_file_changed(doc) is True
        finally:
            bak = raw_path.with_suffix(".bak")
            if bak.exists():
                bak.rename(raw_path)


# ── T1002 : Archivage des versions ───────────────────────────────────────────

class TestArchiving:

    def test_archive_creates_copy(self, tmp_path):
        """T1002 — archive_document_version() crée une copie horodatée."""
        db = _make_db()
        doc, _ = _make_doc(db, tmp_path)
        from src.versioning import archive_document_version
        from src.config import get_settings
        settings = get_settings()
        raw_path = settings.raw_dir / doc.filename
        if not raw_path.exists():
            pytest.skip("Fichier non présent dans data/raw/")
        archive_path = archive_document_version(doc)
        assert archive_path is not None
        assert archive_path.exists()
        assert "archive" in str(archive_path)
        # Nettoyer
        archive_path.unlink(missing_ok=True)

    def test_archive_missing_file_returns_none(self, tmp_path):
        """T1002 — fichier absent → archive retourne None."""
        from src.models.document import Document, VerificationStatus
        from src.versioning import archive_document_version
        import uuid
        # Document fictif pointant vers un fichier inexistant
        fake_doc = Document(
            id=str(uuid.uuid4()),
            title="Fake",
            filename="nonexistent_xyz.pdf",
            file_sha256="a" * 64,
            file_size_bytes=0,
        )
        result = archive_document_version(fake_doc)
        assert result is None


# ── T1003 : Documents non vérifiés ───────────────────────────────────────────

class TestUnverifiedDocuments:

    def test_new_doc_is_unverified(self, tmp_path):
        """T1003 — document importé → statut unverified."""
        db = _make_db()
        doc, _ = _make_doc(db, tmp_path)
        from src.versioning import get_unverified_documents
        unverified = get_unverified_documents(db)
        assert any(d.id == doc.id for d in unverified)

    def test_verified_doc_not_in_unverified(self, tmp_path):
        """T1003 — document vérifié → plus dans la liste non vérifiés."""
        db = _make_db()
        doc, _ = _make_doc(db, tmp_path)
        from src.versioning import mark_verified, get_unverified_documents
        mark_verified(doc, db)
        unverified = get_unverified_documents(db)
        assert not any(d.id == doc.id for d in unverified)

    def test_verification_warning_present(self, tmp_path):
        """T1003 — avertissement présent pour document non vérifié."""
        db = _make_db()
        doc, _ = _make_doc(db, tmp_path)
        from src.versioning import get_verification_warning
        warning = get_verification_warning(doc)
        assert warning is not None
        assert "vigueur" in warning.lower() or "vérifié" in warning.lower()


# ── T1004 : Dates multiples ───────────────────────────────────────────────────

class TestDatesSummary:

    def test_dates_summary_keys(self, tmp_path):
        """T1004 — get_dates_summary() retourne toutes les clés."""
        db = _make_db()
        doc, _ = _make_doc(db, tmp_path)
        from src.versioning import get_dates_summary
        summary = get_dates_summary(doc)
        for key in ("publication_date", "entry_into_force_date",
                    "collected_at", "last_verified_at", "verification_status"):
            assert key in summary

    def test_missing_dates_flagged(self, tmp_path):
        """T1004 — dates manquantes signalées, pas inventées."""
        db = _make_db()
        doc, _ = _make_doc(db, tmp_path)
        from src.versioning import get_dates_summary
        summary = get_dates_summary(doc)
        # publication_date est None → doit être dans _missing_dates
        if summary.get("publication_date") is None:
            assert "_missing_dates" in summary
            assert "publication_date" in summary["_missing_dates"]

    def test_no_automatic_status_inferred(self, tmp_path):
        """T1006 — le résumé ne déduit pas automatiquement l'applicabilité."""
        db = _make_db()
        doc, _ = _make_doc(db, tmp_path)
        from src.versioning import get_dates_summary
        summary = get_dates_summary(doc)
        # Aucun champ "is_applicable" ou "is_abrogated" auto-généré
        assert "is_applicable" not in summary
        assert "is_abrogated" not in summary
        assert "en_vigueur" not in summary


# ── T1005 : Rapport de fraîcheur ─────────────────────────────────────────────

class TestStalenessReport:

    def test_report_structure(self, tmp_path):
        """T1005 — generate_staleness_report() a la structure attendue."""
        db = _make_db()
        _make_doc(db, tmp_path, "Document A")
        from src.versioning import generate_staleness_report
        report = generate_staleness_report(db)
        for key in ("generated_at", "total_documents", "by_status",
                    "never_verified", "legal_disclaimer"):
            assert key in report

    def test_report_legal_disclaimer(self, tmp_path):
        """T1006 — rapport contient un avertissement sur la non-applicabilité auto."""
        db = _make_db()
        from src.versioning import generate_staleness_report
        report = generate_staleness_report(db)
        disclaimer = report.get("legal_disclaimer", "")
        assert "statut juridique" in disclaimer.lower() or "source" in disclaimer.lower()

    def test_never_verified_listed(self, tmp_path):
        """T1005 — documents jamais vérifiés listés dans le rapport."""
        db = _make_db()
        doc, _ = _make_doc(db, tmp_path, "Doc non vérifié")
        from src.versioning import generate_staleness_report
        report = generate_staleness_report(db)
        never = [d["id"] for d in report["never_verified"]]
        assert doc.id in never
