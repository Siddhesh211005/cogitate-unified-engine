import { useEffect, useState, useCallback } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { getEngine, getHealth, listRaters, listTemplates, clearEngineCache } from './api'
import { normalizeRaterMeta } from './normalize'
import Header from './components/Header'
import AdminDashboard from './components/AdminDashboard'
import AdminRaterWorkspace from './components/AdminRaterWorkspace'
import ClientDashboard from './components/ClientDashboard'
import ClientRaterWorkspace from './components/ClientRaterWorkspace'

// ── Root App ──────────────────────────────────────────────────────────────
export default function App() {
  const [engine, setEngine] = useState(null)
  const [raters, setRaters] = useState([])
  const [ready, setReady] = useState(false)
  const [status, setStatus] = useState('Connecting…')

  const refreshRaters = useCallback(async (eng) => {
    const e = eng ?? engine
    if (!e) return []
    try {
      const [rawRaters, rawTemplates] = await Promise.all([
        listRaters(),
        listTemplates(e),
      ])
      const merged = [
        ...(rawRaters || []).map((r) => normalizeRaterMeta(r, e, 'raters')),
        ...(rawTemplates || []).map((r) => normalizeRaterMeta(r, e, 'templates')),
      ]
      setRaters(merged)
      return merged
    } catch {
      return []
    }
  }, [engine])

  useEffect(() => {
    let mounted = true
    async function init() {
      clearEngineCache()
      const eng = await getEngine()
      if (!mounted) return
      setEngine(eng)

      if (!eng) {
        setStatus('No engine selected — open http://localhost:8080 to choose an engine.')
        setReady(true)
        return
      }

      try {
        await getHealth()
        const rows = await refreshRaters(eng)
        if (mounted) setStatus(`${eng === 'schema' ? '🤖 Schema AI' : '📊 Excel Native'} engine · ${rows.length} rater(s) loaded`)
      } catch (e) {
        if (mounted) setStatus(`Backend unavailable: ${e.message}`)
      } finally {
        if (mounted) setReady(true)
      }
    }
    init()
    return () => { mounted = false }
  }, []) // eslint-disable-line

  if (!ready) {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        minHeight: '100vh', flexDirection: 'column', gap: 12,
      }}>
        <div className="brand-mark" style={{ width: 56, height: 56, fontSize: '1.3rem' }}>CR</div>
        <p style={{ color: '#64748b' }}>{status}</p>
      </div>
    )
  }

  // No engine — show gateway redirect notice
  if (!engine) {
    return (
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        minHeight: '100vh', flexDirection: 'column', gap: 16, textAlign: 'center', padding: 24,
      }}>
        <div className="brand-mark" style={{ width: 56, height: 56, fontSize: '1.3rem' }}>CR</div>
        <h2 style={{ margin: 0, fontFamily: 'Space Grotesk, sans-serif' }}>No Engine Selected</h2>
        <p style={{ color: '#64748b', maxWidth: 420 }}>{status}</p>
        <a
          href="http://localhost:8080"
          className="link-btn-solid primary"
          style={{ display: 'inline-block', padding: '10px 24px', borderRadius: 12 }}
        >
          Go to Gateway →
        </a>
      </div>
    )
  }

  const handleRefresh = () => refreshRaters()

  return (
    <BrowserRouter>
      <div className="connection-note">{status}</div>
      <Routes>
        <Route path="/" element={<Navigate to="/admin" replace />} />

        {/* Admin */}
        <Route path="/admin" element={
          <div className={`shell shell-admin`}>
            <Header mode="admin" engine={engine} />
            <AdminDashboard engine={engine} raters={raters} onRefresh={handleRefresh} />
          </div>
        } />
        <Route path="/admin/rater/:id" element={
          <div className="shell shell-admin">
            <Header mode="admin" engine={engine} />
            <AdminRaterWorkspace engine={engine} raters={raters} />
          </div>
        } />

        {/* Client */}
        <Route path="/client" element={
          <div className="shell shell-client">
            <Header mode="client" engine={engine} />
            <ClientDashboard engine={engine} raters={raters} onRefresh={handleRefresh} />
          </div>
        } />
        <Route path="/client/rater/:id" element={
          <div className="shell shell-client">
            <Header mode="client" engine={engine} />
            <ClientRaterWorkspace engine={engine} raters={raters} />
          </div>
        } />

        <Route path="*" element={<Navigate to="/admin" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
