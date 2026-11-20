import { useEffect, useState } from 'react'
import { api, setToken } from './api'

const LANG = { en: 'English', gu: 'ગુજરાતી', hi: 'हिन्दी' }
const KIND = {
  parent_contact: 'Parent contact', remedial_session: 'Catch-up session', practice_test: 'Practice test',
  homework_checklist: 'Homework checklist', counselling: 'Counselling', peer_support: 'Peer support',
  progress_check: 'Progress check', goal_setting: 'Goal setting',
}
const TIER_COLOR = { high: 'var(--coral)', medium: 'var(--amber)', low: 'var(--teal)' }
const pct = (x) => Math.round(x * 100) + '%'

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

/* ---------- small chart pieces ---------- */
function Spark({ label, values, fmt, color, lo, hi }) {
  const W = 200, H = 54
  const min = lo ?? Math.min(...values), max = hi ?? Math.max(...values)
  const span = max - min || 1
  const pts = values.map((v, i) => [(i / (values.length - 1)) * (W - 8) + 4, H - 6 - ((v - min) / span) * (H - 12)])
  const last = values[values.length - 1], first = values[0]
  return (
    <div className="spark">
      <small>{label}</small>
      <b>{fmt(last)} {String(fmt(last)) !== String(fmt(first)) && <small style={{ color: last < first ? 'var(--coral)' : 'var(--teal)' }}>{last < first ? '▼' : '▲'} from {fmt(first)}</small>}</b>
      <svg width={W} height={H} role="img" aria-label={label + ' trend'}>
        <polyline fill="none" stroke={color} strokeWidth="2.5" points={pts.map((p) => p.join(',')).join(' ')} />
        {pts.map((p, i) => <circle key={i} cx={p[0]} cy={p[1]} r={i === pts.length - 1 ? 4 : 2} fill={color} />)}
      </svg>
    </div>
  )
}

function HBar({ label, value, max, text, color = 'var(--blue)' }) {
  return (
    <div className="hbar">
      <span>{label}</span>
      <div className="bar"><i style={{ width: (max ? (value / max) * 100 : 0) + '%', background: color }} /></div>
      <b>{text ?? value}</b>
    </div>
  )
}

