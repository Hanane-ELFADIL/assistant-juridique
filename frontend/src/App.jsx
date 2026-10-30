import { useState, useRef, useEffect, useCallback } from 'react'
import { marked } from 'marked'
import { api } from './api'
import AuthPage from './AuthPage'

marked.setOptions({ breaks: true, gfm: true })

const EX = [
  { label: 'Capital minimum', q: 'Quelles sont les conditions de capital minimum pour les banques ?' },
  { label: 'Agrement bancaire', q: "Conditions d'obtention d'un agrement bancaire ?" },
  { label: 'Missions BAM', q: 'Quelles sont les missions de Bank Al-Maghrib ?' },
  { label: 'Ratios prudentiels', q: 'Quels sont les ratios prudentiels applicables aux etablissements de credit ?' },
]

export default function App() {
  const [token, setToken] = useState(() => localStorage.getItem('bam_token'))
  const [user, setUser] = useState(() => {
    try { return JSON.parse(localStorage.getItem('bam_user')) } catch { return null }
  })
  const auth = (u, t) => { setUser(u); setToken(t) }
  const logout = () => {
    localStorage.removeItem('bam_token')
    localStorage.removeItem('bam_user')
    setUser(null)
    setToken(null)
  }
  if (!token || !user) return <AuthPage onAuth={auth} />
  return <Chat user={user} token={token} onLogout={logout} />
}

