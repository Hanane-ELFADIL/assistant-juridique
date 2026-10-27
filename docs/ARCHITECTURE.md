# Architecture — Assistant Juridique RAG Bank Al-Maghrib

> Dernière mise à jour : Phase 12 / T1200
> Ce document reflète l'état réel du code.

---

## 1. Objectif

Permettre à un utilisateur de poser des questions en langage naturel sur les textes
législatifs et réglementaires de Bank Al-Maghrib, et obtenir des réponses fondées
**uniquement** sur les passages réellement extraits des documents indexés.
Chaque réponse est vérifiable : titre, type, numéro, article, page, URL.

---

## 2. Stack technique

| Composant | Bibliothèque | Version |
|---|---|---|
| API backend | FastAPI + Uvicorn | 0.124.2 / 0.38.0 |
| Validation / config | Pydantic v2 + pydantic-settings | 2.12.5 / 2.10.1 |
| Variables d'env | python-dotenv | 1.0.0 |
| Base de données | SQLAlchemy + SQLite | 2.0.45 |
| Extraction PDF | PyMuPDF (`pymupdf`) | 1.26.1 |
| Embeddings | Google `text-embedding-004` via langchain-google-genai | 4.4.0 |
| LLM | Google Gemini Flash via langchain-google-genai | 4.4.0 |
| Vectorstore | ChromaDB | 1.5.9 |
| Recherche lexicale | rank-bm25 | 0.2.2 |
| Empreintes | xxhash | 4.0.1 |
| Tests | pytest | 9.1.1 |
| Frontend | React 18 + Vite 6 | — |

---

## 3. Structure des dossiers

```
asistant-juridique/
├── .env.example
├── .gitignore
├── README.md
├── TASKS.md
├── requirements.txt
├── requirements-dev.txt
├── docs/
│   ├── ARCHITECTURE.md   ← ce fichier
│   └── RISKS.md
├── data/
│   ├── raw/              ← PDFs originaux (jamais modifiés)
│   ├── processed/        ← textes extraits, chunks JSON
│   └── chroma_db/        ← index vectoriel ChromaDB persisté
├── frontend/             ← React + Vite
├── src/
│   ├── config.py
│   ├── database.py
│   ├── pipeline.py       ← CLI indexation
│   ├── security.py       ← validation fichiers, path traversal, injection
│   ├── versioning.py     ← dates, versions, fraîcheur
│   ├── evaluation.py     ← métriques RAG
│   ├── models/
│   ├── ingestion/
│   ├── extraction/
│   ├── chunking/
│   ├── embeddings/
│   ├── vectorstore/
│   ├── retrieval/
│   ├── generation/
│   └── api/
└── tests/
```

---

## 4. Décisions de conception

| Décision | Choix | Raison |
|---|---|---|
| LLM | Google Gemini Flash | Déjà installé, multilingue, température=0 |
| Embeddings | Google text-embedding-004 | Multilingue FR/AR, déjà installé |
| Vectorstore | ChromaDB 1.5.9 (local) | Zéro serveur, migration Qdrant facile |
| BDD métadonnées | SQLite via SQLAlchemy | Prototype local, migration PostgreSQL simple |
| Recherche lexicale | rank-bm25 | Léger, pur Python |
| Fusion | RRF (k=60) | Standard, documenté |
| Temperature LLM | 0.0 | Déterminisme maximal pour réponses juridiques |
| Import PDF | Manuel uniquement (MVP) | Contrôle total de la provenance |
| MIN_CHUNK_CHARS | 20 | Seuil réaliste pour articles courts |

---

## 5. Pipeline de données

### 5a. Indexation (offline — CLI)

```
PDF source
  │
  ▼ src/ingestion/importer.py
  Validation magic bytes + taille + nom de fichier sûr
  Copie dans data/raw/ (inchangé)
  SHA-256 → détection doublons
  Enregistrement BDD SQLite
  │
  ▼ src/extraction/pdf_extractor.py
  PyMuPDF : extraction page par page
  text_raw (brut) + text_clean (normalisé)
  Détection articles/chapitres par regex
  Rapport qualité (couverture, avertissements)
  │
  ▼ src/chunking/legal_chunker.py
  Segmentation par articles (méthode "legal")
  Sous-chunks avec chevauchement si article > 2000 chars
  Fallback taille fixe si aucune structure détectée
  Hiérarchie : chapter → section → article_number
  │
  ▼ src/embeddings/provider.py
  Google text-embedding-004
  Batch de 50 chunks
  │
  ▼ src/vectorstore/chroma_store.py
  ChromaDB upsert (idempotent par chunk_id)
  Métadonnées : document_id, article_number, page, source_url
  Version du modèle stockée dans les métadonnées de la collection
  │
  ▼ src/retrieval/bm25_index.py
  Index BM25 reconstruit en mémoire depuis la BDD
```

