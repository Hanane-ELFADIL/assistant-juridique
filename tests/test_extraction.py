"""
Tests Phase 2 — T200–T208
Extraction PDF avec PyMuPDF sur fixtures synthétiques.
"""
from __future__ import annotations

from pathlib import Path
import pytest
import pymupdf


# --- Fixtures ---

def _pdf_with_text(path: Path, content: str) -> Path:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 100), content)
    doc.save(str(path))
    doc.close()
    return path


def _pdf_empty_pages(path: Path, n: int = 3) -> Path:
    """PDF avec n pages sans texte (simulation scan)."""
    doc = pymupdf.open()
    for _ in range(n):
        doc.new_page()
    doc.save(str(path))
    doc.close()
    return path


def _pdf_with_articles(path: Path) -> Path:
    content = (
        "TITRE I\n\nChapitre 1\n\n"
        "Article 1\nLes banques doivent respecter les ratios prudentiels.\n\n"
        "Article 2\nLe capital minimum est de 100 millions de dirhams.\n\n"
        "Article 3\nBank Al-Maghrib veille au respect de la présente loi.\n"
    )
    return _pdf_with_text(path, content)


# --- Tests T200 : extraction de base ---

class TestExtraction:

    def test_extract_returns_text(self, tmp_path):
        """T200 — extract_pdf() retourne du texte non vide."""
        pdf = _pdf_with_text(tmp_path / "t.pdf", "Contenu de test juridique.")
        from src.extraction.pdf_extractor import extract_pdf
        result = extract_pdf(pdf, "doc-1")
        assert result.total_pages == 1
        assert result.pages_with_text == 1
        assert "test" in result.full_text.lower()

    def test_page_numbers_stored(self, tmp_path):
        """T201 — numéros de page PDF conservés (1-indexed)."""
        pdf = _pdf_with_text(tmp_path / "t.pdf", "Page une.")
        from src.extraction.pdf_extractor import extract_pdf
        result = extract_pdf(pdf, "doc-2")
        assert result.pages[0].page_number == 1

    def test_text_raw_preserved(self, tmp_path):
        """T206 — text_raw distinct de text_clean, tous deux présents."""
        pdf = _pdf_with_text(tmp_path / "t.pdf", "Texte brut avec   espaces.")
        from src.extraction.pdf_extractor import extract_pdf
        result = extract_pdf(pdf, "doc-3")
        p = result.pages[0]
        assert hasattr(p, 'text_raw')
        assert hasattr(p, 'text_clean')
        assert p.text_raw  # non vide

    def test_empty_pages_detected(self, tmp_path):
        """T202 — pages sans texte comptées."""
        pdf = _pdf_empty_pages(tmp_path / "empty.pdf", n=4)
        from src.extraction.pdf_extractor import extract_pdf
        result = extract_pdf(pdf, "doc-4")
        assert result.pages_without_text == 4
        assert result.pages_with_text == 0

    def test_warning_on_many_empty_pages(self, tmp_path):
        """T202 — avertissement si >30% de pages vides."""
        pdf = _pdf_empty_pages(tmp_path / "scan.pdf", n=5)
        from src.extraction.pdf_extractor import extract_pdf
        result = extract_pdf(pdf, "doc-5")
        assert len(result.warnings) > 0
        assert any("scanné" in w.lower() or "texte" in w.lower() for w in result.warnings)

    def test_normalization(self, tmp_path):
        """T204 — texte normalisé : pas de caractères de contrôle."""
        pdf = _pdf_with_text(tmp_path / "t.pdf", "Texte juridique normal.")
        from src.extraction.pdf_extractor import extract_pdf
        result = extract_pdf(pdf, "doc-6")
        clean = result.pages[0].text_clean
        # Pas de caractères de contrôle (hors \n\t)
        for ch in clean:
            import unicodedata
            cat = unicodedata.category(ch)
            assert cat[0] != 'C' or ch in '\n\t', f"Caractere de controle: {repr(ch)}"

    def test_articles_detected(self, tmp_path):
        """T205 — articles et chapitres détectés dans le texte."""
        pdf = _pdf_with_articles(tmp_path / "legal.pdf")
        from src.extraction.pdf_extractor import extract_pdf
        result = extract_pdf(pdf, "doc-7")
        articles = [e for e in result.structure if e['type'] == 'article']
        chapters = [e for e in result.structure if e['type'] in ('chapter', 'section')]
        assert len(articles) >= 3, f"Articles: {articles}"
        assert len(chapters) >= 1

    def test_quality_report(self, tmp_path):
        """T207 — rapport qualité contient toutes les clés."""
        pdf = _pdf_with_articles(tmp_path / "legal.pdf")
        from src.extraction.pdf_extractor import extract_pdf, extraction_quality_report
        result = extract_pdf(pdf, "doc-8")
        report = extraction_quality_report(result)
        for key in ['total_pages', 'pages_with_text', 'coverage_pct',
                    'total_chars', 'articles_detected', 'warnings']:
            assert key in report, f"Clé manquante: {key}"

    def test_missing_pdf_raises(self, tmp_path):
        """T200 — FileNotFoundError si fichier absent."""
        from src.extraction.pdf_extractor import extract_pdf
        with pytest.raises(FileNotFoundError):
            extract_pdf(tmp_path / "ghost.pdf", "doc-9")

    def test_multipage_pdf(self, tmp_path):
        """T200 — PDF multi-pages traité correctement."""
        path = tmp_path / "multi.pdf"
        doc = pymupdf.open()
        for i in range(5):
            p = doc.new_page()
            # Texte suffisamment long pour dépasser le seuil min_chars_per_page (20)
            p.insert_text((50, 100), f"Page {i+1} : contenu juridique suffisant pour le test.")
        doc.save(str(path))
        doc.close()

        from src.extraction.pdf_extractor import extract_pdf
        result = extract_pdf(path, "doc-10")
        assert result.total_pages == 5
        assert result.pages_with_text == 5
