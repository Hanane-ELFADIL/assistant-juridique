"""
Calcul d'empreintes de fichiers pour la détection de doublons — T104.
"""
from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: Path, chunk_size: int = 65536) -> str:
    """
    Calcule l'empreinte SHA-256 d'un fichier par blocs.
    
    Args:
        path: Chemin vers le fichier.
        chunk_size: Taille des blocs de lecture en octets.
    
    Returns:
        Chaîne hexadécimale SHA-256 (64 caractères).
    
    Raises:
        FileNotFoundError: Si le fichier n'existe pas.
        PermissionError: Si le fichier n'est pas accessible.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {path}")

    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(chunk_size)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def is_safe_filename(filename: str) -> bool:
    """
    Vérifie qu'un nom de fichier est sûr (pas de traversée de chemin).
    
    Returns:
        True si le nom est sûr, False sinon.
    """
    forbidden = {"..", "/", "\\", "\0", ":"}
    return not any(c in filename for c in forbidden) and len(filename) > 0


def safe_filename(original: str) -> str:
    """
    Produit un nom de fichier sûr depuis un nom original.
    Remplace les caractères problématiques par des underscores.
    """
    import re
    # Garde seulement les caractères alphanumériques, tirets, underscores, points
    name = re.sub(r"[^\w\-.]", "_", original.strip())
    # Évite les doubles underscores
    name = re.sub(r"_+", "_", name)
    return name[:255]  # Limite de longueur
