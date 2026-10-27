"""
Chunking juridique et hiérarchique — T300–T308.
Segmente le texte extrait en respectant les articles et paragraphes.
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from src.extraction.pdf_extractor import DocumentExtraction, PageExtraction

logger = logging.getLogger(__name__)

# Taille maximale d'un chunk en caractères avant sous-découpage (T302)
MAX_CHUNK_CHARS = 2000
# Chevauchement pour les sous-chunks (T302)
OVERLAP_CHARS = 200
# Taille minimale d'un chunk pour éviter les fragments inutiles
# 20 chars = "Article 1\nTexte." — seuil réaliste pour les articles courts
MIN_CHUNK_CHARS = 20


@dataclass
class ChunkData:
    """Données brutes d'un chunk avant persistance en base."""
    chunk_id: str
    document_id: str
    text: str
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    page_printed: str = ""
    chapter: str = ""
    section: str = ""
    article_number: str = ""
    paragraph_number: Optional[int] = None
    chunk_index: int = 0
    parent_chunk_id: Optional[str] = None
    is_sub_chunk: bool = False
    overlap_chars: int = 0
    extraction_method: str = "legal"
    has_warnings: bool = False
    # Métadonnées héritées du document
    doc_title: str = ""
    doc_type: str = ""
    doc_number: str = ""
    doc_date: str = ""
    doc_language: str = "fr"
    source_url: str = ""


# --- Patterns de délimitation --------------------------------------------------

_ARTICLE_RE = re.compile(
    r"(?:^|\n)((?:Article|Art\.?)\s+\d+[\w\s\-\.]*?)(?=\n|$)",
    re.IGNORECASE,
)

_ARABIC_ARTICLE_RE = re.compile(
    r"(?:^|\n)(المادة\s+\d+[\w\s\-]*?)(?=\n|$)",
)

_CHAPTER_RE = re.compile(
    r"(?:^|\n)((?:CHAPITRE|Chapitre|TITRE|Titre|Section|الفصل|الباب)\s+[\w\s\-\.]+?)(?=\n|$)",
    re.IGNORECASE,
)

_ANNEX_RE = re.compile(
    r"(?:^|\n)((?:Annexe|ANNEXE)\s*[\w\s\-\.]*?)(?=\n|$)",
    re.IGNORECASE,
)


def _make_chunk_id(document_id: str, text: str, index: int) -> str:
    """Génère un ID de chunk reproductible à partir du contenu."""
    content = f"{document_id}:{index}:{text[:100]}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:32]


def _split_into_sub_chunks(
    text: str,
    document_id: str,
    parent_chunk_id: str,
    base_metadata: dict,
    max_chars: int = MAX_CHUNK_CHARS,
    overlap: int = OVERLAP_CHARS,
) -> list[ChunkData]:
    """
    Découpe un texte trop long en sous-chunks avec chevauchement (T302).
    Préserve les métadonnées de l'article parent.
    """
    sub_chunks = []
    start = 0
    idx = 0

    while start < len(text):
        end = min(start + max_chars, len(text))

        # Essaye de couper à une fin de phrase ou de ligne
        if end < len(text):
            # Cherche le dernier \n ou ". " avant la limite
            best_break = max(
                text.rfind("\n", start, end),
                text.rfind(". ", start, end),
            )
            if best_break > start + MIN_CHUNK_CHARS:
                end = best_break + 1

        chunk_text = text[start:end].strip()
        if len(chunk_text) >= MIN_CHUNK_CHARS:
            cid = _make_chunk_id(document_id, chunk_text, hash(parent_chunk_id) + idx)
            sub_chunks.append(ChunkData(
                chunk_id=cid,
                document_id=document_id,
                text=chunk_text,
                chunk_index=idx,
                parent_chunk_id=parent_chunk_id,
                is_sub_chunk=True,
                overlap_chars=overlap if idx > 0 else 0,
                extraction_method="legal",
                **base_metadata,
            ))
            idx += 1

        # Chevauchement (T302)
        start = max(start + 1, end - overlap)
        if start >= len(text):
            break

    return sub_chunks


