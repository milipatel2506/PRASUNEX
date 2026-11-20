"""SQLite storage + seeding of the synthetic demo school."""
from __future__ import annotations
import hashlib
import json
import secrets
import sqlite3
import time
from pathlib import Path

import numpy as np

from . import datagen, model
from .names import FIRST, SURNAMES

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "saarthi.db"
CLASSES = ["8A", "8B", "9A", "9B", "10A"]
PER_CLASS = 30
CURRENT_WEEK = 8
SUBJ = datagen.SUBJECTS

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT, name TEXT,
  role TEXT, classes TEXT);
CREATE TABLE IF NOT EXISTS students(id INTEGER PRIMARY KEY, name TEXT, first_en TEXT, first_gu TEXT, first_hi TEXT,
  cls TEXT, roll INTEGER, gender TEXT, parent_language TEXT);
CREATE TABLE IF NOT EXISTS weekly(student_id INTEGER, week INTEGER, attendance REAL, homework REAL, incidents INTEGER,
  maths REAL, science REAL, english REAL, social REAL, language REAL, PRIMARY KEY(student_id, week));
CREATE TABLE IF NOT EXISTS risk(student_id INTEGER PRIMARY KEY, risk REAL, tier TEXT, reasons TEXT,
  weakest_subject TEXT, asof_week INTEGER);
CREATE TABLE IF NOT EXISTS plans(id INTEGER PRIMARY KEY, student_id INTEGER, created_at TEXT, provider TEXT,
  language TEXT, actions TEXT, topics TEXT, message TEXT, flags TEXT, status TEXT DEFAULT 'draft',
  approved_by TEXT, approved_at TEXT);
CREATE TABLE IF NOT EXISTS interventions(id INTEGER PRIMARY KEY, student_id INTEGER, plan_id INTEGER, kind TEXT,
  text TEXT, outcome TEXT, created_at TEXT, source TEXT);
CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, plan_id INTEGER, student_id INTEGER, channel TEXT,
  language TEXT, body TEXT, status TEXT, ts TEXT);
CREATE TABLE IF NOT EXISTS ai_log(id INTEGER PRIMARY KEY, ts TEXT, student_ref TEXT, provider TEXT, language TEXT,
  input TEXT, output TEXT, flags TEXT, approved_by TEXT, plan_id INTEGER);
"""

USERS = [
    ("hetal", "demo123", "Ms. Hetal Shah", "teacher", ["9A", "9B"]),
    ("nikhil", "demo123", "Mr. Nikhil Desai", "teacher", ["8A", "8B"]),
    ("rina", "demo123", "Ms. Rina Joshi", "teacher", ["10A"]),
    ("principal", "demo123", "Dr. Anil Mehta", "principal", CLASSES),
    ("admin", "demo123", "Mr. Rajesh Patel", "admin", CLASSES),
]

# Columns added after the first release. Applied on every start so older demo databases keep working.
MIGRATIONS = {
    "students": {"parent_name": "TEXT", "parent_phone": "TEXT"},
    "users": {"active": "INTEGER DEFAULT 1"},
    "messages": {"parent_phone": "TEXT", "provider": "TEXT DEFAULT 'simulated'", "provider_sid": "TEXT",
                 "error": "TEXT", "sent_at": "TEXT", "delivered_at": "TEXT", "read_at": "TEXT"},
}
# Probability that an action of this kind led to improvement (used only for the seeded "last term" history).
KIND_SUCCESS = {"parent_contact": 0.62, "remedial_session": 0.72, "practice_test": 0.55, "homework_checklist": 0.58,
                "counselling": 0.5, "peer_support": 0.52, "progress_check": 0.4, "goal_setting": 0.54}


def now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def hash_pw(pw: str) -> str:
    salt = secrets.token_hex(8)
    return salt + "$" + hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 100_000).hex()


def check_pw(pw: str, stored: str) -> bool:
    try:
        salt, digest = stored.split("$", 1)
    except ValueError:
        return False
    test = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 100_000).hex()
    return secrets.compare_digest(test, digest)


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def migrate(con: sqlite3.Connection) -> None:
    for table, cols in MIGRATIONS.items():
        have = {r["name"] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}
        for col, decl in cols.items():
            if col not in have:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
    con.execute("UPDATE users SET active=1 WHERE active IS NULL")
    con.execute("UPDATE students SET parent_name='Parent of ' || first_en WHERE parent_name IS NULL")
    con.execute("UPDATE students SET parent_phone='+91 00000 ' || printf('%05d', id) WHERE parent_phone IS NULL")
    con.commit()


def init() -> None:
    con = connect()
    try:
        con.executescript(SCHEMA)
        migrate(con)
        if con.execute("SELECT COUNT(*) FROM students").fetchone()[0] == 0:
            seed(con)
            migrate(con)
    finally:
        con.close()


def seed(con: sqlite3.Connection) -> None:
    n = len(CLASSES) * PER_CLASS
    rng = np.random.default_rng(11)
    d = datagen.generate(n, 2026)
    X, weak = datagen.features(d, CURRENT_WEEK)
    scores = model.score(X)

    for u in USERS:
        con.execute("INSERT INTO users(username,password,name,role,classes,active) VALUES(?,?,?,?,?,1)",
                    (u[0], hash_pw(u[1]), u[2], u[3], json.dumps(u[4])))
    used = set()
    langs = rng.choice(["gu", "hi", "en"], n, p=[0.5, 0.3, 0.2])
    for i in range(n):
        while True:
            f = FIRST[rng.integers(len(FIRST))]
            s = SURNAMES[rng.integers(len(SURNAMES))]
            if (f[0], s) not in used:
                used.add((f[0], s))
                break
        cls = CLASSES[i // PER_CLASS]
        con.execute("INSERT INTO students(id,name,first_en,first_gu,first_hi,cls,roll,gender,parent_language) "
                    "VALUES(?,?,?,?,?,?,?,?,?)",
                    (i + 1, f"{f[0]} {s}", f[0], f[1], f[2], cls, i % PER_CLASS + 1, str(d["gender"][i]), str(langs[i])))
        for w in range(CURRENT_WEEK):
            m = d["marks"][i, w]
            con.execute("INSERT INTO weekly VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (i + 1, w + 1, float(d["att"][i, w]), float(d["hw"][i, w]), int(d["inc"][i, w]),
                         *[float(x) for x in m]))
        sc = scores[i]
        con.execute("INSERT INTO risk VALUES(?,?,?,?,?,?)",
                    (i + 1, sc["risk"], sc["tier"], json.dumps(sc["reasons"]), SUBJ[int(weak[i])], CURRENT_WEEK))

    # Seeded "last term" intervention history so the effectiveness chart has something to show.
    kinds = list(KIND_SUCCESS)
    for _ in range(96):
        k = kinds[rng.integers(len(kinds))]
        out = "improved" if rng.random() < KIND_SUCCESS[k] else ("no_change" if rng.random() < 0.7 else "declined")
        con.execute("INSERT INTO interventions(student_id,plan_id,kind,text,outcome,created_at,source) "
                    "VALUES(NULL,NULL,?,?,?,?,?)", (k, k.replace("_", " "), out, "2026-08-15", "last term (demo data)"))
    con.commit()


def reset() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()
    init()


if __name__ == "__main__":
    reset()
    print("database reset and seeded:", DB_PATH)
