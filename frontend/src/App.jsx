import { Fragment, useEffect, useRef, useState } from 'react'
import { BarChart3, ClipboardList, GraduationCap, LogOut, MessageSquare, RefreshCw, ScrollText, Send, Settings as SettingsIcon, ShieldCheck, UserCog, Users, Volume2 } from 'lucide-react'
import { api, hasToken, setToken } from './api'
import { ask, DialogHost } from './dialog'
import { AdminStudents, AdminUsers, MessagesPage, ROLE, SettingsPage, WeeklyPage } from './pages'

const LANG = { en: 'English', gu: 'ગુજરાતી', hi: 'हिन्दी' }
const LANG_NAME = { en: 'English', gu: 'Gujarati', hi: 'Hindi' }
const KIND = {
  parent_contact: 'Parent contact', remedial_session: 'Catch-up session', practice_test: 'Practice test',
  homework_checklist: 'Homework checklist', counselling: 'Counselling', peer_support: 'Peer support',
  progress_check: 'Progress check', goal_setting: 'Goal setting',
}
const TIER = { high: 'High', medium: 'Medium', low: 'Low', unscored: 'Not scored' }
const TIER_BAR = { high: 'var(--danger-bar)', medium: 'var(--warn-bar)', low: 'var(--ok-bar)', unscored: 'var(--line-strong)' }
const ACCOUNTS = [
  { u: 'hetal', name: 'Ms. Hetal Shah', note: 'Faculty, classes 9A and 9B', ini: 'HS' },
  { u: 'nikhil', name: 'Mr. Nikhil Desai', note: 'Faculty, classes 8A and 8B', ini: 'ND' },
  { u: 'rina', name: 'Ms. Rina Joshi', note: 'Faculty, class 10A', ini: 'RJ' },
  { u: 'principal', name: 'Dr. Anil Mehta', note: 'Principal, read-only view of the whole school', ini: 'AM' },
  { u: 'admin', name: 'Mr. Rajesh Patel', note: 'Admin, manages accounts, students and settings', ini: 'RP' },
]
const pct = (x) => Math.round(x * 100) + '%'
const initials = (n) => n.replace(/^(Ms|Mr|Dr)\.\s*/, '').split(' ').map((w) => w[0]).join('').slice(0, 2)

/* ---------- voice (browser text-to-speech) ---------- */
function speak(text, lang) {
  const synth = window.speechSynthesis
  if (!synth) return 'unsupported'
  const code = { en: 'en-IN', gu: 'gu-IN', hi: 'hi-IN' }[lang]
  const voices = synth.getVoices()
  const v = voices.find((x) => x.lang.toLowerCase().replace('_', '-') === code.toLowerCase()) ||
            voices.find((x) => x.lang.toLowerCase().startsWith(lang))
  const u = new SpeechSynthesisUtterance(text)
  u.lang = code
  if (v) u.voice = v
  synth.cancel()
  synth.speak(u)
  return v ? 'ok' : 'novoice'
}

/* ---------- small pieces ---------- */
function Tag({ kind, children }) {
  return <span className={'tag ' + kind}><i />{children}</span>
}

function Spark({ label, values, fmt, color, lo, hi }) {
  if (!values || values.length < 2) return null
  const W = 220, H = 48
  const min = lo ?? Math.min(...values), max = hi ?? Math.max(...values)
  const span = max - min || 1
  const pts = values.map((v, i) => [(i / (values.length - 1)) * (W - 8) + 4, H - 6 - ((v - min) / span) * (H - 12)])
  const last = values[values.length - 1], first = values[0]
  const changed = String(fmt(last)) !== String(fmt(first))
  return (
    <div className="spark">
      <small>{label}</small>
      <b>{fmt(last)}{changed && <em style={{ color: last < first ? 'var(--danger)' : 'var(--ok)' }}>{last < first ? '▼' : '▲'} from {fmt(first)}</em>}</b>
      <svg width={W} height={H} role="img" aria-label={label + ' trend over the last weeks'}>
        <polyline fill="none" stroke={color} strokeWidth="2" points={pts.map((p) => p.join(',')).join(' ')} />
        <circle cx={pts[pts.length - 1][0]} cy={pts[pts.length - 1][1]} r="3.5" fill={color} />
      </svg>
    </div>
  )
}

function HBar({ label, value, max, text, color = 'var(--primary)' }) {
  return (
    <div className="hbar">
      <span>{label}</span>
      <div className="bar"><i style={{ width: (max ? (value / max) * 100 : 0) + '%', background: color }} /></div>
      <b>{text ?? value}</b>
    </div>
  )
}

function PageHead({ title, sub }) {
  return <header className="topbar"><h1>{title}</h1>{sub && <p>{sub}</p>}</header>
}

