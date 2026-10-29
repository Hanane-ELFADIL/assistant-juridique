/** Couche API — toutes les appels backend centralisés. */

const BASE = ''

function authHeaders(token) {
  return token ? { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
               : { 'Content-Type': 'application/json' }
}

async function req(method, path, body, token) {
  const r = await fetch(BASE + path, {
    method,
    headers: authHeaders(token),
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!r.ok) {
    const e = await r.json().catch(() => ({}))
    throw new Error(e.detail || `Erreur ${r.status}`)
  }
  return r.json()
}

export const api = {
  // Auth
  register: (data) => req('POST', '/api/auth/register', data),
  login: (data) => req('POST', '/api/auth/login', data),
  me: (token) => req('GET', '/api/auth/me', null, token),

  // Chat
  chat: (question, token, n_results = 8) =>
    req('POST', '/api/chat', { question, n_results }, token),

  // Health
  health: () => fetch('/health').then(r => r.json()).catch(() => ({ status: 'error' })),

  // Conversations
  getConversations: (token) => req('GET', '/api/user/conversations', null, token),
  getConversation: (id, token) => req('GET', `/api/user/conversations/${id}`, null, token),
  createConversation: (token) => req('POST', '/api/user/conversations', {}, token),
  deleteConversation: (id, token) => req('DELETE', `/api/user/conversations/${id}`, null, token),
  saveMessage: (data, token) => req('POST', '/api/user/messages', data, token),

  // Favorites
  getFavorites: (token) => req('GET', '/api/user/favorites', null, token),
  addFavorite: (data, token) => req('POST', '/api/user/favorites', data, token),
  removeFavorite: (id, token) => req('DELETE', `/api/user/favorites/${id}`, null, token),
}
