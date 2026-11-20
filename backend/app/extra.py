"""Extra API: weekly data entry, admin (users, students, CSV import), messages outbox, WhatsApp delivery, settings.

Registered on the same FastAPI app as main.py (main imports this module before mounting the static site).
"""
from __future__ import annotations
import json
import re
import sqlite3
import time
from typing import Literal

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field, ValidationError

from . import actions, db, scoring, whatsapp
from .main import TOKENS, all_classes, app, can_see, can_write, q, run, user_dep

SUBJECTS = ["maths", "science", "english", "social", "language"]


# ============================ messages outbox ============================
def _parse(ts: str) -> float:
    return time.mktime(time.strptime(ts, "%Y-%m-%d %H:%M:%S"))


def _advance(rows: list[dict]) -> None:
    """Simulated delivery: a 'sent' message becomes 'delivered' after about 2 seconds, like a real phone."""
    for r in rows:
        if str(r["status"]).startswith("delivered"):
            r["status"] = "delivered"
        if r.get("provider") == "simulated" and r["status"] == "sent" and r.get("sent_at"):
            if time.time() - _parse(r["sent_at"]) >= 2:
                stamp = db.now()
                run("UPDATE messages SET status='delivered', delivered_at=? WHERE id=? AND status='sent'", (stamp, r["id"]))
                r["status"], r["delivered_at"] = "delivered", stamp


def deliver_message(mid: int | None) -> None:
    """After approval: send through real WhatsApp if configured and the parent has a real number.
    Otherwise the message stays in simulated mode (the outbox and parent-phone view still work)."""
    if mid is None:
        return
    rows = q("SELECT * FROM messages WHERE id=?", (mid,))
    if not rows:
        return
    m = rows[0]
    to = whatsapp.normalize(m["parent_phone"])
    if not whatsapp.configured() or whatsapp.is_demo(m["parent_phone"]) or not to:
        return
    res = whatsapp.send(to, m["body"])
    if res["ok"]:
        run("UPDATE messages SET provider='twilio', provider_sid=?, status=?, channel='whatsapp', sent_at=? WHERE id=?",
            (res["sid"], res["status"], db.now(), mid))
    else:
        run("UPDATE messages SET provider='twilio', status='failed', channel='whatsapp', error=? WHERE id=?",
            (res["error"], mid))


def _message(mid: int, user: dict) -> dict:
    rows = q("SELECT m.*, s.cls FROM messages m JOIN students s ON s.id=m.student_id WHERE m.id=?", (mid,))
    if not rows:
        raise HTTPException(404, "Message not found")
    if not can_see(user, rows[0]["cls"]):
        raise HTTPException(403, "This message belongs to another class")
    return rows[0]


@app.get("/api/messages")
def list_messages(user: dict = Depends(user_dep)):
    rows = q("""SELECT m.*, s.name student_name, s.cls, s.parent_name, s.first_en FROM messages m
                JOIN students s ON s.id=m.student_id ORDER BY m.id DESC LIMIT 300""")
    rows = [r for r in rows if can_see(user, r["cls"])]
    _advance(rows)
    for r in rows:
        r["demo_number"] = whatsapp.is_demo(r["parent_phone"])
        r["parent_phone"] = whatsapp.mask(r["parent_phone"])
        r["can_refresh"] = bool(r.get("provider_sid"))
        r.pop("provider_sid", None)
    return rows


@app.post("/api/messages/{mid}/read")
def mark_read(mid: int, user: dict = Depends(user_dep)):
    """Demo only: simulates the parent opening the message on their phone."""
    m = _message(mid, user)
    if not can_write(user, m["cls"]):
        raise HTTPException(403, "Read-only access")
    if m["provider"] != "simulated":
        raise HTTPException(409, "Real WhatsApp messages report their own read status. Use Refresh status.")
    stamp = db.now()
    run("UPDATE messages SET status='read', read_at=?, delivered_at=COALESCE(delivered_at, ?) WHERE id=?", (stamp, stamp, mid))
    return {"ok": True, "status": "read"}


