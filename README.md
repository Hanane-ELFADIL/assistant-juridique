# Assistant Juridique RAG — Bank Al-Maghrib

Outil de recherche documentaire sur les textes législatifs et réglementaires de Bank Al-Maghrib.
Les réponses sont fondées **uniquement** sur les documents indexés — chaque citation est vérifiable.

> ⚠️ Cet outil est une aide à la recherche documentaire, **pas un avis juridique**.
> Un texte indexé n'est pas nécessairement en vigueur. Vérifiez toujours sur [bkam.ma](https://www.bkam.ma).

---

## Prérequis

| Composant | Version minimale |
|-----------|-----------------|
| Python | 3.11+ (testé sur 3.13) |
| Node.js | 18+ (pour le frontend) |
| Git | 2.x |
| Clé API Google Gemini | Gratuite sur [aistudio.google.com](https://aistudio.google.com/app/apikey) |

---

## Installation (Windows PowerShell)

```powershell
# 1. Cloner le dépôt
git clone https://github.com/Hanane-ELFADIL/assistant-juridique.git
cd asistant-juridique

# 2. Créer et activer l'environnement virtuel Python
python -m venv .venv
.venv\Scripts\Activate.ps1

# 3. Installer les dépendances Python
pip install -r requirements.txt

# 4. Configurer les variables d'environnement
Copy-Item .env.example .env
notepad .env    # Renseigner GOOGLE_API_KEY
```

---

## Configuration (`.env`)

Copiez `.env.example` vers `.env` et remplissez vos valeurs. **Ne commitez jamais `.env`.**

```env
# Obligatoire
GOOGLE_API_KEY=votre_cle_google_ici

# Optionnel (valeurs par défaut utilisables)
GEMINI_MODEL=gemini-1.5-flash
EMBEDDING_MODEL=models/text-embedding-004
DATABASE_URL=sqlite:///./data/bam_rag.db
DATA_RAW_DIR=./data/raw
CHROMA_PERSIST_DIR=./data/chroma_db
API_HOST=127.0.0.1
API_PORT=8000
LOG_LEVEL=INFO
```

Voir `.env.example` pour toutes les options commentées.

---

## Utilisation — Pipeline d'indexation

### Étape 1 : Importer le PDF

```powershell
python -m src.pipeline import-pdf `
  "Recueil des textes législatifs et réglementaires de BAM _ VF.pdf" `
  --title "Recueil des textes législatifs et réglementaires — Bank Al-Maghrib" `
  --text-type recueil `
  --url "https://www.bkam.ma/Supervision-bancaire/Recueil-des-textes-legislatifs-et-reglementaires"
```

### Étape 2 : Indexer (extraction + chunking + embeddings)

```powershell
python -m src.pipeline index-all
```

> ⏱ Selon la taille du PDF et la vitesse de l'API Google, cette étape peut prendre plusieurs minutes.

### Vérifier l'état

```powershell
python -m src.pipeline inventory     # Liste les documents importés
python -m src.pipeline status        # État de l'index vectoriel
```

---

## Démarrer l'API

```powershell
uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --reload
```

| URL | Description |
|-----|-------------|
| http://127.0.0.1:8000/health | État des composants |
| http://127.0.0.1:8000/docs | Documentation interactive (Swagger) |
| http://127.0.0.1:8000/redoc | Documentation ReDoc |
| http://127.0.0.1:8000/openapi.json | Schéma OpenAPI |

---

## Démarrer le frontend

```powershell
cd frontend
npm install
npm run dev
# Ouvrir http://localhost:3000
```

---

## Utilisation de l'API

### Question-réponse

```bash
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d "{\"question\": \"Quelles sont les conditions de capital minimum pour les banques ?\"}"
```

**Réponse :**
```json
{
  "answer": "Selon l'Article 2 de la Loi 34-03...",
  "answer_type": "sourced",
  "question": "Quelles sont les conditions de capital minimum pour les banques ?",
  "citations": [
    {
      "chunk_id": "abc123",
      "citation": {
        "title": "Loi 34-03 relative aux établissements de crédit",
        "type": "loi",
        "number": "34-03",
        "article": "Article 2",
        "page": 20
      },
      "excerpt": "Le capital minimum des banques est fixé...",
      "score": 0.87,
      "rank": 1
    }
  ],
  "sources": [
    {
      "document_id": "...",
      "title": "Loi 34-03",
      "type": "loi",
      "url": "https://www.bkam.ma/..."
    }
  ],
  "warnings": [
    "⚠️ Ces résultats sont classés par similarité textuelle, non par applicabilité juridique."
  ]
}
```

### Paramètres optionnels

```json
{
  "question": "Votre question",
  "n_results": 5,
  "filters": {"doc_type": "circulaire"}
}
```

---

## Tests

```powershell
# Tous les tests
python -m pytest tests/ -v

# Un module spécifique
python -m pytest tests/test_extraction.py -v
python -m pytest tests/test_api.py -v

# Avec couverture
python -m pytest tests/ --cov=src --cov-report=term-missing
```

**État actuel : 194 tests, 0 échec.**

---

## Structure du projet

```
asistant-juridique/
├── .env.example              # Variables d'environnement (modèle sans secrets)
├── .gitignore
├── README.md                 # Ce fichier
├── TASKS.md                  # Backlog et état des tâches
├── requirements.txt          # Dépendances Python production
├── requirements-dev.txt      # Dépendances développement/test
│
├── docs/
│   ├── ARCHITECTURE.md       # Choix techniques, stack, pipeline
│   └── RISKS.md              # Risques, périmètre MVP, limites
│
├── data/
│   ├── raw/                  # PDFs originaux (jamais modifiés)
│   ├── processed/            # Textes extraits, chunks
│   └── chroma_db/            # Index vectoriel ChromaDB
│
├── frontend/                 # Interface React + Vite
│   ├── src/
│   │   ├── App.jsx           # Application principale
│   │   ├── components/
│   │   │   ├── ChatForm.jsx  # Formulaire de question
│   │   │   ├── AnswerCard.jsx # Réponse + citations
│   │   │   ├── Citation.jsx  # Citation individuelle
│   │   │   └── ApiStatus.jsx # État du backend
│   │   └── index.css
│   └── package.json
│
├── src/
│   ├── config.py             # Configuration centralisée (pydantic-settings)
│   ├── database.py           # SQLAlchemy + SQLite
│   ├── pipeline.py           # CLI : import-pdf, index-all, inventory, status
│   ├── security.py           # Validation fichiers, path traversal, injection
│   ├── versioning.py         # Dates, versions, rapport fraîcheur
│   ├── evaluation.py         # Métriques RAG (Recall@k, MRR, fidélité)
│   │
│   ├── models/
│   │   ├── document.py       # Modèle Document SQLAlchemy
│   │   └── chunk.py          # Modèle Chunk SQLAlchemy
│   │
│   ├── ingestion/
│   │   ├── fingerprint.py    # SHA-256, noms de fichiers sûrs
│   │   ├── importer.py       # Import PDF : validation + copie + BDD
│   │   └── inventory.py      # Rapport inventaire
│   │
│   ├── extraction/
│   │   ├── pdf_extractor.py  # Extraction PyMuPDF page par page
│   │   └── ocr.py            # Interface OCR optionnelle (Tesseract)
│   │
│   ├── chunking/
│   │   └── legal_chunker.py  # Chunking juridique + fallback
│   │
│   ├── embeddings/
│   │   └── provider.py       # Interface embeddings (Google text-embedding-004)
│   │
│   ├── vectorstore/
│   │   └── chroma_store.py   # ChromaDB : upsert idempotent + query + filtres
│   │
│   ├── retrieval/
│   │   ├── bm25_index.py     # Index BM25 lexical
│   │   └── hybrid_search.py  # Fusion RRF vectoriel + BM25
│   │
│   ├── generation/
│   │   ├── prompts.py        # Prompts système RAG (anti-invention, anti-injection)
│   │   └── rag_chain.py      # Pipeline RAG : recherche → LLM → citations
│   │
│   └── api/
│       ├── main.py           # Application FastAPI + lifespan
│       ├── schemas.py        # Schémas Pydantic requête/réponse
│       └── routes/
│           ├── health.py     # GET /health
│           └── chat.py       # POST /api/chat
│
└── tests/
    ├── conftest.py
    ├── fixtures/
    │   └── eval_questions.json   # Jeu d'évaluation (10 questions)
    ├── test_ingestion.py     # 9 tests
    ├── test_extraction.py    # 10 tests
    ├── test_chunking.py      # 17 tests
    ├── test_vectorstore.py   # 16 tests
    ├── test_retrieval.py     # 8 tests
    ├── test_generation.py    # 11 tests
    ├── test_api.py           # 25 tests
    ├── test_security.py      # 30 tests
    ├── test_versioning.py    # 17 tests
    └── test_evaluation.py    # 24 tests
```

---

## Dépannage

| Problème | Cause probable | Solution |
|----------|---------------|----------|
| `ModuleNotFoundError: pydantic_settings` | Package manquant | `pip install pydantic-settings` |
| `ModuleNotFoundError: pymupdf` | Package manquant | `pip install pymupdf` |
| `ModuleNotFoundError: chromadb` | Package manquant | `pip install chromadb` |
| `API key not valid` | Clé Google invalide | Vérifier `GOOGLE_API_KEY` dans `.env` |
| `503 Service Unavailable` | Pipeline non initialisé | Lancer `python -m src.pipeline index-all` |
| Port 8000 occupé | Autre service | `uvicorn ... --port 8001` |
| `PermissionError` sur Windows (ChromaDB) | Fichiers verrouillés | Redémarrer l'API |

---

## Limites importantes

- Les réponses **ne constituent pas** un avis juridique.
- Un texte indexé **n'est pas nécessairement en vigueur** — vérifiez toujours sur [bkam.ma](https://www.bkam.ma).
- L'assistant **n'invente jamais** de numéros d'articles, de dates ou de citations.
- Si les sources sont insuffisantes, un message explicite est affiché.
- Le corpus n'est **pas mis à jour automatiquement** — relancez `import-pdf` + `index-all` pour ajouter des documents.
- Le système **n'est pas validé** pour un usage bancaire opérationnel (validation juridique et sécurité requises).

---

## Références

- [Bank Al-Maghrib — Recueil des textes législatifs](https://www.bkam.ma/Supervision-bancaire/Recueil-des-textes-legislatifs-et-reglementaires)
- [Google Gemini API](https://aistudio.google.com/app/apikey)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [ChromaDB Documentation](https://docs.trychroma.com/)
