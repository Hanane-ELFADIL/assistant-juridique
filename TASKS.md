# TASKS.md — Assistant Juridique RAG Bank Al-Maghrib

> Backlog actif. Une tâche est cochée UNIQUEMENT si ses critères sont satisfaits et ses tests passent.
> Dernière mise à jour : Phase 7 complète — 99 tests passent.

---

## Phase 0 — Audit et cadrage ✅

- [x] T000 — Inspection du dépôt : Python 3.13, Git, dépendances listées.
- [x] T001 — Architecture documentée dans `docs/ARCHITECTURE.md`.
- [x] T002 — Périmètre MVP et limites dans `docs/RISKS.md`.
- [x] T003 — Ce fichier TASKS.md créé avec critères et dépendances.
- [x] T004 — Choix techniques dans `docs/ARCHITECTURE.md`.
- [x] T005 — Risques dans `docs/RISKS.md`.

## Phase 1 — Collecte et inventaire ✅

- [x] T100 — Modèle `Document` SQLAlchemy avec tous les champs requis.
- [x] T101 — `import_pdf()` : copie dans `data/raw/`, validation, métadonnées BDD.
- [ ] T102 — Étude de la page officielle BAM (à faire manuellement).
- [ ] T103 — Collecte limitée des liens publics (post-MVP).
- [x] T104 — Détection doublons par SHA-256 (`DuplicateDocumentError`).
- [x] T105 — Provenance enregistrée, fichier original préservé.
- [x] T106 — Détection PDF scannés (`is_scanned=True` si >50% pages vides).
- [x] T107 — CLI `python -m src.pipeline inventory` fonctionnel.
- [ ] T108 — Documentation mise à jour du corpus (à ajouter dans ARCHITECTURE.md).

## Phase 2 — Extraction PDF ✅

- [x] T200 — `extract_pdf()` avec PyMuPDF, page par page.
- [x] T201 — `page_number` (PDF) et `page_printed` (texte) conservés.
- [x] T202 — `pages_without_text` comptés, avertissement si >30%.
- [x] T203 — Interface OCR dans `src/extraction/ocr.py`, désactivée par défaut.
- [x] T204 — Normalisation : espaces insécables, caractères de contrôle.
- [x] T205 — Articles, chapitres, titres, annexes détectés par regex.
- [x] T206 — `text_raw` préservé séparément de `text_clean`.
- [x] T207 — `extraction_quality_report()` avec toutes les clés.
- [x] T208 — 10 tests pytest sur fixtures synthétiques. ✅

## Phase 3 — Chunking juridique ✅

- [x] T300 — `ChunkData` avec chunk_id, document_id, texte, hiérarchie, pages.
- [x] T301 — Chunking par articles détectés, méthode `legal`.
- [x] T302 — Sous-chunks avec `overlap_chars`, `parent_chunk_id` renseigné.
- [x] T303 — Fallback par taille fixe, `extraction_method='fallback'` marqué.
- [x] T304 — Hiérarchie `chapter`, `section`, `article_number` propagée.
- [x] T305 — `parent_chunk_id` sur chaque sous-chunk.
- [x] T306 — Chaque segment = 1 article max (pas de mélange).
- [x] T307 — Rapport avec `chunks_count`, `articles_found`, `chapters_found`, `sub_chunks`.
- [x] T308 — 17 tests pytest. ✅

## Phase 4 — Embeddings et indexation ✅

- [x] T400 — Classe abstraite `EmbeddingProvider`.
- [x] T401 — `GoogleEmbeddingProvider` : `text-embedding-004`, multilingue FR/AR.
- [x] T402 — `embed_texts()` et `embed_query()` implémentés.
- [x] T403 — `ChromaVectorStore.upsert_chunks()` avec ChromaDB 1.5.9.
- [x] T404 — Métadonnées complètes stockées dans Chroma.
- [x] T405 — Upsert idempotent : même chunk → count inchangé.
- [x] T406 — `delete_document_chunks()` + réindexation sans doublons.
- [x] T407 — `get_index_info()` retourne modèle et version.
- [x] T408 — 16 tests pytest intégrité BDD↔Chroma. ✅
- [ ] T409 — Documentation reconstruction index (à ajouter dans ARCHITECTURE.md).

