/**
 * Affiche l'état des composants du backend — T807 (partiel).
 */
import { useEffect, useState } from 'react'

export default function ApiStatus() {
  const [status, setStatus] = useState(null)

  useEffect(() => {
    fetch('/health')
      .then((r) => r.json())
      .then(setStatus)
      .catch(() => setStatus({ status: 'unreachable' }))
  }, [])

  if (!status) return null

  const ok = status.status === 'ok'
  const degraded = status.status === 'degraded'

  return (
    <div className="api-status" role="status" aria-label="État du service">
      <span
        className={`status-dot ${ok ? 'ok' : degraded ? '' : 'error'}`}
        aria-hidden="true"
      />
      <span>
        API {ok ? 'en ligne' : degraded ? 'dégradée' : 'hors ligne'}
        {status.components && !ok && (
          <span>
            {' '}— {Object.entries(status.components)
              .filter(([, v]) => v !== 'ok')
              .map(([k]) => k)
              .join(', ')} non disponible
          </span>
        )}
      </span>
    </div>
  )
}
