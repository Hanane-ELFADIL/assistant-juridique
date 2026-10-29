import { useState } from 'react'
import { api } from './api'

export default function AuthPage({ onAuth }) {
  const [tab, setTab] = useState('login')
  const [form, setForm] = useState({ email: '', password: '', username: '', full_name: '' })
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(false)

  const set = (k, v) => setForm(p => ({ ...p, [k]: v }))

  async function submit(e) {
    e.preventDefault()
    setErr(''); setLoading(true)
    try {
      const data = tab === 'login'
        ? await api.login({ email: form.email, password: form.password })
        : await api.register(form)
      localStorage.setItem('bam_token', data.access_token)
      localStorage.setItem('bam_user', JSON.stringify(data.user))
      onAuth(data.user, data.access_token)
    } catch (e) { setErr(e.message) }
    finally { setLoading(false) }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-logo">
          <div className="badge">⚖️</div>
          <h1>Assistant Juridique</h1>
          <p>Bank Al-Maghrib — Textes officiels</p>
        </div>

        <div className="auth-tabs">
          <button className={`auth-tab ${tab === 'login' ? 'active' : ''}`} onClick={() => setTab('login')}>
            Connexion
          </button>
          <button className={`auth-tab ${tab === 'register' ? 'active' : ''}`} onClick={() => setTab('register')}>
            Inscription
          </button>
        </div>

        <form onSubmit={submit}>
          {tab === 'register' && (
            <>
              <div className="field">
                <label>Nom complet</label>
                <input placeholder="Votre nom" value={form.full_name}
                  onChange={e => set('full_name', e.target.value)} />
              </div>
              <div className="field">
                <label>Nom d'utilisateur</label>
                <input placeholder="johndoe" value={form.username}
                  onChange={e => set('username', e.target.value)} required />
              </div>
            </>
          )}

          <div className="field">
            <label>Email</label>
            <input type="email" placeholder="vous@exemple.com" value={form.email}
              onChange={e => set('email', e.target.value)} required />
          </div>

          <div className="field">
            <label>Mot de passe</label>
            <input type="password" placeholder="••••••••" value={form.password}
              onChange={e => set('password', e.target.value)} required />
            {err && <div className="err">{err}</div>}
          </div>

          <button type="submit" className="btn-auth" disabled={loading}>
            {loading ? '…' : tab === 'login' ? 'Se connecter' : "S'inscrire"}
          </button>
        </form>

        <div className="auth-sep">ou</div>
        <p style={{ textAlign: 'center', fontSize: '.78rem', color: 'var(--muted)' }}>
          {tab === 'login' ? 'Pas encore de compte ? ' : 'Déjà inscrit ? '}
          <button style={{ background: 'none', border: 'none', color: 'var(--red)', fontWeight: 600, fontSize: '.78rem' }}
            onClick={() => setTab(tab === 'login' ? 'register' : 'login')}>
            {tab === 'login' ? "S'inscrire" : 'Se connecter'}
          </button>
        </p>
      </div>
    </div>
  )
}
