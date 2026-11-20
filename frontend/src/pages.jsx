import { useEffect, useRef, useState } from 'react'
import { Download, RefreshCw, Upload } from 'lucide-react'
import { api } from './api'

export const ROLE = { teacher: 'Faculty', principal: 'Principal', admin: 'Admin' }
const LANG = { en: 'English', gu: 'ગુજરાતી', hi: 'हिन्दी' }
const LANG_NAME = { en: 'English', gu: 'Gujarati', hi: 'Hindi' }
const STATUS = { queued: 'Queued', sending: 'Sending', sent: 'Sent', delivered: 'Delivered', read: 'Read', failed: 'Failed', undelivered: 'Undelivered' }
const TICKS = { sent: '✓', delivered: '✓✓', read: '✓✓' }
const TIER = { high: 'High', medium: 'Medium', low: 'Low', unscored: 'Not scored' }

function Status({ s }) { return <span className={'tag st-' + s}><i />{STATUS[s] || s}</span> }
function Err({ children }) { return children ? <div className="error" role="alert" style={{ margin: '0 0 14px' }}>{children}</div> : null }
function Done({ children }) { return children ? <div className="ok" role="status" style={{ margin: '0 0 14px' }}>{children}</div> : null }
const when = (t) => (t ? t.replace(' ', ' | ') : 'not yet')

