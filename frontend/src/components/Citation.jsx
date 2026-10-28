/**
 * Citation vérifiable avec extrait source — affiche les vrais numéros d'article.
 */
export default function Citation({ citation, index, highlight = '' }) {
  const { chunk_id, citation: ref, excerpt, score, rank } = citation

  // Référence lisible — JAMAIS le chunk_id
  const docRef = []
  if (ref.title) docRef.push(ref.title)
  if (ref.type && ref.number) docRef.push(`${ref.type} n° ${ref.number}`)
  else if (ref.type) docRef.push(ref.type)
  if (ref.date) docRef.push(ref.date)

  const articleRef = ref.article || ''  // ex: "Article 36"
  const chapterRef = ref.chapter ? ref.chapter.split('\n')[0].trim() : ''

  // Qualité lisible au lieu du % brut
  const quality = score >= 0.6 ? { label: 'Élevée', color: '#28a745' }
                : score >= 0.4 ? { label: 'Moyenne', color: '#fd7e14' }
                : { label: 'Faible', color: '#6c757d' }

  // Surlignage des mots de la question
  const highlighted = highlight
    ? highlightText(excerpt || '', highlight)
    : (excerpt || '')

  return (
    <div className="citation-card" id={`cit-${index}`} role="article"
         aria-label={`Source ${index}`}>

      {/* En-tête : numéro de la citation + document */}
      <div className="citation-header">
        <span className="citation-num">[{index}]</span>
        <div className="citation-doc">
          {ref.url ? (
            <a href={ref.url} target="_blank" rel="noopener noreferrer"
               className="citation-link" title="Ouvrir la source officielle">
              {docRef.join(' · ') || 'Document BAM'}
            </a>
          ) : (
            <span className="citation-doc-name">{docRef.join(' · ') || 'Document BAM'}</span>
          )}
        </div>
      </div>

      {/* Localisation exacte */}
      <div className="citation-location">
        {articleRef && <span className="citation-article">{articleRef}</span>}
        {chapterRef && <span className="citation-chapter">{chapterRef}</span>}
        {ref.page && <span className="citation-page">page {ref.page}</span>}
      </div>

      {/* Extrait */}
      {excerpt && (
        <blockquote className="citation-excerpt"
          dangerouslySetInnerHTML={{ __html: `« ${highlighted} »` }} />
      )}

      {/* Pertinence qualitative */}
      <div className="citation-meta">
        <span className="citation-quality" style={{ color: quality.color }}>
          ● Pertinence {quality.label}
        </span>
      </div>
    </div>
  )
}

function highlightText(text, query) {
  if (!query) return escHtml(text)
  const words = query.toLowerCase().split(/\s+/).filter(w => w.length > 2)
  if (!words.length) return escHtml(text)
  const re = new RegExp(`(${words.map(escRe).join('|')})`, 'gi')
  return escHtml(text).replace(re, '<mark>$1</mark>')
}

function escHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
}
function escRe(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')
}
