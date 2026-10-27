# Assistant Juridique RAG — Bank Al-Maghrib

Outil de recherche documentaire sur les textes législatifs et réglementaires de Bank Al-Maghrib.  
Les réponses sont fondées **uniquement** sur les documents indexés — chaque citation est vérifiable.

> ⚠️ Cet outil est un aide à la recherche, pas un avis juridique.

---

## Prérequis

- Python 3.13+
- Git
- Une clé API Google Gemini ([obtenir ici](https://aistudio.google.com/app/apikey))

---

## Installation (Windows PowerShell)

```powershell
# 1. Cloner le dépôt
git clone <url-du-repo>
cd asistant-juridique

# 2. Créer l'environnement virtuel
python -m venv .venv
.venv\Scripts\Activate.ps1

# 3. Installer les dépendances
pip install -r requirements.txt

# 4. Configurer les variables d'environnement
Copy-Item .env.example .env
# Ouvrir .env et renseigner GOOGLE_API_KEY
```

---

## Configuration (`.env`)

```env
GOOGLE_API_KEY=votre_cle_google_ici
GEMINI_MODEL=gemini-1.5-flash
EMBEDDING_MODEL=models/text-embedding-004
DATABASE_URL=sqlite:///./data/bam_rag.db
```

Voir `.env.example` pour toutes les options.

---

## Importer et indexer le PDF BAM

```powershell
# Importer le PDF
python -m src.pipeline import-pdf "Recueil des textes législatifs et réglementaires de BAM _ VF.pdf" `
  --title "Recueil des textes législatifs et réglementaires — Bank Al-Maghrib" `
  --text-type recueil `
  --url "https://www.bkam.ma/Supervision-bancaire/Recueil-des-textes-legislatifs-et-reglementaires"

# Indexer tous les documents importés
python -m src.pipeline index-all

# Vérifier l'inventaire
python -m src.pipeline inventory

# Vérifier l'état de l'index
python -m src.pipeline status
```

---

## Démarrer l'API

```powershell
uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --reload
```

- **Documentation interactive :** http://127.0.0.1:8000/docs
- **Santé :** http://127.0.0.1:8000/health

---

## Utilisation

```bash
# Poser une question
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "Quelles sont les conditions de capital minimum pour les banques ?"}'
```

Réponse :
```json
{
  "answer": "Selon l'Article 2 de la Loi 34-03...",
  "answer_type": "sourced",
  "citations": [{"chunk_id": "...", "citation": {"title": "...", "article": "Article 2", "page": 20}, "excerpt": "..."}],
  "sources": [{"document_id": "...", "title": "Loi 34-03", "type": "loi"}],
  "warnings": ["⚠️ Ces résultats sont classés par similarité textuelle, non par applicabilité juridique."]
}
```

---

## Tests

```powershell
# Tous les tests
python -m pytest tests/ -v

# Un module spécifique
python -m pytest tests/test_extraction.py -v
```

99 tests, 0 échec.

---

## Structure du projet

```
asistant-juridique/
├── .env.example          # Variables d'environnement (modèle)
├── requirements.txt      # Dépendances production
├── data/raw/             # PDFs originaux (jamais modifiés)
├── docs/
│   ├── ARCHITECTURE.md   # Choix techniques
│   └── RISKS.md          # Risques et limites
├── src/
│   ├── config.py         # Configuration centralisée
│   ├── pipeline.py       # CLI d'indexation
│   ├── ingestion/        # Import et inventaire
│   ├── extraction/       # Extraction PDF (PyMuPDF)
│   ├── chunking/         # Segmentation juridique
│   ├── embeddings/       # Interface embeddings (Google)
│   ├── vectorstore/      # ChromaDB
│   ├── retrieval/        # Recherche hybride (vectoriel + BM25 + RRF)
│   ├── generation/       # Pipeline RAG (Gemini)
│   └── api/              # FastAPI (GET /health, POST /api/chat)
└── tests/                # 99 tests pytest
```

---

## Limites importantes

- Les réponses ne constituent **pas** un avis juridique.
- Un texte indexé n'est **pas nécessairement en vigueur** — vérifiez toujours sur [bkam.ma](https://www.bkam.ma).
- L'assistant n'invente jamais de numéros d'articles, de dates ou de citations.
- Si les sources sont insuffisantes, un message explicite est affiché.
