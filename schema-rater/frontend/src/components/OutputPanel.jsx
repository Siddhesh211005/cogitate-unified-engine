import { useMemo } from 'react'
import { formatOutputValue, isFormulaError, isSkippable, isPrimaryOutput } from '../normalize'

/**
 * OutputPanel — displays canonical calculation results.
 * Works identically for both excel-rater and schema-rater results.
 * Props:
 *   result   — { outputs, outputMeta, warnings, refer } (canonical)
 *   schema   — canonical schema (for output field labels)
 *   loading  — bool
 *   mode     — 'admin' | 'client'
 */
export default function OutputPanel({ result, schema, loading = false, mode = 'client' }) {
  const entries = useMemo(() => {
    if (!result) return []

    const metaMap = new Map(
      (result.outputMeta || []).map((m) => [m.name, m])
    )

    // Build from schema outputs list first (preserves order)
    const schemaOutputs = schema?.outputs || []
    const seen = new Set()
    const list = []

    for (const out of schemaOutputs) {
      const val = result.outputs?.[out.field]
      if (isSkippable(val)) continue
      seen.add(out.field)
      const meta = metaMap.get(out.field)
      list.push({
        key: out.field,
        label: meta?.label || out.label,
        value: val,
        group: meta?.group || out.group || 'Results',
        order: meta?.order ?? out.order ?? 0,
        isPrimary: out.isPrimary || isPrimaryOutput(out.field, out.label),
        isError: isFormulaError(val),
      })
    }

    // Add any extra outputs not in schema (schema-rater may return more)
    for (const [key, val] of Object.entries(result.outputs || {})) {
      if (seen.has(key) || isSkippable(val)) continue
      const meta = metaMap.get(key)
      list.push({
        key,
        label: meta?.label || key.replace(/_/g, ' '),
        value: val,
        group: meta?.group || 'Results',
        order: meta?.order ?? 999,
        isPrimary: isPrimaryOutput(key, key),
        isError: isFormulaError(val),
      })
    }

    list.sort((a, b) => a.order - b.order)
    return list
  }, [result, schema])

  // Group entries
  const groups = useMemo(() => {
    const map = new Map()
    for (const e of entries) {
      if (!map.has(e.group)) map.set(e.group, [])
      map.get(e.group).push(e)
    }
    return Array.from(map.entries())
  }, [entries])

  const primaryEntry = entries.find((e) => e.isPrimary)
  const hasErrors = entries.some((e) => e.isError)
  const { warnings = [], refer = false } = result || {}

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '32px 0', color: '#3b82f6', fontWeight: 600 }}>
        <div style={{ marginBottom: 8, fontSize: '1.5rem' }}>⟳</div>
        Calculating…
      </div>
    )
  }

  if (!result) {
    return (
      <div style={{ textAlign: 'center', padding: '40px 0', color: '#94a3b8' }}>
        <div style={{ fontSize: '2rem', marginBottom: 10 }}>📊</div>
        <p>Fill in inputs and press <strong>Calculate</strong></p>
      </div>
    )
  }

  return (
    <div style={{ display: 'grid', gap: 12 }}>
      {/* Hero result */}
      {primaryEntry && (
        <div className="hero-result">
          <div style={{ fontSize: '0.8rem', opacity: 0.85, marginBottom: 4 }}>{primaryEntry.label}</div>
          <div>{formatOutputValue(primaryEntry.value)}</div>
        </div>
      )}

      {/* Summary strip */}
      <div className="result-meta-strip" style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
        <p>Outputs: <strong>{entries.length}</strong></p>
        {result.outputMeta?.length > 0 && (
          <p>Groups: <strong>{groups.length}</strong></p>
        )}
      </div>

      {/* Refer warning */}
      {refer && (
        <div className="validation-box">
          <h4>⚠ Manual Referral Required</h4>
          <p>This risk configuration requires manual review before binding.</p>
        </div>
      )}

      {/* Output groups */}
      {groups.map(([group, items]) => (
        <div key={group}>
          {groups.length > 1 && (
            <p style={{ margin: '0 0 6px', fontSize: '0.75rem', fontWeight: 700,
              textTransform: 'uppercase', letterSpacing: '0.05em', color: '#64748b' }}>
              {group}
            </p>
          )}
          <table>
            <thead>
              <tr><th>Output</th><th>Value</th></tr>
            </thead>
            <tbody>
              {items.map((entry) => (
                <tr key={entry.key}
                  style={entry.isPrimary ? { fontWeight: 700, background: '#f0f7ff' }
                    : entry.isError ? { background: '#fff1f2' } : {}}>
                  <td>{entry.label}</td>
                  <td style={{
                    textAlign: 'right',
                    color: entry.isError ? '#ef4444' : entry.isPrimary ? '#1d4ed8' : undefined,
                  }}>
                    {formatOutputValue(entry.value)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}

      {/* Error notice */}
      {hasErrors && (
        <div className="validation-box">
          <h4>Formula Errors</h4>
          <p>Some outputs show Excel formula errors. These fields use functions not supported by the calculation engine.</p>
        </div>
      )}

      {/* Warnings */}
      {warnings.length > 0 && (
        <details>
          <summary style={{ cursor: 'pointer', color: '#64748b', fontSize: '0.82rem' }}>
            {warnings.length} calculation note{warnings.length > 1 ? 's' : ''}
          </summary>
          <ul style={{ margin: '8px 0 0', paddingLeft: 18 }}>
            {warnings.map((w, i) => <li key={i} style={{ color: '#92400e', fontSize: '0.82rem' }}>{w}</li>)}
          </ul>
        </details>
      )}
    </div>
  )
}