@app.post("/api/messages/{mid}/refresh")
def refresh_status(mid: int, user: dict = Depends(user_dep)):
    m = _message(mid, user)
    if not m.get("provider_sid"):
        raise HTTPException(409, "This message was not sent through real WhatsApp")
    res = whatsapp.fetch_status(m["provider_sid"])
    if not res["ok"]:
        raise HTTPException(502, res["error"] or "Could not reach the WhatsApp service")
    stamps = {"delivered": ("delivered_at", db.now()), "read": ("read_at", db.now())}
    run("UPDATE messages SET status=?, error=? WHERE id=?", (res["status"], res["error"], mid))
    if res["status"] in stamps:
        col, val = stamps[res["status"]]
        run(f"UPDATE messages SET {col}=COALESCE({col}, ?) WHERE id=?", (val, mid))
    return {"ok": True, "status": res["status"]}


# ============================ weekly data entry ============================
def _entry_check(user: dict, cls: str) -> None:
    if user["role"] == "principal":
        raise HTTPException(403, "Principals have read-only access")
    if not can_see(user, cls):
        raise HTTPException(403, "This class is not yours")


from .datagen import SUBJECT_LABEL as CORE  # one set of subject names everywhere
SUBJECT_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 &\-]{1,28}$")
MAX_EXTRA = 12


def _extra_subjects(cls: str) -> list[str]:
    return [r["name"] for r in q("SELECT name FROM class_subjects WHERE cls=? ORDER BY name", (cls,))]


@app.get("/api/subjects")
def list_subjects(cls: str, user: dict = Depends(user_dep)):
    if not can_see(user, cls):
        raise HTTPException(403, "This class is not yours")
    return {"core": [{"key": k, "label": v} for k, v in CORE.items()], "extra": _extra_subjects(cls),
            "can_edit": can_write(user, cls)}


class SubjectIn(BaseModel):
    cls: str = Field(pattern=r"^[0-9]{1,2}[A-Z]$")
    name: str = Field(min_length=2, max_length=30)


@app.post("/api/subjects")
def add_subject(body: SubjectIn, user: dict = Depends(user_dep)):
    _writer(user, body.cls)
    name = " ".join(body.name.split())
    if not SUBJECT_NAME_RE.match(name):
        raise HTTPException(422, "Use letters, numbers, spaces, & or - (2 to 29 characters), starting with a letter.")
    taken = {v.lower() for v in CORE.values()} | set(CORE) | {n.lower() for n in _extra_subjects(body.cls)}
    if name.lower() in taken:
        raise HTTPException(409, f"{name} is already a subject for class {body.cls}")
    if len(_extra_subjects(body.cls)) >= MAX_EXTRA:
        raise HTTPException(409, f"A class can have at most {MAX_EXTRA} extra subjects")
    run("INSERT INTO class_subjects(cls,name) VALUES(?,?)", (body.cls, name))
    run("INSERT INTO activity(ts,actor,action,detail) VALUES(?,?,?,?)", (db.now(), user["name"], "subject_added", f"{name} (class {body.cls})"))
    return {"ok": True, "name": name}


@app.delete("/api/subjects")
def remove_subject(cls: str, name: str, user: dict = Depends(user_dep)):
    """Removes a faculty-added subject from a class together with its recorded marks. Built-in subjects cannot be removed."""
    _writer(user, cls)
    if name not in _extra_subjects(cls):
        raise HTTPException(404, "Subject not found")
    con = db.connect()
    try:
        con.execute("DELETE FROM weekly_extra WHERE subject=? AND student_id IN (SELECT id FROM students WHERE cls=?)", (name, cls))
        con.execute("DELETE FROM class_subjects WHERE cls=? AND name=?", (cls, name))
        ids = [r["id"] for r in con.execute("SELECT id FROM students WHERE cls=?", (cls,)).fetchall()]
        for sid in ids:  # the score no longer includes the removed subject
            scoring.rescore(con, sid)
        con.execute("INSERT INTO activity(ts,actor,action,detail) VALUES(?,?,?,?)", (db.now(), user["name"], "subject_removed", f"{name} (class {cls})"))
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    return {"ok": True}


