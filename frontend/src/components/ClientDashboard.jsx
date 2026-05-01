import { useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'

/**
 * ClientDashboard — card grid of approved raters for client selection.
 * Props: { engine, raters, onRefresh }
 */
export default function ClientDashboard({ engine, raters = [], onRefresh }) {
  // Auto-refresh on window focus
  useEffect(() => {
    const handler = () => onRefresh()
    window.addEventListener('focus', handler)
    return () => window.removeEventListener('focus', handler)
  }, [onRefresh])

  const liveRaters = raters.filter((r) => r.source === 'raters')

  return (
    <div style={{ padding: 20, display: 'grid', gap: 20 }}>
      {/* Hero */}
      <section className="client-hero">
        <div>
          <h2>Quote Scenario Studio</h2>
          <p>Select an approved rater to calculate premiums. New raters added by admin appear automatically.</p>
        </div>
        <div className="hero-meta-cards">
          <article>
            <span>Engine</span>
            <strong>{engine === 'schema' ? 'Schema (AI)' : 'Excel (Native)'}</strong>
          </article>
          <article>
            <span>Available Raters</span>
            <strong>{liveRaters.length}</strong>
          </article>
          <article>
            <span>Status</span>
            <strong style={{ color: '#0d9c74' }}>● Live</strong>
          </article>
        </div>
      </section>

      {/* Rater cards */}
      {liveRaters.length === 0 ? (
        <div className="empty-card">
          <h3>No raters available yet</h3>
          <p>Ask your admin to upload and approve rater workbooks.</p>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 14 }}>
          {liveRaters.map((r) => (
            <Link
              key={r.id}
              to={`/client/rater/${r.id}`}
              style={{ textDecoration: 'none' }}
            >
              <article className="stat-card" style={{
                cursor: 'pointer', display: 'flex', flexDirection: 'column',
                gap: 8, transition: 'transform 160ms ease, box-shadow 160ms ease',
              }}
                onMouseEnter={(e) => { e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.boxShadow = '0 14px 28px rgba(15,23,42,0.12)' }}
                onMouseLeave={(e) => { e.currentTarget.style.transform = ''; e.currentTarget.style.boxShadow = '' }}
              >
                <h4 style={{ margin: 0, fontSize: '1rem', color: '#0f172a', fontFamily: 'Space Grotesk, sans-serif' }}>
                  {r.name}
                </h4>
                {r.filename && (
                  <p style={{ margin: 0, fontSize: '0.8rem', color: '#64748b' }}>📄 {r.filename}</p>
                )}
                {r.uploadedAt && (
                  <p style={{ margin: 0, fontSize: '0.78rem', color: '#94a3b8' }}>
                    Added {new Date(r.uploadedAt).toLocaleDateString()}
                  </p>
                )}
                <div style={{ marginTop: 'auto', color: 'var(--brand)', fontWeight: 700, fontSize: '0.85rem' }}>
                  Open → Calculate
                </div>
              </article>
            </Link>
          ))}
        </div>
      )}

      <button onClick={onRefresh} style={{ alignSelf: 'start', fontSize: '0.85rem' }}>
        ↻ Refresh list
      </button>
    </div>
  )
}
