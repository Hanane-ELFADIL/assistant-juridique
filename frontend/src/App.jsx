import { useState, useRef, useEffect, useCallback } from 'react'

const EXAMPLES = [
  "Quelles sont les conditions de capital minimum pour les banques ?",
  "Quelles sont les missions de Bank Al-Maghrib ?",
  "Quelles sont les conditions d'obtention d'un agrément bancaire ?",
  "Quels sont les ratios prudentiels applicables aux établissements de crédit ?",
  "Que dit la loi bancaire sur la protection des déposants ?",
  "Quelles sont les sanctions prévues en cas de non-respect de la réglementation ?",
]

export default function App() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [apiStatus, setApiStatus] = useState('checking')
  const bottomRef = useRef(null)
  const textareaRef = useRef(null)

  // Vérification de l'API au démarrage
  useEffect(() => {
    fetch('/health').then(r => r.json())
      .then(d => setApiStatus(d.status === 'ok' ? 'ok' : 'degraded'))
      .catch(() => setApiStatus('error'))
  }, [])

  // Scroll automatique
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  // Auto-resize textarea
  function handleInput(e) {
    setInput(e.target.value)
    const el = e.target
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 180) + 'px'
  }

  // Envoi via Enter (Shift+Enter = nouvelle ligne)
  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendQuestion(input)
    }
  }

  const sendQuestion = useCallback(async (question) => {
    const q = question.trim()
    if (!q || loading) return

    setInput('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }

    // Ajoute le message utilisateur
    setMessages(prev => [...prev, { role: 'user', content: q }])
    setLoading(true)

    try {
      const resp = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q }),
      })

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}))
        throw new Error(err.detail || `Erreur ${resp.status}`)
      }

      const data = await resp.json()
      setMessages(prev => [...prev, { role: 'assistant', ...data }])
    } catch (err) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        answer_type: 'error',
        answer: err.message || 'Erreur de connexion au serveur.',
        citations: [], sources: [], warnings: [],
        question: q,
      }])
    } finally {
      setLoading(false)
    }
  }, [loading])

  function newChat() {
    setMessages([])
    setInput('')
  }

  const statusLabel = apiStatus === 'ok' ? 'En ligne' : apiStatus === 'degraded' ? 'Dégradé' : 'Hors ligne'

  return (
    <div className="app">
      {/* Sidebar */}
      <aside className="sidebar" aria-label="Navigation">
        <div className="sidebar-logo">
          <span className="logo-icon">🏛️</span>
          <div>
            <h2>Assistant Juridique</h2>
            <p>Bank Al-Maghrib</p>
          </div>
        </div>

        <button className="btn-new-chat" onClick={newChat} aria-label="Nouvelle conversation">
          ✏️ Nouvelle conversation
        </button>

        <div className="sidebar-section">Questions fréquentes</div>
        <nav className="example-list" aria-label="Exemples de questions">
          {EXAMPLES.map(q => (
            <button key={q} className="example-item" onClick={() => sendQuestion(q)}>
              {q}
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <p>
            Outil de recherche documentaire — pas un avis juridique.<br />
            <a href="https://www.bkam.ma" target="_blank" rel="noopener noreferrer">bkam.ma</a>
          </p>
        </div>
      </aside>

      {/* Zone de chat */}
      <main className="chat-area">
        <header className="chat-header">
          <h1>Recherche dans les textes législatifs BAM</h1>
          <div className="status-pill" aria-live="polite">
            <span className={`status-dot ${apiStatus}`} aria-hidden="true" />
            {statusLabel}
          </div>
        </header>

        {/* Messages */}
        <div className="messages" role="log" aria-live="polite" aria-label="Conversation">
          {messages.length === 0 ? (
            <EmptyState onSelect={sendQuestion} />
          ) : (
            messages.map((msg, i) => (
              msg.role === 'user'
                ? <UserMessage key={i} content={msg.content} />
                : <AssistantMessage key={i} data={msg} />
            ))
          )}

          {loading && (
            <div className="message">
              <div className="avatar assistant" aria-hidden="true">⚖️</div>
              <div className="bubble assistant" role="status" aria-label="Recherche en cours">
                <div className="typing">
                  <span /><span /><span />
                </div>
              </div>
            </div>
          )}
          <div ref={bottomRef} aria-hidden="true" />
        </div>

        {/* Input */}
        <div className="input-area">
          <div className="input-wrap">
            <label htmlFor="chat-input" className="sr-only">Votre question</label>
            <textarea
              id="chat-input"
              ref={textareaRef}
              className="chat-textarea"
              rows={1}
              value={input}
              onChange={handleInput}
              onKeyDown={handleKeyDown}
              placeholder="Posez une question sur les textes de Bank Al-Maghrib…"
              disabled={loading}
              aria-label="Zone de saisie de question"
            />
            <button
              className="btn-send"
              onClick={() => sendQuestion(input)}
              disabled={loading || !input.trim()}
              aria-label="Envoyer"
            >
              ↑
            </button>
          </div>
          <p className="input-hint">Entrée pour envoyer · Maj+Entrée pour une nouvelle ligne</p>
        </div>
      </main>
    </div>
  )
}

/* ===== Composants ===== */

function EmptyState({ onSelect }) {
  return (
    <div className="empty-state">
      <div className="empty-logo">⚖️</div>
      <h2>Assistant Juridique BAM</h2>
      <p>
        Posez vos questions sur les textes législatifs et réglementaires
        de Bank Al-Maghrib. Chaque réponse est sourcée et vérifiable.
      </p>
      <div className="quick-examples">
        {EXAMPLES.slice(0, 3).map(q => (
          <button key={q} className="quick-btn" onClick={() => onSelect(q)}>
            {q.length > 55 ? q.slice(0, 55) + '…' : q}
          </button>
        ))}
      </div>
    </div>
  )
}

function UserMessage({ content }) {
  return (
    <div className="message user" role="article" aria-label="Votre question">
      <div className="avatar user" aria-hidden="true">Vous</div>
      <div className="bubble user">{content}</div>
    </div>
  )
}

function AssistantMessage({ data }) {
  const { answer, answer_type, citations, warnings, search_method, question } = data
  const [showSources, setShowSources] = useState(false)

  const banner = getBanner(answer_type)

  return (
    <div className="message" role="article" aria-label="Réponse de l'assistant">
      <div className="avatar assistant" aria-hidden="true">⚖️</div>
      <div className="bubble assistant">
        {banner && (
          <div className={`answer-banner ${banner.cls}`} role="alert">
            {banner.icon} {banner.text}
          </div>
        )}

        <div className="answer-text">{answer}</div>

        {citations && citations.length > 0 && (
          <>
            <button
              className="sources-toggle"
              onClick={() => setShowSources(s => !s)}
              aria-expanded={showSources}
            >
              📄 {showSources ? 'Masquer' : 'Voir'} les sources
              <span className="count">{citations.length}</span>
              {search_method && <span style={{fontSize:'0.72rem',marginLeft:'auto',opacity:0.7}}>{search_method}</span>}
            </button>

            {showSources && (
              <div className="sources-panel">
                {citations.map((c, i) => (
                  <SourceCard key={c.chunk_id} cit={c} index={i + 1} highlight={question} />
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function SourceCard({ cit, index, highlight }) {
  const { citation: ref, excerpt, score } = cit
  const quality = score >= 0.55 ? {cls:'quality-high', label:'● Pertinence élevée'}
                : score >= 0.35 ? {cls:'quality-mid',  label:'● Pertinence moyenne'}
                :                 {cls:'quality-low',  label:'● Pertinence faible'}

  const docLabel = [ref.title, ref.type && ref.number ? `${ref.type} n° ${ref.number}` : ref.type].filter(Boolean).join(' · ')

  return (
    <div className="source-card" role="article" aria-label={`Source ${index}`}>
      <div className="source-header">
        <span className="source-num">[{index}]</span>
        {ref.article && <span className="source-article">{ref.article}</span>}
        <span className="source-doc">
          {ref.url
            ? <a href={ref.url} target="_blank" rel="noopener noreferrer" title="Ouvrir la source">{docLabel || 'Document BAM'}</a>
            : (docLabel || 'Document BAM')}
        </span>
        {ref.page && <span className="source-page">· p.{ref.page}</span>}
      </div>
      {excerpt && (
        <div className="source-excerpt"
          dangerouslySetInnerHTML={{ __html: `« ${hl(excerpt, highlight)} »` }} />
      )}
      <div className={`quality-badge ${quality.cls}`}>{quality.label}</div>
    </div>
  )
}

/* ===== Helpers ===== */

function getBanner(type) {
  switch (type) {
    case 'degraded': return { cls: 'banner-warning', icon: '⚠️', text: 'Service de génération temporairement indisponible — passages bruts affichés' }
    case 'error': return { cls: 'banner-error', icon: '✗', text: 'Une erreur est survenue' }
    case 'out_of_scope': return { cls: 'banner-oos', icon: 'ℹ️', text: 'Question hors périmètre' }
    case 'insufficient_sources': return { cls: 'banner-warning', icon: '🔍', text: 'Aucun passage suffisant trouvé dans les documents indexés' }
    default: return null
  }
}

function hl(text, query) {
  const safe = esc(text)
  if (!query) return safe
  const words = query.toLowerCase().split(/\s+/).filter(w => w.length > 2)
  if (!words.length) return safe
  const re = new RegExp(`(${words.map(escRe).join('|')})`, 'gi')
  return safe.replace(re, '<mark>$1</mark>')
}
function esc(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;') }
function escRe(s) { return s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&') }
