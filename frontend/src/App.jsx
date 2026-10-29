import { useState, useRef, useEffect, useCallback } from 'react'
import { marked } from 'marked'

// Configure marked pour un rendu sécurisé
marked.setOptions({ breaks: true, gfm: true })

const EXAMPLES = [
  { label: "Capital minimum", q: "Quelles sont les conditions de capital minimum pour les banques ?" },
  { label: "Agrément bancaire", q: "Quelles sont les conditions d'obtention d'un agrément bancaire ?" },
  { label: "Missions BAM", q: "Quelles sont les missions de Bank Al-Maghrib ?" },
  { label: "Ratios prudentiels", q: "Quels sont les ratios prudentiels applicables aux établissements de crédit ?" },
  { label: "Protection déposants", q: "Que dit la loi bancaire sur la protection des déposants ?" },
  { label: "Sanctions", q: "Quelles sont les sanctions en cas de non-respect de la réglementation bancaire ?" },
]

export default function App() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState('checking')
  const bottomRef = useRef(null)
  const taRef = useRef(null)

  useEffect(() => {
    fetch('/health').then(r => r.json())
      .then(d => setStatus(d.status === 'ok' ? 'ok' : 'degraded'))
      .catch(() => setStatus('error'))
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const autoResize = (el) => {
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 160) + 'px'
  }

  const send = useCallback(async (question) => {
    const q = question.trim()
    if (!q || loading) return
    setInput('')
    if (taRef.current) taRef.current.style.height = 'auto'
    setMessages(p => [...p, { role: 'user', content: q }])
    setLoading(true)
    try {
      const r = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q }),
      })
      if (!r.ok) {
        const e = await r.json().catch(() => ({}))
        throw new Error(e.detail || `Erreur ${r.status}`)
      }
      const data = await r.json()
      setMessages(p => [...p, { role: 'assistant', ...data }])
    } catch (e) {
      setMessages(p => [...p, {
        role: 'assistant', answer_type: 'error',
        answer: e.message || 'Erreur de connexion.',
        citations: [], sources: [], warnings: [], question: q,
      }])
    } finally {
      setLoading(false)
    }
  }, [loading])

  const statusMap = { ok: ['ok', 'En ligne'], degraded: ['', 'Dégradé'], checking: ['checking', 'Connexion…'], error: ['error', 'Hors ligne'] }
  const [dotCls, statusTxt] = statusMap[status] || ['', status]

  return (
    <div className="app">

      {/* ── SIDEBAR ── */}
      <aside className="sidebar">
        <div className="sidebar-inner">
          <div className="sidebar-logo">
            <div className="logo-badge">⚖️</div>
            <div className="logo-text">
              <h2>Assistant Juridique</h2>
              <p>Bank Al-Maghrib</p>
            </div>
          </div>

          <button className="btn-new" onClick={() => setMessages([])} aria-label="Nouvelle conversation">
            ✏️ Nouvelle conversation
          </button>

          <div className="sidebar-section">Questions fréquentes</div>
          <nav className="example-list">
            {EXAMPLES.map(({ label, q }) => (
              <button key={q} className="example-btn" onClick={() => send(q)}>
                <strong style={{display:'block',fontSize:'.72rem',marginBottom:'2px',color:'rgba(255,255,255,.5)'}}>{label}</strong>
                {q}
              </button>
            ))}
          </nav>

          <div className="sidebar-divider" />
          <div className="sidebar-footer">
            <p>Outil de recherche documentaire — pas un avis juridique.<br />
            <a href="https://www.bkam.ma" target="_blank" rel="noopener noreferrer">bkam.ma ↗</a></p>
          </div>
        </div>
      </aside>

      {/* ── CHAT AREA ── */}
      <main className="chat-area">
        <header className="chat-header">
          <div className="chat-header-title">
            <h1>Recherche dans les textes législatifs</h1>
            <span className="header-badge">BAM</span>
          </div>
          <div className="status-pill">
            <span className={`dot ${dotCls}`} />
            {statusTxt}
          </div>
        </header>

        <div className="messages" role="log" aria-live="polite">
          {messages.length === 0
            ? <EmptyState onSelect={send} />
            : messages.map((m, i) =>
                m.role === 'user'
                  ? <UserBubble key={i} content={m.content} />
                  : <BotBubble key={i} data={m} />
              )
          }
          {loading && (
            <div className="msg-row">
              <div className="avatar bot" aria-hidden="true">⚖️</div>
              <div className="bubble bot" role="status">
                <div className="typing"><span/><span/><span/></div>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div className="input-area">
          <div className="input-box">
            <label htmlFor="qi" className="sr-only">Question</label>
            <textarea
              id="qi" ref={taRef} className="chat-ta" rows={1}
              value={input} placeholder="Posez votre question juridique…"
              disabled={loading}
              onChange={e => { setInput(e.target.value); autoResize(e.target) }}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input) } }}
            />
            <button className="send-btn" onClick={() => send(input)}
              disabled={loading || !input.trim()} aria-label="Envoyer">
              ↑
            </button>
          </div>
          <p className="input-hint">Entrée pour envoyer · Maj+Entrée pour une nouvelle ligne</p>
        </div>
      </main>
    </div>
  )
}

