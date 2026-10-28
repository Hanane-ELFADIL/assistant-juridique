import { useState, useRef, useEffect } from 'react'
import ChatForm from './components/ChatForm'
import AnswerCard from './components/AnswerCard'
import ApiStatus from './components/ApiStatus'

const API_URL = '/api/chat'

const EXAMPLES = [
  "Quelles sont les conditions de capital minimum pour les banques ?",
  "Quelles sont les missions de Bank Al-Maghrib ?",
  "Quelles sont les conditions d'agrément bancaire ?",
  "Que disent les textes sur les ratios prudentiels ?",
]

export default function App() {
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
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
        if (resp.status === 503) throw new Error("Service non disponible — vérifiez que l'API est démarrée et les documents indexés.")
        if (resp.status === 422) throw new Error('Question invalide (3–500 caractères).')
        throw new Error(`Erreur serveur (${resp.status}).`)
      }
      const data = await resp.json()
      setHistory(prev => [...prev, data])
    } catch (err) {
      setError(err.message || 'Erreur de connexion.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>🏛️ Assistant Juridique — Bank Al-Maghrib</h1>
        <p>Recherche dans les textes législatifs et réglementaires officiels.</p>
        <ApiStatus />
      </header>

      <div className="app-disclaimer" role="note">
        ⚠️ Outil d'aide à la recherche documentaire — pas un avis juridique.
        Vérifiez les textes sur <a href="https://www.bkam.ma" target="_blank" rel="noopener noreferrer">bkam.ma</a>.
      </div>

      <main>
        <ChatForm onSubmit={handleQuestion} loading={loading} />

        {/* Exemples cliquables */}
        {!loading && history.length === 0 && (
          <div className="example-questions" aria-label="Questions exemples">
            {EXAMPLES.map(q => (
              <button key={q} className="example-btn" onClick={() => handleQuestion(q)}>
                {q}
              </button>
            ))}
          </div>
        )}

        {/* Chargement */}
        {loading && (
          <div className="loading" role="status" aria-live="polite">
            <div className="spinner" aria-hidden="true" />
            <span>Recherche dans les textes juridiques…</span>
          </div>
        )}

        {/* Erreur réseau */}
        {error && (
          <div className="answer-card error-card" role="alert">
            <strong>Erreur :</strong> {error}
          </div>
        )}

        {/* État vide */}
        {!loading && !error && history.length === 0 && (
          <div className="empty-state">
            <div className="icon">📚</div>
            <p>Posez une question sur les textes de Bank Al-Maghrib.</p>
          </div>
        )}

        {/* Historique */}
        {history.length > 0 && (
          <div className="history">
            {history.map((result, i) => (
              <AnswerCard key={i} result={result} />
            ))}
            <button className="btn-clear" onClick={() => { setHistory([]); setError(null) }}>
              Effacer l'historique
            </button>
          </div>
        )}

        <div ref={bottomRef} aria-hidden="true" />
      </main>

      <footer>
        Assistant Juridique RAG — Bank Al-Maghrib · Sources : textes officiels indexés · Pas d'avis juridique
      </footer>
    </div>
  )
}
