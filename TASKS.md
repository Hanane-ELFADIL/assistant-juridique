# TASKS.md — Assistant Juridique RAG Bank Al-Maghrib

> Backlog actif. Une tâche est cochée UNIQUEMENT si ses critères sont satisfaits et ses tests passent.
> Dernière mise à jour : Phase 12 complète — **170 tests passent**.

---

## Phase 0 — Audit et cadrage ✅

- [x] T000 — Inspection du dépôt : Python 3.13, Git initialisé, dépendances listées.
- [x] T001 — Architecture documentée dans `docs/ARCHITECTURE.md`.
- [x] T002 — Périmètre MVP et limites dans `docs/RISKS.md`.
- [x] T003 — Ce fichier TASKS.md créé avec critères et dépendances.
- [x] T004 — Choix techniques documentés dans `docs/ARCHITECTURE.md`.
- [x] T005 — Risques documentés dans `docs/RISKS.md`.

---

## Phase 1 — Collecte et inventaire ✅

- [x] T100 — Modèle `Document` SQLAlchemy : id, titre, type, numéro, date, langue, URL, SHA-256, dates collecte/vérification, statut.
- [x] T101 — `import_pdf()` : validation magic bytes + taille, copie dans `data/raw/`, BDD.
- [ ] T102 — Étude page officielle BAM (documentation écrite dans ARCHITECTURE.md §7).
- [ ] T103 — Collecte automatisée des liens (post-MVP, hors périmètre).
- [x] T104 — Détection doublons SHA-256 (`DuplicateDocumentError`).
- [x] T105 — Provenance enregistrée, fichier original préservé sans modification.
- [x] T106 — Détection PDF scannés (`is_scanned=True` si >50% pages vides).
- [x] T107 — CLI `python -m src.pipeline inventory` fonctionnel + JSON.
- [x] T108 — Procédure de mise à jour du corpus documentée dans `docs/ARCHITECTURE.md` §7.

---

## Phase 2 — Extraction PDF ✅

- [x] T200 — `extract_pdf()` PyMuPDF, page par page. Testé sur le PDF BAM réel.
- [x] T201 — `page_number` (PDF) et `page_printed` (texte) conservés par page.
- [x] T202 — `pages_without_text` comptés, avertissement si >30%.
- [x] T203 — Interface OCR dans `src/extraction/ocr.py`, désactivée par défaut.
- [x] T204 — Normalisation Unicode NFC, espaces insécables, caractères de contrôle.
- [x] T205 — Articles, chapitres, titres, annexes détectés par regex FR + AR.
- [x] T206 — `text_raw` préservé séparément de `text_clean` dans `PageExtraction`.
- [x] T207 — `extraction_quality_report()` : pages, couverture, articles, avertissements.
- [x] T208 — 10 tests pytest sur fixtures synthétiques. ✅

---

## Phase 3 — Chunking juridique ✅