@app.get("/api/weekly")
def weekly_form(cls: str, user: dict = Depends(user_dep)):
    _entry_check(user, cls)
    students = q("SELECT id, name, roll FROM students WHERE cls=? ORDER BY roll", (cls,))
    extra_names = _extra_subjects(cls)
    for s in students:
        last = q("SELECT * FROM weekly WHERE student_id=? ORDER BY week DESC LIMIT 1", (s["id"],))
        base = last[0] if last else {"week": 0, "attendance": 0.9, "homework": 0.8, "incidents": 0,
                                     **{k: 60.0 for k in SUBJECTS}}
        s["next_week"] = base["week"] + 1
        s["last"] = {k: base[k] for k in ("attendance", "homework", "incidents", *SUBJECTS)}
        prev = {r["subject"]: r["marks"] for r in q("SELECT subject, marks FROM weekly_extra WHERE student_id=? AND week=?",
                                                    (s["id"], base["week"]))} if last else {}
        s["last_extra"] = {n: prev.get(n, 60.0) for n in extra_names}
        s["weeks_recorded"] = base["week"]
    return students


class WeekRow(BaseModel):
    student_id: int
    week: int | None = Field(default=None, ge=1, le=60)  # the week the form showed; stops a double submit adding two weeks
    attendance: float = Field(ge=0, le=1)
    homework: float = Field(ge=0, le=1)
    incidents: int = Field(ge=0, le=20)
    maths: float = Field(ge=0, le=100)
    science: float = Field(ge=0, le=100)
    english: float = Field(ge=0, le=100)
    social: float = Field(ge=0, le=100)
    language: float = Field(ge=0, le=100)
    extra: dict[str, float] = Field(default_factory=dict, max_length=MAX_EXTRA)  # marks for faculty-added subjects


class WeekReq(BaseModel):
    cls: str
    rows: list[WeekRow] = Field(min_length=1, max_length=80)


