/**
 * Affiche une citation vérifiable avec son extrait source — T802, T803.
 * N'affiche que les champs réellement disponibles.
 */
export default function Citation({ citation }) {
  const { chunk_id, citation: ref, excerpt, score, rank } = citation

  // Construction de la référence lisible
  const parts = []
  if (ref.title) parts.push(ref.title)
  if (ref.type && ref.number) parts.push(`${ref.type} n° ${ref.number}`)
  else if (ref.type) parts.push(ref.type)
  if (ref.article) parts.push(ref.article)
  if (ref.date) parts.push(ref.date)

  return (
    <div className="citation-card" role="article" aria-label={`Source ${rank}`}>
      <div className="citation-ref">
        <span>📄 </span>
        {ref.url ? (
          <a href={ref.url} target="_blank" rel="noopener noreferrer" title="Ouvrir la source officielle">
            {parts.join(' — ') || `Source ${rank}`}
          </a>
        ) : (
          <span>{parts.join(' — ') || `Source ${rank}`}</span>
        )}
        {ref.page && <span style={{ color: '#6c757d', fontWeight: 400 }}> · p. {ref.page}</span>}
      </div>

      {excerpt && (
        <blockquote className="citation-excerpt">
          « {excerpt} »
        </blockquote>
      )}

      <div className="citation-score">
        Pertinence : {Math.round(score * 100)}% · Rang {rank}
      </div>
    </div>
  )
}
