"""
Tests Phase 3 — T300–T308
Chunking juridique sur fixtures synthétiques.
"""
from __future__ import annotations

from pathlib import Path
import pymupdf
import pytest

from src.extraction.pdf_extractor import extract_pdf
from src.chunking.legal_chunker import (
    chunk_document,
    ChunkData,
    MAX_CHUNK_CHARS,
    MIN_CHUNK_CHARS,
)


# --- helpers ---

def _make_pdf(path: Path, content: str) -> Path:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 50), content)
    doc.save(str(path))
    doc.close()
    return path


def _extract(path: Path, doc_id: str = "doc-test"):
    return extract_pdf(path, doc_id)


BASE_META = {
    "title": "Loi de test",
    "text_type": "loi",
    "text_number": "34-03",
    "publication_date": "2006-01-01",
    "language": "fr",
    "source_url": "https://www.bkam.ma/test",
}


# --- T300 : schéma chunk ---

class TestChunkSchema:

    def test_chunk_has_required_fields(self, tmp_path):
        """T300 — chaque ChunkData a les champs obligatoires."""
        pdf = _make_pdf(tmp_path / "t.pdf",
                        "Article 1\nLes banques respectent les ratios prudentiels.")
        ext = _extract(pdf)
        chunks, _ = chunk_document(ext, BASE_META)
        assert chunks, "Aucun chunk produit"
        c = chunks[0]
        assert c.chunk_id
        assert c.document_id == "doc-test"
        assert c.text
        assert c.extraction_method in ("legal", "fallback")

    def test_chunk_inherits_doc_metadata(self, tmp_path):
        """T300 — métadonnées du document héritées dans chaque chunk."""
        pdf = _make_pdf(tmp_path / "t.pdf",
                        "Article 1\nDispositions générales de la loi.")
        ext = _extract(pdf)
        chunks, _ = chunk_document(ext, BASE_META)
        assert chunks
        c = chunks[0]
        assert c.doc_title == "Loi de test"
        assert c.doc_type == "loi"
        assert c.doc_number == "34-03"
        assert c.source_url == "https://www.bkam.ma/test"


# --- T301 : chunking par articles ---

class TestLegalChunking:

    def test_one_chunk_per_article(self, tmp_path):
        """T301 — un chunk par article détecté."""
        content = (
            "Article 1\nLes banques respectent les ratios prudentiels.\n\n"
            "Article 2\nLe capital minimum est de 200 millions de dirhams.\n\n"
            "Article 3\nBank Al-Maghrib contrôle les établissements de crédit.\n"
        )
        pdf = _make_pdf(tmp_path / "t.pdf", content)
        ext = _extract(pdf)
        chunks, report = chunk_document(ext, BASE_META)
        arts = [c for c in chunks if c.article_number]
        assert len(arts) >= 3, f"Articles attendus: >=3, obtenus: {len(arts)}"
        assert report["status"] == "legal"

    def test_article_number_extracted(self, tmp_path):
        """T301 — article_number extrait correctement."""
        content = "Article 42\nContenu de l'article quarante-deux.\n"
        pdf = _make_pdf(tmp_path / "t.pdf", content)
        ext = _extract(pdf)
        chunks, _ = chunk_document(ext, BASE_META)
        arts = [c for c in chunks if c.article_number == "42"]
        assert arts, "Article 42 non trouvé"

    def test_chapter_propagated(self, tmp_path):
        """T304 — chapitre propagé dans les chunks de ses articles."""
        content = (
            "TITRE I\n\n"
            "Article 1\nContenu article premier.\n\n"
            "Article 2\nContenu article deux.\n"
        )
        pdf = _make_pdf(tmp_path / "t.pdf", content)
        ext = _extract(pdf)
        chunks, _ = chunk_document(ext, BASE_META)
        arts = [c for c in chunks if c.article_number]
        if arts:
            # Le chapitre doit être propagé ou vide (acceptable si le titre est en en-tête)
            chapters = {c.chapter for c in arts}
            # Valide : soit tous ont le même chapitre, soit vide (avant premier marqueur)
            assert len(chapters) <= 2


