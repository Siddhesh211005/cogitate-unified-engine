import { useState, useCallback } from 'react'
import { uploadFile, saveUploadedRater } from '../api'
import { normalizeUploadResponse, normalizeSchema, slugify } from '../normalize'

/**
 * FileUpload — handles both engine upload flows:
 *   Schema-rater: single step (upload → done)
 *   Excel-rater: two steps (upload → preview schema → confirm save)
 */
export default function FileUpload({ engine, onUploaded }) {
  const [dragging, setDragging] = useState(false)
  const [phase, setPhase] = useState('idle')       // idle | uploading | preview | saving | done | error
  const [error, setError] = useState(null)

  // Preview state (excel only)
  const [preview, setPreview] = useState(null)      // normalizeUploadResponse result (type='pending')
  const [raterName, setRaterName] = useState('')
  const [raterDesc, setRaterDesc] = useState('')
  const [saveAs, setSaveAs] = useState('raters')

  const reset = () => {
    setPhase('idle'); setError(null); setPreview(null)
    setRaterName(''); setRaterDesc(''); setSaveAs('raters')
  }

  const doUpload = useCallback(async (file) => {
    setError(null)
    setPhase('uploading')
    try {
      const raw = await uploadFile(file, engine)
      const normalized = normalizeUploadResponse(raw, engine)
      const previewData = {
        ...normalized,
        uploadId: normalized.uploadId || normalized.raterId,
        filename: normalized.filename || file.name,
        rawConfig: normalized.rawConfig || normalized.schema,
      }

      setPreview(previewData)
      setRaterName(
        previewData.schema?.name ||
        (previewData.filename || '').replace(/\.[^.]+$/, '')
      )
      setRaterDesc('')
      setPhase('preview')
    } catch (e) {
      setError(e.message)
      setPhase('error')
    }
  }, [engine, onUploaded])

  const doSave = async () => {
    if (!preview) return
    setPhase('saving')
    setError(null)
    try {
      const slug = slugify(raterName) || `rater-${Date.now()}`
      await saveUploadedRater({
        uploadId: preview.uploadId || preview.raterId,
        config: preview.rawConfig,
        slug,
        name: raterName || slug,
        description: raterDesc,
        source: saveAs,
      })
      setPhase('done')
      await onUploaded(slug)
      setTimeout(reset, 2000)
    } catch (e) {
      setError(e.message)
      setPhase('error')
    }
  }

  const handleDrop = (e) => {
    e.preventDefault(); setDragging(false)
    const file = e.dataTransfer.files?.[0]
    if (file) doUpload(file)
  }

  const handleFile = (e) => {
    const file = e.target.files?.[0]
    if (file) doUpload(file)
  }

  // ── Preview step (excel only) ─────────────────────────────────────────
  if (phase === 'preview' && preview) {
    const { schema } = preview
    return (
      <div className="panel">
        <div className="panel-head">
          <div>
            <h3>Confirm Upload</h3>
            <p>Review the parsed schema, then save to make this rater available.</p>
          </div>
        </div>

        <div className="two-col" style={{ gap: 20 }}>
          {/* Left: metadata form */}
          <div>
            <label>
              <span className="field-label">Rater Name</span>
              <input value={raterName} onChange={(e) => setRaterName(e.target.value)} placeholder="e.g. Commercial Auto Rater" />
            </label>
            <label style={{ marginTop: 10 }}>
              <span className="field-label">Description (optional)</span>
              <input value={raterDesc} onChange={(e) => setRaterDesc(e.target.value)} placeholder="Short description" />
            </label>
            <label style={{ marginTop: 10 }}>
              <span className="field-label">Save as</span>
              <select value={saveAs} onChange={(e) => setSaveAs(e.target.value)}>
                <option value="raters">Live Rater (production use)</option>
                <option value="templates">Template (reference model)</option>
              </select>
            </label>
          </div>

          {/* Right: schema summary */}
          <div>
            <div className="schema-inspector">
              <h3 style={{ marginTop: 0 }}>Parsed Schema</h3>
              <div className="schema-stats">
                <p>File: <strong>{preview.filename}</strong></p>
                <p>Inputs: <strong>{schema?.inputs?.length ?? 0}</strong></p>
                <p>Outputs: <strong>{schema?.outputs?.length ?? 0}</strong></p>
              </div>
              <div style={{ maxHeight: 160, overflowY: 'auto', marginTop: 10 }}>
                <table>
                  <thead><tr><th>Field</th><th>Type</th><th>Group</th></tr></thead>
                  <tbody>
                    {(schema?.inputs || []).map((f) => (
                      <tr key={f.field}>
                        <td>{f.label}</td>
                        <td><span className="badge">{f.type}</span></td>
                        <td>{f.group}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>

        {error && <p className="warn" style={{ marginTop: 12 }}>{error}</p>}

        <div className="wizard-actions" style={{ marginTop: 16 }}>
          <button onClick={reset}>Cancel</button>
          <button className="primary" onClick={doSave} disabled={!raterName.trim()}>
            Save Rater
          </button>
        </div>
      </div>
    )
  }

  // ── Done ─────────────────────────────────────────────────────────────
  if (phase === 'done') {
    return (
      <div className="empty-card" style={{ padding: 18 }}>
        <p className="success-note" style={{ fontSize: '1rem' }}>✓ Rater saved successfully!</p>
      </div>
    )
  }

  // ── Drop zone (idle / uploading / error) ──────────────────────────────
  return (
    <label
      className="upload-box"
      style={{ cursor: phase === 'uploading' ? 'wait' : 'pointer', opacity: phase === 'uploading' ? 0.7 : 1,
        borderColor: dragging ? 'var(--brand)' : undefined }}
      onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
    >
      <span style={{ fontSize: '2rem', display: 'block', textAlign: 'center', marginBottom: 6 }}>
        {phase === 'uploading' ? '⏳' : '📂'}
      </span>
      <span style={{ display: 'block', textAlign: 'center', fontWeight: 600, marginBottom: 4 }}>
        {phase === 'uploading' ? 'Uploading & parsing…' : 'Drop a workbook here, or click to browse'}
      </span>
      <span style={{ display: 'block', textAlign: 'center', fontSize: '0.8rem', color: '#64748b' }}>
        .xlsx or .xls · up to 50 MB
      </span>
      <input
        type="file"
        accept=".xlsx,.xls"
        style={{ display: 'none' }}
        disabled={phase === 'uploading'}
        onChange={handleFile}
      />
      {error && <p className="warn" style={{ marginTop: 10, textAlign: 'center' }}>{error}</p>}
    </label>
  )
}