def chunk_document(
    extraction: DocumentExtraction,
    doc_metadata: dict,
    max_chunk_chars: int = MAX_CHUNK_CHARS,
) -> tuple[list[ChunkData], dict]:
    """
    Segmente un document extrait en chunks juridiques (T301–T306).
    
    Stratégie :
    1. Recompose le texte page par page avec les numéros de page.
    2. Détecte les délimiteurs : chapitres, articles, annexes.
    3. Crée un chunk par article (ou section si pas d'articles).
    4. Sous-découpe les chunks trop longs avec chevauchement.
    5. Active le chunking de secours si aucune structure détectée (T303).
    
    Args:
        extraction: Résultat de l'extraction PDF.
        doc_metadata: Métadonnées du document (titre, type, numéro, date...).
        max_chunk_chars: Taille maximale d'un chunk.
    
    Returns:
        (liste de ChunkData, rapport de qualité)
    """
    chunks: list[ChunkData] = []
    document_id = extraction.document_id

    # Métadonnées héritées (dénormalisées)
    base_meta = {
        "doc_title": doc_metadata.get("title", ""),
        "doc_type": doc_metadata.get("text_type", ""),
        "doc_number": doc_metadata.get("text_number", "") or "",
        "doc_date": doc_metadata.get("publication_date", "") or "",
        "doc_language": doc_metadata.get("language", "fr"),
        "source_url": doc_metadata.get("source_url", "") or "",
    }

    # Construction d'un index page → numéro imprimé
    page_printed_map: dict[int, str] = {}
    for page in extraction.pages:
        if page.page_printed:
            page_printed_map[page.page_number] = page.page_printed

    # Recomposition du texte avec marqueurs de page
    # Format : \x00PAGE:N\x00 pour repérer les sauts de page
    full_text_with_markers = ""
    for page in extraction.pages:
        if page.has_text:
            full_text_with_markers += f"\x00PAGE:{page.page_number}\x00\n{page.text_clean}\n"

    if not full_text_with_markers.strip():
        return [], {
            "status": "empty",
            "reason": "Aucun texte extrait",
            "chunks_count": 0,
        }

    # Détection de la structure dans le texte complet
    segments = _split_by_structure(full_text_with_markers)

    if not segments:
        # Chunking de secours (T303)
        logger.warning(
            "Aucune structure juridique détectée pour %r — chunking de secours activé.",
            document_id,
        )
        fallback_chunks = _fallback_chunk(
            full_text_with_markers,
            document_id,
            base_meta,
            max_chunk_chars,
        )
        report = {
            "status": "fallback",
            "reason": "Aucune structure juridique détectée",
            "chunks_count": len(fallback_chunks),
        }
        return fallback_chunks, report

    # Création des chunks depuis les segments
    current_chapter = ""
    current_section = ""

    for seg in segments:
        seg_type = seg["type"]
        seg_text = seg["text"].strip()
        pages = seg.get("pages", [])
        article_num = seg.get("article_number", "")

        if seg_type == "chapter":
            current_chapter = seg_text
            current_section = ""
            continue
        if seg_type == "section":
            current_section = seg_text
            continue

        if not seg_text or len(seg_text) < MIN_CHUNK_CHARS:
            continue

        # Évite de mélanger des articles distincts (T306)
        # Chaque segment est déjà un article ou un bloc

        page_start = min(pages) if pages else None
        page_end = max(pages) if pages else None
        page_printed = page_printed_map.get(page_start, "") if page_start else ""

        chunk_meta = {
            **base_meta,
            "page_start": page_start,
            "page_end": page_end,
            "page_printed": page_printed,
            "chapter": current_chapter,
            "section": current_section,
            "article_number": article_num,
        }

        if len(seg_text) <= max_chunk_chars:
            cid = _make_chunk_id(document_id, seg_text, len(chunks))
            chunks.append(ChunkData(
                chunk_id=cid,
                document_id=document_id,
                text=seg_text,
                chunk_index=0,
                is_sub_chunk=False,
                extraction_method="legal",
                **chunk_meta,
            ))
        else:
            # Sous-découpage (T302)
            parent_cid = _make_chunk_id(document_id, seg_text, len(chunks))
            sub_meta = {
                "doc_title": base_meta["doc_title"],
                "doc_type": base_meta["doc_type"],
                "doc_number": base_meta["doc_number"],
                "doc_date": base_meta["doc_date"],
                "doc_language": base_meta["doc_language"],
                "source_url": base_meta["source_url"],
                "page_start": page_start,
                "page_end": page_end,
                "page_printed": page_printed,
                "chapter": current_chapter,
                "section": current_section,
                "article_number": article_num,
            }
            sub_chunks = _split_into_sub_chunks(
                seg_text, document_id, parent_cid, sub_meta, max_chunk_chars
            )
            chunks.extend(sub_chunks)

    report = {
        "status": "legal" if chunks else "empty",
        "chunks_count": len(chunks),
        "articles_found": sum(1 for c in chunks if c.article_number),
        "chapters_found": len({c.chapter for c in chunks if c.chapter}),
        "sub_chunks": sum(1 for c in chunks if c.is_sub_chunk),
        "warnings": [],
    }

    if not chunks:
        report["status"] = "empty"
        report["warnings"].append("Aucun chunk produit malgré la détection de structure.")

    logger.info(
        "Chunking terminé : %d chunks, %d articles, %d chapitres.",
        report["chunks_count"],
        report["articles_found"],
        report["chapters_found"],
    )

    return chunks, report