@app.post("/api/weekly")
def save_weekly(body: WeekReq, user: dict = Depends(user_dep)):
    _entry_check(user, body.cls)
    ids = {r["id"] for r in q("SELECT id FROM students WHERE cls=?", (body.cls,))}
    if len({r.student_id for r in body.rows}) != len(body.rows):
        raise HTTPException(400, "Each student can appear only once")
    if any(r.student_id not in ids for r in body.rows):
        raise HTTPException(400, f"Some students are not in class {body.cls}")
    known = set(_extra_subjects(body.cls))
    for r in body.rows:
        if set(r.extra) - known:
            raise HTTPException(400, f"Unknown subject: {', '.join(sorted(set(r.extra) - known))}")
        if any(not 0 <= v <= 100 for v in r.extra.values()):
            raise HTTPException(422, "Marks must be between 0 and 100")
    con = db.connect()
    saved = scored = 0
    try:
        for r in body.rows:
            wk = (con.execute("SELECT MAX(week) FROM weekly WHERE student_id=?", (r.student_id,)).fetchone()[0] or 0) + 1
            if r.week is not None and r.week != wk:
                raise HTTPException(409, "This week was already saved (or the data changed). Reload the page to see the latest week.")
            con.execute("INSERT INTO weekly(student_id,week,attendance,homework,incidents,maths,science,english,social,language) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (r.student_id, wk, r.attendance, r.homework, r.incidents, r.maths, r.science, r.english, r.social, r.language))
            for name, marks in r.extra.items():
                con.execute("INSERT INTO weekly_extra(student_id,week,subject,marks) VALUES(?,?,?,?)", (r.student_id, wk, name, marks))
            saved += 1
            scored += 1 if scoring.rescore(con, r.student_id) else 0
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    return {"saved": saved, "scored": scored}


@app.get("/api/weekly/history")
def weekly_history(cls: str, user: dict = Depends(user_dep)):
    """Every recorded week for a class: one block per student, keyed by week number. Read-only, so principals may view it."""
    if not can_see(user, cls):
        raise HTTPException(403, "This class is not yours")
    students = q("SELECT id, name, roll FROM students WHERE cls=? ORDER BY roll", (cls,))
    weeks: set[int] = set()
    by_id = {s["id"]: s for s in students}
    for s in students:
        s["weeks"] = {}
    for w in q("SELECT w.* FROM weekly w JOIN students s ON s.id=w.student_id WHERE s.cls=? ORDER BY w.week", (cls,)):
        weeks.add(w["week"])
        marks = {k: w[k] for k in CORE}
        by_id[w["student_id"]]["weeks"][w["week"]] = {"attendance": w["attendance"], "homework": w["homework"],
                                                       "incidents": w["incidents"], "marks": marks}
    for e in q("SELECT e.* FROM weekly_extra e JOIN students s ON s.id=e.student_id WHERE s.cls=?", (cls,)):
        cell = by_id[e["student_id"]]["weeks"].get(e["week"])
        if cell is not None:
            cell["marks"][e["subject"]] = e["marks"]
    return {"core": [{"key": k, "label": v} for k, v in CORE.items()], "extra": _extra_subjects(cls),
            "weeks": sorted(weeks), "students": students}


# ============================ admin ============================
def _admin(user: dict) -> None:
    if user["role"] != "admin":
        raise HTTPException(403, "Admin access only")


def _check_classes(classes: list[str]) -> None:
    known = set(all_classes())
    bad = [c for c in classes if c not in known]
    if bad:
        raise HTTPException(400, f"Unknown class: {', '.join(bad)}")


class UserIn(BaseModel):
    username: str = Field(pattern=r"^[a-z0-9_.]{3,30}$")
    password: str = Field(min_length=8, max_length=100)
    name: str = Field(min_length=2, max_length=80)
    role: Literal["teacher", "principal", "admin"]
    classes: list[str] = []


class UserPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    classes: list[str] | None = None
    active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=100)


@app.get("/api/admin/users")
def admin_users(user: dict = Depends(user_dep)):
    _admin(user)
    rows = q("SELECT id, username, name, role, classes, active FROM users ORDER BY id")
    for r in rows:
        r["classes"] = json.loads(r["classes"] or "[]")
        r["active"] = r["active"] != 0
    return rows


@app.post("/api/admin/users")
def admin_create_user(body: UserIn, user: dict = Depends(user_dep)):
    _admin(user)
    _check_classes(body.classes)
    try:
        uid = run("INSERT INTO users(username,password,name,role,classes,active) VALUES(?,?,?,?,?,1)",
                  (body.username, db.hash_pw(body.password), body.name, body.role, json.dumps(body.classes)))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "That username is already taken")
    return {"id": uid}


@app.patch("/api/admin/users/{uid}")
def admin_update_user(uid: int, body: UserPatch, user: dict = Depends(user_dep)):
    _admin(user)
    rows = q("SELECT * FROM users WHERE id=?", (uid,))
    if not rows:
        raise HTTPException(404, "User not found")
    target = rows[0]
    if body.active is False and target["username"] == user["username"]:
        raise HTTPException(400, "You cannot disable your own account")
    if body.classes is not None:
        _check_classes(body.classes)
        run("UPDATE users SET classes=? WHERE id=?", (json.dumps(body.classes), uid))
    if body.name:
        run("UPDATE users SET name=? WHERE id=?", (body.name, uid))
    if body.password:
        run("UPDATE users SET password=? WHERE id=?", (db.hash_pw(body.password), uid))
    if body.active is not None:
        run("UPDATE users SET active=? WHERE id=?", (1 if body.active else 0, uid))
        if not body.active:  # sign them out everywhere
            for t in [t for t, u in TOKENS.items() if u["username"] == target["username"]]:
                TOKENS.pop(t, None)
    return {"ok": True}


class StudentIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    cls: str = Field(pattern=r"^[0-9]{1,2}[A-Z]$")
    roll: int = Field(ge=1, le=99)
    parent_language: Literal["en", "gu", "hi"] = "en"
    parent_name: str = Field(default="", max_length=80)
    parent_phone: str = Field(default="", max_length=25)
    first_gu: str = Field(default="", max_length=40)
    first_hi: str = Field(default="", max_length=40)


class StudentPatch(BaseModel):
    parent_name: str | None = Field(default=None, max_length=80)
    parent_phone: str | None = Field(default=None, max_length=25)
    parent_language: Literal["en", "gu", "hi"] | None = None


def _check_phone(p: str | None) -> None:
    if p and not whatsapp.normalize(p):
        raise HTTPException(422, "Phone number looks invalid. Use +91 followed by 10 digits.")


def _add_student(s: StudentIn) -> int:
    _check_phone(s.parent_phone)
    if q("SELECT 1 FROM students WHERE cls=? AND roll=?", (s.cls, s.roll)):
        raise HTTPException(409, f"Class {s.cls} already has roll number {s.roll}")
    first = s.name.split()[0]
    sid = run("INSERT INTO students(name,first_en,first_gu,first_hi,cls,roll,gender,parent_language,parent_name,parent_phone) "
              "VALUES(?,?,?,?,?,?,?,?,?,?)",
              (s.name, first, s.first_gu or first, s.first_hi or first, s.cls, s.roll, "", s.parent_language,
               s.parent_name or f"Parent of {first}", whatsapp.normalize(s.parent_phone) or "pending"))
    if q("SELECT parent_phone FROM students WHERE id=?", (sid,))[0]["parent_phone"] == "pending":
        run("UPDATE students SET parent_phone=? WHERE id=?", (f"+91 00000 {sid:05d}", sid))
    return sid


def _writer(user: dict, cls: str) -> None:
    """Faculty can change students in their own classes, admin in every class. Principal is read-only."""
    if user["role"] == "admin":
        return
    if user["role"] != "teacher" or cls not in user["classes"]:
        raise HTTPException(403, "You can only change students in your own classes")


class ContactPatch(BaseModel):
    parent_name: str | None = Field(default=None, max_length=80)
    parent_phone: str | None = Field(default=None, max_length=25)
    parent_language: Literal["en", "gu", "hi"] | None = None


@app.post("/api/students")
def add_student(body: StudentIn, user: dict = Depends(user_dep)):
    _writer(user, body.cls)
    sid = _add_student(body)
    run("INSERT INTO activity(ts,actor,action,detail) VALUES(?,?,?,?)",
        (db.now(), user["name"], "student_added", f"{body.name} (class {body.cls}, id {sid})"))
    return {"id": sid}


@app.patch("/api/students/{sid}/contact")
def update_contact(sid: int, body: ContactPatch, user: dict = Depends(user_dep)):
    rows = q("SELECT cls FROM students WHERE id=?", (sid,))
    if not rows:
        raise HTTPException(404, "Student not found")
    _writer(user, rows[0]["cls"])
    _check_phone(body.parent_phone)
    if body.parent_phone and body.parent_phone.strip():
        old = q("SELECT parent_phone FROM students WHERE id=?", (sid,))[0]["parent_phone"]
        run("INSERT INTO activity(ts,actor,action,detail) VALUES(?,?,?,?)",
            (db.now(), user["name"], "parent_phone_changed",
             f"student {sid}: {whatsapp.mask(old)} -> {whatsapp.mask(whatsapp.normalize(body.parent_phone))}"))
    if body.parent_name is not None:
        run("UPDATE students SET parent_name=? WHERE id=?", (body.parent_name.strip(), sid))
    if body.parent_phone is not None and body.parent_phone.strip():
        run("UPDATE students SET parent_phone=? WHERE id=?", (whatsapp.normalize(body.parent_phone), sid))
    if body.parent_language:
        run("UPDATE students SET parent_language=? WHERE id=?", (body.parent_language, sid))
    return {"ok": True}