function Chat({ user, token, onLogout }) {
  const [view, setView] = useState('chat')
  const [msgs, setMsgs] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState('checking')
  const [cid, setCid] = useState(null)
  const [convs, setConvs] = useState([])
  const [favs, setFavs] = useState([])
  const botRef = useRef(null)
  const taRef = useRef(null)

  useEffect(() => {
    api.health().then(d => setStatus(d.status)).catch(() => setStatus('error'))
  }, [])
  useEffect(() => {
    api.getConversations(token).then(setConvs).catch(() => {})
    api.getFavorites(token).then(setFavs).catch(() => {})
  }, [token])
  useEffect(() => { botRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [msgs, busy])

  function resize(el) {
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 160) + 'px'
  }

  const send = useCallback(async (question) => {
    const q = question.trim()
    if (!q || busy) return
    setInput('')
    if (taRef.current) taRef.current.style.height = 'auto'
    setView('chat')
    setMsgs(p => [...p, { role: 'user', content: q }])
    setBusy(true)
    try {
      const data = await api.chat(q, token)
      setMsgs(p => [...p, { role: 'bot', ...data }])
      const saved = await api.saveMessage({
        conversation_id: cid, question: q,
        answer: data.answer, answer_type: data.answer_type,
        citations: data.citations || [], sources: data.sources || [],
      }, token).catch(() => null)
      if (saved) {
        setCid(saved.conversation_id)
        setConvs(p => {
          const ex = p.find(c => c.id === saved.conversation_id)
          if (ex) return p.map(c => c.id === saved.conversation_id ? { ...c, title: saved.title } : c)
          return [{ id: saved.conversation_id, title: saved.title, updated_at: new Date().toISOString() }, ...p]
        })
      }
    } catch (e) {
      setMsgs(p => [...p, { role: 'bot', answer_type: 'error', answer: e.message, citations: [], sources: [], warnings: [], question: q }])
    } finally { setBusy(false) }
  }, [busy, cid, token])

  async function addFav(data) {
    const f = await api.addFavorite({
      question: data.question, answer: data.answer,
      answer_type: data.answer_type, citations: data.citations || [],
    }, token).catch(() => null)
    if (f) setFavs(p => [f, ...p])
  }
  function rmFav(id) { api.removeFavorite(id, token); setFavs(p => p.filter(f => f.id !== id)) }
  function delConv(id, e) {
    e.stopPropagation()
    api.deleteConversation(id, token)
    setConvs(p => p.filter(c => c.id !== id))
    if (cid === id) { setMsgs([]); setCid(null) }
  }
  async function loadConv(id) {
    const c = await api.getConversation(id, token).catch(() => null)
    if (!c) return
    setMsgs(c.messages.map(m => ({
      role: m.role === 'user' ? 'user' : 'bot',
      content: m.content, answer: m.content,
      answer_type: m.answer_type || 'sourced',
      citations: m.citations || [], sources: m.sources || [],
      warnings: [], question: m.content,
    })))
    setCid(id); setView('chat')
  }

  const smap = { ok: ['ok', 'En ligne'], degraded: ['', 'Degrade'], checking: ['checking', '...'], error: ['error', 'Hors ligne'] }
  const [dc, st] = smap[status] || ['', '']

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="sb-inner">
          <div className="sb-head">
            <div className="sb-badge">⚖️</div>
            <div><div className="sb-title">Assistant Juridique</div><div className="sb-sub">Bank Al-Maghrib</div></div>
          </div>
          <div className="sb-user">
            <div className="sb-avatar" style={{ background: user.avatar_color || '#c0392b' }}>
              {(user.username || 'U')[0].toUpperCase()}
            </div>
            <div>
              <div className="sb-uname">{user.full_name || user.username}</div>
              <div className="sb-uemail">{user.email}</div>
            </div>
            <button className="sb-logout" onClick={onLogout}>↩</button>
          </div>
          <button className="btn-new-chat" onClick={() => { setMsgs([]); setCid(null); setView('chat') }}>
            ✏️ Nouvelle conversation
          </button>
          <div className="sb-tabs">
            <button className={'sb-tab' + (view === 'chat' ? ' active' : '')} onClick={() => setView('chat')}>💬 Chats</button>
            <button className={'sb-tab' + (view === 'fav' ? ' active' : '')} onClick={() => setView('fav')}>⭐ Favoris</button>
          </div>
          {view !== 'fav' ? (
            <>
              <div className="sb-section">Historique</div>
              <nav className="sb-list">
                {convs.length === 0
                  ? <div style={{ color: 'rgba(255,255,255,.3)', fontSize: '.75rem', padding: '.5rem' }}>Aucune conversation</div>
                  : convs.map(c => (
                    <button key={c.id} className={'sb-item' + (cid === c.id ? ' active' : '')} onClick={() => loadConv(c.id)}>
                      <span className="sb-item-icon">💬</span>
                      <span style={{ flex: 1 }}>{c.title}</span>
                      <button className="sb-item-del" onClick={e => delConv(c.id, e)}>✕</button>
                    </button>
                  ))}
              </nav>
            </>
          ) : (
            <>
              <div className="sb-section">Favoris ({favs.length})</div>
              <nav className="sb-list">
                {favs.length === 0
                  ? <div style={{ color: 'rgba(255,255,255,.3)', fontSize: '.75rem', padding: '.5rem' }}>Aucun favori</div>
                  : favs.map(f => (
                    <button key={f.id} className="sb-item"
                      onClick={() => {
                        setMsgs([{ role: 'user', content: f.question }, { role: 'bot', ...f, citations: f.citations || [], warnings: [] }])
                        setView('chat')
                      }}>
                      <span className="sb-item-icon">⭐</span>
                      <span style={{ flex: 1 }}>{f.question.slice(0, 48)}{f.question.length > 48 ? '...' : ''}</span>
                      <button className="sb-item-del" onClick={e => { e.stopPropagation(); rmFav(f.id) }}>✕</button>
                    </button>
                  ))}
              </nav>
            </>
          )}
          <div className="sb-footer">
            <p>Outil de recherche — pas un avis juridique.<br />
              <a href="https://www.bkam.ma" target="_blank" rel="noopener noreferrer">bkam.ma</a>
            </p>
          </div>
        </div>
      </aside>

      <div className="main-area">
        <header className="chat-header">
          <div className="ch-left">
            <h1>{view === 'fav' ? 'Mes favoris' : 'Recherche juridique'}</h1>
            <span className="ch-badge">BAM</span>
          </div>
          <div className="status-pill"><span className={'dot ' + dc} />{st}</div>
        </header>

        {view === 'fav'
          ? <FavPage favs={favs} onRemove={rmFav} onLoad={q => { send(q); setView('chat') }} />
          : (
            <>
              <div className="messages">
                {msgs.length === 0
                  ? <Empty onSelect={send} />
                  : msgs.map((m, i) => m.role === 'user' ? <URow key={i} content={m.content} /> : <BRow key={i} data={m} onFav={addFav} />)
                }
                {busy && <div className="row"><div className="av bot">⚖️</div><div className="bubble bot"><div className="typing"><span /><span /><span /></div></div></div>}
                <div ref={botRef} />
              </div>
              <div className="input-area">
                <div className="input-box">
                  <textarea ref={taRef} className="chat-ta" rows={1} value={input} disabled={busy}
                    placeholder="Posez votre question sur les textes de Bank Al-Maghrib..."
                    onChange={e => { setInput(e.target.value); resize(e.target) }}
                    onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input) } }}
                  />
                  <button className="send-btn" onClick={() => send(input)} disabled={busy || !input.trim()}>↑</button>
                </div>
                <p className="hint">Entree = envoyer · Maj+Entree = nouvelle ligne</p>
              </div>
            </>
          )
        }
      </div>
    </div>
  )
}

function Empty({ onSelect }) {
  return (
    <div className="empty">
      <div className="empty-icon">⚖️</div>
      <h2>Bienvenue</h2>
      <p>Posez vos questions sur les textes legislatifs de Bank Al-Maghrib. Chaque reponse est sourcee.</p>
      <div className="qgrid">
        {EX.map(({ label, q }) => (
          <button key={q} className="qcard" onClick={() => onSelect(q)}>
            <strong>{label}</strong>{q}
          </button>
        ))}
      </div>
    </div>
  )
}

