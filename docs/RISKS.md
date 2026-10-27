# Risques, périmètre MVP et limites — Assistant Juridique RAG BAM

> Dernière mise à jour : T002 / Phase 0

---

## 1. Périmètre MVP

### Ce que le MVP fait

| Fonctionnalité | Détail |
|---|---|
| Import PDF local | Un ou plusieurs PDFs copiés manuellement dans `data/raw/` |
| Extraction texte | PyMuPDF, page par page, texte numérique uniquement |
| Chunking | Par articles et paragraphes, fallback taille fixe |
| Indexation | Google Embeddings + ChromaDB local, BM25 en mémoire |
| Recherche | Hybride vectoriel + BM25, fusion RRF |
| Réponse | Gemini Flash, basée uniquement sur les passages récupérés |
| Citations | Titre, type, numéro, article, page, URL si disponibles |
| API | `GET /health` + `POST /api/chat` (JSON) |
| Interface | API JSON uniquement — pas de frontend pour le MVP |

### Ce que le MVP ne fait PAS

| Hors périmètre MVP | Note |
|---|---|
| Interface web | Phase 8, après validation de l'API |
| Collecte automatique depuis bkam.ma | T102/T103, étude à faire |
| OCR pour PDFs scannés | T203, optionnel post-MVP |
| Reranker | T506, post-MVP si métriques le justifient |
| Historique de session | T806, post-MVP |
| Mise à jour automatique du corpus | Phase 10, post-MVP |
| Déploiement Docker | Post validation sans conteneurs |
| Avis juridique | Jamais — hors périmètre par principe |

---

## 2. Limites connues et acceptées

### 2.1 Limites juridiques fondamentales

- **Pas d'avis juridique.** L'assistant est un outil de recherche documentaire.
- **Statut "en vigueur" non garanti.** Un texte indexé n'est pas nécessairement applicable.
- **Pas de consolidation automatique.** Les textes modifiés ou abrogés partiellement ne sont pas fusionnés.
- **Pas d'inventaire exhaustif.** Le corpus = les PDFs importés manuellement. Des textes plus récents peuvent exister sur bkam.ma sans être indexés.
- **Aucune référence inventée.** Si une métadonnée (numéro, date, article) est absente du document, elle n'est pas générée.

### 2.2 Limites techniques du MVP

| Limite | Impact | Mitigation |
|---|---|---|
| PyMuPDF non installé | Blocant Phase 2 | À installer avant T200 |
| ChromaDB non installé | Blocant Phase 4 | À installer avant T403 |
| rank-bm25 non installé | BM25 dégradé | Fallback TF-IDF interne |
| Python 3.13 très récent | Incompatibilités possibles | Tester chaque install |
| Google API Key requise | Embeddings et LLM inopérants sans clé | Documenter dans README |
| Arabe partiel | Embeddings Google supportent l'arabe mais pas mesuré | Tester sur fixtures bilingues |
| BM25 en mémoire | Perdu au redémarrage | Reconstruit depuis la BDD au démarrage |

### 2.3 Risques de sécurité (MVP)

- **Injection de prompt :** les textes juridiques sont traités comme données, jamais comme instructions LLM.
- **Secrets :** `.env` exclu de Git. Aucune clé dans le code.
- **Fichiers importés :** validation magic bytes + taille avant copie.
- **Path traversal :** les noms de fichiers sont sanitisés avant copie.

---

## 3. Hypothèses de départ

1. Le PDF `Recueil des textes législatifs et réglementaires de BAM_VF.pdf` est numérique (non scanné). À confirmer en T202.
2. La clé `GOOGLE_API_KEY` est disponible chez l'utilisateur.
3. Déploiement local Windows uniquement pour le MVP.
4. Langue principale : français. L'arabe peut être présent dans certains documents.
5. L'utilisateur sait que l'assistant est un outil de recherche, pas un juriste.

---

## 4. Critères de sortie du MVP

Le MVP est considéré fonctionnel quand :

- [ ] Le PDF BAM peut être importé, extrait et indexé sans erreur.
- [ ] Une question en français retourne une réponse avec citations vérifiables.
- [ ] Une question sans réponse dans le corpus retourne le message "sources insuffisantes".
- [ ] `GET /health` répond 200.
- [ ] `POST /api/chat` répond en moins de 30 secondes.
- [ ] Aucune clé API n'est dans le code ou les logs.
- [ ] Les tests pytest passent.