/* ── Empty state ── */
function EmptyState({ onSelect }) {
  return (
    <div className="empty-state">
      <div className="empty-icon">⚖️</div>
      <h2>Bienvenue</h2>
      <p>Posez vos questions sur les textes législatifs et réglementaires de Bank Al-Maghrib. Chaque réponse est sourcée et vérifiable.</p>
      <div className="quick-grid">
        {EXAMPLES.slice(0, 4).map(({ label, q }) => (
          <button key={q} className="quick-card" onClick={() => onSelect(q)}>
            <strong>{label}</strong>
            {q.length > 60 ? q.slice(0, 60) + '…' : q}
          </button>
        ))}
      </div>
    </div>
  )
}

/* ── User bubble ── */
function UserBubble({ content }) {
  return (
    <div className="msg-row user">
      <div className="avatar user">Vous</div>
      <div className="bubble user">{content}</div>
    </div>
  )
}

/* ── Bot bubble ── */
function BotBubble({ data }) {
  const { answer, answer_type, citations, warnings, search_method, question } = data
  const [open, setOpen] = useState(false)

  const banner = {
    degraded: { cls: 'warn', icon: '⚠️', txt: 'Service LLM temporairement indisponible — passages bruts affichés' },
    error:    { cls: 'err',  icon: '✗',   txt: 'Une erreur est survenue' },
    out_of_scope: { cls: 'info', icon: 'ℹ️', txt: 'Question hors périmètre (textes bancaires BAM uniquement)' },
    insufficient_sources: { cls: 'warn', icon: '🔍', txt: 'Aucun passage suffisant trouvé dans les documents indexés' },
  }[answer_type]

  // Rendu Markdown sécurisé
  const html = marked.parse(answer || '')

  return (
    <div className="msg-row">
      <div className="avatar bot">⚖️</div>
      <div className="bubble bot">
        {banner && (
          <div className={`banner ${banner.cls}`} role="alert">
            {banner.icon}&nbsp; {banner.txt}
          </div>
        )}

        {/* Réponse rendue en Markdown */}
        <div className="md-body" dangerouslySetInnerHTML={{ __html: html }} />

        {/* Bouton sources */}
        {citations?.length > 0 && (
          <>
            <button className="sources-btn" onClick={() => setOpen(o => !o)} aria-expanded={open}>
              📄 {open ? 'Masquer' : 'Voir'} les sources
              <span className="src-count">{citations.length}</span>
              {search_method && <span style={{marginLeft:'auto',opacity:.6,fontSize:'.68rem'}}>{search_method}</span>}
            </button>
            {open && (
              <div className="sources-panel">
                {citations.map((c, i) => <SrcCard key={c.chunk_id} c={c} i={i+1} q={question} />)}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

/* ── Source card ── */
function SrcCard({ c, i, q }) {
  const { citation: ref, excerpt, score } = c
  const [cls, lbl] = score >= .55 ? ['q-high','● Pertinence élevée']
                   : score >= .35 ? ['q-mid', '● Pertinence moyenne']
                   :                ['q-low', '● Pertinence faible']
  const doc = [ref.title, ref.type && ref.number ? `${ref.type} n°${ref.number}` : ref.type].filter(Boolean).join(' · ')

  return (
    <div className="src-card">
      <div className="src-head">
        <span className="src-num">[{i}]</span>
        {ref.article && <span className="src-art">{ref.article}</span>}
        <span className="src-doc">
          {ref.url
            ? <a href={ref.url} target="_blank" rel="noopener noreferrer">{doc || 'Document BAM'}</a>
            : (doc || 'Document BAM')}
        </span>
        {ref.page && <span className="src-page">· p.{ref.page}</span>}
      </div>
      {excerpt && (
        <div className="src-excerpt" dangerouslySetInnerHTML={{ __html: `« ${hl(excerpt, q)} »` }} />
      )}
      <div className={`src-quality ${cls}`}>{lbl}</div>
    </div>
  )
}

function hl(txt, q) {
  const s = esc(txt)
  if (!q) return s
  const words = q.toLowerCase().split(/\s+/).filter(w => w.length > 2)
  if (!words.length) return s
  return s.replace(new RegExp(`(${words.map(r => r.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('|')})`, 'gi'), '<mark>$1</mark>')
}
function esc(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;') }
