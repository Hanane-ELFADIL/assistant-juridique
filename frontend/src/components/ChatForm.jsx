/**
 * Formulaire de saisie de question — T801, T805.
 */
import { useState } from 'react'

const MAX_LENGTH = 500

export default function ChatForm({ onSubmit, loading }) {
  const [question, setQuestion] = useState('')

  function handleSubmit(e) {
    e.preventDefault()
    const q = question.trim()
    if (q.length < 3 || q.length > MAX_LENGTH) return
    onSubmit(q)
  }

  const remaining = MAX_LENGTH - question.length
  const tooShort = question.trim().length > 0 && question.trim().length < 3

  return (
    <form className="chat-form" onSubmit={handleSubmit} aria-label="Poser une question">
      <label htmlFor="question-input" className="sr-only">
        Question sur les textes Bank Al-Maghrib
      </label>
      <input
        id="question-input"
        className="chat-input"
        type="text"
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        placeholder="Ex : Quelles sont les conditions de capital minimum pour les banques ?"
        maxLength={MAX_LENGTH}
        disabled={loading}
        aria-label="Votre question"
        aria-describedby="char-count"
        autoComplete="off"
        autoFocus
      />
      <button
        type="submit"
        className="btn-send"
        disabled={loading || tooShort || question.trim().length === 0}
        aria-label="Envoyer la question"
      >
        {loading ? '…' : 'Envoyer'}
      </button>
      {/* Compteur de caractères — accessibilité */}
      <span id="char-count" className="sr-only" aria-live="polite">
        {remaining} caractères restants
      </span>
    </form>
  )
}
