import { useMemo } from 'react'

/**
 * DynamicForm — renders grouped input fields from a canonical schema.
 * Supports: text, number, dropdown, boolean, date
 * Props:
 *   schema     — canonical schema object { inputs, outputs, name }
 *   values     — { [field]: value }
 *   onChange   — (field, value) => void
 */
export default function DynamicForm({ schema, values = {}, onChange }) {
  const groups = useMemo(() => {
    const map = new Map()
    for (const inp of schema?.inputs || []) {
      const g = inp.group || 'General'
      if (!map.has(g)) map.set(g, [])
      map.get(g).push(inp)
    }
    return Array.from(map.entries())
  }, [schema])

  if (!schema?.inputs?.length) {
    return <p style={{ color: '#64748b' }}>No input fields found in this rater.</p>
  }

  return (
    <div style={{ display: 'grid', gap: 14 }}>
      {groups.map(([group, fields]) => (
        <div key={group} className="panel-sub">
          <h3 style={{ margin: '0 0 12px', fontSize: '0.85rem', textTransform: 'uppercase',
            letterSpacing: '0.05em', color: '#64748b' }}>{group}</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 12 }}>
            {fields.map((inp) => (
              <FieldInput key={inp.field} field={inp} value={values[inp.field]} onChange={onChange} />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function FieldInput({ field, value, onChange }) {
  const id = `field-${field.field}`
  const val = value === undefined ? field.default : value

  const handleChange = (newVal) => onChange(field.field, newVal)
  const coerceSelectValue = (raw) => {
    const match = (field.options || []).find((opt) => String(opt.value) === String(raw))
    return match ? match.value : raw
  }

  return (
    <label htmlFor={id}>
      <span className="field-label">{field.label}</span>
      {field.cellRef && <span className="field-hint">Cell: {field.cellRef}</span>}

      {field.type === 'dropdown' ? (
        <select id={id} value={String(val ?? '')} onChange={(e) => handleChange(coerceSelectValue(e.target.value))}>
          {field.options.map((opt) => (
            <option key={String(opt.value)} value={String(opt.value)}>{opt.label}</option>
          ))}
        </select>
      ) : field.type === 'boolean' ? (
        <select id={id} value={String(Boolean(val))} onChange={(e) => handleChange(e.target.value === 'true')}>
          <option value="true">Yes</option>
          <option value="false">No</option>
        </select>
      ) : field.type === 'number' ? (
        <input
          id={id}
          type="number"
          value={val ?? ''}
          onChange={(e) => handleChange(e.target.value === '' ? '' : Number(e.target.value))}
          placeholder={field.cellRef ? `→ ${field.cellRef}` : ''}
        />
      ) : (
        <input
          id={id}
          type={field.type === 'date' ? 'date' : 'text'}
          value={val ?? ''}
          onChange={(e) => handleChange(e.target.value)}
          placeholder={field.cellRef ? `→ ${field.cellRef}` : ''}
        />
      )}
    </label>
  )
}