def _split_by_structure(text: str) -> list[dict]:
    """
    Découpe le texte en segments selon la structure juridique détectée.
    
    Retourne une liste de segments ordonnés avec leur type et contenu.
    """
    # Trouve tous les délimiteurs et leur position
    delimiters: list[dict] = []

    for m in _CHAPTER_RE.finditer(text):
        label = m.group(1).strip().upper()
        if "TITRE" in label or "PARTIE" in label:
            dtype = "chapter"
        else:
            dtype = "section"
        delimiters.append({"pos": m.start(), "end": m.end(), "type": dtype, "label": m.group(1).strip()})

    for m in _ARTICLE_RE.finditer(text):
        num = re.search(r"\d+", m.group(1))
        delimiters.append({
            "pos": m.start(),
            "end": m.end(),
            "type": "article",
            "label": m.group(1).strip(),
            "article_number": num.group(0) if num else "",
        })

    for m in _ARABIC_ARTICLE_RE.finditer(text):
        num = re.search(r"\d+", m.group(1))
        delimiters.append({
            "pos": m.start(),
            "end": m.end(),
            "type": "article",
            "label": m.group(1).strip(),
            "article_number": num.group(0) if num else "",
        })

    for m in _ANNEX_RE.finditer(text):
        delimiters.append({
            "pos": m.start(),
            "end": m.end(),
            "type": "article",
            "label": m.group(1).strip(),
            "article_number": "",
        })

    if not delimiters:
        return []

    # Tri par position
    delimiters.sort(key=lambda x: x["pos"])

    segments = []
    _PAGE_MARKER_RE = re.compile(r"\x00PAGE:(\d+)\x00\n?")

    for i, delim in enumerate(delimiters):
        # Texte entre ce délimiteur et le suivant
        start = delim["end"]
        end = delimiters[i + 1]["pos"] if i + 1 < len(delimiters) else len(text)
        raw_content = text[start:end]

        # Extraction des numéros de page depuis les marqueurs
        pages = [int(m.group(1)) for m in _PAGE_MARKER_RE.finditer(raw_content)]

        # Supprime les marqueurs de page du texte final
        clean_content = _PAGE_MARKER_RE.sub("", raw_content).strip()

        # Ajoute le label du délimiteur au début du texte du segment
        seg_text = f"{delim['label']}\n{clean_content}" if clean_content else ""

        segments.append({
            "type": delim["type"],
            "text": seg_text,
            "label": delim["label"],
            "article_number": delim.get("article_number", ""),
            "pages": pages,
        })

    return segments


def _fallback_chunk(
    text: str,
    document_id: str,
    base_meta: dict,
    max_chars: int,
) -> list[ChunkData]:
    """
    Chunking de secours par taille fixe (T303).
    Utilisé quand aucune structure juridique n'est détectée.
    """
    _PAGE_MARKER_RE = re.compile(r"\x00PAGE:(\d+)\x00\n?")
    clean_text = _PAGE_MARKER_RE.sub("", text)

    chunks = []
    start = 0
    idx = 0

    while start < len(clean_text):
        end = min(start + max_chars, len(clean_text))

        # Coupe à une fin de phrase
        if end < len(clean_text):
            best = max(
                clean_text.rfind("\n\n", start, end),
                clean_text.rfind(". ", start, end),
            )
            if best > start + MIN_CHUNK_CHARS:
                end = best + 1

        chunk_text = clean_text[start:end].strip()
        if len(chunk_text) >= MIN_CHUNK_CHARS:
            cid = _make_chunk_id(document_id, chunk_text, idx)
            chunks.append(ChunkData(
                chunk_id=cid,
                document_id=document_id,
                text=chunk_text,
                chunk_index=idx,
                is_sub_chunk=False,
                extraction_method="fallback",
                has_warnings=True,
                overlap_chars=OVERLAP_CHARS if idx > 0 else 0,
                **base_meta,
            ))
            idx += 1

        start = max(start + 1, end - OVERLAP_CHARS)
        if start >= len(clean_text):
            break

    return chunks
