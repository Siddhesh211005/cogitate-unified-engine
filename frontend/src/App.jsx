import { useEffect, useState, useCallback } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { getCurrentEngine, selectEngine, getHealth, listRaters, listTemplates } from './api'
import Header from './components/Header'
import AdminDashboard from './components/AdminDashboard'
import AdminRaterWorkspace from './components/AdminRaterWorkspace'
import ClientDashboard from './components/ClientDashboard'
import ClientRaterWorkspace from './components/ClientRaterWorkspace'

// ── Engine Selector Screen ────────────────────────────────────────────────────

function EngineSelector({ onSelected }) {
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState('')

  async function choose(engine) {
    setBusy(engine)
    setError('')
    try {
      await selectEngine(engine)
      onSelected(engine)
    } catch (e) {
      setError(e.message || 'Failed to select engine')
      setBusy(null)
    }
  }

  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      minHeight: '100vh', flexDirection: 'column', gap: 32, padding: 24,
      background: 'var(--bg)',
    }}>
      <div style={{ textAlign: 'center' }}>
        <div className="brand-mark" style={{ width: 64, height: 64, fontSize: '1.5rem', margin: '0 auto 16px' }}>CR</div>
        <h1 style={{ margin: 0, fontFamily: 'Space Grotesk, sans-serif', fontSize: '2rem' }}>
          Cogitate Rater Engine
        </h1>
        <p style={{ color: '#64748b', marginTop: 8 }}>
          Select your rating engine to get started
        </p>
      </div>

      <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap', justifyContent: 'center' }}>
        {[
          { key: 'schema', label: 'Schema Engine', icon: '🤖', desc: 'AI-powered schema analysis. Upload any Excel rater and get an instant dynamic form.' },
          { key: 'excel', label: 'Excel Engine', icon: '📊', desc: 'Native Excel execution. Calculation powered directly by the Excel formula engine.' },
        ].map(({ key, label, icon, desc }) => (
          <button
            key={key}
            id={`engine-select-${key}`}
            onClick={() => choose(key)}
            disabled={!!busy}
            className="panel"
            style={{
              width: 260, padding: 28, textAlign: 'left', cursor: busy ? 'wait' : 'pointer',
              opacity: busy && busy !== key ? 0.5 : 1,
              transition: 'opacity 200ms, transform 200ms',
            }}
          >
            <div style={{ fontSize: '2.5rem', marginBottom: 12 }}>{icon}</div>
            <h2 style={{ margin: '0 0 8px', fontSize: '1.1rem', fontFamily: 'Space Grotesk, sans-serif' }}>
              {label}
            </h2>
            <p style={{ margin: 0, fontSize: '0.85rem', color: '#64748b', lineHeight: 1.5 }}>{desc}</p>
            {busy === key && (
              <p style={{ margin: '10px 0 0', fontSize: '0.8rem', color: '#0f5fff' }}>Connecting…</p>
            )}
          </button>
        ))}
      </div>

      {error && <p style={{ color: '#ef4444', margin: 0 }}>{error}</p>}
    </div>
  )
}

// ── Root App ──────────────────────────────────────────────────────────────────

export default function App() {
  const [engine, setEngine] = useState(undefined)   // undefined = loading
  const [raters, setRaters] = useState([])
  const [ready, setReady] = useState(false)
  const [status, setStatus] = useState('Connecting…')

  const refreshRaters = useCallback(async () => {
    try {
      const [rawRaters, rawTemplates] = await Promise.all([
        listRaters(),
        listTemplates(),
      ])
      const merged = [
        ...(rawRaters || []),
        ...(rawTemplates || []),
      ]
      setRaters(merged)
      return merged
    } catch {
      return []
    }
  }, [])

  useEffect(() => {
    let mounted = true
    async function init() {
      const eng = await getCurrentEngine()
      if (!mounted) return
      setEngine(eng)

      if (!eng) {
        setReady(true)
        return
      }

      try {
        await getHealth()
        const rows = await refreshRaters()
        if (mounted) setStatus(
          `${eng === 'schema' ? '🤖 Schema' : '📊 Excel'} engine · ${rows.length} rater(s) loaded`
        )
      } catch (e) {
        if (mounted) setStatus(`Backend unavailable: ${e.message}`)
      } finally {
        if (mounted) setReady(true)
      }
    }
    init()
    return () => { mounted = false }
  }, []) // eslint-disable-line

  // Loading splash
  if (!ready || engine === undefined) {
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

  // No engine selected → show inline selector
  if (!engine) {
    return (
      <EngineSelector
        onSelected={(eng) => {
          setEngine(eng)
          setReady(false)
          // Re-init with the newly selected engine
          getHealth()
            .then(() => refreshRaters())
            .then((rows) => setStatus(
              `${eng === 'schema' ? '🤖 Schema' : '📊 Excel'} engine · ${rows.length} rater(s) loaded`
            ))
            .catch((e) => setStatus(`Backend unavailable: ${e.message}`))
            .finally(() => setReady(true))
        }}
      />
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
          <div className="shell shell-admin">
            <Header mode="admin" engine={engine} onReset={() => setEngine(null)} />
            <AdminDashboard raters={raters} onRefresh={handleRefresh} />
          </div>
        } />
        <Route path="/admin/rater/:id" element={
          <div className="shell shell-admin">
            <Header mode="admin" engine={engine} onReset={() => setEngine(null)} />
            <AdminRaterWorkspace raters={raters} />
          </div>
        } />

        {/* Client */}
        <Route path="/client" element={
          <div className="shell shell-client">
            <Header mode="client" engine={engine} onReset={() => setEngine(null)} />
            <ClientDashboard raters={raters} onRefresh={handleRefresh} />
          </div>
        } />
        <Route path="/client/rater/:id" element={
          <div className="shell shell-client">
            <Header mode="client" engine={engine} onReset={() => setEngine(null)} />
            <ClientRaterWorkspace raters={raters} />
          </div>
        } />

        <Route path="*" element={<Navigate to="/admin" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
