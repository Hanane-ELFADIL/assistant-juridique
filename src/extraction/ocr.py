"""
Interface OCR optionnelle pour les PDF scannés — T203.
OCR désactivé par défaut. Nécessite Tesseract + pytesseract.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class OCRNotAvailableError(Exception):
    """Levée si Tesseract ou pytesseract n'est pas installé."""
    pass


def is_ocr_available() -> bool:
    """Vérifie si pytesseract et Tesseract sont disponibles."""
    try:
        import pytesseract  # type: ignore
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def ocr_pdf_page(image_bytes: bytes, language: str = "fra+ara") -> str:
    """
    Applique l'OCR sur une image de page PDF.
    
    Args:
        image_bytes: Image de la page en bytes (PNG/JPEG).
        language: Codes langue Tesseract (fra=français, ara=arabe).
    
    Returns:
        Texte extrait par OCR.
    
    Raises:
        OCRNotAvailableError: Si Tesseract n'est pas installé.
    """
    if not is_ocr_available():
        raise OCRNotAvailableError(
            "pytesseract / Tesseract non disponible. "
            "Installez Tesseract (https://github.com/UB-Mannheim/tesseract/wiki) "
            "puis : pip install pytesseract pillow"
        )

    import pytesseract  # type: ignore
    from PIL import Image  # type: ignore
    import io

    try:
        image = Image.open(io.BytesIO(image_bytes))
        text = pytesseract.image_to_string(image, lang=language)
        return text
    except Exception as e:
        logger.error("Erreur OCR : %s", e)
        return ""


def extract_page_as_image(pdf_path: Path, page_number: int, dpi: int = 200) -> bytes:
    """
    Convertit une page PDF en image pour l'OCR.
    
    Args:
        pdf_path: Chemin vers le PDF.
        page_number: Numéro de page 1-indexed.
        dpi: Résolution de rendu (150–300 pour OCR).
    
    Returns:
        Image PNG en bytes.
    """
    try:
        import pymupdf  # type: ignore
    except ImportError:
        raise ImportError("PyMuPDF requis pour le rendu des pages.")

    doc = pymupdf.open(str(pdf_path))
    try:
        page = doc[page_number - 1]
        mat = pymupdf.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        return pix.tobytes("png")
    finally:
        doc.close()
