"""SAARTHI API: risk radar, explainable reasons, AI action plans, parent messages, outcome tracking."""
from __future__ import annotations
import json
import re
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import actions, db, model, whatsapp
from .content import LANGS
from .datagen import SUBJECT_LABEL

TOKENS: dict[str, dict] = {}
DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init()
    model.load()
    yield


app = FastAPI(title="SAARTHI", version="1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])


# ---------- helpers ----------------------------------------------------------------
def q(sql: str, args: tuple = ()) -> list[dict]:
    con = db.connect()
    try:
        return [dict(r) for r in con.execute(sql, args).fetchall()]
    finally:
        con.close()


def run(sql: str, args: tuple = ()) -> int:
    con = db.connect()
    try:
        cur = con.execute(sql, args)
        con.commit()
        return cur.lastrowid
    finally:
        con.close()


def user_dep(authorization: str | None = Header(default=None)) -> dict:
    token = (authorization or "").removeprefix("Bearer ").strip()
    user = TOKENS.get(token)
    if not user or user["exp"] < time.time():
        TOKENS.pop(token, None)
        raise HTTPException(401, "Please sign in")
    return {**user, "token": token}


OVERSIGHT = ("principal", "admin")  # roles that see every class


def can_see(user: dict, cls: str) -> bool:
    return user["role"] in OVERSIGHT or cls in user["classes"]


def all_classes() -> list[str]:
    names = {r["cls"] for r in q("SELECT DISTINCT cls FROM students")}
    return sorted(names, key=lambda c: (int(re.sub(r"\D", "", c) or 0), c))


def my_classes(user: dict) -> list[str]:
    return all_classes() if user["role"] in OVERSIGHT else user["classes"]


def get_student(sid: int, user: dict) -> dict:
    rows = q("SELECT * FROM students WHERE id=?", (sid,))
    if not rows:
        raise HTTPException(404, "Student not found")
    if not can_see(user, rows[0]["cls"]):
        raise HTTPException(403, "This student is not in your classes")
    rows[0].pop("gender", None)  # not needed by the app, so not exposed
    return rows[0]


def get_risk(sid: int) -> dict | None:
    rows = q("SELECT * FROM risk WHERE student_id=?", (sid,))
    if not rows:
        return None  # not scored yet: fewer than 4 weeks of data
    rows[0]["reasons"] = json.loads(rows[0]["reasons"])
    return rows[0]


def plan_out(p: dict) -> dict:
    for k in ("actions", "topics", "flags"):
        p[k] = json.loads(p[k]) if p.get(k) else []
    return p


# ---------- auth -------------------------------------------------------------------
class Login(BaseModel):
    username: str
    password: str


FAILS: dict[str, list[float]] = {}
TOKEN_TTL = 8 * 3600


@app.post("/api/login")
def login(body: Login):
    name = body.username.strip().lower()
    recent = [t for t in FAILS.get(name, []) if t > time.time() - 60]
    if len(recent) >= 5:
        raise HTTPException(429, "Too many attempts. Try again in a minute.")
    rows = q("SELECT * FROM users WHERE username=?", (name,))
    if not rows or not db.check_pw(body.password, rows[0]["password"]):
        FAILS[name] = recent + [time.time()]
        raise HTTPException(401, "Wrong username or password")
    if rows[0].get("active") == 0:
        raise HTTPException(403, "This account is disabled. Please contact the school admin.")
    FAILS.pop(name, None)
    u = rows[0]
    user = {"username": u["username"], "name": u["name"], "role": u["role"], "classes": json.loads(u["classes"])}
    token = secrets.token_urlsafe(24)
    TOKENS[token] = {**user, "exp": time.time() + TOKEN_TTL}
    return {"token": token, "user": user}


@app.post("/api/logout")
def logout(user: dict = Depends(user_dep)):
    TOKENS.pop(user["token"], None)
    return {"ok": True}


@app.get("/api/me")
def me(user: dict = Depends(user_dep)):
    return {k: user[k] for k in ("username", "name", "role", "classes")}


@app.get("/api/health")
def health():
    return {"ok": True, "languages": LANGS}


# ---------- teacher: class + students ---------------------------------------------
@app.get("/api/classes")
def classes(user: dict = Depends(user_dep)):
    out = []
    for c in my_classes(user):
        rows = q("SELECT r.tier, COUNT(*) n FROM risk r JOIN students s ON s.id=r.student_id WHERE s.cls=? GROUP BY r.tier", (c,))
        t = {r["tier"]: r["n"] for r in rows}
        out.append({"cls": c, "high": t.get("high", 0), "medium": t.get("medium", 0), "low": t.get("low", 0)})
    return out


@app.get("/api/students")
def students(cls: str, user: dict = Depends(user_dep)):
    if not can_see(user, cls):
        raise HTTPException(403, "This class is not yours")
    rows = q("""SELECT s.id, s.name, s.cls, s.roll, s.parent_language, r.risk, r.tier, r.reasons,
                (SELECT status FROM plans p WHERE p.student_id=s.id ORDER BY (p.status='approved') DESC, p.id DESC LIMIT 1) plan_status
                FROM students s LEFT JOIN risk r ON r.student_id=s.id WHERE s.cls=?
                ORDER BY r.risk IS NULL, r.risk DESC, s.roll""", (cls,))
    for r in rows:
        r["reasons"] = json.loads(r["reasons"]) if r["reasons"] else []
        r["tier"] = r["tier"] or "unscored"
        r["risk"] = r["risk"] or 0.0
    return rows


@app.get("/api/students/{sid}")
def student_detail(sid: int, user: dict = Depends(user_dep)):
    s = get_student(sid, user)
    r = get_risk(sid)
    weekly = q("SELECT * FROM weekly WHERE student_id=? ORDER BY week", (sid,))
    for w in weekly:
        w["marks_avg"] = sum(w[k] for k in SUBJECT_LABEL) / len(SUBJECT_LABEL)
    plans = [plan_out(p) for p in q("SELECT * FROM plans WHERE student_id=? ORDER BY id DESC", (sid,))]
    ints = q("SELECT * FROM interventions WHERE student_id=? ORDER BY id DESC", (sid,))
    can_edit = user["role"] == "admin" or (user["role"] == "teacher" and s["cls"] in user["classes"])
    phone = s.get("parent_phone") if can_edit else whatsapp.mask(s.get("parent_phone"))  # principal sees it masked
    return {"student": {**s, "parent_phone": phone, "demo_number": whatsapp.is_demo(s.get("parent_phone"))},
            "can_edit": can_edit, "whatsapp_live": whatsapp.configured(),
            "risk": r, "weekly": weekly, "plans": plans, "interventions": ints,
            "weakest_subject_label": SUBJECT_LABEL[r["weakest_subject"]] if r else None}


# ---------- action plans -----------------------------------------------------------
class PlanReq(BaseModel):
    language: str | None = None


def _log(student: dict, res: dict, plan_id: int) -> None:
    run("INSERT INTO ai_log(ts,student_ref,provider,language,input,output,flags,plan_id) VALUES(?,?,?,?,?,?,?,?)",
        (db.now(), res["llm_input"]["student_ref"], res["provider"], res["language"], json.dumps(res["llm_input"]),
         json.dumps({"actions": res["actions"], "message": res["message"]}, ensure_ascii=False),
         json.dumps(res["flags"]), plan_id))


@app.post("/api/students/{sid}/plan")
def make_plan(sid: int, body: PlanReq, user: dict = Depends(user_dep)):
    s = get_student(sid, user)
    lang = body.language or s["parent_language"]
    if lang not in LANGS:
        raise HTTPException(400, "Unsupported language")
    r = get_risk(sid)
    if r is None:
        raise HTTPException(409, "Not scored yet: enter at least 4 weeks of data on the Weekly data page first")
    res = actions.generate_plan(s, r, lang)
    pid = run("INSERT INTO plans(student_id,created_at,provider,language,actions,topics,message,flags) VALUES(?,?,?,?,?,?,?,?)",
              (sid, db.now(), res["provider"], lang, json.dumps(res["actions"]), json.dumps(res["topics"], ensure_ascii=False),
               res["message"], json.dumps(res["flags"])))
    _log(s, res, pid)
    return plan_out(q("SELECT * FROM plans WHERE id=?", (pid,))[0])


class MsgReq(BaseModel):
    language: str


@app.post("/api/plans/{pid}/message")
def retranslate(pid: int, body: MsgReq, user: dict = Depends(user_dep)):
    plan = q("SELECT * FROM plans WHERE id=?", (pid,))
    if not plan:
        raise HTTPException(404, "Plan not found")
    s = get_student(plan[0]["student_id"], user)
    if plan[0]["status"] == "approved":
        raise HTTPException(409, "Approved plans cannot be changed")
    if body.language not in LANGS:
        raise HTTPException(400, "Unsupported language")
    res = actions.translate_message(s, get_risk(s["id"]), body.language)
    run("UPDATE plans SET message=?, language=?, flags=? WHERE id=?",
        (res["message"], body.language, json.dumps(res["flags"]), pid))
    _log(s, {**res, "actions": json.loads(plan[0]["actions"])}, pid)
    return plan_out(q("SELECT * FROM plans WHERE id=?", (pid,))[0])


class ActionIn(BaseModel):
    kind: str
    text: str = Field(min_length=1, max_length=300)


class ApproveReq(BaseModel):
    actions: list[ActionIn] = Field(min_length=1, max_length=3)
    message: str = Field(min_length=1, max_length=1500)
    language: str


@app.post("/api/plans/{pid}/approve")
def approve(pid: int, body: ApproveReq, user: dict = Depends(user_dep)):
    plan = q("SELECT * FROM plans WHERE id=?", (pid,))
    if not plan:
        raise HTTPException(404, "Plan not found")
    p = plan[0]
    s = get_student(p["student_id"], user)
    if p["status"] == "approved":
        raise HTTPException(409, "Already approved")
    if body.language not in LANGS:
        raise HTTPException(400, "Unsupported language")
    if any(a.kind not in actions.KINDS for a in body.actions):
        raise HTTPException(400, "Unknown action type")
    flags = actions.check_message(body.message, body.language)
    for a in body.actions:
        flags += [f"action:{f}" for f in actions.check_message(a.text, "en")]
    if flags:
        raise HTTPException(422, f"Blocked by safety check: {', '.join(flags)}")
    acts = [a.model_dump() for a in body.actions]
    con = db.connect()
    mid = None
    try:
        # claim the plan atomically so a double-click cannot approve (and send) twice
        cur = con.execute("UPDATE plans SET status='approved', actions=?, message=?, language=?, approved_by=?, "
                          "approved_at=? WHERE id=? AND status!='approved'",
                          (json.dumps(acts), body.message, body.language, user["name"], db.now(), pid))
        if cur.rowcount == 0:
            raise HTTPException(409, "Already approved")
        mid = con.execute(
            "INSERT INTO messages(plan_id,student_id,channel,language,body,status,ts,parent_phone,provider,sent_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (pid, s["id"], "whatsapp (simulated)", body.language, body.message, "sent", db.now(),
             s.get("parent_phone"), "simulated", db.now())).lastrowid
        for a in acts:
            con.execute("INSERT INTO interventions(student_id,plan_id,kind,text,outcome,created_at,source) "
                        "VALUES(?,?,?,?,NULL,?,?)", (s["id"], pid, a["kind"], a["text"], db.now(), "live"))
        final = json.dumps({"actions": acts, "message": body.message, "final_after_teacher_edit": True},
                           ensure_ascii=False)
        con.execute("UPDATE ai_log SET approved_by=?, output=? WHERE id=(SELECT MAX(id) FROM ai_log WHERE plan_id=?)",
                    (user["name"], final, pid))
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    from .extra import deliver_message  # imported here: extra.py registers its routes on this app
    deliver_message(mid)
    out = plan_out(q("SELECT * FROM plans WHERE id=?", (pid,))[0])
    out["message_id"] = mid
    return out


