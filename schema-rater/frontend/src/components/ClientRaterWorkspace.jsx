import { useEffect, useState, useCallback, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getRaterConfig, calculateRater, calculateDefaults } from '../api'
import { normalizeSchema, normalizeResult, buildInitialValues } from '../normalize'
import DynamicForm from './DynamicForm'
import OutputPanel from './OutputPanel'

/**
 * ClientRaterWorkspace — dynamic form + live results side by side.
 * Auto-calculates with defaults on load; recalculates on manual submit.
 */
export default function ClientRaterWorkspace({ engine, raters }) {
  const { id } = useParams()
  const navigate = useNavigate()

  const rater = raters.find((r) => r.id === id)
  const [schema, setSchema] = useState(null)
  const [schemaLoading, setSchemaLoading] = useState(true)
  const [schemaError, setSchemaError] = useState('')

  const [values, setValues] = useState({})
  const [result, setResult] = useState(null)
  const [calculating, setCalculating] = useState(false)
  const [calcError, setCalcError] = useState('')
  const abortRef = useRef(null)
  const debounceRef = useRef(null)

  // Load schema
  useEffect(() => {
    if (!rater) return
    let mounted = true
    setSchemaLoading(true); setSchemaError('')
    getRaterConfig(id, engine)
      .then((raw) => {
        if (!mounted) return
        const s = normalizeSchema(raw, engine, id)
        setSchema(s)
        const defaults = buildInitialValues(s)
        setValues(defaults)
      })
      .catch((e) => { if (mounted) setSchemaError(e.message) })
      .finally(() => { if (mounted) setSchemaLoading(false) })
    return () => { mounted = false }
  }, [id, engine, rater])

  // Auto-calculate defaults once schema is loaded
  useEffect(() => {
    if (!schema || !id) return
    let mounted = true
    abortRef.current?.abort()
    abortRef.current = new AbortController()
    setCalculating(true)

    calculateDefaults(id, engine)
      .then((raw) => { if (mounted) setResult(normalizeResult(raw, engine)) })
      .catch((e) => { if (mounted && e.name !== 'AbortError') setCalcError(e.message) })
      .finally(() => { if (mounted) setCalculating(false) })

    return () => { mounted = false; abortRef.current?.abort() }
  }, [schema, id, engine])

  const runCalc = useCallback((vals) => {
    abortRef.current?.abort()
    abortRef.current = new AbortController()
    setCalcError(''); setCalculating(true)
    calculateRater(id, vals, engine)
      .then((raw) => setResult(normalizeResult(raw, engine)))
      .catch((e) => { if (e.name !== 'AbortError') setCalcError(e.message) })
      .finally(() => setCalculating(false))
  }, [id, engine])

  const handleChange = useCallback((field, val) => {
    setValues((prev) => {
      const next = { ...prev, [field]: val }
      if (debounceRef.current) clearTimeout(debounceRef.current)
      debounceRef.current = setTimeout(() => runCalc(next), 650)
      return next
    })
  }, [runCalc])

  const handleCalculate = useCallback(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    runCalc(values)
  }, [runCalc, values])

  if (!rater) return (
    <div style={{ padding: 20 }}>
      <div className="empty-card">
        <h3>Rater not found</h3>
        <button onClick={() => navigate('/client')} style={{ marginTop: 12 }}>← Back to Raters</button>
      </div>
    </div>
  )

  return (
    <div style={{ padding: 20, display: 'grid', gap: 16 }}>
      {/* Breadcrumb */}
      <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
        <button onClick={() => navigate('/client')} style={{ fontSize: '0.85rem' }}>← Raters</button>
        <span style={{ color: '#94a3b8' }}>/</span>
        <span style={{ fontWeight: 700 }}>{rater.name}</span>
      </div>

      {/* Info strip */}
      <section className="client-hero">
        <div>
          <h2>{rater.name}</h2>
          {rater.filename && <p>📄 {rater.filename}</p>}
          {schema && <p>{schema.inputs.length} inputs · {schema.outputs.length} outputs</p>}
        </div>
        {result && !calculating && (
          <div className="hero-meta-cards">
            <article><span>Status</span><strong style={{ color: '#0d9c74' }}>✓ Calculated</strong></article>
            <article><span>Outputs</span><strong>{Object.keys(result.outputs || {}).length}</strong></article>
            <article><span>Warnings</span><strong>{result.warnings?.length || 0}</strong></article>
          </div>
        )}
      </section>

      {schemaLoading && <div className="empty-card"><p>Loading rater schema…</p></div>}
      {schemaError && <p className="warn">{schemaError}</p>}

      {schema && (
        <div className="two-col sticky-workspace">
          {/* Inputs */}
          <div className="panel input-scroll-pane">
            <h3 style={{ margin: '0 0 14px' }}>Inputs</h3>
            <DynamicForm schema={schema} values={values} onChange={handleChange} />
            {calcError && <p className="warn" style={{ marginTop: 10 }}>{calcError}</p>}
            <div className="calc-actions-sticky">
              <div className="inline-actions">
                <button onClick={() => { const d = buildInitialValues(schema); setValues(d); runCalc(d) }}>
                  Reset to Defaults
                </button>
                <button className="primary" onClick={handleCalculate} disabled={calculating}>
                  {calculating ? 'Calculating…' : '▶ Calculate Premium'}
                </button>
              </div>
            </div>
          </div>

          {/* Outputs */}
          <div className="panel output-sticky-pane">
            <h3 style={{ margin: '0 0 14px' }}>Premium Results</h3>
            <OutputPanel result={result} schema={schema} loading={calculating} mode="client" />
          </div>
        </div>
      )}
    </div>
  )
}