/* ======================== Messages outbox + parent's phone ======================== */
export function MessagesPage() {
  const [rows, setRows] = useState(null)
  const [err, setErr] = useState('')
  const [sel, setSel] = useState(null)
  const [busy, setBusy] = useState(false)
  const load = () => api('/messages').then((r) => { setRows(r); setErr('') }).catch((e) => setErr(e.message))
  useEffect(() => { load(); const t = setInterval(load, 3000); return () => clearInterval(t) }, [])
  useEffect(() => { if (rows && rows.length && sel === null) setSel(rows[0].id) }, [rows])
  const m = rows && rows.find((r) => r.id === sel)

  const act = async (path) => {
    setBusy(true)
    try { await api(`/messages/${sel}/${path}`, { method: 'POST' }); await load() } catch (e) { setErr(e.message) }
    setBusy(false)
  }
  if (!rows) return <div className="page" role="status">{err || 'Loading...'}</div>
  return (
    <div className="page">
      <Err>{err}</Err>
      {rows.length === 0 ? (
        <div className="panel"><h3>No messages yet</h3><p className="muted">When a teacher approves a parent message, it is sent and appears here with its delivery status.</p></div>
      ) : (
        <div className="split wide">
          <section className="panel" style={{ padding: 0, overflow: 'auto' }}>
            <table>
              <thead><tr><th>Student</th><th>Parent</th><th>Language</th><th>Status</th><th>Sent</th></tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className={r.id === sel ? 'sel' : ''}>
                    <td><button className="linklike" aria-current={r.id === sel} onClick={() => setSel(r.id)}>{r.student_name}</button><div className="muted small">Class {r.cls}</div></td>
                    <td>{r.parent_name}<div className="muted small">{r.parent_phone}{r.demo_number ? ' (demo number)' : ''}</div></td>
                    <td>{LANG_NAME[r.language]}</td>
                    <td><Status s={r.status} /></td>
                    <td className="small">{when(r.sent_at || r.ts)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
          {m && (
            <section className="panel">
              <h3 className="sec">Parent's phone ({m.provider === 'twilio' ? 'real WhatsApp' : 'simulated'})</h3>
              <div className="phone">
                <div className="bar2">SAARTHI School | official account</div>
                <div className="bubble">{m.body}<div className={'tick ' + m.status}>{m.sent_at && m.sent_at.slice(11, 16)} {TICKS[m.status] || ''}</div></div>
              </div>
              <dl className="facts">
                <dt>To</dt><dd>{m.parent_name} ({m.parent_phone})</dd>
                <dt>About</dt><dd>{m.student_name}, class {m.cls}</dd>
                <dt>Sent</dt><dd>{when(m.sent_at)}</dd>
                <dt>Delivered</dt><dd>{when(m.delivered_at)}</dd>
                <dt>Read</dt><dd>{when(m.read_at)}</dd>
              </dl>
              {m.error && <div className="error" role="alert" style={{ marginTop: 10 }}>Could not deliver: {m.error}</div>}
              {m.provider === 'simulated' && (
                <>
                  <button className="btn alt" disabled={busy || m.status === 'read'} onClick={() => act('read')}>Simulate: parent opens the message</button>
                  <p className="muted small" style={{ margin: '8px 0 0' }}>Demo only. This parent has a placeholder number, so nothing leaves this computer. A real number plus WhatsApp settings (admin, Settings) sends a real message.</p>
                </>
              )}
              {m.can_refresh && <button className="btn alt" disabled={busy} onClick={() => act('refresh')}><RefreshCw size={16} aria-hidden="true" />Refresh status</button>}
            </section>
          )}
        </div>
      )}
    </div>
  )
}

/* ======================== Weekly data entry ======================== */
const FIELDS = [['attendance', 'Attendance %', 0, 100], ['homework', 'Homework %', 0, 100], ['incidents', 'Incidents', 0, 20],
  ['maths', 'Maths', 0, 100], ['science', 'Science', 0, 100], ['english', 'English', 0, 100], ['social', 'Social', 0, 100], ['language', 'Language', 0, 100]]

export function WeeklyPage() {
  const [classes, setClasses] = useState([])
  const [cls, setCls] = useState('')
  const [rows, setRows] = useState([])
  const [err, setErr] = useState('')
  const [done, setDone] = useState('')
  const [busy, setBusy] = useState(false)
  const curCls = useRef('')
  useEffect(() => { api('/classes').then((c) => { setClasses(c); if (c[0]) setCls(c[0].cls) }).catch((e) => setErr(e.message)) }, [])
  const blank = { attendance: 90, homework: 80, incidents: 0, maths: 60, science: 60, english: 60, social: 60, language: 60 }
  const load = () => {
    const c = cls
    if (!c) return Promise.resolve()
    return api('/weekly?cls=' + c).then((r) => {
      if (curRefIs(c)) setRows(r.map((s) => {
        const last = s.last || blank  // a brand-new student has no earlier week to copy from
        return { id: s.id, name: s.name, roll: s.roll, week: s.next_week,
          v: { ...last, attendance: s.last ? Math.round(last.attendance * 100) : last.attendance, homework: s.last ? Math.round(last.homework * 100) : last.homework } }
      }))
    }).catch((e) => setErr(e.message))
  }
  const curRefIs = (c) => curCls.current === c
  useEffect(() => { curCls.current = cls; setRows([]); setDone(''); setErr(''); load() }, [cls])
  const set = (id, k, val) => setRows((rs) => rs.map((r) => (r.id === id ? { ...r, v: { ...r.v, [k]: val } } : r)))

  const save = async () => {
    setErr(''); setDone('')
    for (const r of rows) for (const [k, label, lo, hi] of FIELDS) {
      const n = Number(r.v[k])
      if (r.v[k] === '' || Number.isNaN(n) || n < lo || n > hi) { setErr(`${r.name}: ${label} must be a number from ${lo} to ${hi}.`); return }
    }
    setBusy(true)
    try {
      const res = await api('/weekly', { method: 'POST', body: { cls, rows: rows.map((r) => ({
        student_id: r.id, attendance: Number(r.v.attendance) / 100, homework: Number(r.v.homework) / 100, incidents: Math.round(Number(r.v.incidents)),
        maths: Number(r.v.maths), science: Number(r.v.science), english: Number(r.v.english), social: Number(r.v.social), language: Number(r.v.language) })) } })
      setDone(`Saved this week for ${res.saved} students. Risk scores were updated for ${res.scored} of them.`)
      await load()
    } catch (e) { setErr(e.message) }
    setBusy(false)
  }
  return (
    <div className="page">
      <div className="seg" role="group" aria-label="Class">
        {classes.map((c) => <button key={c.cls} aria-pressed={cls === c.cls} className={cls === c.cls ? 'on' : ''} onClick={() => setCls(c.cls)}><b>Class {c.cls}</b></button>)}
      </div>
      <Err>{err}</Err><Done>{done}</Done>
      <p className="muted" style={{ marginTop: 0 }}>Enter this week's numbers for every student. The values start from last week, so you only change what is different. Saving updates each student's risk score straight away.</p>
      <section className="panel" style={{ padding: 0, overflow: 'auto' }}>
        <table className="entry">
          <thead><tr><th>Roll</th><th>Student</th><th>Week</th>{FIELDS.map(([k, label]) => <th key={k}>{label}</th>)}</tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{r.roll}</td><td>{r.name}</td><td>{r.week}</td>
                {FIELDS.map(([k, label, lo, hi]) => (
                  <td key={k}><input type="number" inputMode="decimal" min={lo} max={hi} value={r.v[k]} aria-label={`${r.name} ${label}`} onChange={(e) => set(r.id, k, e.target.value)} /></td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <div style={{ marginTop: 16 }}><button className="btn" disabled={busy || !rows.length} onClick={save}>{busy ? 'Saving...' : `Save week for class ${cls}`}</button></div>
    </div>
  )
}

/* ======================== Admin: students ======================== */
function parseCsv(text) {
  const rows = []
  let row = [], cur = '', quoted = false
  const endRow = () => { row.push(cur); cur = ''; if (row.some((x) => x.trim() !== '')) rows.push(row); row = [] }
  for (let i = 0; i < text.length; i++) {
    const c = text[i]
    if (quoted) { if (c === '"') { if (text[i + 1] === '"') { cur += '"'; i++ } else quoted = false } else cur += c }
    else if (c === '"') quoted = true
    else if (c === ',') { row.push(cur); cur = '' }
    else if (c === '\n' || c === '\r') { if (c === '\r' && text[i + 1] === '\n') i++; endRow() }
    else cur += c
  }
  endRow()
  if (!rows.length) return []
  const head = rows.shift().map((h) => h.trim().toLowerCase())
  return rows.map((r) => {
    const o = Object.fromEntries(head.map((h, i) => [h, (r[i] ?? '').trim()]))
    return { ...o, roll: Number(o.roll), parent_language: o.parent_language || 'en' }
  })
}
const TEMPLATE = 'name,cls,roll,parent_language,parent_name,parent_phone,first_gu,first_hi\nAarti Shah,9A,31,gu,Mr. Shah,+919876543210,,\n'

const EMPTY = { name: '', cls: '', roll: '', parent_language: 'gu', parent_name: '', parent_phone: '', first_gu: '', first_hi: '' }

export function AdminStudents() {
  const [rows, setRows] = useState(null)
  const [err, setErr] = useState('')
  const [done, setDone] = useState('')
  const [filter, setFilter] = useState('')
  const [form, setForm] = useState(EMPTY)
  const [edit, setEdit] = useState(null)
  const [csv, setCsv] = useState(null)
  const file = useRef(null)
  const load = () => api('/admin/students').then(setRows).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [])
  const run = async (fn, ok) => { setErr(''); setDone(''); try { await fn(); if (ok) setDone(ok); await load() } catch (e) { setErr(e.message) } }

  const add = (e) => { e.preventDefault(); run(() => api('/admin/students', { method: 'POST', body: { ...form, roll: Number(form.roll) } }).then(() => setForm(EMPTY)), 'Student added. Enter at least 4 weeks of data on the Weekly data page to get a risk score.') }
  const saveEdit = () => run(() => api('/admin/students/' + edit.id, { method: 'PATCH', body: { parent_name: edit.parent_name, parent_phone: edit.parent_phone, parent_language: edit.parent_language } }).then(() => setEdit(null)), 'Parent contact saved.')
  const pick = (e) => {
    const f = e.target.files[0]
    if (!f) return
    f.text().then((t) => { try { setCsv(parseCsv(t)) } catch { setErr('Could not read that file as CSV.') } })
  }
  const doImport = () => run(async () => {
    const res = await api('/admin/students/import', { method: 'POST', body: { rows: csv } })
    setCsv(null); if (file.current) file.current.value = ''
    setDone(`Imported ${res.added} students.` + (res.errors.length ? ` ${res.errors.length} rows were skipped: ` + res.errors.slice(0, 4).map((x) => `row ${x.row} (${x.error})`).join('; ') : ''))
  })
  if (!rows) return <div className="page" role="status">{err || 'Loading...'}</div>
  const shown = rows.filter((r) => !filter || (r.name + r.cls + r.parent_name).toLowerCase().includes(filter.toLowerCase()))
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })
  return (
    <div className="page">
      <Err>{err}</Err><Done>{done}</Done>
      <div className="grid2" style={{ marginBottom: 20 }}>
        <section className="panel">
          <h3 className="sec">Add a student</h3>
          <form className="form" onSubmit={add}>
            <label>Full name<input required value={form.name} onChange={set('name')} /></label>
            <div className="two">
              <label>Class (for example 9A)<input required pattern="[0-9]{1,2}[A-Z]" value={form.cls} onChange={set('cls')} /></label>
              <label>Roll number<input required type="number" min="1" max="99" value={form.roll} onChange={set('roll')} /></label>
            </div>
            <label>Parent or guardian name<input value={form.parent_name} onChange={set('parent_name')} /></label>
            <div className="two">
              <label>Parent WhatsApp number<input placeholder="+91 98765 43210" value={form.parent_phone} onChange={set('parent_phone')} /></label>
              <label>Message language<select value={form.parent_language} onChange={set('parent_language')}>{Object.entries(LANG).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
            </div>
            <div className="two">
              <label>First name in Gujarati (optional)<input value={form.first_gu} onChange={set('first_gu')} /></label>
              <label>First name in Hindi (optional)<input value={form.first_hi} onChange={set('first_hi')} /></label>
            </div>
            <div><button className="btn" type="submit">Add student</button></div>
          </form>
        </section>
        <section className="panel">
          <h3 className="sec">Import from a spreadsheet</h3>
          <p className="muted small" style={{ marginTop: 0 }}>Upload a CSV file with the columns name, cls, roll, parent_language, parent_name, parent_phone, first_gu, first_hi.</p>
          <a className="btn alt" href={'data:text/csv;charset=utf-8,' + encodeURIComponent(TEMPLATE)} download="students-template.csv"><Download size={16} aria-hidden="true" />Download template</a>
          <div style={{ marginTop: 14 }}><label className="small muted">Choose CSV file<input ref={file} type="file" accept=".csv,text/csv" onChange={pick} style={{ display: 'block', marginTop: 6 }} /></label></div>
          {csv && (
            <div style={{ marginTop: 14 }}>
              <p>{csv.length} rows found. First row: <b>{csv[0] && csv[0].name}</b>, class {csv[0] && csv[0].cls}.</p>
              <button className="btn" onClick={doImport}><Upload size={16} aria-hidden="true" />Import {csv.length} students</button>
            </div>
          )}
        </section>
      </div>
      <div className="list-head"><b>All students <span className="muted small">{shown.length} of {rows.length}</span></b>
        <input className="search" type="search" placeholder="Search name, class or parent" aria-label="Search students" value={filter} onChange={(e) => setFilter(e.target.value)} /></div>
      <section className="panel" style={{ padding: 0, overflow: 'auto' }}>
        <table>
          <thead><tr><th>Student</th><th>Class</th><th>Parent</th><th>WhatsApp number</th><th>Language</th><th>Level</th><th></th></tr></thead>
          <tbody>
            {shown.map((r) => edit && edit.id === r.id ? (
              <tr key={r.id} className="sel">
                <td>{r.name}</td><td>{r.cls} / {r.roll}</td>
                <td><input aria-label="Parent name" value={edit.parent_name} onChange={(e) => setEdit({ ...edit, parent_name: e.target.value })} /></td>
                <td><input aria-label="Parent phone" value={edit.parent_phone} onChange={(e) => setEdit({ ...edit, parent_phone: e.target.value })} /></td>
                <td><select aria-label="Language" value={edit.parent_language} onChange={(e) => setEdit({ ...edit, parent_language: e.target.value })}>{Object.entries(LANG).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></td>
                <td></td>
                <td><div className="row" style={{ gap: 6 }}><button className="btn" onClick={saveEdit}>Save</button><button className="btn alt" onClick={() => setEdit(null)}>Cancel</button></div></td>
              </tr>
            ) : (
              <tr key={r.id}>
                <td>{r.name}</td><td>{r.cls} / {r.roll}</td><td>{r.parent_name}</td>
                <td>{r.parent_phone}{r.demo_number && <span className="muted small"> (demo)</span>}</td>
                <td>{LANG_NAME[r.parent_language]}</td>
                <td><span className={'tag ' + (r.tier === 'unscored' ? 'unscored' : r.tier)}><i />{TIER[r.tier]}</span></td>
                <td><button className="btn alt" onClick={() => setEdit({ id: r.id, parent_name: r.parent_name, parent_phone: r.demo_number ? '' : r.parent_phone, parent_language: r.parent_language })}>Edit contact</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  )
}

/* ======================== Admin: users ======================== */
function ClassPicker({ classes, value, onChange }) {
  const toggle = (c) => onChange(value.includes(c) ? value.filter((x) => x !== c) : [...value, c])
  return <div className="checks" role="group" aria-label="Classes">{classes.map((c) => <label key={c}><input type="checkbox" checked={value.includes(c)} onChange={() => toggle(c)} />{c}</label>)}</div>
}

export function AdminUsers({ me }) {
  const [users, setUsers] = useState(null)
  const [classes, setClasses] = useState([])
  const [err, setErr] = useState('')
  const [done, setDone] = useState('')
  const [form, setForm] = useState({ username: '', name: '', password: '', role: 'teacher', classes: [] })
  const [edit, setEdit] = useState(null)
  const load = () => api('/admin/users').then(setUsers).catch((e) => setErr(e.message))
  useEffect(() => { load(); api('/classes').then((c) => setClasses(c.map((x) => x.cls))) }, [])
  const run = async (fn, ok) => { setErr(''); setDone(''); try { await fn(); if (ok) setDone(ok); await load() } catch (e) { setErr(e.message) } }
  const create = (e) => { e.preventDefault(); run(() => api('/admin/users', { method: 'POST', body: form }).then(() => setForm({ username: '', name: '', password: '', role: 'teacher', classes: [] })), 'Account created. Share the username and password with them privately.') }
  const patch = (u, body, ok) => run(() => api('/admin/users/' + u.id, { method: 'PATCH', body }), ok)
  if (!users) return <div className="page" role="status">{err || 'Loading...'}</div>
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })
  return (
    <div className="page">
      <Err>{err}</Err><Done>{done}</Done>
      <div className="grid2" style={{ marginBottom: 20 }}>
        <section className="panel">
          <h3 className="sec">Create an account</h3>
          <form className="form" onSubmit={create}>
            <label>Full name<input required minLength={2} value={form.name} onChange={set('name')} /></label>
            <div className="two">
              <label>Username (lowercase, no spaces)<input required pattern="[a-z0-9_.]{3,30}" value={form.username} onChange={set('username')} /></label>
              <label>Role<select value={form.role} onChange={set('role')}><option value="teacher">Faculty</option><option value="principal">Principal</option><option value="admin">Admin</option></select></label>
            </div>
            <label>Password (at least 8 characters)<input required type="password" minLength={8} autoComplete="new-password" value={form.password} onChange={set('password')} /></label>
            {form.role === 'teacher' && <div><div className="small muted">Classes this faculty member teaches</div><ClassPicker classes={classes} value={form.classes} onChange={(v) => setForm({ ...form, classes: v })} /></div>}
            <div><button className="btn" type="submit">Create account</button></div>
          </form>
        </section>
        <section className="panel">
          <h3 className="sec">What each role can do</h3>
          <dl className="facts">
            <dt>Faculty</dt><dd>Sees only their own classes. Enters weekly data, creates and approves action plans, tracks messages.</dd>
            <dt>Principal</dt><dd>Read-only view of every class, the school overview, messages and the AI audit log.</dd>
            <dt>Admin</dt><dd>Everything above, plus managing accounts, students, parent contacts and WhatsApp settings.</dd>
          </dl>
        </section>
      </div>
      <section className="panel" style={{ padding: 0, overflow: 'auto' }}>
        <table>
          <thead><tr><th>Name</th><th>Username</th><th>Role</th><th>Classes</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td>{u.name}</td><td>{u.username}</td><td>{ROLE[u.role]}</td>
                <td>{u.role === 'teacher' ? (edit && edit.id === u.id ? <ClassPicker classes={classes} value={edit.classes} onChange={(v) => setEdit({ ...edit, classes: v })} /> : (u.classes.join(', ') || 'none')) : 'All'}</td>
                <td><span className={'tag ' + (u.active ? 'approved' : 'high')}><i />{u.active ? 'Active' : 'Disabled'}</span></td>
                <td>
                  <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
                    {u.role === 'teacher' && (edit && edit.id === u.id
                      ? <><button className="btn" onClick={() => patch(u, { classes: edit.classes }, 'Classes updated.').then(() => setEdit(null))}>Save</button><button className="btn alt" onClick={() => setEdit(null)}>Cancel</button></>
                      : <button className="btn alt" onClick={() => setEdit({ id: u.id, classes: u.classes })}>Edit classes</button>)}
                    <button className="btn alt" disabled={u.username === me.username && u.active} onClick={() => patch(u, { active: !u.active }, u.active ? 'Account disabled and signed out.' : 'Account enabled.')}>{u.active ? 'Disable' : 'Enable'}</button>
                    <button className="btn alt" onClick={() => { const p = window.prompt(`New password for ${u.name} (at least 8 characters)`); if (p) patch(u, { password: p }, 'Password changed.') }}>Reset password</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  )
}

/* ======================== Admin: settings ======================== */
export function SettingsPage() {
  const [s, setS] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => { api('/admin/settings').then(setS).catch((e) => setErr(e.message)) }, [])
  if (err) return <div className="page"><Err>{err}</Err></div>
  if (!s) return <div className="page" role="status">Loading...</div>
  const w = s.whatsapp
  return (
    <div className="page">
      <div className="grid2">
        <section className="panel">
          <h3 className="sec">WhatsApp delivery</h3>
          <p><span className={'tag ' + (w.configured ? 'approved' : 'draft')}><i />{w.configured ? 'Connected: real messages are sent' : 'Simulated: nothing leaves this computer'}</span></p>
          {!w.configured && <p className="muted small">Missing settings: {w.missing.join(', ')}</p>}
          <p className="muted small">Placeholder demo numbers (+91 00000 ...) are never sent to, even when WhatsApp is connected. A message goes out only when an admin has entered a real number for that student.</p>
          <h4 className="sec" style={{ marginTop: 18 }}>How to test with real WhatsApp (Twilio sandbox, free)</h4>
          <ol className="small steps">
            <li>Create a free account at twilio.com and open Messaging, then Try it out, then Send a WhatsApp message.</li>
            <li>On your phone, send the shown join code (for example "join apple-tiger") to the sandbox number on WhatsApp.</li>
            <li>Set three environment variables before starting the app: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_WHATSAPP_FROM (the sandbox number, +14155238886).</li>
            <li>In Students, edit one student's parent contact and enter your own phone number.</li>
            <li>As faculty, approve a plan for that student. The message arrives on your phone, and Messages shows its status.</li>
          </ol>
        </section>
        <section className="panel">
          <h3 className="sec">AI message writer</h3>
          <p><span className={'tag ' + (s.ai.provider === 'llm' ? 'approved' : 'draft')}><i />{s.ai.provider === 'llm' ? 'AI language model' : 'Built-in template engine'}</span></p>
          <p className="muted small">{s.ai.note}</p>
          <h3 className="sec" style={{ marginTop: 18 }}>Privacy</h3>
          <p className="small">Secrets are read from environment variables and are never stored in the database or shown on screen. Messages to parents contain the child's first name and the teacher's approved text only.</p>
        </section>
      </div>
    </div>
  )
}