/* ---------- sign in ---------- */
function Login({ onLogin }) {
  const [u, setU] = useState('')
  const [p, setP] = useState('')
  const [show, setShow] = useState(false)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (e) => {
    e.preventDefault()
    if (busy) return
    setBusy(true); setErr('')
    try {
      const r = await api('/login', { method: 'POST', body: { username: u.trim(), password: p } })
      setToken(r.token)
      onLogin(r.user)
    } catch (x) { setErr(x.message) }
    setBusy(false)
  }
  return (
    <div className="login">
      <aside className="login-brand">
        <div className="wordmark">SAARTHI</div>
        <div>
          <h1>Student Success Copilot</h1>
          <p>Early warning for students who are falling behind, with clear reasons, practical actions for faculty,
            and messages parents can read in their own language.</p>
        </div>
        <div className="login-foot">Team InnoTech | Prasunex Innovathon 2026</div>
      </aside>
      <main className="login-form">
        <h2>Sign in</h2>
        <p className="muted">Use your school account. Admin, faculty and principal accounts open different screens.</p>
        <form className="form" onSubmit={submit}>
          <label>Username<input autoComplete="username" required autoFocus value={u} onChange={(e) => setU(e.target.value)} /></label>
          <label>Password
            <span className="pw">
              <input type={show ? 'text' : 'password'} autoComplete="current-password" required value={p} onChange={(e) => setP(e.target.value)} />
              <button type="button" className="btn alt" aria-pressed={show} onClick={() => setShow(!show)}>{show ? 'Hide' : 'Show'}</button>
            </span>
          </label>
          {err && <div className="error" role="alert" style={{ margin: 0 }}>{err}</div>}
          <div><button className="btn" type="submit" disabled={busy}>{busy ? 'Signing in...' : 'Sign in'}</button></div>
        </form>
        <h3 className="sec" style={{ marginTop: 28 }}>Demo accounts (password: demo123)</h3>
        <ul className="accounts">
          {ACCOUNTS.map((a) => (
            <li key={a.u}>
              <button type="button" className="account" onClick={() => { setU(a.u); setP('demo123'); setErr('') }}>
                <span className="avatar" aria-hidden="true">{a.ini}</span>
                <span><b>{a.name}</b><small>{a.note}</small></span>
                <span className="fill">Fill in</span>
              </button>
            </li>
          ))}
        </ul>
      </main>
    </div>
  )
}

function LangSwitch({ lang, onPick, disabled }) {
  return (
    <div className="langs" role="group" aria-label="Message language">
      {Object.keys(LANG).map((l) => (
        <button key={l} lang={l} aria-pressed={lang === l} className={lang === l ? 'on' : ''} disabled={disabled} onClick={() => onPick(l)}>{LANG[l]}</button>
      ))}
    </div>
  )
}

