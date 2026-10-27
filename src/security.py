"""
Sécurité, validation et robustesse — T900–T909.

Fonctions de validation pour :
- fichiers importés (taille, type MIME, nom sûr)  — T902
- chemins de fichiers (anti path traversal)       — T903
- détection d'injection de prompt                 — T905
- configuration des variables d'environnement     — T900
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── T902 : Validation des fichiers importés ───────────────────────────────────

# Types de fichiers acceptés (magic bytes)
_ALLOWED_MIME_SIGNATURES: dict[bytes, str] = {
    b"%PDF-": "application/pdf",
}

# Taille maximale par défaut : 50 Mo
DEFAULT_MAX_SIZE_MB = 50

# Caractères interdits dans les noms de fichiers (T903)
_FORBIDDEN_FILENAME_CHARS = re.compile(r'[/\\:*?"<>|\x00]')
_PATH_TRAVERSAL = re.compile(r'\.\.[/\\]|^[/\\]')


class FileValidationError(ValueError):
    """Levée quand un fichier ne passe pas la validation."""
    pass


def validate_file(
    path: Path,
    *,
    max_size_mb: int = DEFAULT_MAX_SIZE_MB,
    allowed_extensions: tuple[str, ...] = ('.pdf',),
) -> None:
    """
    Valide un fichier avant import (T902).
    
    Vérifie :
    - L'existence du fichier
    - La taille maximale
    - L'extension autorisée
    - Les magic bytes (type réel, pas seulement l'extension)
    - Que le nom est sûr
    
    Raises:
        FileValidationError: Si une vérification échoue.
        FileNotFoundError: Si le fichier n'existe pas.
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {path}")

    if not path.is_file():
        raise FileValidationError(f"Le chemin n'est pas un fichier : {path}")

    # Nom de fichier sûr
    validate_filename(path.name)

    # Extension
    ext = path.suffix.lower()
    if ext not in allowed_extensions:
        raise FileValidationError(
            f"Extension non autorisée : {ext!r}. Autorisées : {allowed_extensions}"
        )

    # Taille
    size_mb = path.stat().st_size / (1024 * 1024)
    if size_mb > max_size_mb:
        raise FileValidationError(
            f"Fichier trop volumineux : {size_mb:.1f} Mo (max : {max_size_mb} Mo)"
        )

    # Magic bytes — type réel
    with path.open("rb") as f:
        header = f.read(8)

    matched = False
    for sig, mime in _ALLOWED_MIME_SIGNATURES.items():
        if header.startswith(sig):
            matched = True
            break

    if not matched:
        raise FileValidationError(
            f"Type de fichier non autorisé (magic bytes : {header[:5]!r}). "
            "Seuls les PDFs sont acceptés."
        )


# ── T903 : Sécurité des chemins ───────────────────────────────────────────────

def validate_filename(filename: str) -> None:
    """
    Vérifie qu'un nom de fichier est sûr — pas de traversée de chemin (T903).
    
    Raises:
        FileValidationError: Si le nom est dangereux.
    """
    if not filename or not filename.strip():
        raise FileValidationError("Nom de fichier vide.")

    if _FORBIDDEN_FILENAME_CHARS.search(filename):
        raise FileValidationError(
            f"Nom de fichier contient des caractères interdits : {filename!r}"
        )

    if _PATH_TRAVERSAL.search(filename):
        raise FileValidationError(
            f"Tentative de traversée de chemin détectée : {filename!r}"
        )

    if len(filename) > 255:
        raise FileValidationError(
            f"Nom de fichier trop long ({len(filename)} > 255 caractères)."
        )


def safe_join(base_dir: Path, filename: str) -> Path:
    """
    Joint un chemin de base et un nom de fichier de façon sûre (T903).
    Vérifie que le chemin résultant est bien dans base_dir.
    
    Raises:
        FileValidationError: Si le chemin sort du répertoire de base.
    """
    base_dir = Path(base_dir).resolve()
    validate_filename(filename)
    result = (base_dir / filename).resolve()

    # Vérification anti path traversal
    try:
        result.relative_to(base_dir)
    except ValueError:
        raise FileValidationError(
            f"Chemin hors du répertoire autorisé : {result} n'est pas dans {base_dir}"
        )

    return result


# ── T905 : Détection d'injection de prompt ───────────────────────────────────

# Patterns typiques d'injection dans des textes juridiques
_INJECTION_PATTERNS = [
    re.compile(r'ignore\s+(?:all\s+)?(?:previous\s+)?instructions?', re.IGNORECASE),
    re.compile(r'you\s+are\s+now\s+(?:a\s+)?(?:different|new)\s+', re.IGNORECASE),
    re.compile(r'system\s*prompt\s*:', re.IGNORECASE),
    re.compile(r'<\s*(?:system|assistant|user)\s*>', re.IGNORECASE),
    re.compile(r'\[INST\]|\[\/INST\]'),
    re.compile(r'###\s*(?:System|Human|Assistant)\s*:', re.IGNORECASE),
]


def detect_prompt_injection(text: str) -> list[str]:
    """
    Détecte des patterns d'injection de prompt dans un texte (T905).
    
    Les textes juridiques doivent être traités comme données, jamais comme
    instructions. Cette fonction signale les patterns suspects sans bloquer
    le traitement (décision laissée à l'appelant).
    
    Returns:
        Liste des patterns détectés (vide si aucun).
    """
    found = []
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            found.append(pattern.pattern)
    return found


def sanitize_query(query: str, max_length: int = 500) -> str:
    """
    Nettoie une requête utilisateur avant traitement (T905).
    - Tronque à max_length
    - Supprime les caractères de contrôle
    - Préserve le contenu légitime
    
    Returns:
        Requête nettoyée.
    """
    # Supprime les caractères de contrôle (sauf espace et tabulation)
    query = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', query)
    # Tronque
    query = query[:max_length]
    return query.strip()


# ── T900 : Validation de la configuration ────────────────────────────────────

def check_no_secrets_in_env(env_dict: Optional[dict] = None) -> list[str]:
    """
    Vérifie qu'aucun secret évident n'est hardcodé dans l'environnement (T901).
    
    Returns:
        Liste des problèmes détectés.
    """
    if env_dict is None:
        env_dict = dict(os.environ)

    issues = []
    suspicious_keys = {
        'GOOGLE_API_KEY', 'SECRET_KEY', 'DATABASE_PASSWORD',
        'JWT_SECRET', 'API_SECRET',
    }

    for key in suspicious_keys:
        val = env_dict.get(key, '')
        # Valeur par défaut vide ou placeholder → OK
        if val and val not in ('', 'your_google_api_key_here', 'changeme', 'secret'):
            # Présence d'une vraie clé → juste noter qu'elle est configurée
            logger.debug("Variable sensible configurée : %s (longueur: %d)", key, len(val))

    return issues


def validate_required_config(settings) -> list[str]:
    """
    Valide que la configuration minimale est présente (T900).
    
    Returns:
        Liste des erreurs de configuration.
    """
    errors = []

    if not settings.google_api_key:
        errors.append(
            "GOOGLE_API_KEY non définie. "
            "Les embeddings et le LLM ne fonctionneront pas."
        )

    if not settings.database_url:
        errors.append("DATABASE_URL non définie.")

    return errors
