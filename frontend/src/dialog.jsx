import { useEffect, useRef, useState } from 'react'

/* Accessible replacement for window.confirm and window.prompt.
   `await ask({ title, body, confirmLabel, danger })` resolves true or false.
   With `input: { label }` it resolves the typed text, or null when cancelled.
   Uses the native <dialog> element: focus is trapped, Esc cancels, focus returns to the button that opened it. */
let opener = null

export const ask = (opts) => new Promise((resolve) => {
  if (opener) opener({ ...opts, resolve })
  else if (opts.input) resolve(window.prompt(opts.body || opts.title))  // host not mounted: fall back to the browser box
  else resolve(window.confirm(opts.body || opts.title))
})

export function DialogHost() {
  const [d, setD] = useState(null)
  const [val, setVal] = useState('')
  const ref = useRef(null)
  const back = useRef(null)
  const cur = useRef(null)

  useEffect(() => {
    opener = (o) => {
      if (cur.current) cur.current.resolve(cur.current.input ? null : false)  // never leave an earlier question hanging
      back.current = document.activeElement; cur.current = o; setVal(''); setD(o)
    }
    return () => { opener = null }
  }, [])
  useEffect(() => { if (d && ref.current && !ref.current.open) ref.current.showModal() }, [d])

  if (!d) return null
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
  const cancelled = d.input ? null : false
  return (
    <dialog ref={ref} className="dialog" aria-labelledby="dlg-title" aria-describedby="dlg-body"
      onCancel={(e) => { e.preventDefault(); finish(cancelled) }}>
      <form onSubmit={(e) => { e.preventDefault(); finish(d.input ? val : true) }}>
        <h2 id="dlg-title">{d.title}</h2>
        <p id="dlg-body">{d.body}</p>
        {d.input && (
          <label>{d.input.label}
            <input type="password" required minLength={8} autoComplete="new-password" autoFocus value={val} onChange={(e) => setVal(e.target.value)} />
          </label>
        )}
        <div className="row" style={{ justifyContent: 'flex-end', gap: 8, marginTop: 18 }}>
          <button type="button" className="btn alt" onClick={() => finish(cancelled)}>Cancel</button>
          <button type="submit" className={'btn' + (d.danger ? ' danger' : '')} autoFocus={!d.input}>{d.confirmLabel || 'Confirm'}</button>
        </div>
      </form>
    </dialog>
  )
}
