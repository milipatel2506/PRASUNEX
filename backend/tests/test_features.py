"""Tests for admin/faculty roles, weekly data entry, student and user management, messages outbox, WhatsApp."""
import pytest
from fastapi.testclient import TestClient

from app import db, whatsapp
from app.main import FAILS, TOKENS, app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("TWILIO_WHATSAPP_FROM", raising=False)
    FAILS.clear()
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