## Phase 5 — Recherche hybride ✅

- [x] T500 — `chroma_store.query()` : recherche vectorielle avec scores.
- [x] T501 — `BM25Index.search()` : recherche lexicale BM25/TF-IDF.
- [x] T502 — `reciprocal_rank_fusion()` : fusion RRF documentée.
- [x] T503 — Filtres `where` sur métadonnées dans Chroma.
- [x] T504 — Détection référence article dans la requête → filtre automatique.
- [x] T505 — `LEGAL_WARNING` dans chaque réponse de `HybridSearch`.
- [ ] T506 — Reranker (post-MVP).
- [x] T507 — Résultats avec chunk_id, text, score, rank, citation.
- [x] T508 — Jeu de questions de test intégré dans les tests pytest.
- [ ] T509 — Mesures Recall@k / MRR (post-MVP).

## Phase 6 — Génération RAG ✅

- [x] T600 — `RAGChain` avec `ChatGoogleGenerativeAI`, configurable par `.env`.
- [x] T601 — `SYSTEM_PROMPT` interdit l'invention, impose le contexte.
- [x] T602 — Passages présentés comme DONNÉES dans le prompt.
- [x] T603 — Réponse structurée : `answer`, `sources`, `citations`, `warnings`.
- [x] T604 — Chaque citation contient le `chunk_id` réel.
- [x] T605 — `_build_citation()` : uniquement les champs non vides.
- [x] T606 — Aucune valeur vide ou inventée dans les citations.
- [x] T607 — Mode `insufficient_sources` + message avec URL BAM.
- [x] T608 — `CONTRADICTION_WARNING` si >1 document source.
- [x] T609 — `excerpt` distingue les extraits des résumés générés.
- [x] T610 — 11 tests pytest (prompts + RAG chain). ✅

## Phase 7 — API backend ✅

- [x] T700 — `create_app()` FastAPI avec lifespan, CORS, logging.
- [x] T701 — `GET /health` : 200, status, composants.
- [x] T702 — `POST /api/chat` : reçoit question, retourne `ChatResponse`.
- [x] T703 — `ChatRequest` : min_length=3, max_length=500, n_results 1-20.
- [x] T704 — `ChatResponse` : answer, citations, sources, warnings.
- [x] T705 — 503 si RAG absent, 500 si exception, 422 si requête invalide.
- [x] T706 — Logs : longueur de question uniquement, pas de clé API.
- [x] T707 — 25 tests pytest API. ✅
- [x] T708 — `/openapi.json` et `/docs` accessibles.

---

## Phases 8–12 — À faire

- [ ] Phase 8 — Interface utilisateur (T800–T808)
- [ ] Phase 9 — Sécurité et robustesse (T900–T909)
- [ ] Phase 10 — Actualité et versions (T1000–T1007)
- [ ] Phase 11 — Évaluation bout en bout (T1100–T1107)
- [ ] Phase 12 — Documentation et livraison (T1200–T1208)

---

## Résumé tests

| Phase | Tests | Statut |
|---|---|---|
| Phase 1 — Ingestion | 9 | ✅ |
| Phase 2 — Extraction | 10 | ✅ |
| Phase 3 — Chunking | 17 | ✅ |
| Phase 4 — Embeddings/Chroma/BM25 | 16 | ✅ |
| Phase 5 — Recherche hybride | 8 | ✅ |
| Phase 6 — Génération RAG | 11 | ✅ |
| Phase 7 — API FastAPI | 25 | ✅ |
| **Total** | **99** | **✅ 99/99** |
