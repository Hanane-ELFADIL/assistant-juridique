# Architecture — Assistant Juridique RAG Bank Al-Maghrib

> Dernière mise à jour : T001 / Phase 0
> Ce document reflète l'état réel du code — pas une projection future.

## 1. Objectif

Permettre à un utilisateur de poser des questions en langage naturel sur les textes
législatifs et réglementaires de Bank Al-Maghrib, et obtenir des réponses fondées
**uniquement** sur les passages réellement extraits des documents indexés.
Chaque réponse doit être vérifiable : titre, type, numéro, article, page, URL.

## 2. Stack technique (confirmée)

| Composant | Bibliothèque | Version | Statut |
|---|---|---|---|
| API backend | FastAPI + Uvicorn | 0.124.2 / 0.38.0 | ✅ installé |
| Validation / config | Pydantic v2 + pydantic-settings | 2.12.5 / 2.10.1 | ✅ installé |
| Variables d'env | python-dotenv | 1.0.0 | ✅ installé |
| Base de données | SQLAlchemy + SQLite | 2.0.45 | ✅ installé |
| Extraction PDF | PyMuPDF (`pymupdf`) | 1.26.1 | à installer |
| Embeddings | Google `text-embedding-004` via langchain-google-genai | 4.4.0 | ✅ installé |
| LLM | Google Gemini via langchain-google-genai | 4.4.0 | ✅ installé |
| Vectorstore | ChromaDB | 0.6.3 | à installer |
| Recherche lexicale | rank-bm25 | 0.2.2 | à installer |
| Empreintes | xxhash | 4.0.1 | ✅ installé |
| Tests | pytest | 9.1.1 | ✅ installé |

## 3. Structure des dossiers (état réel)

```
asistant-juridique/
│
├── .env.example              # Variables d'environnement (sans secrets)
├── .gitignore
├── requirements.txt          # Dépendances production
├── requirements-dev.txt      # Dépendances tests
├── TASKS.md                  # Backlog actif
│
├── docs/
│   ├── ARCHITECTURE.md       # Ce fichier
│   └── RISKS.md
│
├── data/
│   ├── raw/                  # PDFs originaux — jamais modifiés
│   ├── processed/            # Textes extraits, chunks JSON
│   └── chroma_db/            # Index vectoriel persisté
│
├── logs/                     # Journaux applicatifs
│
├── src/
│   ├── config.py             # Paramètres via pydantic-settings ✅
│   ├── database.py           # SQLAlchemy + init SQLite
│   ├── pipeline.py           # CLI d'indexation
│   │
│   ├── models/
│   │   ├── document.py       # Modèle Document (métadonnées)
│   │   └── chunk.py          # Modèle Chunk
│   │
│   ├── ingestion/
│   │   ├── fingerprint.py    # SHA-256 + détection doublons
│   │   ├── importer.py       # Import manuel PDF
│   │   └── inventory.py      # Rapport inventaire
│   │
│   ├── extraction/
│   │   ├── pdf_extractor.py  # Extraction PyMuPDF page par page
│   │   └── ocr.py            # OCR optionnel (Tesseract)
│   │
│   ├── chunking/
│   │   └── legal_chunker.py  # Chunking juridique + fallback
│   │
│   ├── embeddings/
│   │   └── provider.py       # Interface embeddings (Google)
│   │
│   ├── vectorstore/
│   │   └── chroma_store.py   # ChromaDB : upsert + query
│   │
│   ├── retrieval/
│   │   ├── bm25_index.py     # Index BM25
│   │   └── hybrid_search.py  # Fusion RRF (vectoriel + BM25)
│   │
│   ├── generation/
│   │   ├── prompts.py        # Prompts système RAG
│   │   └── rag_chain.py      # Pipeline RAG complet
│   │
│   └── api/
│       ├── main.py           # Application FastAPI
│       ├── schemas.py        # Schémas Pydantic requête/réponse
│       └── routes/
│           ├── health.py     # GET /health
│           └── chat.py       # POST /api/chat
│
└── tests/
    ├── conftest.py           # Fixtures partagées
    ├── fixtures/             # PDFs synthétiques
    └── test_ingestion.py     # Tests Phase 1
```

## 4. Pipeline de données

### 4a. Indexation (hors-ligne, CLI)
```
PDF source
  → import_pdf()       : copie dans data/raw/, SHA-256, enregistrement BDD
  → extract_pdf()      : PyMuPDF, page par page, texte brut + normalisé
  → chunk_document()   : découpage par articles/paragraphes (fallback si pas de structure)
  → embed_texts()      : Google text-embedding-004
  → chroma.upsert()    : stockage vectoriel + métadonnées (idempotent)
  → bm25.build()       : index lexical en mémoire
```

### 4b. Requête (en ligne, API)
```
POST /api/chat  { "question": "..." }
  → HybridSearch.search()   : vectoriel (Chroma) + BM25, fusion RRF
  → RAGChain.answer()       : prompt strict → Gemini → réponse structurée
  → ChatResponse            : answer + citations + sources + warnings
```

## 5. Décisions de conception

| Décision | Choix | Raison |
|---|---|---|
| LLM | Google Gemini | Déjà installé, aucune installation locale |
| Embeddings | Google text-embedding-004 | Multilingue FR/AR, déjà installé |
| Vectorstore | ChromaDB (fichier local) | Zéro serveur, migration Qdrant facile |
| BDD métadonnées | SQLite | Prototype local, migration PostgreSQL simple |
| Recherche lexicale | rank-bm25 | Léger, pur Python |
| Fusion | RRF (k=60) | Standard, documenté, paramétrable |
| Température LLM | 0.0 | Déterminisme maximal pour juridique |
| Import PDF | Manuel uniquement (MVP) | Contrôle de la provenance |

## 6. Règles invariantes

1. Les PDFs originaux ne sont **jamais** modifiés.
2. Chaque chunk connaît son document, sa page et son article.
3. Le LLM répond **uniquement** depuis les passages récupérés.
4. Les textes juridiques sont traités comme **données**, pas comme instructions.
5. Si les sources sont insuffisantes → message explicite, pas d'invention.
6. Aucun statut "en vigueur" n'est affirmé sans vérification humaine.

## 7. Dépendances à installer avant la Phase 1

```bash
python -m pip install pymupdf==1.26.1 chromadb==0.6.3 rank-bm25==0.2.2
```