@app.delete("/api/students/{sid}")
def remove_student(sid: int, user: dict = Depends(user_dep)):
    """Permanently removes a student and all of their records (weekly data, risk, plans, messages)."""
    rows = q("SELECT cls, name FROM students WHERE id=?", (sid,))
    if not rows:
        raise HTTPException(404, "Student not found")
    _writer(user, rows[0]["cls"])
    con = db.connect()
    try:  # one transaction: either everything is removed or nothing is
        con.execute("DELETE FROM ai_log WHERE plan_id IN (SELECT id FROM plans WHERE student_id=?)", (sid,))
        for t in ("weekly", "weekly_extra", "risk", "plans", "interventions", "messages"):
            con.execute(f"DELETE FROM {t} WHERE student_id=?", (sid,))
        con.execute("DELETE FROM students WHERE id=?", (sid,))
        con.execute("INSERT INTO activity(ts,actor,action,detail) VALUES(?,?,?,?)",
                    (db.now(), user["name"], "student_removed", f"{rows[0]['name']} (class {rows[0]['cls']}, id {sid})"))
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    return {"ok": True}


@app.get("/api/admin/students")
def admin_students(user: dict = Depends(user_dep)):
    _admin(user)
    rows = q("""SELECT s.id, s.name, s.cls, s.roll, s.parent_language, s.parent_name, s.parent_phone,
                (SELECT COUNT(*) FROM weekly w WHERE w.student_id=s.id) weeks,
                (SELECT tier FROM risk r WHERE r.student_id=s.id) tier FROM students s ORDER BY s.cls, s.roll""")
    for r in rows:
        r["demo_number"] = whatsapp.is_demo(r["parent_phone"])
        r["tier"] = r["tier"] or "unscored"
    return rows


@app.post("/api/admin/students")
def admin_add_student(body: StudentIn, user: dict = Depends(user_dep)):
    _admin(user)
    return {"id": _add_student(body)}


@app.patch("/api/admin/students/{sid}")
def admin_update_student(sid: int, body: StudentPatch, user: dict = Depends(user_dep)):
    _admin(user)
    if not q("SELECT 1 FROM students WHERE id=?", (sid,)):
        raise HTTPException(404, "Student not found")
    _check_phone(body.parent_phone)
    if body.parent_name is not None:
        run("UPDATE students SET parent_name=? WHERE id=?", (body.parent_name, sid))
    if body.parent_phone:
        run("UPDATE students SET parent_phone=? WHERE id=?", (whatsapp.normalize(body.parent_phone), sid))
    if body.parent_language:
        run("UPDATE students SET parent_language=? WHERE id=?", (body.parent_language, sid))
    return {"ok": True}


class ImportReq(BaseModel):
    rows: list[dict] = Field(min_length=1, max_length=300)


@app.post("/api/admin/students/import")
def admin_import_students(body: ImportReq, user: dict = Depends(user_dep)):
    """Bulk add students from a spreadsheet (the browser parses the CSV and posts the rows)."""
    _admin(user)
    added, errors = 0, []
    for i, raw in enumerate(body.rows, start=1):
        try:
            _add_student(StudentIn.model_validate({k: ("" if v is None else v) for k, v in raw.items()}))
            added += 1
        except ValidationError as e:
            errors.append({"row": i, "error": "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())})
        except HTTPException as e:
            errors.append({"row": i, "error": str(e.detail)})
    return {"added": added, "errors": errors}


@app.get("/api/admin/settings")
def admin_settings(user: dict = Depends(user_dep)):
    _admin(user)
    return {"whatsapp": whatsapp.status(), "ai": actions.provider_info()}
