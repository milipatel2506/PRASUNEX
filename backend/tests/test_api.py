"""Automated tests for SAARTHI: access control, approval safety, guardrails, model sanity.

Run from the backend folder:  .venv\\Scripts\\python -m pytest -q
Each test uses a throwaway database, so the demo data is never touched.
"""
import pytest
from fastapi.testclient import TestClient

from app import actions, db, model
from app.main import FAILS, TOKENS, app, IP_ATTEMPTS


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db, "PW_ITERS", 1000)  # fast hashing for tests; the stored hash records its own count
    FAILS.clear()
    IP_ATTEMPTS.clear()
    TOKENS.clear()
    with TestClient(app) as c:
        yield c


def login(c, user="hetal", pw="demo123"):
    r = c.post("/api/login", json={"username": user, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


def first_flagged(c, h, cls="9A"):
    rows = c.get(f"/api/students?cls={cls}", headers=h).json()
    return next(r for r in rows if r["tier"] != "low")


# ---------- login and access control ----------
def test_wrong_password_rejected(client):
    assert client.post("/api/login", json={"username": "hetal", "password": "nope"}).status_code == 401


def test_login_throttled_after_repeated_failures(client):
    for _ in range(5):
        client.post("/api/login", json={"username": "hetal", "password": "bad"})
    assert client.post("/api/login", json={"username": "hetal", "password": "demo123"}).status_code == 429


def test_passwords_are_hashed():
    assert db.check_pw("demo123", db.hash_pw("demo123"))
    assert not db.check_pw("other", db.hash_pw("demo123"))
    assert "demo123" not in db.hash_pw("demo123")


def test_requires_sign_in(client):
    assert client.get("/api/classes").status_code == 401


def test_logout_invalidates_token(client):
    h = login(client)
    assert client.post("/api/logout", headers=h).status_code == 200
    assert client.get("/api/me", headers=h).status_code == 401


def test_me_does_not_leak_token(client):
    h = login(client)
    assert set(client.get("/api/me", headers=h).json()) == {"username", "name", "role", "classes"}


def test_teacher_cannot_open_other_class(client):
    h = login(client, "hetal")  # teaches 9A and 9B
    assert client.get("/api/students?cls=8A", headers=h).status_code == 403


def test_teacher_cannot_open_other_teachers_student(client):
    other = login(client, "nikhil")
    sid = client.get("/api/students?cls=8A", headers=other).json()[0]["id"]
    mine = login(client, "hetal")
    assert client.get(f"/api/students/{sid}", headers=mine).status_code == 403
    assert client.post(f"/api/students/{sid}/plan", json={}, headers=mine).status_code == 403


def test_principal_only_endpoints(client):
    teacher, principal = login(client, "hetal"), login(client, "principal")
    for path in ("/api/principal/overview", "/api/audit"):
        assert client.get(path, headers=teacher).status_code == 403
        assert client.get(path, headers=principal).status_code == 200


def test_health_does_not_reveal_ai_configuration(client):
    assert set(client.get("/api/health").json()) == {"ok", "languages"}


def test_student_detail_does_not_expose_gender(client):
    h = login(client)
    sid = first_flagged(client, h)["id"]
    assert "gender" not in client.get(f"/api/students/{sid}", headers=h).json()["student"]


# ---------- plans, messages, approval ----------
def make_plan(c, h, lang="gu"):
    sid = first_flagged(c, h)["id"]
    r = c.post(f"/api/students/{sid}/plan", json={"language": lang}, headers=h)
    assert r.status_code == 200, r.text
    return sid, r.json()


@pytest.mark.parametrize("lang", ["en", "gu", "hi"])
def test_plan_has_three_actions_and_clean_message(client, lang):
    _, plan = make_plan(client, login(client), lang)
    assert len(plan["actions"]) == 3
    assert plan["flags"] == []
    assert plan["message"].strip()


def test_message_uses_student_name_in_message_script(client):
    _, plan = make_plan(client, login(client), "gu")
    assert "{student_name}" not in plan["message"]
    letters = [c for c in plan["message"] if c.isalpha()]
    assert sum(0x0A80 <= ord(c) <= 0x0AFF for c in letters) / len(letters) > 0.6


def approve_body(plan, **over):
    body = {"actions": plan["actions"], "message": plan["message"], "language": plan["language"]}
    body.update(over)
    return body


def test_approve_then_second_approve_conflicts(client):
    h = login(client)
    _, plan = make_plan(client, h)
    assert client.post(f"/api/plans/{plan['id']}/approve", json=approve_body(plan), headers=h).status_code == 200
    assert client.post(f"/api/plans/{plan['id']}/approve", json=approve_body(plan), headers=h).status_code == 409
    p = login(client, "principal")
    assert client.get("/api/principal/overview", headers=p).json()["stats"]["messages_sent"] == 1


def test_approve_blocks_phone_numbers_links_and_emails(client):
    h = login(client)
    _, plan = make_plan(client, h, "en")
    for bad in ("Call +91 98765 43210 now", "visit https://example.com", "mail me at a@b.com", "ring 98765-43210"):
        r = client.post(f"/api/plans/{plan['id']}/approve", json=approve_body(plan, message=bad, language="en"), headers=h)
        assert r.status_code == 422, bad


def test_approve_rejects_bad_language_kind_and_size(client):
    h = login(client)
    _, plan = make_plan(client, h)
    url = f"/api/plans/{plan['id']}/approve"
    assert client.post(url, json=approve_body(plan, language="xx"), headers=h).status_code == 400
    bad_kind = [{"kind": "hack", "text": "x"}] * 3
    assert client.post(url, json=approve_body(plan, actions=bad_kind), headers=h).status_code == 400
    assert client.post(url, json=approve_body(plan, actions=plan["actions"] * 2), headers=h).status_code == 422
    assert client.post(url, json=approve_body(plan, message="x" * 2000), headers=h).status_code == 422


def test_cannot_retranslate_after_approval(client):
    h = login(client)
    _, plan = make_plan(client, h)
    client.post(f"/api/plans/{plan['id']}/approve", json=approve_body(plan), headers=h)
    r = client.post(f"/api/plans/{plan['id']}/message", json={"language": "hi"}, headers=h)
    assert r.status_code == 409


def test_audit_log_stores_only_anonymised_input_and_final_text(client):
    h = login(client)
    sid, plan = make_plan(client, h)
    student = client.get(f"/api/students/{sid}", headers=h).json()["student"]
    client.post(f"/api/plans/{plan['id']}/approve", json=approve_body(plan), headers=h)
    rows = client.get("/api/audit", headers=login(client, "principal")).json()
    text = str(rows[0]["input"])
    assert student["first_en"] not in text and student["name"] not in text
    assert rows[0]["input"]["student_ref"].startswith("S-")
    assert rows[0]["output"]["final_after_teacher_edit"] is True
    assert rows[0]["approved_by"]


def test_outcome_validation_and_logging(client):
    h = login(client)
    sid, plan = make_plan(client, h)
    client.post(f"/api/plans/{plan['id']}/approve", json=approve_body(plan), headers=h)
    iid = client.get(f"/api/students/{sid}", headers=h).json()["interventions"][0]["id"]
    assert client.post(f"/api/interventions/{iid}/outcome", json={"outcome": "bogus"}, headers=h).status_code == 400
    assert client.post(f"/api/interventions/{iid}/outcome", json={"outcome": "improved"}, headers=h).status_code == 200


# ---------- risk model ----------
def test_low_risk_students_get_no_reasons(client):
    rows = client.get("/api/students?cls=9A", headers=login(client)).json()
    assert all(r["reasons"] == [] for r in rows if r["tier"] == "low")
    assert all(1 <= len(r["reasons"]) <= 3 for r in rows if r["tier"] != "low")


def test_students_sorted_by_risk(client):
    risks = [r["risk"] for r in client.get("/api/students?cls=9A", headers=login(client)).json()]
    assert risks == sorted(risks, reverse=True)


def test_model_beats_manual_rule_at_equal_flag_share():
    m = model.load()["metrics"]
    assert m["auc"] > 0.9
    eq = m["equal_flag"]
    assert eq["model_precision"] > eq["rule_precision"]
    assert eq["model_recall"] > eq["rule_recall"]


# ---------- guardrails ----------
def test_guardrails_flag_wrong_script_and_banned_words():
    assert "wrong_script" in actions.check_message("This is plain English text only", "gu")
    assert any(f.startswith("banned_phrase") for f in actions.check_message("Your child is lazy", "en"))
    assert actions.check_message("We are failing to reach home, so please call the school", "en") == []


def test_guardrails_do_not_flag_normal_numbers():
    assert actions.check_message("Please revise 20 minutes each evening. Class 10A.", "en") == []


def test_llm_plan_schema_validation():
    good = {"actions": [{"kind": "progress_check", "text": "ok"}] * 3, "parent_message": "Hello {student_name}"}
    assert actions.validate_plan(good, "en") == []
    assert "bad_actions_schema" in actions.validate_plan({**good, "actions": good["actions"][:2]}, "en")
    assert "bad_actions_schema" in actions.validate_plan({**good, "actions": [{"text": 5}] * 3}, "en")
    assert "missing_name_placeholder" in actions.validate_plan({**good, "parent_message": "Hello"}, "en")


def test_llm_input_has_no_names(client):
    h = login(client)
    d = client.get(f"/api/students/{first_flagged(client, h)['id']}", headers=h).json()
    ctx = actions.build_context(d["student"], d["risk"])
    assert d["student"]["first_en"] not in str(ctx["llm_input"])
    assert set(ctx["llm_input"]) == {"student_ref", "grade", "risk_tier", "reasons", "weakest_subject", "suggested_topics"}
