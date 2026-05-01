import { useEffect, useState, useCallback, useRef } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { getRaterConfig, getTemplateConfig, calculateRater, calculateTemplate } from '../api'
import { normalizeSchema, normalizeResult, buildInitialValues } from '../normalize'
import DynamicForm from './DynamicForm'
import OutputPanel from './OutputPanel'

/**
 * AdminRaterWorkspace — schema inspector + test calculation workspace.
 * Opens to the Schema tab by default; switches to Test tab if navigated
 * with state { testMode: true }.
 */
export default function AdminRaterWorkspace({ engine, raters }) {
  const { id } = useParams()
  const navigate = useNavigate()
  const location = useLocation()

  const rater = raters.find((r) => r.id === id)
  const [schema, setSchema] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [tab, setTab] = useState(location.state?.testMode ? 'test' : 'schema')

  // Test workspace state
  const [values, setValues] = useState({})
  const [result, setResult] = useState(null)
  const [testError, setTestError] = useState('')
  const [calculating, setCalculating] = useState(false)
  const [jsonMode, setJsonMode] = useState(false)
  const [rawJson, setRawJson] = useState('{}')
  const abortRef = useRef(null)

  useEffect(() => {
    if (!rater) return
    let mounted = true
    setLoading(true); setError('')
    const load = rater.source === 'templates'
      ? getTemplateConfig(id, engine)
      : getRaterConfig(id, engine)

    load.then((raw) => {
      if (!mounted) return
      const s = normalizeSchema(raw, engine, id)
      setSchema(s)
      const defaults = buildInitialValues(s)
      setValues(defaults)
      setRawJson(JSON.stringify(defaults, null, 2))
    }).catch((e) => {
      if (mounted) setError(e.message || 'Failed to load schema')
    }).finally(() => { if (mounted) setLoading(false) })

    return () => { mounted = false }
  }, [id, engine, rater])

  const runTest = useCallback(async () => {
    let payload = values
    if (jsonMode) {
      try { payload = JSON.parse(rawJson) } catch {
        setTestError('Invalid JSON'); return
      }
    }
    abortRef.current?.abort()
    abortRef.current = new AbortController()
    setTestError(''); setCalculating(true)
    try {
      const raw = rater?.source === 'templates'
        ? await calculateTemplate(id, payload, engine)
        : await calculateRater(id, payload, engine)
      setResult(normalizeResult(raw, engine))
    } catch (e) {
      if (e.name !== 'AbortError') setTestError(e.message || 'Calculation failed')
    } finally { setCalculating(false) }
  }, [values, jsonMode, rawJson, id, engine, rater])

  const handleChange = useCallback((field, val) => {
    setValues((prev) => {
      const next = { ...prev, [field]: val }
      if (jsonMode) setRawJson(JSON.stringify(next, null, 2))
      return next
    })
  }, [jsonMode])

  if (!rater) return (
    <div style={{ padding: 20 }}>
      <div className="empty-card">
        <h3>Rater not found</h3>
        <p>The rater "{id}" could not be found.</p>
        <button onClick={() => navigate('/admin')} style={{ marginTop: 12 }}>← Back to Admin</button>
      </div>
    </div>
  )

  return (
    <div style={{ padding: 20, display: 'grid', gap: 16 }}>
      {/* Breadcrumb + controls */}
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <button onClick={() => navigate('/admin')} style={{ fontSize: '0.85rem' }}>← Admin</button>
        <span style={{ color: '#94a3b8' }}>/</span>
        <span style={{ fontWeight: 700 }}>{rater.name}</span>
        <span className={`badge badge-${rater.source === 'templates' ? 'draft' : 'published'}`}
          style={{ marginLeft: 4 }}>{rater.status}</span>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 8 }}>
        {['schema', 'test'].map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={tab === t ? 'primary' : ''}
            style={{ textTransform: 'capitalize' }}>
            {t === 'schema' ? '📋 Schema Inspector' : '🧪 Test Workspace'}
          </button>
        ))}
      </div>

      {loading && <div className="empty-card"><p>Loading schema…</p></div>}
      {error && <p className="warn">{error}</p>}

      {/* ── Schema Inspector tab ── */}
      {!loading && !error && schema && tab === 'schema' && (
        <section className="panel">
          <div className="panel-head">
            <div><h2>{schema.name} — Schema Inspector</h2>
              <p>{schema.inputs.length} input fields · {schema.outputs.length} output fields</p>
            </div>
            <button className="primary" onClick={() => setTab('test')}>Open Test Workspace →</button>
          </div>

          <div className="schema-inspector">
            <div className="schema-stats">
              <p>Inputs: <strong>{schema.inputs.length}</strong></p>
              <p>Outputs: <strong>{schema.outputs.length}</strong></p>
              <p>Filename: <strong>{schema.filename || '—'}</strong></p>
            </div>
            <div className="schema-columns">
              <div>
                <h4>Input Fields</h4>
                <table>
                  <thead><tr><th>Label</th><th>Type</th><th>Cell</th><th>Group</th></tr></thead>
                  <tbody>
                    {schema.inputs.map((f) => (
                      <tr key={f.field}>
                        <td>{f.label}</td>
                        <td><span className="badge">{f.type}</span></td>
                        <td style={{ color: '#64748b', fontSize: '0.82rem' }}>{f.cellRef || '—'}</td>
                        <td style={{ color: '#64748b', fontSize: '0.82rem' }}>{f.group}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div>
                <h4>Output Fields</h4>
                <table>
                  <thead><tr><th>Label</th><th>Cell</th><th>Primary</th></tr></thead>
                  <tbody>
                    {schema.outputs.map((f) => (
                      <tr key={f.field}>
                        <td>{f.label}</td>
                        <td style={{ color: '#64748b', fontSize: '0.82rem' }}>{f.cellRef || '—'}</td>
                        <td>{f.isPrimary ? '✓' : ''}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* ── Test Workspace tab ── */}
      {!loading && !error && schema && tab === 'test' && (
        <section className="panel two-col sticky-workspace">
          {/* Left: inputs */}
          <div className="panel-sub input-scroll-pane">
            <div className="panel-head">
              <h3>Inputs</h3>
              <button onClick={() => setJsonMode((v) => !v)}>
                {jsonMode ? '📝 Use Form' : '{ } Use JSON'}
              </button>
            </div>
            {jsonMode ? (
              <textarea
                rows={16}
                value={rawJson}
                onChange={(e) => setRawJson(e.target.value)}
                style={{ fontFamily: 'monospace', fontSize: '0.82rem' }}
              />
            ) : (
              <DynamicForm schema={schema} values={values} onChange={handleChange} />
            )}
            {testError && <p className="warn" style={{ marginTop: 10 }}>{testError}</p>}
            <div className="calc-actions-sticky">
              <div className="inline-actions">
                <button onClick={() => { const d = buildInitialValues(schema); setValues(d); setRawJson(JSON.stringify(d, null, 2)); setResult(null) }}>
                  Reset
                </button>
                <button className="primary" onClick={runTest} disabled={calculating}>
                  {calculating ? 'Running…' : '▶ Run Test'}
                </button>
              </div>
            </div>
          </div>

          {/* Right: outputs */}
          <div className="panel-sub output-sticky-pane">
            <h3 style={{ margin: '0 0 14px' }}>Results</h3>
            <OutputPanel result={result} schema={schema} loading={calculating} mode="admin" />
          </div>
        </section>
      )}
    </div>
  )
}
