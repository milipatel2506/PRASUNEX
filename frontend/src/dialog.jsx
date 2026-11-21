import { useEffect, useRef, useState } from 'react'

/* Accessible replacement for window.confirm and window.prompt.
   `await ask({ title, body, confirmLabel, danger })` resolves true or false.
   With `input: { label }` it resolves the typed (hidden) text, or null when cancelled.
   With `fields: [{ key, label, type, autoComplete, minLength }]` it resolves an object of the typed values, or null.
   Uses the native <dialog> element: focus is trapped, Esc cancels, focus returns to the button that opened it. */
let opener = null

export const ask = (opts) => new Promise((resolve) => {
  if (opener) opener({ ...opts, resolve })
  else if (opts.input || opts.fields) resolve(window.prompt(opts.body || opts.title))  // host not mounted: fall back to the browser box
  else resolve(window.confirm(opts.body || opts.title))
})

const fieldsOf = (d) => d.fields || (d.input ? [{ key: 'v', label: d.input.label, type: 'password', autoComplete: 'new-password', minLength: 8 }] : null)

export function DialogHost() {
  const [d, setD] = useState(null)
  const [vals, setVals] = useState({})
  const ref = useRef(null)
  const back = useRef(null)
  const cur = useRef(null)

  useEffect(() => {
    opener = (o) => {
      if (cur.current) cur.current.resolve(fieldsOf(cur.current) ? null : false)  // never leave an earlier question hanging
      if (!cur.current) back.current = document.activeElement  // keep the first opener if a dialog replaces another
      cur.current = o; setVals({}); setD(o)
    }
    return () => { opener = null }
  }, [])
  useEffect(() => { if (d && ref.current && !ref.current.open) ref.current.showModal() }, [d])

  if (!d) return null
  const fields = fieldsOf(d)
  const finish = (result) => {
    const resolve = d.resolve
    if (ref.current && ref.current.open) ref.current.close()
    cur.current = null
    setD(null)
    resolve(result)
    const b = back.current
    const target = b && b.isConnected && !b.disabled && b !== document.body ? b : document.getElementById('main')
    if (target && target.focus) setTimeout(() => target.focus(), 0)
  }
  const cancelled = fields ? null : false
  const submitted = () => (d.fields ? vals : d.input ? vals.v : true)
  return (
    <dialog ref={ref} className="dialog" aria-labelledby="dlg-title" aria-describedby="dlg-body"
      onCancel={(e) => { e.preventDefault(); finish(cancelled) }}>
      <form onSubmit={(e) => { e.preventDefault(); finish(submitted()) }}>
        <h2 id="dlg-title">{d.title}</h2>
        <p id="dlg-body">{d.body}</p>
        {fields && fields.map((f, i) => (
          <label key={f.key} style={{ marginBottom: 10 }}>{f.label}
            <input type={f.type || 'text'} required minLength={f.minLength} autoComplete={f.autoComplete || 'off'} autoFocus={i === 0}
              value={vals[f.key] || ''} onChange={(e) => setVals({ ...vals, [f.key]: e.target.value })} />
          </label>
        ))}
        <div className="row" style={{ justifyContent: 'flex-end', gap: 8, marginTop: 18 }}>
          <button type="button" className="btn alt" onClick={() => finish(cancelled)}>Cancel</button>
          <button type="submit" className={'btn' + (d.danger ? ' danger' : '')} autoFocus={!fields}>{d.confirmLabel || 'Confirm'}</button>
        </div>
      </form>
    </dialog>
  )
}
