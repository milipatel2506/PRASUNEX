import { Fragment, useEffect, useRef, useState } from 'react'
import { BarChart3, LogOut, RefreshCw, ScrollText, Send, ShieldCheck, Users, Volume2 } from 'lucide-react'
import { api, hasToken, setToken } from './api'

const LANG = { en: 'English', gu: 'ગુજરાતી', hi: 'हिन्दी' }
const LANG_NAME = { en: 'English', gu: 'Gujarati', hi: 'Hindi' }
const KIND = {
  parent_contact: 'Parent contact', remedial_session: 'Catch-up session', practice_test: 'Practice test',
  homework_checklist: 'Homework checklist', counselling: 'Counselling', peer_support: 'Peer support',
  progress_check: 'Progress check', goal_setting: 'Goal setting',
}
const TIER = { high: 'High', medium: 'Medium', low: 'Low' }
const TIER_BAR = { high: 'var(--danger-bar)', medium: 'var(--warn-bar)', low: 'var(--ok-bar)' }
const ACCOUNTS = [
  { u: 'hetal', name: 'Ms. Hetal Shah', note: 'Teacher, classes 9A and 9B', ini: 'HS' },
  { u: 'nikhil', name: 'Mr. Nikhil Desai', note: 'Teacher, classes 8A and 8B', ini: 'ND' },
  { u: 'rina', name: 'Ms. Rina Joshi', note: 'Teacher, class 10A', ini: 'RJ' },
  { u: 'principal', name: 'Dr. Anil Mehta', note: 'Principal, whole school view and AI audit log', ini: 'AM' },
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
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const go = async (username) => {
    if (busy) return
    setBusy(true); setErr('')
    try {
      const r = await api('/login', { method: 'POST', body: { username, password: 'demo123' } })
      setToken(r.token)
      onLogin(r.user)
    } catch (e) { setErr(e.message) }
    setBusy(false)
  }
  return (
    <div className="login">
      <aside className="login-brand">
        <div className="wordmark">SAARTHI</div>
        <div>
          <h1>Student Success Copilot</h1>
          <p>Early warning for students who are falling behind, with clear reasons, practical actions for teachers,
            and messages parents can read in their own language.</p>
        </div>
        <div className="login-foot">Team InnoTech | Prasunex Innovathon 2026</div>
      </aside>
      <main className="login-form">
        <h2>Sign in</h2>
        <p className="muted">Choose a demo account. All data in this prototype is synthetic.</p>
        {err && <div className="error" role="alert">{err}</div>}
        <ul className="accounts">
          {ACCOUNTS.map((a) => (
            <li key={a.u}>
              <button className="account" disabled={busy} onClick={() => go(a.u)}>
                <span className="avatar" aria-hidden="true">{a.ini}</span>
                <span><b>{a.name}</b><small>{a.note}</small></span>
              </button>
            </li>
          ))}
        </ul>
      </main>
    </div>
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
  useEffect(() => { load().catch((e) => setErr(e.message)) }, [sid])
  if (!d) return <div className="panel" role="status">{err || 'Loading...'}</div>

  const { student: s, risk, weekly } = d
  const approved = plan && plan.status === 'approved'

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
  const approve = () => wrap(async () => {
    await api(`/plans/${plan.id}/approve`, { method: 'POST', body: { actions: plan.actions, message: msg, language: lang } })
    await load(); onChanged()
  })
  const setOutcome = (id, outcome) => wrap(async () => { await api(`/interventions/${id}/outcome`, { method: 'POST', body: { outcome } }); await load() })
  const editAction = (i, text) => setPlan((p) => ({ ...p, actions: p.actions.map((a, j) => (j === i ? { ...a, text } : a)) }))
  const voice = () => {
    const r = speak(msg, lang)
    setVoiceNote(r === 'ok' ? '' : r === 'unsupported' ? 'Voice is not supported in this browser.' :
      `No ${LANG_NAME[lang]} voice is installed on this device. Try Chrome or Edge, or install the language voice in system settings.`)
  }
  const LangSwitch = ({ onPick, disabled }) => (
    <div className="langs" role="group" aria-label="Message language">
      {Object.keys(LANG).map((l) => (
        <button key={l} aria-pressed={lang === l} className={lang === l ? 'on' : ''} disabled={disabled} onClick={() => onPick(l)}>{LANG[l]}</button>
      ))}
    </div>
  )

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

      <section className="panel">
        <div className="plan-head">
          <h3>Action plan and parent message</h3>
          {plan && <Tag kind={plan.status}>{plan.status === 'approved' ? 'Approved and sent' : 'Draft, needs your approval'}</Tag>}
        </div>
        {err && <div className="error" role="alert" style={{ margin: '0 0 12px' }}>{err}</div>}
        {!plan && (
          <>
            <p className="muted" style={{ marginTop: 0 }}>SAARTHI drafts three practical actions and a parent message. You review and approve before anything is sent.</p>
            <div className="small muted">Message language</div>
            <LangSwitch onPick={setLang} disabled={busy} />
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
              <LangSwitch onPick={switchLang} disabled={approved || busy} />
              <div className="phone">
                <div className="bar2">Parent of {s.first_en} | WhatsApp (simulated)</div>
                <div className="bubble">{msg}<div className="tick">{approved ? '✓✓ delivered (simulated)' : 'draft'}</div></div>
              </div>
              {!approved && <textarea style={{ marginTop: 12, minHeight: 110 }} value={msg} onChange={(e) => setMsg(e.target.value)} aria-label="Edit message" />}
              <div className="row" style={{ marginTop: 12, flexWrap: 'wrap' }}>
                <button className="btn alt" onClick={voice}><Volume2 size={16} aria-hidden="true" />Play voice</button>
                {!approved && <button className="btn go" disabled={busy} onClick={approve}><Send size={16} aria-hidden="true" />Approve and send (simulated)</button>}
                {!approved && <button className="btn alt" disabled={busy} onClick={create}><RefreshCw size={16} aria-hidden="true" />Redraft</button>}
              </div>
              {voiceNote && <div className="flag">{voiceNote}</div>}
              {approved && <div className="ok">Sent by {plan.approved_by}. Sending is simulated in this prototype.</div>}
            </div>
          </div>
        )}
      </section>

      {d.interventions.length > 0 && (
        <section className="panel">
          <h3>Outcome tracker</h3>
          <p className="muted small" style={{ margin: '4px 0 8px' }}>After the follow-up period, record what happened. SAARTHI learns which actions work best.</p>
          <table>
            <thead><tr><th>Action</th><th>Type</th><th>Outcome</th></tr></thead>
            <tbody>
              {d.interventions.map((i) => (
                <tr key={i.id}>
                  <td>{i.text}</td><td>{KIND[i.kind] || i.kind}</td>
                  <td>{i.outcome ? <Tag kind={i.outcome === 'improved' ? 'approved' : i.outcome === 'declined' ? 'high' : 'medium'}>{i.outcome.replace('_', ' ')}</Tag> :
                    <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
                      <button className="btn alt" disabled={busy} onClick={() => setOutcome(i.id, 'improved')}>Improved</button>
                      <button className="btn alt" disabled={busy} onClick={() => setOutcome(i.id, 'no_change')}>No change</button>
                      <button className="btn alt" disabled={busy} onClick={() => setOutcome(i.id, 'declined')}>Declined</button>
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
function Classes() {
  const [cls, setCls] = useState([])
  const [cur, setCur] = useState(null)
  const [list, setList] = useState([])
  const [sel, setSel] = useState(null)
  const [all, setAll] = useState(false)
  const [err, setErr] = useState('')
  const curRef = useRef(null)
  curRef.current = cur

  const loadClasses = () => api('/classes').then((c) => { setCls(c); if (!curRef.current && c.length) setCur(c[0].cls) }).catch((e) => setErr(e.message))
  const loadList = () => {
    const c = cur
    if (!c) return
    api('/students?cls=' + c).then((r) => { if (curRef.current === c) setList(r) }).catch((e) => setErr(e.message))
  }
  useEffect(() => { loadClasses() }, [])
  useEffect(() => { setSel(null); loadList() }, [cur])

  const flagged = list.filter((s) => s.tier !== 'low')
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
      <div className="split">
        <div>
          <div className="list-head">
            <div><b>Students</b> <span className="muted small">{all ? `all ${list.length} students` : `${flagged.length} need attention`}</span></div>
            <button className="btn alt" onClick={() => setAll(!all)}>{all ? 'Show only flagged' : 'Show all students'}</button>
          </div>
          <div className="list">
            {shown.map((s) => (
              <button key={s.id} aria-current={sel === s.id} className={'student' + (sel === s.id ? ' on' : '')} onClick={() => setSel(s.id)}>
                <div className="l1">
                  <span className="name">{s.name}</span>
                  <span className="score"><span className="n">{pct(s.risk)}</span><Tag kind={s.tier}>{TIER[s.tier]}</Tag></span>
                </div>
                <div className="l2">
                  <span>{s.reasons.length ? s.reasons.map((r) => r.label).join(', ') : 'On track'}</span>
                  {s.plan_status && <Tag kind={s.plan_status}>{s.plan_status === 'approved' ? 'Sent' : 'Draft'}</Tag>}
                </div>
                <div className="riskbar"><i style={{ width: s.risk * 100 + '%', background: TIER_BAR[s.tier] }} /></div>
              </button>
            ))}
            {!shown.length && <div className="empty">No students flagged in this class.</div>}
          </div>
        </div>
        <div>{sel ? <StudentPanel key={sel} sid={sel} onChanged={() => { loadClasses(); loadList() }} /> :
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
      <section className="panel" style={{ padding: 0 }}>
        <table>
          <thead><tr><th>Time</th><th>Student ref</th><th>Source</th><th>Language</th><th>Safety flags</th><th>Approved by</th><th></th></tr></thead>
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
            <thead><tr><th>Group</th><th>Flag rate</th><th>Recall</th></tr></thead>
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
    if (hasToken()) api('/me').then(setUser).catch(() => setToken('')).finally(() => setReady(true))
    else setReady(true)
    return () => window.removeEventListener('saarthi-logout', out)
  }, [])
  if (!ready) return null
  if (!user) return <Login onLogin={(u) => { setUser(u); setTab('classes') }} />

  const principal = user.role === 'principal'
  const tabs = [
    ['classes', principal ? 'All classes' : 'My classes', Users, 'Risk radar', 'Students ranked by risk of falling behind'],
    ...(principal ? [['overview', 'School overview', BarChart3, 'School overview', 'Risk and outcomes across every class'],
                     ['audit', 'AI audit log', ScrollText, 'AI audit log', 'Everything the AI was given and produced']] : []),
    ['model', 'Model and safety', ShieldCheck, 'Model and safety', 'How the risk model performs and how data is protected'],
  ]
  const cur = tabs.find((t) => t[0] === tab) || tabs[0]
  return (
    <div className="app">
      <aside className="side">
        <div className="brand">SAARTHI<small>Student Success Copilot</small></div>
        <nav className="nav" aria-label="Main">
          {tabs.map(([k, label, Icon]) => (
            <button key={k} className={tab === k ? 'on' : ''} aria-current={tab === k ? 'page' : undefined} onClick={() => setTab(k)}>
              <Icon size={18} aria-hidden="true" />{label}
            </button>
          ))}
        </nav>
        <div className="who">
          <div className="who-row"><span className="avatar" aria-hidden="true">{initials(user.name)}</span><div><b>{user.name}</b><small>{principal ? 'Principal' : 'Teacher'}</small></div></div>
          <button className="signout" onClick={() => { setToken(''); setUser(null) }}><LogOut size={16} aria-hidden="true" />Sign out</button>
        </div>
      </aside>
      <div className="main">
        <PageHead title={cur[3]} sub={cur[4]} />
        {tab === 'classes' && <Classes />}
        {tab === 'overview' && <Overview />}
        {tab === 'audit' && <Audit />}
        {tab === 'model' && <ModelPage />}
      </div>
    </div>
  )
}