/* ---------- parent contact + remove student ---------- */
function ContactCard({ d, sid, reload, onChanged }) {
  const s = d.student
  const [open, setOpen] = useState(false)
  const [f, setF] = useState({ parent_name: s.parent_name, parent_phone: s.demo_number ? '' : s.parent_phone, parent_language: s.parent_language })
  const [err, setErr] = useState('')
  const [ok, setOk] = useState('')
  const [busy, setBusy] = useState(false)
  const openEdit = () => {
    setF({ parent_name: s.parent_name, parent_phone: s.demo_number ? '' : s.parent_phone, parent_language: s.parent_language })
    setErr(''); setOk(''); setOpen(true)
  }
  const save = async (e) => {
    e.preventDefault()
    if (busy) return
    setBusy(true); setErr(''); setOk('')
    try {
      await api(`/students/${sid}/contact`, { method: 'PATCH', body: f })
      await reload(); setOpen(false); setOk('Parent contact saved.')
    } catch (x) { setErr(x.message) }
    setBusy(false)
  }
  const remove = async () => {
    if (busy) return
    if (!(await ask({ title: `Remove ${s.name}?`, body: `${s.name} will be removed from class ${s.cls}. Their weekly data, plans and messages are deleted. This cannot be undone.`, confirmLabel: 'Remove student', danger: true }))) return
    setBusy(true)
    try { await api('/students/' + sid, { method: 'DELETE' }); onChanged(true) } catch (x) { setErr(x.message); setBusy(false) }
  }
  return (
    <section className="panel">
      <div className="plan-head">
        <h3>Parent contact</h3>
        {d.can_edit && !open && <div className="row" style={{ gap: 8 }}>
          <button className="btn alt" onClick={openEdit}>{s.demo_number ? 'Add WhatsApp number' : 'Edit contact'}</button>
          <button className="btn danger" disabled={busy} onClick={remove}>Remove student</button>
        </div>}
      </div>
      {err && <div className="error" role="alert">{err}</div>}
      <div role="status">{ok && <div className="ok">{ok}</div>}</div>
      {!open ? (
        <div className="meta">
          <span>Parent <b>{s.parent_name}</b></span>
          <span>WhatsApp <b>{s.demo_number ? 'not added yet' : s.parent_phone}</b></span>
          <span>Language <b>{LANG_NAME[s.parent_language]}</b></span>
        </div>
      ) : (
        <form className="form" onSubmit={save}>
          <div className="two">
            <label>Parent or guardian name<input value={f.parent_name} onChange={(e) => setF({ ...f, parent_name: e.target.value })} /></label>
            <label>Parent WhatsApp number<input autoFocus placeholder="+91 98765 43210" value={f.parent_phone} onChange={(e) => setF({ ...f, parent_phone: e.target.value })} /></label>
          </div>
          <label>Message language<select value={f.parent_language} onChange={(e) => setF({ ...f, parent_language: e.target.value })}>{Object.entries(LANG_NAME).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
          <div className="row" style={{ gap: 8 }}><button className="btn" type="submit" disabled={busy}>{busy ? "Saving..." : "Save"}</button><button className="btn alt" type="button" onClick={() => setOpen(false)}>Cancel</button></div>
        </form>
      )}
      {s.demo_number && <p className="muted small" style={{ marginBottom: 0 }}>No real number saved, so messages stay in the simulated outbox. Add the parent's number to send on WhatsApp.</p>}
    </section>
  )
}

function WeeklyRecord({ d }) {
  const cols = d.subjects
  if (!d.weekly.length) return null
  const cell = (w, c) => (c.extra ? w.extra[c.key] : w[c.key])
  return (
    <section className="panel">
      <h3 className="sec">Weekly record</h3>
      <div style={{ overflow: 'auto' }} tabIndex={0} role="region" aria-label={`Weekly record for ${d.student.name}`}>
        <table>
          <caption className="sr-only">Every recorded week for {d.student.name}</caption>
          <thead><tr><th scope="col">Week</th><th scope="col">Attendance</th><th scope="col">Homework</th><th scope="col">Incidents</th>{cols.map((c) => <th scope="col" key={c.key}>{c.label}</th>)}<th scope="col">Average</th></tr></thead>
          <tbody>
            {[...d.weekly].reverse().map((w) => (
              <tr key={w.week}><th scope="row">Week {w.week}</th><td>{pct(w.attendance)}</td><td>{pct(w.homework)}</td><td>{w.incidents}</td>
                {cols.map((c) => { const v = cell(w, c); return <td key={c.key}>{v === undefined ? '-' : Math.round(v)}</td> })}
                <td><b>{Math.round(w.marks_avg)}</b></td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

/* ---------- student detail + action flow ---------- */
function StudentPanel({ sid, onChanged }) {
  const [d, setD] = useState(null)
  const [plan, setPlan] = useState(null)
  const [lang, setLang] = useState('en')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [voiceNote, setVoiceNote] = useState('')
  const [err, setErr] = useState('')

  const load = async () => {
    const r = await api('/students/' + sid)
    setD(r)
    const latest = r.plans[0] || null
    setPlan(latest)
    setLang(latest ? latest.language : r.student.parent_language)
    setMsg(latest ? latest.message : '')
    setErr(''); setVoiceNote('')
  }
  const refresh = async () => setD(await api('/students/' + sid))  // contact changes keep any unsaved plan edits
  useEffect(() => { load().catch((e) => setErr(e.message)) }, [sid])
  if (!d) return <div className="panel" role="status">{err || 'Loading...'}</div>

  const { student: s, risk, weekly } = d
  if (!risk) {
    return (
      <div className="stack">
        <section className="panel">
          <div className="hdr">
            <div>
              <h2>{s.name}</h2>
              <div className="meta"><span>Class <b>{s.cls}</b>, roll {s.roll}</span><span>Parent <b>{s.parent_name}</b></span></div>
            </div>
            <Tag kind="unscored">Not scored</Tag>
          </div>
          {err && <div className="error" role="alert">{err}</div>}
          <div className="note" style={{ margin: 0 }}>Not scored yet. SAARTHI needs at least 4 weeks of attendance, marks and homework for this student. Enter them on the Weekly data page, and the risk score will appear here.</div>
        </section>
        <ContactCard d={d} sid={sid} reload={refresh} onChanged={onChanged} />
      <WeeklyRecord d={d} />
      </div>
    )
  }
  const approved = plan && plan.status === 'approved'
  const live = d.whatsapp_live && !s.demo_number  // a real send will happen only with WhatsApp connected and a real number

  const wrap = async (fn) => { setBusy(true); setErr(''); try { await fn() } catch (e) { setErr(e.message) } finally { setBusy(false) } }
  const create = () => wrap(async () => {
    const p = await api(`/students/${sid}/plan`, { method: 'POST', body: { language: lang } })
    setPlan(p); setMsg(p.message)
  })
  const switchLang = (l) => {
    if (!plan || approved) { setLang(l); return }
    wrap(async () => {
      const p = await api(`/plans/${plan.id}/message`, { method: 'POST', body: { language: l } })
      setLang(l); setPlan(p); setMsg(p.message)
    })
  }
  const approve = async () => {
    const to = live ? `${s.parent_name} (${s.parent_phone}) on WhatsApp` : `${s.parent_name} (simulated, nothing leaves this computer)`
    // ask first, before the button is disabled, so keyboard focus can return to it afterwards
    if (!(await ask({ title: 'Approve and send?', body: `This message goes to ${to}. It cannot be undone.`, confirmLabel: live ? 'Send on WhatsApp' : 'Approve (simulated)' }))) return
    wrap(async () => {
    await api(`/plans/${plan.id}/approve`, { method: 'POST', body: { actions: plan.actions, message: msg, language: lang } })
    await load(); onChanged()
    })
  }
  const setOutcome = (id, outcome) => wrap(async () => { await api(`/interventions/${id}/outcome`, { method: 'POST', body: { outcome } }); await load() })
  const editAction = (i, text) => setPlan((p) => ({ ...p, actions: p.actions.map((a, j) => (j === i ? { ...a, text } : a)) }))
  const voice = () => {
    const r = speak(msg, lang)
    setVoiceNote(r === 'ok' ? '' : r === 'unsupported' ? 'Voice is not supported in this browser.' :
      `No ${LANG_NAME[lang]} voice is installed on this device. Try Chrome or Edge, or install the language voice in system settings.`)
  }
  return (
    <div className="stack">
      <section className="panel">
        <div className="hdr">
          <div>
            <h2>{s.name}</h2>
            <div className="meta">
              <span>Class <b>{s.cls}</b>, roll {s.roll}</span>
              <span>Parent language <b>{LANG_NAME[s.parent_language]}</b></span>
              <span>Weakest subject <b>{d.weakest_subject_label}</b></span>
            </div>
          </div>
          <div className="gauge"><Tag kind={risk.tier}>{TIER[risk.tier]} risk</Tag><div className="big">{pct(risk.risk)}</div></div>
        </div>
        <div className="grid2">
          <div>
            <h3 className="sec">Why this student is flagged</h3>
            {risk.reasons.length === 0 && <div className="muted">No significant risk drivers. On track.</div>}
            {risk.reasons.map((r) => (
              <div className="reason" key={r.key}>
                <div className="lbl"><span>{r.label}</span><span>{pct(r.impact)} of the risk</span></div>
                <div className="ev">{r.evidence}</div>
                <div className="bar"><i style={{ width: r.impact * 100 + '%' }} /></div>
              </div>
            ))}
            <p className="muted small" style={{ margin: '10px 0 0' }}>Reasons come from SHAP values of the risk model, grouped into plain language.</p>
          </div>
          <div>
            <h3 className="sec">Weekly trends</h3>
            <div className="trends">
              <Spark label="Attendance" values={weekly.map((w) => w.attendance)} fmt={pct} color="#1e40af" lo={0.5} hi={1} />
              <Spark label="Average marks" values={weekly.map((w) => w.marks_avg)} fmt={(v) => Math.round(v)} color="#b45309" lo={20} hi={100} />
              <Spark label="Homework on time" values={weekly.map((w) => w.homework)} fmt={pct} color="#0f766e" lo={0} hi={1} />
            </div>
          </div>
        </div>
      </section>

      <ContactCard d={d} sid={sid} reload={refresh} onChanged={onChanged} />
      <WeeklyRecord d={d} />

      <section className="panel">
        <div className="plan-head">
          <h3>Action plan and parent message</h3>
          {plan && <Tag kind={plan.status}>{plan.status === 'approved' ? 'Approved and sent' : 'Draft, needs your approval'}</Tag>}
        </div>
        {err && <div className="error" role="alert" style={{ margin: '0 0 12px' }}>{err}</div>}
        {!plan && !d.can_edit && <p className="muted" style={{ margin: 0 }}>Read-only view: only the class faculty or admin can create and send plans.</p>}
        {!plan && d.can_edit && (
          <>
            <p className="muted" style={{ marginTop: 0 }}>SAARTHI drafts three practical actions and a parent message. You review and approve before anything is sent.</p>
            <div className="small muted">Message language</div>
            <LangSwitch lang={lang} onPick={setLang} disabled={busy} />
            <div><button className="btn" disabled={busy} onClick={create}>{busy ? 'Drafting...' : 'Create action plan'}</button></div>
          </>
        )}
        {plan && (
          <div className="grid2">
            <div>
              <h4 className="sec">Actions for you</h4>
              {plan.actions.map((a, i) => (
                <div className="act-row" key={i}>
                  <span className="num">{i + 1}</span>
                  <textarea className="act" rows={4} value={a.text} disabled={approved} onChange={(e) => editAction(i, e.target.value)} aria-label={`Action ${i + 1}`} />
                </div>
              ))}
              {plan.topics.length > 0 && <><div className="small muted">Topics to revisit</div><div className="topics">{plan.topics.map((t) => <span className="chip" key={t}>{t}</span>)}</div></>}
              <div className="muted small">Made by {plan.provider === 'llm' ? 'an AI language model, checked by guardrails' : 'the built-in template engine'}</div>
              {plan.flags.length > 0 && <div className="flag">Safety notes: {plan.flags.join(', ')}</div>}
            </div>
            <div>
              <h4 className="sec">Message to parent</h4>
              <LangSwitch lang={lang} onPick={switchLang} disabled={approved || busy} />
              <div className="phone">
                <div className="bar2">{s.parent_name} | {live ? s.parent_phone + ' | WhatsApp' : 'WhatsApp (simulated)'}</div>
                <div className="bubble" lang={lang}>{msg}<div className="tick">{approved ? '✓ sent' : 'draft'}</div></div>
              </div>
              {!approved && <textarea style={{ marginTop: 12, minHeight: 110 }} value={msg} onChange={(e) => setMsg(e.target.value)} aria-label="Edit message" />}
              <div className="row" style={{ marginTop: 12, flexWrap: 'wrap' }}>
                <button className="btn alt" onClick={voice}><Volume2 size={16} aria-hidden="true" />Play voice</button>
                {!approved && d.can_edit && <button className="btn go" disabled={busy} onClick={approve}><Send size={16} aria-hidden="true" />{live ? 'Approve and send on WhatsApp' : 'Approve and send (simulated)'}</button>}
                {!approved && d.can_edit && <button className="btn alt" disabled={busy} onClick={create}><RefreshCw size={16} aria-hidden="true" />Redraft</button>}
              </div>
              {voiceNote && <div className="flag" role="status">{voiceNote}</div>}
              {approved && <div className="ok" role="status">Approved by {plan.approved_by}. {live ? `Sent to ${s.parent_name} (${s.parent_phone}).` : `Recorded in the simulated outbox for ${s.parent_name}; add a real WhatsApp number to send for real.`} Track delivery on the Messages page.</div>}
            </div>
          </div>
        )}
      </section>

      {d.interventions.length > 0 && (
        <section className="panel">
          <h3>Outcome tracker</h3>
          <p className="muted small" style={{ margin: '4px 0 8px' }}>After the follow-up period, record what happened. SAARTHI learns which actions work best.</p>
          <table>
            <thead><tr><th scope="col">Action</th><th scope="col">Type</th><th scope="col">Outcome</th></tr></thead>
            <tbody>
              {d.interventions.map((i) => (
                <tr key={i.id}>
                  <td>{i.text}</td><td>{KIND[i.kind] || i.kind}</td>
                  <td>{i.outcome ? <Tag kind={i.outcome === 'improved' ? 'approved' : i.outcome === 'declined' ? 'high' : 'medium'}>{i.outcome.replace('_', ' ')}</Tag> :
                    <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
                      <button className="btn alt" disabled={busy || !d.can_edit} aria-label={`Mark "${i.text.slice(0, 40)}" as improved`} onClick={() => setOutcome(i.id, 'improved')}>Improved</button>
                      <button className="btn alt" disabled={busy || !d.can_edit} aria-label={`Mark "${i.text.slice(0, 40)}" as no change`} onClick={() => setOutcome(i.id, 'no_change')}>No change</button>
                      <button className="btn alt" disabled={busy || !d.can_edit} aria-label={`Mark "${i.text.slice(0, 40)}" as declined`} onClick={() => setOutcome(i.id, 'declined')}>Declined</button>
                    </div>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  )
}

/* ---------- teacher view ---------- */
const NEW_STUDENT = { name: '', roll: '', parent_name: '', parent_phone: '', parent_language: 'gu' }

function AddStudent({ cls, onDone, onCancel }) {
  const [f, setF] = useState(NEW_STUDENT)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr('')
    try {
      const r = await api('/students', { method: 'POST', body: { ...f, cls, roll: Number(f.roll) } })
      onDone(r.id)
    } catch (x) { setErr(x.message) }
    setBusy(false)
  }
  return (
    <section className="panel" style={{ marginBottom: 16 }}>
      <div className="plan-head"><h3>Add a student to class {cls}</h3></div>
      {err && <div className="error" role="alert">{err}</div>}
      <form className="form" onSubmit={submit}>
        <div className="two">
          <label>Full name<input required autoFocus value={f.name} onChange={set('name')} /></label>
          <label>Roll number<input required type="number" min="1" max="99" value={f.roll} onChange={set('roll')} /></label>
        </div>
        <div className="two">
          <label>Parent or guardian name<input value={f.parent_name} onChange={set('parent_name')} /></label>
          <label>Parent WhatsApp number<input placeholder="+91 98765 43210" value={f.parent_phone} onChange={set('parent_phone')} /></label>
        </div>
        <label>Message language<select value={f.parent_language} onChange={set('parent_language')}>{Object.entries(LANG_NAME).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
        <div className="row" style={{ gap: 8 }}><button className="btn" type="submit" disabled={busy}>Add student</button><button className="btn alt" type="button" onClick={onCancel}>Cancel</button></div>
      </form>
      <p className="muted small" style={{ marginBottom: 0 }}>The new student gets a risk score after you enter 4 weeks of data on the Weekly data page.</p>
    </section>
  )
}

function Classes({ canEdit }) {
  const [adding, setAdding] = useState(false)
  const [cls, setCls] = useState([])
  const [cur, setCur] = useState(null)
  const [list, setList] = useState([])
  const [sel, setSel] = useState(null)
  const [all, setAll] = useState(false)
  const [err, setErr] = useState('')
  const curRef = useRef(null)
  curRef.current = cur

  const loadClasses = () => api('/classes').then((c) => { setErr(''); setCls(c); if ((!curRef.current || !c.some((x) => x.cls === curRef.current)) && c.length) setCur(c[0].cls) }).catch((e) => setErr(e.message))
  const loadList = () => {
    const c = cur
    if (!c) return
    api('/students?cls=' + c).then((r) => { if (curRef.current === c) { setList(r); setErr('') } }).catch((e) => setErr(e.message))
  }
  useEffect(() => { loadClasses() }, [])
  useEffect(() => { setSel(null); loadList() }, [cur])

  const flagged = list.filter((s) => s.tier === 'high' || s.tier === 'medium')
  const shown = all ? list : flagged
  return (
    <div className="page">
      {err && <div className="error" role="alert" style={{ marginBottom: 12 }}>{err}</div>}
      <div className="seg" role="group" aria-label="Class">
        {cls.map((c) => (
          <button key={c.cls} aria-pressed={cur === c.cls} className={cur === c.cls ? 'on' : ''} onClick={() => setCur(c.cls)}>
            <b>Class {c.cls}</b>
            <span>{c.high} high, {c.medium} medium</span>
          </button>
        ))}
      </div>
      {canEdit && cur && !adding && <div style={{ marginBottom: 12 }}><button className="btn alt" onClick={() => setAdding(true)}>Add student to class {cur}</button></div>}
      {adding && <AddStudent cls={cur} onCancel={() => setAdding(false)}
        onDone={(id) => { setAdding(false); setAll(true); loadClasses(); loadList(); setSel(id) }} />}
      <div className="split">
        <div>
          <div className="list-head">
            <div><b>Students</b> <span className="muted small">{all ? `all ${list.length} students` : `${flagged.length} need attention`}</span></div>
            <button className="btn alt" onClick={() => setAll(!all)}>{all ? 'Show only flagged' : 'Show all students'}</button>
          </div>
          <div className="list">
            {shown.map((s) => (
              <button key={s.id} aria-current={sel === s.id || undefined} className={'student' + (sel === s.id ? ' on' : '')} onClick={() => setSel(s.id)}>
                <div className="l1">
                  <span className="name">{s.name}</span>
                  <span className="score"><span className="n">{s.tier === 'unscored' ? '' : pct(s.risk)}</span><Tag kind={s.tier}>{TIER[s.tier]}</Tag></span>
                </div>
                <div className="l2">
                  <span>{s.tier === 'unscored' ? 'Needs 4 weeks of data' : s.reasons.length ? s.reasons.map((r) => r.label).join(', ') : 'On track'}</span>
                  {s.plan_status && <Tag kind={s.plan_status}>{s.plan_status === 'approved' ? 'Sent' : 'Draft'}</Tag>}
                </div>
                <div className="riskbar"><i style={{ width: s.risk * 100 + '%', background: TIER_BAR[s.tier] }} /></div>
              </button>
            ))}
            {!shown.length && <div className="empty">{all ? 'This class has no students yet.' : 'No students flagged in this class. Use Show all students to see everyone.'}</div>}
          </div>
        </div>
        <div>{sel ? <StudentPanel key={sel} sid={sel} onChanged={(removed) => { if (removed === true) setSel(null); loadClasses(); loadList() }} /> :
          <div className="panel"><h3>Select a student</h3><p className="muted">Pick someone from the risk radar to see why they were flagged and to create an action plan.</p></div>}</div>
      </div>
    </div>
  )
}

/* ---------- principal ---------- */
function Overview() {
  const [o, setO] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => { api('/principal/overview').then(setO).catch((e) => setErr(e.message)) }, [])
  if (err) return <div className="page"><div className="error" role="alert">{err}</div></div>
  if (!o) return <div className="page" role="status">Loading...</div>
  const s = o.stats
  const rmax = Math.max(1, ...Object.values(o.reasons))
  const smax = Math.max(1, ...Object.values(o.weak_subjects))
  return (
    <div className="page">
      <div className="stats">
        <div className="stat"><b>{s.students}</b><span>students</span></div>
        <div className="stat"><b>{s.flagged}</b><span>flagged for attention</span></div>
        <div className="stat"><b>{s.plans_approved}</b><span>action plans approved</span></div>
        <div className="stat"><b>{s.messages_sent}</b><span>parent messages (simulated)</span></div>
        <div className="stat"><b>{s.outcomes_logged}</b><span>outcomes logged</span></div>
      </div>
      <div className="grid2">
        <section className="panel">
          <h3 className="sec">Risk by class</h3>
          <div className="legend"><span><i style={{ background: 'var(--danger-bar)' }} />High</span><span><i style={{ background: 'var(--warn-bar)' }} />Medium</span><span><i style={{ background: 'var(--ok-bar)' }} />Low</span></div>
          {o.by_class.map((c) => {
            const t = c.high + c.medium + c.low || 1
            return (
              <div className="hbar" key={c.cls} style={{ gridTemplateColumns: '56px 1fr 120px' }}>
                <span>{c.cls}</span>
                <div className="stackbar"><i style={{ width: (c.high / t) * 100 + '%', background: 'var(--danger-bar)' }} /><i style={{ width: (c.medium / t) * 100 + '%', background: 'var(--warn-bar)' }} /><i style={{ width: (c.low / t) * 100 + '%', background: 'var(--ok-bar)' }} /></div>
                <span className="muted small" style={{ textAlign: 'right' }}>{c.high} high, {c.medium} medium</span>
              </div>
            )
          })}
        </section>
        <section className="panel">
          <h3 className="sec">What is driving risk (flagged students)</h3>
          {Object.entries(o.reasons).sort((a, b) => b[1] - a[1]).map(([k, v]) => <HBar key={k} label={k} value={v} max={rmax} />)}
        </section>
        <section className="panel">
          <h3 className="sec">Weakest subjects among flagged students</h3>
          {Object.entries(o.weak_subjects).sort((a, b) => b[1] - a[1]).map(([k, v]) => <HBar key={k} label={k} value={v} max={smax} color="var(--warn-bar)" />)}
        </section>
        <section className="panel">
          <h3 className="sec">Which actions work best</h3>
          <p className="muted small" style={{ margin: '0 0 6px' }}>Share of logged outcomes that improved. Includes seeded last-term demo history plus live outcomes.</p>
          {o.effectiveness.map((e) => <HBar key={e.kind} label={KIND[e.kind] || e.kind} value={e.rate} max={1} text={pct(e.rate) + ' (' + e.n + ')'} color="var(--ok-bar)" />)}
        </section>
      </div>
    </div>
  )
}

function Audit() {
  const [rows, setRows] = useState([])
  const [open, setOpen] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => { api('/audit').then(setRows).catch((e) => setErr(e.message)) }, [])
  return (
    <div className="page">
      {err && <div className="error" role="alert" style={{ marginBottom: 12 }}>{err}</div>}
      <div className="note">Every AI output is logged with exactly what was sent to the AI and who approved it. Only an anonymous reference, grade, risk reasons and topics are ever sent. Names and contact details are never included.</div>
      <section className="panel" style={{ padding: 0, overflow: 'auto' }} tabIndex={0} role="region" aria-label="AI audit log table">
        <table>
          <thead><tr><th scope="col">Time</th><th scope="col">Student ref</th><th scope="col">Source</th><th scope="col">Language</th><th scope="col">Safety flags</th><th scope="col">Approved by</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <Fragment key={r.id}>
                <tr>
                  <td>{r.ts}</td><td>{r.student_ref}</td><td>{r.provider}</td><td>{LANG[r.language]}</td>
                  <td>{r.flags.length ? r.flags.join(', ') : 'none'}</td><td>{r.approved_by || 'pending'}</td>
                  <td><button className="btn alt" onClick={() => setOpen(open === r.id ? null : r.id)}>{open === r.id ? 'Hide' : 'Inspect'}</button></td>
                </tr>
                {open === r.id && <tr key={r.id + 'x'}><td colSpan="7"><b className="small">Sent to the AI</b><pre>{JSON.stringify(r.input, null, 2)}</pre></td></tr>}
              </Fragment>
            ))}
            {!rows.length && <tr><td colSpan="7" className="muted">No AI activity yet. Create an action plan as a teacher first.</td></tr>}
          </tbody>
        </table>
      </section>
    </div>
  )
}

/* ---------- model & safety ---------- */
function ModelPage() {
  const [m, setM] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => { api('/model').then(setM).catch((e) => setErr(e.message)) }, [])
  if (err) return <div className="page"><div className="error" role="alert">{err}</div></div>
  if (!m) return <div className="page" role="status">Loading...</div>
  const x = m.metrics
  const imax = Math.max(...Object.values(m.importance))
  return (
    <div className="page">
      <div className="note">
        <b>Honest scope:</b> this prototype is trained and tested on realistic <b>synthetic</b> data. Scores are measured against labels from the same simulation, so they show the pipeline works, not real-world accuracy. Real-school validation is the first pilot step. AI source right now: <b>{m.ai.note}</b>.
      </div>
      <div className="stats">
        <div className="stat"><b>{x.auc.toFixed(2)}</b><span>AUC (ranking quality)</span></div>
        <div className="stat"><b>{pct(x.equal_flag.model_precision)}</b><span>precision, flagging the same {pct(x.equal_flag.share)} of students</span></div>
        <div className="stat"><b>{pct(x.equal_flag.model_recall)}</b><span>recall, same {pct(x.equal_flag.share)} flagged</span></div>
        <div className="stat"><b>{pct(x.rule_baseline.precision)}</b><span>precision of manual rule-of-thumb</span></div>
        <div className="stat"><b>{pct(x.rule_baseline.recall)}</b><span>recall of manual rule-of-thumb</span></div>
      </div>
      <div className="grid2">
        <section className="panel">
          <h3 className="sec">What the model looks at</h3>
          {Object.entries(m.importance).map(([k, v]) => <HBar key={k} label={k} value={v} max={imax} text={pct(v)} />)}
          <p className="muted small" style={{ margin: '10px 0 0' }}>Model: {m.model}. Trained on {x.train_students} students, tested on {x.test_students}. Retrained monthly in production.</p>
        </section>
        <section className="panel">
          <h3 className="sec">Fairness check</h3>
          <table>
            <thead><tr><th scope="col">Group</th><th scope="col">Flag rate</th><th scope="col">Recall</th></tr></thead>
            <tbody>{Object.entries(x.fairness).map(([g, v]) => <tr key={g}><td>{g === 'F' ? 'Girls' : 'Boys'}</td><td>{pct(v.flag_rate)}</td><td>{pct(v.recall)}</td></tr>)}</tbody>
          </table>
          <p className="muted small">Gender is never a model input. We check that flag rates and recall stay balanced across groups.</p>
          <h3 className="sec" style={{ marginTop: 18 }}>Safety by design</h3>
          <ul className="small" style={{ margin: 0, paddingLeft: 18, lineHeight: 1.8 }}>
            <li>Teacher approves every action and message before it is sent</li>
            <li>No names or contact details are sent to any AI model</li>
            <li>Guardrails check language, tone, length and script</li>
            <li>Template fallback if the AI is unavailable or fails a check</li>
            <li>Role-based access: teachers see only their classes</li>
          </ul>
        </section>
      </div>
    </div>
  )
}

/* ---------- app shell ---------- */
export default function App() {
  const [user, setUser] = useState(null)
  const [ready, setReady] = useState(false)
  const [tab, setTab] = useState('classes')

  useEffect(() => {
    try { if (window.speechSynthesis) window.speechSynthesis.getVoices() } catch { /* voices load lazily */ }
    const out = () => setUser(null)
    window.addEventListener('saarthi-logout', out)
    if (hasToken()) api('/me').then(setUser).catch((e) => { if (e.status === 401) setToken('') }).finally(() => setReady(true))
    else setReady(true)
    return () => window.removeEventListener('saarthi-logout', out)
  }, [])
  if (!ready) return <div className="page" role="status">Loading...</div>
  if (!user) return <Login onLogin={(u) => { setUser(u); setTab('classes') }} />

  const role = user.role
  const all = role !== 'teacher'
  const T = {
    classes: [all ? 'All classes' : 'My classes', Users, 'Risk radar', 'Students ranked by risk of falling behind'],
    weekly: ['Weekly data', ClipboardList, 'Weekly data entry', "Enter this week's attendance, homework and marks"],
    messages: ['Messages', MessageSquare, 'Messages', 'Parent messages and their delivery status'],
    overview: ['School overview', BarChart3, 'School overview', 'Risk and outcomes across every class'],
    students: ['Students', GraduationCap, 'Students', 'Add students, import a spreadsheet, and manage parent contacts'],
    users: ['Users', UserCog, 'Users and roles', 'Faculty, principal and admin accounts'],
    settings: ['Settings', SettingsIcon, 'Settings', 'WhatsApp delivery and the AI message writer'],
    audit: ['AI audit log', ScrollText, 'AI audit log', 'Everything the AI was given and produced'],
    model: ['Model and safety', ShieldCheck, 'Model and safety', 'How the risk model performs and how data is protected'],
  }
  const order = role === 'teacher' ? ['classes', 'weekly', 'messages', 'model']
    : role === 'principal' ? ['classes', 'overview', 'messages', 'audit', 'model']
    : ['classes', 'overview', 'weekly', 'messages', 'students', 'users', 'settings', 'audit', 'model']
  const cur = T[order.includes(tab) ? tab : 'classes']
  return (
    <div className="app">
      <a href="#main" className="skip">Skip to content</a>
      <DialogHost />
      <aside className="side">
        <div className="brand">SAARTHI<small>Student Success Copilot</small></div>
        <nav className="nav" aria-label="Main">
          {order.map((k) => {
            const Icon = T[k][1]
            return (
              <button key={k} className={tab === k ? 'on' : ''} aria-current={tab === k ? 'page' : undefined} onClick={() => setTab(k)}>
                <Icon size={18} aria-hidden="true" />{T[k][0]}
              </button>
            )
          })}
        </nav>
        <div className="who">
          <div className="who-row"><span className="avatar" aria-hidden="true">{initials(user.name)}</span><div><b>{user.name}</b><small>{ROLE[role]}</small></div></div>
          <button className="signout" onClick={() => { setToken(''); setUser(null) }}><LogOut size={16} aria-hidden="true" />Sign out</button>
        </div>
      </aside>
      <main className="main" id="main" tabIndex={-1}>
        <PageHead title={cur[2]} sub={cur[3]} />
        {tab === 'classes' && <Classes canEdit={role !== 'principal'} />}
        {tab === 'weekly' && <WeeklyPage />}
        {tab === 'messages' && <MessagesPage />}
        {tab === 'overview' && <Overview />}
        {tab === 'students' && <AdminStudents />}
        {tab === 'users' && <AdminUsers me={user} />}
        {tab === 'settings' && <SettingsPage />}
        {tab === 'audit' && <Audit />}
        {tab === 'model' && <ModelPage />}
      </main>
    </div>
  )
}