function URow({ content }) {
  return <div className="row user"><div className="av user">Vous</div><div className="bubble user">{content}</div></div>
}

function BRow({ data, onFav }) {
  const { answer, answer_type, citations, search_method, question } = data
  const [open, setOpen] = useState(false)
  const [faved, setFaved] = useState(false)
  const BANNERS = {
    degraded: { cls: 'warn', icon: '⚠️', txt: 'LLM indisponible - passages bruts' },
    error: { cls: 'err', icon: '✗', txt: 'Une erreur est survenue' },
    out_of_scope: { cls: 'info', icon: 'ℹ️', txt: 'Hors perimetre BAM' },
    insufficient_sources: { cls: 'warn', icon: '🔍', txt: 'Aucun passage suffisant trouve' },
  }
  const banner = BANNERS[answer_type]
  const html = marked.parse(answer || '')
  function handleFav() { onFav(data); setFaved(true); setTimeout(() => setFaved(false), 2500) }
  return (
    <div className="row">
      <div className="av bot">⚖️</div>
      <div className="bubble bot">
        {banner && <div className={'banner ' + banner.cls}>{banner.icon} {banner.txt}</div>}
        <div className="md" dangerouslySetInnerHTML={{ __html: html }} />
        <div className="bubble-actions">
          {citations && citations.length > 0 && (
            <button className="act-btn" onClick={() => setOpen(o => !o)}>
              📄 {open ? 'Masquer' : 'Sources'} <span className="src-count">{citations.length}</span>
            </button>
          )}
          {answer_type === 'sourced' && (
            <button className={'act-btn' + (faved ? ' fav' : '')} onClick={handleFav}>
              {faved ? '⭐ Sauvegarde' : '☆ Favori'}
            </button>
          )}
          {search_method && <span style={{ fontSize: '.7rem', color: 'var(--muted)', marginLeft: 'auto' }}>{search_method}</span>}
        </div>
        {open && citations && citations.length > 0 && (
          <div className="src-panel">{citations.map((c, i) => <SrcCard key={c.chunk_id} c={c} i={i + 1} q={question} />)}</div>
        )}
      </div>
    </div>
  )
}

function SrcCard({ c, i, q }) {
  const { citation: ref, excerpt, score } = c
  const [qcls, qlbl] = score >= 0.55 ? ['q-hi', '● Elevee'] : score >= 0.35 ? ['q-mid', '● Moyenne'] : ['q-lo', '● Faible']
  const doc = [ref.title, ref.type && ref.number ? ref.type + ' n\u00b0' + ref.number : ref.type].filter(Boolean).join(' · ')
  return (
    <div className="src-card">
      <div className="src-head">
        <span className="src-num">[{i}]</span>
        {ref.article && <span className="src-art">{ref.article}</span>}
        <span className="src-doc">{ref.url ? <a href={ref.url} target="_blank" rel="noopener noreferrer">{doc || 'BAM'}</a> : doc || 'BAM'}</span>
        {ref.page && <span className="src-page">p.{ref.page}</span>}
      </div>
      {excerpt && <div className="src-exc" dangerouslySetInnerHTML={{ __html: hl(excerpt, q) }} />}
      <div className={'src-q ' + qcls}>{qlbl}</div>
    </div>
  )
}

function FavPage({ favs, onRemove, onLoad }) {
  if (!favs.length) return <div className="fav-page"><div className="empty-fav">⭐ Aucun favori. Cliquez "☆ Favori" sous une reponse.</div></div>
  return (
    <div className="fav-page">
      <h2>⭐ Mes favoris ({favs.length})</h2>
      <div className="fav-grid">
        {favs.map(f => (
          <div key={f.id} className="fav-card">
            <div className="fav-q">{f.question}</div>
            <div className="fav-a">{f.answer ? f.answer.slice(0, 200) + (f.answer.length > 200 ? '...' : '') : ''}</div>
            <div className="fav-meta">
              <span className="fav-date">{f.created_at ? new Date(f.created_at).toLocaleDateString('fr-FR') : ''}</span>
              <button className="fav-load" onClick={() => onLoad(f.question)}>↗ Reposer</button>
              <button className="fav-del" onClick={() => onRemove(f.id)}>🗑</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
function hl(txt, q) {
  const s = esc(txt); if (!q) return s
  const words = q.toLowerCase().split(/\s+/).filter(w => w.length > 2)
  if (!words.length) return s
  return s.replace(new RegExp('(' + words.map(r => r.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|') + ')', 'gi'), '<mark>$1</mark>')
}