### 5b. Requête (online — API)

```
POST /api/chat { "question": "..." }
  │
  ▼ src/retrieval/hybrid_search.py
  Recherche vectorielle (ChromaDB, embed_query)
  + Recherche BM25 (tokenisation FR/AR)
  → Fusion RRF (k=60, poids 0.6/0.4)
  → Avertissement légal systématique
  │
  ▼ src/generation/rag_chain.py
  Score < seuil → mode "insufficient_sources"
  Prompt : passages comme DONNÉES (anti-injection)
  Gemini Flash temperature=0
  → answer, citations (chunk_id réel), sources, warnings
  │
  ▼ src/api/routes/chat.py
  ChatResponse : réponse typée et validée
```

---

## 6. Reconstruction complète de l'index (T409)

Si l'index ChromaDB est corrompu ou doit être reconstruit :

```powershell
# 1. Supprimer l'index existant
Remove-Item -Recurse -Force data\chroma_db

# 2. Vérifier que les PDFs sont dans data/raw/
python -m src.pipeline inventory

# 3. Réindexer tous les documents depuis la BDD
python -m src.pipeline index-all
```

L'opération est **idempotente** : relancer `index-all` n'a pas d'effet si l'index est déjà à jour.

Si la BDD SQLite est aussi perdue :

```powershell
# 1. Supprimer la BDD
Remove-Item data\bam_rag.db

# 2. Réimporter les PDFs
python -m src.pipeline import-pdf "chemin\vers\votre.pdf" --title "Titre"

# 3. Réindexer
python -m src.pipeline index-all
```

---

## 7. Mise à jour du corpus (T108)

Pour ajouter un nouveau document ou une version mise à jour :

```powershell
# Importer le nouveau PDF (détecte automatiquement les doublons)
python -m src.pipeline import-pdf "nouveau_texte.pdf" `
  --title "Titre officiel" `
  --text-type circulaire `
  --number "W/2024/01" `
  --url "https://www.bkam.ma/..."

# Indexer (seul le nouveau document est traité)
python -m src.pipeline index-all
```

**Procédure de vérification périodique :**

1. Consulter [bkam.ma/Supervision-bancaire](https://www.bkam.ma/Supervision-bancaire/Recueil-des-textes-legislatifs-et-reglementaires) pour identifier les nouveaux textes.
2. Télécharger les PDFs manuellement.
3. Importer avec `import-pdf` + `index-all`.
4. Marquer les documents vérifiés : `python -c "from src.versioning import mark_verified; ..."`.
5. Documenter la date de vérification.

> ⚠️ Le système ne vérifie **jamais** automatiquement l'actualité des textes sur le site BAM.
> Le statut "en vigueur" doit toujours être confirmé manuellement.

---

## 8. Diagramme du pipeline RAG

```
┌─────────────────────────────────────────────────────────┐
│                     INDEXATION (offline)                │
│                                                         │
│  PDF ──► Validation ──► Extraction ──► Chunking         │
│           (magic bytes,   (PyMuPDF,    (articles,       │
│            taille, nom)    pages)       fallback)       │
│                                    │                    │
│                            Embeddings (Google)          │
│                                    │                    │
│                         ChromaDB + BM25 Index           │
└─────────────────────────────────────────────────────────┘
                              │
                    (persisté sur disque)
                              │
┌─────────────────────────────────────────────────────────┐
│                      REQUÊTE (online)                   │
│                                                         │
│  Question ──► Hybride Search ──► RAG Chain ──► Réponse  │
│               (Vectoriel +       (Gemini,      (JSON    │
│                BM25 + RRF)        prompt       + cit.)  │
│                                   strict)              │
└─────────────────────────────────────────────────────────┘
```

---

## 9. Évolutions post-MVP

| Feature | Effort | Priorisation |
|---|---|---|
| Qdrant (prod) | Moyen | P1 |
| sentence-transformers local (offline) | Moyen | P1 |
| PostgreSQL | Faible | P1 |
| Reranker cross-encoder | Moyen | P2 |
| Collecte automatisée bkam.ma | Élevé | P2 |
| Historique utilisateur persisté | Faible | P2 |
| Docker Compose | Faible | P1 |