/* ---------- login ---------- */
function Login({ onLogin }) {
  const [err, setErr] = useState('')
  const go = async (username) => {
    try {
      const r = await api('/login', { method: 'POST', body: { username, password: 'demo123' } })
      setToken(r.token)
      onLogin(r.user)
    } catch (e) { setErr(e.message) }
  }
  return (
    <div className="login">
      <div className="login-hero">
        <div className="tag">PRASUNEX INNOVATHON 2026 | TEAM INNOTECH</div>
        <h1>SAARTHI</h1>
        <p>The AI Student Success Copilot. Spot struggling students weeks earlier, tell teachers exactly what to do,
          and reach every parent in their own language.</p>
      </div>
      <div className="login-box">
        <h2 className="serif">Demo sign-in</h2>
        <p className="muted">Choose a role. All data is synthetic. Teachers see only their own classes.</p>
        {err && <div className="error">{err}</div>}
        <button className="demo-btn" onClick={() => go('hetal')}><b>Ms. Hetal Shah</b><span>Teacher, classes 9A and 9B</span></button>
        <button className="demo-btn" onClick={() => go('nikhil')}><b>Mr. Nikhil Desai</b><span>Teacher, classes 8A and 8B</span></button>
        <button className="demo-btn" onClick={() => go('rina')}><b>Ms. Rina Joshi</b><span>Teacher, class 10A</span></button>
        <button className="demo-btn" onClick={() => go('principal')}><b>Dr. Anil Mehta</b><span>Principal, whole school view and AI audit log</span></button>
      </div>
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
  if (!d) return <div className="card">{err || 'Loading...'}</div>

  const { student: s, risk, weekly } = d
  const approved = plan && plan.status === 'approved'

  const wrap = async (fn) => { setBusy(true); setErr(''); try { await fn() } catch (e) { setErr(e.message) } setBusy(false) }
  const create = () => wrap(async () => {
    const p = await api(`/students/${sid}/plan`, { method: 'POST', body: { language: lang } })
    setPlan(p); setMsg(p.message)
  })
  const switchLang = (l) => { setLang(l); if (plan && !approved) wrap(async () => {
    const p = await api(`/plans/${plan.id}/message`, { method: 'POST', body: { language: l } })
    setPlan(p); setMsg(p.message)
  }) }
  const approve = () => wrap(async () => {
    const p = await api(`/plans/${plan.id}/approve`, { method: 'POST', body: { actions: plan.actions, message: msg, language: lang } })
    setPlan(p); await load(); onChanged()
  })
  const setOutcome = (id, outcome) => wrap(async () => { await api(`/interventions/${id}/outcome`, { method: 'POST', body: { outcome } }); await load() })
  const editAction = (i, text) => setPlan({ ...plan, actions: plan.actions.map((a, j) => (j === i ? { ...a, text } : a)) })
  const voice = () => {
    const r = speak(msg, lang)
    setVoiceNote(r === 'ok' ? '' : r === 'unsupported' ? 'Voice is not supported in this browser.' :
      `No ${LANG[lang]} voice is installed on this device. Try Chrome or Edge, or install the language voice in system settings.`)
  }

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <div className="card">
        <div className="hdr">
          <div>
            <h2 className="serif">{s.name}</h2>
            <div className="muted">Class {s.cls}, roll {s.roll} | Parent language: {LANG[s.parent_language]} | Weakest subject: {d.weakest_subject_label}</div>
          </div>
          <div className="gauge"><span className={'pill ' + risk.tier}>{risk.tier.toUpperCase()} RISK</span><br /><b style={{ color: TIER_COLOR[risk.tier] }}>{pct(risk.risk)}</b></div>
        </div>
        <div className="grid2">
          <div>
            <h3>Why this student is flagged</h3>
            {risk.reasons.length === 0 && <div className="muted">No significant risk drivers. On track.</div>}
            {risk.reasons.map((r) => (
              <div className="reason" key={r.key}>
                <div className="lbl"><span>{r.label}</span><span>{pct(r.impact)} of the risk</span></div>
                <div className="ev">{r.evidence}</div>
                <div className="bar"><i style={{ width: r.impact * 100 + '%' }} /></div>
              </div>
            ))}
            <div className="muted small">Reasons come from SHAP values of the risk model, grouped into plain language.</div>
          </div>
          <div style={{ display: 'grid', gap: 10 }}>
            <Spark label="Attendance" values={weekly.map((w) => w.attendance)} fmt={pct} color="var(--blue)" lo={0.5} hi={1} />
            <Spark label="Average marks" values={weekly.map((w) => w.marks_avg)} fmt={(v) => Math.round(v)} color="var(--coral)" lo={20} hi={100} />
            <Spark label="Homework on time" values={weekly.map((w) => w.homework)} fmt={pct} color="var(--teal)" lo={0} hi={1} />
          </div>
        </div>
      </div>

      <div className="card">
        <div className="hdr">
          <h3 style={{ margin: 0 }}>Action plan and parent message</h3>
          {plan && <span className={'pill ' + plan.status}>{plan.status === 'approved' ? 'APPROVED AND SENT' : 'DRAFT, NEEDS YOUR APPROVAL'}</span>}
        </div>
        {err && <div className="error" style={{ marginBottom: 10 }}>{err}</div>}
        {!plan && (
          <>
            <p className="muted">SAARTHI drafts three practical actions and a parent message. You review and approve before anything is sent.</p>
            <div className="langs">{Object.keys(LANG).map((l) => <button key={l} className={lang === l ? 'on' : ''} onClick={() => setLang(l)}>{LANG[l]}</button>)}</div>
            <button className="btn" disabled={busy} onClick={create}>{busy ? 'Drafting...' : 'Create action plan'}</button>
          </>
        )}
        {plan && (
          <div className="grid2">
            <div>
              <h3>Actions for you</h3>
              {plan.actions.map((a, i) => (
                <div className="act-row" key={i}>
                  <span className="num">{i + 1}</span>
                  <textarea className="act" rows={4} value={a.text} disabled={approved} onChange={(e) => editAction(i, e.target.value)} aria-label={`Action ${i + 1}`} />
                </div>
              ))}
              {plan.topics.length > 0 && <><div className="muted small">Topics to revisit</div><div className="topics">{plan.topics.map((t) => <span className="chip" key={t}>{t}</span>)}</div></>}
              <div className="muted small">Made by: {plan.provider === 'llm' ? 'AI language model, checked by guardrails' : 'built-in template engine'}</div>
              {plan.flags.length > 0 && <div className="flag">Safety notes: {plan.flags.join(', ')}</div>}
            </div>
            <div>
              <h3>Message to parent</h3>
              <div className="langs">{Object.keys(LANG).map((l) => <button key={l} className={lang === l ? 'on' : ''} disabled={approved || busy} onClick={() => switchLang(l)}>{LANG[l]}</button>)}</div>
              <div className="row" style={{ alignItems: 'flex-start' }}>
                <div className="phone" style={{ flex: 1 }}>
                  <div className="bar2">Parent of {s.first_en} | WhatsApp (simulated)</div>
                  <div className="bubble">{msg}<div className="tick">{approved ? '✓✓ delivered (simulated)' : 'draft'}</div></div>
                </div>
              </div>
              {!approved && <textarea style={{ marginTop: 10, minHeight: 120 }} value={msg} onChange={(e) => setMsg(e.target.value)} aria-label="Edit message" />}
              <div className="row" style={{ marginTop: 10, flexWrap: 'wrap' }}>
                <button className="btn alt" onClick={voice}>Play voice</button>
                {!approved && <button className="btn go" disabled={busy} onClick={approve}>Approve and send (simulated)</button>}
                {!approved && <button className="btn alt" disabled={busy} onClick={create}>Redraft</button>}
              </div>
              {voiceNote && <div className="flag">{voiceNote}</div>}
              {approved && <div className="ok">Sent by {plan.approved_by}. Sending is simulated in this prototype.</div>}
            </div>
          </div>
        )}
      </div>

      {d.interventions.length > 0 && (
        <div className="card">
          <h3>Outcome tracker</h3>
          <p className="muted small">After the follow-up period, record what happened. SAARTHI learns which actions work best.</p>
          <table>
            <thead><tr><th>Action</th><th>Type</th><th>Outcome</th></tr></thead>
            <tbody>
              {d.interventions.map((i) => (
                <tr key={i.id}>
                  <td>{i.text}</td><td>{KIND[i.kind] || i.kind}</td>
                  <td>{i.outcome ? <span className={'pill ' + (i.outcome === 'improved' ? 'approved' : i.outcome === 'declined' ? 'high' : 'medium')}>{i.outcome.replace('_', ' ')}</span> :
                    <div className="row" style={{ gap: 6 }}>
                      <button className="btn alt" onClick={() => setOutcome(i.id, 'improved')}>Improved</button>
                      <button className="btn alt" onClick={() => setOutcome(i.id, 'no_change')}>No change</button>
                      <button className="btn alt" onClick={() => setOutcome(i.id, 'declined')}>Declined</button>
                    </div>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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

  const loadClasses = () => api('/classes').then((c) => { setCls(c); if (!cur && c.length) setCur(c[0].cls) })
  const loadList = () => cur && api('/students?cls=' + cur).then(setList)
  useEffect(() => { loadClasses() }, [])
  useEffect(() => { setSel(null); loadList() }, [cur])

  const flagged = list.filter((s) => s.tier !== 'low')
  const shown = all ? list : flagged
  return (
    <div className="page">
      <div className="tabs">
        {cls.map((c) => (
          <button key={c.cls} className={'tab' + (cur === c.cls ? ' on' : '')} onClick={() => setCur(c.cls)}>
            <b>Class {c.cls}</b>
            <div className="counts"><span style={{ color: 'var(--coral)' }}>{c.high} high</span> · <span style={{ color: 'var(--amber)' }}>{c.medium} medium</span></div>
          </button>
        ))}
      </div>
      <div className="split">
        <div>
          <div className="toolbar">
            <div><b>Risk radar</b> <span className="muted small">{all ? `all ${list.length} students` : `${flagged.length} need attention`}</span></div>
            <button className="btn alt" onClick={() => setAll(!all)}>{all ? 'Show only flagged' : 'Show all students'}</button>
          </div>
          {shown.map((s) => (
            <button key={s.id} className={'student' + (sel === s.id ? ' on' : '')} onClick={() => setSel(s.id)}>
              <div className="top2">
                <b>{s.name}</b>
                <span>{s.plan_status && <span className={'pill ' + s.plan_status} style={{ marginRight: 6 }}>{s.plan_status === 'approved' ? 'sent' : 'draft'}</span>}
                  <span className={'pill ' + s.tier}>{s.tier} {pct(s.risk)}</span></span>
              </div>
              {s.reasons.length > 0 && <div className="why">{s.reasons.map((r) => <span className="chip" key={r.key}>{r.label}</span>)}</div>}
              <div className="riskbar"><i style={{ width: s.risk * 100 + '%', background: TIER_COLOR[s.tier] }} /></div>
            </button>
          ))}
          {!shown.length && <div className="card muted">No students flagged in this class.</div>}
        </div>
        <div>{sel ? <StudentPanel sid={sel} onChanged={() => { loadClasses(); loadList() }} /> :
          <div className="card"><h3>Select a student</h3><p className="muted">Pick someone from the risk radar to see why they were flagged, and to create an action plan.</p></div>}</div>
      </div>
    </div>
  )
}

/* ---------- principal ---------- */
function Overview() {
  const [o, setO] = useState(null)
  useEffect(() => { api('/principal/overview').then(setO) }, [])
  if (!o) return <div className="page">Loading...</div>
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
        <div className="card">
          <h3>Risk by class</h3>
          {o.by_class.map((c) => {
            const t = c.high + c.medium + c.low
            return (
              <div className="hbar" key={c.cls} style={{ gridTemplateColumns: '60px 1fr 90px' }}>
                <span>{c.cls}</span>
                <div className="stack"><i style={{ width: (c.high / t) * 100 + '%', background: 'var(--coral)' }} /><i style={{ width: (c.medium / t) * 100 + '%', background: 'var(--amber)' }} /><i style={{ width: (c.low / t) * 100 + '%', background: 'var(--teal)' }} /></div>
                <span className="muted small">{c.high} high, {c.medium} med</span>
              </div>
            )
          })}
        </div>
        <div className="card">
          <h3>What is driving risk (flagged students)</h3>
          {Object.entries(o.reasons).sort((a, b) => b[1] - a[1]).map(([k, v]) => <HBar key={k} label={k} value={v} max={rmax} color="var(--blue)" />)}
        </div>
        <div className="card">
          <h3>Weakest subjects among flagged students</h3>
          {Object.entries(o.weak_subjects).sort((a, b) => b[1] - a[1]).map(([k, v]) => <HBar key={k} label={k} value={v} max={smax} color="var(--coral)" />)}
        </div>
        <div className="card">
          <h3>Which actions work best</h3>
          <p className="muted small">Share of logged outcomes that improved. Includes seeded last-term demo history plus live outcomes.</p>
          {o.effectiveness.map((e) => <HBar key={e.kind} label={KIND[e.kind] || e.kind} value={e.rate} max={1} text={pct(e.rate) + ' (' + e.n + ')'} color="var(--green)" />)}
        </div>
      </div>
    </div>
  )
}

function Audit() {
  const [rows, setRows] = useState([])
  const [open, setOpen] = useState(null)
  useEffect(() => { api('/audit').then(setRows) }, [])
  return (
    <div className="page">
      <div className="note" style={{ marginBottom: 14 }}>Every AI output is logged with exactly what was sent to the AI and who approved it. Only an anonymous reference, grade, risk reasons and topics are ever sent. Names and contact details are never included.</div>
      <div className="card">
        <table>
          <thead><tr><th>Time</th><th>Student ref</th><th>Source</th><th>Language</th><th>Safety flags</th><th>Approved by</th><th></th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <>
                <tr key={r.id}>
                  <td>{r.ts}</td><td>{r.student_ref}</td><td>{r.provider}</td><td>{LANG[r.language]}</td>
                  <td>{r.flags.length ? r.flags.join(', ') : 'none'}</td><td>{r.approved_by || 'pending'}</td>
                  <td><button className="btn alt" onClick={() => setOpen(open === r.id ? null : r.id)}>{open === r.id ? 'Hide' : 'Inspect'}</button></td>
                </tr>
                {open === r.id && <tr key={r.id + 'x'}><td colSpan="7"><b className="small">Sent to the AI</b><pre>{JSON.stringify(r.input, null, 2)}</pre></td></tr>}
              </>
            ))}
            {!rows.length && <tr><td colSpan="7" className="muted">No AI activity yet. Create an action plan as a teacher first.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/* ---------- model & safety ---------- */
function ModelPage() {
  const [m, setM] = useState(null)
  useEffect(() => { api('/model').then(setM) }, [])
  if (!m) return <div className="page">Loading...</div>
  const x = m.metrics
  const imax = Math.max(...Object.values(m.importance))
  return (
    <div className="page">
      <div className="note" style={{ marginBottom: 14 }}>
        <b>Honest scope:</b> this prototype is trained and tested on realistic <b>synthetic</b> data. Real-school validation is the first pilot step. AI source right now: <b>{m.ai.note}</b>.
      </div>
      <div className="stats">
        <div className="stat"><b>{x.auc.toFixed(2)}</b><span>AUC (ranking quality)</span></div>
        <div className="stat"><b>{pct(x.precision_at_top20)}</b><span>precision, top 20% flagged</span></div>
        <div className="stat"><b>{pct(x.recall_at_top20)}</b><span>recall, top 20% flagged</span></div>
        <div className="stat"><b>{pct(x.rule_baseline.precision)}</b><span>precision of manual rule-of-thumb</span></div>
        <div className="stat"><b>{pct(x.rule_baseline.recall)}</b><span>recall of manual rule-of-thumb</span></div>
      </div>
      <div className="grid2">
        <div className="card">
          <h3>What the model looks at</h3>
          {Object.entries(m.importance).map(([k, v]) => <HBar key={k} label={k} value={v} max={imax} text={pct(v)} />)}
          <p className="muted small">Model: {m.model}. Trained on {x.train_students} students, tested on {x.test_students}. Retrained monthly in production.</p>
        </div>
        <div className="card">
          <h3>Fairness check</h3>
          <table>
            <thead><tr><th>Group</th><th>Flag rate</th><th>Recall</th></tr></thead>
            <tbody>{Object.entries(x.fairness).map(([g, v]) => <tr key={g}><td>{g === 'F' ? 'Girls' : 'Boys'}</td><td>{pct(v.flag_rate)}</td><td>{pct(v.recall)}</td></tr>)}</tbody>
          </table>
          <p className="muted small">Gender is never a model input. We check that flag rates and recall stay balanced across groups.</p>
          <h3 style={{ marginTop: 14 }}>Safety by design</h3>
          <ul className="small" style={{ margin: 0, paddingLeft: 18, lineHeight: 1.7 }}>
            <li>Teacher approves every action and message before it is sent</li>
            <li>No names or contact details are sent to any AI model</li>
            <li>Guardrails check language, tone, length and script</li>
            <li>Template fallback if the AI is unavailable or fails a check</li>
            <li>Role-based access: teachers see only their classes</li>
          </ul>
        </div>
      </div>
    </div>
  )
}

/* ---------- app shell ---------- */
export default function App() {
  const [user, setUser] = useState(null)
  const [ready, setReady] = useState(false)
  const [tab, setTab] = useState('classes')

  useEffect(() => { api('/me').then(setUser).catch(() => setToken('')).finally(() => setReady(true)) }, [])
  if (!ready) return null
  if (!user) return <Login onLogin={(u) => { setUser(u); setTab('classes') }} />
  const principal = user.role === 'principal'
  const tabs = [['classes', principal ? 'All classes' : 'My classes'], ...(principal ? [['overview', 'School overview'], ['audit', 'AI audit log']] : []), ['model', 'Model and safety']]
  return (
    <>
      <div className="top">
        <div className="brand">SAARTHI<small>STUDENT SUCCESS COPILOT</small></div>
        <div className="nav">{tabs.map(([k, l]) => <button key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{l}</button>)}</div>
        <div className="who">{user.name}<button onClick={() => { setToken(''); setUser(null) }}>Sign out</button></div>
      </div>
      {tab === 'classes' && <Classes />}
      {tab === 'overview' && <Overview />}
      {tab === 'audit' && <Audit />}
      {tab === 'model' && <ModelPage />}
    </>
  )
}
