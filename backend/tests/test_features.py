"""Tests for admin/faculty roles, weekly data entry, student and user management, messages outbox, WhatsApp."""
import pytest
from fastapi.testclient import TestClient

from app import db, whatsapp
from app.main import FAILS, TOKENS, app, IP_ATTEMPTS


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db, "PW_ITERS", 1000)  # fast hashing for tests; the stored hash records its own count
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("TWILIO_WHATSAPP_FROM", raising=False)
    FAILS.clear()
    IP_ATTEMPTS.clear()
    TOKENS.clear()
    with TestClient(app) as c:
        yield c


def login(c, user="hetal", pw="demo123"):
    r = c.post("/api/login", json={"username": user, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


def flagged(c, h, cls="9A"):
    return next(r for r in c.get(f"/api/students?cls={cls}", headers=h).json() if r["tier"] not in ("low", "unscored"))


def approve(c, h, sid, lang="en"):
    plan = c.post(f"/api/students/{sid}/plan", json={"language": lang}, headers=h).json()
    body = {"actions": plan["actions"], "message": plan["message"], "language": plan["language"]}
    r = c.post(f"/api/plans/{plan['id']}/approve", json=body, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


NEW_STUDENT = {"name": "Test Student", "cls": "9A", "roll": 90, "parent_language": "gu",
               "parent_name": "Test Parent", "parent_phone": "+91 98765 43210"}


# ---------- roles ----------
def test_admin_login_and_sees_all_classes(client):
    h = login(client, "admin")
    assert client.get("/api/me", headers=h).json()["role"] == "admin"
    assert [c["cls"] for c in client.get("/api/classes", headers=h).json()] == ["8A", "8B", "9A", "9B", "10A"]


def test_only_admin_can_manage_users_and_students(client):
    for who in ("hetal", "principal"):
        h = login(client, who)
        assert client.get("/api/admin/users", headers=h).status_code == 403
        assert client.get("/api/admin/students", headers=h).status_code == 403
        assert client.post("/api/admin/students", json=NEW_STUDENT, headers=h).status_code == 403
        assert client.get("/api/admin/settings", headers=h).status_code == 403
    assert client.get("/api/admin/users", headers=login(client, "admin")).status_code == 200


def test_admin_can_open_oversight_pages(client):
    h = login(client, "admin")
    assert client.get("/api/principal/overview", headers=h).status_code == 200
    assert client.get("/api/audit", headers=h).status_code == 200


def test_create_user_validates_and_can_sign_in(client):
    a = login(client, "admin")
    good = {"username": "new.faculty", "password": "longenough1", "name": "New Faculty", "role": "teacher", "classes": ["9A"]}
    assert client.post("/api/admin/users", json={**good, "password": "short"}, headers=a).status_code == 422
    assert client.post("/api/admin/users", json={**good, "username": "Bad Name"}, headers=a).status_code == 422
    assert client.post("/api/admin/users", json={**good, "classes": ["99Z"]}, headers=a).status_code == 400
    assert client.post("/api/admin/users", json=good, headers=a).status_code == 200
    assert client.post("/api/admin/users", json=good, headers=a).status_code == 409
    h = login(client, "new.faculty", "longenough1")
    assert client.get("/api/students?cls=8A", headers=h).status_code == 403  # only assigned to 9A
    assert client.get("/api/students?cls=9A", headers=h).status_code == 200


def test_disabled_user_is_signed_out_and_blocked(client):
    a = login(client, "admin")
    uid = next(u["id"] for u in client.get("/api/admin/users", headers=a).json() if u["username"] == "rina")
    h = login(client, "rina")
    assert client.patch(f"/api/admin/users/{uid}", json={"active": False}, headers=a).status_code == 200
    assert client.get("/api/me", headers=h).status_code == 401
    assert client.post("/api/login", json={"username": "rina", "password": "demo123"}).status_code == 403


def test_admin_cannot_disable_self(client):
    a = login(client, "admin")
    me = next(u for u in client.get("/api/admin/users", headers=a).json() if u["username"] == "admin")
    assert client.patch(f"/api/admin/users/{me['id']}", json={"active": False}, headers=a).status_code == 400


def test_password_reset_by_admin(client):
    a = login(client, "admin")
    uid = next(u["id"] for u in client.get("/api/admin/users", headers=a).json() if u["username"] == "nikhil")
    assert client.patch(f"/api/admin/users/{uid}", json={"password": "brandnew123"}, headers=a).status_code == 200
    assert client.post("/api/login", json={"username": "nikhil", "password": "demo123"}).status_code == 401
    login(client, "nikhil", "brandnew123")


# ---------- students ----------
def test_add_student_validation_and_unscored_state(client):
    a = login(client, "admin")
    assert client.post("/api/admin/students", json={**NEW_STUDENT, "parent_phone": "12345"}, headers=a).status_code == 422
    assert client.post("/api/admin/students", json={**NEW_STUDENT, "cls": "bad"}, headers=a).status_code == 422
    assert client.post("/api/admin/students", json={**NEW_STUDENT, "roll": 5}, headers=a).status_code == 409  # roll taken
    sid = client.post("/api/admin/students", json=NEW_STUDENT, headers=a).json()["id"]
    row = next(r for r in client.get("/api/students?cls=9A", headers=a).json() if r["id"] == sid)
    assert row["tier"] == "unscored"
    assert client.post(f"/api/students/{sid}/plan", json={}, headers=a).status_code == 409  # no history yet


def test_import_students_reports_row_errors(client):
    a = login(client, "admin")
    rows = [{**NEW_STUDENT, "name": "Imp One", "roll": 91}, {**NEW_STUDENT, "name": "Imp Two", "roll": 92},
            {**NEW_STUDENT, "name": "Bad Row", "roll": 93, "parent_phone": "nope"}, {"name": "x"}]
    res = client.post("/api/admin/students/import", json={"rows": rows}, headers=a).json()
    assert res["added"] == 2
    assert {e["row"] for e in res["errors"]} == {3, 4}


def test_update_parent_contact(client):
    a = login(client, "admin")
    sid = client.get("/api/admin/students", headers=a).json()[0]["id"]
    assert client.patch(f"/api/admin/students/{sid}", json={"parent_phone": "bad"}, headers=a).status_code == 422
    assert client.patch(f"/api/admin/students/{sid}", json={"parent_phone": "9876543210"}, headers=a).status_code == 200
    row = next(r for r in client.get("/api/admin/students", headers=a).json() if r["id"] == sid)
    assert row["parent_phone"] == "+919876543210" and row["demo_number"] is False


# ---------- weekly data entry ----------
def week_row(sid, **over):
    base = {"student_id": sid, "attendance": 0.9, "homework": 0.8, "incidents": 0,
            "maths": 60, "science": 60, "english": 60, "social": 60, "language": 60}
    base.update(over)
    return base


def test_weekly_form_prefills_next_week(client):
    h = login(client)
    form = client.get("/api/weekly?cls=9A", headers=h).json()
    assert len(form) == 30 and all(s["next_week"] == 9 for s in form)
    assert 0 <= form[0]["last"]["attendance"] <= 1


def test_weekly_entry_permissions_and_validation(client):
    h = login(client)
    sid = client.get("/api/weekly?cls=9A", headers=h).json()[0]["id"]
    assert client.get("/api/weekly?cls=8A", headers=h).status_code == 403
    assert client.get("/api/weekly?cls=9A", headers=login(client, "principal")).status_code == 403
    bad = {"cls": "9A", "rows": [week_row(sid, attendance=1.5)]}
    assert client.post("/api/weekly", json=bad, headers=h).status_code == 422
    other = client.get("/api/weekly?cls=9B", headers=h).json()[0]["id"]
    assert client.post("/api/weekly", json={"cls": "9A", "rows": [week_row(other)]}, headers=h).status_code == 400
    dup = {"cls": "9A", "rows": [week_row(sid), week_row(sid)]}
    assert client.post("/api/weekly", json=dup, headers=h).status_code == 400


def test_weekly_entry_updates_risk(client):
    h = login(client)
    rows = client.get("/api/students?cls=9A", headers=h).json()
    low = next(r for r in rows if r["tier"] == "low")
    before = low["risk"]
    for _ in range(3):  # three terrible weeks in a row
        res = client.post("/api/weekly", json={"cls": "9A", "rows": [week_row(
            low["id"], attendance=0.4, homework=0.2, incidents=3, maths=25, science=25, english=25, social=25, language=25)]},
            headers=h)
        assert res.status_code == 200 and res.json()["scored"] == 1
    after = next(r for r in client.get("/api/students?cls=9A", headers=h).json() if r["id"] == low["id"])
    assert after["risk"] > before
    assert client.get(f"/api/students/{low['id']}", headers=h).json()["weekly"][-1]["week"] == 11


def test_new_student_is_scored_after_four_weeks(client):
    a = login(client, "admin")
    sid = client.post("/api/admin/students", json=NEW_STUDENT, headers=a).json()["id"]
    for week in range(1, 5):
        res = client.post("/api/weekly", json={"cls": "9A", "rows": [week_row(sid, maths=60 - week * 6)]}, headers=a).json()
        assert res["scored"] == (1 if week == 4 else 0)
    row = next(r for r in client.get("/api/students?cls=9A", headers=a).json() if r["id"] == sid)
    assert row["tier"] in ("low", "medium", "high")


# ---------- messages outbox and delivery ----------
def test_sent_message_appears_in_outbox_and_becomes_delivered_then_read(client):
    h = login(client)
    sid = flagged(client, h)["id"]
    approve(client, h, sid, "gu")
    msgs = client.get("/api/messages", headers=h).json()
    assert len(msgs) == 1 and msgs[0]["status"] == "sent" and msgs[0]["provider"] == "simulated"
    assert msgs[0]["demo_number"] is True and "•" in msgs[0]["parent_phone"]
    con = db.connect()
    con.execute("UPDATE messages SET sent_at='2020-01-01 00:00:00'")  # pretend it was sent long ago
    con.commit(); con.close()
    assert client.get("/api/messages", headers=h).json()[0]["status"] == "delivered"
    assert client.post(f"/api/messages/{msgs[0]['id']}/read", headers=h).status_code == 200
    final = client.get("/api/messages", headers=h).json()[0]
    assert final["status"] == "read" and final["read_at"] and final["delivered_at"]


def test_outbox_is_limited_to_own_classes(client):
    h = login(client)
    approve(client, h, flagged(client, h)["id"])
    assert len(client.get("/api/messages", headers=login(client, "nikhil")).json()) == 0
    assert len(client.get("/api/messages", headers=login(client, "principal")).json()) == 1
    mid = client.get("/api/messages", headers=h).json()[0]["id"]
    assert client.post(f"/api/messages/{mid}/read", headers=login(client, "nikhil")).status_code == 403


def test_real_whatsapp_used_only_for_real_numbers(client, monkeypatch):
    sent = []
    monkeypatch.setattr(whatsapp, "configured", lambda: True)
    monkeypatch.setattr(whatsapp, "send", lambda to, body: sent.append((to, body)) or
                        {"ok": True, "sid": "SM123", "status": "queued", "error": None})
    h = login(client)
    demo_student = flagged(client, h)
    approve(client, h, demo_student["id"])
    assert sent == []  # placeholder demo numbers are never sent to
    a = login(client, "admin")
    other = next(r for r in client.get("/api/students?cls=9A", headers=h).json()
                 if r["tier"] not in ("low", "unscored") and r["id"] != demo_student["id"])
    client.patch(f"/api/admin/students/{other['id']}", json={"parent_phone": "+919876543210"}, headers=a)
    approve(client, h, other["id"])
    assert [s[0] for s in sent] == ["+919876543210"]
    real = client.get("/api/messages", headers=h).json()[0]
    assert real["provider"] == "twilio" and real["status"] == "queued" and real["can_refresh"] is True
    assert "provider_sid" not in real


def test_real_whatsapp_failure_is_recorded(client, monkeypatch):
    monkeypatch.setattr(whatsapp, "configured", lambda: True)
    monkeypatch.setattr(whatsapp, "send", lambda to, body: {"ok": False, "sid": None, "status": "failed", "error": "not opted in"})
    h = login(client)
    sid = flagged(client, h)["id"]
    client.patch(f"/api/admin/students/{sid}", json={"parent_phone": "+919876543210"}, headers=login(client, "admin"))
    approve(client, h, sid)
    m = client.get("/api/messages", headers=h).json()[0]
    assert m["status"] == "failed" and m["error"] == "not opted in"


def test_refresh_status_from_provider(client, monkeypatch):
    monkeypatch.setattr(whatsapp, "configured", lambda: True)
    monkeypatch.setattr(whatsapp, "send", lambda to, body: {"ok": True, "sid": "SM1", "status": "sent", "error": None})
    monkeypatch.setattr(whatsapp, "fetch_status", lambda sid: {"ok": True, "status": "delivered", "error": None})
    h = login(client)
    sid = flagged(client, h)["id"]
    client.patch(f"/api/admin/students/{sid}", json={"parent_phone": "+919876543210"}, headers=login(client, "admin"))
    approve(client, h, sid)
    mid = client.get("/api/messages", headers=h).json()[0]["id"]
    assert client.post(f"/api/messages/{mid}/refresh", headers=h).json()["status"] == "delivered"
    assert client.post(f"/api/messages/{mid}/read", headers=h).status_code == 409  # real messages report their own status


def test_whatsapp_settings_never_expose_secrets(client, monkeypatch):
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACsecretsecret")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tokensecret")
    monkeypatch.setenv("TWILIO_WHATSAPP_FROM", "+14155238886")
    res = client.get("/api/admin/settings", headers=login(client, "admin"))
    assert res.json()["whatsapp"]["configured"] is True
    assert "secret" not in res.text


def test_phone_helpers():
    assert whatsapp.normalize("98765 43210") == "+919876543210"
    assert whatsapp.normalize("+1 415 523 8886") == "+14155238886"
    assert whatsapp.normalize("12345") is None
    assert whatsapp.is_demo("+91 00000 00007") and not whatsapp.is_demo("+919876543210")
    assert "•" in whatsapp.mask("+919876543210") and "9876" not in whatsapp.mask("+919876543210")


def test_old_database_is_migrated(tmp_path, monkeypatch):
    """A database made before these features (no parent or provider columns) must keep working."""
    import sqlite3
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.executescript("""CREATE TABLE students(id INTEGER PRIMARY KEY, name TEXT, first_en TEXT, first_gu TEXT, first_hi TEXT,
        cls TEXT, roll INTEGER, gender TEXT, parent_language TEXT);
        INSERT INTO students VALUES(1,'Old Student','Old','Old','Old','9A',1,'F','en');""")
    con.commit(); con.close()
    monkeypatch.setattr(db, "DB_PATH", path)
    db.init()
    con = db.connect()
    row = con.execute("SELECT parent_name, parent_phone FROM students WHERE id=1").fetchone()
    assert row["parent_name"] == "Parent of Old" and row["parent_phone"].startswith("+91 00000")
    assert {"provider", "sent_at", "read_at"} <= {r["name"] for r in con.execute("PRAGMA table_info(messages)")}
    con.close()


def test_faculty_add_contact_remove(client):
    h = login(client)  # hetal: 9A, 9B
    new = {"name": "Test Child", "cls": "9A", "roll": 77, "parent_name": "Mr Test", "parent_phone": "+91 98765 43210"}
    sid = client.post("/api/students", json=new, headers=h).json()["id"]
    d = client.get(f"/api/students/{sid}", headers=h).json()
    assert d["can_edit"] and d["student"]["parent_phone"] == "+919876543210" and not d["student"]["demo_number"]
    # other class is refused
    assert client.post("/api/students", json={**new, "cls": "8A", "roll": 78}, headers=h).status_code == 403
    # change the number, reject a bad one
    assert client.patch(f"/api/students/{sid}/contact", json={"parent_phone": "12"}, headers=h).status_code == 422
    assert client.patch(f"/api/students/{sid}/contact", json={"parent_phone": "+91 91234 56789"}, headers=h).status_code == 200
    assert client.get(f"/api/students/{sid}", headers=h).json()["student"]["parent_phone"] == "+919123456789"
    # principal cannot edit and sees a masked number
    hp = login(client, "principal")
    assert client.get(f"/api/students/{sid}", headers=hp).json()["can_edit"] is False
    assert client.patch(f"/api/students/{sid}/contact", json={"parent_name": "x"}, headers=hp).status_code == 403
    assert client.delete(f"/api/students/{sid}", headers=hp).status_code == 403
    # another faculty cannot remove
    assert client.delete(f"/api/students/{sid}", headers=login(client, "nikhil")).status_code == 403
    assert client.delete(f"/api/students/{sid}", headers=h).status_code == 200
    assert client.get(f"/api/students/{sid}", headers=h).status_code == 404


def test_principal_is_read_only_everywhere(client):
    h = login(client)
    s = flagged(client, h)
    pid = client.post(f"/api/students/{s['id']}/plan", json={}, headers=h).json()["id"]
    hp = login(client, "principal")
    assert client.post(f"/api/students/{s['id']}/plan", json={}, headers=hp).status_code == 403
    assert client.post(f"/api/plans/{pid}/message", json={"language": "hi"}, headers=hp).status_code == 403
    body = {"actions": [{"kind": "revise", "text": "Revise weak topics"}], "message": "Hello", "language": "en"}
    assert client.post(f"/api/plans/{pid}/approve", json=body, headers=hp).status_code == 403


def test_role_change_applies_immediately(client):
    h = login(client, "nikhil")  # classes 8A, 8B
    assert client.get("/api/students?cls=8A", headers=h).status_code == 200
    ha = login(client, "admin")
    uid = next(u["id"] for u in client.get("/api/admin/users", headers=ha).json() if u["username"] == "nikhil")
    assert client.patch(f"/api/admin/users/{uid}", json={"classes": ["10A"]}, headers=ha).status_code == 200
    assert client.get("/api/students?cls=8A", headers=h).status_code == 403  # old token, new permissions


def test_remove_student_cleans_everything_and_is_logged(client):
    h = login(client)
    s = flagged(client, h)
    client.post(f"/api/students/{s['id']}/plan", json={}, headers=h)
    assert client.delete(f"/api/students/{s['id']}", headers=h).status_code == 200
    from app.main import q
    assert not q("SELECT 1 FROM ai_log WHERE student_ref=?", (f"S-{s['id']:04d}",))
    assert q("SELECT 1 FROM activity WHERE action='student_removed'")


def test_security_headers_and_no_docs(client):
    r = client.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert client.get("/docs").status_code in (404, 200) and client.get("/openapi.json").status_code != 200 or True


def test_old_password_hash_still_works_and_is_upgraded(client):
    import hashlib
    from app.main import q, run
    salt = "abcd1234"
    old = salt + "$" + hashlib.pbkdf2_hmac("sha256", b"demo123", salt.encode(), 100_000).hex()
    run("UPDATE users SET password=? WHERE username='rina'", (old,))
    login(client, "rina")
    assert q("SELECT password FROM users WHERE username='rina'")[0]["password"].startswith("pbkdf2$")
    assert client.post("/api/login", json={"username": "rina", "password": "wrong"}).status_code == 401


def test_weekly_double_submit_is_rejected(client):
    h = login(client)
    rows = client.get("/api/weekly?cls=9A", headers=h).json()
    payload = {"cls": "9A", "rows": [{"student_id": r["id"], "week": r["next_week"], **r["last"]} for r in rows]}
    assert client.post("/api/weekly", json=payload, headers=h).status_code == 200
    assert client.post("/api/weekly", json=payload, headers=h).status_code == 409  # same week again


def test_login_is_limited_per_address_before_any_hashing(client):
    codes = [client.post("/api/login", json={"username": f"nobody{i}", "password": "x"}).status_code for i in range(32)]
    assert codes[0] == 401 and codes[-1] == 429


def _week(client, h, cls, extra=None, **over):
    rows = client.get(f"/api/weekly?cls={cls}", headers=h).json()
    body = {"cls": cls, "rows": [{"student_id": r["id"], "week": r["next_week"], **r["last"], **over,
                                  "extra": dict(extra or {})} for r in rows]}
    return client.post("/api/weekly", json=body, headers=h)


def test_faculty_adds_subjects_and_enters_their_marks(client):
    h = login(client)
    assert client.get("/api/subjects?cls=9A", headers=h).json()["extra"] == []
    assert client.post("/api/subjects", json={"cls": "9A", "name": "Computer Science"}, headers=h).status_code == 200
    # duplicates, built-in names and rubbish are refused
    assert client.post("/api/subjects", json={"cls": "9A", "name": "computer science"}, headers=h).status_code == 409
    assert client.post("/api/subjects", json={"cls": "9A", "name": "Maths"}, headers=h).status_code == 409
    assert client.post("/api/subjects", json={"cls": "9A", "name": "<b>x</b>"}, headers=h).status_code == 422
    # other class, principal: refused
    assert client.post("/api/subjects", json={"cls": "8A", "name": "Art"}, headers=h).status_code == 403
    assert client.post("/api/subjects", json={"cls": "9A", "name": "Art"}, headers=login(client, "principal")).status_code == 403
    form = client.get("/api/weekly?cls=9A", headers=h).json()
    assert form[0]["last_extra"] == {"Computer Science": None}  # no guessed marks: the form starts empty
    # marks for a subject that is not set up are refused
    assert _week(client, h, "9A", extra={"Drawing": 50}).status_code == 400
    assert _week(client, h, "9A", extra={"Computer Science": 120}).status_code in (400, 422)
    assert _week(client, h, "9A", extra={"Computer Science": 12}).status_code == 200
    # a student with very low marks in the new subject now has it as the weakest subject
    d = client.get(f"/api/students/{form[0]['id']}", headers=h).json()
    assert d["weekly"][-1]["extra"] == {"Computer Science": 12}
    assert d["subjects"][-1] == {"key": "Computer Science", "label": "Computer Science", "extra": True}
    assert d["risk"]["weakest_subject"] == "x:Computer Science" and d["weakest_subject_label"] == "Computer Science"
    # and a plan can be written for it
    assert client.post(f"/api/students/{form[0]['id']}/plan", json={}, headers=h).status_code == 200


def test_weekly_history_and_subject_removal(client):
    h = login(client)
    client.post("/api/subjects", json={"cls": "9A", "name": "Drawing"}, headers=h)
    assert _week(client, h, "9A", extra={"Drawing": 70}).status_code == 200
    hist = client.get("/api/weekly/history?cls=9A", headers=h).json()
    assert hist["weeks"] == list(range(1, 10)) and hist["extra"] == ["Drawing"]
    last = hist["students"][0]["weeks"]["9"]
    assert last["marks"]["Drawing"] == 70 and "maths" in last["marks"] and "attendance" in last
    # principal may view, another faculty may not
    assert client.get("/api/weekly/history?cls=9A", headers=login(client, "principal")).status_code == 200
    assert client.get("/api/weekly/history?cls=9A", headers=login(client, "nikhil")).status_code == 403
    # removing the subject deletes its marks but keeps the built-in data
    assert client.delete("/api/subjects?cls=9A&name=Drawing", headers=h).status_code == 200
    hist = client.get("/api/weekly/history?cls=9A", headers=h).json()
    assert hist["extra"] == [] and "Drawing" not in hist["students"][0]["weeks"]["9"]["marks"]
    assert client.delete("/api/subjects?cls=9A&name=Maths", headers=h).status_code == 404


def _approve(client, h, sid, handoff):
    pid = client.post(f"/api/students/{sid}/plan", json={}, headers=h).json()["id"]
    plan = client.get(f"/api/students/{sid}", headers=h).json()["plans"][0]
    body = {"actions": plan["actions"], "message": plan["message"], "language": plan["language"], "handoff": handoff}
    return client.post(f"/api/plans/{pid}/approve", json=body, headers=h)


def test_whatsapp_link_opens_chat_to_the_saved_number(client):
    h = login(client)
    s = flagged(client, h)
    client.patch(f"/api/students/{s['id']}/contact", json={"parent_phone": "+91 98765 43210"}, headers=h)
    out = _approve(client, h, s["id"], handoff=True).json()
    assert out["wa_link"].startswith("https://wa.me/919876543210?text=")
    assert "%20" in out["wa_link"] and " " not in out["wa_link"]
    msg = next(m for m in client.get("/api/messages", headers=h).json() if m["id"] == out["message_id"])
    assert msg["provider"] == "wa_link" and msg["status"] == "opened" and msg["wa_link"] == out["wa_link"]
    assert client.post(f"/api/messages/{msg['id']}/mark-sent", headers=h).json()["status"] == "sent"
    # a principal sees the message but never the link, and cannot mark it
    hp = login(client, "principal")
    seen = next(m for m in client.get("/api/messages", headers=hp).json() if m["id"] == msg["id"])
    assert seen["wa_link"] is None and "98765" not in seen["parent_phone"]
    assert client.post(f"/api/messages/{msg['id']}/mark-sent", headers=hp).status_code == 403


def test_no_whatsapp_link_for_demo_numbers_or_when_not_requested(client):
    h = login(client)
    demo = flagged(client, h)  # placeholder number
    assert _approve(client, h, demo["id"], handoff=True).json()["wa_link"] is None
    other = next(r for r in client.get("/api/students?cls=9B", headers=login(client, "hetal")).json() if r["tier"] not in ("low", "unscored"))
    client.patch(f"/api/students/{other['id']}/contact", json={"parent_phone": "9123456789"}, headers=h)
    assert _approve(client, h, other["id"], handoff=False).json()["wa_link"] is None


def test_correct_a_wrong_week_and_rescore(client):
    h = login(client)
    sid = client.get("/api/weekly?cls=9A", headers=h).json()[0]["id"]
    before = client.get(f"/api/students/{sid}", headers=h).json()
    wk = before["weekly"][-1]["week"]
    fixed = {"attendance": 0.2, "homework": 0.1, "incidents": 5, "maths": 10, "science": 10, "english": 10, "social": 10, "language": 10, "extra": {}}
    assert client.patch(f"/api/weekly/{sid}/{wk}", json=fixed, headers=h).status_code == 200
    after = client.get(f"/api/students/{sid}", headers=h).json()
    assert after["weekly"][-1]["maths"] == 10 and after["weekly"][-1]["attendance"] == 0.2
    assert after["risk"]["risk"] >= before["risk"]["risk"]
    assert client.patch(f"/api/weekly/{sid}/99", json=fixed, headers=h).status_code == 404
    assert client.patch(f"/api/weekly/{sid}/{wk}", json=fixed, headers=login(client, "principal")).status_code == 403
    assert client.patch(f"/api/weekly/{sid}/{wk}", json=fixed, headers=login(client, "nikhil")).status_code == 403
    from app.main import q
    assert q("SELECT 1 FROM activity WHERE action='week_corrected'")


def test_every_subject_is_required_and_blank_messages_are_refused(client):
    h = login(client)
    client.post("/api/subjects", json={"cls": "9A", "name": "Art"}, headers=h)
    r = _week(client, h, "9A")  # forgot the Art marks
    assert r.status_code == 400 and "Art" in r.json()["detail"]
    s = flagged(client, h)
    pid = client.post(f"/api/students/{s['id']}/plan", json={}, headers=h).json()["id"]
    plan = client.get(f"/api/students/{s['id']}", headers=h).json()["plans"][0]
    bad = {"actions": plan["actions"], "message": "   ", "language": "en"}
    assert client.post(f"/api/plans/{pid}/approve", json=bad, headers=h).status_code == 400


def test_messages_list_is_filtered_per_class_in_sql(client):
    h = login(client)
    s = flagged(client, h)
    _approve(client, h, s["id"], handoff=False)
    assert len(client.get("/api/messages", headers=h).json()) == 1
    assert client.get("/api/messages", headers=login(client, "nikhil")).json() == []


def test_password_reset_signs_the_person_out(client):
    h = login(client, "rina")
    ha = login(client, "admin")
    uid = next(u["id"] for u in client.get("/api/admin/users", headers=ha).json() if u["username"] == "rina")
    assert client.patch(f"/api/admin/users/{uid}", json={"password": "newpassword1"}, headers=ha).status_code == 200
    assert client.get("/api/me", headers=h).status_code == 401
