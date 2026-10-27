"""
Extraction de texte PDF avec PyMuPDF — T200, T201, T202, T204, T205, T206, T207.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class PageExtraction:
    """Résultat de l'extraction d'une page PDF."""
    page_number: int          # Numéro de page PDF (0-indexed → on stocke 1-indexed)
    page_printed: str         # Numéro imprimé dans le document (si détecté)
    text_raw: str             # Texte brut non normalisé (T206)
    text_clean: str           # Texte normalisé (T204)
    char_count: int
    has_text: bool
    warnings: list[str] = field(default_factory=list)


@dataclass
class DocumentExtraction:
    """Résultat complet de l'extraction d'un document PDF."""
    document_id: str
    filename: str
    total_pages: int
    pages: list[PageExtraction] = field(default_factory=list)
    pages_with_text: int = 0
    pages_without_text: int = 0
    warnings: list[str] = field(default_factory=list)
    full_text: str = ""       # Texte complet concaténé
    structure: list[dict] = field(default_factory=list)  # Éléments structuraux détectés


# Patterns de structure juridique (T205)
_ARTICLE_PATTERNS = [
    re.compile(r"^(Article\s+\d+[\w\s\-]*)", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^(Art\.?\s*\d+[\w\s\-]*)", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^(المادة\s+\d+)", re.MULTILINE),  # Arabe
]

_CHAPTER_PATTERNS = [
    re.compile(r"^(Chapitre\s+\w+[\s\w\-]*)", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^(CHAPITRE\s+\w+[\s\w\-]*)", re.MULTILINE),
    re.compile(r"^(TITRE\s+\w+[\s\w\-]*)", re.MULTILINE),
    re.compile(r"^(Titre\s+\w+[\s\w\-]*)", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^(Section\s+\w+[\s\w\-]*)", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^(الفصل\s+\w+)", re.MULTILINE),  # Arabe
    re.compile(r"^(الباب\s+\w+)", re.MULTILINE),   # Arabe
]

_PRINTED_PAGE_PATTERN = re.compile(
    r"(?:^|\s)[-–—]?\s*(\d{1,4})\s*[-–—]?\s*$",
    re.MULTILINE,
)


def _normalize_text(text: str) -> str:
    """
    Normalise le texte extrait sans altérer les références juridiques (T204).
    
    - Normalise les espaces insécables et caractères de contrôle.
    - Préserve la ponctuation, les numéros, l'arabe et le français.
    - Ne supprime pas les tirets de numérotation juridique.
    """
    if not text:
        return ""

    # Normalisation Unicode NFC (composition canonique)
    text = unicodedata.normalize("NFC", text)

    # Remplace les espaces insécables et variations par un espace normal
    text = text.replace("\u00a0", " ")
    text = text.replace("\u200b", "")  # Zero-width space
    text = text.replace("\ufeff", "")  # BOM

    # Normalise les guillemets
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2018", "'").replace("\u2019", "'")

    # Normalise les tirets longs en tirets simples (hors contexte de numérotation)
    text = text.replace("\u2013", "-").replace("\u2014", " - ")

    # Supprime les caractères de contrôle sauf \n et \t
    text = "".join(
        c for c in text
        if unicodedata.category(c)[0] != "C" or c in "\n\t"
    )

    # Normalise les espaces multiples sur une ligne (préserve les sauts de ligne)
    lines = text.split("\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in lines]
    text = "\n".join(lines)

    # Supprime les lignes vides multiples (max 2 sauts consécutifs)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def _detect_printed_page_number(page_text: str) -> str:
    """
    Tente de détecter le numéro de page imprimé dans le texte (T201).
    Retourne une chaîne vide si non détecté.
    """
    matches = _PRINTED_PAGE_PATTERN.findall(page_text)
    if matches:
        # Retourne le dernier numéro trouvé (souvent en pied de page)
        return matches[-1]
    return ""


def _detect_structure_elements(text: str, page_number: int) -> list[dict]:
    """
    Détecte les éléments structuraux juridiques dans le texte (T205).
    
    Returns:
        Liste de dicts {type, text, page}.
    """
    elements = []

    for pattern in _CHAPTER_PATTERNS:
        for m in pattern.finditer(text):
            elements.append({
                "type": "chapter",
                "text": m.group(1).strip(),
                "page": page_number,
                "position": m.start(),
            })

    for pattern in _ARTICLE_PATTERNS:
        for m in pattern.finditer(text):
            elements.append({
                "type": "article",
                "text": m.group(1).strip(),
                "page": page_number,
                "position": m.start(),
            })

    elements.sort(key=lambda x: x["position"])
    return elements


def extract_pdf(
    pdf_path: Path | str,
    document_id: str,
    *,
    min_chars_per_page: int = 20,
) -> DocumentExtraction:
    """
    Extrait le texte d'un PDF page par page avec PyMuPDF (T200–T207).
    
    Args:
        pdf_path: Chemin vers le fichier PDF.
        document_id: Identifiant du document dans la base.
        min_chars_per_page: Seuil en dessous duquel une page est considérée vide.
    
    Returns:
        DocumentExtraction avec tout le texte et les métadonnées.
    
    Raises:
        ImportError: Si PyMuPDF n'est pas installé.
        FileNotFoundError: Si le fichier n'existe pas.
        RuntimeError: En cas d'erreur d'ouverture du PDF.
    """
    try:
        import pymupdf  # type: ignore
    except ImportError:
        raise ImportError(
            "PyMuPDF n'est pas installé. Exécutez : pip install pymupdf"
        )

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF introuvable : {pdf_path}")

    logger.info("Début extraction : %s", pdf_path.name)

    result = DocumentExtraction(
        document_id=document_id,
        filename=pdf_path.name,
        total_pages=0,
    )

    try:
        doc = pymupdf.open(str(pdf_path))
    except Exception as e:
        raise RuntimeError(f"Impossible d'ouvrir le PDF {pdf_path.name!r} : {e}") from e

    result.total_pages = len(doc)
    all_structure: list[dict] = []

    for page_idx in range(len(doc)):
        page_num = page_idx + 1  # 1-indexed
        try:
            page = doc[page_idx]
            raw_text = page.get_text("text")
        except Exception as e:
            warn = f"Page {page_num} : erreur d'extraction — {e}"
            logger.warning(warn)
            result.warnings.append(warn)
            raw_text = ""

        # Préserve le brut pour audit (T206)
        text_raw = raw_text

        # Détection numéro de page imprimé (T201)
        printed_page = _detect_printed_page_number(raw_text)

        # Normalisation (T204)
        text_clean = _normalize_text(raw_text)

        char_count = len(text_clean)
        has_text = char_count >= min_chars_per_page

        page_warnings: list[str] = []

        # Rapport pages vides (T202)
        if not has_text:
            warn = f"Page {page_num} sans texte exploitable (chars: {char_count})"
            logger.debug(warn)
            page_warnings.append(warn)
            result.pages_without_text += 1
        else:
            result.pages_with_text += 1

        # Détection structure (T205)
        if has_text:
            elements = _detect_structure_elements(text_clean, page_num)
            for e in elements:
                all_structure.append(e)

        page_extraction = PageExtraction(
            page_number=page_num,
            page_printed=printed_page,
            text_raw=text_raw,
            text_clean=text_clean,
            char_count=char_count,
            has_text=has_text,
            warnings=page_warnings,
        )
        result.pages.append(page_extraction)

    doc.close()

    # Texte complet concaténé
    result.full_text = "\n\n".join(
        p.text_clean for p in result.pages if p.has_text
    )
    result.structure = all_structure

    # Avertissement global si trop de pages vides
    empty_ratio = result.pages_without_text / result.total_pages if result.total_pages else 0
    if empty_ratio > 0.3:
        warn = (
            f"{result.pages_without_text}/{result.total_pages} pages sans texte "
            f"({empty_ratio:.0%}) — document potentiellement scanné."
        )
        result.warnings.append(warn)
        logger.warning(warn)

    logger.info(
        "Extraction terminée : %d pages, %d avec texte, %d sans texte, "
        "%d éléments de structure détectés.",
        result.total_pages,
        result.pages_with_text,
        result.pages_without_text,
        len(all_structure),
    )

    return result


def extraction_quality_report(extraction: DocumentExtraction) -> dict:
    """
    Génère un rapport de qualité d'extraction (T207).
    """
    return {
        "document_id": extraction.document_id,
        "filename": extraction.filename,
        "total_pages": extraction.total_pages,
        "pages_with_text": extraction.pages_with_text,
        "pages_without_text": extraction.pages_without_text,
        "coverage_pct": round(
            extraction.pages_with_text / extraction.total_pages * 100
            if extraction.total_pages else 0,
            1,
        ),
        "total_chars": sum(p.char_count for p in extraction.pages),
        "structure_elements": len(extraction.structure),
        "articles_detected": sum(
            1 for e in extraction.structure if e["type"] == "article"
        ),
        "chapters_detected": sum(
            1 for e in extraction.structure if e["type"] == "chapter"
        ),
        "warnings": extraction.warnings,
        "page_warnings": [
            w for p in extraction.pages for w in p.warnings
        ],
    }
