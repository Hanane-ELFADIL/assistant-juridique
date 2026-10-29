/**
 * Affiche une réponse complète avec avertissements et citations — T801, T802, T804.
 */
import Citation from './Citation'

export default function AnswerCard({ result }) {
  const { answer, answer_type, question, citations, warnings, search_method, relevant_used } = result

  const cardClass = [
    'answer-card',
    answer_type === 'insufficient_sources' ? 'insufficient' : '',
    answer_type === 'error' ? 'error-card' : '',
  ].filter(Boolean).join(' ')

  return (
    <article className={cardClass}>
      {/* Question posée */}
      <p className="answer-question">
        <strong>Q :</strong> {question}
      </p>

      {/* Réponse — T802 */}
      <div className="answer-text" role="main">
        {answer}
      </div>

      {/* Avertissements — T804 */}
      {warnings && warnings.length > 0 && (
        <div className="warnings" role="alert" aria-label="Avertissements">
          {warnings.map((w, i) => (
            <div key={i} className="warning-item">{w}</div>
          ))}
        </div>
      )}

      {/* Note sur la vérification */}
      {answer_type === 'sourced' && (
        <p className="verification-notice">
          ⚠️ Vérifiez toujours le statut juridique des textes sur{' '}
          <a href="https://www.bkam.ma/Supervision-bancaire/Recueil-des-textes-legislatifs-et-reglementaires"
             target="_blank" rel="noopener noreferrer">bkam.ma</a>.
        </p>
      )}

      {/* Citations vérifiables — T802, T803 */}
      {citations && citations.length > 0 && (
        <section className="sources-section" aria-label="Sources">
          <h3>Sources ({citations.length} passage{citations.length > 1 ? 's' : ''})</h3>
          <div className="citations-list">
            {citations.map((cit) => (
              <Citation key={cit.chunk_id} citation={cit} />
            ))}
          </div>
          {search_method && (
            <p className="citation-score" style={{ marginTop: '0.5rem' }}>
              Méthode : {search_method} · {relevant_used} passage{relevant_used > 1 ? 's' : ''} utilisé{relevant_used > 1 ? 's' : ''}
            </p>
          )}
        </section>
      )}
    </article>
  )
}