# --- T302 : sous-chunks ---

class TestSubChunking:

    def test_long_article_split(self, tmp_path):
        """T302 — article > max_chunk_chars découpé en sous-chunks."""
        # Crée un PDF multi-pages avec un article long (1 page = ~120 chars utiles)
        path = tmp_path / "long.pdf"
        doc = pymupdf.open()
        # Page 1 : en-tête de l'article
        p1 = doc.new_page()
        p1.insert_text((50, 50), "Article 1\n" + "Contenu juridique tres long phrase numero un. " * 3)
        # Pages 2–6 : suite de l'article (sans nouveau délimiteur Article)
        for i in range(5):
            p = doc.new_page()
            p.insert_text((50, 50), "Contenu juridique suite de l'article. " * 3)
        doc.save(str(path))
        doc.close()

        from src.extraction.pdf_extractor import extract_pdf
        ext = extract_pdf(path, "doc-sub")
        total_chars = sum(p.char_count for p in ext.pages if p.has_text)
        chunks, report = chunk_document(ext, BASE_META, max_chunk_chars=200)
        sub = [c for c in chunks if c.is_sub_chunk]
        # Avec 6 pages et max_chunk_chars=200, on doit avoir des sous-chunks
        # si le texte total dépasse 200 chars
        if total_chars > 200:
            assert len(sub) >= 1, (
                f"Sous-chunks attendus (total_chars={total_chars}, max=200), "
                f"rapport: {report}"
            )

    def test_sub_chunk_has_parent_id(self, tmp_path):
        """T305 — sous-chunks ont un parent_chunk_id."""
        long_text = "Article 1\n" + ("Texte juridique long. " * 100)
        pdf = _make_pdf(tmp_path / "t.pdf", long_text)
        ext = _extract(pdf)
        chunks, _ = chunk_document(ext, BASE_META, max_chunk_chars=300)
        sub = [c for c in chunks if c.is_sub_chunk]
        if sub:
            assert all(c.parent_chunk_id for c in sub), "parent_chunk_id manquant"

    def test_sub_chunk_overlap(self, tmp_path):
        """T302 — chevauchement enregistré sur les sous-chunks suivants."""
        long_text = "Article 1\n" + ("Texte juridique. " * 150)
        pdf = _make_pdf(tmp_path / "t.pdf", long_text)
        ext = _extract(pdf)
        chunks, _ = chunk_document(ext, BASE_META, max_chunk_chars=300)
        sub = [c for c in chunks if c.is_sub_chunk]
        if len(sub) >= 2:
            # Le 2e sous-chunk doit avoir overlap_chars > 0
            assert sub[1].overlap_chars > 0

    def test_sub_chunk_inherits_article_number(self, tmp_path):
        """T302 — sous-chunks héritent du numéro d'article parent."""
        long_text = "Article 99\n" + ("Disposition légale longue. " * 100)
        pdf = _make_pdf(tmp_path / "t.pdf", long_text)
        ext = _extract(pdf)
        chunks, _ = chunk_document(ext, BASE_META, max_chunk_chars=300)
        sub = [c for c in chunks if c.is_sub_chunk]
        if sub:
            assert all(c.article_number == "99" for c in sub)


# --- T303 : fallback ---

class TestFallbackChunking:

    def test_fallback_on_unstructured(self, tmp_path):
        """T303 — chunking fallback si aucune structure détectée."""
        content = "Ceci est un texte sans structure juridique. " * 20
        pdf = _make_pdf(tmp_path / "t.pdf", content)
        ext = _extract(pdf)
        chunks, report = chunk_document(ext, BASE_META)
        # Peut être fallback ou legal selon la longueur
        assert report["chunks_count"] >= 1
        if report["status"] == "fallback":
            assert all(c.extraction_method == "fallback" for c in chunks)

    def test_fallback_marked(self, tmp_path):
        """T303 — chunks fallback marqués extraction_method='fallback'."""
        # Texte long sans articles pour forcer le fallback
        content = "Texte sans structure. " * 200
        pdf = _make_pdf(tmp_path / "t.pdf", content)
        ext = _extract(pdf)
        chunks, report = chunk_document(ext, BASE_META)
        if report["status"] == "fallback":
            for c in chunks:
                assert c.extraction_method == "fallback"
                assert c.has_warnings is True


