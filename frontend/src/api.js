/** Couche API — appels backend centralisés. */
const BASE = ''

function headers(token) {
  return token
    ? { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
    : { 'Content-Type': 'application/json' }
}

async function req(method, path, body, token) {
  const r = await fetch(BASE + path, {
    method,
    headers: headers(token),
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!r.ok) {
    const e = await r.json().catch(() => ({}))
    throw new Error(e.detail || `Erreur ${r.status}`)
  }
  return r.json()
}

export const api = {
  register:        (d)    => req('POST', '/api/auth/register', d),
  login:           (d)    => req('POST', '/api/auth/login', d),
  me:              (t)    => req('GET',  '/api/auth/me', null, t),
  health:          ()     => fetch('/health').then(r => r.json()).catch(() => ({ status: 'error' })),
  chat:            (q, t) => req('POST', '/api/chat', { question: q, n_results: 8 }, t),
  getConversations:(t)    => req('GET',  '/api/user/conversations', null, t),
  getConversation: (id,t) => req('GET',  `/api/user/conversations/${id}`, null, t),
  deleteConversation:(id,t)=>req('DELETE',`/api/user/conversations/${id}`, null, t),
  saveMessage:     (d, t) => req('POST', '/api/user/messages', d, t),
  getFavorites:    (t)    => req('GET',  '/api/user/favorites', null, t),
  addFavorite:     (d, t) => req('POST', '/api/user/favorites', d, t),
  removeFavorite:  (id,t) => req('DELETE',`/api/user/favorites/${id}`, null, t),
}
