/**
 * Application principale — T801–T808
 * - Chat simple, accessible, responsive
 * - Citations vérifiables avec liens sources
 * - Avertissements et sources insuffisantes affichés clairement
 * - Historique de session en mémoire (T806)
 * - État vide, chargement, erreurs (T805)
 */
import { useState, useRef, useEffect } from 'react'
import ChatForm from './components/ChatForm'
import AnswerCard from './components/AnswerCard'
import ApiStatus from './components/ApiStatus'

const API_URL = '/api/chat'

export default function App() {
  const [history, setHistory] = useState([])   // T806 : historique session
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const bottomRef = useRef(null)

  // Scroll automatique vers le bas — T805
  useEffect(() => {
    if (bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [history, loading])

  async function handleQuestion(question) {
    setLoading(true)
    setError(null)

    try {
      const resp = await fetch(API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      })

      if (!resp.ok) {
        if (resp.status === 503) {
          throw new Error("Le service n'est pas disponible. Vérifiez que l'API est démarrée et que les documents sont indexés.")
        }
        if (resp.status === 422) {
          throw new Error('Question invalide. Vérifiez la longueur (3–500 caractères).')
        }
        throw new Error(`Erreur serveur (${resp.status}).`)
      }

      const data = await resp.json()
      setHistory((prev) => [...prev, data])

    } catch (err) {
      setError(err.message || 'Erreur de connexion au serveur.')
    } finally {
      setLoading(false)
    }
  }

  function handleClear() {
    setHistory([])
    setError(null)
  }

  return (
    <div className="app">
      {/* En-tête — T801 */}
      <header className="app-header">
        <h1>🏛️ Assistant Juridique — Bank Al-Maghrib</h1>
        <p>Recherche documentaire sur les textes législatifs et réglementaires officiels.</p>
        <ApiStatus />
      </header>

      {/* Avertissement légal — T804 */}
      <div className="app-disclaimer" role="note">
        ⚠️ Cet outil est une aide à la recherche documentaire, pas un avis juridique.
        Les réponses sont fondées uniquement sur les documents indexés.
        Vérifiez toujours le statut des textes sur{' '}
        <a href="https://www.bkam.ma" target="_blank" rel="noopener noreferrer">bkam.ma</a>.
      </div>

      <main>
        {/* Formulaire — T801 */}
        <ChatForm onSubmit={handleQuestion} loading={loading} />

        {/* Indicateur de chargement — T805 */}
        {loading && (
          <div className="loading" role="status" aria-live="polite">
            <div className="spinner" aria-hidden="true" />
            <span>Recherche en cours…</span>
          </div>
        )}

        {/* Erreur réseau / API — T805 */}
        {error && (
          <div className="answer-card error-card" role="alert">
            <strong>Erreur :</strong> {error}
          </div>
        )}

        {/* État vide — T805 */}
        {!loading && !error && history.length === 0 && (
          <div className="empty-state" aria-label="Aucune question posée">
            <div className="icon" aria-hidden="true">📚</div>
            <p>Posez une question sur les textes de Bank Al-Maghrib.</p>
            <p style={{ marginTop: '0.5rem', fontSize: '0.85rem' }}>
              Exemple : <em>Quelles sont les conditions de capital minimum pour les banques ?</em>
            </p>
          </div>
        )}

        {/* Historique des réponses — T806 */}
        {history.length > 0 && (
          <div className="history" aria-label="Historique des réponses">
            {history.map((result, i) => (
              <AnswerCard key={i} result={result} />
            ))}
            {/* Bouton effacer l'historique */}
            <button
              onClick={handleClear}
              style={{
                alignSelf: 'flex-start',
                background: 'none',
                border: '1px solid #dee2e6',
                borderRadius: '6px',
                padding: '0.4rem 0.8rem',
                cursor: 'pointer',
                fontSize: '0.82rem',
                color: '#6c757d',
              }}
              aria-label="Effacer l'historique"
            >
              Effacer l'historique
            </button>
          </div>
        )}

        <div ref={bottomRef} aria-hidden="true" />
      </main>

      <footer>
        Assistant Juridique RAG — Bank Al-Maghrib · Sources : textes officiels indexés ·
        Réponses non vérifiées juridiquement
      </footer>

      {/* CSS utilitaire accessibilité */}
      <style>{`.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);border:0}`}</style>
    </div>
  )
}