- [x] T300 — `ChunkData` : chunk_id, document_id, texte, hiérarchie, pages, URL.
- [x] T301 — Chunking par articles détectés, `extraction_method='legal'`.
- [x] T302 — Sous-chunks avec `overlap_chars=200`, `parent_chunk_id` renseigné.
- [x] T303 — Fallback taille fixe, `extraction_method='fallback'`, `has_warnings=True`.
- [x] T304 — Hiérarchie `chapter`, `section`, `article_number` propagée dans chaque chunk.
- [x] T305 — `parent_chunk_id` sur chaque sous-chunk.
- [x] T306 — Un segment = un article max (pas de mélange d'articles distincts).
- [x] T307 — Rapport : `chunks_count`, `articles_found`, `chapters_found`, `sub_chunks`, `warnings`.
- [x] T308 — 17 tests pytest (fixtures FR, AR, vide, long article). ✅

---

## Phase 4 — Embeddings et indexation ✅

- [x] T400 — Classe abstraite `EmbeddingProvider` avec `embed_texts()` et `embed_query()`.
- [x] T401 — `GoogleEmbeddingProvider` : `text-embedding-004`, multilingue FR/AR, documenté.
- [x] T402 — `embed_texts()` en batch de 50, `embed_query()` avec `retrieval_query`.
- [x] T403 — `ChromaVectorStore.upsert_chunks()` avec ChromaDB 1.5.9, persistance disque.
- [x] T404 — Métadonnées complètes stockées (document_id, article_number, page, source_url…).
- [x] T405 — Upsert idempotent : même chunk_id → mise à jour, pas doublon.
- [x] T406 — `delete_document_chunks()` + réindexation propre.
- [x] T407 — `get_index_info()` : modèle, version interface, total chunks.
- [x] T408 — 16 tests pytest intégrité BDD↔Chroma. ✅
- [x] T409 — Procédure de reconstruction complète documentée dans `docs/ARCHITECTURE.md` §6.

---

## Phase 5 — Recherche hybride ✅

- [x] T500 — `chroma_store.query()` : vectoriel avec scores, filtres, rang.
- [x] T501 — `BM25Index.search()` : tokenisation FR/AR, fallback TF-IDF.
- [x] T502 — `reciprocal_rank_fusion()` (RRF k=60, poids 0.6/0.4).
- [x] T503 — Filtres `where` sur métadonnées (doc_type, document_id…).
- [x] T504 — Détection référence article dans la requête → filtre automatique `article_number`.
- [x] T505 — `LEGAL_WARNING` dans chaque réponse de `HybridSearch`.
- [ ] T506 — Reranker (post-MVP).
- [x] T507 — Résultats : chunk_id, text, score, rank, citation complète.
- [x] T508 — Jeu de questions dans `tests/fixtures/eval_questions.json` (10 questions).
- [ ] T509 — Mesures Recall@k / MRR sur corpus réel (évaluation manuelle, post-MVP).

---

## Phase 6 — Génération RAG ✅

- [x] T600 — `RAGChain` avec `ChatGoogleGenerativeAI`, température=0, configurable via `.env`.
- [x] T601 — `SYSTEM_PROMPT` : interdit l'invention, impose le contexte fourni.
- [x] T602 — Passages présentés comme DONNÉES dans le prompt (anti-injection).
- [x] T603 — Réponse structurée : `answer`, `sources`, `citations`, `warnings`, `answer_type`.
- [x] T604 — Chaque citation contient le `chunk_id` réellement récupéré.
- [x] T605 — `_build_citation()` : uniquement les champs non vides.
- [x] T606 — Aucune valeur vide ou inventée dans les citations.
- [x] T607 — Mode `insufficient_sources` + message avec URL officielle BAM.
- [x] T608 — `CONTRADICTION_WARNING` si >1 document source dans la réponse.
- [x] T609 — `excerpt` distingue les extraits textuels des résumés générés.
- [x] T610 — 11 tests pytest (prompts + RAG chain avec mock LLM). ✅

---

## Phase 7 — API backend ✅

- [x] T700 — `create_app()` FastAPI avec lifespan, CORS restreint à localhost, logging.
- [x] T701 — `GET /health` : 200, status, composants (chromadb, pymupdf, langchain, bm25).
- [x] T702 — `POST /api/chat` : `ChatRequest` → `ChatResponse`.
- [x] T703 — `ChatRequest` : min_length=3, max_length=500, n_results 1–20, filters dict.
- [x] T704 — `ChatResponse` : answer, answer_type, citations, sources, warnings, search_method.
- [x] T705 — 503 si RAG absent, 500 si exception interne, 422 si requête invalide.
- [x] T706 — Logs : longueur de question uniquement, pas de contenu ni de clé API.
- [x] T707 — 25 tests pytest API (validation, erreurs, logging, OpenAPI). ✅
- [x] T708 — `/openapi.json` et `/docs` accessibles et documentés.

---

## Phase 8 — Interface utilisateur ✅

- [x] T800 — Frontend React + Vite choisi (dépôt neuf, pas de framework existant).
- [x] T801 — Page de chat simple, accessible (aria-label, role, sr-only), responsive mobile.
- [x] T802 — Réponses affichées avec citations, extraits et scores.
- [x] T803 — Liens vers la source officielle, numéro de page dans la citation.
- [x] T804 — Avertissement légal permanent + statut non garanti affiché.
- [x] T805 — Spinner de chargement, gestion erreurs réseau (503/422/500), état vide.
- [x] T806 — Historique de session en mémoire, bouton "Effacer l'historique".
- [ ] T807 — Vue administration avancée (post-MVP).
- [x] T808 — Accessibilité : aria, focus-visible, responsive 320px+, lisibilité française.

---

## Phase 9 — Sécurité et robustesse ✅

- [x] T900 — `validate_required_config()` : vérifie GOOGLE_API_KEY + DATABASE_URL.
- [x] T901 — `.env` dans `.gitignore`, `.env.example` avec placeholder uniquement, pas de vraie clé.
- [x] T902 — `validate_file()` : magic bytes PDF, taille max, extension, nom sûr.
- [x] T903 — `validate_filename()` + `safe_join()` : anti path traversal, null bytes, chars interdits.
- [ ] T904 — Limites de débit (post-MVP, nécessite déploiement exposé).
- [x] T905 — `detect_prompt_injection()` + `sanitize_query()` : patterns d'injection détectés.
- [x] T906 — Avertissement documenté dans RISKS.md sur l'envoi de données à des services externes.
- [ ] T907 — Politique de conservation des logs (post-MVP).
- [x] T908 — 30 tests pytest sécurité. ✅
- [x] T909 — Risques résiduels documentés dans `docs/RISKS.md`.

---

## Phase 10 — Actualité et versions ✅

- [x] T1000 — `collected_at` et `last_verified_at` enregistrés ; `mark_verified()` implémenté.
- [x] T1001 — `check_file_changed()` : détection par SHA-256, fichier manquant signalé.
- [x] T1002 — `archive_document_version()` : copie horodatée dans `data/raw/archive/`.
- [x] T1003 — `get_unverified_documents()` ; avertissement sur les documents non vérifiés.
- [x] T1004 — `get_dates_summary()` : publication, entrée en vigueur, collecte, vérification.
- [x] T1005 — `generate_staleness_report()` : never_verified, missing_files, file_changed.
- [x] T1006 — Aucune conclusion juridique automatique sur l'abrogation ou l'applicabilité.
- [x] T1007 — Procédure de revue périodique documentée dans `docs/ARCHITECTURE.md` §7.
- Tests : 17 tests pytest. ✅

---

## Phase 11 — Évaluation bout en bout ✅

- [x] T1100 — Jeu de 10 questions dans `tests/fixtures/eval_questions.json`.
- [x] T1101 — Questions simples, complexes, hors corpus et référence directe.
- [x] T1102 — `recall_at_k()` et `mean_reciprocal_rank()` implémentés et testés.
- [x] T1103 — `verify_citations()` : chunk_id réel, extrait non vide, pas de champs vides.
- [x] T1104 — `check_answer_faithfulness()` : cohérence answer_type/citations/warnings.
- [x] T1105 — `check_unavailable_component()` : LLM absent → réponse gracieuse.
- [x] T1106 — `generate_eval_report()` : métriques reproductibles.
- [x] T1107 — Disclaimer explicite : système non validé pour usage bancaire opérationnel.
- Tests : 24 tests pytest. ✅

---

## Phase 12 — Documentation et livraison ✅

- [x] T1200 — `README.md` complet avec présentation et prérequis.
- [x] T1201 — Installation pas à pas sous Windows PowerShell documentée.
- [x] T1202 — Configuration `.env`, options LLM et embeddings documentées.
- [x] T1203 — Pipeline complet (import, extraction, chunking, indexation, réindexation) documenté.
- [x] T1204 — Endpoints API documentés avec exemples de requêtes et réponses.
- [x] T1205 — Schéma d'architecture et diagramme pipeline RAG dans ARCHITECTURE.md.
- [x] T1206 — Section dépannage dans README avec erreurs courantes.
- [x] T1207 — Commandes tests, lint disponibles documentées.
- [x] T1208 — Installation reproductible vérifiée : README auto-suffisant.

---

## Résumé final des tests

| Phase | Fichier de tests | Tests |
|---|---|---|
| Phase 1 — Ingestion | test_ingestion.py | 9 |
| Phase 2 — Extraction | test_extraction.py | 10 |
| Phase 3 — Chunking | test_chunking.py | 17 |
| Phase 4 — Embeddings/Chroma/BM25 | test_vectorstore.py | 16 |
| Phase 5 — Recherche hybride | test_retrieval.py | 8 |
| Phase 6 — Génération RAG | test_generation.py | 11 |
| Phase 7 — API FastAPI | test_api.py | 25 |
| Phase 9 — Sécurité | test_security.py | 30 |
| Phase 10 — Versioning | test_versioning.py | 17 |
| Phase 11 — Évaluation | test_evaluation.py | 24 |
| **Total** | | **167** |

> Note : 3 tests supplémentaires dans conftest.py → **170 au total**.
