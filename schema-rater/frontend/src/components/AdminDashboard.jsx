import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { deleteRater } from '../api'
import FileUpload from './FileUpload'

/**
 * AdminDashboard — upload section + rater list table.
 * Props: { engine, raters, onRefresh }
 */
export default function AdminDashboard({ engine, raters = [], onRefresh }) {
  const [q, setQ] = useState('')
  const [busyId, setBusyId] = useState('')
  const [deleteError, setDeleteError] = useState('')

  const filtered = raters.filter((r) =>
    (r.name || '').toLowerCase().includes(q.toLowerCase())
  )
  const liveCount = raters.filter((r) => r.source === 'raters').length
  const templateCount = raters.filter((r) => r.source === 'templates').length

  const handleUploaded = useCallback(async () => {
    await onRefresh()
  }, [onRefresh])

  const handleDelete = useCallback(async (rater) => {
    if (rater.source !== 'raters') return
    if (!window.confirm(`Delete rater "${rater.name}"? This cannot be undone.`)) return
    setDeleteError('')
    setBusyId(rater.id)
    try {
      await deleteRater(rater.id, engine)
      await onRefresh()
    } catch (e) {
      setDeleteError(e.message || 'Failed to delete rater')
    } finally {
      setBusyId('')
    }
  }, [engine, onRefresh])

  return (
    <div style={{ padding: 20, display: 'grid', gap: 20 }}>
      {/* Flow strip */}
      <div className="flow-strip">
        {['Upload', 'Inspect', 'Test', 'Approve'].map((s, i) => (
          <div key={s} className="flow-chip"><span>{i + 1}</span>{s}</div>
        ))}
      </div>

      {/* Upload section */}
      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>Upload Rater</h2>
            <p>Upload any Excel-based rater (.xlsx). The engine will parse its schema automatically.</p>
          </div>
        </div>
        <FileUpload engine={engine} onUploaded={handleUploaded} />
      </section>

      {/* Rater list */}
      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>Backend Artifacts</h2>
            <p>Raters loaded from the {engine === 'schema' ? 'schema' : 'excel'} backend.</p>
          </div>
          <button onClick={onRefresh}>↻ Refresh</button>
        </div>

        {/* Stats */}
        <div className="stats-grid">
          <article className="stat-card">
            <h4>Total</h4>
            <strong>{raters.length}</strong>
            <p>Raters and templates</p>
          </article>
          <article className="stat-card">
            <h4>Live Raters</h4>
            <strong>{liveCount}</strong>
            <p>Available for calculations</p>
          </article>
          <article className="stat-card">
            <h4>Templates</h4>
            <strong>{templateCount}</strong>
            <p>Reference models</p>
          </article>
        </div>

        {/* Search */}
        <div className="filter-row" style={{ marginBottom: 12 }}>
          <input
            className="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search by name…"
          />
        </div>

        {deleteError && <p className="warn" style={{ marginBottom: 10 }}>{deleteError}</p>}

        {!filtered.length ? (
          <div className="empty-card">
            <h3>{q ? 'No matches found' : 'No raters uploaded yet'}</h3>
            <p>{q ? 'Try a different search term.' : 'Upload your first rater using the section above.'}</p>
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Type</th>
                <th>File</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <tr key={r.id}>
                  <td><strong>{r.name}</strong></td>
                  <td>
                    <span className={`badge badge-${r.status === 'template' ? 'draft' : 'published'}`}>
                      {r.status}
                    </span>
                  </td>
                  <td style={{ color: '#64748b', fontSize: '0.85rem' }}>{r.filename || '—'}</td>
                  <td className="row-actions">
                    <Link to={`/admin/rater/${r.id}`}>Inspect</Link>
                    <Link to={`/admin/rater/${r.id}`} state={{ testMode: true }}>Test</Link>
                    {r.source === 'raters' && (
                      <button
                        onClick={() => handleDelete(r)}
                        disabled={busyId === r.id}
                        style={{ color: '#ef4444', borderColor: '#fecaca', background: '#fff1f2' }}
                      >
                        {busyId === r.id ? 'Deleting…' : 'Delete'}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}