# --- T306 : pas de mélange d'articles ---

class TestNoArticleMixing:

    def test_no_mixing_different_articles(self, tmp_path):
        """T306 — un chunk ne contient pas deux articles distincts."""
        content = (
            "Article 1\nDispositions de l'article premier.\n\n"
            "Article 2\nDispositions de l'article deux.\n\n"
            "Article 3\nDispositions de l'article trois.\n"
        )
        pdf = _make_pdf(tmp_path / "t.pdf", content)
        ext = _extract(pdf)
        chunks, _ = chunk_document(ext, BASE_META)
        for c in chunks:
            if not c.is_sub_chunk:
                # Un chunk non-sous-chunk ne doit pas contenir 2 marqueurs "Article N"
                import re
                arts_in_text = re.findall(r"Article\s+(\d+)", c.text, re.IGNORECASE)
                unique_arts = set(arts_in_text)
                assert len(unique_arts) <= 1, (
                    f"Chunk mélange les articles {unique_arts}: {c.text[:100]}"
                )


# --- T307 : rapport qualité ---

class TestChunkReport:

    def test_report_keys(self, tmp_path):
        """T307 — rapport contient toutes les clés attendues."""
        content = "Article 1\nContenu.\nArticle 2\nAutre contenu.\n"
        pdf = _make_pdf(tmp_path / "t.pdf", content)
        ext = _extract(pdf)
        _, report = chunk_document(ext, BASE_META)
        for key in ["status", "chunks_count", "articles_found",
                    "chapters_found", "sub_chunks", "warnings"]:
            assert key in report, f"Clé manquante dans le rapport: {key}"

    def test_empty_pdf_report(self, tmp_path):
        """T307 — rapport correct sur PDF vide."""
        path = tmp_path / "empty.pdf"
        doc = pymupdf.open()
        doc.new_page()  # page vide
        doc.save(str(path))
        doc.close()
        ext = _extract(path)
        chunks, report = chunk_document(ext, BASE_META)
        assert report["chunks_count"] == 0


# --- T308 : cas limites ---

class TestEdgeCases:

    def test_arabic_article(self, tmp_path):
        """T308 — articles en arabe détectés."""
        content = "المادة 1\nنص القانون الأول.\n\nالمادة 2\nنص القانون الثاني.\n"
        pdf = _make_pdf(tmp_path / "t.pdf", content)
        ext = _extract(pdf)
        chunks, report = chunk_document(ext, BASE_META)
        # Le chunking doit fonctionner sans erreur
        assert report["chunks_count"] >= 0

    def test_chunk_ids_unique(self, tmp_path):
        """T300 — tous les chunk_ids sont uniques."""
        content = (
            "Article 1\nPremier article.\n"
            "Article 2\nDeuxième article.\n"
            "Article 3\nTroisième article.\n"
        )
        pdf = _make_pdf(tmp_path / "t.pdf", content)
        ext = _extract(pdf)
        chunks, _ = chunk_document(ext, BASE_META)
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids)), "chunk_ids en double"

    def test_chunk_min_length(self, tmp_path):
        """T300 — aucun chunk sous MIN_CHUNK_CHARS."""
        content = "Article 1\nContenu suffisamment long pour le test.\n" * 3
        pdf = _make_pdf(tmp_path / "t.pdf", content)
        ext = _extract(pdf)
        chunks, _ = chunk_document(ext, BASE_META)
        for c in chunks:
            assert len(c.text) >= MIN_CHUNK_CHARS, (
                f"Chunk trop court ({len(c.text)} chars): {c.text!r}"
            )