class OutcomeReq(BaseModel):
    outcome: str


@app.post("/api/interventions/{iid}/outcome")
def outcome(iid: int, body: OutcomeReq, user: dict = Depends(user_dep)):
    if body.outcome not in ("improved", "no_change", "declined"):
        raise HTTPException(400, "Invalid outcome")
    row = q("SELECT * FROM interventions WHERE id=?", (iid,))
    if not row or row[0]["student_id"] is None:
        raise HTTPException(404, "Intervention not found")
    get_student(row[0]["student_id"], user)
    run("UPDATE interventions SET outcome=? WHERE id=?", (body.outcome, iid))
    return {"ok": True}


# ---------- principal --------------------------------------------------------------
def _principal(user: dict) -> None:
    if user["role"] not in OVERSIGHT:
        raise HTTPException(403, "Principal or admin access only")


@app.get("/api/principal/overview")
def overview(user: dict = Depends(user_dep)):
    _principal(user)
    by_class = []
    for c in all_classes():
        rows = q("SELECT r.tier, COUNT(*) n FROM risk r JOIN students s ON s.id=r.student_id WHERE s.cls=? GROUP BY r.tier", (c,))
        t = {r["tier"]: r["n"] for r in rows}
        by_class.append({"cls": c, "high": t.get("high", 0), "medium": t.get("medium", 0), "low": t.get("low", 0)})
    reasons: dict[str, int] = {}
    subj: dict[str, int] = {}
    for r in q("SELECT reasons, weakest_subject, tier FROM risk WHERE tier != 'low'"):
        for x in json.loads(r["reasons"]):
            reasons[x["label"]] = reasons.get(x["label"], 0) + 1
        subj[SUBJECT_LABEL[r["weakest_subject"]]] = subj.get(SUBJECT_LABEL[r["weakest_subject"]], 0) + 1
    eff = q("""SELECT kind, COUNT(*) n, SUM(outcome='improved') improved, SUM(source='live') live FROM interventions
               WHERE outcome IS NOT NULL GROUP BY kind""")
    for e in eff:
        e["rate"] = (e["improved"] or 0) / e["n"] if e["n"] else 0
    eff.sort(key=lambda e: -e["rate"])
    stats = {
        "students": q("SELECT COUNT(*) n FROM students")[0]["n"],
        "flagged": q("SELECT COUNT(*) n FROM risk WHERE tier != 'low'")[0]["n"],
        "plans_approved": q("SELECT COUNT(*) n FROM plans WHERE status='approved'")[0]["n"],
        "messages_sent": q("SELECT COUNT(*) n FROM messages")[0]["n"],
        "outcomes_logged": q("SELECT COUNT(*) n FROM interventions WHERE outcome IS NOT NULL AND source='live'")[0]["n"],
    }
    return {"by_class": by_class, "reasons": reasons, "weak_subjects": subj, "effectiveness": eff, "stats": stats}


@app.get("/api/audit")
def audit(user: dict = Depends(user_dep)):
    _principal(user)
    rows = q("SELECT * FROM ai_log ORDER BY id DESC LIMIT 40")
    for r in rows:
        r["input"] = json.loads(r["input"])
        r["output"] = json.loads(r["output"])
        r["flags"] = json.loads(r["flags"])
    return rows


@app.get("/api/model")
def model_info(user: dict = Depends(user_dep)):
    return {**model.info(), "ai": actions.provider_info()}


# Extra API: weekly data entry, admin, messages outbox, WhatsApp. Imported BEFORE the static mount below,
# because a mount at "/" would otherwise swallow these routes.
from . import extra  # noqa: E402,F401


# ---------- static frontend (built React app) ------------------------------------
if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="web")
