/**
 * Réponse complète : synthèse en premier, sources en dessous.
 * Citations numérotées [1][2] cliquables dans la réponse.
 */
import { useState } from 'react'
import Citation from './Citation'

export default function AnswerCard({ result }) {
  const { answer, answer_type, question, citations, warnings, search_method, relevant_used } = result
  const [expanded, setExpanded] = useState({})

  const cardClass = [
    'answer-card',
    answer_type === 'insufficient_sources' ? 'insufficient' : '',
    answer_type === 'error' ? 'error-card' : '',
    answer_type === 'degraded' ? 'degraded-card' : '',
    answer_type === 'out_of_scope' ? 'out-of-scope-card' : '',
  ].filter(Boolean).join(' ')

  // Rend les [1] [2] cliquables dans le texte de réponse
  const answerHtml = answer
    .replace(/\n/g, '<br/>')
    .replace(/\[(\d+)\]/g, (_, n) =>
      `<a href="#cit-${n}" class="cit-link" onclick="document.getElementById('cit-${n}')?.scrollIntoView({behavior:'smooth'});return false;">[${n}]</a>`
    )

  const showSources = citations && citations.length > 0 &&
    answer_type !== 'error' && answer_type !== 'out_of_scope'

  return (
    <article className={cardClass}>
      {/* Question posée */}
      <p className="answer-question"><strong>Q :</strong> {question}</p>

      {/* Bandeaux d'état */}
      {answer_type === 'degraded' && (
        <div className="answer-banner banner-warning" role="alert">
          ⚠️ Service de génération indisponible — passages bruts affichés
        </div>
      )}
      {answer_type === 'out_of_scope' && (
        <div className="answer-banner banner-info" role="note">
          ℹ️ Question hors périmètre
        </div>
      )}
      {answer_type === 'insufficient_sources' && (
        <div className="answer-banner banner-warning" role="alert">
          ℹ️ Aucun passage suffisant trouvé dans les documents indexés
        </div>
      )}

      {/* Réponse — EN PREMIER */}
      <div className="answer-text" role="main"
           dangerouslySetInnerHTML={{ __html: answerHtml }} />

      {/* Avertissements légaux — discrets */}
      {warnings && warnings.length > 0 && (
        <details className="warnings-details">
          <summary>Avertissements ({warnings.length})</summary>
          {warnings.map((w, i) => (
            <div key={i} className="warning-item">{w}</div>
          ))}
        </details>
      )}

      {/* Sources — EN DESSOUS */}
      {showSources && (
        <section className="sources-section" aria-label="Sources">
          <h3>
            Sources ({citations.length} passage{citations.length > 1 ? 's' : ''})
            {search_method && <span className="search-method"> · {search_method}</span>}
          </h3>
          <div className="citations-list">
            {citations.map((cit, i) => (
              <Citation
                key={cit.chunk_id}
                citation={cit}
                index={i + 1}
                highlight={question}
              />
            ))}
          </div>
          <p className="verification-notice">
            ⚠️ Vérifiez le statut juridique des textes sur{' '}
            <a href="https://www.bkam.ma/Supervision-bancaire/Recueil-des-textes-legislatifs-et-reglementaires"
               target="_blank" rel="noopener noreferrer">bkam.ma</a>.
          </p>
        </section>
      )}
    </article>
  )
}
